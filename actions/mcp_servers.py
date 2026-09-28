"""
mcp_servers — connect the assistant to Model Context Protocol servers.

MCP servers give the assistant new tools without writing code: file systems,
GitHub, databases, Home Assistant, Spotify, Notion, browsers and thousands more.
Configuration is kept in config/mcp_servers.json (Claude Desktop format).
"""
from core import mcp_client


def mcp_servers(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action", "list")).lower().strip()
    mgr = mcp_client.manager()
    if action in ("list", "status"):
        tools = [d["name"] for d in mgr.gemini_declarations()]
        extra = f"\nTools: {', '.join(tools[:60])}" if tools else ""
        return mgr.summary() + extra
    if action == "reload":
        return mgr.reload()
    if action == "add":
        name = str(p.get("name", "")).strip()
        if not name:
            return "Give the server a short name."
        cfg = mcp_client.load_config()
        entry: dict = {}
        if p.get("url"):
            entry["url"] = str(p["url"])
            if p.get("token"):
                entry["headers"] = {"Authorization": f"Bearer {p['token']}"}
        elif p.get("command"):
            entry["command"] = str(p["command"])
            args = p.get("args") or []
            if isinstance(args, str):
                import shlex
                args = shlex.split(args, posix=False)
            entry["args"] = [str(a) for a in args]
        else:
            return "Provide either a command (with args) or a url."
        cfg[name] = entry
        mcp_client.save_config(cfg)
        return f"Saved MCP server '{name}'. " + mgr.reload()
    if action == "remove":
        name = str(p.get("name", "")).strip()
        cfg = mcp_client.load_config()
        if name not in cfg:
            return f"No MCP server named '{name}'."
        cfg.pop(name)
        mcp_client.save_config(cfg)
        return f"Removed '{name}'. " + mgr.reload()
    return "Unknown action. Use list, add, remove or reload."


TOOL = {
    "name": "mcp_servers",
    "description": (
        "Manage Model Context Protocol (MCP) servers that give you extra tools: list connected "
        "servers and their tools, add a server (a command like npx/uvx with args, or a URL), "
        "remove one, or reload them."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list | add | remove | reload"},
            "name": {"type": "STRING", "description": "Short server name"},
            "command": {"type": "STRING", "description": "Executable, e.g. npx or uvx"},
            "args": {"type": "STRING", "description": "Arguments, space separated"},
            "url": {"type": "STRING", "description": "URL of a remote (HTTP) MCP server"},
            "token": {"type": "STRING", "description": "Bearer token for a remote server"},
        },
        "required": ["action"],
    },
    "handler": mcp_servers,
}
