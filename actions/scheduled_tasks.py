"""
scheduled_tasks — let the assistant do something later, once or on a schedule.

"Every weekday at 8:30 tell me the weather and the top news"
"In 20 minutes check if the download in my Downloads folder finished"
"Every 2 hours remind me to drink water"

The task is carried out by the assistant itself at the due time (see
core/scheduler.py), with all its tools — not just a notification. For a plain
OS notification that fires even when the app is closed, the `reminder` tool
still exists.
"""
from core import scheduler


def scheduled_tasks(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action", "add")).lower().strip()
    if action in ("add", "create", "schedule", "set"):
        return scheduler.add(p.get("task", ""), p.get("time", ""), p.get("repeat", "once"),
                             p.get("days", ""), p.get("in_minutes"))
    if action in ("list", "show"):
        return scheduler.list_jobs()
    if action in ("remove", "delete", "cancel"):
        return scheduler.remove(str(p.get("id", "")), str(p.get("task", "")))
    if action == "clear":
        return scheduler.clear()
    return "Unknown action. Use add, list, remove or clear."


TOOL = {
    "name": "scheduled_tasks",
    "description": (
        "Schedule something for YOU (the assistant) to do later — once, daily, on weekdays, "
        "weekly or every N minutes/hours — using all your tools when it fires: briefings, "
        "checks, messages, device control, reports. Also list or cancel scheduled tasks. "
        "Runs while the assistant is open. For a simple pop-up alarm use `reminder` instead."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "add | list | remove | clear"},
            "task": {"type": "STRING", "description": "What to do, as an instruction to yourself"},
            "time": {"type": "STRING", "description": "HH:MM (24h) or YYYY-MM-DD HH:MM"},
            "in_minutes": {"type": "NUMBER", "description": "Run once, this many minutes from now"},
            "repeat": {"type": "STRING",
                       "description": "once | daily | weekdays | weekends | weekly | hourly | "
                                      "every_N_minutes | every_N_hours (e.g. every_30_minutes)"},
            "days": {"type": "STRING", "description": "For weekly: mon,wed,fri"},
            "id": {"type": "STRING", "description": "Task id for remove"},
        },
        "required": ["action"],
    },
    "handler": scheduled_tasks,
}
