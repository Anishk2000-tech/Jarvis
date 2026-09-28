"""
hardware_control — drive ESP32, ESP8266 and Arduino boards, and the motors,
servos, relays, LEDs and sensors wired to them.

Boards run the small firmware in firmware/ (flash it once with the Arduino
IDE). They are reached three ways:

    serial   USB cable — any Arduino (Uno, Nano, Mega, Leonardo…), ESP32, ESP8266
    wifi     ESP32/ESP8266 on your network (http://<ip>/cmd?c=…), found by mDNS
             as jarvis-<name>.local
    mqtt     through a broker, for boards far away or behind other networks

All three speak the same line protocol, so the assistant does not care how a
board is connected:

    PING                          → OK JARVIS <board> <version>
    PIN <pin> HIGH|LOW            digital output (LEDs, relays, buzzers)
    TOGGLE <pin>
    PWM <pin> <0-255>             dimming, DC motor speed without a driver
    SERVO <pin> <0-180>           hobby servos
    MOTOR <A|B> <-255..255>       DC motor through an L298N / TB6612 / L9110
    STEPPER <steps> [rpm]         stepper through an A4988 / DRV8825 (STEP/DIR)
    READ <pin>                    digital input  → VAL <0|1>
    AREAD <pin>                   analog input   → VAL <0-4095 or 0-1023>
    DIST                          HC-SR04 ultrasonic → VAL <cm>
    TEMP                          DHT11/22 → VAL <°C> <%RH>
    STATUS                        → JSON

Named pins ("fan" → pin 5, "door servo" → pin 13) are stored per board so you
can say "turn on the fan" or "open the door servo to 90 degrees".
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
REGISTRY = _BASE / "memory" / "hardware.json"
FIRMWARE = _BASE / "firmware"
_lock = threading.RLock()
_serial_cache: dict[str, object] = {}
_serial_lock = threading.Lock()

_KNOWN_USB = {
    (0x2341, None): "Arduino", (0x2A03, None): "Arduino", (0x1A86, 0x7523): "CH340 (Arduino clone / ESP)",
    (0x1A86, 0x55D4): "CH9102 (ESP32)", (0x10C4, 0xEA60): "CP210x (ESP32/ESP8266)",
    (0x0403, 0x6001): "FTDI", (0x303A, None): "Espressif ESP32-S2/S3/C3",
}


def _load() -> dict:
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {"boards": {}}


def _save(data: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_ports() -> list[dict]:
    try:
        from serial.tools import list_ports as lp
    except Exception:
        return []
    out = []
    for p in lp.comports():
        label = ""
        for (vid, pid), name in _KNOWN_USB.items():
            if p.vid == vid and (pid is None or p.pid == pid):
                label = name
                break
        out.append({"port": p.device, "desc": p.description or "", "board": label,
                    "vid": p.vid, "pid": p.pid})
    return out


def _serial(port: str, baud: int):
    import serial
    with _serial_lock:
        s = _serial_cache.get(port)
        if s is not None and getattr(s, "is_open", False):
            return s
        s = serial.Serial(port, baud, timeout=2)
        # Most Arduinos reset when the port opens; give the bootloader time.
        time.sleep(2.0)
        s.reset_input_buffer()
        _serial_cache[port] = s
        return s


def send(board: dict, line: str, timeout: float = 4.0) -> str:
    t = board.get("transport", "serial")
    line = line.strip()
    if t == "serial":
        s = _serial(board["port"], int(board.get("baud", 115200)))
        with _serial_lock:
            s.reset_input_buffer()
            s.write((line + "\n").encode())
            s.flush()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                resp = s.readline().decode(errors="replace").strip()
                if resp and not resp.startswith("#"):
                    return resp
        return "no reply from the board (is the JARVIS firmware flashed?)"
    if t in ("wifi", "http"):
        import requests
        r = requests.get(f"http://{board['ip']}/cmd", params={"c": line}, timeout=timeout)
        return r.text.strip() or f"HTTP {r.status_code}"
    if t == "mqtt":
        import paho.mqtt.client as mqtt
        from memory.config_manager import get_plugin_config
        cfg = get_plugin_config("smart_home")
        topic = board.get("topic") or f"jarvis/{board.get('name', 'board')}"
        box: dict = {}
        ev = threading.Event()
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if cfg.get("mqtt_user"):
            cli.username_pw_set(cfg.get("mqtt_user"), cfg.get("mqtt_password") or None)

        def on_msg(_c, _u, msg):
            box["r"] = msg.payload.decode(errors="replace")
            ev.set()
        cli.on_message = on_msg
        cli.connect(cfg.get("mqtt_host") or "localhost", int(cfg.get("mqtt_port") or 1883), 30)
        cli.subscribe(topic + "/resp")
        cli.loop_start()
        try:
            cli.publish(topic + "/cmd", line)
            ev.wait(timeout)
        finally:
            cli.loop_stop()
            cli.disconnect()
        return box.get("r", "sent (no reply)")
    return f"unknown transport '{t}'"


def _board(name: str) -> tuple[str, dict] | None:
    data = _load()
    boards = data.get("boards", {})
    if not boards:
        return None
    if not name:
        n = next(iter(boards))
        return n, boards[n]
    key = name.lower().strip()
    for n, b in boards.items():
        if n.lower() == key:
            return n, b
    for n, b in boards.items():
        if key in n.lower() or n.lower() in key:
            return n, b
    return None


def _pin(board: dict, pin) -> str:
    """A pin number, or a name given to one ("fan")."""
    s = str(pin).strip().lower()
    names = {k.lower(): v for k, v in (board.get("pins") or {}).items()}
    if s in names:
        return str(names[s])
    for k, v in names.items():
        if k in s or s in k:
            return str(v)
    m = re.search(r"\d+", s)
    if m:
        return m.group(0)
    raise ValueError(f"unknown pin '{pin}' — name it first (action=name_pin)")


def _discover_wifi(seconds: float = 3.0) -> list[dict]:
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except Exception:
        return []
    found: list[dict] = []

    class L:
        def add_service(self, zc, typ, name):
            info = zc.get_service_info(typ, name, timeout=1500)
            if info and info.parsed_addresses():
                found.append({"name": name.split(".")[0], "ip": info.parsed_addresses()[0]})

        def update_service(self, *a):
            pass

        def remove_service(self, *a):
            pass
    zc = Zeroconf()
    try:
        ServiceBrowser(zc, "_jarvis._tcp.local.", L())
        time.sleep(seconds)
    finally:
        zc.close()
    return found


def run(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "").lower().strip()
    try:
        if action in ("ports", "list_ports"):
            ports = list_ports()
            if not ports:
                return "No serial ports found. Plug the board in with a data USB cable (not charge-only)."
            return "Serial ports: " + "; ".join(f"{x['port']} {x['board'] or x['desc']}" for x in ports)
        if action in ("discover", "scan"):
            found = _discover_wifi()
            with _lock:
                data = _load()
                for f in found:
                    data["boards"].setdefault(f["name"], {"transport": "wifi", "ip": f["ip"], "pins": {}})
                _save(data)
            return ("Found WiFi boards: " + ", ".join(f"{f['name']} ({f['ip']})" for f in found)) if found \
                else "No JARVIS boards answered on WiFi. Check the board is powered and joined your network."
        if action in ("add", "add_board", "connect"):
            name = str(p.get("board") or "board").strip()
            addr = str(p.get("address") or "").strip()
            b: dict = {"pins": {}}
            if re.match(r"^(com\d+|/dev/)", addr, re.I):
                b.update(transport="serial", port=addr, baud=int(p.get("value") or 115200))
            elif addr.startswith("mqtt:") or p.get("transport") == "mqtt":
                b.update(transport="mqtt", topic=addr.replace("mqtt:", "") or f"jarvis/{name}")
            elif addr:
                b.update(transport="wifi", ip=addr)
            else:
                ports = [x for x in list_ports() if x["board"]] or list_ports()
                if not ports:
                    return "Give the board's COM port or IP address."
                b.update(transport="serial", port=ports[0]["port"], baud=115200)
            with _lock:
                data = _load()
                old = data["boards"].get(name, {})
                b["pins"] = old.get("pins", {})
                data["boards"][name] = b
                _save(data)
            try:
                pong = send(b, "PING")
            except Exception as e:
                pong = f"not answering yet ({e})"
            return f"Board '{name}' saved ({b['transport']}). Ping: {pong}"
        if action in ("boards", "list"):
            boards = _load().get("boards", {})
            if not boards:
                return ("No boards yet. Flash firmware/jarvis_esp32 or firmware/jarvis_arduino, plug it in, "
                        "then say 'add my board'.")
            return "; ".join(f"{n} ({b.get('transport')} {b.get('port') or b.get('ip') or b.get('topic')}, "
                             f"pins: {b.get('pins') or 'none named'})" for n, b in boards.items())
        if action == "firmware":
            return (f"Firmware sketches are in {FIRMWARE}. ESP32/ESP8266: open jarvis_esp32/jarvis_esp32.ino in the "
                    "Arduino IDE, set your WiFi name and password at the top, pick your board and upload. "
                    "Arduino Uno/Nano/Mega: upload jarvis_arduino/jarvis_arduino.ino.")
        found = _board(str(p.get("board") or ""))
        if not found:
            return "No board is registered yet. Say 'add my board' after plugging it in (or give its IP)."
        name, board = found
        if action == "name_pin":
            label = str(p.get("label") or "").strip()
            pin = str(p.get("pin") or "").strip()
            if not label or not pin.isdigit():
                return "Give a label and a pin number."
            with _lock:
                data = _load()
                data["boards"][name].setdefault("pins", {})[label] = int(pin)
                _save(data)
            return f"On {name}, '{label}' is now pin {pin}."
        value = p.get("value")
        if action in ("on", "off", "digital_write", "high", "low"):
            level = "HIGH" if action in ("on", "high") or str(value).lower() in ("1", "on", "high", "true") \
                else "LOW"
            return send(board, f"PIN {_pin(board, p.get('pin'))} {level}")
        if action == "toggle":
            return send(board, f"TOGGLE {_pin(board, p.get('pin'))}")
        if action in ("pwm", "analog_write", "dim"):
            v = max(0, min(255, int(float(value or 0))))
            return send(board, f"PWM {_pin(board, p.get('pin'))} {v}")
        if action == "servo":
            v = max(0, min(180, int(float(value or 90))))
            return send(board, f"SERVO {_pin(board, p.get('pin'))} {v}")
        if action == "motor":
            m = str(p.get("pin") or "A").upper()[:1]
            v = max(-255, min(255, int(float(value or 0))))
            res = send(board, f"MOTOR {m} {v}")
            secs = float(p.get("seconds") or 0)
            if secs > 0 and v != 0:
                time.sleep(min(secs, 60))
                res += " → " + send(board, f"MOTOR {m} 0")
            return res
        if action == "stepper":
            steps = int(float(value or 200))
            rpm = int(float(p.get("seconds") or 60))
            return send(board, f"STEPPER {steps} {rpm}", timeout=max(5.0, abs(steps) / 100))
        if action in ("read", "digital_read"):
            return send(board, f"READ {_pin(board, p.get('pin'))}")
        if action in ("analog_read", "aread"):
            return send(board, f"AREAD {_pin(board, p.get('pin'))}")
        if action in ("distance", "dist"):
            return send(board, "DIST")
        if action in ("temperature", "temp", "humidity"):
            return send(board, "TEMP")
        if action in ("status", "ping"):
            return send(board, "STATUS" if action == "status" else "PING")
        if action in ("raw", "send"):
            return send(board, str(value or ""))
        return "Unknown action."
    except Exception as e:
        return f"Hardware error: {type(e).__name__}: {str(e)[:200]}"


PLUGIN = {
    "name": "hardware_control",
    "description": (
        "Control ESP32 / ESP8266 / Arduino boards and what is wired to them — LEDs, relays, DC motors, "
        "servos, steppers, buzzers — and read sensors (digital, analog, distance, temperature). Boards "
        "connect by USB serial, WiFi or MQTT and run the JARVIS firmware. Pins can be given names "
        "('fan', 'door servo'). Actions: ports, discover, add, boards, firmware, name_pin, on, off, toggle, "
        "pwm, servo, motor, stepper, read, analog_read, distance, temperature, status, raw."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "See description"},
            "board": {"type": "STRING", "description": "Board name (optional when there is one)"},
            "pin": {"type": "STRING", "description": "Pin number or pin name; for motor: A or B"},
            "value": {"type": "STRING",
                      "description": "pwm 0-255 | servo angle 0-180 | motor speed -255..255 | stepper steps | raw line"},
            "seconds": {"type": "NUMBER", "description": "motor: run this long then stop | stepper: rpm"},
            "address": {"type": "STRING", "description": "For add: COM3, /dev/ttyUSB0, an IP, or mqtt:topic"},
            "label": {"type": "STRING", "description": "For name_pin: the name to give the pin"},
        },
        "required": ["action"],
    },
}
