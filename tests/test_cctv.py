"""CCTV: URLs, config, a fake HTTP camera, ONVIF over SOAP, and event handling."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

from core import cctv


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    from core import brain_config, journal
    monkeypatch.setattr(cctv, "CFG_FILE", tmp_path / "cctv.json")
    monkeypatch.setattr(cctv, "EVENTS_DIR", tmp_path / "events")
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(brain_config, "BASE_DIR", tmp_path)
    cfg = tmp_path / "api_keys.json"
    cfg.write_text(json.dumps({"brain": {"provider": "ollama", "model": "m"}}), encoding="utf-8")
    monkeypatch.setattr(brain_config, "CONFIG_FILE", cfg)
    return tmp_path


def test_brand_urls_and_masking():
    u = cctv.build_url("hikvision", "192.168.1.20", "admin", "p@ss:w/rd", channel=2)
    assert u == "rtsp://admin:p%40ss%3Aw%2Frd@192.168.1.20:554/Streaming/Channels/202"
    assert cctv.build_url("dahua", "10.0.0.5", "admin", "x") == \
        "rtsp://admin:x@10.0.0.5:554/cam/realmonitor?channel=1&subtype=1"
    assert cctv.build_url("tapo", "10.0.0.6", "cam", "pw").endswith("@10.0.0.6:554/stream2")
    assert cctv.build_url("reolink", "10.0.0.7", "admin", "pw", 3).endswith("/h264Preview_03_sub")
    assert cctv.build_url("esp32cam", "10.0.0.8") == "http://10.0.0.8:81/stream"
    assert cctv.mask(u) == "rtsp://admin:***@192.168.1.20:554/Streaming/Channels/202"
    assert cctv.with_credentials("rtsp://10.0.0.9/live", "u", "p w") == "rtsp://u:p%20w@10.0.0.9/live"
    assert cctv._kind("http://x/snapshot.jpg") == "snapshot" and cctv._kind("ha:camera.porch") == "ha"
    assert cctv._kind("rtsp://x/y") == "stream" and cctv._kind("usb:1") == "usb"


def test_config_add_find_remove_mode(sandbox):
    cam = cctv.add_camera("Front Door", "rtsp://a/b")
    cctv.add_camera("Back Yard", "rtsp://c/d")
    data = cctv.load_cfg()
    assert [c["name"] for c in data["cameras"]] == ["Front Door", "Back Yard"]
    assert cctv.find_camera(data, "front")["id"] == cam["id"] == "front_door"
    assert cctv.set_mode("leaving") == "away" and cctv.load_cfg()["mode"] == "away"
    with pytest.raises(ValueError):
        cctv.set_mode("party")
    assert cctv.remove_camera("back yard") and len(cctv.load_cfg()["cameras"]) == 1


def _jpeg(color=(0, 128, 255), size=(240, 320)):
    import cv2
    img = np.zeros((size[0], size[1], 3), np.uint8)
    img[:] = color
    cv2.putText(img, "CAM", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    return cv2.imencode(".jpg", img)[1].tobytes()


@pytest.fixture
def fake_camera():
    frame = _jpeg()
    onvif = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/snapshot.jpg":
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
            elif self.path == "/video.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                try:
                    for _ in range(200):
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                        self.wfile.flush()
                        time.sleep(0.05)
                except Exception:
                    pass
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
            onvif.setdefault("calls", []).append(body)
            if "UsernameToken" not in body:
                self.send_response(401)
                self.end_headers()
                return
            host = self.headers.get("Host")
            if "GetCapabilities" in body:
                x = f"<tt:Media><tt:XAddr>http://{host}/onvif/media</tt:XAddr></tt:Media>"
            elif "GetProfiles" in body:
                x = ('<trt:Profiles token="main"><tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080'
                     '</tt:Height></tt:Resolution></trt:Profiles><trt:Profiles token="sub"><tt:Resolution>'
                     '<tt:Width>640</tt:Width><tt:Height>360</tt:Height></tt:Resolution></trt:Profiles>')
            else:
                tok = "sub" if "sub" in body else "main"
                x = f"<tt:Uri>rtsp://10.1.1.9:554/stream?profile={tok}&amp;x=1</tt:Uri>"
            b = f"<s:Envelope><s:Body>{x}</s:Body></s:Envelope>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/soap+xml")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", onvif
    srv.shutdown()


def test_snapshot_camera_and_feed(sandbox, fake_camera):
    base, _ = fake_camera
    f = cctv.grab_once(base + "/snapshot.jpg")
    assert f is not None and f.shape == (240, 320, 3)
    feed = cctv.Feed({"id": "t", "name": "Test", "url": base + "/snapshot.jpg", "snapshot_seconds": 0.2},
                     log=lambda m: None)
    feed.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline and feed.latest() is None:
            time.sleep(0.05)
        assert feed.latest() is not None and feed.status == "online"
    finally:
        feed.stop()


def test_mjpeg_stream_through_ffmpeg(sandbox, fake_camera):
    base, _ = fake_camera
    frame = cctv.grab_once(base + "/video.mjpg", timeout=10)
    if frame is None:
        pytest.skip("this OpenCV build cannot read MJPEG over HTTP")
    assert frame.shape[:2] == (240, 320)


def test_onvif_stream_uris(fake_camera):
    base, onvif = fake_camera
    uris = cctv.onvif_stream_uris(base + "/onvif/device_service", "admin", "secret")
    assert [u["profile"] for u in uris] == ["sub", "main"], "smallest stream first"
    assert uris[0]["uri"] == "rtsp://admin:secret@10.1.1.9:554/stream?profile=sub&x=1"
    assert any("PasswordDigest" in c for c in onvif["calls"])
    with pytest.raises(RuntimeError):
        cctv.onvif_stream_uris(base + "/onvif/device_service", "", "")


class _Det:
    def __init__(self, dets):
        self.dets = dets

    def detect(self, frame, min_conf=0.4, nms=0.6, classes=None):
        return [dict(d) for d in self.dets if not classes or d["label"] in classes]


def test_person_event_saves_announces_and_alerts(sandbox, monkeypatch):
    from core import face_id, journal, perception, runtime, telegram_bridge
    tmp = sandbox
    cam = cctv.add_camera("Front Door", "rtsp://x/y")
    cctv.set_mode("night")
    mgr = cctv.CCTVManager()
    monkeypatch.setattr(face_id, "engine", lambda log=print: type("E", (), {"people": {}})())
    monkeypatch.setattr(perception, "_can_see", lambda: False)
    said, sent = [], []
    monkeypatch.setattr(runtime, "inject", lambda t: said.append(t) or True)
    monkeypatch.setattr(telegram_bridge, "configured", lambda: True)
    monkeypatch.setattr(telegram_bridge, "send_photo", lambda b, cap: sent.append((len(b), cap)) or "sent")
    person = {"label": "person", "conf": 0.9, "box": (100, 60, 80, 200)}
    empty = np.full((360, 640, 3), 60, np.uint8)
    busy = empty.copy()
    busy[60:260, 100:180] = 220                       # something moved
    data = cctv.load_cfg()
    mgr._analyse(cam, empty, _Det([]), data)          # background
    for _ in range(3):
        mgr._analyse(cam, busy, _Det([person]), data)
    deadline = time.time() + 5
    while time.time() < deadline and not sent:
        time.sleep(0.05)
    assert said and "Front Door" in said[0] and "person" in said[0], said
    assert sent and "Front Door" in sent[0][1], "night mode: an unidentified person goes to the phone"
    evs = cctv.events()
    assert len(evs) == 1 and evs[0]["labels"] == ["person"] and evs[0]["snapshot"]
    assert (tmp / evs[0]["snapshot"]).exists()
    assert "person at Front Door" in journal.search("", "today")
    # the same person standing there does not fire again
    for _ in range(3):
        mgr._analyse(cam, busy, _Det([person]), data)
    time.sleep(0.3)
    assert len(cctv.events()) == 1


def test_cctv_tool(sandbox, fake_camera, monkeypatch):
    from actions.cctv import cctv_tool
    base, _ = fake_camera
    assert "No CCTV cameras" in cctv_tool({"action": "list"})
    r = cctv_tool({"action": "add", "camera": "Gate", "url": base + "/snapshot.jpg"})
    assert "connected, 320×240" in r, r
    assert "Gate" in cctv_tool({"action": "list"})
    assert "Away mode" in cctv_tool({"action": "mode", "mode": "away"})
    r = cctv_tool({"action": "look", "camera": "gate"})
    assert r.startswith("Gate camera:"), r
    assert "Nothing was seen" in cctv_tool({"action": "events"})
    assert "Removed" in cctv_tool({"action": "remove", "camera": "Gate"})
    cctv.set_mode("off")
    cctv.manager().stop()
