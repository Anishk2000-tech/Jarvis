"""
End-to-end test of the local voice engine, headless.

Real main.py, real JarvisLive + LocalEngineMixin, real action discovery and tool
dispatch, real VAD on real (synthesized) speech, real HTTP to an Ollama-style
server — only the sound card, the speech recogniser, the voice and the model
are stand-ins.
"""
import asyncio
import json
import os
import shutil
import sys
import threading
import time
import wave

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = "/tmp/claude-0/-home-user-Jarvis/c2721e9b-db56-5896-bce0-0f1c1c0ddab8/scratchpad"

from tests.mock_llm_server import MockLLM  # noqa: E402


class FakeUI:
    def __init__(self):
        self.logs, self.states, self.muted, self.current_file = [], [], False, None
        self._win = type("W", (), {"_ready": True})()
        self.content = []

    def write_log(self, t):
        self.logs.append(t)

    def set_state(self, s):
        self.states.append(s)

    def show_content(self, title, text):
        self.content.append((title, text))

    def __getattr__(self, name):          # every other hook is a no-op
        return lambda *a, **k: None


class FakeInput:
    instances = []

    def __init__(self, samplerate, channels, dtype, blocksize, device, callback):
        self.cb = callback
        FakeInput.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def feed(self, samples):
        for i in range(0, samples.size, 1024):
            blk = samples[i:i + 1024]
            if blk.size < 1024:
                blk = np.pad(blk, (0, 1024 - blk.size))
            self.cb(blk.reshape(-1, 1).astype(np.int16), 1024, None, None)
            time.sleep(0.004)


class FakeOutput:
    written = bytearray()

    def __init__(self, **kw):
        self.latency = 0.05

    def start(self):
        pass

    def write(self, data):
        FakeOutput.written.extend(data)
        time.sleep(len(data) / 2 / 24000 * 0.1)

    def stop(self):
        pass

    def close(self):
        pass


def llm_script(messages, tools, api):
    last = messages[-1]
    content = str(last.get("content"))
    if "single word: ready" in content:
        return {"text": "ready"}
    if last.get("role") == "tool":
        return {"text": "Done. I'll remind you every thirty minutes."}
    if "stretch" in content:
        return {"text": "Setting that up. ", "tool_calls": [{"name": "scheduled_tasks", "arguments": {
            "action": "add", "task": "remind the user to stretch", "repeat": "every_30_minutes"}}]}
    return {"text": "Hello sir."}


class FakeSTT:
    name = "fake"

    def load(self):
        pass

    def transcribe(self, samples):
        return "Jarvis, remind me to stretch every thirty minutes.", "en"


class FakeTTS:
    name = "fake"
    spoken = []

    def load(self):
        pass

    def synth(self, text, lang=""):
        FakeTTS.spoken.append(text)
        n = int(24000 * 0.03 * max(1, len(text.split())))
        t = np.arange(n) / 24000
        yield (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)


@pytest.fixture
def sandbox_config():
    cfg_dir = os.path.join(ROOT, "config")
    path = os.path.join(cfg_dir, "api_keys.json")
    backup = None
    if os.path.exists(path):
        backup = open(path, encoding="utf-8").read()
    mem_backup = {}
    for f in ("memory/schedule.json",):
        p = os.path.join(ROOT, f)
        mem_backup[p] = open(p, encoding="utf-8").read() if os.path.exists(p) else None
    yield path
    if backup is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    else:
        open(path, "w", encoding="utf-8").write(backup)
    for p, content in mem_backup.items():
        if content is None:
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        else:
            open(p, "w", encoding="utf-8").write(content)
    shutil.rmtree(os.path.join(ROOT, "memory", "journal"), ignore_errors=True)


def test_voice_request_runs_tool_and_speaks(sandbox_config, monkeypatch):
    server = MockLLM(llm_script, models=("test-model",))
    os.makedirs(os.path.dirname(sandbox_config), exist_ok=True)
    json.dump({"os_system": "linux", "assistant_name": "JARVIS", "morning_brief_enabled": False,
               "brain": {"provider": "ollama", "base_url": server.url, "model": "test-model"},
               "senses": {"listen_mode": "ambient", "face_presence": False},
               "voice": {"end_silence_ms": 500}},
              open(sandbox_config, "w"))

    sys.modules["dashboard.server"] = None            # no phone dashboard in tests
    import sounddevice
    monkeypatch.setattr(sounddevice, "InputStream", FakeInput)
    monkeypatch.setattr(sounddevice, "RawOutputStream", FakeOutput)
    import main
    from core import local_engine
    monkeypatch.setattr(local_engine, "create_stt", lambda log=print: FakeSTT())
    monkeypatch.setattr(local_engine, "create_tts", lambda log=print: FakeTTS())

    class LocalJarvis(local_engine.LocalEngineMixin, main.JarvisLive):
        INLINE_TOOLS = main.TOOL_DECLARATIONS

    ui = FakeUI()
    eng = LocalJarvis(ui)
    threading.Thread(target=lambda: asyncio.run(eng.run()), daemon=True).start()

    deadline = time.time() + 20
    while time.time() < deadline and not (FakeInput.instances and any("Brain ready" in l for l in ui.logs)):
        time.sleep(0.1)
    assert FakeInput.instances, ui.logs
    assert any("Brain ready" in l for l in ui.logs), ui.logs

    w = wave.open(os.path.join(SP, "hello.wav"))
    from core.vad import resample
    speech = resample(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate(), 16000)
    mic = FakeInput.instances[-1]
    mic.feed(np.zeros(16000, dtype=np.int16))
    mic.feed(speech)
    mic.feed(np.zeros(24000, dtype=np.int16))

    deadline = time.time() + 30
    while time.time() < deadline and not any(l.startswith("JARVIS:") for l in ui.logs):
        time.sleep(0.1)
    server.close()
    joined = "\n".join(ui.logs)
    assert "You: Jarvis, remind me to stretch" in joined, joined
    assert "JARVIS: Setting that up. Done. I'll remind you every thirty minutes." in joined, joined
    sched = json.load(open(os.path.join(ROOT, "memory", "schedule.json")))
    assert sched and sched[0]["repeat"] == "every_30_minutes"
    assert FakeTTS.spoken[:2] == ["Setting that up.", "Done."], FakeTTS.spoken
    expected = sum(int(24000 * 0.03 * max(1, len(t.split()))) * 2 for t in FakeTTS.spoken)
    deadline = time.time() + 5
    while time.time() < deadline and len(FakeOutput.written) < expected:
        time.sleep(0.05)
    assert len(FakeOutput.written) == expected, "every spoken sentence reached the speaker"
    assert "SPEAKING" in ui.states
    # the tool call went over the wire with a proper tools list and a big enough context
    chat_reqs = [r["body"] for r in server.requests if r["path"] == "/api/chat"]
    assert chat_reqs[-1]["options"]["num_ctx"] >= 8192
    names = {t["function"]["name"] for t in chat_reqs[-1]["tools"]}
    assert {"scheduled_tasks", "save_memory", "open_app", "conversation_log"} <= names
    # ambient mode: the heard line went to the journal as addressed
    from core import journal
    assert "remind me to stretch" in journal.search("stretch", "today")
