import json, sys, os
from datetime import datetime, timedelta
import pytest
from core import mcp_client, scheduler


def test_mcp_stdio_roundtrip(tmp_path, monkeypatch):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"fake": {"command": sys.executable, "args": [os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")]},
                                              "off": {"command": "nope", "disabled": True}}}))
    monkeypatch.setattr(mcp_client, "CONFIG_FILE", cfg)
    m = mcp_client.McpManager()
    logs = []
    m._log = logs.append
    m.reload()
    names = [d["name"] for d in m.gemini_declarations()]
    assert names == ["mcp_fake_add", "mcp_fake_fail"], (names, logs)
    decl = m.gemini_declarations()[0]
    assert decl["parameters"]["properties"]["a"]["type"] == "NUMBER"
    assert m.call("mcp_fake_add", {"a": 2, "b": 3}) == "5"
    assert m.call("mcp_fake_fail", {}).startswith("ERROR:")
    assert "not available" in m.call("mcp_zzz", {})


def test_scheduler_once_and_recurring(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "SCHEDULE_FILE", tmp_path / "s.json")
    out = scheduler.add("say hi", in_minutes=1)
    assert "Scheduled" in out
    assert scheduler.due_jobs() == []
    fired = scheduler.due_jobs(datetime.now() + timedelta(minutes=2))
    assert [j["task"] for j in fired] == ["say hi"]
    assert scheduler.due_jobs(datetime.now() + timedelta(minutes=3)) == []   # once only
    scheduler.add("drink water", repeat="every_30_minutes")
    t = datetime.now() + timedelta(minutes=31)
    assert [j["task"] for j in scheduler.due_jobs(t)] == ["drink water"]
    assert "drink water" in scheduler.list_jobs()
    assert "Removed" in scheduler.remove(task_hint="water")
    scheduler.add("news", time="08:30", repeat="weekdays")
    job = json.loads((tmp_path / "s.json").read_text())[0]
    nxt = datetime.fromisoformat(job["next"])
    assert nxt.hour == 8 and nxt.minute == 30 and nxt.weekday() < 5 and nxt > datetime.now()


def test_scheduler_skips_long_missed(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "SCHEDULE_FILE", tmp_path / "s.json")
    scheduler.add("x", in_minutes=1)
    assert scheduler.due_jobs(datetime.now() + timedelta(hours=5)) == []


def test_scheduler_bad_time(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "SCHEDULE_FILE", tmp_path / "s.json")
    assert "could not read" in scheduler.add("x", time="banana")
    assert scheduler._parse_time("7pm", datetime.now()).hour == 19
