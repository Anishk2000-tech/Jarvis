"""
telegram_notify — message the owner's phone through their Telegram bot.

Also sets the bridge up: give it the bot token from @BotFather and it prints a
pairing code in the HUD log; sending /pair <code> to the bot links the phone.
"""
from core import telegram_bridge


def telegram_notify(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action", "send")).lower().strip()
    if action == "setup":
        token = str(p.get("token", "")).strip()
        if ":" not in token:
            return "That does not look like a bot token (it has the form 123456:ABC…)."
        telegram_bridge.save_cfg(bot_token=token, owner_chat_id="", enabled=True)
        from core import runtime
        telegram_bridge.start(log=runtime.log)
        return "Telegram token saved. A pairing code will appear in the log in a few seconds."
    if action == "disable":
        telegram_bridge.save_cfg(enabled=False)
        return "Telegram bridge disabled."
    if not telegram_bridge.configured():
        return ("Telegram is not set up. The user must create a bot with @BotFather and give me "
                "the token (they can type it into the HUD).")
    try:
        if action == "screenshot":
            from actions.screen_processor import _capture_screen
            img, _ = _capture_screen()
            return telegram_bridge.send_photo(img, str(p.get("message", ""))[:900])
        if action == "camera":
            from actions.screen_processor import _capture_camera
            img, _ = _capture_camera()
            return telegram_bridge.send_photo(img, str(p.get("message", ""))[:900])
        msg = str(p.get("message", "")).strip()
        if not msg:
            return "No message given."
        return telegram_bridge.send_text(msg)
    except Exception as e:
        return f"Telegram failed: {e}"


TOOL = {
    "name": "telegram_notify",
    "description": (
        "Send a message, a screenshot or a webcam photo to the user's phone via their Telegram "
        "bot — e.g. 'text me when it's done', 'send me a picture of my screen'. action=setup "
        "stores a bot token given by the user."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "send | screenshot | camera | setup | disable"},
            "message": {"type": "STRING", "description": "Text (or photo caption)"},
            "token": {"type": "STRING", "description": "Bot token, only for setup"},
        },
        "required": ["action"],
    },
    "handler": telegram_notify,
}
