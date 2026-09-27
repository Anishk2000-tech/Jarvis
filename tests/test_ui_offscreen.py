import json, os, sys
import pytest
os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def clean_config():
    path = os.path.join(ROOT, "config", "api_keys.json")
    backup = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    if backup is not None:
        os.remove(path)
    yield path
    if backup is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        open(path, "w", encoding="utf-8").write(backup)


def test_first_run_and_settings(clean_config):
    from PyQt6.QtWidgets import QApplication
    import ui
    from ui_brain import BrainSettingsOverlay
    from core import brain_config
    ju = ui.JarvisUI("face.png")
    win = ju._win
    assert win._ready is False
    ov = win._overlay
    assert isinstance(ov, BrainSettingsOverlay) and ov.isVisible()
    # pick LM Studio and save
    idx = ov._w["provider"].findData("lmstudio")
    ov._w["provider"].setCurrentIndex(idx)
    assert not ov._rows["api_key_row"].isVisibleTo(ov)
    assert ov._w["base_url"].text() == "http://localhost:1234/v1"
    ov._w["model"].setCurrentText("qwen2.5-7b-instruct")
    ov._save()
    QApplication.processEvents()
    assert win._ready is True and win._overlay is None
    cfg = json.load(open(clean_config))
    assert cfg["brain"]["provider"] == "lmstudio" and cfg["brain"]["model"] == "qwen2.5-7b-instruct"
    assert cfg["voice"]["tts_engine"] == "edge" and cfg["senses"]["listen_mode"] == "active"
    assert brain_config.is_configured() and brain_config.uses_local_engine()
    # cloud provider without key is refused
    ov2 = BrainSettingsOverlay(win.centralWidget(), first_run=False)
    ov2._w["provider"].setCurrentIndex(ov2._w["provider"].findData("anthropic"))
    fired = []
    ov2.saved.connect(fired.append)
    ov2._w["api_key"].setText("")
    ov2._save()
    assert not fired and "API key" in ov2._status["save"].text()
    # switching to Gemini Live from a local brain requires a restart
    ov2._w["provider"].setCurrentIndex(ov2._w["provider"].findData("gemini_live"))
    ov2._w["api_key"].setText("AIzaTESTKEY1234567890")
    ov2._save()
    assert fired == [True]
    cfg = json.load(open(clean_config))
    assert cfg["gemini_api_key"] == "AIzaTESTKEY1234567890" and cfg["brain"]["provider"] == "gemini_live"
    # listen toggle
    win._toggle_listen_mode()
    assert brain_config.get_senses()["listen_mode"] == "ambient"
    assert "AMBIENT" in win._listen_btn.text()
    win._open_brain_settings()
    assert win._brain_overlay.isVisible()
    win.close()
