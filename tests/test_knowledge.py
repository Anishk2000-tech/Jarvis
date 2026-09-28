"""Learning: the fact store, recall, and distilling the journal with a model."""
import json

import pytest

from tests.mock_llm_server import MockLLM


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    from core import brain_config, journal, knowledge
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(knowledge, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(knowledge, "EMB_FILE", tmp_path / "emb.npz")
    st = knowledge.KnowledgeStore(tmp_path / "knowledge.jsonl")
    monkeypatch.setattr(knowledge, "_store", st)
    cfg = tmp_path / "api_keys.json"
    cfg.write_text(json.dumps({"user_name": "Anish", "brain": {"provider": "ollama", "model": "m"}}),
                   encoding="utf-8")
    monkeypatch.setattr(brain_config, "CONFIG_FILE", cfg)
    return tmp_path, st, cfg


def test_store_merges_searches_and_forgets(sandbox):
    tmp, st, _ = sandbox
    a = st.add("Anish's sister Priya visits on Sundays", "person", "room", "Priya")
    b = st.add("Priya, Anish's sister, visits on Sundays", "person", "camera", "Priya")
    assert a == b and st.facts[a]["count"] == 2, "the same fact seen twice is reinforced, not duplicated"
    st.add("The living-room lamp is called Lamp 2 in Smart Life", "device")
    st.add("open_app cannot start WhatsApp; the web version works", "lesson")
    st.save()
    hits = st.search("when does priya come over")
    assert hits and "Priya" in hits[0]["text"]
    assert st.search("whatsapp")[0]["kind"] == "lesson"
    st2 = type(st)(tmp / "knowledge.jsonl")
    st2.load()
    assert len(st2.facts) == 3
    gone = st.forget("lamp 2 smart life")
    assert gone and "Lamp 2" in gone[0] and len(st.facts) == 2


def test_context_block(sandbox):
    from core import knowledge
    _, st, _ = sandbox
    st.add("Anish prefers tea over coffee", "preference", "conversation", "Anish")
    st.add("The router is in the hall cupboard", "place")
    block = knowledge.context_block("make me a hot drink")
    assert "[THINGS YOU HAVE LEARNED" in block and "tea" in block


def test_tool_results_are_journaled(sandbox):
    from core import journal, knowledge
    knowledge.note_tool_result("open_app", {"app_name": "WhatsApp"}, "Could not find WhatsApp.")
    knowledge.note_tool_result("save_memory", {"k": "v"}, "saved")        # not interesting
    text = journal.search("", "today")
    assert "open_app" in text and "FAILED" in text and "save_memory" not in text


def test_consolidate_with_a_model(sandbox):
    from core import brain_config, journal, knowledge
    tmp, st, cfg = sandbox
    old = st.add("Anish's favourite colour is blue", "preference", "conversation", "Anish")
    journal.append("room", "Priya: I'll come by every Sunday for lunch from now on.", False)
    journal.append("seen", "Anish sits at the desk wearing a red hoodie", None, via="camera")
    journal.append("user", "Actually my favourite colour is green now.", True)
    journal.append("tool", 'open_app({"app_name": "WhatsApp"}) → FAILED: not installed', None)
    prompts = []

    def script(messages, tools, api):
        prompts.append(messages)
        return {"text": json.dumps({
            "add": [{"fact": "Priya comes for lunch every Sunday", "kind": "routine", "about": "Priya"},
                    {"fact": "WhatsApp is not installed as an app; use web.whatsapp.com", "kind": "lesson"}],
            "update": [{"id": old, "fact": "Anish's favourite colour is green"}],
            "delete": []})}
    srv = MockLLM(script, models=("m",))
    try:
        data = json.loads(cfg.read_text())
        data["brain"]["base_url"] = srv.url
        cfg.write_text(json.dumps(data))
        res = knowledge.consolidate()
    finally:
        srv.close()
    assert res["added"] == 2 and res["updated"] == 1 and res["observations"] == 4, res
    user_msg = prompts[0][-1]["content"]
    assert f"[{old}]" in user_msg and "overheard: Priya" in user_msg and "camera: Anish" in user_msg
    texts = [f["text"] for f in st.facts.values()]
    assert "Anish's favourite colour is green." in texts
    assert any("Sunday" in t for t in texts)
    # nothing new: nothing to do, and no model call
    n = len(prompts)
    res2 = knowledge.consolidate()
    assert res2["observations"] == 0 and len(prompts) == n


def test_learning_respects_switches(sandbox):
    from core import brain_config, journal, knowledge
    tmp, st, cfg = sandbox
    data = json.loads(cfg.read_text())
    data["learning"] = {"from_screen": False, "from_room": False}
    cfg.write_text(json.dumps(data))
    journal.append("screen", "Switched to chrome: bank statement", None)
    journal.append("room", "someone talking", False)
    journal.append("user", "remember I start work at nine", True)
    obs, _ = knowledge.pending_observations()
    assert [o["speaker"] for o in obs] == ["user"]


def test_knowledge_tool(sandbox):
    from actions.knowledge import knowledge_tool
    _, st, _ = sandbox
    assert "Learned" in knowledge_tool({"action": "teach", "query": "The spare key is under the blue pot"})
    assert "blue pot" in knowledge_tool({"action": "search", "query": "where is the spare key"})
    assert "1 learned facts" in knowledge_tool({"action": "stats"})
    assert "Forgot" in knowledge_tool({"action": "forget", "query": "spare key blue pot"})
