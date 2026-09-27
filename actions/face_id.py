"""
face_id — remember faces and recognise who is at the computer.

"Remember my face" enrols the owner; "this is my sister Priya, remember her"
enrols someone else; "who's in front of the camera?" identifies; presence mode
greets the owner, can lock the PC when they leave, and can alert about
strangers. Embeddings stay in memory/faces/ on this machine.
"""
from core import brain_config


def face_id(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action", "status")).lower().strip()
    name = str(p.get("name", "") or "").strip()
    try:
        from core import face_id as fid
    except Exception as e:
        return f"Face recognition is not available: {e}"

    def log(msg):
        if player:
            try:
                player.write_log(f"SYS: {msg}" if not msg.startswith(("SYS", "ERR")) else msg)
            except Exception:
                pass

    toggles = {"presence": "face_presence", "owner_only": "owner_only",
               "lock_on_leave": "lock_on_leave", "alert_unknown": "alert_unknown_faces",
               "greet": "greet_on_arrival"}
    if action in toggles:
        on = str(p.get("enabled", "true")).lower() in ("true", "1", "yes", "on")
        brain_config.save_senses({toggles[action]: on})
        if action == "presence" or (on and action in ("owner_only", "lock_on_leave", "alert_unknown")):
            if on:
                brain_config.save_senses({"face_presence": True})
                fid.presence().start(log=log)
            elif action == "presence":
                fid.presence().stop()
        return f"{action.replace('_', ' ')} is now {'on' if on else 'off'}."
    try:
        eng = fid.engine(log)
    except Exception as e:
        return f"Face models could not be loaded: {e}"
    if action in ("enroll", "enrol", "remember", "add", "add_person"):
        owner = action in ("enroll", "enrol", "remember") and (not name or bool(p.get("owner", True)))
        if not name:
            name = brain_config.user_name() or "owner"
        if player:
            try:
                player.start_camera_stream()
            except Exception:
                pass
        try:
            msg = eng.enroll(name, owner=owner, log=log)
        finally:
            if player:
                try:
                    player.stop_camera_stream()
                except Exception:
                    pass
        return msg
    if action in ("who", "identify", "recognize", "recognise"):
        from core.camera import hub
        frame = hub().snapshot()
        if frame is None:
            return f"No camera image — {hub().error or 'is a webcam connected?'}"
        seen = eng.identify(frame)
        if not seen:
            return "Nobody is in front of the camera."
        parts = [f"{s['name']} (match {s['score']:.2f})" for s in seen]
        return "In view: " + ", ".join(parts)
    if action in ("forget", "delete", "remove"):
        if not name:
            return "Whose face should I forget?"
        return f"Forgot {name}." if eng.forget(name) else f"I had no face stored for {name}."
    if action in ("list", "people"):
        if not eng.people:
            return "No faces are stored."
        return "Known faces: " + ", ".join(
            f"{n}{' (owner)' if i.get('owner') else ''}" for n, i in eng.people.items())
    s = brain_config.get_senses()
    pres = fid.presence()
    return (f"Known faces: {', '.join(eng.people) or 'none'}. Owner: {eng.owner() or 'not enrolled'}. "
            f"Presence watching: {'on' if pres.running() else 'off'}"
            f"{' — in view: ' + ', '.join(pres.in_view) if pres.running() and pres.in_view else ''}. "
            f"Owner-only mode: {'on' if s.get('owner_only') else 'off'}. "
            f"Lock on leave: {'on' if s.get('lock_on_leave') else 'off'}.")


TOOL = {
    "name": "face_id",
    "description": (
        "Face recognition with the webcam: enroll/remember the owner's face, add_person to learn "
        "someone else's face by name, who = identify people in front of the camera, forget, list, "
        "status, and switches: presence (watch continuously, greet the owner), owner_only (obey "
        "voice commands only while the owner is in view), lock_on_leave, alert_unknown."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "enroll | add_person | who | forget | list | status | presence | owner_only | lock_on_leave | alert_unknown | greet"},
            "name": {"type": "STRING", "description": "Person's name (add_person / forget)"},
            "enabled": {"type": "BOOLEAN", "description": "For switches: true = on, false = off"},
        },
        "required": ["action"],
    },
    "handler": face_id,
}
