import json
from core.speech_text import SpeechStream, visible_text
from core import llm, tool_schema


def run_stream(chunks):
    s = SpeechStream()
    out = []
    for c in chunks:
        out += s.feed(c)
    out += s.flush()
    return out


def test_sentences_split_as_they_arrive():
    s = SpeechStream()
    assert s.feed("Hello there. How ") == ["Hello there."]
    assert s.feed("are you?") == []
    assert s.flush() == ["How are you?"]


def test_think_block_is_never_spoken():
    out = run_stream(["<th", "ink>secret plan. more", " thoughts</thi", "nk>Done. Opening it now."])
    assert out == ["Done.", "Opening it now."]


def test_tool_call_text_is_hidden():
    out = run_stream(["Opening Chrome now. <tool_", 'call>{"name": "open_app", "arguments": {"app_name": "chrome"}}</tool_call>'])
    assert out == ["Opening Chrome now."]


def test_json_reply_is_held_and_dropped():
    out = run_stream(['{"name": "open_app", ', '"arguments": {"app_name": "x"}}'])
    assert out == []


def test_markdown_cleanup_and_code():
    out = run_stream(["**Sure**. Here:\n```python\nprint(1)\n```\n"])
    assert out == ["Sure.", "Here:"]
    out = run_stream(["```python\nprint(1)\n```"])
    assert out == ["I've put the code on screen."]


def test_long_first_chunk_breaks_on_comma():
    s = SpeechStream(first_chunk_chars=40)
    out = s.feed("Well, the forecast for tomorrow in Mumbai looks warm, with a high of 33 degrees")
    assert out and out[0].endswith(",")


def test_parse_text_tool_calls_shapes():
    known = {"open_app", "web_search"}
    calls, rest = llm.parse_text_tool_calls('Sure. <tool_call>{"name":"open_app","arguments":{"app_name":"notepad"}}</tool_call>', known)
    assert calls[0].name == "open_app" and calls[0].arguments == {"app_name": "notepad"} and rest == "Sure."
    calls, _ = llm.parse_text_tool_calls('```json\n{"name": "web_search", "parameters": {"query": "x"}}\n```', known)
    assert calls[0].arguments == {"query": "x"}
    calls, _ = llm.parse_text_tool_calls("{'name': 'open_app', 'arguments': {'app_name': 'calc'},}", known)
    assert calls and calls[0].arguments["app_name"] == "calc"
    calls, _ = llm.parse_text_tool_calls('{"name": "rm_rf", "arguments": {}}', known)
    assert calls == []
    calls, _ = llm.parse_text_tool_calls('I like {curly} braces', known)
    assert calls == []


def test_schema_roundtrip():
    g = {"type": "OBJECT", "properties": {"a": {"type": "STRING", "description": "x"},
         "n": {"type": "INTEGER"}, "l": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["a", "zz"]}
    j = tool_schema.gemini_to_json_schema(g)
    assert j["type"] == "object" and j["properties"]["n"]["type"] == "integer"
    assert j["required"] == ["a"]
    back = tool_schema.json_schema_to_gemini({"type": "object", "properties": {
        "q": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "query"},
        "k": {"type": ["integer", "null"]}}, "required": ["q"], "additionalProperties": False})
    assert back["properties"]["q"]["type"] == "STRING" and back["properties"]["k"]["type"] == "INTEGER"
    assert "additionalProperties" not in back


def test_coerce_arguments():
    params = {"type": "OBJECT", "properties": {"n": {"type": "INTEGER"}, "b": {"type": "BOOLEAN"},
              "s": {"type": "STRING"}, "l": {"type": "ARRAY"}}}
    out = tool_schema.coerce_arguments('{"n": "3", "b": "true", "s": 5, "l": "a, b"}', params)
    assert out == {"n": 3, "b": True, "s": "5", "l": ["a", "b"]}


def test_visible_text():
    assert visible_text("<think>x</think>Hi <tool_call>{}</tool_call>") == "Hi"
