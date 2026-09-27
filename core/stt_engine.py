"""
Speech-to-text for the local voice engine.

    whisper   faster-whisper on this machine. Private and offline once the model
              is downloaded (tiny 75 MB … small 480 MB … large-v3-turbo 1.6 GB).
              Runs on the CPU by default so the GPU stays free for the LLM.
    openai    Any OpenAI-compatible /audio/transcriptions endpoint — Groq's free
              whisper-large-v3-turbo is the fastest option there is, OpenAI's
              whisper-1 / gpt-4o-mini-transcribe work the same way.

Every engine takes 16 kHz int16 samples and returns (text, language_code).
"""
from __future__ import annotations

import io
import os
import re
import threading
import wave
from typing import Callable

import numpy as np

from core import brain_config

# Whisper invents these on silence, breathing and keyboard noise — lines from
# the subtitles it was trained on. Dropped only when they are the WHOLE result.
_HALLUCINATIONS = {
    "thank you", "thank you.", "thanks for watching", "thanks for watching!",
    "thank you for watching", "thank you for watching.", "thank you so much for watching",
    "please subscribe", "subscribe", "bye", "bye.", "you", "okay", ".", "..", "...",
    "the end", "so", "hmm", "uh", "um", "ah", "oh", "mm", "huh",
    "[music]", "(music)", "[blank_audio]", "[silence]", "(silence)", "♪", "♪♪",
    "[applause]", "(applause)", "[laughter]", "(laughs)", "(upbeat music)",
}
_CREDITS = re.compile(r"(subtitles? by|captions? by|amara\.org|transcribed by|"
                      r"www\.|\.com$|translated by)", re.I)


def is_hallucination(text: str) -> bool:
    t = " ".join((text or "").lower().split()).strip(" -—")
    if not t:
        return True
    if t in _HALLUCINATIONS or t.rstrip(".!?") in _HALLUCINATIONS:
        return True
    if _CREDITS.search(t) and len(t) < 80:
        return True
    words = t.split()
    # "you you you you" / "the the the"
    if len(words) >= 4 and len(set(words)) == 1:
        return True
    return not re.search(r"\w", t)


def _wav_bytes(samples: np.ndarray, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.asarray(samples, dtype=np.int16).tobytes())
    return buf.getvalue()


class WhisperSTT:
    name = "whisper"

    def __init__(self, model: str = "small", device: str = "cpu", language: str = "auto",
                 prompt_hint: str = "", log: Callable[[str], None] = print):
        self._model_name = model or "small"
        self._device = (device or "cpu").lower()
        self._lang = None if not language or language == "auto" else language
        self._hint = prompt_hint
        self._log = log
        self._model = None
        self._lock = threading.Lock()
        self.device_used = "cpu"

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            from faster_whisper import WhisperModel
            root = brain_config.MODELS_DIR / "whisper"
            root.mkdir(parents=True, exist_ok=True)
            threads = max(2, min(8, (os.cpu_count() or 4) - 1))
            tries = []
            if self._device in ("cuda", "auto"):
                tries += [("cuda", "float16"), ("cuda", "int8_float16")]
            tries.append(("cpu", "int8"))
            last = None
            for dev, ct in tries:
                try:
                    self._log(f"SYS: Loading speech recognition ({self._model_name}, {dev})"
                              " — the first time this downloads the model…")
                    self._model = WhisperModel(self._model_name, device=dev, compute_type=ct,
                                               download_root=str(root), cpu_threads=threads)
                    self.device_used = dev
                    # A first pass compiles kernels; do it now, not on your first sentence.
                    self._model.transcribe(np.zeros(16000, dtype=np.float32), beam_size=1,
                                           language=self._lang or "en")
                    self._log(f"SYS: Speech recognition ready ({self._model_name} on {dev}).")
                    return
                except Exception as e:
                    last = e
                    self._model = None
            raise RuntimeError(f"Whisper could not be loaded: {last}")

    def transcribe(self, samples: np.ndarray) -> tuple[str, str]:
        if self._model is None:
            self.load()
        audio = np.asarray(samples, dtype=np.float32) / 32768.0
        kw = dict(language=self._lang, beam_size=1, best_of=1, vad_filter=False,
                  condition_on_previous_text=False, without_timestamps=True,
                  temperature=0.0)
        if self._hint:
            kw["initial_prompt"] = self._hint
        segments, info = self._model.transcribe(audio, **kw)
        parts = []
        for seg in segments:
            # A segment the model itself thinks is not speech is usually noise.
            if getattr(seg, "no_speech_prob", 0) > 0.75 and getattr(seg, "avg_logprob", 0) < -0.9:
                continue
            parts.append(seg.text)
        text = " ".join(p.strip() for p in parts).strip()
        if self._hint and text.strip().rstrip(".,") == self._hint.strip().rstrip(".,"):
            text = ""
        return text, str(getattr(info, "language", "") or "")


class OpenAISTT:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, language: str = "auto",
                 prompt_hint: str = ""):
        self._url = (base_url or "https://api.groq.com/openai/v1").rstrip("/") + "/audio/transcriptions"
        self._key = api_key
        self._model = model or "whisper-large-v3-turbo"
        self._lang = None if not language or language == "auto" else language
        self._hint = prompt_hint

    def load(self) -> None:
        if not self._key:
            raise RuntimeError("The transcription API needs a key (⚙ → AI BRAIN → Speech).")

    def transcribe(self, samples: np.ndarray) -> tuple[str, str]:
        import requests
        data = {"model": self._model, "response_format": "verbose_json", "temperature": "0"}
        if self._lang:
            data["language"] = self._lang
        if self._hint:
            data["prompt"] = self._hint
        files = {"file": ("speech.wav", _wav_bytes(samples), "audio/wav")}
        r = requests.post(self._url, headers={"Authorization": f"Bearer {self._key}"},
                          data=data, files=files, timeout=30)
        if r.status_code == 400 and "verbose_json" in r.text:
            data["response_format"] = "json"
            files = {"file": ("speech.wav", _wav_bytes(samples), "audio/wav")}
            r = requests.post(self._url, headers={"Authorization": f"Bearer {self._key}"},
                              data=data, files=files, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"transcription HTTP {r.status_code}: {r.text[:200]}")
        js = r.json()
        return str(js.get("text", "")).strip(), str(js.get("language", "") or "")


_LANG_NAMES = {"english": "en", "hindi": "hi", "spanish": "es", "french": "fr", "german": "de",
               "turkish": "tr", "arabic": "ar", "russian": "ru", "japanese": "ja",
               "chinese": "zh", "portuguese": "pt", "italian": "it", "bengali": "bn",
               "urdu": "ur", "tamil": "ta", "telugu": "te", "marathi": "mr"}


def normalize_lang(code: str) -> str:
    c = (code or "").strip().lower()
    return _LANG_NAMES.get(c, c[:2])


def create_stt(log: Callable[[str], None] = print):
    v = brain_config.get_voice_cfg()
    hint = f"{brain_config.assistant_name().title()}."
    if v.get("stt_engine") == "openai":
        return OpenAISTT(v.get("stt_base_url", ""), v.get("stt_api_key", ""),
                         v.get("stt_api_model", ""), v.get("stt_language", "auto"), hint)
    return WhisperSTT(v.get("stt_model", "small"), v.get("stt_device", "cpu"),
                      v.get("stt_language", "auto"), hint, log=log)
