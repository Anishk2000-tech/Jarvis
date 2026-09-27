"""
Talk to the assistant from anywhere through your own Telegram bot.

Setup (once):
  1. In Telegram, message @BotFather, send /newbot, and copy the token.
  2. Give the token to JARVIS (⚙ → AI BRAIN → Integrations, or type
     "set up telegram with token 123456:ABC…" into the HUD).
  3. The HUD log shows a pairing code; send  /pair <code>  to your bot.
     Only that chat is obeyed from then on — everyone else is ignored.

From the phone you can then type any request exactly as you would say it, and
the reply comes back as a message. Extra commands:
  /screenshot   a picture of the screen
  /camera       a webcam photo (home security)
  /status       CPU, memory, what the assistant is doing
  /stop         interrupt whatever it is saying

The assistant can also message you on its own (the telegram_notify tool):
"tell me on Telegram when the download finishes".
"""
from __future__ import annotations

import json
import random
import threading
import time
from typing import Callable

import requests

from core import brain_config, runtime

_API = "https://api.telegram.org/bot{token}/{method}"
_thread: threading.Thread | None = None
_stop = threading.Event()
_pair_code = ""
_awaiting_reply_until = 0.0
_log: Callable[[str], None] = print


def _cfg() -> dict:
    try:
        data = json.loads(brain_config.CONFIG_FILE.read_text(encoding="utf-8"))
        t = data.get("telegram")
        return dict(t) if isinstance(t, dict) else {}
    except Exception:
        return {}


def save_cfg(**updates) -> None:
    brain_config._save_section("telegram", updates)


def configured() -> bool:
    c = _cfg()
    return bool(c.get("bot_token")) and c.get("enabled", True)


def _call(method: str, _timeout: float = 30, files=None, **params):
    token = _cfg().get("bot_token", "")
    if not token:
        raise RuntimeError("Telegram is not set up")
    url = _API.format(token=token, method=method)
    if files:
        r = requests.post(url, data=params, files=files, timeout=_timeout)
    else:
        r = requests.post(url, json=params, timeout=_timeout)
    data = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description', r.status_code)}")
    return data.get("result")


def send_text(text: str) -> str:
    chat = _cfg().get("owner_chat_id")
    if not chat:
        return "Telegram is not paired yet."
    for i in range(0, len(text or ""), 3900):
        _call("sendMessage", chat_id=chat, text=text[i:i + 3900])
    return "Sent to Telegram."


def send_photo(data: bytes, caption: str = "") -> str:
    chat = _cfg().get("owner_chat_id")
    if not chat:
        return "Telegram is not paired yet."
    _call("sendPhoto", _timeout=60, files={"photo": ("image.jpg", data, "image/jpeg")},
          chat_id=str(chat), caption=caption[:1000])
    return "Photo sent to Telegram."


def _on_assistant_text(text: str) -> None:
    global _awaiting_reply_until
    if time.monotonic() < _awaiting_reply_until and text:
        try:
            send_text(text)
        except Exception as e:
            print(f"[Telegram] reply failed: {e}")
        _awaiting_reply_until = time.monotonic() + 8   # allow a short follow-up


def _handle(msg: dict) -> None:
    global _awaiting_reply_until
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    text = str(msg.get("text") or msg.get("caption") or "").strip()
    cfg = _cfg()
    owner = str(cfg.get("owner_chat_id") or "")
    if not owner:
        if text.startswith("/pair") and _pair_code and _pair_code in text:
            save_cfg(owner_chat_id=chat_id)
            _call("sendMessage", chat_id=chat_id,
                  text=f"Paired. {brain_config.assistant_name()} will take requests from this chat.")
            _log("SYS: Telegram paired with your phone.")
        return
    if chat_id != owner:
        return
    if not text:
        return
    low = text.lower()
    if low.startswith("/screenshot"):
        from actions.screen_processor import _capture_screen
        img, _ = _capture_screen()
        send_photo(img, "Screen")
        return
    if low.startswith("/camera"):
        from actions.screen_processor import _capture_camera
        img, _ = _capture_camera()
        send_photo(img, "Camera")
        return
    if low.startswith("/status"):
        import psutil
        vm = psutil.virtual_memory()
        eng = runtime.engine()
        busy = "speaking" if getattr(eng, "_is_speaking", False) else "idle"
        send_text(f"CPU {psutil.cpu_percent(interval=0.5):.0f}% · RAM {vm.percent:.0f}% · {busy}")
        return
    if low.startswith("/stop"):
        eng = runtime.engine()
        if eng:
            eng.interrupt()
        send_text("Stopped.")
        return
    if low.startswith("/start"):
        send_text("Send me any request, or /screenshot, /camera, /status, /stop.")
        return
    _log(f"SYS: Telegram → {text[:80]}")
    _awaiting_reply_until = time.monotonic() + 180
    if not runtime.user_command(text):
        send_text("The assistant is not running a session right now.")


def _loop() -> None:
    global _pair_code
    offset = 0
    backoff = 2
    while not _stop.is_set():
        if not configured():
            time.sleep(10)
            continue
        if not _cfg().get("owner_chat_id") and not _pair_code:
            _pair_code = str(random.randint(1000, 9999))
            try:
                me = _call("getMe")
                _log(f"SYS: Telegram: send  /pair {_pair_code}  to @{me.get('username')} to link your phone.")
            except Exception as e:
                _log(f"ERR: Telegram token rejected — {e}")
                time.sleep(60)
                continue
        try:
            updates = _call("getUpdates", _timeout=65, offset=offset,
                            allowed_updates=["message"], timeout=50)
            backoff = 2
            for u in updates or []:
                offset = max(offset, int(u.get("update_id", 0)) + 1)
                msg = u.get("message")
                if msg:
                    try:
                        _handle(msg)
                    except Exception as e:
                        print(f"[Telegram] handler error: {e}")
        except Exception as e:
            print(f"[Telegram] poll error: {e}")
            time.sleep(backoff)
            backoff = min(60, backoff * 2)


def start(log: Callable[[str], None] = print) -> None:
    global _thread, _log
    _log = log
    runtime.on_assistant_text(_on_assistant_text)
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="telegram-bridge")
    _thread.start()
