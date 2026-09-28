"""
Text-to-speech for the local voice engine.

Every engine returns 24 kHz mono int16 — the format the playback loop, the
lip-sync and the echo guard in main.py already expect — so any of them drops
into the same path the Gemini Live voice uses, avatar mouth included.

    edge        Microsoft Edge neural voices. Free, no key, very natural, 300+
                voices in 70+ languages (Indian English and Hindi included).
                Needs internet.
    sapi        The voices built into Windows. Fully offline, zero download.
                The automatic fallback whenever another engine fails.
    piper       Offline neural voices (~60 MB each), fast on any CPU.
    kokoro      Offline neural voices (~330 MB), the most natural offline option.
    elevenlabs  Cloud, API key, top quality.
    openai      OpenAI-compatible /audio/speech (OpenAI, or a local server).

Language: with "edge" the voice follows the language being spoken — a reply in
Hindi is read by a Hindi voice even if the chosen voice is English — unless the
chosen voice is one of the "Multilingual" voices, which speak everything.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import time
from typing import Callable, Iterator

import numpy as np

from core import brain_config
from core.vad import resample

SR = 24000

EDGE_VOICES = [
    ("en-GB-RyanNeural", "British male — the classic JARVIS"),
    ("en-GB-ThomasNeural", "British male"),
    ("en-GB-SoniaNeural", "British female"),
    ("en-IN-PrabhatNeural", "Indian English male"),
    ("en-IN-NeerjaNeural", "Indian English female"),
    ("hi-IN-MadhurNeural", "Hindi male"),
    ("hi-IN-SwaraNeural", "Hindi female"),
    ("en-US-AndrewMultilingualNeural", "US male — speaks every language"),
    ("en-US-BrianMultilingualNeural", "US male — speaks every language"),
    ("en-US-AvaMultilingualNeural", "US female — speaks every language"),
    ("en-US-EmmaMultilingualNeural", "US female — speaks every language"),
    ("en-US-GuyNeural", "US male"),
    ("en-US-JennyNeural", "US female"),
    ("en-AU-WilliamNeural", "Australian male"),
]

_FEMALE = ("sonia", "neerja", "swara", "ava", "emma", "jenny", "aria", "libby", "maisie",
           "natasha", "michelle", "clara", "denise", "katja", "elvira", "emel", "zira", "hazel",
           "heera", "kalpana")

# (male, female) per language — used when the reply's language differs from the voice.
_LANG_VOICES = {
    "hi": ("hi-IN-MadhurNeural", "hi-IN-SwaraNeural"),
    "bn": ("bn-IN-BashkarNeural", "bn-IN-TanishaaNeural"),
    "ta": ("ta-IN-ValluvarNeural", "ta-IN-PallaviNeural"),
    "te": ("te-IN-MohanNeural", "te-IN-ShrutiNeural"),
    "mr": ("mr-IN-ManoharNeural", "mr-IN-AarohiNeural"),
    "gu": ("gu-IN-NiranjanNeural", "gu-IN-DhwaniNeural"),
    "kn": ("kn-IN-GaganNeural", "kn-IN-SapnaNeural"),
    "ml": ("ml-IN-MidhunNeural", "ml-IN-SobhanaNeural"),
    "ur": ("ur-PK-AsadNeural", "ur-PK-UzmaNeural"),
    "ar": ("ar-SA-HamedNeural", "ar-SA-ZariyahNeural"),
    "ru": ("ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"),
    "uk": ("uk-UA-OstapNeural", "uk-UA-PolinaNeural"),
    "ja": ("ja-JP-KeitaNeural", "ja-JP-NanamiNeural"),
    "zh": ("zh-CN-YunxiNeural", "zh-CN-XiaoxiaoNeural"),
    "ko": ("ko-KR-InJoonNeural", "ko-KR-SunHiNeural"),
    "el": ("el-GR-NestorasNeural", "el-GR-AthinaNeural"),
    "th": ("th-TH-NiwatNeural", "th-TH-PremwadeeNeural"),
    "he": ("he-IL-AvriNeural", "he-IL-HilaNeural"),
    "es": ("es-ES-AlvaroNeural", "es-ES-ElviraNeural"),
    "fr": ("fr-FR-HenriNeural", "fr-FR-DeniseNeural"),
    "de": ("de-DE-ConradNeural", "de-DE-KatjaNeural"),
    "it": ("it-IT-DiegoNeural", "it-IT-ElsaNeural"),
    "pt": ("pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"),
    "tr": ("tr-TR-AhmetNeural", "tr-TR-EmelNeural"),
    "nl": ("nl-NL-MaartenNeural", "nl-NL-ColetteNeural"),
    "pl": ("pl-PL-MarekNeural", "pl-PL-ZofiaNeural"),
    "id": ("id-ID-ArdiNeural", "id-ID-GadisNeural"),
    "vi": ("vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"),
    "fa": ("fa-IR-FaridNeural", "fa-IR-DilaraNeural"),
}

_SCRIPTS = [
    ("hi", r"[ऀ-ॿ]"), ("bn", r"[ঀ-৿]"), ("ta", r"[஀-௿]"),
    ("te", r"[ఀ-౿]"), ("gu", r"[઀-૿]"), ("kn", r"[ಀ-೿]"),
    ("ml", r"[ഀ-ൿ]"), ("ar", r"[؀-ۿ]"), ("ru", r"[Ѐ-ӿ]"),
    ("ja", r"[぀-ヿ]"), ("ko", r"[가-힯]"), ("zh", r"[一-鿿]"),
    ("el", r"[Ͱ-Ͽ]"), ("th", r"[฀-๿]"), ("he", r"[֐-׿]"),
]


def detect_script_lang(text: str) -> str:
    for lang, pat in _SCRIPTS:
        if len(re.findall(pat, text or "")) >= 2:
            return lang
    return ""


def _to_int16(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x)
    if x.dtype == np.int16:
        return x
    return (np.clip(x.astype(np.float32), -1.0, 1.0) * 32767.0).astype(np.int16)


class _Engine:
    name = "base"

    def load(self) -> None:
        pass

    def synth(self, text: str, lang: str = "") -> Iterator[np.ndarray]:
        raise NotImplementedError


class EdgeTTS(_Engine):
    name = "edge"

    def __init__(self, voice: str, rate: int = 0, follow_language: bool = True):
        self.voice = voice or "en-GB-RyanNeural"
        self.rate = f"{'+' if rate >= 0 else ''}{int(rate)}%"
        self.follow = follow_language and "multilingual" not in self.voice.lower()
        self._female = any(n in self.voice.lower() for n in _FEMALE)
        self._voice_lang = self.voice.split("-")[0].lower()

    def load(self) -> None:
        import edge_tts  # noqa: F401
        import miniaudio  # noqa: F401

    def _voice_for(self, text: str, lang: str) -> str:
        if not self.follow:
            return self.voice
        want = detect_script_lang(text) or (lang or "").lower()[:2]
        if not want or want == self._voice_lang or want == "en":
            return self.voice
        pair = _LANG_VOICES.get(want)
        if not pair:
            return self.voice
        return pair[1] if self._female else pair[0]

    def synth(self, text: str, lang: str = "") -> Iterator[np.ndarray]:
        import edge_tts
        import miniaudio

        voice = self._voice_for(text, lang)

        async def run() -> bytes:
            comm = edge_tts.Communicate(text, voice, rate=self.rate)
            buf = bytearray()
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        mp3 = asyncio.run(asyncio.wait_for(run(), timeout=25))
        if not mp3:
            raise RuntimeError("Edge TTS returned no audio")
        dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16,
                               nchannels=1, sample_rate=SR)
        yield np.frombuffer(dec.samples, dtype=np.int16).copy()


class SapiTTS(_Engine):
    """Windows' own voices through SAPI 5, rendered straight to memory."""
    name = "sapi"

    def __init__(self, voice_hint: str = "", rate: int = 0):
        self.hint = (voice_hint or "").lower()
        self.rate = max(-10, min(10, int(round(rate / 10))))
        self._local = threading.local()

    def load(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows voices are only available on Windows")
        import win32com.client  # noqa: F401

    def _voice(self):
        v = getattr(self._local, "voice", None)
        if v is None:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            v = win32com.client.Dispatch("SAPI.SpVoice")
            if self.hint:
                try:
                    for tok in v.GetVoices():
                        if self.hint in tok.GetDescription().lower():
                            v.Voice = tok
                            break
                except Exception:
                    pass
            v.Rate = self.rate
            self._local.voice = v
        return v

    def synth(self, text: str, lang: str = "") -> Iterator[np.ndarray]:
        import tempfile
        import wave
        import win32com.client
        voice = self._voice()
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_tts_")
        os.close(fd)
        try:
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            try:
                fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
                fmt.Type = 26                     # SAFT24kHz16BitMono
                stream.Format = fmt
            except Exception:
                pass                              # the default format is read back below
            stream.Open(path, 3, False)           # SSFMCreateForWrite
            voice.AudioOutputStream = stream
            voice.Speak(text, 0)                  # synchronous
            stream.Close()
            with wave.open(path, "rb") as w:
                sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
                raw = w.readframes(w.getnframes())
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if width == 2:
            pcm = np.frombuffer(raw, dtype=np.int16)
        elif width == 1:
            pcm = ((np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) << 8).astype(np.int16)
        else:
            raise RuntimeError(f"unexpected SAPI sample width {width}")
        if ch > 1:
            pcm = pcm.reshape(-1, ch).mean(axis=1).astype(np.int16)
        yield resample(pcm.copy(), sr, SR)

    @staticmethod
    def list_voices() -> list[str]:
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            v = win32com.client.Dispatch("SAPI.SpVoice")
            return [t.GetDescription() for t in v.GetVoices()]
        except Exception:
            return []


class PiperTTS(_Engine):
    name = "piper"
    _URL = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "{family}/{code}/{name}/{quality}/{voice}{ext}?download=true")

    def __init__(self, voice: str, rate: int = 0, log: Callable[[str], None] = print):
        self.voice_name = voice or "en_GB-alan-medium"
        self.length_scale = max(0.5, min(2.0, 1.0 - rate / 100.0))
        self._log = log
        self._voice = None

    def load(self) -> None:
        if self._voice is not None:
            return
        from core.downloader import fetch
        from piper import PiperVoice
        code, name, quality = self.voice_name.split("-", 2)
        family = code.split("_")[0]
        d = brain_config.MODELS_DIR / "piper"
        onnx = d / f"{self.voice_name}.onnx"
        cfg = d / f"{self.voice_name}.onnx.json"
        fmt = dict(family=family, code=code, name=name, quality=quality, voice=self.voice_name)
        fetch([self._URL.format(ext=".onnx", **fmt)], onnx, 1_000_000, progress=self._log)
        fetch([self._URL.format(ext=".onnx.json", **fmt)], cfg, 100, progress=self._log)
        self._voice = PiperVoice.load(str(onnx), config_path=str(cfg))

    def synth(self, text: str, lang: str = "") -> Iterator[np.ndarray]:
        from piper.config import SynthesisConfig
        self.load()
        conf = SynthesisConfig(length_scale=self.length_scale)
        for chunk in self._voice.synthesize(text, syn_config=conf):
            audio = _to_int16(chunk.audio_float_array)
            yield resample(audio, chunk.sample_rate, SR)


class KokoroTTS(_Engine):
    name = "kokoro"
    _BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
    _LANG = {"a": "en-us", "b": "en-gb", "h": "hi", "e": "es", "f": "fr-fr", "i": "it",
             "p": "pt-br", "j": "ja", "z": "cmn"}

    def __init__(self, voice: str, rate: int = 0, log: Callable[[str], None] = print):
        self.voice = voice or "bm_george"
        self.speed = max(0.5, min(2.0, 1.0 + rate / 100.0))
        self._log = log
        self._k = None

    def load(self) -> None:
        if self._k is not None:
            return
        from core.downloader import fetch
        from kokoro_onnx import Kokoro
        d = brain_config.MODELS_DIR / "kokoro"
        model = fetch([self._BASE + "kokoro-v1.0.onnx"], d / "kokoro-v1.0.onnx", 50_000_000,
                      progress=self._log, timeout=300)
        voices = fetch([self._BASE + "voices-v1.0.bin"], d / "voices-v1.0.bin", 1_000_000,
                       progress=self._log, timeout=300)
        self._k = Kokoro(str(model), str(voices))

    def synth(self, text: str, lang: str = "") -> Iterator[np.ndarray]:
        self.load()
        lang_code = self._LANG.get(self.voice[:1], "en-us")
        samples, sr = self._k.create(text, voice=self.voice, speed=self.speed, lang=lang_code)
        yield resample(_to_int16(samples), sr, SR)


class ElevenLabsTTS(_Engine):
    name = "elevenlabs"

    def __init__(self, key: str, voice_id: str):
        self.key, self.voice_id = key, voice_id or "pNInz6obpgDQGcFmaJgB"

    def load(self) -> None:
        if not self.key:
            raise RuntimeError("ElevenLabs needs an API key")

    def synth(self, text: str, lang: str = "") -> Iterator[np.ndarray]:
        import requests
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?output_format=pcm_24000",
            headers={"xi-api-key": self.key, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_flash_v2_5"}, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:160]}")
        yield np.frombuffer(r.content[: len(r.content) // 2 * 2], dtype=np.int16).copy()


class OpenAITTS(_Engine):
    name = "openai"

    def __init__(self, base_url: str, key: str, model: str, voice: str):
        self.url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/audio/speech"
        self.key, self.model, self.voice = key, model or "gpt-4o-mini-tts", voice or "onyx"

    def synth(self, text: str, lang: str = "") -> Iterator[np.ndarray]:
        import requests
        h = {"Content-Type": "application/json"}
        if self.key:
            h["Authorization"] = f"Bearer {self.key}"
        r = requests.post(self.url, headers=h, timeout=40, json={
            "model": self.model, "voice": self.voice, "input": text, "response_format": "pcm"})
        if r.status_code >= 400:
            raise RuntimeError(f"speech API HTTP {r.status_code}: {r.text[:160]}")
        yield np.frombuffer(r.content[: len(r.content) // 2 * 2], dtype=np.int16).copy()


class TTSChain:
    """The chosen engine, with the offline Windows voice behind it.

    A failing engine (no internet for Edge, a missing model) is rested for a
    minute rather than retried on every sentence, and the fallback speaks in the
    meantime — the assistant never goes mute because a cloud voice is down."""

    def __init__(self, primary: _Engine, fallback: _Engine | None, log: Callable[[str], None]):
        self.primary, self.fallback, self._log = primary, fallback, log
        self._rest_until = 0.0
        self._warned = False

    @property
    def name(self) -> str:
        return self.primary.name

    def load(self) -> None:
        try:
            self.primary.load()
        except Exception as e:
            self._log(f"ERR: Voice '{self.primary.name}' unavailable — {e}")
            self._rest_until = time.monotonic() + 60
        if self.fallback:
            try:
                self.fallback.load()
            except Exception:
                self.fallback = None

    def synth(self, text: str, lang: str = "") -> Iterator[np.ndarray]:
        if time.monotonic() >= self._rest_until:
            try:
                chunks = list(self.primary.synth(text, lang))
                if chunks:
                    self._warned = False
                    yield from chunks
                    return
            except Exception as e:
                self._rest_until = time.monotonic() + 60
                if not self._warned:
                    self._warned = True
                    self._log(f"ERR: Voice '{self.primary.name}' failed ({str(e)[:120]}) — "
                              + ("using the Windows voice for now." if self.fallback else "no fallback voice."))
        if self.fallback is not None:
            yield from self.fallback.synth(text, lang)
            return
        raise RuntimeError(f"no working voice ({self.primary.name})")


def create_tts(log: Callable[[str], None] = print) -> TTSChain:
    v = brain_config.get_voice_cfg()
    eng = str(v.get("tts_engine") or "edge").lower()
    rate = int(v.get("tts_rate") or 0)
    if eng == "sapi":
        primary: _Engine = SapiTTS(v.get("tts_voice", "") if "Neural" not in str(v.get("tts_voice")) else "", rate)
    elif eng == "piper":
        primary = PiperTTS(v.get("piper_voice", ""), rate, log)
    elif eng == "kokoro":
        primary = KokoroTTS(v.get("kokoro_voice", ""), rate, log)
    elif eng == "elevenlabs":
        primary = ElevenLabsTTS(v.get("elevenlabs_api_key", ""), v.get("elevenlabs_voice_id", ""))
    elif eng == "openai":
        b = brain_config.get_brain()
        key = v.get("openai_tts_key") or (b.get("api_key") if b.get("provider") == "openai" else "")
        primary = OpenAITTS(v.get("openai_tts_url", "") or "https://api.openai.com/v1", key,
                            v.get("openai_tts_model", ""), v.get("openai_tts_voice", ""))
    else:
        primary = EdgeTTS(v.get("tts_voice", ""), rate)
    fallback = SapiTTS("", rate) if (sys.platform == "win32" and primary.name != "sapi") else None
    return TTSChain(primary, fallback, log)
