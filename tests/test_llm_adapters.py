import json
import pytest
from core import llm
from tests.mock_llm_server import MockLLM

DECLS = [{"name": "open_app", "description": "Opens an app", "parameters": {
    "type": "OBJECT", "properties": {"app_name": {"type": "STRING"}}, "required": ["app_name"]}}]


def script(messages, tools, api):
    last = messages[-1]
    content = last.get("content")
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    content = str(content)
    if "tool_result" in content or last.get("role") == "tool" or (isinstance(last.get("content"), list) and any(b.get("type") == "tool_result" for b in last["content"])):
        return {"text": "Notepad is open."}
    if "open notepad" in content:
        if tools:
            return {"text": "Opening it. ", "tool_calls": [{"name": "open_app", "arguments": {"app_name": "notepad"}}]}
        return {"text": 'Opening it. <tool_call>{"name": "open_app", "arguments": {"app_name": "notepad"}}</tool_call>'}
    return {"text": "Hello. I am fine."}


@pytest.fixture
def server():
    s = MockLLM(script, no_tools_models={"dumb"})
    yield s
    s.close()


@pytest.mark.parametrize("provider,base", [("ollama", ""), ("lmstudio", "/v1"), ("openai", "/v1"), ("anthropic", "")])
def test_tool_roundtrip(server, provider, base):
    s = llm.Settings(provider=provider, base_url=server.url + base, api_key="k", model="test-model")
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "please open notepad"}]
    texts = []
    done = None
    for ev in llm.stream_chat(msgs, DECLS, s=s):
        if ev.kind == "text":
            texts.append(ev.text)
        else:
            done = ev
    assert done.tool_calls and done.tool_calls[0].name == "open_app"
    assert done.tool_calls[0].arguments == {"app_name": "notepad"}
    assert "".join(texts).startswith("Opening it.")
    # feed the result back
    msgs.append({"role": "assistant", "content": done.text, "tool_calls": [t.as_dict() for t in done.tool_calls]})
    msgs.append({"role": "tool", "tool_call_id": done.tool_calls[0].id, "name": "open_app", "content": "Opened notepad"})
    final = llm.chat(msgs, DECLS, s=s)
    assert final.text == "Notepad is open." and not final.tool_calls


def test_ollama_falls_back_to_prompted_tools(server):
    s = llm.Settings(provider="ollama", base_url=server.url, model="dumb")
    msgs = [{"role": "user", "content": "open notepad"}]
    ev = llm.chat(msgs, DECLS, s=s)
    assert ev.tool_calls[0].name == "open_app"
    assert "<tool_call>" not in ev.text
    # the request that succeeded carried the tool list in the system prompt, not `tools`
    last = server.requests[-1]["body"]
    assert "tools" not in last and "open_app" in last["messages"][0]["content"]


def test_list_models_and_ping(server):
    s = llm.Settings(provider="ollama", base_url=server.url, model="test-model")
    assert llm.list_models(s) == ["test-model"]
    ok, _ = llm.ping(s)
    assert ok
    s.model = "missing"
    ok, msg = llm.ping(s)
    assert not ok and "ollama pull missing" in msg


def test_unreachable_message():
    s = llm.Settings(provider="ollama", base_url="http://127.0.0.1:9", model="x")
    with pytest.raises(llm.ProviderUnreachable):
        llm.list_models(s, timeout=2)


def test_cancel(server):
    import threading
    s = llm.Settings(provider="openai", base_url=server.url + "/v1", model="test-model")
    ev = threading.Event(); ev.set()
    out = list(llm.stream_chat([{"role": "user", "content": "hi"}], None, s=s, cancel=ev))
    assert out[-1].cancelled


def test_images_are_sent(server):
    s = llm.Settings(provider="ollama", base_url=server.url, model="test-model")
    img = llm.image_part(b"\x89PNG....", "image/png")
    llm.chat([{"role": "user", "content": "what is this", "images": [img]}], None, s=s)
    assert server.requests[-1]["body"]["messages"][0]["images"] == [img["data"]]
    s2 = llm.Settings(provider="openai", base_url=server.url + "/v1", model="test-model")
    llm.chat([{"role": "user", "content": "what is this", "images": [img]}], None, s=s2)
    parts = server.requests[-1]["body"]["messages"][0]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
