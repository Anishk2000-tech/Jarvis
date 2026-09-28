import wave, os
import numpy as np
from core import vad

def load_speech(path):
    w = wave.open(path)
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return vad.resample(x, w.getframerate(), 16000)


def run(path, det=None, noise=0.0):
    speech = load_speech(path)
    rng = np.random.default_rng(0)
    sil = np.zeros(16000, dtype=np.int16)
    stream = np.concatenate([sil, speech, sil, sil, speech, sil]).astype(np.float32)
    stream += rng.normal(0, noise, stream.size)
    stream = np.clip(stream, -32768, 32767).astype(np.int16)
    got, starts = [], []
    seg = vad.Segmenter(got.append, on_start=lambda: starts.append(1), detector=det)
    for i in range(0, stream.size, 1024):
        seg.feed(stream[i:i + 1024])
    seg.flush()
    return got, starts, seg.kind, speech.size


def test_silero_finds_two_utterances(speech_wav):
    got, starts, kind, n = run(speech_wav)
    assert kind == "silero"
    assert len(got) == 2 and len(starts) == 2, [g.size / 16000 for g in got]
    for g in got:
        assert 0.6 * n < g.size < 1.5 * n


def test_energy_fallback_finds_utterances(speech_wav):
    got, starts, kind, n = run(speech_wav, det=vad.EnergyVAD(), noise=30.0)
    assert len(got) >= 2


def test_silence_and_noise_produce_nothing():
    seg = vad.Segmenter(lambda a: (_ for _ in ()).throw(AssertionError("should not fire")))
    rng = np.random.default_rng(1)
    for _ in range(100):
        seg.feed((rng.normal(0, 40, 1024)).astype(np.int16))
    seg.flush()


def test_resample_lengths():
    x = np.arange(22050, dtype=np.int16)
    assert vad.resample(x, 22050, 24000).size == 24000
