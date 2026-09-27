"""
A local transcript of what the assistant has heard and said.

In ambient mode the microphone transcribes the room, not only requests. Those
lines are kept here — one JSON line per utterance, one file per day, in
memory/journal/ on this machine and nowhere else — so the assistant can answer
"what did Rahul say about Friday?" or "summarise this morning's meeting".

Old days are deleted after the configured retention (30 days by default).
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

from core import brain_config

JOURNAL_DIR = brain_config.BASE_DIR / "memory" / "journal"
_lock = threading.Lock()


def _file(day: datetime) -> Path:
    return JOURNAL_DIR / f"{day:%Y-%m-%d}.jsonl"


def append(speaker: str, text: str, addressed: bool | None = None, **extra) -> None:
    text = (text or "").strip()
    if not text:
        return
    try:
        if not brain_config.get_senses().get("journal", True):
            return
    except Exception:
        pass
    now = datetime.now()
    rec = {"t": now.isoformat(timespec="seconds"), "speaker": speaker, "text": text}
    if addressed is not None:
        rec["addressed"] = bool(addressed)
    rec.update({k: v for k, v in extra.items() if v is not None})
    try:
        with _lock:
            JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
            with open(_file(now), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Journal] write failed: {e}")


def _period(period: str) -> tuple[datetime, datetime]:
    now = datetime.now()
    p = (period or "today").lower().strip()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    m = re.match(r"last_?(\d+)_?(minute|min|hour|day)s?", p)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = timedelta(minutes=n) if unit.startswith("min") else \
            timedelta(hours=n) if unit == "hour" else timedelta(days=n)
        return now - delta, now
    if p in ("last_hour", "hour"):
        return now - timedelta(hours=1), now
    if p == "yesterday":
        return start_of_day - timedelta(days=1), start_of_day
    if p in ("this_week", "week"):
        return start_of_day - timedelta(days=start_of_day.weekday()), now
    if p in ("all", "everything", "any"):
        return now - timedelta(days=3650), now
    if p in ("morning", "this_morning"):
        return start_of_day + timedelta(hours=5), start_of_day + timedelta(hours=12)
    return start_of_day, now


def read(start: datetime, end: datetime) -> list[dict]:
    out: list[dict] = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= end:
        f = _file(day)
        if f.exists():
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    try:
                        rec = json.loads(line)
                        t = datetime.fromisoformat(rec["t"])
                    except Exception:
                        continue
                    if start <= t <= end:
                        out.append(rec)
            except Exception:
                pass
        day += timedelta(days=1)
    return out


def _fmt(rec: dict) -> str:
    try:
        t = datetime.fromisoformat(rec["t"]).strftime("%a %H:%M")
    except Exception:
        t = rec.get("t", "")
    return f"[{t}] {rec.get('speaker', '?')}: {rec.get('text', '')}"


def search(query: str = "", period: str = "today", limit: int = 60) -> str:
    start, end = _period(period)
    recs = read(start, end)
    if not recs:
        return f"Nothing was heard in that period ({period})."
    q = [w for w in re.findall(r"\w+", (query or "").lower()) if len(w) > 2]
    if q:
        scored = []
        for i, r in enumerate(recs):
            low = r.get("text", "").lower()
            score = sum(1 for w in q if w in low)
            if score:
                scored.append((score, i))
        if not scored:
            return (f"No line mentioning '{query}' in that period. "
                    f"{len(recs)} lines were heard; ask without a keyword for the whole transcript.")
        # Keep each hit with a little context either side, in time order.
        keep: set[int] = set()
        for _, i in sorted(scored, reverse=True)[: max(1, limit // 3)]:
            keep.update(range(max(0, i - 2), min(len(recs), i + 3)))
        chosen = [recs[i] for i in sorted(keep)]
    else:
        chosen = recs[-limit:]
    body = "\n".join(_fmt(r) for r in chosen[-limit:])
    return f"{len(chosen)} of {len(recs)} lines heard ({period}):\n{body}"


def prune(days: int | None = None) -> None:
    try:
        days = int(days or brain_config.get_senses().get("journal_days", 30))
    except Exception:
        days = 30
    cutoff = datetime.now() - timedelta(days=max(1, days))
    try:
        for f in JOURNAL_DIR.glob("*.jsonl"):
            try:
                if datetime.strptime(f.stem, "%Y-%m-%d") < cutoff:
                    f.unlink()
            except Exception:
                continue
    except Exception:
        pass
