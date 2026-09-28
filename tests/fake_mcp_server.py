import json, sys
def send(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    m = json.loads(line)
    if m.get("method") == "initialize":
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}})
        send({"jsonrpc": "2.0", "id": 99, "method": "ping"})
    elif m.get("method") == "tools/list":
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"tools": [
            {"name": "add", "description": "Add two numbers", "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}},
            {"name": "fail", "description": "Always fails", "inputSchema": {"type": "object"}}]}})
    elif m.get("method") == "tools/call":
        p = m["params"]
        if p["name"] == "add":
            send({"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": str(p["arguments"]["a"] + p["arguments"]["b"])}]}})
        else:
            send({"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "boom"}], "isError": True}})
