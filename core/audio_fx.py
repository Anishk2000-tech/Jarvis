"""
The assistant's own loudness: 0–200 %, like VLC's volume boost.

Windows' master volume stops at 100 %. Above that the only way to get louder is
to amplify the samples themselves, which is what VLC does — and, done naively,
what makes VLC crackle at 200 %: every peak that would exceed full scale is
chopped flat.

Here the boost goes through a peak limiter instead. Each 1 ms block's peak is
measured after the gain; where it would clip, the gain is pulled down for that
block at once (attack) and let back up over ~40 ms (release), so loud syllables
are compressed rather than squared off. Whatever still pokes above the ceiling
is rounded off by a soft-knee curve. The result is what a person hears as
"twice as loud" on laptop speakers, without the distortion.

Only the assistant's voice passes through this — music and videos keep the
system volume. The setting lives in config (voice.voice_volume) and is read at
most every two seconds, so moving the slider or saying "louder" takes effect
within a sentence.
"""
from __future__ import annotations

import threading
import time

import numpy as np

MAX_PERCENT = 200
_CEILING = 0.97          # of full scale
_KNEE = 0.85
_BLOCK = 24              # samples: 1 ms at 24 kHz
_RELEASE_S = 0.04

_cache = {"t": 0.0, "v": 100.0}
_cache_lock = threading.Lock()


def clamp_percent(value) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        v = 100
    return max(0, min(MAX_PERCENT, v))


def volume_percent(max_age: float = 2.0) -> float:
    """The configured voice volume, cached briefly (called for every batch)."""
    now = time.monotonic()
    with _cache_lock:
        if now - _cache["t"] < max_age:
            return _cache["v"]
    try:
        from core import brain_config
        v = float(clamp_percent(brain_config.get_voice_cfg().get("voice_volume", 100)))
    except Exception:
        v = 100.0
    with _cache_lock:
        _cache.update(t=now, v=v)
    return v


def set_volume_percent(value) -> int:
    """Store a new voice volume and apply it immediately."""
    v = clamp_percent(value)
    try:
        from core import brain_config
        brain_config.save_voice_cfg({"voice_volume": v})
    except Exception as e:
        print(f"[Volume] could not save: {e}")
    with _cache_lock:
        _cache.update(t=time.monotonic(), v=float(v))
    return v


def _soft_clip(y: np.ndarray, knee: float = _KNEE) -> np.ndarray:
    a = np.abs(y)
    over = a > knee
    if np.any(over):
        head = 1.0 - knee
        y = y.copy()
        y[over] = np.sign(y[over]) * (knee + head * np.tanh((a[over] - knee) / head))
    return y


class VoiceLimiter:
    """Gain + peak limiter with state carried across batches."""

    def __init__(self, sr: int = 24000):
        self.sr = sr
        self._env = 1.0                      # current gain reduction (1 = none)
        self._rel = float(np.exp(-(_BLOCK / sr) / _RELEASE_S))

    def process(self, pcm, percent: float | None = None) -> np.ndarray:
        """int16 samples (array or bytes) in, int16 out."""
        x = np.frombuffer(pcm, dtype=np.int16) if isinstance(pcm, (bytes, bytearray, memoryview)) \
            else np.asarray(pcm, dtype=np.int16)
        pct = volume_percent() if percent is None else float(percent)
        g = max(0.0, min(MAX_PERCENT, pct)) / 100.0
        if abs(g - 1.0) < 0.005 or x.size == 0:
            self._env = 1.0
            return x
        y = x.astype(np.float32) * (g / 32768.0)
        if g > 1.0:
            n = y.size
            nb = (n + _BLOCK - 1) // _BLOCK
            pad = nb * _BLOCK - n
            peaks = np.abs(np.pad(y, (0, pad))).reshape(nb, _BLOCK).max(axis=1)
            gains = np.empty(nb, dtype=np.float32)
            env = self._env
            for i in range(nb):
                need = _CEILING / peaks[i] if peaks[i] > _CEILING else 1.0
                env = need if need < env else min(1.0, need, 1.0 - (1.0 - env) * self._rel)
                gains[i] = env
            self._env = env
            y *= np.repeat(gains, _BLOCK)[:n]
            y = _soft_clip(y)
        return np.clip(y * 32768.0, -32768, 32767).astype(np.int16)


def apply_gain(pcm, percent: float) -> np.ndarray:
    """Stateless helper (tests, one-off playback such as the voice test)."""
    return VoiceLimiter().process(pcm, percent)
