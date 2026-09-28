"""
Live vision — the assistant keeps its eyes open.

While "live vision" is on, the webcam is watched continuously, the way a person
in the room would notice things without being asked:

    every ~0.5 s   object detection (people, phones, cups, pets…) and face
                   recognition (who they are) — a few tens of milliseconds on
                   the CPU, see core/vision_detect.py and core/face_id.py
    on a change    a vision language model looks at the frame and writes one or
                   two sentences about what is happening ("Anish is at the desk
                   drinking coffee; a second person has come in behind him")
    always         a short summary of the current scene is put in front of the
                   brain with every request, and a live frame is attached when
                   the user asks something visual ("what am I holding?")

and, depending on the chosen level, it speaks up by itself:

    off      never — it still sees, answers and remembers
    low      greets people it knows when they arrive, mentions a stranger
    normal   also reacts to notable changes (someone joins, a pet appears,
             the user holds something up); the brain decides whether a remark
             is worth making and stays silent otherwise
    chatty   also makes an occasional remark about what it sees

Budget on a 4 GB GPU laptop: detection runs on 2 CPU threads at 2 frames a
second (~5 % CPU). Descriptions run at most once a minute, never while a reply
is being generated or spoken, and use the conversation model itself when it can
see (Gemma 4, Qwen-VL, Gemma 3…) so the GPU never has to swap models.

With Gemini Live the frames themselves are streamed to the realtime session
(see main.py `_stream_live_video`), which sees video natively.

Everything seen is written to the local journal ("seen" lines), which the
learning memory (core/knowledge.py) distils into long-term facts.
"""
from __future__ import annotations

import collections
import re
import threading
import time
from datetime import datetime
from typing import Callable

import numpy as np

from core import brain_config, runtime
from core.camera import hub

LEVELS = ("off", "low", "normal", "chatty")
_GAP = {"low": 120.0, "normal": 90.0, "chatty": 150.0}     # seconds between own remarks
_NOTABLE_HOLD = {"cell phone", "cup", "bottle", "wine glass", "book", "remote", "scissors",
                 "knife", "banana", "apple", "orange", "sandwich", "pizza", "donut", "cake",
                 "teddy bear", "umbrella", "backpack", "handbag", "suitcase", "sports ball",
                 "toothbrush", "hair drier", "laptop"}

# Requests about what is in front of the camera: attach the live frame.
_VISUAL = re.compile(
    r"\b(can you see|do you see|what do you see|you see|see me|look at me|looking at|"
    r"take a look|have a look|look at (this|that|it|my)|in front of (you|me|the camera)|"
    r"what am i (holding|wearing|doing)|am i holding|i'?m holding|in my hands?|"
    r"how do i look|what (colou?r|brand|kind|type) is|what is (this|that)|what's (this|that)|"
    r"is this|who is (this|that|here|with me|behind me|there)|who'?s (this|that|here|behind)|"
    r"how many (fingers|people)|the camera|webcam|show(ing)? you|read this|"
    r"dekh|dikh|dikhai|kya hai (ye|yeh|woh|wo)|(ye|yeh) kya|haath me|pehen|pehna|kaisa lag|"
    r"देख|दिख|हाथ में|ये क्या|यह क्या|पहन|कैमरा)",
    re.I)
_NOT_CAMERA = re.compile(r"\b(screen|monitor|window|desktop|tab|page|website|document|file|"
                         r"स्क्रीन)\b", re.I)


def wants_camera(text: str) -> bool:
    t = text or ""
    return bool(_VISUAL.search(t)) and not _NOT_CAMERA.search(t)


def _now_hm() -> str:
    return datetime.now().strftime("%H:%M")


def _ago(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 60:
        return f"{s} s ago"
    if s < 3600:
        return f"{s // 60} min ago"
    return f"{s // 3600} h ago"


def _same_gist(a: str, b: str) -> bool:
    wa = set(re.findall(r"\w{4,}", (a or "").lower()))
    wb = set(re.findall(r"\w{4,}", (b or "").lower()))
    if not wa or not wb:
        return False
    return len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.6


class Scene:
    """What is in view right now, smoothed over the last few seconds."""

    def __init__(self):
        self.updated = 0.0
        self.objects: dict[str, int] = {}          # label -> count (stable)
        self.people: list[str] = []                # names in view ("unknown" for strangers)
        self.faces: list[dict] = []
        self.dets: list[dict] = []
        self.brightness = 0.0
        self.motion = 0.0
        self.caption = ""
        self.caption_at = 0.0
        self.events: collections.deque = collections.deque(maxlen=12)   # (time, text)

    def summary(self, with_caption: bool = True) -> str:
        from core.vision_detect import BACKGROUND, summarize
        people_n = self.objects.get("person", 0)
        known = sorted({p for p in self.people if p != "unknown"})
        strangers = sum(1 for p in self.people if p == "unknown")
        parts = []
        if people_n or known:
            who = ", ".join(known)
            if strangers:
                who = (who + ", " if who else "") + (f"{strangers} unrecognised" if strangers > 1
                                                    else "someone unrecognised")
            n = max(people_n, len(self.people))
            parts.append(f"People: {n}" + (f" ({who})" if who else ""))
        else:
            parts.append("People: nobody in view")
        things = summarize([{"label": k} for k, n in self.objects.items() for _ in range(n)
                            if k != "person"], skip=BACKGROUND)
        if things:
            parts.append(f"Objects: {things}")
        if self.brightness and self.brightness < 35:
            parts.append("The room looks dark.")
        if with_caption and self.caption:
            parts.append(f"Scene ({_ago(time.monotonic() - self.caption_at)}): {self.caption}")
        return "\n".join(parts)


class Perception:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._log: Callable[[str], None] = print
        self.scene = Scene()
        self._frame = None
        self._frame_ts = 0.0
        self._lock = threading.Lock()
        self._window: collections.deque = collections.deque(maxlen=6)     # per-tick label counts
        self._face_window: collections.deque = collections.deque(maxlen=8)
        self._last_seen: dict[str, float] = {}      # name/label -> monotonic
        self._started_at = time.monotonic()
        self._announced: dict[str, float] = {}
        self._last_remark = 0.0
        self._caption_busy = False
        self._last_caption_try = 0.0
        self._prev_small = None
        self._changed = True
        self.on_frame: Callable[[bytes, str], None] | None = None          # HUD preview
        self.error = ""

    # ── lifecycle ────────────────────────────────────────────────────────────
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, log: Callable[[str], None] = print) -> None:
        self._log = log
        if self.running():
            if not self._stop.is_set():
                return
            self._thread.join(timeout=3)           # switched off a moment ago: let it finish
            if self.running():
                self._stop.clear()
                return
        self._stop.clear()
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="live-vision")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        runtime.set_state("scene", None)

    # ── what other parts of the app read ─────────────────────────────────────
    def latest_frame(self, max_age: float = 3.0):
        with self._lock:
            if self._frame is None or time.monotonic() - self._frame_ts > max_age:
                return None
            return self._frame

    def latest_jpeg(self, max_side: int = 768, quality: int = 80, max_age: float = 3.0) -> bytes | None:
        import cv2
        frame = self.latest_frame(max_age)
        if frame is None:
            return None
        h, w = frame.shape[:2]
        s = min(1.0, max_side / max(h, w))
        if s < 1.0:
            frame = cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    def context_block(self) -> str:
        """For the system prompt: what is in view, in a few lines."""
        if not self.running() or not self.scene.updated:
            return ""
        age = time.monotonic() - self.scene.updated
        if age > 30:
            return ""
        lines = [f"[WHAT YOU SEE — your webcam, live ({_ago(age)})]", self.scene.summary()]
        ev = [f"{t} {txt}" for t, txt in list(self.scene.events)[-4:]]
        if ev:
            lines.append("Recently: " + "; ".join(ev))
        lines.append("This is your own eyesight: talk about it in the first person. For a "
                     "detailed look, a live frame is attached to visual questions.")
        return "\n".join(lines)

    # ── the watch loop ───────────────────────────────────────────────────────
    def _loop(self) -> None:
        from core import vision_detect
        det = vision_detect.detector(self._log)
        faces = None
        try:
            from core import face_id
            faces = face_id.engine(self._log)
        except Exception as e:
            print(f"[Vision] face recognition unavailable: {e}")
        cam = hub()
        cam.acquire()
        self._log("SYS: 👁 Live vision on — I can see through the webcam.")
        tick = 0
        last_retry = 0.0
        try:
            if cam.wait_frame(timeout=8.0) is None:
                self.error = cam.error or "no camera image"
                self._log(f"ERR: Live vision — {self.error}. Check the webcam and Windows camera privacy.")
                return
            while not self._stop.is_set():
                senses = brain_config.get_senses()
                fps = max(0.5, min(5.0, float(senses.get("vision_fps", 2) or 2)))
                t0 = time.monotonic()
                frame = cam.latest(max_age=2.0)
                if frame is not None:
                    try:
                        self._process(frame, det, faces, tick, senses)
                    except Exception as e:
                        print(f"[Vision] {type(e).__name__}: {e}")
                    tick += 1
                elif not cam.active and time.monotonic() - last_retry > 10:
                    last_retry = time.monotonic()        # the camera dropped: reopen it
                    cam.acquire()
                    cam.release()
                self._stop.wait(max(0.05, 1.0 / fps - (time.monotonic() - t0)))
        finally:
            cam.release()
            self._log("SYS: 👁 Live vision off.")

    def _process(self, frame, det, faces, tick: int, senses: dict) -> None:
        import cv2
        h, w = frame.shape[:2]
        small = frame if w <= 800 else cv2.resize(frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_AREA)
        with self._lock:
            self._frame = frame
            self._frame_ts = time.monotonic()
        gray = cv2.cvtColor(cv2.resize(small, (64, 48), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        g = gray.astype(np.float32)
        motion = float(np.mean(np.abs(g - self._prev_small))) if self._prev_small is not None else 0.0
        self._prev_small = g
        dets = det.detect(small, min_conf=0.45) if det is not None else []
        scale = w / small.shape[1]
        for d in dets:
            x, y, bw, bh = d["box"]
            d["box"] = (int(x * scale), int(y * scale), int(bw * scale), int(bh * scale))
        seen_faces = []
        if faces is not None and (tick % 2 == 0 or any(d["label"] == "person" for d in dets)):
            try:
                # With nobody enrolled there is no one to recognise — and no
                # one to call a stranger either.
                seen_faces = faces.identify(small) if faces.people else []
                for f in seen_faces:
                    x, y, bw, bh = f["box"]
                    f["box"] = (int(x * scale), int(y * scale), int(bw * scale), int(bh * scale))
            except Exception as e:
                print(f"[Vision] faces: {e}")
        now = time.monotonic()
        counts: dict[str, int] = {}
        for d in dets:
            counts[d["label"]] = counts.get(d["label"], 0) + 1
        self._window.append(counts)
        self._face_window.append([f["name"] for f in seen_faces])

        # Smooth: a label is present at the median count over the window; a
        # name is present if seen in at least 2 of the last 8 looks.
        labels = set().union(*self._window) if self._window else set()
        stable = {}
        for lb in labels:
            med = int(np.median([c.get(lb, 0) for c in self._window]))
            if med > 0:
                stable[lb] = med
        name_hits: dict[str, int] = {}
        for names in self._face_window:
            for n in set(names):
                name_hits[n] = name_hits.get(n, 0) + 1
        people = sorted(n for n, k in name_hits.items() if k >= 2)
        unknown_n = max((names.count("unknown") for names in list(self._face_window)[-3:]), default=0)
        people = [p for p in people if p != "unknown"] + ["unknown"] * (unknown_n if "unknown" in people else 0)

        sc = self.scene
        prev_objects, prev_people = dict(sc.objects), list(sc.people)
        sc.objects, sc.people, sc.dets, sc.faces = stable, people, dets, seen_faces
        sc.brightness = float(gray.mean())
        sc.motion = motion
        sc.updated = now
        runtime.set_state("scene", {"objects": stable, "people": people})
        if stable != prev_objects or people != prev_people:
            self._changed = True
        self._events(prev_objects, prev_people, stable, people, now, senses, frame)

        if self.on_frame is not None and senses.get("vision_preview", True) and tick % 2 == 0:
            try:
                from core.vision_detect import draw
                view = draw(frame, dets, seen_faces)
                vh, vw = view.shape[:2]
                if vw > 480:
                    view = cv2.resize(view, (480, vh * 480 // vw), interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    self.on_frame(buf.tobytes(), sc.summary(with_caption=False).replace("\n", " · "))
            except Exception:
                pass

        self._maybe_caption(now, senses)

    # ── noticing things ──────────────────────────────────────────────────────
    def _events(self, prev_objects, prev_people, objects, people, now, senses, frame) -> None:
        from core import journal
        level = str(senses.get("vision_proactive", "low")).lower()
        owner = None
        try:
            from core import face_id
            owner = face_id.engine().owner()
        except Exception:
            pass
        notes = []

        for name in set(people) - set(prev_people):
            if name == "unknown":
                continue
            away = now - self._last_seen.get(name, -1e9)
            self._last_seen[name] = now
            if away > 300:
                notes.append(f"{name} arrived")
                journal.append("seen", f"{name} came into view", None, via="camera")
                presence_greets = False
                try:
                    from core import face_id
                    presence_greets = face_id.presence().running() and name == owner
                except Exception:
                    pass
                # Not in the first minute: whoever is at the desk when the app
                # starts has not "arrived", and the startup briefing greets them.
                if level != "off" and not presence_greets and now - self._started_at > 60:
                    who = f"{name} (the owner)" if name == owner else name
                    mins = int(away // 60) if away < 86400 else None
                    back = f" after about {mins} minutes away" if mins else ""
                    self._remark(f"[VISION_EVENT] {who} has just come into view of your camera{back}. "
                                 f"Greet them by name in one short, natural sentence.",
                                 key=f"arrive:{name}", cooldown=1800, force=True)
        for name in people:
            if name != "unknown":
                self._last_seen[name] = now

        strangers = people.count("unknown")
        if strangers and "unknown" not in prev_people:
            notes.append("an unrecognised person appeared")
            journal.append("seen", "An unrecognised person came into view", None, via="camera")
            if owner and level != "off" and owner not in people:
                self._remark("[VISION_EVENT] Someone you do not recognise is in front of the camera and "
                             "the owner is not in view. Politely ask who they are in one short sentence.",
                             key="stranger", cooldown=600, force=True)

        n_now, n_before = objects.get("person", 0), prev_objects.get("person", 0)
        if n_now == 0 and n_before > 0:
            notes.append("everyone left the view")
            journal.append("seen", "Nobody is in front of the camera any more", None, via="camera")
        elif n_now > n_before > 0:
            notes.append(f"{n_now} people in view now")
            if level in ("normal", "chatty"):
                self._remark(f"[VISION_EVENT] Another person has joined — {n_now} people are in view now. "
                             "Say something only if it is natural and useful; otherwise reply SILENT.",
                             key="count", cooldown=300)

        # Something new in view (not furniture), that was not there for the
        # last two minutes: worth a line in the journal, maybe a remark.
        from core.vision_detect import BACKGROUND
        new_things = [lb for lb in objects
                      if lb not in prev_objects and lb != "person" and lb not in BACKGROUND]
        for lb in new_things:
            if now - self._last_seen.get("obj:" + lb, -1e9) > 120:
                notes.append(f"a {lb} appeared")
                if level in ("normal", "chatty") and (lb in _NOTABLE_HOLD or lb in _animals()):
                    self._remark(f"[VISION_EVENT] A {lb} has just appeared in view. If the user seems to be "
                                 "showing it to you, or it is worth a friendly remark, say one short "
                                 "sentence about it; otherwise reply SILENT.",
                                 key="obj:" + lb, cooldown=600)
        for lb in objects:
            self._last_seen["obj:" + lb] = now

        for n in notes:
            self.scene.events.append((_now_hm(), n))
        if notes:
            self._changed = True

    def _remark(self, text: str, key: str, cooldown: float, force: bool = False) -> None:
        """Offer an event to the brain; it may speak (or stay SILENT)."""
        now = time.monotonic()
        if now - self._announced.get(key, -1e9) < cooldown:
            return
        level = str(brain_config.get_senses().get("vision_proactive", "low")).lower()
        if level == "off":
            return
        gap = _GAP.get(level, 120.0)
        if not force and now - self._last_remark < gap:
            return
        eng = runtime.engine()
        if eng is None or getattr(eng, "_busy", False) or getattr(eng, "_is_speaking", False):
            return
        if now - float(getattr(eng, "_last_user_speech", 0.0) or 0.0) < 8:
            return
        self._announced[key] = now
        self._last_remark = now
        img = self.latest_jpeg(max_side=640)
        submit = getattr(eng, "_submit_vision_event", None)
        if submit is not None:
            submit(text, img)
        elif "SILENT" not in text:
            runtime.inject(text)

    # ── describing the scene with a vision language model ────────────────────
    def _maybe_caption(self, now: float, senses: dict) -> None:
        if self._caption_busy or not senses.get("vision_captions", True):
            return
        interval = max(20.0, float(senses.get("vision_caption_seconds", 60) or 60))
        idle_refresh = interval * 5
        due = (self._changed and now - self.scene.caption_at > interval) or \
            (now - self.scene.caption_at > idle_refresh)
        if not due or now - self._last_caption_try < 15:
            return
        b = brain_config.get_brain()
        if b.get("provider") in ("", "gemini_live"):
            return            # Gemini Live watches the video itself
        eng = runtime.engine()
        if eng is not None and (getattr(eng, "_busy", False) or getattr(eng, "_is_speaking", False)):
            return
        self._last_caption_try = now
        self._caption_busy = True
        threading.Thread(target=self._caption, daemon=True, name="vision-caption").start()

    def _caption(self) -> None:
        from core import journal, llm
        try:
            img = self.latest_jpeg(max_side=640, quality=75)
            if img is None:
                return
            if not _can_see():
                return
            names = [f for f in self.scene.faces if f.get("name") and f["name"] != "unknown"]
            hint = ""
            if names:
                w = self.latest_frame().shape[1] if self.latest_frame() is not None else 1
                pos = []
                for f in names:
                    cx = (f["box"][0] + f["box"][2] / 2) / max(1, w)
                    side = "left" if cx < 0.4 else "right" if cx > 0.6 else "centre"
                    pos.append(f"{f['name']} ({side})")
                hint = "Face recognition says these people are visible: " + ", ".join(pos) + ". "
            prompt = (hint + "You are the eyes of a home assistant. In one or two short sentences, "
                      "describe what is happening in this webcam frame: who is there and what they are "
                      "doing, anything they hold or show to the camera, and anything unusual. Use the "
                      "names given. Describe only what is visible; no preamble.")
            text = llm.complete([prompt, llm.image_part(img, "image/jpeg")], role="vision",
                                max_tokens=120, timeout=90, background=True)
            text = " ".join((text or "").split())
            if not text:
                return
            sc = self.scene
            changed = not _same_gist(text, sc.caption)
            sc.caption, sc.caption_at = text, time.monotonic()
            self._changed = False
            if changed:
                journal.append("seen", text, None, via="camera")
                if str(brain_config.get_senses().get("vision_proactive", "low")).lower() == "chatty":
                    self._remark(f"[VISION_EVENT] What you see now: {text} If there is something genuinely "
                                 "worth saying to the user about it, say one short sentence; otherwise "
                                 "reply SILENT.", key="caption", cooldown=180)
        except Exception as e:
            print(f"[Vision] caption failed: {type(e).__name__}: {str(e)[:160]}")
        finally:
            self._caption_busy = False


def _animals() -> set[str]:
    from core.vision_detect import ANIMALS
    return ANIMALS


_see_cache = {"t": 0.0, "v": False, "k": None}


def _can_see() -> bool:
    """Is there a model that can look at pictures (the brain or a vision model)?"""
    from core import llm
    b = brain_config.get_brain()
    key = (b.get("provider"), b.get("model"), b.get("vision_model"))
    if _see_cache["k"] == key and time.monotonic() - _see_cache["t"] < 300:
        return _see_cache["v"]
    try:
        s = llm.settings_for("vision")
        v = bool(llm.capabilities(s).get("vision"))
    except Exception:
        v = False
    _see_cache.update(t=time.monotonic(), v=v, k=key)
    return v


_perception = Perception()


def perception() -> Perception:
    return _perception
