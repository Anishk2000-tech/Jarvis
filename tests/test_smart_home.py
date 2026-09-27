import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from plugins import smart_home as sh, _smart_home_backends as B


class Fake:
    def __init__(self):
        self.calls = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _send(self, obj, code=200):
                b = json.dumps(obj).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}") if n else {}
            def do_GET(self):
                outer.calls.append(("GET", self.path, None))
                if self.path == "/api/states":
                    return self._send([
                        {"entity_id": "light.bedroom", "state": "on", "attributes": {"friendly_name": "Bedroom Light"}},
                        {"entity_id": "vacuum.roborock", "state": "docked", "attributes": {"friendly_name": "Robot Vacuum"}},
                        {"entity_id": "climate.ac", "state": "cool", "attributes": {"friendly_name": "Living Room AC"}},
                        {"entity_id": "automation.x", "state": "on", "attributes": {}}])
                if self.path.startswith("/api/states/"):
                    return self._send({"state": "on", "attributes": {"brightness": 200}})
                if self.path.startswith("/rpc/") or self.path.startswith("/cm") or self.path.startswith("/relay"):
                    return self._send({"ok": True})
                self._send({})
            def do_POST(self):
                outer.calls.append(("POST", self.path, self._body()))
                if self.path == "/api/conversation/process":
                    return self._send({"response": {"speech": {"plain": {"speech": "Turned on the lights"}}}})
                self._send([] if self.path.startswith("/api/services") else {"ok": True})
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.host = f"127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = Fake()
    monkeypatch.setattr(sh, "REGISTRY", tmp_path / "sh.json")
    cfg = {"ha_url": fake.url, "ha_token": "t"}
    monkeypatch.setattr(sh, "_cfg", lambda: cfg)
    yield fake
    fake.srv.shutdown()


def test_import_and_control_home_assistant(env):
    ok, msg = sh.sync()
    assert ok and "Imported 3 devices" in msg, msg
    out = sh.run({"action": "control", "device": "bedroom light", "command": "brightness", "value": "40"})
    assert out.startswith("Done"), out
    assert ("POST", "/api/services/light/turn_on", {"entity_id": "light.bedroom", "brightness_pct": 40}) in env.calls
    sh.run({"action": "control", "device": "the robot vacuum", "command": "clean"})
    assert ("POST", "/api/services/vacuum/start", {"entity_id": "vacuum.roborock"}) in env.calls
    sh.run({"action": "control", "device": "living room ac", "command": "temperature", "value": "24"})
    assert ("POST", "/api/services/climate/set_temperature", {"entity_id": "climate.ac", "temperature": 24.0}) in env.calls
    sh.run({"action": "control", "device": "bedroom light", "command": "color", "value": "purple"})
    assert ("POST", "/api/services/light/turn_on", {"entity_id": "light.bedroom", "rgb_color": [150, 0, 255]}) in env.calls
    assert "on" in sh.run({"action": "status", "device": "bedroom light"})
    assert sh.run({"action": "ask_home", "value": "lights on"}) == "Turned on the lights"
    # rename survives re-import
    sh.run({"action": "rename", "device": "bedroom light", "new_name": "Night Lamp", "room": "bedroom"})
    sh.sync()
    names = [d.name for d in sh._load()]
    assert "Night Lamp" in names and "Bedroom Light" not in names
    assert "I don't know" in sh.run({"action": "control", "device": "garage door xyz", "command": "on"})


def test_lan_device_types(env):
    host = env.host
    sh.run({"action": "add", "device": "desk strip", "type": "wled", "address": host, "room": "office"})
    sh.run({"action": "add", "device": "heater plug", "type": "shelly", "address": host})
    sh.run({"action": "add", "device": "fan relay", "type": "tasmota", "address": host})
    sh.run({"action": "add", "device": "office light", "type": "wled", "address": host, "room": "office", "kind": "light"})
    assert sh.run({"action": "control", "device": "desk strip", "command": "color", "value": "#00ff00"}).startswith("Done")
    assert ("POST", "/json/state", {"on": True, "seg": [{"col": [[0, 255, 0]]}]}) in env.calls
    assert sh.run({"action": "control", "device": "heater plug", "command": "off"}).startswith("Done")
    assert any(c[1].startswith("/rpc/Switch.Set?id=0&on=false") for c in env.calls)
    sh.run({"action": "control", "device": "fan relay", "command": "on"})
    assert any(c[1].startswith("/cm?cmnd=Power+On") for c in env.calls)
    assert "desk strip" in sh.run({"action": "list"})


def test_resolve_groups_and_fuzzy(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "REGISTRY", tmp_path / "r.json")
    devs = [B.Device("Kitchen Light", "hue", {"light": "1"}, "light", "kitchen"),
            B.Device("Bedroom Lamp", "hue", {"light": "2"}, "light", "bedroom"),
            B.Device("Washing Machine", "smartthings", {"device_id": "w"}, "washer"),
            B.Device("TV", "smartthings", {"device_id": "t"}, "tv", aliases=["telly"])]
    assert len(sh.resolve("all lights", devs)) == 2
    assert [d.name for d in sh.resolve("the washing machine", devs)] == ["Washing Machine"]
    assert [d.name for d in sh.resolve("telly", devs)] == ["TV"]
    assert [d.name for d in sh.resolve("bedroom light", devs)] == ["Bedroom Lamp"]
    assert sh.resolve("garage", devs) == []


def test_helpers():
    assert B.parse_color("red") == (255, 0, 0) and B.parse_color("#10ff20") == (16, 255, 32)
    assert B.parse_color("warm white") == (255, 197, 143)
    pkt = B.magic_packet("AA:BB:CC:DD:EE:FF")
    assert len(pkt) == 102 and pkt[:6] == b"\xff" * 6
