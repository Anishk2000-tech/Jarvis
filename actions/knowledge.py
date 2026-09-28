"""
knowledge — what the assistant has learned on its own (core/knowledge.py).

"What have you learned about me?", "what do you know about Priya?", "forget
that I like jazz", "learn from today now", "remember that the gate code is at
the back of the fridge" (teach).
"""
from core import knowledge


def _fmt(facts: list[dict]) -> str:
    if not facts:
        return "Nothing learned about that yet."
    lines = []
    for f in facts:
        n = int(f.get("count", 1))
        lines.append(f"- {f['text']} [{f.get('kind', 'fact')}, from {f.get('source', '?')}, "
                     f"{'confirmed ' + str(n) + '×, ' if n > 1 else ''}last {f.get('last', '')[:10]}]")
    return "\n".join(lines)


def knowledge_tool(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action", "search")).lower().strip()
    query = str(p.get("query", "") or p.get("fact", "")).strip()
    st = knowledge.store()
    if action in ("search", "about", "recall", "lookup"):
        if not query:
            return _fmt(st.recent(12))
        return _fmt(st.search(query, k=12, min_score=0.2))
    if action == "recent":
        return _fmt(st.recent(int(p.get("count") or 12)))
    if action in ("teach", "add", "remember"):
        if not query:
            return "Say what to remember."
        fid = st.add(query, str(p.get("kind", "fact")), "user", str(p.get("about", "")), conf=0.95)
        st.save()
        return "Learned." if fid else "That was too short to keep."
    if action in ("forget", "delete"):
        if not query:
            return "Say what to forget."
        gone = st.forget(query)
        return ("Forgot:\n" + "\n".join(f"- {g}" for g in gone)) if gone else "I had nothing matching that."
    if action in ("learn_now", "consolidate", "reflect"):
        res = knowledge.consolidate()
        if res.get("skipped"):
            return f"Not now: {res['skipped']}."
        return (f"Went through {res.get('observations', 0)} new observations: {res.get('added', 0)} new facts, "
                f"{res.get('updated', 0)} corrected, {res.get('deleted', 0)} dropped.")
    if action == "stats":
        facts = list(st.facts.values()) if st._loaded else (st.load() or list(st.facts.values()))
        kinds: dict[str, int] = {}
        for f in facts:
            kinds[f.get("kind", "fact")] = kinds.get(f.get("kind", "fact"), 0) + 1
        detail = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]))
        return f"{len(facts)} learned facts" + (f": {detail}." if detail else ".")
    return "Unknown action. Use search, recent, teach, forget, learn_now or stats."


TOOL = {
    "name": "knowledge",
    "description": (
        "Your self-learned long-term knowledge: facts you worked out yourself from what you saw on "
        "camera, heard in the room, noticed on the screen and learned from your own actions. "
        "search/about a person or topic, recent, teach a fact, forget something, learn_now to "
        "digest today's observations, stats."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "search | recent | teach | forget | learn_now | stats"},
            "query": {"type": "STRING", "description": "Topic, person, or the fact to teach/forget"},
            "kind": {"type": "STRING", "description": "For teach: person|preference|routine|place|object|device|lesson|plan|fact"},
        },
        "required": ["action"],
    },
    "handler": knowledge_tool,
}
