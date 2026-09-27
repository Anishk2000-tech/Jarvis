"""
smart_home — control WiFi / smart devices from every brand, the way the Samsung
SmartThings app does, but by voice and from one place.

Ecosystems (fill in the ones you use in ⚙ → PLUGIN SETTINGS → Smart Home, then
press TEST & IMPORT DEVICES — or just ask "import my smart home devices"):

  Home Assistant   URL + long-lived token. The widest coverage: it integrates
                   2000+ brands (Xiaomi/Roborock/Dreame vacuums, LG ThinQ and
                   Samsung appliances, Zigbee, Z-Wave, Sonos, Chromecast…).
  SmartThings      Personal access token from account.smartthings.com/tokens —
                   Samsung washers, dryers, ACs, fridges, TVs, Jet Bot vacuums
                   and everything else linked to your SmartThings account.
  Tuya / Smart Life  Cloud API key/secret, or local keys (tinytuya devices.json).
  Philips Hue      Bridge IP; press the bridge button, then IMPORT pairs it.
  Yeelight, TP-Link Kasa/Tapo, WLED, ESPHome, Shelly, Tasmota and this
  project's own ESP32 firmware are found on the LAN with "discover devices".
  MQTT             Any broker; devices publish/subscribe on topics.
  Wake-on-LAN      Switch a PC on by its MAC address.
  Custom HTTP      Any device with a URL per command.

Devices are remembered in memory/smart_home.json with a name, a room and
aliases, so "turn off the bedroom light", "start the robot vacuum", "set the AC
to 24" and "switch off all lights" work regardless of brand.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
from pathlib import Path

from plugins import _smart_home_backends as B

_BASE = Path(__file__).resolve().parent.parent
REGISTRY = _BASE / "memory" / "smart_home.json"
_lock = threading.RLock()
NS = "smart_home"


def _cfg() -> dict:
    try:
        from memory.config_manager import get_plugin_config
        return get_plugin_config(NS)
    except Exception:
        return {}


def _load() -> list[B.Device]:
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        return [B.Device.from_dict(d) for d in data.get("devices", [])]
    except Exception:
        return []


def _save(devs: list[B.Device]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps({"devices": [d.to_dict() for d in devs]}, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(REGISTRY)


def _backend(name: str, cfg: dict | None = None) -> B.Backend:
    cls = B.BACKENDS.get(name)
    if cls is None:
        raise ValueError(f"unknown backend '{name}'")
    return cls(cfg if cfg is not None else _cfg())


_STOP = {"the", "my", "a", "an", "please", "all", "every", "in", "of", "room", "device", "smart"}


def _norm(s: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in _STOP)


_KIND_WORDS = {"light": ("light", "lights", "lamp", "lamps", "bulb", "bulbs", "led"),
               "switch": ("switch", "switches", "plug", "plugs", "socket"),
               "plug": ("plug", "plugs", "socket"),
               "vacuum": ("vacuum", "robot", "cleaner", "roomba", "hoover"),
               "washer": ("washer", "washing", "laundry"),
               "tv": ("tv", "television"), "climate": ("ac", "aircon", "thermostat", "heater", "climate"),
               "cover": ("blind", "blinds", "curtain", "curtains", "shutter", "garage"),
               "lock": ("lock", "door lock"), "fan": ("fan", "fans")}


def resolve(text: str, devices: list[B.Device] | None = None) -> list[B.Device]:
    devs = devices if devices is not None else _load()
    raw = (text or "").lower()
    want = _norm(text)
    if not want:
        return []
    # exact name / alias
    for d in devs:
        if want in {_norm(d.name)} | {_norm(a) for a in d.aliases}:
            return [d]
    # group request: "all lights", "bedroom lights"
    plural_or_all = raw.strip().startswith(("all ", "every ")) or re.search(r"\b(lights|lamps|plugs|fans|switches)\b", raw)
    kind = next((k for k, words in _KIND_WORDS.items() if any(re.search(rf"\b{w}\b", raw) for w in words)), None)
    rooms = {_norm(d.room) for d in devs if d.room}
    room = next((r for r in rooms if r and r in want), None)
    if plural_or_all and kind:
        group = [d for d in devs if d.kind == kind and (not room or _norm(d.room) == room)]
        if group:
            return group
    # room + kind
    if room and kind:
        match = [d for d in devs if _norm(d.room) == room and d.kind == kind]
        if len(match) == 1:
            return match
    # fuzzy
    best, score = None, 0.0
    for d in devs:
        for cand in [d.name] + list(d.aliases) + ([f"{d.room} {d.name}"] if d.room else []):
            c = _norm(cand)
            s = difflib.SequenceMatcher(None, want, c).ratio()
            if want in c or c in want:
                s = max(s, 0.85)
            if s > score:
                best, score = d, s
    return [best] if best is not None and score >= 0.6 else []


_CMD_ALIASES = {"turn on": "on", "switch on": "on", "power on": "on", "turn off": "off",
                "switch off": "off", "power off": "off", "dim": "brightness", "set brightness": "brightness",
                "colour": "color", "set color": "color", "set temperature": "temperature", "temp": "temperature",
                "clean": "start", "start cleaning": "start", "go home": "dock", "return": "dock",
                "charge": "dock", "resume": "start", "run": "start", "volume up": "volume",
                "set mode": "mode", "wake": "on", "execute": "activate", "trigger": "activate"}


def _norm_cmd(cmd: str) -> str:
    c = (cmd or "").lower().strip().replace("_", " ")
    c = _CMD_ALIASES.get(c, c)
    return c.replace(" ", "_")


def _ident(d: B.Device) -> tuple:
    for k in ("entity_id", "device_id", "scene_id", "light", "group", "id", "ip", "mac", "topic"):
        if d.ref.get(k):
            return (d.backend, k, str(d.ref[k]))
    return (d.backend, "name", d.name)


def sync(values: dict | None = None) -> tuple[bool, str]:
    cfg = dict(values or _cfg())
    msgs, imported = [], []
    for name in ("homeassistant", "smartthings", "hue", "tuya"):
        be = _backend(name, cfg)
        if name == "hue" and cfg.get("hue_bridge") and not cfg.get("hue_user"):
            ok, res = B.Hue.pair(cfg["hue_bridge"])
            if ok:
                cfg["hue_user"] = res
                try:
                    from memory.config_manager import save_plugin_config
                    save_plugin_config(NS, {"hue_user": res})
                except Exception:
                    pass
                be = _backend(name, cfg)
                msgs.append("Hue bridge paired.")
            else:
                msgs.append(f"Hue: {res} (press the bridge button, then import again)")
                continue
        if not be.configured():
            continue
        try:
            found = be.discover()
            imported.append((name, found))
            msgs.append(f"{name}: {len(found)} devices")
        except Exception as e:
            msgs.append(f"{name}: failed — {str(e)[:120]}")
    with _lock:
        devs = _load()
        for name, found in imported:
            keep = [d for d in devs if not (d.backend == name and d.ref.get("_auto", True))]
            existing = {_ident(d): d for d in devs if d.backend == name}
            for f in found:
                old = existing.get(_ident(f))
                if old:
                    f.room, f.aliases = old.room, old.aliases
                    if old.ref.get("_renamed"):
                        f.name = old.name
                        f.ref["_renamed"] = True
                keep.append(f)
            devs = keep
        _save(devs)
    if not imported and not msgs:
        return False, ("No ecosystem is configured yet. Add Home Assistant, SmartThings, Hue or Tuya "
                       "details in ⚙ → PLUGIN SETTINGS → Smart Home, or say 'discover devices' for LAN devices.")
    total = sum(len(f) for _, f in imported)
    return bool(imported), f"Imported {total} devices. " + "; ".join(msgs)


def discover_lan(seconds: float = 4.0) -> str:
    """Find LAN devices: Yeelight, Kasa, and mDNS-advertised ESPHome, WLED,
    Shelly, Hue bridges and this project's ESP32 firmware."""
    found: list[B.Device] = []
    notes = []
    for name in ("yeelight", "kasa"):
        try:
            found += _backend(name).discover()
        except Exception as e:
            notes.append(f"{name}: {str(e)[:60]}")
    try:
        from zeroconf import ServiceBrowser, Zeroconf
        types = {"_esphomelib._tcp.local.": ("esphome", "switch"), "_wled._tcp.local.": ("wled", "light"),
                 "_shelly._tcp.local.": ("shelly", "switch"), "_jarvis._tcp.local.": ("jarvis_esp32", "switch"),
                 "_hue._tcp.local.": ("hue_bridge", "bridge")}
        seen: dict[str, tuple] = {}

        class L:
            def add_service(self, zc, typ, name):
                info = zc.get_service_info(typ, name, timeout=1500)
                if info and info.parsed_addresses():
                    seen[name] = (typ, info.parsed_addresses()[0], name.split(".")[0])

            def update_service(self, *a):
                pass

            def remove_service(self, *a):
                pass
        zc = Zeroconf()
        try:
            browsers = [ServiceBrowser(zc, t, L()) for t in types]
            import time
            time.sleep(seconds)
        finally:
            zc.close()
        for _n, (typ, ip, label) in seen.items():
            kind_type, kind = types[typ]
            if kind_type == "hue_bridge":
                notes.append(f"Hue bridge at {ip} — put {ip} in the Smart Home settings and import")
                continue
            found.append(B.Device(name=label.replace("-", " "), backend="http", kind=kind,
                                  ref={"type": kind_type, "ip": ip, "_auto": True}))
    except Exception as e:
        notes.append(f"mDNS: {str(e)[:60]}")
    if not found:
        return "No devices answered on the local network. " + "; ".join(notes)
    with _lock:
        devs = _load()
        have = {json.dumps(d.ref, sort_keys=True) for d in devs}
        new = [f for f in found if json.dumps(f.ref, sort_keys=True) not in have]
        _save(devs + new)
    return (f"Found {len(found)} device(s) on the network ({len(new)} new): "
            + ", ".join(f"{d.name} ({d.backend}{'/' + d.ref.get('type') if d.ref.get('type') else ''})" for d in found)
            + ("; " + "; ".join(notes) if notes else ""))


def _add_device(p: dict) -> str:
    name = str(p.get("device") or p.get("name") or "").strip()
    typ = str(p.get("type") or "").lower().strip()
    if not name or not typ:
        return "To add a device give it a name and a type (tasmota, shelly, wled, esphome, jarvis_esp32, " \
               "custom, mqtt, wol, yeelight, kasa, roku)."
    try:
        extra = json.loads(p.get("details") or "{}")
    except Exception:
        return "details must be JSON, e.g. {\"pin\": 5} or {\"on_url\": \"http://…\"}."
    addr = str(p.get("address") or extra.pop("ip", "") or "").strip()
    ref = {"_auto": False, **extra}
    kind = str(p.get("kind") or extra.pop("kind", "") or "switch")
    if typ in ("tasmota", "shelly", "wled", "esphome", "jarvis_esp32", "custom", "roku"):
        backend, ref["type"] = "http", typ
        if addr:
            ref["ip"] = addr
    elif typ == "mqtt":
        backend = "mqtt"
        ref.setdefault("topic", addr or f"jarvis/{name.replace(' ', '_')}/cmd")
    elif typ in ("wol", "wake_on_lan"):
        backend, ref["mac"] = "wol", addr or ref.get("mac", "")
        kind = "computer"
    elif typ in ("yeelight", "kasa"):
        backend, ref["ip"] = typ, addr
    else:
        return f"Unknown device type '{typ}'."
    dev = B.Device(name=name, backend=backend, ref=ref, kind=kind, room=str(p.get("room") or ""),
                   aliases=[a.strip() for a in str(p.get("aliases") or "").split(",") if a.strip()])
    with _lock:
        devs = [d for d in _load() if _norm(d.name) != _norm(name)]
        devs.append(dev)
        _save(devs)
    return f"Added {name} ({typ})."


def _list(room: str = "") -> str:
    devs = _load()
    if room:
        devs = [d for d in devs if _norm(room) in _norm(d.room) or _norm(room) in _norm(d.name)]
    if not devs:
        return ("No smart devices are registered. Set up an ecosystem in ⚙ → PLUGIN SETTINGS → Smart Home "
                "and say 'import my devices', or say 'discover devices' to scan the WiFi.")
    lines = [f"- {d.name} [{d.kind}, {d.backend}{', ' + d.room if d.room else ''}]" for d in devs[:150]]
    return f"{len(devs)} devices:\n" + "\n".join(lines)


def _control(p: dict) -> str:
    target = str(p.get("device") or "").strip()
    cmd = _norm_cmd(str(p.get("command") or "on"))
    value = str(p.get("value") if p.get("value") is not None else "").strip()
    devs = resolve(target)
    if not devs:
        known = ", ".join(d.name for d in _load()[:25])
        return f"I don't know a device called '{target}'." + (f" Known: {known}" if known else "")
    results = []
    for d in devs:
        try:
            res = _backend(d.backend).command(d, cmd, value)
        except Exception as e:
            res = f"failed — {type(e).__name__}: {str(e)[:120]}"
        results.append(f"{d.name}: {res}")
    if all(r.endswith(": ok") for r in results):
        return f"Done — {cmd.replace('_', ' ')}{(' ' + value) if value else ''} on " + ", ".join(d.name for d in devs) + "."
    return "; ".join(results)


def run(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "control").lower().strip()
    try:
        if action in ("control", "command", "set", "turn"):
            return _control(p)
        if action in ("list", "devices"):
            return _list(str(p.get("room") or ""))
        if action == "status":
            devs = resolve(str(p.get("device") or ""))
            if not devs:
                return f"I don't know a device called '{p.get('device')}'."
            return "; ".join(f"{d.name}: {_backend(d.backend).status(d)}" for d in devs[:8])
        if action in ("sync", "import"):
            return sync()[1]
        if action in ("discover", "scan"):
            return discover_lan()
        if action in ("add", "add_device"):
            return _add_device(p)
        if action in ("remove", "remove_device", "forget"):
            name = _norm(str(p.get("device") or ""))
            with _lock:
                devs = _load()
                keep = [d for d in devs if _norm(d.name) != name]
                _save(keep)
            return "Removed." if len(keep) < len(devs) else "No such device."
        if action in ("rename", "set_room", "alias"):
            devs = resolve(str(p.get("device") or ""))
            if len(devs) != 1:
                return "Which device exactly?"
            with _lock:
                allv = _load()
                for d in allv:
                    if d.to_dict() == devs[0].to_dict():
                        if p.get("new_name"):
                            d.name = str(p["new_name"])
                            d.ref["_renamed"] = True
                        if p.get("room"):
                            d.room = str(p["room"])
                        if p.get("aliases"):
                            d.aliases = sorted(set(d.aliases) | {a.strip() for a in str(p["aliases"]).split(",") if a.strip()})
                _save(allv)
            return "Updated."
        if action in ("ask_home", "assist"):
            ha = _backend("homeassistant")
            if not ha.configured():
                return "Home Assistant is not configured."
            return ha.converse(str(p.get("value") or p.get("command") or ""))
        return "Unknown action."
    except Exception as e:
        return f"Smart home error: {type(e).__name__}: {str(e)[:200]}"


PLUGIN = {
    "name": "smart_home",
    "description": (
        "Control smart/WiFi home devices of any brand — lights, bulbs, plugs, switches, fans, AC and "
        "thermostats, robot vacuums, washing machines and dryers, TVs, blinds, locks, scenes, ESP32 "
        "boards — via Home Assistant, SmartThings, Tuya/Smart Life, Hue, Yeelight, Kasa, WLED, "
        "ESPHome, Shelly, Tasmota, MQTT or Wake-on-LAN. Refer to devices by name or room "
        "('bedroom light', 'all lights'). Actions: control, status, list, import (from configured "
        "ecosystems), discover (scan WiFi), add, remove, rename, ask_home."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "control | status | list | import | discover | add | remove | rename | ask_home"},
            "device": {"type": "STRING", "description": "Device name, room + type, or 'all lights'"},
            "command": {"type": "STRING",
                        "description": "on | off | toggle | brightness | color | color_temp | temperature | mode | "
                                       "fan_speed | start | pause | stop | dock | open | close | position | lock | "
                                       "unlock | volume | mute | play | next | activate | raw"},
            "value": {"type": "STRING", "description": "Value for the command: 60, red, 24, cool, …"},
            "room": {"type": "STRING", "description": "Room (list / add / rename)"},
            "type": {"type": "STRING",
                     "description": "For add: tasmota | shelly | wled | esphome | jarvis_esp32 | custom | mqtt | wol | yeelight | kasa | roku"},
            "address": {"type": "STRING", "description": "For add: IP address, MQTT topic or MAC"},
            "details": {"type": "STRING", "description": "For add: extra JSON, e.g. {\"pin\": 5} or {\"on_url\": \"http://…\"}"},
            "new_name": {"type": "STRING", "description": "For rename"},
            "aliases": {"type": "STRING", "description": "Comma-separated nicknames"},
        },
        "required": ["action"],
    },
}


def _test_and_import(values: dict):
    return sync(values)


PLUGIN_SETTINGS = {
    "namespace": NS,
    "title": "🏠 Smart Home",
    "fields": [
        {"key": "ha_url", "label": "Home Assistant URL", "placeholder": "http://homeassistant.local:8123"},
        {"key": "ha_token", "label": "Home Assistant long-lived token", "type": "password"},
        {"key": "st_token", "label": "SmartThings personal access token", "type": "password",
         "placeholder": "account.smartthings.com/tokens"},
        {"key": "hue_bridge", "label": "Philips Hue bridge IP", "placeholder": "192.168.1.20"},
        {"key": "hue_user", "label": "Hue username (filled automatically)", "type": "password"},
        {"key": "tuya_api_key", "label": "Tuya IoT access ID", "type": "password"},
        {"key": "tuya_api_secret", "label": "Tuya IoT access secret", "type": "password"},
        {"key": "tuya_region", "label": "Tuya region", "type": "choice",
         "options": ["in", "us", "eu", "cn", "sg", "us-e", "eu-w"], "default": "in"},
        {"key": "mqtt_host", "label": "MQTT broker host", "placeholder": "192.168.1.10"},
        {"key": "mqtt_port", "label": "MQTT port", "default": "1883"},
        {"key": "mqtt_user", "label": "MQTT user"},
        {"key": "mqtt_password", "label": "MQTT password", "type": "password"},
        {"key": "kasa_user", "label": "TP-Link cloud e-mail (Tapo only)"},
        {"key": "kasa_password", "label": "TP-Link cloud password (Tapo only)", "type": "password"},
    ],
    "action": {"label": "TEST & IMPORT DEVICES", "run": _test_and_import},
}
