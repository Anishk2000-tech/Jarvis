import numpy as np
from core import tts_engine, stt_engine, brain_config


class Boom(tts_engine._Engine):
    name = "boom"
    calls = 0
    def synth(self, text, lang=""):
        Boom.calls += 1
        raise RuntimeError("no internet")


class Ok(tts_engine._Engine):
    name = "ok"
    def synth(self, text, lang=""):
        yield np.ones(100, dtype=np.int16)


def test_tts_chain_falls_back_and_rests_the_failed_engine():
    logs = []
    chain = tts_engine.TTSChain(Boom(), Ok(), logs.append)
    assert sum(c.size for c in chain.synth("hello")) == 100
    assert sum(c.size for c in chain.synth("again")) == 100
    assert Boom.calls == 1, "a failed engine is rested, not retried every sentence"
    assert len([l for l in logs if "failed" in l]) == 1


def test_tts_chain_without_fallback_raises():
    chain = tts_engine.TTSChain(Boom(), None, lambda m: None)
    try:
        list(chain.synth("x"))
        assert False
    except RuntimeError:
        pass


def test_edge_voice_follows_language():
    e = tts_engine.EdgeTTS("en-GB-RyanNeural")
    assert e._voice_for("नमस्ते आप कैसे हैं", "") == "hi-IN-MadhurNeural"
    assert e._voice_for("Hola, ¿cómo estás?", "es") == "es-ES-AlvaroNeural"
    assert e._voice_for("Hello there", "en") == "en-GB-RyanNeural"
    f = tts_engine.EdgeTTS("en-IN-NeerjaNeural")
    assert f._voice_for("नमस्ते आप कैसे हैं", "") == "hi-IN-SwaraNeural"
    m = tts_engine.EdgeTTS("en-US-AvaMultilingualNeural")
    assert m._voice_for("नमस्ते आप कैसे हैं", "hi") == "en-US-AvaMultilingualNeural"


def test_hallucination_filter():
    for t in ["Thank you.", "Thanks for watching!", "you", "[Music]", "Subtitles by the Amara.org community",
              "the the the the", "..."]:
        assert stt_engine.is_hallucination(t), t
    for t in ["Thank you, now open Chrome", "turn off the lights", "you are late"]:
        assert not stt_engine.is_hallucination(t), t


def test_recommendations_for_this_laptop():
    r = brain_config.recommend({"ram_gb": 32, "vram_gb": 4, "gpu": "GTX 1650", "cores": 6})
    assert r["model"] == "qwen2.5:7b" and r["vision_model"] == "qwen2.5vl:3b" and "qwen2.5:3b" in r["why"]
    assert brain_config.recommend({"ram_gb": 16, "vram_gb": 0})["model"] == "qwen2.5:3b"
    assert brain_config.recommend({"ram_gb": 8, "vram_gb": 0})["model"] == "qwen2.5:1.5b"
    assert brain_config.recommend({"ram_gb": 64, "vram_gb": 12})["smart_model"] == "qwen2.5:14b"
