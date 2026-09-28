"""
CCTV — watching the house through its WiFi cameras.

Any camera that speaks RTSP (almost every IP camera: Hikvision, Dahua, CP Plus,
Imou, TP-Link Tapo, EZVIZ, Reolink, Uniview, Amcrest, Axis…), serves MJPEG or
JPEG snapshots over HTTP (ESP32-CAM, Android "IP Webcam", DroidCam), is
reachable through Home Assistant (cloud-only cameras such as Ring, Nest,
Xiaomi, Blink via their HA integrations), or is a second USB webcam.

    readers    one thread per camera keeps the newest frame; streams are opened
               over TCP, re-opened with back-off when a camera drops, and read
               at a low rate so a sub-stream costs a few % of one core
    analyser   one thread visits every camera ~1-2× a second: a motion check
               on a 96-px thumbnail, and only when something moved, object
               detection (people, vehicles, animals) and face recognition
    events     "person at Front Door — Rahul", "car at Gate", "unknown person
               at Back Yard": an annotated snapshot is saved in
               memory/cctv_events/<date>/, a line goes to the journal (which
               the learning memory reads), and a vision model describes the
               scene when one is available
    reacting   by mode —
                 home   announce people at the cameras by voice (who, if known)
                 night  as home, and an unknown person also goes to Telegram
                 away   everything notable goes to Telegram with the photo
                 off    cameras are only watched on request

Configuration: memory/cctv.json (cameras with their stream URLs, which include
passwords — the file stays on this PC and is excluded from the repository).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlparse, urlunparse

import numpy as np

from core import brain_config, journal, runtime

# RTSP over TCP: UDP loses packets on WiFi and smears the picture.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;8000000")

CFG_FILE = brain_config.BASE_DIR / "memory" / "cctv.json"
EVENTS_DIR = brain_config.BASE_DIR / "memory" / "cctv_events"
MODES = ("home", "night", "away", "off")
DEFAULT_DETECT = ["person", "car", "motorcycle", "bicycle", "truck", "bus", "dog", "cat"]

# Stream URL templates. Sub-streams where the brand has one: detection needs
# 640 px, and decoding 4K for it wastes a CPU core per camera.
BRANDS = {
    "hikvision": ("rtsp://{auth}{ip}:{port}/Streaming/Channels/{ch}02", 554,
                  "Hikvision / HiLook / Annke"),
    "dahua": ("rtsp://{auth}{ip}:{port}/cam/realmonitor?channel={ch}&subtype=1", 554,
              "Dahua / CP Plus / Imou / Amcrest / Lorex"),
    "cpplus": ("rtsp://{auth}{ip}:{port}/cam/realmonitor?channel={ch}&subtype=1", 554, "CP Plus"),
    "imou": ("rtsp://{auth}{ip}:{port}/cam/realmonitor?channel={ch}&subtype=1", 554, "Imou"),
    "tapo": ("rtsp://{auth}{ip}:{port}/stream2", 554,
             "TP-Link Tapo (create a camera account in the Tapo app: Advanced → Camera Account)"),
    "ezviz": ("rtsp://{auth}{ip}:{port}/h264/ch1/sub/av_stream", 554,
              "EZVIZ (user admin, password = the verification code on the label)"),
    "reolink": ("rtsp://{auth}{ip}:{port}/h264Preview_{ch2}_sub", 554, "Reolink"),
    "uniview": ("rtsp://{auth}{ip}:{port}/unicast/c{ch}/s1/live", 554, "Uniview"),
    "hanwha": ("rtsp://{auth}{ip}:{port}/profile2/media.smp", 554, "Hanwha / Wisenet"),
    "axis": ("rtsp://{auth}{ip}:{port}/axis-media/media.amp?resolution=640x480", 554, "Axis"),
    "foscam": ("rtsp://{auth}{ip}:{port}/videoSub", 88, "Foscam"),
    "wyze": ("rtsp://{auth}{ip}:{port}/live", 554, "Wyze (RTSP firmware)"),
    "esp32cam": ("http://{ip}:{port}/stream", 81, "ESP32-CAM (CameraWebServer sketch)"),
    "ipwebcam": ("http://{auth}{ip}:{port}/video", 8080, "Android IP Webcam app"),
    "droidcam": ("http://{ip}:{port}/video", 4747, "DroidCam"),
    "generic": ("rtsp://{auth}{ip}:{port}/", 554, "Any RTSP camera (give the full URL if you know it)"),
}

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def mask(url: str) -> str:
    """The URL with the password hidden, for logs and replies."""
    try:
        u = urlparse(url)
        if u.password:
            netloc = f"{u.username}:***@{u.hostname}" + (f":{u.port}" if u.port else "")
            return urlunparse(u._replace(netloc=netloc))
    except Exception:
        pass
    return url


def build_url(brand: str, ip: str, user: str = "", password: str = "", channel: int = 1,
              port: int | None = None) -> str:
    brand = (brand or "generic").lower().replace(" ", "").replace("-", "")
    tmpl, default_port, _ = BRANDS.get(brand, BRANDS["generic"])
    auth = ""
    if user or password:
        auth = f"{quote(user or '', safe='')}:{quote(password or '', safe='')}@"
    ch = max(1, int(channel or 1))
    return tmpl.format(auth=auth, ip=ip.strip(), port=int(port or default_port), ch=ch, ch2=f"{ch:02d}")


def with_credentials(url: str, user: str, password: str) -> str:
    if not user:
        return url
    u = urlparse(url)
    if u.username:
        return url
    host = u.hostname or ""
    netloc = f"{quote(user, safe='')}:{quote(password or '', safe='')}@{host}" + (f":{u.port}" if u.port else "")
    return urlunparse(u._replace(netloc=netloc))


# ── configuration ────────────────────────────────────────────────────────────

def load_cfg() -> dict:
    try:
        data = json.loads(CFG_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("mode", "home")
    data.setdefault("cameras", [])
    data.setdefault("settings", {})
    st = data["settings"]
    st.setdefault("analysis_fps", 1.5)
    st.setdefault("announce_cooldown", 120)
    st.setdefault("telegram_cooldown", 60)
    st.setdefault("keep_days", 7)
    st.setdefault("describe_events", True)
    st.setdefault("announce_vehicles", False)
    return data


def save_cfg(data: dict) -> None:
    with _lock:
        CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CFG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CFG_FILE)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "camera").lower()).strip("_") or "camera"


def find_camera(data: dict, name: str) -> dict | None:
    key = (name or "").strip().lower()
    if not key:
        return None
    for c in data["cameras"]:
        if c["name"].lower() == key or c["id"] == key:
            return c
    for c in data["cameras"]:
        if key in c["name"].lower() or c["name"].lower() in key:
            return c
    return None


# ── reading frames ───────────────────────────────────────────────────────────

def _kind(url: str) -> str:
    low = (url or "").lower()
    if low.startswith("ha:"):
        return "ha"
    if re.fullmatch(r"(usb|webcam)?:?\d+", low):
        return "usb"
    if low.startswith(("http://", "https://")) and re.search(r"\.(jpe?g|png)(\?|$)|snapshot|snap\.|/jpg|"
                                                              r"image\.cgi|capture", low):
        return "snapshot"
    return "stream"


def _ha_snapshot(entity: str, timeout: float = 8.0):
    import requests
    try:
        from memory.config_manager import get_plugin_config
        c = get_plugin_config("smart_home")
    except Exception:
        c = {}
    base, token = str(c.get("ha_url") or "").rstrip("/"), c.get("ha_token") or ""
    if not base or not token:
        raise RuntimeError("Home Assistant is not connected (⚙ PLUGIN SETTINGS → Smart Home)")
    r = requests.get(f"{base}/api/camera_proxy/{entity}", headers={"Authorization": f"Bearer {token}"},
                     timeout=timeout)
    r.raise_for_status()
    return r.content


def _decode(jpeg: bytes):
    import cv2
    arr = np.frombuffer(jpeg, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def grab_once(url: str, timeout: float = 12.0):
    """One frame from a camera URL (used to test a camera before saving it)."""
    import cv2
    kind = _kind(url)
    if kind == "ha":
        return _decode(_ha_snapshot(url[3:], timeout))
    if kind == "snapshot":
        import requests
        u = urlparse(url)
        auth = None
        if u.username:
            from requests.auth import HTTPDigestAuth
            clean = urlunparse(u._replace(netloc=u.hostname + (f":{u.port}" if u.port else "")))
            r = requests.get(clean, timeout=timeout, auth=(u.username, u.password or ""))
            if r.status_code == 401:
                r = requests.get(clean, timeout=timeout, auth=HTTPDigestAuth(u.username, u.password or ""))
        else:
            r = requests.get(url, timeout=timeout, auth=auth)
        r.raise_for_status()
        return _decode(r.content)
    if kind == "usb":
        idx = int(re.sub(r"\D", "", url) or 0)
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
    else:
        cap = _open_capture(url, timeout)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if ok and frame is not None:
                return frame
            time.sleep(0.1)
        return None
    finally:
        cap.release()


def _open_capture(url: str, timeout: float = 10.0):
    import cv2
    params = []
    for prop, val in (("CAP_PROP_OPEN_TIMEOUT_MSEC", int(timeout * 1000)),
                      ("CAP_PROP_READ_TIMEOUT_MSEC", int(timeout * 1000)),
                      ("CAP_PROP_HW_ACCELERATION", getattr(cv2, "VIDEO_ACCELERATION_ANY", None))):
        pid = getattr(cv2, prop, None)
        if pid is not None and val is not None:
            params += [pid, val]
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, params)
    except Exception:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(url)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    except Exception:
        pass
    return cap


class Feed:
    """Keeps the newest frame of one camera."""

    def __init__(self, cam: dict, log: Callable[[str], None]):
        self.cam = dict(cam)
        self.id = cam["id"]
        self.name = cam["name"]
        self._log = log
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.frame = None
        self.ts = 0.0
        self.status = "connecting"
        self.error = ""
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"cctv-{self.id}")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def alive(self) -> bool:
        return self._thread.is_alive()

    def latest(self, max_age: float = 10.0):
        with self._lock:
            if self.frame is None or time.monotonic() - self.ts > max_age:
                return None
            return self.frame

    def _set(self, frame) -> None:
        with self._lock:
            self.frame = frame
            self.ts = time.monotonic()
        if self.status != "online":
            if self.status in ("offline", "error"):
                self._log(f"SYS: 📹 {self.name} is back online.")
            self.status, self.error = "online", ""

    def _fail(self, why: str) -> None:
        if self.status == "online":
            self._log(f"ERR: 📹 {self.name} went offline — {why[:100]}")
        self.status, self.error = ("offline" if self.status == "online" else "error"), why

    def _run(self) -> None:
        url = str(self.cam.get("url") or "")
        kind = _kind(url)
        backoff = 5.0
        while not self._stop.is_set():
            try:
                if kind in ("snapshot", "ha"):
                    period = float(self.cam.get("snapshot_seconds", 2.0) or 2.0)
                    while not self._stop.is_set():
                        frame = grab_once(url, timeout=10)
                        if frame is None:
                            raise RuntimeError("no image")
                        self._set(frame)
                        backoff = 5.0
                        self._stop.wait(period)
                    return
                import cv2
                if kind == "usb":
                    idx = int(re.sub(r"\D", "", url) or 0)
                    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
                else:
                    cap = _open_capture(url)
                if not cap.isOpened():
                    raise RuntimeError("stream did not open (address, port, user or password wrong?)")
                last_ret, fails = 0.0, 0
                try:
                    while not self._stop.is_set():
                        if not cap.grab():
                            fails += 1
                            if fails > 25:
                                raise RuntimeError("stream stopped delivering frames")
                            time.sleep(0.04)
                            continue
                        fails = 0
                        now = time.monotonic()
                        # Decoding happens in grab(); converting to a picture only
                        # 4× a second is plenty for watching and for the wall.
                        if now - last_ret >= 0.25:
                            ok, frame = cap.retrieve()
                            if ok and frame is not None:
                                self._set(frame)
                                last_ret = now
                                backoff = 5.0
                finally:
                    cap.release()
            except Exception as e:
                self._fail(str(e))
            if self._stop.wait(backoff):
                return
            backoff = min(60.0, backoff * 1.7)


# ── ONVIF: finding cameras on the network ────────────────────────────────────

_PROBE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<e:Header><w:MessageID>uuid:{mid}</w:MessageID>
<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header>
<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>"""


def discover_onvif(timeout: float = 3.0) -> list[dict]:
    """ONVIF cameras on the local network: [{ip, xaddr, name, hardware}]."""
    found: dict[str, dict] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(0.5)
        msg = _PROBE.format(mid=uuid.uuid4()).encode()
        for _ in range(2):
            sock.sendto(msg, ("239.255.255.250", 3702))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            text = data.decode("utf-8", errors="replace")
            xaddrs = re.findall(r"<[^>]*XAddrs>([^<]+)</", text)
            scopes = " ".join(re.findall(r"<[^>]*Scopes>([^<]+)</", text))
            name = re.search(r"onvif://www\.onvif\.org/name/([^\s<]+)", scopes)
            hw = re.search(r"onvif://www\.onvif\.org/hardware/([^\s<]+)", scopes)
            xaddr = next((x for x in (xaddrs[0].split() if xaddrs else []) if addr[0] in x),
                         xaddrs[0].split()[0] if xaddrs else f"http://{addr[0]}/onvif/device_service")
            found[addr[0]] = {"ip": addr[0], "xaddr": xaddr,
                              "name": requests_unquote(name.group(1)) if name else "",
                              "hardware": requests_unquote(hw.group(1)) if hw else ""}
    finally:
        sock.close()
    return sorted(found.values(), key=lambda d: tuple(int(p) for p in d["ip"].split(".") if p.isdigit()))


def requests_unquote(s: str) -> str:
    from urllib.parse import unquote
    return unquote(s or "")


def _wsse(user: str, password: str) -> str:
    if not user:
        return ""
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()
    return (
        '<s:Header><Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-wssecurity-secext-1.0.xsd"><UsernameToken><Username>' + user + '</Username>'
        '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-'
        '1.0#PasswordDigest">' + digest + '</Password><Nonce EncodingType="http://docs.oasis-open.org/wss/'
        '2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">' + base64.b64encode(nonce).decode()
        + '</Nonce><Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-'
        'utility-1.0.xsd">' + created + '</Created></UsernameToken></Security></s:Header>')


def _soap(url: str, body: str, user: str, password: str, timeout: float = 6.0) -> str:
    import requests
    env = ('<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/'
           'soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/'
           'ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">' + _wsse(user, password)
           + '<s:Body>' + body + '</s:Body></s:Envelope>')
    r = requests.post(url, data=env.encode(), timeout=timeout,
                      headers={"Content-Type": "application/soap+xml; charset=utf-8"})
    if r.status_code >= 400:
        auth = r.status_code == 401 or "NotAuthorized" in r.text
        raise RuntimeError(f"ONVIF HTTP {r.status_code}" + (" — wrong user or password" if auth else ""))
    return r.text


def onvif_stream_uris(xaddr: str, user: str, password: str) -> list[dict]:
    """[{profile, width, height, uri}] from an ONVIF camera, smallest first."""
    media = xaddr
    try:
        caps = _soap(xaddr, '<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>',
                     user, password)
        m = re.search(r"<[^>]*Media>\s*<[^>]*XAddr>([^<]+)</", caps)
        if m:
            media = m.group(1).strip()
    except Exception:
        pass
    prof = _soap(media, "<trt:GetProfiles/>", user, password)
    out = []
    for m in re.finditer(r'<[^>]*Profiles[^>]*token="([^"]+)"(.*?)</[^>]*Profiles>', prof, re.S):
        token, body = m.group(1), m.group(2)
        w = re.search(r"<[^>]*Width>(\d+)</", body)
        h = re.search(r"<[^>]*Height>(\d+)</", body)
        try:
            su = _soap(media, '<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>'
                              '<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>'
                              f'<trt:ProfileToken>{token}</trt:ProfileToken></trt:GetStreamUri>', user, password)
            uri = re.search(r"<[^>]*Uri>([^<]+)</", su)
        except Exception:
            uri = None
        if uri:
            out.append({"profile": token, "width": int(w.group(1)) if w else 0,
                        "height": int(h.group(1)) if h else 0,
                        "uri": with_credentials(uri.group(1).strip().replace("&amp;", "&"), user, password)})
    out.sort(key=lambda d: (d["width"] * d["height"]) or 1e9)
    return out


# ── the manager ──────────────────────────────────────────────────────────────

class _Track:
    def __init__(self):
        self.window: list[dict] = []          # per-analysis label counts
        self.present: set[str] = set()
        self.last_event: dict[str, float] = {}
        self.bg = None
        self.last_full = 0.0
        self.last_names: list[str] = []


class CCTVManager:
    def __init__(self):
        self.feeds: dict[str, Feed] = {}
        self._tracks: dict[str, _Track] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._log: Callable[[str], None] = print
        self._lock = threading.RLock()
        self._last_announce: dict[str, float] = {}
        self._last_telegram = 0.0
        self._describe_busy = threading.Lock()
        self.viewers = 0                      # the camera wall is open
        self.on_event: Callable[[dict, bytes], None] | None = None

    # lifecycle
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, log: Callable[[str], None] = print) -> None:
        self._log = log
        self.sync()
        if not self.running():
            self._stop.clear()
            self._thread = threading.Thread(target=self._analyse_loop, daemon=True, name="cctv-analyser")
            self._thread.start()
        self.prune()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for f in self.feeds.values():
                f.stop()
            self.feeds.clear()

    def sync(self) -> None:
        """Start readers for enabled cameras, stop the rest (after config changes)."""
        data = load_cfg()
        want = {c["id"]: c for c in data["cameras"] if c.get("enabled", True)}
        watching = data["mode"] != "off" or self.viewers > 0
        with self._lock:
            for cid in list(self.feeds):
                f = self.feeds[cid]
                cam = want.get(cid)
                if not watching or cam is None or cam.get("url") != f.cam.get("url"):
                    f.stop()
                    del self.feeds[cid]
            if watching:
                for cid, cam in want.items():
                    if cid not in self.feeds:
                        f = Feed(cam, self._log)
                        self.feeds[cid] = f
                        f.start()
                        self._tracks.setdefault(cid, _Track())

    def status(self) -> list[dict]:
        data = load_cfg()
        out = []
        for c in data["cameras"]:
            f = self.feeds.get(c["id"])
            out.append({"id": c["id"], "name": c["name"], "enabled": c.get("enabled", True),
                        "status": f.status if f else ("disabled" if not c.get("enabled", True) else "idle"),
                        "error": f.error if f else "", "url": mask(c.get("url", ""))})
        return out

    def latest(self, cam_id: str, max_age: float = 10.0):
        f = self.feeds.get(cam_id)
        return f.latest(max_age) if f else None

    def snapshot(self, cam: dict, timeout: float = 12.0):
        """Newest frame — from the running reader, or opened just for this."""
        frame = self.latest(cam["id"], max_age=5.0)
        if frame is None:
            frame = grab_once(cam["url"], timeout=timeout)
        return frame

    # analysis
    def _analyse_loop(self) -> None:
        from core import vision_detect
        det = None
        while not self._stop.is_set():
            data = load_cfg()
            st = data["settings"]
            if data["mode"] == "off" or not self.feeds:
                self._stop.wait(2.0)
                continue
            if det is None:
                det = vision_detect.detector(self._log)
                if det is None:
                    self._stop.wait(30)
                    continue
            fps = max(0.3, min(5.0, float(st.get("analysis_fps", 1.5) or 1.5)))
            t0 = time.monotonic()
            cams = {c["id"]: c for c in data["cameras"]}
            for cid, feed in list(self.feeds.items()):
                cam = cams.get(cid)
                if cam is None or not cam.get("watch", True):
                    continue
                frame = feed.latest(max_age=5.0)
                if frame is None:
                    continue
                try:
                    self._analyse(cam, frame, det, data)
                except Exception as e:
                    print(f"[CCTV] {cam['name']}: {type(e).__name__}: {e}")
            self._stop.wait(max(0.05, 1.0 / fps - (time.monotonic() - t0)))

    def _analyse(self, cam: dict, frame, det, data: dict) -> None:
        import cv2
        tr = self._tracks.setdefault(cam["id"], _Track())
        h, w = frame.shape[:2]
        thumb = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, (96, max(8, 96 * h // w))),
                                              cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
        if tr.bg is None or tr.bg.shape != thumb.shape:
            tr.bg = thumb.copy()
        diff = np.abs(thumb - tr.bg)
        moving = float(np.mean(diff > 18))
        cv2.accumulateWeighted(thumb, tr.bg, 0.08)
        now = time.monotonic()
        sens = float(cam.get("motion_sensitivity", 0.004) or 0.004)
        if moving < sens and now - tr.last_full < (5 if tr.present else 12):
            return                   # nothing moved: look again only now and then
        tr.last_full = now
        wanted = set(cam.get("detect") or DEFAULT_DETECT)
        small = frame if w <= 960 else cv2.resize(frame, (960, int(h * 960 / w)), interpolation=cv2.INTER_AREA)
        dets = det.detect(small, min_conf=float(cam.get("min_conf", 0.5) or 0.5), classes=wanted)
        k = w / small.shape[1]
        for d in dets:
            x, y, bw, bh = d["box"]
            d["box"] = (int(x * k), int(y * k), int(bw * k), int(bh * k))
        counts: dict[str, int] = {}
        for d in dets:
            counts[d["label"]] = counts.get(d["label"], 0) + 1
        tr.window = (tr.window + [counts])[-4:]
        stable = {lb for lb in set().union(*tr.window) if sum(1 for c in tr.window if lb in c) >= 2}
        new = stable - tr.present
        tr.present = stable
        if not new:
            return
        rearm = float(cam.get("rearm_seconds", 90) or 90)
        fresh = [lb for lb in new if now - tr.last_event.get(lb, -1e9) > rearm]
        if not fresh:
            return
        for lb in fresh:
            tr.last_event[lb] = now
        names = []
        if "person" in stable:
            names = self._faces(frame, [d for d in dets if d["label"] == "person"])
        self._event(cam, frame, dets, fresh, names, data)

    def _faces(self, frame, persons: list[dict]) -> list[str]:
        try:
            from core import face_id
            eng = face_id.engine()
            if not eng.people:
                return []
        except Exception:
            return []
        import cv2
        names = []
        h, w = frame.shape[:2]
        for p in persons[:4]:
            x, y, bw, bh = p["box"]
            x0, y0 = max(0, x - bw // 4), max(0, y - bh // 8)
            x1, y1 = min(w, x + bw + bw // 4), min(h, y + bh // 2 + bh // 8)
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            if crop.shape[1] < 320:
                s = 320 / crop.shape[1]
                crop = cv2.resize(crop, (320, int(crop.shape[0] * s)), interpolation=cv2.INTER_CUBIC)
            for f in eng.identify(crop):
                names.append(f["name"])
        return names

    def _event(self, cam: dict, frame, dets: list[dict], fresh: list[str], names: list[str], data: dict) -> None:
        import cv2
        from core import vision_detect
        people = [n for n in names if n != "unknown"]
        # unknown: a face was seen and matched nobody. With no face in view
        # (back turned, too far) the person is simply not identified.
        unknown = "person" in fresh and "unknown" in names and not people
        what = vision_detect.summarize([d for d in dets if d["label"] in set(fresh) | {"person"}])
        who = f" — {', '.join(sorted(set(people)))}" if people else (" — not recognised" if unknown else "")
        summary = f"{what or ', '.join(fresh)} at {cam['name']}{who}"
        view = vision_detect.draw(frame, dets)
        ok, buf = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 82])
        jpeg = buf.tobytes() if ok else b""
        day = datetime.now().strftime("%Y-%m-%d")
        folder = EVENTS_DIR / day
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%H%M%S")
        snap = folder / f"{stamp}_{_slug(cam['name'])}.jpg"
        if jpeg:
            snap.write_bytes(jpeg)
        ev = {"t": _now_iso(), "camera": cam["name"], "camera_id": cam["id"], "labels": sorted(fresh),
              "people": sorted(set(people)), "unknown": bool(unknown), "summary": summary,
              "snapshot": str(snap.relative_to(brain_config.BASE_DIR)) if jpeg else "", "description": ""}
        self._log(f"SYS: 📹 {summary}")
        journal.append("cctv", summary, None, camera=cam["name"])
        threading.Thread(target=self._describe_and_react, args=(cam, ev, jpeg, frame, data),
                         daemon=True, name="cctv-react").start()

    def _describe_and_react(self, cam: dict, ev: dict, jpeg: bytes, frame, data: dict) -> None:
        st = data["settings"]
        if st.get("describe_events", True) and jpeg and self._describe_busy.acquire(timeout=1):
            try:
                from core import llm, perception
                if perception._can_see():
                    hint = f"Recognised: {', '.join(ev['people'])}. " if ev["people"] else ""
                    txt = llm.complete([f"{hint}This is a frame from the security camera '{cam['name']}'. In one "
                                        "short sentence say who or what is there and what they are doing "
                                        "(e.g. delivering a parcel, walking to the door, parking). Only what is "
                                        "visible.", llm.image_part(jpeg, "image/jpeg")],
                                       role="vision", max_tokens=80, timeout=60, background=True)
                    ev["description"] = " ".join((txt or "").split())
                    if ev["description"]:
                        journal.append("cctv", f"{cam['name']}: {ev['description']}", None, camera=cam["name"])
            except Exception as e:
                print(f"[CCTV] describe failed: {e}")
            finally:
                self._describe_busy.release()
        self._save_event(ev)
        if self.on_event is not None:
            try:
                self.on_event(ev, jpeg)
            except Exception:
                pass
        self._react(cam, ev, jpeg, data)

    def _react(self, cam: dict, ev: dict, jpeg: bytes, data: dict) -> None:
        mode = data["mode"]
        st = data["settings"]
        now = time.monotonic()
        labels = set(ev["labels"])
        person = "person" in labels
        vehicle = bool(labels & {"car", "truck", "bus", "motorcycle", "bicycle"})
        text = ev["description"] or ev["summary"]
        # Voice: people at a camera, at home or at night.
        speak = (mode in ("home", "night") and cam.get("announce", True)
                 and (person or (vehicle and st.get("announce_vehicles"))))
        if speak and now - self._last_announce.get(cam["id"], -1e9) > float(st.get("announce_cooldown", 120)):
            self._last_announce[cam["id"]] = now
            who = ("It is " + ", ".join(ev["people"]) + ". ") if ev["people"] else \
                ("The person is not someone you recognise. " if ev["unknown"] else "")
            runtime.inject(f"[CCTV_EVENT] Your security camera '{cam['name']}' just saw: {text}. {who}"
                           "Tell the user in one short, calm sentence.")
            ui = runtime.ui()
            if ui is not None and jpeg:
                try:
                    ui.show_camera_frame(jpeg)
                except Exception:
                    pass
        # Phone: when nobody is home, or a stranger at night.
        tg = (mode == "away" and (person or vehicle or labels & {"dog", "cat"})) or \
             (mode == "night" and person and not ev["people"]) or cam.get("telegram_always")
        if tg and now - self._last_telegram > float(st.get("telegram_cooldown", 60)):
            try:
                from core import telegram_bridge
                if telegram_bridge.configured():
                    self._last_telegram = now
                    telegram_bridge.send_photo(jpeg, f"📹 {cam['name']}: {text}"[:900])
            except Exception as e:
                print(f"[CCTV] Telegram alert failed: {e}")

    # events on disk
    def _save_event(self, ev: dict) -> None:
        day = ev["t"][:10]
        f = EVENTS_DIR / day / "events.jsonl"
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            with _lock, open(f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[CCTV] could not save event: {e}")

    def prune(self) -> None:
        keep = int(load_cfg()["settings"].get("keep_days", 7) or 7)
        cutoff = datetime.now() - timedelta(days=max(1, keep))
        try:
            for d in EVENTS_DIR.iterdir():
                try:
                    if d.is_dir() and datetime.strptime(d.name, "%Y-%m-%d") < cutoff:
                        for f in d.iterdir():
                            f.unlink()
                        d.rmdir()
                except Exception:
                    continue
        except FileNotFoundError:
            pass


def events(camera: str = "", hours: float = 24.0, limit: int = 40) -> list[dict]:
    start = datetime.now() - timedelta(hours=hours)
    out = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day.date() <= datetime.now().date():
        f = EVENTS_DIR / day.strftime("%Y-%m-%d") / "events.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    ev = json.loads(line)
                    if datetime.fromisoformat(ev["t"]) < start:
                        continue
                except Exception:
                    continue
                if camera and camera.lower() not in ev.get("camera", "").lower():
                    continue
                out.append(ev)
        day += timedelta(days=1)
    return out[-limit:]


_manager = CCTVManager()


def manager() -> CCTVManager:
    return _manager


def add_camera(name: str, url: str, detect: list[str] | None = None, announce: bool = True) -> dict:
    data = load_cfg()
    existing = find_camera(data, name)
    if existing is not None and existing["name"].lower() == name.strip().lower():
        existing["url"] = url
        cam = existing
    else:
        cid = _slug(name)
        ids = {c["id"] for c in data["cameras"]}
        base, i = cid, 2
        while cid in ids:
            cid, i = f"{base}_{i}", i + 1
        cam = {"id": cid, "name": name.strip() or cid, "url": url, "enabled": True, "watch": True,
               "announce": bool(announce), "detect": list(detect or DEFAULT_DETECT)}
        data["cameras"].append(cam)
    save_cfg(data)
    return cam


def remove_camera(name: str) -> bool:
    data = load_cfg()
    cam = find_camera(data, name)
    if cam is None:
        return False
    data["cameras"] = [c for c in data["cameras"] if c["id"] != cam["id"]]
    save_cfg(data)
    return True


def set_mode(mode: str) -> str:
    mode = (mode or "").lower().strip()
    aliases = {"disarm": "off", "disarmed": "off", "stop": "off", "armed": "away", "arm": "away",
               "leaving": "away", "out": "away", "sleep": "night", "bed": "night", "back": "home"}
    mode = aliases.get(mode, mode)
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    data = load_cfg()
    data["mode"] = mode
    save_cfg(data)
    return mode
