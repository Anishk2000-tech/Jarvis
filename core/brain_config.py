"""
Which brain the assistant runs on, and how it hears and speaks.

Everything lives in config/api_keys.json next to the settings that were already
there, under three keys:

    "brain":  provider, endpoint, key and the models for each role
    "voice":  speech-to-text and text-to-speech for the local engine
    "senses": always-on listening, barge-in, voice confirmation, face ID

Providers
---------
    gemini_live   Google's realtime voice model (the original engine).
                  Needs a Gemini key; audio goes to Google.
    ollama        Local models through Ollama (http://localhost:11434).
    lmstudio      Local models through LM Studio's server (port 1234).
    openai        Any OpenAI-compatible API: OpenAI, Groq, OpenRouter,
                  DeepSeek, Together, Mistral, xAI, vLLM, llama.cpp, Jan…
    anthropic     Claude through the Anthropic Messages API.
    gemini        Gemini text models through Google's OpenAI-compatible API
                  (the local voice pipeline, a Gemini brain).

Every provider except gemini_live runs on the local voice engine: the
microphone is transcribed on this machine, the text goes to the brain, and the
reply is spoken by the chosen TTS voice.

Nothing here raises. A missing or corrupt config yields the defaults.
"""
from __future__ import annotations

import copy
import json
import sys
import threading
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
CONFIG_FILE = BASE_DIR / "config" / "api_keys.json"
MODELS_DIR = BASE_DIR / "models"

_lock = threading.RLock()

PROVIDERS = ("gemini_live", "ollama", "lmstudio", "openai", "anthropic", "gemini")
LOCAL_PROVIDERS = ("ollama", "lmstudio")

PROVIDER_LABELS = {
    "gemini_live": "Gemini Live (cloud, realtime voice)",
    "ollama":      "Ollama (local, free, private)",
    "lmstudio":    "LM Studio (local, free, private)",
    "openai":      "OpenAI-compatible API (OpenAI, Groq, OpenRouter…)",
    "anthropic":   "Anthropic Claude (cloud)",
    "gemini":      "Gemini text API (cloud, local voice pipeline)",
}

DEFAULT_URLS = {
    "ollama":    "http://localhost:11434",
    "lmstudio":  "http://localhost:1234/v1",
    "openai":    "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini":    "https://generativelanguage.googleapis.com/v1beta/openai",
}

# Handy endpoints for the OpenAI-compatible provider, shown in the settings UI.
OPENAI_COMPAT_PRESETS = {
    "OpenAI":     "https://api.openai.com/v1",
    "Groq":       "https://api.groq.com/openai/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "DeepSeek":   "https://api.deepseek.com/v1",
    "Mistral":    "https://api.mistral.ai/v1",
    "Together":   "https://api.together.xyz/v1",
    "xAI":        "https://api.x.ai/v1",
    "Jan (local)":        "http://localhost:1337/v1",
    "llama.cpp (local)":  "http://localhost:8080/v1",
}

DEFAULT_MODELS = {
    "ollama":    "qwen2.5:7b",
    "lmstudio":  "",                 # whatever is loaded
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "gemini":    "gemini-2.5-flash",
}

# Recommendations for a laptop with 32 GB RAM and a 4 GB GPU — the machine this
# fork was built for — and a sensible spread for others. Sizes are the default
# Q4 downloads. Anything that does not fit in VRAM still runs: Ollama splits the
# layers between the GPU and system RAM, it is just slower.
OLLAMA_RECOMMENDED = [
    # (model, role, approx size GB, note)
    ("qwen2.5:3b",        "fast",   1.9, "Fits fully in 4 GB VRAM — the snappiest voice replies"),
    ("llama3.2:3b",       "fast",   2.0, "Fits in 4 GB VRAM — good English conversation"),
    ("qwen3:4b",          "fast",   2.6, "Fits in 4 GB VRAM — strong tool use for its size"),
    ("qwen2.5:7b",        "smart",  4.7, "Best all-rounder for tools; GPU+RAM split on 4 GB cards"),
    ("qwen3:8b",          "smart",  5.2, "Stronger reasoning; GPU+RAM split on 4 GB cards"),
    ("llama3.1:8b",       "smart",  4.9, "Reliable tool calling; GPU+RAM split"),
    ("qwen2.5vl:3b",      "vision", 3.2, "Sees the screen and camera; fits 4 GB VRAM"),
    ("gemma3:4b",         "vision", 3.3, "Vision + chat; fits 4 GB VRAM"),
    ("moondream",         "vision", 1.7, "Tiny, fast image descriptions"),
    ("qwen2.5:14b",       "heavy",  9.0, "Runs from your 32 GB RAM — slow but clever, for agent tasks"),
    ("qwen2.5-coder:7b",  "code",   4.7, "Code writing and fixing"),
]

_DEFAULT_BRAIN = {
    "provider": "",            # "" until the setup screen has been completed
    "base_url": "",
    "api_key": "",
    "model": "",               # conversation model
    "smart_model": "",         # long tasks: computer agent, planning, code ("" = model)
    "vision_model": "",        # screenshots / camera ("" = model if it can see)
    "fast_model": "",          # one-line classifications ("" = model)
    "temperature": 0.6,
    "num_ctx": 16384,          # Ollama context window — its own default is far too small
    "tool_profile": "auto",    # auto | full | lean  (lean hides niche tools for small models)
    "keep_alive": "30m",
    "tool_mode": "auto",       # auto | native | prompted
    "compact_tools": True,     # shorter tool descriptions for small models
    "max_steps": 10,           # tool rounds per request before stopping
    "max_reply_tokens": 700,
    "disabled_tools": [],
    "request_timeout": 180,
}

_DEFAULT_VOICE = {
    "stt_engine": "whisper",       # whisper (local) | openai (Groq/OpenAI API)
    "stt_model": "small",          # tiny | base | small | medium | large-v3-turbo | *.en
    "stt_language": "auto",        # auto, or a code such as en / hi
    "stt_device": "cpu",           # cpu | cuda | auto — cpu leaves the GPU to the LLM
    "stt_base_url": "https://api.groq.com/openai/v1",
    "stt_api_key": "",
    "stt_api_model": "whisper-large-v3-turbo",
    "tts_engine": "edge",          # edge | sapi | piper | kokoro | elevenlabs | openai
    "tts_voice": "en-GB-RyanNeural",
    "tts_rate": 0,                 # percent, -50..+50
    "piper_voice": "en_GB-alan-medium",
    "kokoro_voice": "bm_george",
    "elevenlabs_api_key": "",
    "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
    "openai_tts_model": "gpt-4o-mini-tts",
    "openai_tts_voice": "onyx",
    "end_silence_ms": 700,         # pause that ends your sentence
    "vad_threshold": 0.5,
}

_DEFAULT_SENSES = {
    "listen_mode": "active",       # active | ambient
    "barge_in": True,              # talk over the assistant to interrupt it
    "voice_confirm": True,         # say "confirm" instead of pressing the button
    "journal": True,               # keep a local transcript of what was heard
    "journal_days": 30,
    "follow_up_seconds": 20,       # ambient: keep listening after a reply
    "name_aliases": [],            # extra spellings of the assistant's name
    "smart_interject": False,      # ambient: let the model decide to join in
    "face_presence": False,        # background face recognition
    "owner_only": False,           # obey only while the owner's face is seen
    "greet_on_arrival": True,
    "lock_on_leave": False,
    "alert_unknown_faces": False,
}


def _read() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONFIG_FILE)


def _section(name: str, defaults: dict) -> dict:
    raw = _read().get(name)
    out = copy.deepcopy(defaults)
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[k] = v
    return out


def _save_section(name: str, updates: dict) -> None:
    with _lock:
        data = _read()
        cur = data.get(name)
        cur = dict(cur) if isinstance(cur, dict) else {}
        cur.update(updates or {})
        data[name] = cur
        _write(data)


# ── brain ────────────────────────────────────────────────────────────────────

def save_top(**fields) -> None:
    """Write top-level config keys (gemini_api_key, os_system…)."""
    with _lock:
        data = _read()
        data.update(fields)
        _write(data)


def get_brain() -> dict:
    b = _section("brain", _DEFAULT_BRAIN)
    p = str(b.get("provider") or "").strip().lower()
    if not p:
        # A config written by the original app has only a Gemini key: it was
        # running Gemini Live, and keeps doing so.
        if _read().get("gemini_api_key"):
            p = "gemini_live"
    if p == "lm_studio":
        p = "lmstudio"
    b["provider"] = p if p in PROVIDERS else ""
    if b["provider"] and b["provider"] != "gemini_live":
        if not str(b.get("base_url") or "").strip():
            b["base_url"] = DEFAULT_URLS.get(b["provider"], "")
        if not str(b.get("model") or "").strip():
            b["model"] = DEFAULT_MODELS.get(b["provider"], "")
    if b["provider"] == "gemini" and not b.get("api_key"):
        b["api_key"] = _read().get("gemini_api_key", "")
    try:
        b["num_ctx"] = max(4096, min(131072, int(b.get("num_ctx") or 16384)))
    except (TypeError, ValueError):
        b["num_ctx"] = 16384
    try:
        b["temperature"] = float(b.get("temperature", 0.6))
    except (TypeError, ValueError):
        b["temperature"] = 0.6
    try:
        b["max_steps"] = max(1, min(40, int(b.get("max_steps") or 10)))
    except (TypeError, ValueError):
        b["max_steps"] = 10
    if not isinstance(b.get("disabled_tools"), list):
        b["disabled_tools"] = []
    return b


def save_brain(updates: dict) -> None:
    _save_section("brain", updates)


# Hidden from small models by the "lean" tool profile: tools for one hobby or a
# rare job, whose descriptions cost context and add wrong choices. Any of them
# can still be reached on a bigger model, or with the profile set to "full".
LEAN_HIDDEN = ("flight_finder", "game_updater", "youtube_video", "dev_agent", "code_helper",
               "manage_monitor", "mcp_servers", "skill_manager", "desktop_control",
               "file_processor", "telegram_notify", "hardware_control", "email")


def detect_hardware() -> dict:
    """RAM, NVIDIA VRAM and CPU cores — for model recommendations."""
    out = {"ram_gb": 0.0, "vram_gb": 0.0, "gpu": "", "cores": 0}
    try:
        import psutil
        out["ram_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
        out["cores"] = psutil.cpu_count(logical=False) or psutil.cpu_count() or 0
    except Exception:
        pass
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        out["vram_gb"] = round(pynvml.nvmlDeviceGetMemoryInfo(h).total / 2**30, 1)
        name = pynvml.nvmlDeviceGetName(h)
        out["gpu"] = name.decode() if isinstance(name, bytes) else str(name)
    except Exception:
        pass
    return out


def recommend(hw: dict | None = None) -> dict:
    """Ollama models that suit this machine, with a sentence explaining why."""
    hw = hw or detect_hardware()
    ram, vram = hw.get("ram_gb") or 0, hw.get("vram_gb") or 0
    if vram >= 10:
        r = {"model": "qwen2.5:7b", "smart_model": "qwen2.5:14b", "vision_model": "qwen2.5vl:7b",
             "why": "Your GPU holds 7B models completely — fast and capable."}
    elif vram >= 6:
        r = {"model": "qwen2.5:7b", "smart_model": "qwen2.5:7b", "vision_model": "qwen2.5vl:3b",
             "why": "A 7B model fits your GPU: good tool use at conversational speed."}
    elif vram >= 3.5:
        r = {"model": "qwen2.5:7b", "smart_model": "qwen2.5:7b", "vision_model": "qwen2.5vl:3b",
             "why": (f"{vram:.0f} GB GPU + {ram:.0f} GB RAM: qwen2.5:7b splits between GPU and RAM — "
                     "reliable with tools, a few seconds per reply. For the fastest replies pick "
                     "qwen2.5:3b (runs fully on the GPU).")}
    elif ram >= 15:
        r = {"model": "qwen2.5:3b", "smart_model": "qwen2.5:7b", "vision_model": "moondream",
             "why": "No usable GPU: a 3B model keeps voice replies quick on the CPU; 7B for long tasks."}
    else:
        r = {"model": "qwen2.5:1.5b", "smart_model": "qwen2.5:3b", "vision_model": "moondream",
             "why": "Limited memory: small models only. A cloud brain (Groq, Gemini) will feel faster."}
    return r


def provider() -> str:
    return get_brain()["provider"]


def uses_local_engine() -> bool:
    """True for every provider that runs on the local STT → LLM → TTS pipeline."""
    p = provider()
    return bool(p) and p != "gemini_live"


def is_configured() -> bool:
    """Enough is set to start: a provider, and a key where one is needed."""
    data = _read()
    b = get_brain()
    p = b["provider"]
    if not p:
        return False
    if p == "gemini_live":
        return bool(data.get("gemini_api_key"))
    if p in ("openai", "anthropic", "gemini"):
        # Local OpenAI-compatible servers (llama.cpp, Jan, vLLM) need no key.
        url = str(b.get("base_url") or "")
        if p == "openai" and ("localhost" in url or "127.0.0.1" in url):
            return True
        return bool(b.get("api_key"))
    return True


def model_for(role: str = "chat") -> str:
    """The model name to use for a role: chat | smart | vision | fast."""
    b = get_brain()
    base = str(b.get("model") or "").strip()
    key = {"smart": "smart_model", "vision": "vision_model", "fast": "fast_model"}.get(role)
    if key:
        v = str(b.get(key) or "").strip()
        if v:
            return v
    return base


# ── voice ────────────────────────────────────────────────────────────────────

def get_voice_cfg() -> dict:
    v = _section("voice", _DEFAULT_VOICE)
    try:
        v["tts_rate"] = max(-50, min(50, int(v.get("tts_rate") or 0)))
    except (TypeError, ValueError):
        v["tts_rate"] = 0
    try:
        v["end_silence_ms"] = max(250, min(3000, int(v.get("end_silence_ms") or 700)))
    except (TypeError, ValueError):
        v["end_silence_ms"] = 700
    try:
        v["vad_threshold"] = max(0.1, min(0.95, float(v.get("vad_threshold") or 0.5)))
    except (TypeError, ValueError):
        v["vad_threshold"] = 0.5
    return v


def save_voice_cfg(updates: dict) -> None:
    _save_section("voice", updates)


# ── senses ───────────────────────────────────────────────────────────────────

def get_senses() -> dict:
    s = _section("senses", _DEFAULT_SENSES)
    if s.get("listen_mode") not in ("active", "ambient"):
        s["listen_mode"] = "active"
    if not isinstance(s.get("name_aliases"), list):
        s["name_aliases"] = []
    return s


def save_senses(updates: dict) -> None:
    _save_section("senses", updates)


def assistant_name() -> str:
    return (str(_read().get("assistant_name") or "JARVIS")).strip() or "JARVIS"


def user_name() -> str:
    return str(_read().get("user_name") or "").strip()


def gemini_key() -> str:
    return str(_read().get("gemini_api_key") or "").strip()


def ensure_os_field() -> None:
    """The original setup screen stored the OS; several actions still read it."""
    import platform
    with _lock:
        data = _read()
        if not data.get("os_system"):
            data["os_system"] = {"Windows": "windows", "Darwin": "mac"}.get(
                platform.system(), "linux")
            _write(data)
