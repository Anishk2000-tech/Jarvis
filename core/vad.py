"""
Finding speech in the microphone stream, and cutting it into utterances.

Two detectors, the better one first:

  Silero VAD   A 2 MB neural model that ships inside faster-whisper, run with
               onnxruntime on the CPU in well under a millisecond per 32 ms
               frame. Tells a voice from a fan, a keyboard or music.
  Energy       An adaptive loudness gate. Always available; used only when the
               model cannot be loaded.

`Segmenter` turns the frame decisions into whole utterances: it keeps a short
pre-roll so the first syllable is not clipped, waits out a configurable pause
before deciding you have finished, and hands each utterance over as 16 kHz
int16 samples.
"""
from __future__ import annotations

import collections
import glob
import os
import threading
import time
from typing import Callable

import numpy as np

SR = 16000
FRAME = 512                    # samples per decision (32 ms at 16 kHz)
_CONTEXT = 64


def _silero_path() -> str | None:
    try:
        import faster_whisper
        base = os.path.join(os.path.dirname(faster_whisper.__file__), "assets")
        found = sorted(glob.glob(os.path.join(base, "silero_vad*.onnx")))
        return found[-1] if found else None
    except Exception:
        return None


class SileroVAD:
    """Streaming wrapper around the Silero ONNX model (v5/v6 interface)."""

    def __init__(self, path: str):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self._sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"], sess_options=opts)
        self._inputs = [i.name for i in self._sess.get_inputs()]
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._ctx = np.zeros((1, _CONTEXT), dtype=np.float32)

    def __call__(self, frame_f32: np.ndarray) -> float:
        x = frame_f32.reshape(1, -1).astype(np.float32)
        inp = np.concatenate([self._ctx, x], axis=1)
        self._ctx = x[:, -_CONTEXT:]
        if "h" in self._inputs:
            out, self._h, self._c = self._sess.run(None, {"input": inp, "h": self._h, "c": self._c})
        else:   # v5 interface: input, state, sr
            feeds = {"input": inp, "state": self._state}
            if "sr" in self._inputs:
                feeds["sr"] = np.array(SR, dtype=np.int64)
            out, self._state = self._sess.run(None, feeds)
        return float(np.asarray(out).reshape(-1)[-1])


class EnergyVAD:
    """Adaptive loudness gate: speech is well above the room's own noise."""

    def __init__(self):
        self._floor = -60.0

    def reset(self) -> None:
        pass

    def __call__(self, frame_f32: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(frame_f32 * frame_f32)) + 1e-9)
        db = 20.0 * np.log10(rms)
        # The floor follows quiet quickly and loud slowly.
        if db < self._floor:
            self._floor = 0.7 * self._floor + 0.3 * db
        else:
            self._floor = 0.998 * self._floor + 0.002 * db
        margin = db - max(self._floor, -70.0)
        if db < -48.0:
            return 0.0
        return float(min(1.0, max(0.0, (margin - 6.0) / 12.0)))


def make_detector():
    path = _silero_path()
    if path:
        try:
            det = SileroVAD(path)
            det(np.zeros(FRAME, dtype=np.float32))
            return det, "silero"
        except Exception as e:
            print(f"[VAD] Silero unavailable ({e}) — using the energy gate")
    return EnergyVAD(), "energy"


class Segmenter:
    """Feed 16 kHz int16 audio; get whole utterances back.

    on_utterance(samples_int16) is called from the feeding thread; keep it cheap
    (push to a queue). on_start() fires when speech begins — used to show that
    the assistant is hearing you and to decide barge-in."""

    def __init__(self, on_utterance: Callable[[np.ndarray], None],
                 on_start: Callable[[], None] | None = None,
                 threshold: float = 0.5, end_silence_ms: int = 700,
                 min_speech_ms: int = 250, max_utterance_s: float = 30.0,
                 preroll_ms: int = 320, detector=None):
        self._det, self.kind = (detector, "custom") if detector is not None else make_detector()
        self._on_utt = on_utterance
        self._on_start = on_start
        self.threshold = threshold
        self._off = max(0.15, threshold - 0.15)
        self.end_frames = max(3, int(end_silence_ms / 32))
        self._min_frames = max(2, int(min_speech_ms / 32))
        self._max_frames = int(max_utterance_s * 1000 / 32)
        self._pre = collections.deque(maxlen=max(1, int(preroll_ms / 32)))
        self._pending = np.zeros(0, dtype=np.int16)
        self._lock = threading.Lock()
        self.reset()

    def set_end_silence(self, ms: int) -> None:
        self.end_frames = max(3, int(ms / 32))

    def reset(self) -> None:
        with getattr(self, "_lock", threading.Lock()):
            self._speech: list[np.ndarray] = []
            self._in_speech = False
            self._voiced = 0
            self._silent = 0
            self._run = 0
            self._pre.clear()
            try:
                self._det.reset()
            except Exception:
                pass
        self.last_prob = 0.0
        self.last_voice_time = 0.0

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def feed(self, pcm_int16) -> None:
        x = np.asarray(pcm_int16, dtype=np.int16).reshape(-1)
        with self._lock:
            buf = np.concatenate([self._pending, x]) if self._pending.size else x
            n = (buf.size // FRAME) * FRAME
            self._pending = buf[n:].copy()
            for i in range(0, n, FRAME):
                self._frame(buf[i:i + FRAME])

    def _frame(self, fr: np.ndarray) -> None:
        f = fr.astype(np.float32) / 32768.0
        try:
            p = self._det(f)
        except Exception:
            p = 0.0
        self.last_prob = p
        if p >= self.threshold:
            self.last_voice_time = time.monotonic()
        if not self._in_speech:
            self._pre.append(fr.copy())
            self._run = self._run + 1 if p >= self.threshold else 0
            if self._run >= 2:
                self._in_speech = True
                self._speech = list(self._pre)
                self._pre.clear()
                self._voiced = self._run
                self._silent = 0
                if self._on_start:
                    try:
                        self._on_start()
                    except Exception:
                        pass
            return
        self._speech.append(fr.copy())
        if p >= self._off:
            self._voiced += 1
            self._silent = 0
        else:
            self._silent += 1
        if self._silent >= self.end_frames or len(self._speech) >= self._max_frames:
            self._finish()

    def _finish(self) -> None:
        frames, voiced = self._speech, self._voiced
        self._speech, self._in_speech, self._voiced, self._silent, self._run = [], False, 0, 0, 0
        # Trim most of the trailing silence, keep a little for natural endings.
        keep_tail = 6
        if self._silent >= keep_tail and len(frames) > keep_tail:
            frames = frames[: len(frames) - (self.end_frames - keep_tail)]
        if voiced < self._min_frames or not frames:
            return
        audio = np.concatenate(frames)
        try:
            self._on_utt(audio)
        except Exception as e:
            print(f"[VAD] utterance handler error: {e}")

    def flush(self) -> None:
        with self._lock:
            if self._in_speech:
                self._finish()


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Linear resampling — plenty for speech between 16/22/24/44/48 kHz."""
    if src == dst or x.size == 0:
        return x
    n = int(round(x.size * dst / src))
    if n <= 0:
        return np.zeros(0, dtype=x.dtype)
    xp = np.linspace(0.0, 1.0, num=x.size, endpoint=False)
    fp = x.astype(np.float32)
    out = np.interp(np.linspace(0.0, 1.0, num=n, endpoint=False), xp, fp)
    if x.dtype == np.int16:
        return np.clip(out, -32768, 32767).astype(np.int16)
    return out.astype(x.dtype)
