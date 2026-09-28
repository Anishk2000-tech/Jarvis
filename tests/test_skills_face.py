import json
from actions import skill_manager as sm

GOOD = '''
PLUGIN = {"name": "coin_flip", "description": "Flip a coin", "parameters": {"type": "OBJECT", "properties": {}}}
def run(parameters, player=None):
    import random
    return random.choice(["heads", "tails"])
'''


def test_validate_plugin_source():
    assert sm.validate_plugin_source(GOOD) == (True, "ok", "coin_flip")
    assert not sm.validate_plugin_source("def run(:")[0]
    assert "run" in sm.validate_plugin_source('PLUGIN = {"name": "x_y", "parameters": {"type": "OBJECT"}}')[1]
    assert not sm.validate_plugin_source(GOOD.replace('"OBJECT"', '"object"'))[0]


def test_create_goes_through_confirmation_then_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "PLUGINS", tmp_path)
    captured = {}
    monkeypatch.setattr(sm.confirm_gate, "request", lambda key, title, detail, run: captured.update(run=run, title=title) or "[CONFIRMATION_PENDING]")
    monkeypatch.setattr(sm.runtime, "reload_tools", lambda: "Reloaded plugins: 1 active.")
    monkeypatch.setattr(sm.runtime, "inject", lambda t: True)
    out = sm.skill_manager({"action": "create", "code": GOOD})
    assert out == "[CONFIRMATION_PENDING]" and not (tmp_path / "coin_flip.py").exists()
    assert "coin_flip" in captured["title"]
    captured["run"]()
    assert (tmp_path / "coin_flip.py").exists()
    from core.plugin_loader import discover_plugins
    reg = discover_plugins(tmp_path, set(), logger=lambda m: None)
    assert reg.has("coin_flip") and reg.run("coin_flip", {}) in ("heads", "tails")


def test_routines(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "ROUTINES", tmp_path / "r.json")
    assert "Saved" in sm.skill_manager({"action": "save_routine", "name": "Morning", "steps": "1. weather 2. news"})
    out = sm.skill_manager({"action": "run_routine", "name": "morning"})
    assert out.startswith("[ROUTINE morning]") and "weather" in out
    assert "No routine" in sm.skill_manager({"action": "run_routine", "name": "evening"})
