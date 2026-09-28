"""Voice volume 0-200 %: gain, limiter, and the voice-volume actions."""
import json
import os

import numpy as np
import pytest

from core import audio_fx


def _speechlike(seconds=1.0, peak=0.97, sr=24000):
    t = np.arange(int(sr * seconds)) / sr
    env = np.clip(np.sin(2 * np.pi * 3 * t), 0, 1) ** 2               # syllables with pauses
    x = (np.sin(2 * np.pi * 180 * t) + 0.4 * np.sin(2 * np.pi * 1300 * t)) * env
    return (x / np.abs(x).max() * peak * 32767).astype(np.int16)


def _rms_db(x):
    y = x.astype(np.float32) / 32768
    return 20 * np.log10(np.sqrt(np.mean(y * y)) + 1e-9)


def test_unity_and_cut():
    x = _speechlike()
    assert np.array_equal(audio_fx.apply_gain(x, 100), x)
    half = audio_fx.apply_gain(x, 50)
    assert abs(_rms_db(half) - (_rms_db(x) - 6.02)) < 0.1
    assert not np.any(audio_fx.apply_gain(x, 0))


def test_boost_is_louder_without_clipping(speech_wav):
    import wave
    from core.vad import resample
    w = wave.open(speech_wav)
    x = resample(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate(), 24000)
    x = (x.astype(np.float32) / np.abs(x).max() * 0.97 * 32767).astype(np.int16)   # a TTS-level voice
    for pct, gain_db in ((150, 2.0), (200, 3.0)):
        y = audio_fx.apply_gain(x, pct)
        assert _rms_db(y) > _rms_db(x) + gain_db, (pct, _rms_db(y) - _rms_db(x))
        assert np.abs(y.astype(np.int32)).max() <= 32767 * 0.999
    # a quiet voice gets the full boost: 2x = +6 dB
    quiet = _speechlike(peak=0.3)
    assert abs(_rms_db(audio_fx.apply_gain(quiet, 200)) - (_rms_db(quiet) + 6.02)) < 0.2


def test_streaming_batches_match_length_and_stay_bounded():
    x = _speechlike(2.0)
    lim = audio_fx.VoiceLimiter()
    out = np.concatenate([lim.process(x[i:i + 4800].tobytes(), 200) for i in range(0, x.size, 4800)])
    assert out.size == x.size and out.dtype == np.int16
    assert np.abs(out.astype(np.int32)).max() < 32767


def test_percent_is_clamped():
    assert audio_fx.clamp_percent(350) == 200
    assert audio_fx.clamp_percent(-5) == 0
    assert audio_fx.clamp_percent("abc") == 100


@pytest.fixture
def cfg_sandbox(tmp_path, monkeypatch):
    from core import brain_config
    f = tmp_path / "api_keys.json"
    f.write_text(json.dumps({"brain": {"provider": "ollama"}}), encoding="utf-8")
    monkeypatch.setattr(brain_config, "CONFIG_FILE", f)
    audio_fx._cache.update(t=0.0, v=100.0)
    return f


def test_voice_volume_actions(cfg_sandbox, monkeypatch):
    from actions import computer_settings as cs
    r = cs.computer_settings({"action": "voice_volume_set", "value": "180"})
    assert "180%" in r
    assert audio_fx.volume_percent(max_age=0) == 180
    assert json.loads(cfg_sandbox.read_text())["voice"]["voice_volume"] == 180
    r = cs.computer_settings({"action": "voice_louder"})
    assert "200%" in r and "maximum" in r
    r = cs.computer_settings({"description": "speak quieter"})
    assert audio_fx.volume_percent(max_age=0) == 175, r
    # "set volume to 150%": Windows stops at 100, the voice takes the rest
    calls = []
    monkeypatch.setattr(cs, "volume_set", lambda v: calls.append(v))
    monkeypatch.setattr(cs, "volume_get", lambda: 60)
    monkeypatch.setattr(cs, "_PYAUTOGUI", True)
    r = cs.computer_settings({"action": "volume_set", "value": "150"})
    assert calls == [100] and audio_fx.volume_percent(max_age=0) == 150, r
    assert cs._detect_action("set your volume to 120")["action"] == "voice_volume_set"
    assert cs._detect_action("louder")["action"] == "volume_up"
