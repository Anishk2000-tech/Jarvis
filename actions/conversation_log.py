"""
conversation_log — recall what the microphone heard around the assistant.

In ambient mode everything said in the room is transcribed locally into
memory/journal/ (see core/journal.py), including talk that was not addressed to
the assistant. This tool searches that transcript so the assistant can answer
"what did my brother say about the trip?", "summarise the meeting we just had",
or "what was I saying before lunch?".
"""
from core import journal


def conversation_log(parameters: dict, player=None) -> str:
    p = parameters or {}
    try:
        limit = max(5, min(200, int(p.get("limit") or 60)))
    except (TypeError, ValueError):
        limit = 60
    return journal.search(str(p.get("query", "") or ""), str(p.get("period", "today") or "today"),
                          limit)


TOOL = {
    "name": "conversation_log",
    "description": (
        "Search the local transcript of everything the microphone heard — conversations in the "
        "room, not only requests to you. Use to answer what someone said, what was discussed, "
        "or to summarise a conversation or meeting. Leave query empty to get the transcript "
        "of the period."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Keyword(s) or a name to look for (optional)"},
            "period": {"type": "STRING",
                       "description": "last_10_minutes | last_hour | this_morning | today | "
                                      "yesterday | this_week | all (default today)"},
            "limit": {"type": "INTEGER", "description": "Max lines (default 60)"},
        },
        "required": [],
    },
    "handler": conversation_log,
}
