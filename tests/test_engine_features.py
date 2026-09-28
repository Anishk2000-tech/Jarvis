"""The local engine's new behaviour, against a scripted model over real HTTP:
look things up before/after the model is unsure, react to what live vision
sees (or stay silent), attach the webcam frame to visual questions, and put
learned knowledge in front of the model."""
import asyncio
import json
import os
import sys
import threading

import numpy as np
import pytest

from tests.mock_llm_server import MockLLM

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeUI:
    def __init__(self):
        self.logs, self.states, self.muted, self.current_file = [], [], False, None
        self._win = type("W", (), {"_ready": True})()

    def write_log(self, t):
        self.logs.append(t)

    def set_state(self, s):
        self.states.append(s)

    def __getattr__(self, name):
        return lambda *a, **k: None


SCRIPT = {}


def script(messages, tools, api):
    return SCRIPT["fn"](messages, tools)


@pytest.fixture(scope="module")
def server():
    srv = MockLLM(script, models=("test-model",), vision_models=("test-model",))
    yield srv
    srv.close()


@pytest.fixture
def engine(server, tmp_path, monkeypatch):
    from core import brain_config, journal, knowledge, websearch
    cfg = tmp_path / "api_keys.json"
    cfg.write_text(json.dumps({
        "os_system": "linux", "assistant_name": "JARVIS", "morning_brief_enabled": False,
        "brain": {"provider": "ollama", "base_url": server.url, "model": "test-model"},
        "senses": {"live_vision": True, "vision_attach": True},
        "search": {"auto_search": True}}), encoding="utf-8")
    monkeypatch.setattr(brain_config, "CONFIG_FILE", cfg)
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    st = knowledge.KnowledgeStore(tmp_path / "knowledge.jsonl")
    monkeypatch.setattr(knowledge, "_store", st)
    websearch._cache.clear()
    sys.modules["dashboard.server"] = None
    import main
    from core import local_engine

    class LocalJarvis(local_engine.LocalEngineMixin, main.JarvisLive):
        INLINE_TOOLS = main.TOOL_DECLARATIONS

    eng = LocalJarvis(FakeUI())
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    eng._loop = loop
    yield eng, st
    loop.call_soon_threadsafe(loop.stop)


def _spoken(eng):
    out = []
    while not eng._tts_q.empty():
        out.append(eng._tts_q.get_nowait()[1])
    return out


def _last_user(messages):
    return str([m for m in messages if m.get("role") == "user"][-1].get("content"))


def test_fresh_question_is_looked_up_first(engine, monkeypatch):
    from core import local_engine, websearch
    eng, _ = engine
    asked = []
    monkeypatch.setattr(websearch, "research", lambda q, mode="search", deadline=14.0: asked.append(q) or
                        '[WEB_RESULTS for "x"] Petrol in Delhi: Rs 94.77 a litre (iocl.com).')
    SCRIPT["fn"] = lambda m, t: ({"text": "Petrol is 94.77 rupees a litre in Delhi today, says Indian Oil."}
                                if "[WEB_RESULTS" in _last_user(m) else {"text": "I am not sure."})
    req = local_engine.Request("What is the petrol price in Delhi today?", source="voice")
    final = eng._agent_turn(req, eng._turn_id)
    spoken = _spoken(eng)
    assert asked == ["What is the petrol price in Delhi today?"]
    assert spoken[0] in sum(local_engine._SEARCH_ACKS.values(), []), spoken
    assert "94.77" in final and not any("not sure" in s for s in spoken), spoken


def test_unsure_answer_triggers_search_and_is_not_spoken(engine, monkeypatch):
    from core import local_engine, websearch
    eng, _ = engine
    monkeypatch.setattr(websearch, "research", lambda q, mode="search", deadline=14.0:
                        '[WEB_RESULTS for "x"] Acme Widgets CEO: Jane Doe (reuters.com).')

    def fn(messages, tools):
        if any("[WEB_RESULTS" in str(x.get("content")) for x in messages):
            return {"text": "Acme Widgets is run by Jane Doe, according to Reuters."}
        return {"text": "I'm not sure who runs it. It might be John."}
    SCRIPT["fn"] = fn
    final = eng._agent_turn(local_engine.Request("Who runs Acme Widgets?", source="voice"), eng._turn_id)
    spoken = _spoken(eng)
    assert "Jane Doe" in final
    assert not any("not sure" in s or "John" in s for s in spoken), spoken


def test_vision_event_speaks_or_stays_silent(engine):
    from core import local_engine
    eng, _ = engine
    SCRIPT["fn"] = lambda m, t: ({"text": "SILENT"} if "phone" in _last_user(m)
                                else {"text": "Welcome back, Anish."})
    r = eng._vision_remark(local_engine.Request("[VISION_EVENT] A cell phone has just appeared in view.",
                                                source="vision"), eng._turn_id)
    assert r == "" and _spoken(eng) == []
    jpeg = b"\xff\xd8fake"
    from core import llm
    r = eng._vision_remark(local_engine.Request("[VISION_EVENT] Anish (the owner) has just come into view.",
                                                source="vision", images=[llm.image_part(jpeg, "image/jpeg")]),
                           eng._turn_id)
    assert r == "Welcome back, Anish." and _spoken(eng) == ["Welcome back, Anish."]


def test_visual_question_gets_the_live_frame(engine, server, monkeypatch):
    from core import local_engine, perception
    eng, _ = engine

    class FakePer:
        scene = perception.Scene()

        def running(self):
            return True

        def latest_jpeg(self, max_side=768, quality=80, max_age=3.0):
            return b"\xff\xd8\xff\xe0 a jpeg"

        def context_block(self):
            return "[WHAT YOU SEE — your webcam, live (1 s ago)]\nPeople: 1 (Anish)"
    monkeypatch.setattr(perception, "perception", lambda: FakePer())
    SCRIPT["fn"] = lambda m, t: {"text": "You're holding a blue mug."}
    n = len(server.requests)
    final = eng._agent_turn(local_engine.Request("What am I holding?", source="voice"), eng._turn_id)
    assert final == "You're holding a blue mug."
    chat = [r["body"] for r in server.requests[n:] if r["path"] == "/api/chat"][-1]
    user = [m for m in chat["messages"] if m["role"] == "user"][-1]
    assert user.get("images"), "the webcam frame was attached"
    assert "WEBCAM, live" in user["content"]
    assert "[WHAT YOU SEE —" in user["content"] and "[WHAT YOU SEE —" not in chat["messages"][0]["content"], \
        "per-turn context rides in the user's message so the system prompt stays cacheable"


def test_learned_facts_reach_the_model(engine, server):
    from core import local_engine
    eng, st = engine
    st.add("Anish prefers green tea without sugar", "preference", "camera", "Anish")
    SCRIPT["fn"] = lambda m, t: {"text": "Green tea, no sugar, coming up."}
    n = len(server.requests)
    eng._agent_turn(local_engine.Request("Make me my usual tea", source="typed"), eng._turn_id)
    chat = [r["body"] for r in server.requests[n:] if r["path"] == "/api/chat"][-1]
    user = [m for m in chat["messages"] if m["role"] == "user"][-1]
    assert "green tea without sugar" in user["content"]


def test_system_prompt_is_stable_between_turns(engine, server):
    """Ollama reuses its cache of the conversation only while the start of the
    prompt stays the same: two turns must send an identical system prompt."""
    from core import local_engine
    eng, st = engine
    SCRIPT["fn"] = lambda m, t: {"text": "Sure."}
    n = len(server.requests)
    eng._agent_turn(local_engine.Request("What time is it in Tokyo?", source="typed"), eng._turn_id)
    eng._agent_turn(local_engine.Request("And in London?", source="typed"), eng._turn_id)
    chats = [r["body"] for r in server.requests[n:] if r["path"] == "/api/chat"]
    assert chats[0]["messages"][0] == chats[-1]["messages"][0]
    first = chats[0]["messages"]
    assert chats[-1]["messages"][:len(first)] == first, "the earlier turn is resent unchanged"
