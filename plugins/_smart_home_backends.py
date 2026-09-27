"""
Backends for plugins/smart_home.py — one small class per ecosystem.

Every backend answers three questions:
    discover()                    -> [Device]           what is there
    command(device, cmd, value)   -> str                do something
    status(device)                -> str                what state is it in

and every device, whatever its brand, is described by the same record so the
assistant can say "turn off the bedroom light" without caring whether that is a
Hue bulb, a Tuya plug, a SmartThings washer or an ESP32 on the shelf.

Commands (not every device supports every one):
    on off toggle
    brightness <0-100>      color <name | #rrggbb>      color_temp <kelvin>
    temperature <°C>        mode <cool|heat|auto|dry|fan_only|off>
    fan_speed <0-100>       volume <0-100>              mute / unmute
    open close stop position <0-100>                    lock unlock
    start pause stop dock (vacuums, washers, dryers)    play pause next previous
    activate (scenes)       raw <backend-specific JSON>
"""
from __future__ import annotations

import colorsys
import json
import re
import socket
import time
from dataclasses import asdict, dataclass, field

import requests

_TIMEOUT = 8

_COLORS = {
    "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "white": (255, 255, 255),
    "warm white": (255, 197, 143), "yellow": (255, 220, 0), "orange": (255, 120, 0),
    "purple": (150, 0, 255), "violet": (140, 60, 255), "pink": (255, 80, 160),
    "cyan": (0, 255, 255), "magenta": (255, 0, 255), "teal": (0, 160, 160),
    "lime": (160, 255, 0), "gold": (255, 190, 0), "indigo": (75, 0, 130),
    "lavender": (200, 160, 255), "turquoise": (64, 224, 208), "amber": (255, 170, 0),
    "crimson": (220, 20, 60), "sky blue": (135, 206, 235), "cool white": (220, 235, 255),
}


def parse_color(value: str) -> tuple[int, int, int] | None:
    v = (value or "").strip().lower()
    if v in _COLORS:
        return _COLORS[v]
    m = re.fullmatch(r"#?([0-9a-f]{6})", v)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.fullmatch(r"\(?\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)?", v)
    if m:
        return tuple(max(0, min(255, int(x))) for x in m.groups())  # type: ignore[return-value]
    for name, rgb in _COLORS.items():
        if name in v:
            return rgb
    return None


def pct(value, default: int = 100) -> int:
    try:
        return max(0, min(100, int(float(str(value).strip().rstrip("%")))))
    except (TypeError, ValueError):
        return default


@dataclass
class Device:
    name: str
    backend: str
    ref: dict = field(default_factory=dict)
    kind: str = "device"            # light, switch, plug, vacuum, washer, tv, climate, cover, lock, scene…
    room: str = ""
    aliases: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Device":
        return Device(name=d.get("name", "?"), backend=d.get("backend", "http"),
                      ref=d.get("ref") or {}, kind=d.get("kind", "device"),
                      room=d.get("room", ""), aliases=list(d.get("aliases") or []))


class Backend:
    name = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def configured(self) -> bool:
        return True

    def discover(self) -> list[Device]:
        return []

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        raise NotImplementedError

    def status(self, dev: Device) -> str:
        return "status is not available for this device"


# ── Home Assistant ───────────────────────────────────────────────────────────
class HomeAssistant(Backend):
    """Covers everything Home Assistant integrates: 2000+ brands, including
    Xiaomi/Roborock/Dreame vacuums, LG ThinQ and Samsung appliances, Tuya,
    Hue, Zigbee/Z-Wave, ESPHome, Sonos, Chromecast, cameras, climate…"""
    name = "homeassistant"
    _DOMAINS = {"light": "light", "switch": "switch", "fan": "fan", "cover": "cover",
                "climate": "climate", "vacuum": "vacuum", "media_player": "tv", "lock": "lock",
                "scene": "scene", "script": "scene", "button": "button", "input_boolean": "switch",
                "humidifier": "humidifier", "water_heater": "climate", "sensor": "sensor",
                "binary_sensor": "sensor", "alarm_control_panel": "alarm", "valve": "cover",
                "lawn_mower": "vacuum", "siren": "switch", "select": "select", "number": "number"}

    def configured(self) -> bool:
        return bool(self.cfg.get("ha_url") and self.cfg.get("ha_token"))

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.cfg.get('ha_token', '')}",
                "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return str(self.cfg.get("ha_url", "")).rstrip("/") + path

    def test(self) -> tuple[bool, str]:
        r = requests.get(self._url("/api/"), headers=self._h(), timeout=_TIMEOUT)
        if r.status_code == 200:
            return True, "Connected to Home Assistant."
        return False, f"HTTP {r.status_code}: {r.text[:120]}"

    def discover(self) -> list[Device]:
        r = requests.get(self._url("/api/states"), headers=self._h(), timeout=_TIMEOUT)
        r.raise_for_status()
        out = []
        for st in r.json():
            eid = st.get("entity_id", "")
            domain = eid.split(".")[0]
            if domain not in self._DOMAINS:
                continue
            if domain in ("sensor", "binary_sensor") and not st.get("attributes", {}).get("friendly_name"):
                continue
            name = st.get("attributes", {}).get("friendly_name") or eid
            out.append(Device(name=name, backend=self.name, ref={"entity_id": eid},
                              kind=self._DOMAINS[domain]))
        return out

    def _svc(self, domain: str, service: str, data: dict) -> str:
        r = requests.post(self._url(f"/api/services/{domain}/{service}"), headers=self._h(),
                          json=data, timeout=_TIMEOUT)
        if r.status_code >= 400:
            return f"Home Assistant refused {domain}.{service}: HTTP {r.status_code} {r.text[:120]}"
        return "ok"

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        eid = dev.ref.get("entity_id", "")
        domain = eid.split(".")[0]
        base = {"entity_id": eid}
        c = cmd
        if c == "raw":
            spec = json.loads(value or "{}")
            return self._svc(spec.get("domain", domain), spec["service"], {**base, **spec.get("data", {})})
        if domain in ("scene", "script"):
            return self._svc(domain, "turn_on", base)
        if domain == "button":
            return self._svc("button", "press", base)
        if domain in ("vacuum", "lawn_mower"):
            m = {"on": "start", "start": "start", "pause": "pause", "stop": "stop", "off": "return_to_base",
                 "dock": "return_to_base", "locate": "locate"}
            svc = m.get(c)
            if domain == "lawn_mower":
                svc = {"start": "start_mowing", "on": "start_mowing", "pause": "pause", "dock": "dock",
                       "off": "dock", "stop": "pause"}.get(c)
            if svc:
                return self._svc(domain, svc, base)
        if domain in ("cover", "valve"):
            if c in ("open", "on"):
                return self._svc(domain, f"open_{domain}", base)
            if c in ("close", "off"):
                return self._svc(domain, f"close_{domain}", base)
            if c == "stop":
                return self._svc(domain, f"stop_{domain}", base)
            if c == "position":
                return self._svc(domain, f"set_{domain}_position", {**base, "position": pct(value)})
        if domain == "lock":
            if c in ("lock", "on"):
                return self._svc("lock", "lock", base)
            if c in ("unlock", "off"):
                return self._svc("lock", "unlock", base)
        if domain == "climate":
            if c == "temperature":
                return self._svc("climate", "set_temperature", {**base, "temperature": float(value)})
            if c == "mode":
                return self._svc("climate", "set_hvac_mode", {**base, "hvac_mode": value})
            if c == "fan_speed":
                return self._svc("climate", "set_fan_mode", {**base, "fan_mode": value})
        if domain == "media_player":
            m = {"play": "media_play", "pause": "media_pause", "stop": "media_stop",
                 "next": "media_next_track", "previous": "media_previous_track"}
            if c in m:
                return self._svc("media_player", m[c], base)
            if c == "volume":
                return self._svc("media_player", "volume_set", {**base, "volume_level": pct(value) / 100})
            if c in ("mute", "unmute"):
                return self._svc("media_player", "volume_mute", {**base, "is_volume_muted": c == "mute"})
        if domain == "fan" and c == "fan_speed":
            return self._svc("fan", "set_percentage", {**base, "percentage": pct(value)})
        if domain == "light":
            if c == "brightness":
                return self._svc("light", "turn_on", {**base, "brightness_pct": pct(value)})
            if c == "color":
                rgb = parse_color(value)
                if not rgb:
                    return f"I don't know the colour '{value}'."
                return self._svc("light", "turn_on", {**base, "rgb_color": list(rgb)})
            if c == "color_temp":
                return self._svc("light", "turn_on", {**base, "color_temp_kelvin": int(float(value))})
        if c in ("on", "off", "toggle", "start", "stop"):
            svc = {"on": "turn_on", "off": "turn_off", "toggle": "toggle", "start": "turn_on",
                   "stop": "turn_off"}[c]
            d = "homeassistant" if domain not in ("light", "switch", "fan", "input_boolean",
                                                  "humidifier", "siren", "media_player",
                                                  "climate", "water_heater") else domain
            return self._svc(d, svc, base)
        return f"'{c}' is not something {dev.name} supports."

    def status(self, dev: Device) -> str:
        r = requests.get(self._url(f"/api/states/{dev.ref.get('entity_id')}"), headers=self._h(),
                         timeout=_TIMEOUT)
        if r.status_code != 200:
            return f"HTTP {r.status_code}"
        st = r.json()
        attrs = st.get("attributes", {})
        keep = {k: attrs[k] for k in ("brightness", "temperature", "current_temperature", "hvac_mode",
                                      "battery_level", "fan_speed", "volume_level", "media_title",
                                      "unit_of_measurement", "percentage", "current_position")
                if k in attrs}
        return f"{st.get('state')}" + (f" {json.dumps(keep)}" if keep else "")

    def converse(self, text: str) -> str:
        """Home Assistant Assist: let HA understand a whole sentence."""
        r = requests.post(self._url("/api/conversation/process"), headers=self._h(),
                          json={"text": text, "language": self.cfg.get("ha_language") or "en"},
                          timeout=15)
        if r.status_code != 200:
            return f"Home Assistant Assist failed: HTTP {r.status_code}"
        speech = (((r.json().get("response") or {}).get("speech") or {}).get("plain") or {}).get("speech")
        return speech or "Home Assistant handled it."


# ── Samsung SmartThings ──────────────────────────────────────────────────────
class SmartThings(Backend):
    """Samsung SmartThings cloud API: Samsung washers, dryers, fridges, ACs,
    Jet Bot vacuums, TVs, and every third-party device linked to SmartThings."""
    name = "smartthings"
    API = "https://api.smartthings.com/v1"

    def configured(self) -> bool:
        return bool(self.cfg.get("st_token"))

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.cfg.get('st_token', '')}", "Content-Type": "application/json"}

    def test(self) -> tuple[bool, str]:
        r = requests.get(f"{self.API}/devices", headers=self._h(), timeout=_TIMEOUT)
        if r.status_code == 200:
            return True, f"Connected — {len(r.json().get('items', []))} SmartThings devices."
        return False, f"HTTP {r.status_code}: {r.text[:120]}"

    @staticmethod
    def _kind(caps: set[str], label: str) -> str:
        low = label.lower()
        if "robotCleanerMovement" in caps or "samsungce.robotCleanerOperatingState" in caps:
            return "vacuum"
        if "washerOperatingState" in caps or "samsungce.washerOperatingState" in caps:
            return "washer"
        if "dryerOperatingState" in caps:
            return "dryer"
        if "tvChannel" in caps or "mediaInputSource" in caps and "tv" in low:
            return "tv"
        if "thermostatCoolingSetpoint" in caps or "airConditionerMode" in caps:
            return "climate"
        if "colorControl" in caps or "colorTemperature" in caps or "switchLevel" in caps and "light" in low:
            return "light"
        if "lock" in caps:
            return "lock"
        if "windowShade" in caps:
            return "cover"
        if "switch" in caps:
            return "switch"
        return "device"

    def discover(self) -> list[Device]:
        out = []
        url = f"{self.API}/devices"
        while url:
            r = requests.get(url, headers=self._h(), timeout=_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            for d in data.get("items", []):
                caps = {c.get("id") for comp in d.get("components", []) for c in comp.get("capabilities", [])}
                label = d.get("label") or d.get("name") or d.get("deviceId")
                out.append(Device(name=label, backend=self.name,
                                  ref={"device_id": d.get("deviceId"), "caps": sorted(c for c in caps if c)},
                                  kind=self._kind(caps, label)))
            url = ((data.get("_links") or {}).get("next") or {}).get("href")
        try:
            r = requests.get(f"{self.API}/scenes", headers=self._h(), timeout=_TIMEOUT)
            if r.status_code == 200:
                for sc in r.json().get("items", []):
                    out.append(Device(name=sc.get("sceneName", "scene"), backend=self.name,
                                      ref={"scene_id": sc.get("sceneId")}, kind="scene"))
        except Exception:
            pass
        return out

    def _send(self, dev: Device, capability: str, command: str, args: list | None = None,
              component: str = "main") -> str:
        body = {"commands": [{"component": component, "capability": capability, "command": command,
                              "arguments": args or []}]}
        r = requests.post(f"{self.API}/devices/{dev.ref['device_id']}/commands", headers=self._h(),
                          json=body, timeout=_TIMEOUT)
        if r.status_code >= 400:
            return f"SmartThings refused {capability}.{command}: HTTP {r.status_code} {r.text[:160]}"
        return "ok"

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        if dev.ref.get("scene_id"):
            r = requests.post(f"{self.API}/scenes/{dev.ref['scene_id']}/execute", headers=self._h(),
                              timeout=_TIMEOUT)
            return "ok" if r.status_code < 400 else f"HTTP {r.status_code}"
        caps = set(dev.ref.get("caps") or [])
        c = cmd
        if c == "raw":
            spec = json.loads(value or "{}")
            return self._send(dev, spec["capability"], spec["command"], spec.get("arguments", []),
                              spec.get("component", "main"))
        if dev.kind == "vacuum" or "robotCleanerMovement" in caps:
            m = {"start": "cleaning", "on": "cleaning", "pause": "pause", "stop": "pause",
                 "dock": "homing", "off": "homing"}
            if c in m:
                if "samsungce.robotCleanerOperatingState" in caps and c in ("start", "on"):
                    return self._send(dev, "samsungce.robotCleanerOperatingState", "start")
                return self._send(dev, "robotCleanerMovement", "setRobotCleanerMovement", [m[c]])
        for cap in ("samsungce.washerOperatingState", "washerOperatingState",
                    "samsungce.dryerOperatingState", "dryerOperatingState"):
            if cap in caps and c in ("start", "pause", "stop", "on", "off"):
                state = {"start": "run", "on": "run", "pause": "pause", "stop": "stop", "off": "stop"}[c]
                if cap.startswith("samsungce."):
                    return self._send(dev, cap, {"run": "start", "pause": "pause", "stop": "cancel"}[state])
                return self._send(dev, cap, "setMachineState", [state])
        if c in ("on", "off"):
            return self._send(dev, "switch", c)
        if c == "toggle":
            st = self._raw_status(dev)
            cur = (((st.get("components", {}).get("main", {}).get("switch") or {}).get("switch") or {})
                   .get("value"))
            return self._send(dev, "switch", "off" if cur == "on" else "on")
        if c == "brightness":
            return self._send(dev, "switchLevel", "setLevel", [pct(value)])
        if c == "color":
            rgb = parse_color(value)
            if not rgb:
                return f"I don't know the colour '{value}'."
            h, s, _v = colorsys.rgb_to_hsv(*(x / 255 for x in rgb))
            return self._send(dev, "colorControl", "setColor", [{"hue": round(h * 100), "saturation": round(s * 100)}])
        if c == "color_temp":
            return self._send(dev, "colorTemperature", "setColorTemperature", [int(float(value))])
        if c == "temperature":
            cap = "thermostatCoolingSetpoint" if "thermostatCoolingSetpoint" in caps else "thermostatHeatingSetpoint"
            cmd_name = "setCoolingSetpoint" if cap.endswith("CoolingSetpoint") else "setHeatingSetpoint"
            return self._send(dev, cap, cmd_name, [float(value)])
        if c == "mode" and "airConditionerMode" in caps:
            return self._send(dev, "airConditionerMode", "setAirConditionerMode", [value])
        if c == "volume":
            return self._send(dev, "audioVolume", "setVolume", [pct(value)])
        if c in ("mute", "unmute"):
            return self._send(dev, "audioMute", c)
        if c in ("play", "pause", "stop") and "mediaPlayback" in caps:
            return self._send(dev, "mediaPlayback", c)
        if c in ("next", "previous") and "mediaTrackControl" in caps:
            return self._send(dev, "mediaTrackControl", "nextTrack" if c == "next" else "previousTrack")
        if c in ("lock", "unlock"):
            return self._send(dev, "lock", c)
        if c in ("open", "close"):
            return self._send(dev, "windowShade", c)
        return f"'{c}' is not supported by {dev.name}. Its capabilities: {', '.join(sorted(caps))[:300]}"

    def _raw_status(self, dev: Device) -> dict:
        r = requests.get(f"{self.API}/devices/{dev.ref['device_id']}/status", headers=self._h(), timeout=_TIMEOUT)
        return r.json() if r.status_code == 200 else {}

    def status(self, dev: Device) -> str:
        if dev.ref.get("scene_id"):
            return "scene"
        main = self._raw_status(dev).get("components", {}).get("main", {})
        parts = []
        for cap, attrs in main.items():
            for attr, val in (attrs or {}).items():
                v = (val or {}).get("value")
                if v is None or isinstance(v, (dict, list)) and len(json.dumps(v)) > 80:
                    continue
                if attr in ("switch", "level", "machineState", "operatingState", "temperature",
                            "coolingSetpoint", "battery", "volume", "robotCleanerMovement", "lock",
                            "completionTime", "remainingTime", "washerJobState", "airConditionerMode",
                            "mute", "playbackStatus", "contact", "motion", "humidity"):
                    parts.append(f"{attr}={v}")
        return ", ".join(parts[:15]) or "no state reported"


# ── Tuya / Smart Life ────────────────────────────────────────────────────────
class Tuya(Backend):
    """Tuya / Smart Life (thousands of cheap WiFi bulbs, plugs, switches,
    vacuums). Local control needs each device's local key — get them once with
    `python -m tinytuya wizard`, which writes devices.json. Cloud control needs a
    Tuya IoT developer project (API key/secret/region)."""
    name = "tuya"

    def configured(self) -> bool:
        return bool(self.cfg.get("tuya_api_key")) or self._devices_json() is not None

    def _devices_json(self):
        import os
        from pathlib import Path
        for p in [self.cfg.get("tuya_devices_json"), Path.cwd() / "devices.json",
                  Path(__file__).resolve().parent.parent / "config" / "tuya_devices.json"]:
            if p and os.path.exists(str(p)):
                try:
                    return json.loads(Path(p).read_text(encoding="utf-8"))
                except Exception:
                    return None
        return None

    def _cloud(self):
        import tinytuya
        return tinytuya.Cloud(apiRegion=self.cfg.get("tuya_region") or "in",
                              apiKey=self.cfg.get("tuya_api_key"), apiSecret=self.cfg.get("tuya_api_secret"))

    def discover(self) -> list[Device]:
        out = []
        local = self._devices_json() or []
        for d in local:
            kind = "light" if str(d.get("category", "")) in ("dj", "dd", "xdd", "fwd") else \
                "vacuum" if str(d.get("category", "")) == "sd" else "switch"
            out.append(Device(name=d.get("name") or d.get("id"), backend=self.name, kind=kind,
                              ref={"id": d.get("id"), "key": d.get("key"), "ip": d.get("ip", ""),
                                   "version": str(d.get("version") or "3.3"), "category": d.get("category", "")}))
        if not out and self.cfg.get("tuya_api_key"):
            for d in self._cloud().getdevices() or []:
                out.append(Device(name=d.get("name") or d.get("id"), backend=self.name,
                                  ref={"id": d.get("id"), "key": d.get("key", ""), "category": d.get("category", ""),
                                       "cloud": True}, kind="switch"))
        return out

    def _local(self, dev: Device):
        import tinytuya
        ref = dev.ref
        cls = tinytuya.BulbDevice if dev.kind == "light" else tinytuya.OutletDevice
        d = cls(ref["id"], ref.get("ip") or "Auto", ref.get("key"))
        d.set_version(float(ref.get("version") or 3.3))
        d.set_socketTimeout(5)
        return d

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        if dev.ref.get("cloud") or not dev.ref.get("key"):
            code = {"on": ("switch_led" if dev.kind == "light" else "switch_1", True),
                    "off": ("switch_led" if dev.kind == "light" else "switch_1", False)}.get(cmd)
            if cmd == "raw":
                cmds = json.loads(value)
            elif code:
                cmds = {"commands": [{"code": code[0], "value": code[1]}]}
            else:
                return f"'{cmd}' needs local control for this Tuya device."
            res = self._cloud().sendcommand(dev.ref["id"], cmds)
            return "ok" if (res or {}).get("success") else f"Tuya cloud: {res}"
        d = self._local(dev)
        if cmd == "on":
            d.turn_on()
        elif cmd == "off":
            d.turn_off()
        elif cmd == "toggle":
            st = d.status().get("dps", {})
            key = "20" if "20" in st else "1"
            d.set_status(not bool(st.get(key)), int(key))
        elif cmd == "brightness" and dev.kind == "light":
            d.set_brightness_percentage(pct(value))
        elif cmd == "color" and dev.kind == "light":
            rgb = parse_color(value)
            if not rgb:
                return f"I don't know the colour '{value}'."
            d.set_colour(*rgb)
        elif cmd == "color_temp" and dev.kind == "light":
            k = int(float(value))
            d.set_colourtemp_percentage(max(0, min(100, int((k - 2700) / 38))))
        elif cmd == "raw":
            spec = json.loads(value)
            d.set_value(int(spec["dp"]), spec["value"])
        else:
            return f"'{cmd}' is not supported for this Tuya device."
        return "ok"

    def status(self, dev: Device) -> str:
        if dev.ref.get("cloud"):
            return json.dumps(self._cloud().getstatus(dev.ref["id"]))[:300]
        return json.dumps(self._local(dev).status())[:300]


# ── Philips Hue ──────────────────────────────────────────────────────────────
class Hue(Backend):
    name = "hue"

    def configured(self) -> bool:
        return bool(self.cfg.get("hue_bridge") and self.cfg.get("hue_user"))

    def _u(self, path: str) -> str:
        return f"http://{self.cfg.get('hue_bridge')}/api/{self.cfg.get('hue_user')}{path}"

    @staticmethod
    def pair(bridge_ip: str) -> tuple[bool, str]:
        r = requests.post(f"http://{bridge_ip}/api", json={"devicetype": "jarvis#pc"}, timeout=_TIMEOUT)
        data = r.json()
        if isinstance(data, list) and data and "success" in data[0]:
            return True, data[0]["success"]["username"]
        err = data[0].get("error", {}).get("description", "") if isinstance(data, list) and data else str(data)
        return False, err or "pairing failed"

    def test(self) -> tuple[bool, str]:
        r = requests.get(self._u("/lights"), timeout=_TIMEOUT)
        data = r.json()
        if isinstance(data, dict):
            return True, f"Connected — {len(data)} Hue lights."
        return False, str(data)[:160]

    def discover(self) -> list[Device]:
        out = []
        for lid, l in (requests.get(self._u("/lights"), timeout=_TIMEOUT).json() or {}).items():
            out.append(Device(name=l.get("name", f"light {lid}"), backend=self.name, ref={"light": lid}, kind="light"))
        for gid, g in (requests.get(self._u("/groups"), timeout=_TIMEOUT).json() or {}).items():
            if g.get("type") in ("Room", "Zone"):
                out.append(Device(name=f"{g.get('name')} lights", backend=self.name, ref={"group": gid},
                                  kind="light", room=g.get("name", "")))
        return out

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        body: dict
        if cmd in ("on", "off"):
            body = {"on": cmd == "on"}
        elif cmd == "toggle":
            body = {"on": not self._on(dev)}
        elif cmd == "brightness":
            body = {"on": True, "bri": max(1, int(pct(value) * 2.54))}
        elif cmd == "color":
            rgb = parse_color(value)
            if not rgb:
                return f"I don't know the colour '{value}'."
            h, s, _v = colorsys.rgb_to_hsv(*(x / 255 for x in rgb))
            body = {"on": True, "hue": int(h * 65535), "sat": int(s * 254)}
        elif cmd == "color_temp":
            body = {"on": True, "ct": max(153, min(500, int(1_000_000 / max(2000, float(value)))))}
        elif cmd == "raw":
            body = json.loads(value)
        else:
            return f"'{cmd}' is not supported by Hue lights."
        path = f"/groups/{dev.ref['group']}/action" if "group" in dev.ref else f"/lights/{dev.ref['light']}/state"
        r = requests.put(self._u(path), json=body, timeout=_TIMEOUT)
        return "ok" if r.status_code < 400 and "error" not in r.text else r.text[:160]

    def _on(self, dev: Device) -> bool:
        if "group" in dev.ref:
            return bool(requests.get(self._u(f"/groups/{dev.ref['group']}"), timeout=_TIMEOUT).json()
                        .get("state", {}).get("any_on"))
        return bool(requests.get(self._u(f"/lights/{dev.ref['light']}"), timeout=_TIMEOUT).json()
                    .get("state", {}).get("on"))

    def status(self, dev: Device) -> str:
        return "on" if self._on(dev) else "off"


# ── Yeelight (LAN) ───────────────────────────────────────────────────────────
class Yeelight(Backend):
    """Xiaomi Yeelight bulbs over the LAN. Turn on 'LAN Control' in the Yeelight
    app once."""
    name = "yeelight"

    def discover(self) -> list[Device]:
        msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1982\r\nMAN: \"ssdp:discover\"\r\n"
               "ST: wifi_bulb\r\n\r\n").encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.settimeout(2.0)
        found: dict[str, Device] = {}
        try:
            s.sendto(msg, ("239.255.255.250", 1982))
            end = time.time() + 2.5
            while time.time() < end:
                try:
                    data, _ = s.recvfrom(4096)
                except socket.timeout:
                    break
                txt = data.decode(errors="replace")
                loc = re.search(r"Location:\s*yeelight://([\d.]+):(\d+)", txt, re.I)
                name = re.search(r"name:\s*(.*)", txt, re.I)
                ident = re.search(r"id:\s*(\S+)", txt, re.I)
                if loc:
                    ip = loc.group(1)
                    label = (name.group(1).strip() if name and name.group(1).strip() else f"Yeelight {ip}")
                    found[ip] = Device(name=label, backend=self.name, kind="light",
                                       ref={"ip": ip, "port": int(loc.group(2)),
                                            "id": ident.group(1) if ident else ""})
        finally:
            s.close()
        return list(found.values())

    def _call(self, dev: Device, method: str, params: list) -> str:
        with socket.create_connection((dev.ref["ip"], int(dev.ref.get("port", 55443))), timeout=4) as c:
            c.sendall((json.dumps({"id": 1, "method": method, "params": params}) + "\r\n").encode())
            c.settimeout(4)
            data = c.recv(4096).decode(errors="replace")
        return "ok" if '"ok"' in data or '"result"' in data else data[:160]

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        if cmd in ("on", "off"):
            return self._call(dev, "set_power", [cmd, "smooth", 400])
        if cmd == "toggle":
            return self._call(dev, "toggle", [])
        if cmd == "brightness":
            return self._call(dev, "set_bright", [max(1, pct(value)), "smooth", 400])
        if cmd == "color":
            rgb = parse_color(value)
            if not rgb:
                return f"I don't know the colour '{value}'."
            return self._call(dev, "set_rgb", [(rgb[0] << 16) + (rgb[1] << 8) + rgb[2], "smooth", 400])
        if cmd == "color_temp":
            return self._call(dev, "set_ct_abx", [max(1700, min(6500, int(float(value)))), "smooth", 400])
        return f"'{cmd}' is not supported by Yeelight."

    def status(self, dev: Device) -> str:
        with socket.create_connection((dev.ref["ip"], int(dev.ref.get("port", 55443))), timeout=4) as c:
            c.sendall((json.dumps({"id": 1, "method": "get_prop", "params": ["power", "bright"]}) + "\r\n").encode())
            return c.recv(4096).decode(errors="replace")[:160]


# ── TP-Link Kasa / Tapo (python-kasa) ────────────────────────────────────────
class Kasa(Backend):
    name = "kasa"

    def _run(self, coro):
        import asyncio
        return asyncio.run(coro)

    def discover(self) -> list[Device]:
        try:
            from kasa import Discover
        except Exception:
            return []

        async def go():
            found = await Discover.discover(timeout=3,
                                            username=self.cfg.get("kasa_user") or None,
                                            password=self.cfg.get("kasa_password") or None)
            out = []
            for ip, d in found.items():
                try:
                    await d.update()
                except Exception:
                    pass
                out.append(Device(name=getattr(d, "alias", None) or ip, backend="kasa",
                                  ref={"ip": ip}, kind="light" if getattr(d, "is_bulb", False) else "plug"))
            return out
        return self._run(go())

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        from kasa import Device as KDevice

        async def go():
            d = await KDevice.connect(host=dev.ref["ip"]) if hasattr(KDevice, "connect") else None
            if d is None:
                from kasa import Discover
                d = await Discover.discover_single(dev.ref["ip"])
            await d.update()
            if cmd == "on":
                await d.turn_on()
            elif cmd == "off":
                await d.turn_off()
            elif cmd == "toggle":
                await (d.turn_off() if d.is_on else d.turn_on())
            elif cmd == "brightness" and hasattr(d, "set_brightness"):
                await d.set_brightness(pct(value))
            else:
                return f"'{cmd}' is not supported by this Kasa device."
            return "ok"
        return self._run(go())


# ── Plain HTTP devices: ESP32 firmware, Tasmota, Shelly, ESPHome, WLED ──────
class Http(Backend):
    name = "http"

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        r = dev.ref
        typ = r.get("type", "custom")
        ip = r.get("ip", "")
        try:
            if typ == "tasmota":
                t = {"on": "Power On", "off": "Power Off", "toggle": "Power Toggle"}.get(cmd)
                if cmd == "brightness":
                    t = f"Dimmer {pct(value)}"
                elif cmd == "color":
                    rgb = parse_color(value)
                    t = "Color " + ("%02X%02X%02X" % rgb if rgb else value)
                elif cmd == "raw":
                    t = value
                if not t:
                    return f"'{cmd}' is not supported."
                resp = requests.get(f"http://{ip}/cm", params={"cmnd": t}, timeout=_TIMEOUT)
                return "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
            if typ == "shelly":
                ch = int(r.get("channel", 0))
                if r.get("gen", 2) in (2, "2", 3, "3"):
                    on = {"on": "true", "off": "false"}.get(cmd)
                    if cmd == "toggle":
                        resp = requests.get(f"http://{ip}/rpc/Switch.Toggle", params={"id": ch}, timeout=_TIMEOUT)
                    elif on:
                        resp = requests.get(f"http://{ip}/rpc/Switch.Set", params={"id": ch, "on": on}, timeout=_TIMEOUT)
                    else:
                        return f"'{cmd}' is not supported."
                else:
                    turn = {"on": "on", "off": "off", "toggle": "toggle"}.get(cmd)
                    if not turn:
                        return f"'{cmd}' is not supported."
                    resp = requests.get(f"http://{ip}/relay/{ch}", params={"turn": turn}, timeout=_TIMEOUT)
                return "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
            if typ == "wled":
                body: dict = {}
                if cmd in ("on", "off"):
                    body = {"on": cmd == "on"}
                elif cmd == "toggle":
                    body = {"on": "t"}
                elif cmd == "brightness":
                    body = {"on": True, "bri": int(pct(value) * 2.55)}
                elif cmd == "color":
                    rgb = parse_color(value)
                    if not rgb:
                        return f"I don't know the colour '{value}'."
                    body = {"on": True, "seg": [{"col": [list(rgb)]}]}
                elif cmd == "raw":
                    body = json.loads(value)
                else:
                    return f"'{cmd}' is not supported by WLED."
                resp = requests.post(f"http://{ip}/json/state", json=body, timeout=_TIMEOUT)
                return "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
            if typ == "esphome":
                domain = r.get("domain", "switch")
                oid = r.get("object_id", "")
                action = {"on": "turn_on", "off": "turn_off", "toggle": "toggle",
                          "open": "open", "close": "close", "stop": "stop"}.get(cmd)
                params = {}
                if cmd == "brightness":
                    action, params = "turn_on", {"brightness": int(pct(value) * 2.55)}
                if cmd == "color":
                    rgb = parse_color(value)
                    action, params = "turn_on", {"r": rgb[0], "g": rgb[1], "b": rgb[2]} if rgb else {}
                if not action:
                    return f"'{cmd}' is not supported."
                resp = requests.post(f"http://{ip}/{domain}/{oid}/{action}", params=params, timeout=_TIMEOUT)
                return "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
            if typ == "jarvis_esp32":
                pin = r.get("pin", 2)
                line = {"on": f"PIN {pin} HIGH", "off": f"PIN {pin} LOW", "toggle": f"TOGGLE {pin}"}.get(cmd)
                if cmd == "brightness":
                    line = f"PWM {pin} {int(pct(value) * 2.55)}"
                elif cmd == "raw":
                    line = value
                if not line:
                    return f"'{cmd}' is not supported."
                resp = requests.get(f"http://{ip}/cmd", params={"c": line}, timeout=_TIMEOUT)
                return resp.text.strip()[:200] or "ok"
            if typ == "roku":
                key = {"on": "PowerOn", "off": "PowerOff", "play": "Play", "pause": "Play", "mute": "VolumeMute",
                       "next": "Fwd", "previous": "Rev"}.get(cmd)
                if cmd == "raw":
                    key = value
                if not key:
                    return f"'{cmd}' is not supported by Roku."
                resp = requests.post(f"http://{ip}:8060/keypress/{key}", timeout=_TIMEOUT)
                return "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
            # custom: explicit URLs per command
            spec = (r.get("commands") or {}).get(cmd) or r.get(f"{cmd}_url")
            if not spec:
                return f"No URL is configured for '{cmd}' on {dev.name}."
            if isinstance(spec, str):
                spec = {"url": spec}
            url = str(spec["url"]).replace("{value}", str(value))
            method = str(spec.get("method", "GET")).upper()
            body = spec.get("body")
            if isinstance(body, str):
                body = body.replace("{value}", str(value))
            resp = requests.request(method, url, data=body if isinstance(body, str) else None,
                                    json=body if isinstance(body, (dict, list)) else None,
                                    headers=spec.get("headers"), timeout=_TIMEOUT)
            return "ok" if resp.status_code < 400 else f"HTTP {resp.status_code}: {resp.text[:120]}"
        except requests.exceptions.RequestException as e:
            return f"{dev.name} did not answer ({type(e).__name__}). Is it powered and on the same WiFi?"

    def status(self, dev: Device) -> str:
        r = dev.ref
        ip = r.get("ip", "")
        try:
            if r.get("type") == "tasmota":
                return requests.get(f"http://{ip}/cm", params={"cmnd": "Status 11"}, timeout=_TIMEOUT).text[:300]
            if r.get("type") == "shelly":
                return requests.get(f"http://{ip}/rpc/Shelly.GetStatus", timeout=_TIMEOUT).text[:300]
            if r.get("type") == "wled":
                s = requests.get(f"http://{ip}/json/state", timeout=_TIMEOUT).json()
                return f"on={s.get('on')} bri={s.get('bri')}"
            if r.get("type") == "jarvis_esp32":
                return requests.get(f"http://{ip}/status", timeout=_TIMEOUT).text[:300]
            if r.get("status_url"):
                return requests.get(r["status_url"], timeout=_TIMEOUT).text[:300]
        except requests.exceptions.RequestException as e:
            return f"no answer ({type(e).__name__})"
        return "status is not available for this device"


# ── MQTT ─────────────────────────────────────────────────────────────────────
class Mqtt(Backend):
    name = "mqtt"

    def _publish(self, topic: str, payload: str) -> str:
        import paho.mqtt.publish as publish
        auth = None
        if self.cfg.get("mqtt_user"):
            auth = {"username": self.cfg.get("mqtt_user"), "password": self.cfg.get("mqtt_password") or None}
        publish.single(topic, payload, hostname=self.cfg.get("mqtt_host") or "localhost",
                       port=int(self.cfg.get("mqtt_port") or 1883), auth=auth)
        return "ok"

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        r = dev.ref
        topic = r.get("topic") or f"jarvis/{dev.name.replace(' ', '_')}/cmd"
        payload = (r.get("payloads") or {}).get(cmd)
        if payload is None:
            payload = {"on": r.get("on_payload", "ON"), "off": r.get("off_payload", "OFF"),
                       "toggle": "TOGGLE"}.get(cmd, f"{cmd.upper()} {value}".strip())
        payload = str(payload).replace("{value}", str(value))
        if not (self.cfg.get("mqtt_host")):
            return "No MQTT broker is set in the smart-home settings."
        return self._publish(topic, payload)


# ── Wake-on-LAN ──────────────────────────────────────────────────────────────
def magic_packet(mac: str) -> bytes:
    hexmac = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(hexmac) != 12:
        raise ValueError("a MAC address has 12 hex digits")
    return b"\xff" * 6 + bytes.fromhex(hexmac) * 16


class Wol(Backend):
    name = "wol"

    def command(self, dev: Device, cmd: str, value: str = "") -> str:
        if cmd not in ("on", "wake", "start"):
            return "Wake-on-LAN can only switch a computer on."
        pkt = magic_packet(dev.ref.get("mac", ""))
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(pkt, (dev.ref.get("broadcast", "255.255.255.255"), 9))
        s.close()
        return "ok"


BACKENDS = {"homeassistant": HomeAssistant, "smartthings": SmartThings, "tuya": Tuya, "hue": Hue,
            "yeelight": Yeelight, "kasa": Kasa, "http": Http, "mqtt": Mqtt, "wol": Wol}
