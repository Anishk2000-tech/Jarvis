from actions import computer_agent as ca
from core import screen_reader, llm


class FakePG:
    def __init__(self):
        self.calls = []
    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a))


def test_agent_clicks_types_and_finishes(monkeypatch):
    pg = FakePG()
    monkeypatch.setattr(ca, "_pyautogui", lambda: pg)
    monkeypatch.setattr(ca.time, "sleep", lambda s: None)
    els = [screen_reader.Element(0, "Edit", "Search", 100, 100, 200, 30),
           screen_reader.Element(0, "Button", "Go", 320, 100, 40, 30)]

    def observe(with_image=True, with_ocr=True, max_items=140):
        for i, e in enumerate(els, 1):
            e.idx = i
        return screen_reader.Observation("Browser", ["Browser"], list(els))
    monkeypatch.setattr(ca.screen_reader, "observe", observe)
    monkeypatch.setattr(ca.llm, "capabilities", lambda s, model=None: {"vision": False})
    script = iter([
        '{"thought": "type query", "action": "type", "id": 1, "text": "weather", "enter": false}',
        'Sure! {"action": "click", "id": 2}',
        '{"action": "done", "summary": "searched for weather"}',
    ])
    seen_prompts = []

    def chat(msgs, decls, s=None, max_tokens=None, cancel=None):
        seen_prompts.append(msgs[-1]["content"])
        return llm.Event("done", text=next(script))
    monkeypatch.setattr(ca.llm, "chat", chat)
    out = ca.run_goal("search the weather", max_steps=10)
    assert out.startswith("Done in 3 steps"), out
    names = [c[0] for c in pg.calls]
    assert names[:2] == ["click", "write"] and ("click", (340, 115)) in pg.calls
    assert '[2] Button "Go" @(340,115)' in seen_prompts[0]
    assert "1. type: typed 7 characters" in seen_prompts[1]


def test_agent_stops_when_stuck(monkeypatch):
    pg = FakePG()
    monkeypatch.setattr(ca, "_pyautogui", lambda: pg)
    monkeypatch.setattr(ca.time, "sleep", lambda s: None)
    monkeypatch.setattr(ca.screen_reader, "observe", lambda **k: screen_reader.Observation("x", [], []))
    monkeypatch.setattr(ca.llm, "capabilities", lambda s, model=None: {"vision": False})
    monkeypatch.setattr(ca.llm, "chat", lambda *a, **k: llm.Event("done", text='{"action": "press", "key": "tab"}'))
    out = ca.run_goal("loop forever", max_steps=10)
    assert out.startswith("Stuck repeating"), out
