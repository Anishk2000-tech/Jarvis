"""
Tool-schema conversion between the two dialects this app speaks.

Every bundled action and plugin declares its parameters in the Gemini dialect —
an OpenAPI subset with UPPERCASE type names ("OBJECT", "STRING", ...). That is
what the Live API wants, and it stays the source of truth: nothing in actions/
or plugins/ has to change for a local model to use it.

Ollama, LM Studio, the OpenAI-compatible APIs and Anthropic all want plain JSON
Schema with lowercase types. MCP servers hand us JSON Schema too, and when the
Live engine is in use those have to go the other way.

Both directions are deliberately forgiving: a declaration nobody wrote with this
converter in mind must never stop the assistant from starting. Anything that
cannot be represented is dropped, never raised.
"""
from __future__ import annotations

import copy
import re
from typing import Any

_GEMINI_TO_JSON = {
    "OBJECT": "object", "STRING": "string", "INTEGER": "integer",
    "NUMBER": "number", "BOOLEAN": "boolean", "ARRAY": "array",
}
_JSON_TO_GEMINI = {v: k for k, v in _GEMINI_TO_JSON.items()}

# Keys JSON Schema readers understand and that are safe to pass through.
_JSON_KEEP = {"type", "description", "properties", "required", "items", "enum",
              "default", "minimum", "maximum", "format", "nullable"}
# The subset the Gemini function-declaration schema accepts.
_GEMINI_KEEP = {"type", "description", "properties", "required", "items",
                "enum", "nullable", "format"}

_NAME_OK = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


def _shorten(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if limit <= 0 or len(text) <= limit:
        return text
    # Prefer ending on a sentence, then on a word.
    cut = text[:limit]
    dot = max(cut.rfind(". "), cut.rfind("; "))
    if dot >= limit * 0.5:
        return cut[:dot + 1]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit * 0.5 else cut).rstrip(",;:") + "…"


def gemini_to_json_schema(schema: Any, desc_limit: int = 0) -> dict:
    """Gemini/OpenAPI-subset schema → JSON Schema (lowercase types)."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    out: dict = {}
    t = schema.get("type")
    if isinstance(t, str):
        out["type"] = _GEMINI_TO_JSON.get(t.upper(), t.lower())
    for key, val in schema.items():
        if key == "type" or key not in _JSON_KEEP:
            continue
        if key == "description":
            if val:
                out["description"] = _shorten(val, desc_limit) if desc_limit else str(val)
        elif key == "properties" and isinstance(val, dict):
            out["properties"] = {k: gemini_to_json_schema(v, desc_limit)
                                 for k, v in val.items() if isinstance(v, dict)}
        elif key == "items" and isinstance(val, dict):
            out["items"] = gemini_to_json_schema(val, desc_limit)
        elif key == "required" and isinstance(val, (list, tuple)):
            out["required"] = [str(r) for r in val]
        elif key == "nullable":
            continue      # JSON Schema has no such keyword; the type says enough
        else:
            out[key] = copy.deepcopy(val)
    if out.get("type") == "object":
        out.setdefault("properties", {})
        props = out.get("properties", {})
        if "required" in out:
            out["required"] = [r for r in out["required"] if r in props]
            if not out["required"]:
                out.pop("required")
    if out.get("type") == "array" and "items" not in out:
        out["items"] = {"type": "string"}
    if "type" not in out:
        out["type"] = "object" if "properties" in out else "string"
    return out


def _first_type(t: Any) -> str:
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        return str(non_null[0]) if non_null else "string"
    return str(t or "")


def json_schema_to_gemini(schema: Any) -> dict:
    """JSON Schema (e.g. from an MCP server) → Gemini function schema.

    Unions (anyOf/oneOf) collapse to their first non-null branch, `$ref`s are
    not followed, and anything unknown is dropped — the model gets a slightly
    looser description instead of the whole session failing to connect."""
    if not isinstance(schema, dict):
        return {"type": "OBJECT", "properties": {}}
    for union in ("anyOf", "oneOf", "allOf"):
        if union in schema and isinstance(schema[union], list) and "type" not in schema:
            branches = [b for b in schema[union]
                        if isinstance(b, dict) and b.get("type") != "null"]
            if branches:
                merged = dict(branches[0])
                if schema.get("description") and not merged.get("description"):
                    merged["description"] = schema["description"]
                return json_schema_to_gemini(merged)
    out: dict = {}
    t = _first_type(schema.get("type"))
    if not t:
        t = "object" if "properties" in schema else "string"
    out["type"] = _JSON_TO_GEMINI.get(t.lower(), "STRING")
    for key, val in schema.items():
        if key == "type" or key not in _GEMINI_KEEP:
            continue
        if key == "properties" and isinstance(val, dict):
            out["properties"] = {k: json_schema_to_gemini(v) for k, v in val.items()
                                 if isinstance(v, dict)}
        elif key == "items" and isinstance(val, dict):
            out["items"] = json_schema_to_gemini(val)
        elif key == "required" and isinstance(val, (list, tuple)):
            out["required"] = [str(r) for r in val]
        elif key == "enum" and isinstance(val, list):
            out["enum"] = [str(v) for v in val]
        elif key == "description":
            out["description"] = str(val)[:1000]
        elif key == "format":
            continue      # Gemini only accepts a few formats; not worth the risk
        else:
            out[key] = copy.deepcopy(val)
    if out["type"] == "OBJECT":
        out.setdefault("properties", {})
        if "required" in out:
            out["required"] = [r for r in out["required"] if r in out["properties"]]
            if not out["required"]:
                out.pop("required")
    if out["type"] == "ARRAY" and "items" not in out:
        out["items"] = {"type": "STRING"}
    if out["type"] != "STRING" and "enum" in out:
        out.pop("enum")
    return out


def _decl_field(decl: Any, key: str, default=None):
    if isinstance(decl, dict):
        return decl.get(key, default)
    return getattr(decl, key, default)


def to_openai_tools(declarations, compact: bool = False) -> list[dict]:
    """Declarations (Gemini dialect) → OpenAI / Ollama `tools` list."""
    tools = []
    seen = set()
    for d in declarations or ():
        name = _decl_field(d, "name")
        if not isinstance(name, str) or not _NAME_OK.match(name) or name in seen:
            continue
        seen.add(name)
        desc = str(_decl_field(d, "description", "") or "")
        params = _decl_field(d, "parameters") or {"type": "OBJECT", "properties": {}}
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": _shorten(desc, 220) if compact else " ".join(desc.split()),
                "parameters": gemini_to_json_schema(params, desc_limit=70 if compact else 0),
            },
        })
    return tools


def to_anthropic_tools(declarations, compact: bool = False) -> list[dict]:
    out = []
    for t in to_openai_tools(declarations, compact=compact):
        fn = t["function"]
        out.append({"name": fn["name"], "description": fn["description"] or fn["name"],
                    "input_schema": fn["parameters"]})
    return out


def tools_as_text(declarations, compact: bool = True) -> str:
    """A compact, model-readable listing for the prompted tool-calling fallback."""
    lines = []
    for t in to_openai_tools(declarations, compact=compact):
        fn = t["function"]
        props = fn["parameters"].get("properties", {})
        req = set(fn["parameters"].get("required", []))
        args = []
        for pname, p in props.items():
            ptype = p.get("type", "string")
            mark = "" if pname in req else "?"
            pdesc = p.get("description", "")
            enum = p.get("enum")
            extra = f" one of {enum}" if enum else ""
            args.append(f"{pname}{mark}: {ptype}{extra}" + (f" — {pdesc}" if pdesc else ""))
        lines.append(f"- {fn['name']}: {fn['description']}")
        for a in args:
            lines.append(f"    · {a}")
    return "\n".join(lines)


def sanitize_tool_name(name: str) -> str:
    """Make an arbitrary string a legal tool name (^[a-zA-Z_][a-zA-Z0-9_]{0,63}$)."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", str(name or ""))
    if not s or not re.match(r"[a-zA-Z_]", s[0]):
        s = "t_" + s
    return s[:64]


def coerce_arguments(args: Any, parameters: dict | None) -> dict:
    """Make model-produced arguments match the declared types where it is safe.

    Small local models routinely send "3" for an INTEGER or "true" for a
    BOOLEAN, or wrap everything in a string. The handlers were written for
    Gemini, which never does, so the repair happens here once instead of in
    every action."""
    import json as _json
    if isinstance(args, str):
        s = args.strip()
        try:
            args = _json.loads(s) if s else {}
        except Exception:
            args = {"input": s}
    if not isinstance(args, dict):
        return {}
    props = (parameters or {}).get("properties", {}) if isinstance(parameters, dict) else {}
    out = dict(args)
    for key, spec in props.items():
        if key not in out or not isinstance(spec, dict):
            continue
        t = str(spec.get("type", "")).upper()
        v = out[key]
        try:
            if t == "INTEGER" and isinstance(v, (str, float)) and str(v).strip():
                out[key] = int(float(str(v).strip()))
            elif t == "NUMBER" and isinstance(v, str) and v.strip():
                out[key] = float(v.strip())
            elif t == "BOOLEAN" and isinstance(v, str):
                out[key] = v.strip().lower() in ("true", "1", "yes", "y", "on")
            elif t == "STRING" and isinstance(v, (int, float, bool)):
                out[key] = str(v)
            elif t == "STRING" and isinstance(v, (list, dict)):
                out[key] = _json.dumps(v, ensure_ascii=False)
            elif t == "ARRAY" and isinstance(v, str):
                s = v.strip()
                if s.startswith("["):
                    out[key] = _json.loads(s)
                else:
                    out[key] = [x.strip() for x in s.split(",") if x.strip()]
        except Exception:
            pass
    return out
