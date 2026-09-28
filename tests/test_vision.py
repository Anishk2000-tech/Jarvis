"""Object detection on a real photo, and the live-vision watcher's logic."""
import os
import threading
import time

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO = os.path.join(ROOT, "tests", "data", "people.jpg")


def _detector():
    from core import vision_detect
    try:
        return vision_detect.Detector(log=lambda m: None)
    except Exception as e:           # no model and no network
        pytest.skip(f"detector model unavailable: {e}")


def test_detects_people_in_photo():
    import cv2
    det = _detector()
    img = cv2.imread(PHOTO)
    found = det.detect(img, min_conf=0.4)
    people = [d for d in found if d["label"] == "person"]
    assert len(people) >= 2, found
    for d in people:
        x, y, w, h = d["box"]
        assert 0 <= x < img.shape[1] and 0 <= y < img.shape[0] and w > 40 and h > 100
    t0 = time.monotonic()
    for _ in range(5):
        det.detect(img)
    assert (time.monotonic() - t0) / 5 < 0.5, "detection must stay cheap on the CPU"
    assert det.detect(np.zeros((240, 320, 3), np.uint8)) == []
    only_cars = det.detect(img, classes={"car"})
    assert all(d["label"] == "car" for d in only_cars)


def test_summary_and_drawing():
    from core import vision_detect as vd
    dets = [{"label": "person", "conf": 0.9, "box": (1, 1, 20, 40)},
            {"label": "person", "conf": 0.8, "box": (30, 1, 20, 40)},
            {"label": "dog", "conf": 0.7, "box": (60, 20, 30, 20)},
            {"label": "chair", "conf": 0.7, "box": (60, 20, 30, 20)}]
    assert vd.summarize(dets, skip=vd.BACKGROUND) == "2 people, a dog"
    img = vd.draw(np.zeros((100, 120, 3), np.uint8), dets, [{"name": "Anish", "box": (1, 1, 10, 10)}])
    assert img.shape == (100, 120, 3) and img.any()


def test_wants_camera():
    from core.perception import wants_camera
    for t in ("What am I holding?", "Can you see me?", "how do I look today", "who is behind me",
              "ye kya hai", "मेरे हाथ में क्या है", "what colour is this mug"):
        assert wants_camera(t), t
    for t in ("what's on my screen", "open notepad", "read this document", "what time is it"):
        assert not wants_camera(t), t


class _FakeHub:
    def __init__(self, frames):
        self.frames = frames
        self.i = 0
        self.active = True
        self.error = ""

    def acquire(self):
        pass

    def release(self):
        pass

    def wait_frame(self, timeout=4.0, fresh_after=None):
        return self.frames[0]

    def latest(self, max_age=1.0):
        f = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return f


class _FakeDet:
    def __init__(self, script):
        self.script = script
        self.n = 0

    def detect(self, frame, min_conf=0.4, nms=0.6, classes=None):
        out = self.script(self.n)
        self.n += 1
        return out


class _FakeFaces:
    def __init__(self, script):
        self.script = script
        self.n = 0
        self.people = {"Anish": {"owner": True}}

    def owner(self):
        return "Anish"

    def identify(self, frame):
        out = self.script(self.n)
        self.n += 1
        return out

    def detect(self, frame):
        return np.zeros((0, 15), np.float32)


class _FakeEngine:
    def __init__(self):
        self._busy = False
        self._is_speaking = False
        self._last_user_speech = 0.0
        self.events = []

    def _submit_vision_event(self, text, jpeg):
        self.events.append((text, jpeg))


def test_live_vision_notices_arrival_and_objects(monkeypatch, tmp_path):
    from core import brain_config, face_id, journal, perception, runtime, vision_detect
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    senses = dict(brain_config.get_senses(), live_vision=True, vision_fps=20, vision_proactive="normal",
                  vision_captions=False, journal=True)
    monkeypatch.setattr(brain_config, "get_senses", lambda: senses)
    frame = np.full((480, 640, 3), 90, np.uint8)
    person = {"label": "person", "conf": 0.9, "box": (100, 50, 200, 400)}
    phone = {"label": "cell phone", "conf": 0.8, "box": (300, 300, 40, 70)}
    # ticks 0-5: empty room; 6+: Anish arrives; 14+: holds up a phone
    det = _FakeDet(lambda n: [] if n < 6 else ([person, phone] if n >= 14 else [person]))
    faces = _FakeFaces(lambda n: [] if n < 6 else [{"name": "Anish", "box": (150, 60, 80, 90), "score": 0.8}])
    monkeypatch.setattr(vision_detect, "detector", lambda log=print: det)
    monkeypatch.setattr(face_id, "engine", lambda log=print: faces)
    monkeypatch.setattr(perception, "hub", lambda: _FakeHub([frame]))
    monkeypatch.setattr(perception, "_GAP", {"low": 0.0, "normal": 0.0, "chatty": 0.0})
    eng = _FakeEngine()
    runtime.set_engine(eng)
    per = perception.Perception()
    per._started_at -= 1000                          # past the start-up grace minute
    frames_shown = []
    per.on_frame = lambda data, summary: frames_shown.append(summary)
    try:
        per.start(log=lambda m: None)
        per._started_at = time.monotonic() - 1000
        deadline = time.time() + 10
        while time.time() < deadline and len(eng.events) < 2:
            time.sleep(0.05)
    finally:
        per.stop()
        runtime.set_engine(None)
    texts = [t for t, _ in eng.events]
    assert any("Anish" in t and "Greet" in t for t in texts), texts
    assert any("cell phone" in t for t in texts), texts
    assert all(j for _, j in eng.events), "the live frame goes with every event"
    block = per.context_block()
    assert "Anish" in block and "cell phone" in block, block
    assert frames_shown and "People" in frames_shown[-1]
    log = journal.search("", "today")
    assert "Anish came into view" in log


def test_caption_uses_vision_model(monkeypatch, tmp_path):
    from core import journal, llm, perception
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    per = perception.Perception()
    per._frame = np.full((240, 320, 3), 120, np.uint8)
    per._frame_ts = time.monotonic()
    per.scene.faces = [{"name": "Anish", "box": (10, 10, 50, 50)}]
    seen = {}

    def fake_complete(contents, **kw):
        seen["prompt"] = contents[0]
        seen["kw"] = kw
        return "Anish sits at the desk drinking tea."
    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(perception, "_can_see", lambda: True)
    per._caption()
    assert per.scene.caption == "Anish sits at the desk drinking tea."
    assert "Anish (left)" in seen["prompt"] and seen["kw"]["background"] is True
    assert "drinking tea" in journal.search("tea", "today")
