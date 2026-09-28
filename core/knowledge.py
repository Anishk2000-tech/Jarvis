"""
Learning — what the assistant works out on its own and keeps, on this PC.

Everything the assistant perceives already lands in the local journal
(core/journal.py): what it hears (conversation and, in ambient mode, the room),
what its camera sees (live vision and CCTV descriptions), which windows are in
use (ScreenActivity below), and how its own actions went (tool results). That
journal is raw and grows every minute.

This module turns it into knowledge. Every few minutes, only while nobody is
talking to the assistant, the new journal lines are handed to the brain with
the facts it already holds about the same things, and it answers with what to
add, correct or drop:

    "Anish's sister is called Priya and visits on Sundays"           person
    "Anish starts work in VS Code around 9:30 on weekdays"           routine
    "The living-room lamp is 'Lamp 2' in Smart Life"                 device
    "open_app cannot start WhatsApp; use the web version instead"   lesson

Facts live in memory/knowledge.jsonl (one JSON object per line, readable and
editable), each with how often it was confirmed and when it was last seen.
Before every reply the facts relevant to the request are looked up — a BM25
keyword ranking, optionally blended with embeddings from a local Ollama model —
and the best few are put in front of the brain under [THINGS YOU HAVE LEARNED].

Nothing leaves the machine unless the brain itself is a cloud API.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from core import brain_config, journal

KNOW_FILE = brain_config.BASE_DIR / "memory" / "knowledge.jsonl"
STATE_FILE = brain_config.BASE_DIR / "memory" / "knowledge_state.json"
EMB_FILE = brain_config.BASE_DIR / "memory" / "knowledge_emb.npz"
KINDS = ("person", "preference", "routine", "place", "object", "device", "lesson", "plan", "fact",
         "event")
_SOURCES_BY_SPEAKER = {"room": "room", "seen": "camera", "cctv": "camera", "screen": "screen",
                       "tool": "tools"}

_STOP = set("""a an the of in on at to for from by with and or but is are was were be been being do does
did what who whom whose which when where why how this that these those it its i me my you your he she
they them his her their we our us as about into over than then so if not no yes can could will would
should may might must there here also just only very more most much many some any all has have had
user owner assistant jarvis""".split())


def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[\wऀ-ॿ]+", (text or "").lower())
            if (len(w) > 2 or not w.isascii()) and w not in _STOP]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class KnowledgeStore:
    def __init__(self, path: Path = KNOW_FILE):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.facts: dict[str, dict] = {}
        self._terms: dict[str, list[str]] = {}
        self._emb: dict[str, list[float]] = {}
        self._loaded = False

    # ── storage ──────────────────────────────────────────────────────────────
    def load(self) -> None:
        with self._lock:
            self.facts.clear()
            self._terms.clear()
            try:
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    try:
                        f = json.loads(line)
                    except Exception:
                        continue
                    if f.get("id") and f.get("text"):
                        self.facts[f["id"]] = f
                        self._terms[f["id"]] = _terms(f["text"] + " " + f.get("about", ""))
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"[Knowledge] load failed: {e}")
            try:
                import numpy as np
                if EMB_FILE.exists() and self.path == KNOW_FILE:
                    d = np.load(EMB_FILE, allow_pickle=False)
                    self._emb = {i: v.tolist() for i, v in zip(d["ids"].tolist(), d["vecs"])
                                 if i in self.facts}
            except Exception:
                self._emb = {}
            self._loaded = True

    def _ensure(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for fact in sorted(self.facts.values(), key=lambda x: x.get("first", "")):
                    f.write(json.dumps(fact, ensure_ascii=False) + "\n")
            tmp.replace(self.path)
            if self._emb and self.path == KNOW_FILE:
                try:
                    import numpy as np
                    ids = [i for i in self._emb if i in self.facts]
                    if ids:
                        np.savez(EMB_FILE, ids=np.array(ids), vecs=np.array([self._emb[i] for i in ids],
                                                                          dtype=np.float32))
                except Exception as e:
                    print(f"[Knowledge] embeddings not saved: {e}")

    # ── editing ──────────────────────────────────────────────────────────────
    def _similar(self, text: str) -> str | None:
        t = set(_terms(text))
        if not t:
            return None
        best, best_s = None, 0.0
        for fid, ts in self._terms.items():
            s2 = set(ts)
            if not s2:
                continue
            j = len(t & s2) / len(t | s2)
            if j > best_s:
                best, best_s = fid, j
        return best if best_s >= 0.6 else None

    def add(self, text: str, kind: str = "fact", source: str = "conversation", about: str = "",
            conf: float = 0.7) -> str:
        text = " ".join(str(text or "").split()).strip().rstrip(".") + "."
        if len(text) < 6:
            return ""
        kind = kind if kind in KINDS else "fact"
        with self._lock:
            self._ensure()
            fid = self._similar(text)
            now = _now()
            if fid:
                f = self.facts[fid]
                f["count"] = int(f.get("count", 1)) + 1
                f["last"] = now
                f["conf"] = round(min(1.0, float(f.get("conf", 0.7)) + 0.05), 2)
                if len(text) > len(f["text"]) * 1.2:
                    f["text"] = text
                    self._terms[fid] = _terms(text + " " + f.get("about", ""))
                    self._emb.pop(fid, None)
                return fid
            fid = "k_" + uuid.uuid4().hex[:8]
            self.facts[fid] = {"id": fid, "text": text, "kind": kind, "about": str(about or "")[:60],
                               "source": source, "first": now, "last": now, "count": 1,
                               "conf": round(float(conf), 2)}
            self._terms[fid] = _terms(text + " " + str(about or ""))
            self._trim()
            return fid

    def update(self, fid: str, text: str) -> bool:
        with self._lock:
            self._ensure()
            f = self.facts.get(fid)
            if not f or not text:
                return False
            f["text"] = " ".join(str(text).split()).strip().rstrip(".") + "."
            f["last"] = _now()
            self._terms[fid] = _terms(f["text"] + " " + f.get("about", ""))
            self._emb.pop(fid, None)
            return True

    def delete(self, fid: str) -> bool:
        with self._lock:
            self._ensure()
            self._terms.pop(fid, None)
            self._emb.pop(fid, None)
            return self.facts.pop(fid, None) is not None

    def forget(self, query: str) -> list[str]:
        """Remove the facts matching a description; returns their texts."""
        hits = self.search(query, k=5, min_score=1.0)
        gone = []
        for f in hits:
            if self.delete(f["id"]):
                gone.append(f["text"])
        if gone:
            self.save()
        return gone

    def clear(self) -> int:
        with self._lock:
            self._ensure()
            n = len(self.facts)
            self.facts.clear()
            self._terms.clear()
            self._emb.clear()
            self.save()
            try:
                EMB_FILE.unlink()
            except Exception:
                pass
            return n

    def _trim(self) -> None:
        cap = brain_config.get_learning_cfg().get("max_facts", 4000)
        if len(self.facts) <= cap:
            return
        # Forget what was seen once, long ago, first.
        ranked = sorted(self.facts.values(), key=lambda f: (int(f.get("count", 1)), f.get("last", "")))
        for f in ranked[: len(self.facts) - cap]:
            self.delete(f["id"])

    # ── recall ───────────────────────────────────────────────────────────────
    def search(self, query: str, k: int = 8, min_score: float = 0.3, kinds: set | None = None) -> list[dict]:
        with self._lock:
            self._ensure()
            q = list(dict.fromkeys(_terms(query)))
            if not q or not self.facts:
                return []
            n = len(self.facts)
            df = {t: sum(1 for ts in self._terms.values() if t in ts) for t in q}
            avg = sum(len(ts) for ts in self._terms.values()) / n or 1.0
            scores: dict[str, float] = {}
            for fid, ts in self._terms.items():
                if kinds and self.facts[fid].get("kind") not in kinds:
                    continue
                s = 0.0
                for t in q:
                    tf = ts.count(t)
                    if tf:
                        idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                        s += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(ts) / avg))
                if s > 0:
                    f = self.facts[fid]
                    s *= 1.0 + 0.1 * math.log(1 + int(f.get("count", 1)))
                    scores[fid] = s
            vec_scores = self._vector_scores(query) if self._emb else {}
            for fid, v in vec_scores.items():
                if v > 0.55:
                    scores[fid] = scores.get(fid, 0.0) + (v - 0.55) * 12
            ranked = sorted(scores.items(), key=lambda kv: -kv[1])
            return [dict(self.facts[fid], score=round(s, 2)) for fid, s in ranked[:k] if s >= min_score]

    def _vector_scores(self, query: str) -> dict[str, float]:
        vec = embed([query])
        if not vec:
            return {}
        import numpy as np
        qv = np.asarray(vec[0], dtype=np.float32)
        qv /= (np.linalg.norm(qv) + 1e-9)
        out = {}
        for fid, v in self._emb.items():
            a = np.asarray(v, dtype=np.float32)
            out[fid] = float(a @ qv / (np.linalg.norm(a) + 1e-9))
        return out

    def core_facts(self, k: int = 5) -> list[dict]:
        """The most confirmed facts about the owner — always worth knowing."""
        with self._lock:
            self._ensure()
            owner_words = {"user", "owner", (brain_config.user_name() or "").lower()} - {""}
            cands = [f for f in self.facts.values()
                     if f.get("kind") in ("person", "preference", "routine", "plan")
                     and (str(f.get("about", "")).lower() in owner_words or int(f.get("count", 1)) >= 3)]
            cands.sort(key=lambda f: (int(f.get("count", 1)), f.get("last", "")), reverse=True)
            return cands[:k]

    def recent(self, n: int = 10) -> list[dict]:
        with self._lock:
            self._ensure()
            return sorted(self.facts.values(), key=lambda f: f.get("last", ""), reverse=True)[:n]

    def index_embeddings(self, batch: int = 32) -> int:
        """Embed facts that have no vector yet (only with an embedding model)."""
        with self._lock:
            self._ensure()
            todo = [fid for fid in self.facts if fid not in self._emb][:batch]
            texts = [self.facts[fid]["text"] for fid in todo]
        if not todo:
            return 0
        vecs = embed(texts)
        if not vecs or len(vecs) != len(todo):
            return 0
        with self._lock:
            for fid, v in zip(todo, vecs):
                if fid in self.facts:
                    self._emb[fid] = list(map(float, v))
        return len(todo)


def embed(texts: list[str]) -> list[list[float]] | None:
    """Vectors from the configured Ollama embedding model (on the CPU, so the
    chat model keeps the GPU). None when no model is set or it fails."""
    model = str(brain_config.get_learning_cfg().get("embed_model") or "").strip()
    b = brain_config.get_brain()
    if not model or b.get("provider") != "ollama":
        return None
    try:
        import requests
        from core import llm
        s = llm.settings_for("chat")
        r = requests.post(f"{llm._ollama_base(s)}/api/embed", timeout=30,
                          json={"model": model, "input": texts, "keep_alive": "10m",
                                "options": {"num_gpu": 0}})
        if r.status_code != 200:
            return None
        return r.json().get("embeddings") or None
    except Exception:
        return None


_store = KnowledgeStore()


def store() -> KnowledgeStore:
    return _store


def context_block(query: str, k: int = 6) -> str:
    """[THINGS YOU HAVE LEARNED] for the system prompt, or ''."""
    try:
        if not brain_config.get_learning_cfg().get("enabled", True):
            return ""
        st = store()
        hits = st.search(query, k=k) if query else []
        seen = {f["id"] for f in hits}
        core = [f for f in st.core_facts(4) if f["id"] not in seen]
        facts = hits + core
        if not facts:
            return ""
        lines = ["[THINGS YOU HAVE LEARNED — from what you saw, heard and did]"]
        for f in facts[: k + 4]:
            n = int(f.get("count", 1))
            when = f.get("last", "")[:10]
            lines.append(f"- {f['text']}" + (f" (confirmed {n}×, last {when})" if n > 1 else f" ({when})"))
        return "\n".join(lines)
    except Exception as e:
        print(f"[Knowledge] context failed: {e}")
        return ""


# ── learning from the journal ────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except Exception:
        pass


def _allowed(rec: dict, cfg: dict) -> bool:
    sp = rec.get("speaker", "")
    src = _SOURCES_BY_SPEAKER.get(sp)
    if src == "room":
        return bool(cfg.get("from_room", True))
    if src == "camera":
        return bool(cfg.get("from_camera", True))
    if src == "screen":
        return bool(cfg.get("from_screen", True))
    if src == "tools":
        return bool(cfg.get("from_tools", True))
    return True


def pending_observations(limit_chars: int = 5000, max_lines: int = 90) -> tuple[list[dict], str]:
    """Journal lines not yet learned from, oldest first, and the last timestamp."""
    state = _load_state()
    cfg = brain_config.get_learning_cfg()
    last = state.get("last_t")
    try:
        start = datetime.fromisoformat(last) if last else datetime.now() - timedelta(days=2)
    except Exception:
        start = datetime.now() - timedelta(days=2)
    recs = [r for r in journal.read(start, datetime.now()) if r.get("t", "") > (last or "")]
    out, size = [], 0
    for r in recs:
        if not _allowed(r, cfg):
            continue
        line = r.get("text", "")
        size += len(line) + 30
        if out and (size > limit_chars or len(out) >= max_lines):
            break
        out.append(r)
    upto = out[-1]["t"] if out else (recs[-1]["t"] if recs else (last or ""))
    return out, upto


_PROMPT = """You maintain the long-term memory of {name}, a personal assistant living on {owner}'s computer.
From the NEW OBSERVATIONS below, extract knowledge worth remembering for weeks:
- facts about {owner} and the people around them: names, relationships, jobs, preferences, habits, routines, plans and dates
- places and objects in the home, devices and how they are named or operated
- lessons about the assistant's own actions: what worked, what failed and why, and what to do instead
Ignore small talk, momentary states ("someone is sitting", "a cup is on the desk"), guesses, and anything the KNOWN FACTS already say.
If an observation corrects or contradicts a known fact, update it; if a known fact is clearly wrong now, delete it.
Write each fact as one short, self-contained sentence using names, not pronouns.
Reply with ONLY this JSON (empty lists are fine):
{{"add": [{{"fact": "...", "kind": "person|preference|routine|place|object|device|lesson|plan|fact|event", "about": "who or what"}}],
 "update": [{{"id": "k_...", "fact": "..."}}],
 "delete": ["k_..."]}}"""


def _fmt_obs(r: dict) -> str:
    try:
        t = datetime.fromisoformat(r["t"]).strftime("%a %d %b %H:%M")
    except Exception:
        t = r.get("t", "")
    sp = r.get("speaker", "?")
    label = {"seen": "camera", "cctv": "cctv", "screen": "screen", "tool": "action", "room": "overheard"}.get(sp, sp)
    return f"[{t}] {label}: {r.get('text', '')}"


def consolidate(cancel: threading.Event | None = None, max_rounds: int = 3) -> dict:
    """Learn from new journal lines. Returns counts. Safe to call any time."""
    from core import llm
    cfg = brain_config.get_learning_cfg()
    if not cfg.get("enabled", True):
        return {"skipped": "learning is off"}
    b = brain_config.get_brain()
    if not b.get("provider"):
        return {"skipped": "no brain configured"}
    st = store()
    totals = {"added": 0, "updated": 0, "deleted": 0, "observations": 0}
    owner = brain_config.user_name() or "the user"
    name = brain_config.assistant_name()
    for _ in range(max_rounds):
        if cancel is not None and cancel.is_set():
            break
        obs, upto = pending_observations()
        if not obs:
            if upto:
                state = _load_state()
                state["last_t"] = upto
                _save_state(state)
            break
        digest = "\n".join(_fmt_obs(r) for r in obs)
        related = st.search(digest, k=14, min_score=0.5)
        known = "\n".join(f"[{f['id']}] {f['text']}" for f in related) or "(none yet)"
        system = _PROMPT.format(name=name, owner=owner)
        user = f"KNOWN FACTS:\n{known}\n\nNEW OBSERVATIONS:\n{digest}"
        try:
            s = llm.settings_for("chat")
            s.timeout = 240
            msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            ev = llm.chat(msgs, None, s=s, cancel=cancel, max_tokens=700)
            if ev.cancelled or (cancel is not None and cancel.is_set()):
                break
            data = llm._loads_loose(_json_part(llm.strip_thinking(ev.text))) or {}
        except Exception as e:
            print(f"[Knowledge] consolidation failed: {type(e).__name__}: {str(e)[:160]}")
            break
        if not isinstance(data, dict):
            data = {}
        srcs = {_SOURCES_BY_SPEAKER.get(r.get("speaker", ""), "conversation") for r in obs}
        source = srcs.pop() if len(srcs) == 1 else "mixed"
        for item in data.get("add") or []:
            if isinstance(item, dict) and item.get("fact"):
                if st.add(item["fact"], str(item.get("kind", "fact")).lower(), source, str(item.get("about", ""))):
                    totals["added"] += 1
            elif isinstance(item, str):
                if st.add(item, "fact", source):
                    totals["added"] += 1
        for item in data.get("update") or []:
            if isinstance(item, dict) and st.update(str(item.get("id", "")), str(item.get("fact", ""))):
                totals["updated"] += 1
        for fid in data.get("delete") or []:
            if isinstance(fid, str) and st.delete(fid):
                totals["deleted"] += 1
        totals["observations"] += len(obs)
        state = _load_state()
        state["last_t"] = upto
        state["last_run"] = _now()
        state["runs"] = int(state.get("runs", 0)) + 1
        _save_state(state)
        st.save()
    try:
        if st.index_embeddings():
            st.save()
    except Exception:
        pass
    return totals


def _json_part(text: str) -> str:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return m.group(1)
    i, j = text.find("{"), text.rfind("}")
    return text[i:j + 1] if i >= 0 and j > i else text


class Learner:
    """Background: distil the journal into knowledge while the user is not talking."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._log = print
        self.last_result: dict = {}

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, log=print) -> None:
        self._log = log
        if self.running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="learner")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._cancel.set()

    def _idle(self) -> bool:
        from core import runtime
        e = runtime.engine()
        if e is None:
            return True
        if getattr(e, "_busy", False) or getattr(e, "_is_speaking", False):
            return False
        return time.monotonic() - float(getattr(e, "_last_user_speech", 0.0) or 0.0) > 45

    def _loop(self) -> None:
        self._stop.wait(90)             # let the app settle first
        while not self._stop.is_set():
            cfg = brain_config.get_learning_cfg()
            period = cfg["consolidate_minutes"] * 60
            if cfg.get("enabled", True) and self._idle():
                self._cancel.clear()
                watcher = threading.Thread(target=self._watch_busy, daemon=True)
                watcher.start()
                try:
                    res = consolidate(cancel=self._cancel)
                    self.last_result = res
                    if res.get("added") or res.get("updated") or res.get("deleted"):
                        print(f"[Knowledge] learned: {res}")
                except Exception as e:
                    print(f"[Knowledge] {e}")
                finally:
                    self._cancel.set()
            self._stop.wait(period)

    def _watch_busy(self) -> None:
        # The user started talking: abandon the round, the reply comes first.
        while not self._cancel.is_set():
            if not self._idle():
                self._cancel.set()
                return
            time.sleep(0.5)


_learner = Learner()


def learner() -> Learner:
    return _learner


# ── noticing what is on screen ───────────────────────────────────────────────

_PRIVATE = re.compile(r"inprivate|incognito|private brows|password|keepass|bitwarden|1password|"
                      r"lastpass|bank|netbanking|otp", re.I)


class ScreenActivity:
    """Notes the active app and window title (never the screen's contents)."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last = ("", "")
        self._since = 0.0

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="screen-activity")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def foreground() -> tuple[str, str]:
        try:
            import win32gui
            import win32process
            import psutil
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd) or ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            app = psutil.Process(pid).name().rsplit(".", 1)[0] if pid else ""
            return app, title
        except Exception:
            return "", ""

    def _loop(self) -> None:
        while not self._stop.is_set():
            cfg = brain_config.get_learning_cfg()
            if cfg.get("enabled", True) and cfg.get("from_screen", True):
                app, title = self.foreground()
                if app and (app, title) != self._last and app.lower() not in ("jarvis", "python", "pythonw"):
                    now = time.monotonic()
                    prev_app, prev_title = self._last
                    if self._since and prev_app:
                        mins = int((now - self._since) // 60)
                        if mins >= 2:
                            journal.append("screen", f"Used {prev_app} for about {mins} min"
                                           + (f" ('{prev_title[:80]}')" if not _PRIVATE.search(prev_title) else ""),
                                           None)
                    self._last, self._since = (app, title), now
                    if not _PRIVATE.search(title):
                        journal.append("screen", f"Switched to {app}: {title[:100]}", None)
            self._stop.wait(cfg.get("screen_seconds", 60))


_screen = ScreenActivity()


def screen_activity() -> ScreenActivity:
    return _screen


def note_tool_result(name: str, args: dict, result: str) -> None:
    """Journal how an action went, for the lessons the learner draws."""
    try:
        if not brain_config.get_learning_cfg().get("from_tools", True):
            return
        if name in ("save_memory", "recall_memory", "knowledge", "conversation_log", "system_status"):
            return
        low = (result or "").lower()
        failed = any(w in low for w in ("failed", "error", "could not", "couldn't", "not found", "unable",
                                        "no such", "denied", "timed out", "unknown action"))
        short_args = json.dumps({k: (str(v)[:60]) for k, v in (args or {}).items()}, ensure_ascii=False)[:200]
        verdict = "FAILED" if failed else "ok"
        journal.append("tool", f"{name}({short_args}) → {verdict}: {' '.join(str(result).split())[:220]}", None)
    except Exception:
        pass
