"""
Scheduled assistant tasks — "every weekday at 8:30, give me the news and my
reminders", "in 20 minutes check whether the download finished".

Unlike actions/reminder.py (an OS notification that fires even when the app is
closed), a scheduled task is carried out BY THE ASSISTANT: at the due time the
task is handed to it as an instruction and it uses its tools like it would for
a spoken request. It therefore runs only while JARVIS is running; a task that
was missed by more than an hour is skipped rather than fired late.

Jobs live in memory/schedule.json.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta

from core import brain_config

SCHEDULE_FILE = brain_config.BASE_DIR / "memory" / "schedule.json"
_lock = threading.Lock()
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_LATE_LIMIT = timedelta(minutes=60)


def _load() -> list[dict]:
    try:
        data = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(jobs: list[dict]) -> None:
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SCHEDULE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SCHEDULE_FILE)


def _parse_time(text: str, now: datetime) -> datetime | None:
    t = (text or "").strip().lower().replace(".", ":")
    if not t:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M",
                "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            pass
    ampm = None
    if t.endswith("am") or t.endswith("pm"):
        ampm, t = t[-2:], t[:-2].strip()
    try:
        if ":" in t:
            h, m = [int(x) for x in t.split(":")[:2]]
        else:
            h, m = int(t), 0
    except ValueError:
        return None
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def _next_run(job: dict, after: datetime) -> datetime | None:
    rep = job.get("repeat", "once")
    base = datetime.fromisoformat(job["anchor"])
    if rep == "once":
        return None
    if rep.startswith("every_"):
        try:
            mins = max(1, int(rep.split("_")[1]))
        except Exception:
            mins = 60
        if job.get("repeat", "").endswith("hours"):
            mins *= 60
        n = base
        step = timedelta(minutes=mins)
        if n <= after:
            k = int((after - n) / step) + 1
            n = n + k * step
        return n
    if rep == "hourly":
        n = after.replace(minute=base.minute, second=0, microsecond=0)
        return n if n > after else n + timedelta(hours=1)
    cand = after.replace(hour=base.hour, minute=base.minute, second=0, microsecond=0)
    if cand <= after:
        cand += timedelta(days=1)
    days = job.get("days") or []
    for _ in range(8):
        wd = _DAYS[cand.weekday()]
        if rep == "daily" or (rep == "weekdays" and cand.weekday() < 5) \
                or (rep == "weekends" and cand.weekday() >= 5) \
                or (rep == "weekly" and (wd in days if days else cand.weekday() == base.weekday())):
            return cand
        cand += timedelta(days=1)
    return cand


def add(task: str, time: str = "", repeat: str = "once", days: str = "", in_minutes=None) -> str:
    task = (task or "").strip()
    if not task:
        return "What should I do at that time? No task was given."
    now = datetime.now()
    repeat = (repeat or "once").strip().lower().replace(" ", "_")
    if repeat in ("every_day", "everyday"):
        repeat = "daily"
    m = None
    if repeat.startswith("every_"):
        m = repeat
    when: datetime | None = None
    if in_minutes not in (None, "", 0, "0"):
        try:
            when = now + timedelta(minutes=float(in_minutes))
        except (TypeError, ValueError):
            return "in_minutes must be a number."
    elif time:
        when = _parse_time(time, now)
        if when is None:
            return f"I could not read the time '{time}'. Use HH:MM or YYYY-MM-DD HH:MM."
        if when <= now and repeat == "once" and len(time.strip()) <= 7:
            when += timedelta(days=1)
    elif m:
        when = now
    else:
        return "When should it run? Give a time (HH:MM) or in_minutes."
    day_list = [d.strip()[:3].lower() for d in (days or "").replace(";", ",").split(",") if d.strip()]
    job = {"id": uuid.uuid4().hex[:6], "task": task, "repeat": repeat, "days": day_list,
           "anchor": when.isoformat(timespec="minutes"), "created": now.isoformat(timespec="seconds"),
           "enabled": True}
    if m:
        job["next"] = (_next_run(job, now) or when).isoformat(timespec="minutes")
    elif repeat == "once" or when > now:
        job["next"] = when.isoformat(timespec="minutes")
    else:
        job["next"] = (_next_run(job, now) or when).isoformat(timespec="minutes")
    with _lock:
        jobs = _load()
        jobs.append(job)
        _save(jobs)
    nxt = datetime.fromisoformat(job["next"])
    rep_txt = "" if repeat == "once" else f", repeating {repeat.replace('_', ' ')}"
    if day_list:
        rep_txt += f" on {', '.join(day_list)}"
    return (f"Scheduled (id {job['id']}): \"{task}\" at {nxt:%a %d %b %H:%M}{rep_txt}. "
            f"It runs while JARVIS is open.")


def list_jobs() -> str:
    jobs = [j for j in _load() if j.get("enabled", True)]
    if not jobs:
        return "No scheduled tasks."
    lines = []
    for j in sorted(jobs, key=lambda x: x.get("next", "")):
        try:
            nxt = datetime.fromisoformat(j["next"]).strftime("%a %d %b %H:%M")
        except Exception:
            nxt = j.get("next", "?")
        rep = "" if j.get("repeat") == "once" else f" ({j['repeat']})"
        lines.append(f"- {j['id']}: {j['task']} — next {nxt}{rep}")
    return "Scheduled tasks:\n" + "\n".join(lines)


def remove(job_id: str = "", task_hint: str = "") -> str:
    with _lock:
        jobs = _load()
        keep, gone = [], []
        hint = (task_hint or "").lower().strip()
        for j in jobs:
            if (job_id and j.get("id") == job_id) or (hint and hint in j.get("task", "").lower()):
                gone.append(j)
            else:
                keep.append(j)
        if not gone:
            return "No matching scheduled task."
        _save(keep)
    return "Removed: " + "; ".join(j["task"] for j in gone)


def clear() -> str:
    with _lock:
        n = len(_load())
        _save([])
    return f"Cleared {n} scheduled task(s)."


def due_jobs(now: datetime | None = None) -> list[dict]:
    """Jobs to run now. Advances or removes them, so each fires once."""
    now = now or datetime.now()
    fire: list[dict] = []
    with _lock:
        jobs = _load()
        changed = False
        keep = []
        for j in jobs:
            if not j.get("enabled", True):
                keep.append(j)
                continue
            try:
                nxt = datetime.fromisoformat(j["next"])
            except Exception:
                changed = True
                continue
            if nxt > now:
                keep.append(j)
                continue
            changed = True
            if now - nxt <= _LATE_LIMIT:
                fire.append(dict(j))
            following = _next_run(j, now)
            if following is not None:
                j["next"] = following.isoformat(timespec="minutes")
                keep.append(j)
        if changed:
            _save(keep)
    return fire
