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


def test_new_controls_vision_cctv_volume(clean_config, tmp_path, monkeypatch):
    """The live-vision view, the camera wall, the volume slider and the new
    settings sections all build and save."""
    from PyQt6.QtWidgets import QApplication
    import ui
    from core import audio_fx, brain_config, cctv
    from ui_brain import BrainSettingsOverlay
    monkeypatch.setattr(cctv, "CFG_FILE", tmp_path / "cctv.json")
    os.makedirs(os.path.dirname(clean_config), exist_ok=True)
    json.dump({"brain": {"provider": "ollama", "model": "gemma4:e4b"}}, open(clean_config, "w"))
    ju = ui.JarvisUI("face.png")
    win = ju._win
    # voice volume slider in the controls drawer
    win._vol_slider.setValue(170)
    win._save_voice_volume()
    assert audio_fx.volume_percent(max_age=0) == 170
    assert "170%" in win._vol_lbl.text()
    # live vision picture-in-picture shows annotated frames only while enabled
    import cv2
    import numpy as np
    jpeg = cv2.imencode(".jpg", np.full((120, 160, 3), 128, np.uint8))[1].tobytes()
    brain_config.save_senses({"live_vision": True})
    ju.show_vision_frame(jpeg, "People: 1 (Anish)")
    QApplication.processEvents()
    assert win._live_pip.isVisible() and "Anish" in win._live_pip._txt.text()
    brain_config.save_senses({"live_vision": False})
    ju.show_vision_frame(jpeg, "x")
    QApplication.processEvents()
    assert not win._live_pip.isVisible()
    # the camera wall
    cctv.add_camera("Porch", "http://127.0.0.1:9/snapshot.jpg")
    ju.open_cctv()
    QApplication.processEvents()
    wall = win._cctv_wall
    assert wall is not None and wall.isVisible() and "porch" in wall._tiles
    wall._refresh()
    wall.close_wall()
    cctv.manager().stop()
    # the settings overlay carries the new sections and saves them
    ov = BrainSettingsOverlay(win.centralWidget(), first_run=False)
    ov._w["live_vision"].setChecked(True)
    ov._w["vision_proactive"].setCurrentIndex(ov._w["vision_proactive"].findData("normal"))
    ov._w["search_provider"].setCurrentIndex(ov._w["search_provider"].findData("tavily"))
    ov._w["tavily_key"].setText("tvly-123")
    ov._w["learn_screen"].setChecked(False)
    ov._w["voice_volume"].setValue(140)
    ov._save()
    cfg = json.load(open(clean_config))
    assert cfg["senses"]["live_vision"] is True and cfg["senses"]["vision_proactive"] == "normal"
    assert cfg["search"]["provider"] == "tavily" and cfg["search"]["tavily_key"] == "tvly-123"
    assert cfg["learning"]["from_screen"] is False and cfg["voice"]["voice_volume"] == 140
    from core import perception
    perception.perception().stop()
    win.close()
