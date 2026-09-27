"""
A scripted stand-in for Ollama, OpenAI-compatible servers and Anthropic.

The script is a function(messages, tools, api) -> reply dict:
    {"text": "...", "tool_calls": [{"name": ..., "arguments": {...}}]}
It lets tests drive the real HTTP adapters, streaming and all, without a model.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockLLM:
    def __init__(self, script, no_tools_models=(), vision_models=(), models=("test-model",)):
        self.script = script
        self.no_tools_models = set(no_tools_models)
        self.vision_models = set(vision_models)
        self.models = list(models)
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}")

            def do_GET(self):
                if self.path.startswith("/api/tags"):
                    return self._json(200, {"models": [{"name": m} for m in outer.models]})
                if self.path.endswith("/models"):
                    return self._json(200, {"data": [{"id": m} for m in outer.models]})
                self._json(404, {"error": "nope"})

            def do_POST(self):
                body = self._body()
                outer.requests.append({"path": self.path, "body": body})
                if self.path == "/api/show":
                    m = body.get("model")
                    caps = ["completion"]
                    if m not in outer.no_tools_models:
                        caps.append("tools")
                    if m in outer.vision_models:
                        caps.append("vision")
                    return self._json(200, {"capabilities": caps})
                if self.path == "/api/chat":
                    return self._ollama(body)
                if self.path.endswith("/chat/completions"):
                    return self._openai(body)
                if self.path == "/v1/messages":
                    return self._anthropic(body)
                self._json(404, {"error": "unknown"})

            def _reply(self, body, api):
                return outer.script(body.get("messages", []), body.get("tools"), api) or {}

            def _stream(self, ctype):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

            def _chunk(self, data: str):
                b = data.encode()
                self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
                self.wfile.flush()

            def _end(self):
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()

            def _ollama(self, body):
                if body.get("tools") and body.get("model") in outer.no_tools_models:
                    return self._json(400, {"error": f"registry.ollama.ai/library/{body['model']} does not support tools"})
                r = self._reply(body, "ollama")
                self._stream("application/x-ndjson")
                text = r.get("text", "")
                for i in range(0, len(text), 7):
                    self._chunk(json.dumps({"message": {"role": "assistant", "content": text[i:i + 7]}, "done": False}) + "\n")
                if r.get("tool_calls"):
                    self._chunk(json.dumps({"message": {"role": "assistant", "content": "", "tool_calls": [
                        {"function": {"name": t["name"], "arguments": t.get("arguments", {})}} for t in r["tool_calls"]]},
                        "done": False}) + "\n")
                self._chunk(json.dumps({"message": {"role": "assistant", "content": ""}, "done": True,
                                        "done_reason": "stop"}) + "\n")
                self._end()

            def _openai(self, body):
                r = self._reply(body, "openai")
                self._stream("text/event-stream")
                text = r.get("text", "")
                for i in range(0, len(text), 5):
                    self._chunk("data: " + json.dumps({"choices": [{"index": 0, "delta": {"content": text[i:i + 5]}}]}) + "\n\n")
                for n, t in enumerate(r.get("tool_calls") or []):
                    args = json.dumps(t.get("arguments", {}))
                    self._chunk("data: " + json.dumps({"choices": [{"index": 0, "delta": {"tool_calls": [
                        {"index": n, "id": f"c{n}", "type": "function", "function": {"name": t["name"], "arguments": ""}}]}}]}) + "\n\n")
                    for j in range(0, len(args), 4):
                        self._chunk("data: " + json.dumps({"choices": [{"index": 0, "delta": {"tool_calls": [
                            {"index": n, "function": {"arguments": args[j:j + 4]}}]}}]}) + "\n\n")
                self._chunk("data: " + json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n")
                self._chunk("data: [DONE]\n\n")
                self._end()

            def _anthropic(self, body):
                r = self._reply(body, "anthropic")
                self._stream("text/event-stream")

                def ev(obj):
                    self._chunk(f"event: {obj['type']}\ndata: {json.dumps(obj)}\n\n")
                ev({"type": "message_start", "message": {"id": "m"}})
                idx = 0
                text = r.get("text", "")
                if text:
                    ev({"type": "content_block_start", "index": idx, "content_block": {"type": "text", "text": ""}})
                    for i in range(0, len(text), 6):
                        ev({"type": "content_block_delta", "index": idx, "delta": {"type": "text_delta", "text": text[i:i + 6]}})
                    ev({"type": "content_block_stop", "index": idx})
                    idx += 1
                for t in r.get("tool_calls") or []:
                    ev({"type": "content_block_start", "index": idx,
                        "content_block": {"type": "tool_use", "id": f"tu{idx}", "name": t["name"], "input": {}}})
                    args = json.dumps(t.get("arguments", {}))
                    for j in range(0, len(args), 5):
                        ev({"type": "content_block_delta", "index": idx, "delta": {"type": "input_json_delta", "partial_json": args[j:j + 5]}})
                    ev({"type": "content_block_stop", "index": idx})
                    idx += 1
                ev({"type": "message_delta", "delta": {"stop_reason": "tool_use" if r.get("tool_calls") else "end_turn"}})
                ev({"type": "message_stop"})
                self._end()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._t.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
