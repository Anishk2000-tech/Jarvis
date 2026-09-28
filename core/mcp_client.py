"""
Model Context Protocol client — use any MCP server's tools as the assistant's own.

Servers are listed in config/mcp_servers.json, in the same format Claude
Desktop, Cursor and most MCP documentation use:

    {
      "mcpServers": {
        "filesystem": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/me/Documents"]
        },
        "home-assistant": {
          "url": "http://homeassistant.local:8123/mcp_server/sse",
          "headers": {"Authorization": "Bearer <token>"}
        }
      }
    }

Each server's tools appear to the model as  mcp_<server>_<tool>. Both engines
use them: the local engine picks them up on the next request, the Gemini Live
engine reconnects (keeping the conversation) when they arrive.

The protocol is implemented directly — JSON-RPC 2.0 over a subprocess's stdio,
or over HTTP for remote servers — so no extra package is needed.
"""
from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from core import brain_config
from core.tool_schema import json_schema_to_gemini, sanitize_tool_name

CONFIG_FILE = brain_config.BASE_DIR / "config" / "mcp_servers.json"
PROTOCOL = "2025-06-18"

_EXAMPLE = {
    "mcpServers": {
        "_example_filesystem": {
            "disabled": True,
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", str(Path.home() / "Documents")],
            "note": "Remove 'disabled' (needs Node.js) to let the assistant use this server."
        }
    }
}


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", data.get("servers", {}))
        return servers if isinstance(servers, dict) else {}
    except FileNotFoundError:
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(_EXAMPLE, indent=2), encoding="utf-8")
        except Exception:
            pass
        return {}
    except Exception as e:
        print(f"[MCP] config unreadable: {e}")
        return {}


def save_config(servers: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8")


class _StdioServer:
    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self._proc: subprocess.Popen | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, dict] = {}
        self._cv = threading.Condition()
        self._wlock = threading.Lock()
        self.stderr_tail: list[str] = []

    def start(self, timeout: float = 60.0) -> dict:
        cmd = str(self.cfg.get("command") or "")
        args = [str(a) for a in (self.cfg.get("args") or [])]
        exe = shutil.which(cmd) or cmd
        argv = [exe] + args
        if sys.platform == "win32" and exe.lower().endswith((".cmd", ".bat")):
            argv = ["cmd.exe", "/c", exe] + args
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (self.cfg.get("env") or {}).items()})
        kw: dict = {}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, env=env, cwd=self.cfg.get("cwd") or None,
                                      **kw)
        threading.Thread(target=self._read_out, daemon=True, name=f"mcp-{self.name}-out").start()
        threading.Thread(target=self._read_err, daemon=True, name=f"mcp-{self.name}-err").start()
        res = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                          "clientInfo": {"name": "jarvis", "version": "1.0"}}, timeout)
        self.notify("notifications/initialized")
        return res

    def _send(self, obj: dict) -> None:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self._wlock:
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(data)
            self._proc.stdin.flush()

    def notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def request(self, method: str, params: dict | None = None, timeout: float = 60.0) -> dict:
        rid = next(self._ids)
        with self._cv:
            self._pending[rid] = {}
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        with self._cv:
            while not self._pending.get(rid):
                left = deadline - time.monotonic()
                if left <= 0 or (self._proc and self._proc.poll() is not None):
                    self._pending.pop(rid, None)
                    tail = " | ".join(self.stderr_tail[-3:])
                    raise RuntimeError(f"{self.name}: no answer to {method}" + (f" ({tail})" if tail else ""))
                self._cv.wait(timeout=min(left, 0.5))
            msg = self._pending.pop(rid)
        if "error" in msg:
            err = msg["error"]
            raise RuntimeError(f"{self.name}: {err.get('message', err) if isinstance(err, dict) else err}")
        return msg.get("result") or {}

    def _read_out(self) -> None:
        assert self._proc and self._proc.stdout
        for raw in self._proc.stdout:
            try:
                msg = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if not isinstance(msg, dict):
                continue
            if "id" in msg and ("result" in msg or "error" in msg) and "method" not in msg:
                with self._cv:
                    if msg["id"] in self._pending:
                        self._pending[msg["id"]] = msg
                        self._cv.notify_all()
            elif "method" in msg and "id" in msg:
                # A request from the server (ping, roots/list, sampling…).
                method = msg["method"]
                if method == "ping":
                    self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
                elif method == "roots/list":
                    self._send({"jsonrpc": "2.0", "id": msg["id"],
                                "result": {"roots": [{"uri": Path.home().as_uri(), "name": "home"}]}})
                else:
                    self._send({"jsonrpc": "2.0", "id": msg["id"],
                                "error": {"code": -32601, "message": "not supported"}})

    def _read_err(self) -> None:
        assert self._proc and self._proc.stderr
        for raw in self._proc.stderr:
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                self.stderr_tail = (self.stderr_tail + [line])[-10:]

    def alive(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    def stop(self) -> None:
        try:
            if self._proc:
                self._proc.terminate()
        except Exception:
            pass


class _HttpServer:
    """Streamable-HTTP transport (and the older SSE-in-response variant)."""

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.url = str(cfg.get("url"))
        self.headers = {str(k): str(v) for k, v in (cfg.get("headers") or {}).items()}
        self._sid = None
        self._ids = itertools.count(1)
        self.stderr_tail: list[str] = []

    def _post(self, obj: dict, timeout: float) -> dict | None:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
             "MCP-Protocol-Version": PROTOCOL, **self.headers}
        if self._sid:
            h["Mcp-Session-Id"] = self._sid
        r = requests.post(self.url, json=obj, headers=h, timeout=timeout, stream=True)
        if r.headers.get("Mcp-Session-Id"):
            self._sid = r.headers["Mcp-Session-Id"]
        if r.status_code == 202 or "id" not in obj:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"{self.name}: HTTP {r.status_code} {r.text[:200]}")
        ctype = r.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    try:
                        msg = json.loads(line[5:].strip())
                    except Exception:
                        continue
                    if isinstance(msg, dict) and msg.get("id") == obj["id"]:
                        return msg
            return None
        return r.json()

    def start(self, timeout: float = 30.0) -> dict:
        res = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                          "clientInfo": {"name": "jarvis", "version": "1.0"}}, timeout)
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout)
        except Exception:
            pass
        return res

    def request(self, method: str, params: dict | None = None, timeout: float = 60.0) -> dict:
        msg = self._post({"jsonrpc": "2.0", "id": next(self._ids), "method": method,
                          "params": params or {}}, timeout)
        if not msg:
            raise RuntimeError(f"{self.name}: empty reply to {method}")
        if "error" in msg:
            raise RuntimeError(f"{self.name}: {msg['error']}")
        return msg.get("result") or {}

    def alive(self) -> bool:
        return True

    def stop(self) -> None:
        pass


class McpManager:
    def __init__(self):
        self._servers: dict[str, object] = {}
        self._tools: dict[str, tuple[str, str, dict]] = {}   # exposed → (server, tool, decl)
        self._lock = threading.RLock()
        self._log: Callable[[str], None] = print
        self.status: dict[str, str] = {}
        self._started = False

    def start_async(self, log: Callable[[str], None] = print) -> None:
        if self._started:
            return
        self._started = True
        self._log = log
        threading.Thread(target=self.reload, daemon=True, name="mcp-start").start()

    def reload(self) -> str:
        with self._lock:
            for srv in self._servers.values():
                srv.stop()
            self._servers.clear()
            self._tools.clear()
        cfg = load_config()
        active = {k: v for k, v in cfg.items() if isinstance(v, dict) and not v.get("disabled")
                  and not k.startswith("_")}
        for name, sc in active.items():
            try:
                srv = _HttpServer(name, sc) if sc.get("url") else _StdioServer(name, sc)
                srv.start()
                tools, cursor = [], None
                for _ in range(20):
                    res = srv.request("tools/list", {"cursor": cursor} if cursor else {})
                    tools += res.get("tools") or []
                    cursor = res.get("nextCursor")
                    if not cursor:
                        break
                with self._lock:
                    self._servers[name] = srv
                    for t in tools:
                        tname = str(t.get("name", ""))
                        exposed = sanitize_tool_name(f"mcp_{name}_{tname}")
                        decl = {"name": exposed,
                                "description": f"[{name}] " + str(t.get("description") or tname)[:600],
                                "parameters": json_schema_to_gemini(t.get("inputSchema") or {"type": "object"})}
                        self._tools[exposed] = (name, tname, decl)
                self.status[name] = f"connected, {len(tools)} tools"
                self._log(f"SYS: MCP server '{name}' connected — {len(tools)} tools.")
            except Exception as e:
                self.status[name] = f"failed: {str(e)[:160]}"
                self._log(f"ERR: MCP server '{name}' failed — {str(e)[:160]}")
        self._notify_engine()
        return self.summary()

    def _notify_engine(self) -> None:
        try:
            from core import runtime
            eng = runtime.engine()
            if eng is not None and getattr(eng, "engine_kind", "") != "local" and self._tools:
                eng.request_reconnect(keep_context=True, reason="new MCP tools")
        except Exception:
            pass

    def summary(self) -> str:
        if not self.status:
            return ("No MCP servers configured. Add them to config/mcp_servers.json "
                    "(same format as Claude Desktop).")
        return "MCP servers:\n" + "\n".join(f"- {k}: {v}" for k, v in self.status.items())

    def gemini_declarations(self) -> list[dict]:
        with self._lock:
            return [d for (_s, _t, d) in self._tools.values()]

    def has(self, exposed: str) -> bool:
        with self._lock:
            return exposed in self._tools

    def call(self, exposed: str, args: dict, timeout: float = 120.0) -> str:
        with self._lock:
            entry = self._tools.get(exposed)
            srv = self._servers.get(entry[0]) if entry else None
        if not entry or srv is None:
            return f"MCP tool '{exposed}' is not available."
        if not srv.alive():
            return f"The MCP server '{entry[0]}' has stopped. Say 'reload MCP servers' to restart it."
        try:
            res = srv.request("tools/call", {"name": entry[1], "arguments": args or {}}, timeout)
        except Exception as e:
            return f"MCP call failed: {e}"
        parts = []
        for c in res.get("content") or []:
            if c.get("type") == "text":
                parts.append(str(c.get("text", "")))
            elif c.get("type") == "image":
                parts.append("[image returned]")
            elif c.get("type") == "resource":
                r = c.get("resource") or {}
                parts.append(str(r.get("text") or r.get("uri") or ""))
        if not parts and res.get("structuredContent") is not None:
            parts.append(json.dumps(res["structuredContent"], ensure_ascii=False)[:6000])
        text = "\n".join(p for p in parts if p).strip() or "(no output)"
        return ("ERROR: " + text) if res.get("isError") else text


_manager: McpManager | None = None


def manager() -> McpManager:
    global _manager
    if _manager is None:
        _manager = McpManager()
    return _manager
