"""
One client for every text brain the assistant can run on.

    Ollama          native /api/chat        (tools, images, NDJSON stream)
    LM Studio       OpenAI-compatible       (tools, images, SSE stream)
    OpenAI & co.    OpenAI-compatible       (OpenAI, Groq, OpenRouter, DeepSeek,
                                             Mistral, Together, xAI, llama.cpp,
                                             Jan, vLLM, Gemini's /openai path)
    Anthropic       /v1/messages            (tools, images, SSE stream)

Messages use one internal shape, close to OpenAI's, and each adapter converts:

    {"role": "system",    "content": str}
    {"role": "user",      "content": str, "images": [{"mime": str, "data": b64}]}
    {"role": "assistant", "content": str, "tool_calls": [ToolCall-as-dict, ...]}
    {"role": "tool",      "tool_call_id": str, "name": str, "content": str}

Tool calling has three modes:

    native     the provider's own tool API
    prompted   tools are described in the system prompt and the model answers
               with <tool_call>{...}</tool_call>. Works with ANY model — the
               only way many small local models can drive tools at all.
    auto       native, switching to prompted for a model the server says cannot
               take tools (Ollama answers "does not support tools").

Only `requests` is needed; no provider SDK is imported.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

import requests

from core import brain_config
from core import tool_schema


class LLMError(RuntimeError):
    pass


class ToolsUnsupported(LLMError):
    pass


class ProviderUnreachable(LLMError):
    pass


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)
    id: str = ""

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass
class Settings:
    provider: str
    base_url: str
    api_key: str = ""
    model: str = ""
    temperature: float = 0.6
    num_ctx: int = 8192
    keep_alive: str = "30m"
    timeout: float = 180.0
    tool_mode: str = "auto"
    compact_tools: bool = True
    max_tokens: int = 700


def settings_for(role: str = "chat", model: str | None = None) -> Settings:
    b = brain_config.get_brain()
    prov = b["provider"]
    if prov == "gemini_live":
        # The Live engine's side calls use the Gemini text API with the same key.
        prov = "gemini"
        base = brain_config.DEFAULT_URLS["gemini"]
        key = brain_config.gemini_key()
        mdl = model or "gemini-2.5-flash"
    else:
        base = str(b.get("base_url") or brain_config.DEFAULT_URLS.get(prov, ""))
        key = str(b.get("api_key") or "")
        mdl = model or brain_config.model_for(role)
    return Settings(
        provider=prov, base_url=base, api_key=key, model=mdl,
        temperature=float(b.get("temperature", 0.6)),
        num_ctx=int(b.get("num_ctx", 8192)),
        keep_alive=str(b.get("keep_alive") or "30m"),
        timeout=float(b.get("request_timeout") or 180),
        tool_mode=str(b.get("tool_mode") or "auto"),
        compact_tools=bool(b.get("compact_tools", True)),
        max_tokens=int(b.get("max_reply_tokens") or 700),
    )


# ── URL helpers ──────────────────────────────────────────────────────────────

def _openai_base(s: Settings) -> str:
    """LM Studio and friends are often entered without /v1 — add it."""
    base = (s.base_url or "").rstrip("/")
    if not base:
        base = brain_config.DEFAULT_URLS.get(s.provider, "http://localhost:1234/v1")
    tail = base.split("://", 1)[-1]
    if "/" not in tail:          # bare host:port
        base += "/v1"
    return base


def _ollama_base(s: Settings) -> str:
    base = (s.base_url or "http://localhost:11434").rstrip("/")
    for suffix in ("/api", "/v1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def _anthropic_base(s: Settings) -> str:
    base = (s.base_url or "https://api.anthropic.com").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base


def _openai_headers(s: Settings) -> dict:
    h = {"Content-Type": "application/json"}
    if s.api_key:
        h["Authorization"] = f"Bearer {s.api_key}"
    if "openrouter.ai" in (s.base_url or ""):
        h["HTTP-Referer"] = "https://github.com/anishk2000-tech/jarvis"
        h["X-Title"] = "JARVIS"
    return h


def _anthropic_headers(s: Settings) -> dict:
    return {"Content-Type": "application/json", "x-api-key": s.api_key,
            "anthropic-version": "2023-06-01"}


def _http_error(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)
            if err:
                return str(err)
            return json.dumps(data)[:400]
    except Exception:
        pass
    return (resp.text or "")[:400]


def _raise_for(resp: requests.Response, provider: str) -> None:
    if resp.status_code < 400:
        return
    msg = _http_error(resp)
    low = msg.lower()
    if ("does not support tools" in low or "tool use is not supported" in low
            or "tools is not supported" in low or "does not support function" in low
            or ("tool" in low and "not supported" in low)):
        raise ToolsUnsupported(msg)
    if resp.status_code in (401, 403):
        raise LLMError(f"{provider}: the API key was rejected ({resp.status_code}): {msg}")
    if resp.status_code == 404 and ("model" in low or "not found" in low):
        raise LLMError(f"{provider}: model not found — {msg}")
    raise LLMError(f"{provider} HTTP {resp.status_code}: {msg}")


# ── capability detection ─────────────────────────────────────────────────────

_VISION_HINTS = ("vision", "-vl", "vl:", "vl-", "llava", "bakllava", "moondream",
                 "minicpm-v", "gemma3", "gemma-3", "llama3.2-vision", "pixtral",
                 "qwen2.5vl", "qwen2.5-vl", "qwen3-vl", "granite3.2-vision", "gpt-4o",
                 "gpt-4.1", "gpt-5", "claude", "gemini", "mistral-small3.1",
                 "mistral-small3.2", "llama4", "internvl", "phi-4-multimodal",
                 "phi4-multimodal")

_caps_cache: dict[tuple, dict] = {}
_caps_lock = threading.Lock()
# Models the server told us cannot take a `tools` field: prompted mode for them.
_no_native_tools: set[tuple] = set()


def capabilities(s: Settings, model: str | None = None) -> dict:
    """{"tools": bool|None, "vision": bool|None, "thinking": bool|None}."""
    model = model or s.model
    key = (s.provider, s.base_url, model)
    with _caps_lock:
        if key in _caps_cache:
            return dict(_caps_cache[key])
    caps: dict = {"tools": None, "vision": None, "thinking": None}
    low = (model or "").lower()
    if s.provider == "ollama":
        try:
            r = requests.post(f"{_ollama_base(s)}/api/show", json={"model": model}, timeout=8)
            if r.status_code == 200:
                data = r.json()
                cl = data.get("capabilities")
                if isinstance(cl, list):
                    caps["tools"] = "tools" in cl
                    caps["vision"] = "vision" in cl
                    caps["thinking"] = "thinking" in cl
                else:
                    tmpl = str(data.get("template") or "")
                    caps["tools"] = ".Tools" in tmpl or "tools" in tmpl.lower()
                    fam = json.dumps(data.get("details", {})).lower()
                    caps["vision"] = "clip" in fam or "mllama" in fam
        except Exception:
            pass
    elif s.provider == "lmstudio":
        try:
            root = _openai_base(s).rsplit("/v1", 1)[0]
            r = requests.get(f"{root}/api/v0/models/{model}", timeout=5)
            if r.status_code == 200:
                data = r.json()
                caps["vision"] = data.get("type") == "vlm"
                cl = data.get("capabilities")
                if isinstance(cl, list):
                    caps["tools"] = "tool_use" in cl
        except Exception:
            pass
    elif s.provider in ("anthropic", "gemini"):
        caps.update(tools=True, vision=True, thinking=False)
    if caps["vision"] is None:
        caps["vision"] = any(h in low for h in _VISION_HINTS)
    if caps["thinking"] is None:
        caps["thinking"] = any(h in low for h in ("qwen3", "deepseek-r1", "qwq", "magistral",
                                                   "gpt-oss", "phi4-reasoning"))
    with _caps_lock:
        _caps_cache[key] = dict(caps)
    return caps


def model_size_b(s: Settings, model: str | None = None) -> float | None:
    """Parameter count in billions, when the server reports it (Ollama)."""
    model = model or s.model
    key = ("size", s.provider, s.base_url, model)
    with _caps_lock:
        if key in _caps_cache:
            return _caps_cache[key].get("b")
    size = None
    if s.provider == "ollama":
        try:
            r = requests.post(f"{_ollama_base(s)}/api/show", json={"model": model}, timeout=8)
            if r.status_code == 200:
                ps = str((r.json().get("details") or {}).get("parameter_size") or "")
                m = re.match(r"([\d.]+)\s*([BM])", ps.upper())
                if m:
                    size = float(m.group(1)) / (1000.0 if m.group(2) == "M" else 1.0)
        except Exception:
            pass
    if size is None:
        m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", (model or "").lower().replace(":", " ").replace("-", " "))
        if m:
            size = float(m.group(1))
    with _caps_lock:
        _caps_cache[key] = {"b": size}
    return size


def forget_capabilities() -> None:
    with _caps_lock:
        _caps_cache.clear()
        _no_native_tools.clear()


# ── model listing / health ───────────────────────────────────────────────────

def list_models(s: Settings | None = None, timeout: float = 6.0) -> list[str]:
    s = s or settings_for()
    try:
        if s.provider == "ollama":
            r = requests.get(f"{_ollama_base(s)}/api/tags", timeout=timeout)
            _raise_for(r, "Ollama")
            return sorted(m.get("name", "") for m in r.json().get("models", []) if m.get("name"))
        if s.provider == "anthropic":
            r = requests.get(f"{_anthropic_base(s)}/v1/models", headers=_anthropic_headers(s),
                             timeout=timeout)
            _raise_for(r, "Anthropic")
            return [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
        r = requests.get(f"{_openai_base(s)}/models", headers=_openai_headers(s), timeout=timeout)
        _raise_for(r, s.provider)
        data = r.json()
        items = data.get("data", data if isinstance(data, list) else [])
        names = []
        for m in items:
            mid = m.get("id") if isinstance(m, dict) else str(m)
            if mid:
                names.append(mid.replace("models/", "") if s.provider == "gemini" else mid)
        return sorted(names)
    except requests.exceptions.ConnectionError as e:
        raise ProviderUnreachable(_unreachable_msg(s)) from e
    except requests.exceptions.Timeout as e:
        raise ProviderUnreachable(f"{s.provider} did not answer within {timeout:.0f}s") from e


def _unreachable_msg(s: Settings) -> str:
    if s.provider == "ollama":
        return ("Ollama is not running at " + _ollama_base(s) +
                ". Install it from ollama.com and start it (it runs in the tray).")
    if s.provider == "lmstudio":
        return ("LM Studio's server is not reachable at " + _openai_base(s) +
                ". In LM Studio open the Developer tab, load a model and press Start Server.")
    return f"Cannot reach {s.base_url}. Check the address and your internet connection."


def ping(s: Settings | None = None) -> tuple[bool, str]:
    s = s or settings_for()
    try:
        names = list_models(s)
    except Exception as e:
        return False, str(e)
    if s.provider == "ollama" and s.model:
        base = s.model.split(":")[0]
        found = any(n == s.model or n.split(":")[0] == base and ":" not in s.model
                    or n == s.model + ":latest" for n in names)
        if not found:
            return False, (f"Ollama is running but '{s.model}' is not downloaded. "
                           f"Pull it from the AI Brain settings, or run: ollama pull {s.model}")
    if s.provider == "lmstudio" and not names:
        return False, "LM Studio is running but no model is loaded."
    return True, f"{len(names)} model(s) available"


def ensure_ollama_running(s: Settings | None = None, wait: float = 20.0) -> bool:
    """Start `ollama serve` if Ollama is installed but not running."""
    import os
    import shutil
    import subprocess
    import sys as _sys
    s = s or settings_for()
    base = _ollama_base(s)

    def up() -> bool:
        try:
            return requests.get(f"{base}/api/tags", timeout=3).status_code == 200
        except Exception:
            return False

    if up():
        return True
    if "localhost" not in base and "127.0.0.1" not in base:
        return False
    exe = shutil.which("ollama")
    if not exe and _sys.platform == "win32":
        cand = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
        exe = cand if os.path.exists(cand) else None
    if not exe:
        return False
    try:
        kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if _sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([exe, "serve"], **kw)
    except Exception:
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(0.7)
        if up():
            return True
    return False


def ollama_pull(model: str, progress: Callable[[str, float], None] | None = None,
                s: Settings | None = None, cancel: threading.Event | None = None) -> tuple[bool, str]:
    """Download a model into Ollama, reporting (status, fraction)."""
    s = s or settings_for()
    try:
        with requests.post(f"{_ollama_base(s)}/api/pull", json={"model": model, "stream": True},
                           stream=True, timeout=(10, 600)) as r:
            _raise_for(r, "Ollama")
            last = ""
            for line in r.iter_lines():
                if cancel is not None and cancel.is_set():
                    return False, "cancelled"
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("error"):
                    return False, str(ev["error"])
                status = str(ev.get("status", ""))
                total, done = ev.get("total") or 0, ev.get("completed") or 0
                frac = (done / total) if total else 0.0
                if progress and (status != last or total):
                    progress(status, frac)
                last = status
                if status == "success":
                    forget_capabilities()
                    return True, "downloaded"
        return True, "downloaded"
    except requests.exceptions.ConnectionError:
        return False, _unreachable_msg(s)
    except Exception as e:
        return False, str(e)


# ── message conversion ───────────────────────────────────────────────────────

def image_part(data: bytes, mime: str = "image/jpeg") -> dict:
    return {"mime": mime or "image/jpeg", "data": base64.b64encode(data).decode("ascii")}


def _new_id() -> str:
    return "call_" + uuid.uuid4().hex[:12]


def _to_ollama(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            item = {"role": "tool", "content": str(m.get("content", ""))}
            if m.get("name"):
                item["tool_name"] = m["name"]
            out.append(item)
            continue
        item = {"role": role, "content": str(m.get("content") or "")}
        if m.get("images"):
            item["images"] = [im["data"] for im in m["images"]]
        if role == "assistant" and m.get("tool_calls"):
            item["tool_calls"] = [{"function": {"name": tc["name"], "arguments": tc.get("arguments") or {}}}
                                  for tc in m["tool_calls"]]
        out.append(item)
    return out


def _to_openai(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id") or _new_id(),
                        "content": str(m.get("content", ""))})
            continue
        if m.get("images"):
            parts: list = []
            if m.get("content"):
                parts.append({"type": "text", "text": str(m["content"])})
            for im in m["images"]:
                parts.append({"type": "image_url",
                              "image_url": {"url": f"data:{im['mime']};base64,{im['data']}"}})
            out.append({"role": role, "content": parts})
            continue
        item: dict = {"role": role, "content": str(m.get("content") or "")}
        if role == "assistant" and m.get("tool_calls"):
            item["tool_calls"] = [{
                "id": tc.get("id") or _new_id(), "type": "function",
                "function": {"name": tc["name"],
                             "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False)},
            } for tc in m["tool_calls"]]
            if not item["content"]:
                item["content"] = None
        out.append(item)
    return out


def _to_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    out: list[dict] = []

    def push(role: str, blocks: list) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        if role == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m.get("tool_call_id") or _new_id(),
                           "content": str(m.get("content", "")) or "(empty)"}])
            continue
        blocks: list = []
        for im in m.get("images") or []:
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": im["mime"],
                                                       "data": im["data"]}})
        if m.get("content"):
            blocks.append({"type": "text", "text": str(m["content"])})
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                blocks.append({"type": "tool_use", "id": tc.get("id") or _new_id(),
                               "name": tc["name"], "input": tc.get("arguments") or {}})
            push("assistant", blocks)
        else:
            push("user", blocks)
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"type": "text", "text": "(continuing)"}]})
    return system, out


# ── prompted tool calling ────────────────────────────────────────────────────

PROMPTED_TOOLS_HEADER = """
[TOOLS]
You can act on this computer by calling tools. To call a tool, output a line of
exactly this form and NOTHING after it:
<tool_call>{"name": "TOOL_NAME", "arguments": {"param": "value"}}</tool_call>
You may say one short sentence before it. Use real JSON with double quotes.
Call one tool at a time; its result comes back in a <tool_result> message and
then you continue. When no tool is needed, just answer normally.
Available tools:
"""


def _to_prompted(messages: list[dict]) -> list[dict]:
    """Rewrite tool traffic as plain text for a model with no tool API."""
    out = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            text = str(m.get("content") or "").strip()
            calls = "\n".join("<tool_call>" + json.dumps({"name": tc["name"], "arguments": tc.get("arguments") or {}},
                                                         ensure_ascii=False) + "</tool_call>"
                              for tc in m["tool_calls"])
            out.append({"role": "assistant", "content": (text + "\n" + calls).strip()})
        elif role == "tool":
            out.append({"role": "user",
                        "content": f"<tool_result name=\"{m.get('name', '')}\">\n{m.get('content', '')}\n</tool_result>"})
        else:
            out.append(dict(m))
    # Merge consecutive user messages (tool results + next question) — some
    # chat templates reject two user turns in a row.
    merged: list[dict] = []
    for m in out:
        if merged and merged[-1]["role"] == m["role"] == "user" and not m.get("images") \
                and not merged[-1].get("images"):
            merged[-1] = dict(merged[-1])
            merged[-1]["content"] = str(merged[-1]["content"]) + "\n\n" + str(m["content"])
        else:
            merged.append(m)
    return merged


_TC_TAG = re.compile(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", re.S)
_FENCE = re.compile(r"```(?:json|tool_call|tool)?\s*(\{.*?\})\s*```", re.S)


def _json_objects(text: str) -> list[str]:
    """Every balanced {...} substring, outermost first."""
    found, depth, start, in_str, esc = [], 0, -1, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                found.append(text[start:i + 1])
    return found


def _loads_loose(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    fixed = re.sub(r",\s*([}\]])", r"\1", raw)            # trailing commas
    fixed = re.sub(r"(?<![\"\w])'([^']*)'", r'"\1"', fixed)  # single quotes
    fixed = fixed.replace("True", "true").replace("False", "false").replace("None", "null")
    try:
        return json.loads(fixed)
    except Exception:
        return None


def parse_text_tool_calls(text: str, known: set[str] | None = None) -> tuple[list[ToolCall], str]:
    """Find tool calls written as text. Returns (calls, text with them removed).

    Accepts <tool_call>{...}</tool_call>, fenced JSON, and a bare JSON object
    carrying a "name" — the three shapes small models actually produce."""
    calls: list[ToolCall] = []
    candidates: list[tuple[str, str]] = []   # (json, span to remove)
    for m in _TC_TAG.finditer(text or ""):
        candidates.append((m.group(1), m.group(0)))
    if not candidates:
        for m in _FENCE.finditer(text or ""):
            candidates.append((m.group(1), m.group(0)))
    if not candidates:
        for obj in _json_objects(text or ""):
            candidates.append((obj, obj))
    cleaned = text or ""
    for raw, span in candidates:
        data = _loads_loose(raw)
        items = data if isinstance(data, list) else [data]
        took = False
        for d in items:
            if not isinstance(d, dict):
                continue
            name = d.get("name") or d.get("tool") or d.get("function") or d.get("tool_name")
            if isinstance(name, dict):
                d = name
                name = d.get("name")
            if not isinstance(name, str):
                continue
            if known is not None and name not in known:
                continue
            args = d.get("arguments", d.get("parameters", d.get("args", d.get("input", {}))))
            if isinstance(args, str):
                args = _loads_loose(args) or {"input": args}
            if not isinstance(args, dict):
                args = {}
            calls.append(ToolCall(name=name, arguments=args, id=_new_id()))
            took = True
        if took:
            cleaned = cleaned.replace(span, " ")
    return calls, cleaned.strip()


# ── streaming ────────────────────────────────────────────────────────────────

@dataclass
class Event:
    kind: str                      # "text" | "done"
    text: str = ""
    tool_calls: list = field(default_factory=list)
    stop_reason: str = ""
    cancelled: bool = False


class _Cancelled(Exception):
    pass


def _iter_lines(resp: requests.Response, cancel: threading.Event | None) -> Iterator[str]:
    for raw in resp.iter_lines(decode_unicode=False):
        if cancel is not None and cancel.is_set():
            raise _Cancelled()
        if not raw:
            continue
        yield raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw


def _stream_ollama(s: Settings, messages, tools, cancel, caps, max_tokens) -> Iterator[Event]:
    payload: dict = {
        "model": s.model, "messages": _to_ollama(messages), "stream": True,
        "keep_alive": s.keep_alive,
        "options": {"num_ctx": s.num_ctx, "temperature": s.temperature,
                    "num_predict": max_tokens},
    }
    if tools:
        payload["tools"] = tools
    if caps.get("thinking"):
        payload["think"] = False        # a voice reply cannot wait for a monologue
    url = f"{_ollama_base(s)}/api/chat"
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.post(url, json=payload, stream=True, timeout=(10, s.timeout))
        except requests.exceptions.ConnectionError as e:
            if attempt == 1 and ensure_ollama_running(s):
                continue
            raise ProviderUnreachable(_unreachable_msg(s)) from e
        if resp.status_code >= 400:
            msg = _http_error(resp).lower()
            if "think" in msg and "think" in payload and attempt < 3:
                payload.pop("think", None)
                resp.close()
                continue
            _raise_for(resp, "Ollama")
        break
    text, calls = "", []
    with resp:
        for line in _iter_lines(resp, cancel):
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("error"):
                err = str(ev["error"])
                if "support tools" in err.lower():
                    raise ToolsUnsupported(err)
                raise LLMError(f"Ollama: {err}")
            msg = ev.get("message") or {}
            delta = msg.get("content") or ""
            if delta:
                text += delta
                yield Event("text", text=delta)
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                args = fn.get("arguments")
                if isinstance(args, str):
                    args = _loads_loose(args) or {}
                calls.append(ToolCall(name=fn.get("name", ""), arguments=args or {},
                                      id=tc.get("id") or _new_id()))
            if ev.get("done"):
                yield Event("done", text=text, tool_calls=calls,
                            stop_reason=str(ev.get("done_reason", "")))
                return
    yield Event("done", text=text, tool_calls=calls)


def _stream_openai(s: Settings, messages, tools, cancel, caps, max_tokens) -> Iterator[Event]:
    payload: dict = {"model": s.model, "messages": _to_openai(messages), "stream": True,
                     "temperature": s.temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if max_tokens and s.provider in ("lmstudio",):
        payload["max_tokens"] = max_tokens
    url = f"{_openai_base(s)}/chat/completions"
    dropped: set[str] = set()
    while True:
        try:
            resp = requests.post(url, json=payload, headers=_openai_headers(s), stream=True,
                                 timeout=(10, s.timeout))
        except requests.exceptions.ConnectionError as e:
            raise ProviderUnreachable(_unreachable_msg(s)) from e
        if resp.status_code == 400:
            msg = _http_error(resp).lower()
            # Reasoning models refuse a custom temperature; some servers refuse
            # tool_choice. Drop the offending field once and try again.
            for fld in ("temperature", "tool_choice", "max_tokens"):
                if fld in msg and fld in payload and fld not in dropped:
                    payload.pop(fld, None)
                    dropped.add(fld)
                    resp.close()
                    break
            else:
                _raise_for(resp, s.provider)
            continue
        _raise_for(resp, s.provider)
        break
    text = ""
    frags: dict[int, dict] = {}
    finish = ""
    with resp:
        for line in _iter_lines(resp, cancel):
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except Exception:
                continue
            if chunk.get("error"):
                raise LLMError(f"{s.provider}: {chunk['error']}")
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    text += piece
                    yield Event("text", text=piece)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", len(frags))
                    f = frags.setdefault(idx, {"id": "", "name": "", "args": ""})
                    f["id"] = f["id"] or tc.get("id") or ""
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        f["name"] += fn["name"]
                    if fn.get("arguments"):
                        a = fn["arguments"]
                        f["args"] += a if isinstance(a, str) else json.dumps(a)
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
    calls = []
    for idx in sorted(frags):
        f = frags[idx]
        args = _loads_loose(f["args"]) if f["args"].strip() else {}
        calls.append(ToolCall(name=f["name"], arguments=args if isinstance(args, dict) else {},
                              id=f["id"] or _new_id()))
    yield Event("done", text=text, tool_calls=calls, stop_reason=finish)


def _stream_anthropic(s: Settings, messages, tools, cancel, caps, max_tokens) -> Iterator[Event]:
    system, msgs = _to_anthropic(messages)
    payload: dict = {"model": s.model, "messages": msgs, "stream": True,
                     "max_tokens": max(256, int(max_tokens or 1024)),
                     "temperature": min(1.0, max(0.0, s.temperature))}
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = tools
    url = f"{_anthropic_base(s)}/v1/messages"
    try:
        resp = requests.post(url, json=payload, headers=_anthropic_headers(s), stream=True,
                             timeout=(10, s.timeout))
    except requests.exceptions.ConnectionError as e:
        raise ProviderUnreachable(_unreachable_msg(s)) from e
    if resp.status_code == 400 and "temperature" in _http_error(resp).lower():
        resp.close()
        payload.pop("temperature", None)
        resp = requests.post(url, json=payload, headers=_anthropic_headers(s), stream=True,
                             timeout=(10, s.timeout))
    _raise_for(resp, "Anthropic")
    text, blocks, stop = "", {}, ""
    with resp:
        for line in _iter_lines(resp, cancel):
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except Exception:
                continue
            et = ev.get("type")
            if et == "error":
                raise LLMError(f"Anthropic: {ev.get('error', {}).get('message', ev)}")
            if et == "content_block_start":
                cb = ev.get("content_block") or {}
                blocks[ev.get("index", 0)] = {"type": cb.get("type"), "id": cb.get("id", ""),
                                              "name": cb.get("name", ""), "json": ""}
            elif et == "content_block_delta":
                d = ev.get("delta") or {}
                if d.get("type") == "text_delta":
                    piece = d.get("text", "")
                    text += piece
                    if piece:
                        yield Event("text", text=piece)
                elif d.get("type") == "input_json_delta":
                    b = blocks.setdefault(ev.get("index", 0), {"type": "tool_use", "json": ""})
                    b["json"] += d.get("partial_json", "")
            elif et == "message_delta":
                stop = (ev.get("delta") or {}).get("stop_reason") or stop
            elif et == "message_stop":
                break
    calls = []
    for idx in sorted(blocks):
        b = blocks[idx]
        if b.get("type") == "tool_use":
            args = _loads_loose(b["json"]) if b["json"].strip() else {}
            calls.append(ToolCall(name=b.get("name", ""), arguments=args if isinstance(args, dict) else {},
                                  id=b.get("id") or _new_id()))
    yield Event("done", text=text, tool_calls=calls, stop_reason=stop)


def _adapter(s: Settings):
    if s.provider == "ollama":
        return _stream_ollama
    if s.provider == "anthropic":
        return _stream_anthropic
    return _stream_openai


def _tools_for(s: Settings, declarations) -> list:
    if s.provider == "anthropic":
        return tool_schema.to_anthropic_tools(declarations, compact=s.compact_tools)
    return tool_schema.to_openai_tools(declarations, compact=s.compact_tools)


def use_prompted_tools(s: Settings) -> bool:
    if s.tool_mode == "prompted":
        return True
    if s.tool_mode == "native":
        return False
    if (s.provider, s.base_url, s.model) in _no_native_tools:
        return True
    if s.provider == "ollama":
        caps = capabilities(s)
        if caps.get("tools") is False:
            return True
    return False


def stream_chat(messages: list[dict], declarations=None, s: Settings | None = None,
                cancel: threading.Event | None = None, max_tokens: int | None = None) -> Iterator[Event]:
    """Stream one assistant turn. Yields Event("text") deltas, then one
    Event("done") carrying the full text and any tool calls.

    Tool calls come back as ToolCall objects whether the model used the native
    API or wrote them as text; in the second case they are removed from the
    final text so they are never read aloud."""
    s = s or settings_for()
    if not s.model and s.provider != "lmstudio":
        raise LLMError("No model is selected. Choose one in ⚙ → AI BRAIN.")
    if not s.model and s.provider == "lmstudio":
        try:
            names = list_models(s)
            s.model = names[0] if names else ""
        except Exception:
            pass
    known = {d.get("name") if isinstance(d, dict) else getattr(d, "name", "")
             for d in (declarations or [])}
    known.discard(None)
    caps = capabilities(s) if s.provider in ("ollama",) else {}
    max_tokens = max_tokens or s.max_tokens
    prompted = bool(declarations) and use_prompted_tools(s)

    def run(prompted_mode: bool) -> Iterator[Event]:
        msgs = list(messages)
        tools = None
        if declarations:
            if prompted_mode:
                listing = tool_schema.tools_as_text(declarations, compact=True)
                sys_extra = PROMPTED_TOOLS_HEADER + listing
                msgs = _to_prompted(msgs)
                if msgs and msgs[0].get("role") == "system":
                    msgs[0] = {"role": "system", "content": str(msgs[0]["content"]) + "\n" + sys_extra}
                else:
                    msgs.insert(0, {"role": "system", "content": sys_extra})
            else:
                tools = _tools_for(s, declarations)
        adapter = _adapter(s)
        for ev in adapter(s, msgs, tools, cancel, caps, max_tokens):
            if ev.kind == "done" and declarations and not ev.tool_calls:
                # Native mode too: small models often write the call as text.
                calls, cleaned = parse_text_tool_calls(ev.text, known)
                if calls:
                    ev = Event("done", text=cleaned, tool_calls=calls, stop_reason="tool_calls")
            if ev.kind == "done":
                ev.tool_calls = [tc for tc in ev.tool_calls if tc.name]
            yield ev

    try:
        try:
            yield from run(prompted)
        except ToolsUnsupported:
            if prompted:
                raise LLMError(f"{s.model} rejected the request even without tools")
            _no_native_tools.add((s.provider, s.base_url, s.model))
            yield from run(True)
    except _Cancelled:
        yield Event("done", cancelled=True)


def chat(messages: list[dict], declarations=None, s: Settings | None = None,
         cancel: threading.Event | None = None, max_tokens: int | None = None) -> Event:
    final = Event("done")
    for ev in stream_chat(messages, declarations, s=s, cancel=cancel, max_tokens=max_tokens):
        if ev.kind == "done":
            final = ev
    return final


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def strip_thinking(text: str) -> str:
    text = _THINK.sub("", text or "")
    if "</think>" in text.lower():
        text = re.split(r"</think>", text, flags=re.I)[-1]
    return text.strip()


def complete(contents, system: str = "", role: str = "smart", model: str | None = None,
             max_tokens: int = 1500, timeout: float | None = None) -> str:
    """One-shot generation for side calls (summaries, code, JSON, vision).

    `contents` may be a string, or a list mixing strings and image parts as
    returned by image_part() — or google-genai Part objects, which is how the
    existing actions pass screenshots."""
    texts: list[str] = []
    images: list[dict] = []
    items = contents if isinstance(contents, (list, tuple)) else [contents]
    for it in items:
        if isinstance(it, str):
            texts.append(it)
        elif isinstance(it, dict) and "data" in it and "mime" in it:
            images.append(it)
        else:
            blob = getattr(it, "inline_data", None)
            if blob is not None and getattr(blob, "data", None) is not None:
                data = blob.data
                if isinstance(data, str):
                    images.append({"mime": blob.mime_type or "image/png", "data": data})
                else:
                    images.append(image_part(data, blob.mime_type or "image/png"))
                continue
            t = getattr(it, "text", None)
            if t:
                texts.append(str(t))
    if images and role != "vision":
        role = "vision"
    s = settings_for(role, model=model)
    if images:
        vis = brain_config.model_for("vision")
        if vis:
            s.model = vis
    if timeout:
        s.timeout = timeout
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    user: dict = {"role": "user", "content": "\n\n".join(texts)}
    if images:
        user["images"] = images
    msgs.append(user)
    ev = chat(msgs, None, s=s, max_tokens=max_tokens)
    return strip_thinking(ev.text)
