"""
media_control — the keyboard's media keys, for whatever is playing: Spotify,
YouTube in a browser, VLC, Windows Media Player, Netflix…
"""


def media_control(parameters: dict, player=None) -> str:
    action = str((parameters or {}).get("action", "play_pause")).lower().strip()
    keys = {"play_pause": "playpause", "play": "playpause", "pause": "playpause", "resume": "playpause",
            "next": "nexttrack", "skip": "nexttrack", "previous": "prevtrack", "prev": "prevtrack",
            "back": "prevtrack", "stop": "stop", "mute": "volumemute", "volume_up": "volumeup",
            "volume_down": "volumedown"}
    key = keys.get(action)
    if not key:
        return f"Unknown media action '{action}'."
    try:
        import pyautogui
        times = 1
        if key in ("volumeup", "volumedown"):
            try:
                times = max(1, min(25, int((parameters or {}).get("steps") or 5)))
            except (TypeError, ValueError):
                times = 5
        for _ in range(times):
            pyautogui.press(key)
        return f"Sent {action.replace('_', ' ')}."
    except Exception as e:
        return f"Media keys are unavailable: {e}"


TOOL = {
    "name": "media_control",
    "description": ("System-wide media keys for whatever app is playing music or video (Spotify, YouTube, "
                    "VLC…): play_pause, next, previous, stop, mute, volume_up, volume_down."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "play_pause | next | previous | stop | mute | volume_up | volume_down"},
            "steps": {"type": "INTEGER", "description": "Volume steps (default 5)"},
        },
        "required": ["action"],
    },
    "handler": media_control,
}
