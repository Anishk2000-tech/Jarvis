"""
computer_agent — operate the computer like a person would, step by step, until
a goal is done.

    "open WhatsApp desktop and send 'on my way' to Mom"
    "in Excel, make the header row bold and sort by the Date column"
    "turn on Bluetooth in Settings"
    "find the invoice PDF from last week in my Downloads and attach it to a new
     Outlook email to Ravi"

Every step the agent looks at the screen (core/screen_reader: the accessibility
tree of the foreground window plus OCR, and — when the brain can see — a
screenshot with each element numbered), decides ONE action, performs it with
the real mouse and keyboard, and looks again. It works with local models
because it never asks for pixel coordinates: the model picks an element number.

Stopping: say "stop" (or press Esc in the HUD), or slam the mouse into a screen
corner — PyAutoGUI's fail-safe aborts immediately.
"""
from __future__ import annotations

import json
import platform
import time

from core import brain_config, llm, runtime, screen_reader

_IS_WIN = platform.system() == "Windows"

_SYSTEM = """You operate a {os} computer with the mouse and keyboard to achieve the user's GOAL.
Each turn you get the current screen: the foreground window, open windows, and a numbered
list of on-screen elements with their type, name and centre coordinates (and, if you can
see, a screenshot with the same numbers drawn on it).

Reply with ONE JSON object and nothing else:
{{"thought": "<one short sentence>", "action": "<action>", ...arguments}}

Actions:
  click        {{"id": N}}            left-click element N
  double_click {{"id": N}}
  right_click  {{"id": N}}
  click_xy     {{"x": X, "y": Y}}     only if no element fits
  type         {{"text": "...", "id": N (optional: click it first), "enter": true|false}}
  press        {{"key": "enter"}}     single key: enter, tab, esc, backspace, delete, up, down, left, right, pageup, pagedown, home, end, f1..f12, win
  hotkey       {{"keys": "ctrl+s"}}  key combination
  scroll       {{"direction": "down"|"up", "amount": 5}}
  focus        {{"title": "part of a window title"}}
  open_app     {{"name": "app name"}}
  run          {{"command": "PowerShell command"}}   for things faster done by command
  wait         {{"seconds": 2}}
  done         {{"summary": "what was accomplished"}}
  fail         {{"reason": "why it cannot be done"}}

Rules: act on what is actually on screen; after typing into a search or address box
usually press enter; if something did not change, try a different approach instead of
repeating; never type passwords or pay for anything unless the goal explicitly says so;
finish with done as soon as the goal is achieved."""


def _pyautogui():
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


def _type_text(text: str) -> None:
    pg = _pyautogui()
    if text.isascii() and len(text) < 200:
        pg.write(text, interval=0.012)
        return
    import pyperclip
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)
    time.sleep(0.05)
    pg.hotkey("ctrl", "v")
    time.sleep(0.15)
    if old is not None:
        try:
            pyperclip.copy(old)
        except Exception:
            pass


def _focus(title: str) -> str:
    if not _IS_WIN:
        return "focus is only implemented on Windows"
    import win32con
    import win32gui
    want = title.lower()
    for hwnd, t in screen_reader.top_windows(60):
        if want in t.lower():
            try:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                # Windows refuses SetForegroundWindow from a background process
                # unless a key event came first; an ALT tap satisfies it.
                pg = _pyautogui()
                pg.press("alt")
                win32gui.SetForegroundWindow(hwnd)
                return f"Focused '{t}'."
            except Exception as e:
                return f"Could not focus '{t}': {e}"
    return f"No window title contains '{title}'."


def _execute(act: dict, obs: screen_reader.Observation) -> str:
    pg = _pyautogui()
    a = str(act.get("action", "")).lower()

    def target():
        try:
            el = obs.find(int(act.get("id")))
        except (TypeError, ValueError):
            el = None
        if el is None:
            raise ValueError(f"there is no element [{act.get('id')}] on this screen")
        return el

    if a in ("click", "double_click", "right_click"):
        el = target()
        x, y = el.center
        if a == "click":
            pg.click(x, y)
        elif a == "double_click":
            pg.doubleClick(x, y)
        else:
            pg.rightClick(x, y)
        return f"{a} on [{el.idx}] {el.kind} '{el.name[:40]}'"
    if a == "click_xy":
        pg.click(int(act.get("x", 0)), int(act.get("y", 0)))
        return f"clicked at ({act.get('x')},{act.get('y')})"
    if a == "type":
        if act.get("id") not in (None, ""):
            el = target()
            pg.click(*el.center)
            time.sleep(0.15)
        text = str(act.get("text", ""))
        _type_text(text)
        if act.get("enter"):
            pg.press("enter")
        return f"typed {len(text)} characters" + (" and pressed enter" if act.get("enter") else "")
    if a == "press":
        key = str(act.get("key", "enter")).lower()
        pg.press(key)
        return f"pressed {key}"
    if a == "hotkey":
        keys = [k.strip().lower() for k in str(act.get("keys", "")).replace(" ", "").split("+") if k.strip()]
        keys = ["win" if k in ("windows", "super", "cmd") else k for k in keys]
        pg.hotkey(*keys)
        return f"pressed {'+'.join(keys)}"
    if a == "scroll":
        amt = int(act.get("amount", 5) or 5)
        clicks = amt * (120 if _IS_WIN else 1)
        pg.scroll(clicks if str(act.get("direction", "down")).lower() == "up" else -clicks)
        return f"scrolled {act.get('direction', 'down')}"
    if a == "focus":
        return _focus(str(act.get("title", "")))
    if a == "open_app":
        from actions.open_app import open_app
        return str(open_app({"app_name": str(act.get("name", ""))}))[:200]
    if a == "run":
        from actions.terminal import terminal
        return str(terminal({"command": str(act.get("command", ""))}))[:800]
    if a == "wait":
        time.sleep(max(0.2, min(10.0, float(act.get("seconds", 1) or 1))))
        return "waited"
    raise ValueError(f"unknown action '{a}'")


def _parse(text: str) -> dict | None:
    text = llm.strip_thinking(text or "")
    for raw in llm._json_objects(text):
        d = llm._loads_loose(raw)
        if isinstance(d, dict) and d.get("action"):
            return d
    return None


def run_goal(goal: str, max_steps: int = 25, speak=None) -> str:
    if not goal.strip():
        return "No goal given."
    try:
        _pyautogui()
    except Exception as e:
        return f"Mouse/keyboard control is unavailable: {e}"
    started = time.monotonic()
    s = llm.settings_for("smart")
    if brain_config.get_brain().get("provider") == "gemini_live":
        s = llm.settings_for("smart", model="gemini-2.5-flash")
    caps = llm.capabilities(s)
    vision_model = brain_config.model_for("vision")
    use_image = bool(caps.get("vision"))
    vs = None
    if not use_image and vision_model and vision_model != s.model:
        vs = llm.settings_for("vision")
        use_image = bool(llm.capabilities(vs).get("vision"))
    system = _SYSTEM.format(os=platform.system())
    history: list[str] = []
    last_sig = ""
    repeats = 0
    for step in range(1, max_steps + 1):
        if (runtime.get_state("interrupt_at") or 0) > started:
            return f"Stopped by the user after {step - 1} steps. " + ("; ".join(history[-3:]))
        obs = screen_reader.observe(with_image=use_image, with_ocr=True)
        user = (f"GOAL: {goal}\nStep {step} of {max_steps}.\n"
                + ("Previous actions:\n" + "\n".join(history[-10:]) + "\n" if history else "")
                + "\nCURRENT SCREEN\n" + obs.text())
        msg: dict = {"role": "user", "content": user}
        if use_image and obs.image is not None:
            im = obs.annotated() or obs.image
            msg["images"] = [llm.image_part(screen_reader.jpeg_bytes(im), "image/jpeg")]
        try:
            ev = llm.chat([{"role": "system", "content": system}, msg], None,
                          s=vs if (vs and use_image) else s, max_tokens=300)
        except Exception as e:
            return f"The model failed during step {step}: {e}"
        act = _parse(ev.text)
        if act is None:
            history.append(f"{step}. (reply was not a JSON action — must reply with JSON only)")
            continue
        a = str(act.get("action", "")).lower()
        if a == "done":
            return f"Done in {step} steps: {act.get('summary', 'goal reached')}"
        if a == "fail":
            return f"Could not finish: {act.get('reason', 'unknown reason')}"
        sig = json.dumps({k: v for k, v in act.items() if k != "thought"}, sort_keys=True)
        repeats = repeats + 1 if sig == last_sig else 0
        last_sig = sig
        if repeats >= 3:
            return f"Stuck repeating the same action ({a}) — stopped. Last steps: " + "; ".join(history[-3:])
        try:
            result = _execute(act, obs)
        except Exception as e:
            if type(e).__name__ == "FailSafeException":
                return "Stopped: the mouse was moved to a screen corner (fail-safe)."
            result = f"ERROR {e}"
        thought = str(act.get("thought", ""))[:120]
        history.append(f"{step}. {a}: {result}" + (f"  (why: {thought})" if thought else ""))
        if runtime.ui() is not None and step % 3 == 0:
            try:
                runtime.ui().write_log(f"[Agent] step {step}: {result[:80]}")
            except Exception:
                pass
        time.sleep(0.7)
    return f"Reached the step limit ({max_steps}). Progress: " + "; ".join(history[-4:])


def computer_agent(parameters: dict, player=None, speak=None) -> str:
    p = parameters or {}
    goal = str(p.get("goal") or p.get("task") or "").strip()
    try:
        steps = max(3, min(60, int(p.get("max_steps") or 25)))
    except (TypeError, ValueError):
        steps = 25
    if player:
        try:
            player.write_log(f"[Agent] goal: {goal[:120]}")
        except Exception:
            pass
    return run_goal(goal, steps, speak)


TOOL = {
    "name": "computer_agent",
    "description": (
        "Autonomously operate the computer's apps like a human — looking at the screen, "
        "clicking, typing, scrolling and using shortcuts step by step — to complete a multi-step "
        "goal inside any application (desktop apps, settings, dialogs, web pages). Use when no "
        "specific tool can do the job directly. Give the complete goal in one sentence."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {"type": "STRING", "description": "The full goal, e.g. 'In Notepad, write a shopping list and save it to the Desktop as list.txt'"},
            "max_steps": {"type": "INTEGER", "description": "Step limit (default 25)"},
        },
        "required": ["goal"],
    },
    "handler": computer_agent,
}
