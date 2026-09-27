import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from plugins import maker_hardware as mh


def test_wifi_board(tmp_path, monkeypatch):
    got = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query).get("c", [""])[0]
            got.append(q)
            body = ("OK JARVIS esp32 test 1.0" if q == "PING" else f"OK {q}").encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(mh, "REGISTRY", tmp_path / "hw.json")
    monkeypatch.setattr(mh.time, "sleep", lambda s: None)
    ip = f"127.0.0.1:{srv.server_address[1]}"
    assert "Ping: OK JARVIS esp32" in mh.run({"action": "add", "board": "garage", "address": ip})
    assert mh.run({"action": "name_pin", "label": "fan", "pin": "5"}) == "On garage, 'fan' is now pin 5."
    assert mh.run({"action": "on", "pin": "the fan"}) == "OK PIN 5 HIGH"
    assert mh.run({"action": "servo", "pin": "13", "value": "90"}) == "OK SERVO 13 90"
    out = mh.run({"action": "motor", "pin": "A", "value": "180", "seconds": 2})
    assert out == "OK MOTOR A 180 → OK MOTOR A 0"
    assert "unknown pin" in mh.run({"action": "on", "pin": "laser"})
    assert "garage" in mh.run({"action": "boards"})
    srv.shutdown()
