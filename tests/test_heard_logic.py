import asyncio
import time
import pytest
from core import local_engine as le, brain_config


class Stub(le.LocalEngineMixin):
    """Just enough of the engine to exercise _on_heard."""
    def __init__(self, senses):
        self._asst_name = "JARVIS"
        self._busy = False
        self._is_speaking = False
        self._spoken = __import__("collections").deque(maxlen=40)
        self._last_reply_end = 0.0
        self._wake_enabled = False
        self._awake = True
        self._session_log = []
        self._dashboard = None
        self._turn_id = 0
        self._last_lang = ""
        self._last_user_speech = 0
        self.logs, self.submitted, self.spoken_out, self.interrupts = [], [], [], 0
        self.ui = type("U", (), {"write_log": lambda s, t: self.logs.append(t)})()
        self._senses = senses

    def _tail_active(self):
        return False

    def interrupt(self):
        self.interrupts += 1
        self._is_speaking = False

    def _submit(self, text, images=None, source="system", lang=""):
        self.submitted.append(text)

    def _speak(self, sentence, turn_id):
        self.spoken_out.append(sentence)


@pytest.fixture
def make(monkeypatch, tmp_path):
    monkeypatch.setattr(le.journal, "append", lambda *a, **k: None)

    def f(**senses):
        base = dict(brain_config._DEFAULT_SENSES)
        base.update(senses)
        monkeypatch.setattr(brain_config, "get_senses", lambda: base)
        return Stub(base)
    return f


def heard(eng, text, during=False):
    asyncio.run(eng._on_heard(text, "en", during))


def test_echo_is_ignored_and_new_voice_interrupts(make):
    eng = make()
    eng._is_speaking = True
    eng._spoken.append((time.monotonic(), "The weather in Mumbai is thirty two degrees with rain."))
    heard(eng, "weather in Mumbai is thirty two degrees", during=True)
    assert eng.interrupts == 0 and eng.submitted == []
    heard(eng, "actually what about Delhi tomorrow", during=True)
    assert eng.interrupts == 1 and eng.submitted == ["actually what about Delhi tomorrow"]


def test_stop_while_speaking_or_busy(make):
    eng = make()
    eng._is_speaking = True
    heard(eng, "stop", during=True)
    assert eng.interrupts == 1 and eng.submitted == []
    eng._busy = True
    heard(eng, "wait")
    assert eng.interrupts == 2 and eng.submitted == []


def test_ambient_mode_needs_the_name(make):
    eng = make(listen_mode="ambient")
    heard(eng, "did you see the match yesterday")
    assert eng.submitted == [] and any(l.startswith("Heard:") for l in eng.logs)
    heard(eng, "Jarvis, turn off the lights")
    assert eng.submitted == ["turn off the lights"]
    eng._last_reply_end = time.monotonic()          # it just answered → follow-up window
    heard(eng, "and the fan too")
    assert eng.submitted[-1] == "and the fan too"


def test_voice_confirmation_only_outside_own_speech(make, monkeypatch):
    eng = make()
    resolved = []
    monkeypatch.setattr(le.confirm_gate, "pending_title", lambda: "Shut down the computer?")
    monkeypatch.setattr(le.confirm_gate, "resolve", lambda ok: resolved.append(ok))
    eng._spoken.append((time.monotonic(), "Please say confirm to shut down."))
    eng._is_speaking = True
    heard(eng, "confirm", during=True)                  # its own voice: must not count
    assert resolved == []
    eng._is_speaking = False
    heard(eng, "confirm")
    assert resolved == [True] and eng.submitted == []


def test_owner_only_mode(make, monkeypatch):
    eng = make(owner_only=True, face_presence=True)
    monkeypatch.setattr(le.runtime, "get_state", lambda k, d=None: False if k == "owner_present" else d)
    heard(eng, "open notepad")
    assert eng.submitted == []
    monkeypatch.setattr(le.runtime, "get_state", lambda k, d=None: True if k == "owner_present" else d)
    heard(eng, "open notepad")
    assert eng.submitted == ["open notepad"]
