"""
A small switchboard between the running engine and the parts of the app that
need to reach it from elsewhere — the scheduler, the Telegram bridge, face
presence, skills that add tools, the settings screen.

Everything here is safe to call when no engine is running yet: it does nothing.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Callable

_engine = None
_lock = threading.Lock()
_text_listeners: list[Callable[[str], None]] = []
_state: dict = {}


def set_engine(engine) -> None:
    global _engine
    _engine = engine


def engine():
    return _engine


def ui():
    e = _engine
    return getattr(e, "ui", None) if e is not None else None


def log(text: str) -> None:
    u = ui()
    if u is not None:
        try:
            u.write_log(text)
            return
        except Exception:
            pass
    print(text)


def inject(instruction: str) -> bool:
    """Hand the assistant an instruction from the application (not the user).
    It answers out loud as it would to anything else. Returns False when no
    session is up."""
    e = _engine
    if e is None:
        return False
    try:
        e.speak(instruction)
        return True
    except Exception:
        return False


def user_command(text: str) -> bool:
    """A request typed or sent by the user through another channel (phone,
    Telegram): handled exactly like typing into the HUD."""
    e = _engine
    if e is None:
        return False
    try:
        cb = getattr(e, "_on_text_command", None)
        if cb:
            cb(text)
            return True
    except Exception:
        pass
    return False


def on_assistant_text(cb: Callable[[str], None]) -> None:
    with _lock:
        if cb not in _text_listeners:
            _text_listeners.append(cb)


def emit_assistant_text(text: str) -> None:
    with _lock:
        listeners = list(_text_listeners)
    for cb in listeners:
        try:
            cb(text)
        except Exception as ex:
            print(f"[runtime] listener failed: {ex}")


def set_state(key: str, value) -> None:
    _state[key] = value


def get_state(key: str, default=None):
    return _state.get(key, default)


def reload_tools() -> str:
    """Re-read plugins/ so a new skill is usable without restarting."""
    e = _engine
    if e is None:
        return "No session is running."
    fn = getattr(e, "reload_plugins", None)
    if not fn:
        return "This engine cannot reload tools; restart JARVIS to load the new skill."
    try:
        return fn()
    except Exception as ex:
        return f"Reload failed: {ex}"


def restart_app() -> None:
    """Start a fresh copy of the app and leave. Used when switching between the
    Gemini Live engine and the local engine, which cannot swap in place."""
    args = [sys.executable] + list(sys.argv)
    kw: dict = {"close_fds": True}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    try:
        subprocess.Popen(args, cwd=os.getcwd(), **kw)
    finally:
        os._exit(0)
