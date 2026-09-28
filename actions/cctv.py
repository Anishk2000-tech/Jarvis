"""
cctv — the house's WiFi cameras (core/cctv.py).

"Add my Tapo camera at 192.168.1.40 as Front Door", "find the cameras on my
network", "what's happening at the gate?", "anyone at the front door?",
"I'm leaving — watch the house", "what happened while I was out?",
"send me a picture of the back yard".
"""
from __future__ import annotations

import time

from core import cctv


def _describe(cam: dict, question: str) -> tuple[str, bytes]:
    import cv2
    from core import llm, perception, vision_detect
    frame = cctv.manager().snapshot(cam)
    if frame is None:
        return f"I could not get a picture from {cam['name']} — the camera did not answer.", b""
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    jpeg = buf.tobytes() if ok else b""
    det = vision_detect.detector()
    seen = vision_detect.summarize(det.detect(frame, min_conf=0.45), skip=vision_detect.BACKGROUND) \
        if det is not None else ""
    if perception._can_see() and jpeg:
        try:
            txt = llm.complete([f"[IMAGE SOURCE: SECURITY CAMERA '{cam['name']}'] {question or 'What is happening here?'}"
                                f"\n(Object detector sees: {seen or 'nothing notable'}.) Answer precisely from "
                                "what is visible.", llm.image_part(jpeg, "image/jpeg")],
                               role="vision", max_tokens=250, timeout=90)
            if txt:
                return f"{cam['name']} camera: {txt}", jpeg
        except Exception as e:
            print(f"[CCTV] look failed: {e}")
    return (f"{cam['name']} camera: the detector sees {seen or 'nobody and nothing notable'}. "
            "(No vision model is set, so I cannot describe more.)"), jpeg


def cctv_tool(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action", "list")).lower().strip()
    name = str(p.get("camera") or p.get("name") or "").strip()
    data = cctv.load_cfg()
    mgr = cctv.manager()

    if action in ("list", "status"):
        if not data["cameras"]:
            return ("No CCTV cameras are set up. Add one with action=add (name, and either the stream url, "
                    "or brand + ip + user + password), or action=discover to find ONVIF cameras.")
        lines = [f"Mode: {data['mode']}."]
        for c in mgr.status():
            err = f" ({c['error'][:80]})" if c["error"] else ""
            lines.append(f"- {c['name']}: {c['status']}{err}")
        return "\n".join(lines)

    if action in ("add", "update"):
        if not name:
            return "Give the camera a name, e.g. 'Front Door'."
        url = str(p.get("url") or "").strip()
        user, pw = str(p.get("user") or ""), str(p.get("password") or "")
        if not url:
            ip = str(p.get("ip") or "").strip()
            if not ip:
                return ("Give either the camera's stream url, or its brand and IP address (plus the camera's "
                        "user name and password). Brands: " + ", ".join(sorted(cctv.BRANDS)) + ".")
            brand = str(p.get("brand") or "generic")
            if brand.lower() == "onvif":
                try:
                    uris = cctv.onvif_stream_uris(f"http://{ip}/onvif/device_service", user, pw)
                except Exception as e:
                    return f"ONVIF did not answer at {ip}: {e}"
                if not uris:
                    return f"The camera at {ip} answered ONVIF but offered no stream."
                url = uris[0]["uri"]
            else:
                url = cctv.build_url(brand, ip, user, pw, int(p.get("channel") or 1),
                                     int(p["port"]) if p.get("port") else None)
        else:
            url = cctv.with_credentials(url, user, pw)
        frame = None
        err = ""
        try:
            frame = cctv.grab_once(url, timeout=15)
        except Exception as e:
            err = str(e)
        detect = p.get("detect")
        if isinstance(detect, str):
            detect = [d.strip() for d in detect.split(",") if d.strip()]
        cam = cctv.add_camera(name, url, detect or None)
        mgr.sync()
        if frame is None:
            return (f"Saved '{cam['name']}' ({cctv.mask(url)}), but no picture came back yet"
                    + (f": {err[:160]}" if err else "") + ". Check the IP, the camera's user/password, and "
                    "that RTSP is enabled in the camera's app.")
        h, w = frame.shape[:2]
        return f"Added '{cam['name']}' — connected, {w}×{h}. I'm watching it (mode {data['mode']})."

    if action in ("remove", "delete"):
        ok = cctv.remove_camera(name)
        mgr.sync()
        return f"Removed '{name}'." if ok else f"No camera called '{name}'."

    if action == "discover":
        try:
            found = cctv.discover_onvif(timeout=float(p.get("seconds") or 3))
        except Exception as e:
            return f"Discovery failed: {e}"
        if not found:
            return ("No ONVIF cameras answered. Many cameras need ONVIF switched on in their app; otherwise add "
                    "them by brand and IP.")
        user, pw = str(p.get("user") or ""), str(p.get("password") or "")
        lines = [f"Found {len(found)} camera(s):"]
        for d in found:
            label = " ".join(x for x in (d.get("name"), d.get("hardware")) if x) or "camera"
            line = f"- {d['ip']} ({label})"
            if user:
                try:
                    uris = cctv.onvif_stream_uris(d["xaddr"], user, pw)
                    if uris:
                        line += f" stream {cctv.mask(uris[0]['uri'])}"
                except Exception as e:
                    line += f" — {str(e)[:60]}"
            lines.append(line)
        lines.append("Add one with action=add, a name, brand=onvif, the ip, user and password.")
        return "\n".join(lines)

    if action in ("look", "check", "describe", "view"):
        cams = data["cameras"] if name.lower() in ("", "all", "every", "everything") else \
            [c for c in [cctv.find_camera(data, name)] if c]
        if not cams:
            return f"No camera called '{name}'." if name else "No cameras are set up."
        out = []
        for cam in cams[:4]:
            text, jpeg = _describe(cam, str(p.get("question") or ""))
            out.append(text)
            if jpeg and player is not None:
                try:
                    player.show_camera_frame(jpeg)
                except Exception:
                    pass
        return "\n".join(out)

    if action in ("snapshot", "send", "photo"):
        cam = cctv.find_camera(data, name)
        if cam is None:
            return f"No camera called '{name}'."
        import cv2
        frame = mgr.snapshot(cam)
        if frame is None:
            return f"{cam['name']} did not return a picture."
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        from core import telegram_bridge
        if not telegram_bridge.configured():
            if player is not None:
                player.show_camera_frame(buf.tobytes())
            return "Shown on screen. (Telegram is not set up, so I cannot send it to the phone.)"
        return telegram_bridge.send_photo(buf.tobytes(), f"📹 {cam['name']} — {time.strftime('%H:%M')}")

    if action in ("events", "history", "log"):
        hours = float(p.get("hours") or 12)
        evs = cctv.events(name, hours=hours)
        if not evs:
            return f"Nothing was seen{' at ' + name if name else ''} in the last {hours:g} hours."
        lines = [f"{len(evs)} event(s) in the last {hours:g} h:"]
        for e in evs[-25:]:
            lines.append(f"- {e['t'][11:16]} {e['camera']}: {e.get('description') or e['summary']}")
        return "\n".join(lines)

    if action in ("mode", "arm", "disarm", "set_mode"):
        want = str(p.get("mode") or ("off" if action == "disarm" else "away" if action == "arm" else "")).strip()
        try:
            mode = cctv.set_mode(want)
        except ValueError as e:
            return str(e)
        mgr.sync()
        if not mgr.running() and mode != "off":
            from core import runtime
            mgr.start(runtime.log)
        return {"home": "Home mode: I'll tell you by voice when someone is at a camera.",
                "night": "Night mode: I'll announce people, and send unknown visitors to your phone.",
                "away": "Away mode: anything notable goes to your phone with a photo.",
                "off": "CCTV monitoring is off."}[mode]

    if action == "show":
        from core import runtime
        ui = runtime.ui()
        if ui is not None and hasattr(ui, "open_cctv"):
            ui.open_cctv()
            return "Camera wall opened."
        return "The camera wall is not available."

    return "Unknown action. Use list, add, remove, discover, look, snapshot, events, mode or show."


TOOL = {
    "name": "cctv",
    "description": (
        "The user's WiFi/CCTV cameras: look at what a camera sees now (look), what happened (events), "
        "switch monitoring mode (home = announce people by voice, night, away = alerts to phone, off), "
        "send a snapshot to the phone, add/remove/discover cameras, show the camera wall. Use this for "
        "security cameras, NOT for your own webcam."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "list | look | events | mode | snapshot | add | remove | discover | show"},
            "camera": {"type": "STRING", "description": "Camera name ('all' for look)"},
            "question": {"type": "STRING", "description": "For look: what to check"},
            "mode": {"type": "STRING", "description": "home | night | away | off"},
            "hours": {"type": "NUMBER", "description": "For events: how far back"},
            "url": {"type": "STRING", "description": "For add: full rtsp:// or http:// stream URL"},
            "brand": {"type": "STRING", "description": "For add: hikvision, dahua, cpplus, imou, tapo, ezviz, "
                                                       "reolink, uniview, onvif, esp32cam, ipwebcam, generic…"},
            "ip": {"type": "STRING", "description": "For add: camera IP address"},
            "user": {"type": "STRING", "description": "Camera user name"},
            "password": {"type": "STRING", "description": "Camera password"},
            "channel": {"type": "NUMBER", "description": "NVR/DVR channel, default 1"},
        },
        "required": ["action"],
    },
    "handler": cctv_tool,
}
