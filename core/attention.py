"""
Deciding what to do with something the microphone heard.

Pure functions, so they can be tested without audio:

  addressed_by_name   was the assistant called by name ("Jarvis, …", "ok jarvis")?
  echo_fraction       how much of a transcript is just our own voice coming
                      back through the speakers
  is_stop_command     "stop", "wait", "enough", "ruko", "bas" — cut speech now
  confirm_answer      a spoken yes/no to a pending confirmation, decided by
                      matching the words themselves — never by the model, so the
                      model can never confirm its own irreversible actions
"""
from __future__ import annotations

import difflib
import re

# Split on spaces and punctuation rather than matching \w: Python's \w leaves
# out combining marks, which would cut Hindi and other Indic words into pieces.
_WORD = re.compile(r"[^\s.,!?;:\"()\[\]{}…।|/\\-]+", re.U)


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "")]


def _near(a: str, b: str, cutoff: float) -> bool:
    if a == b:
        return True
    if len(a) < 3 or len(b) < 3:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= cutoff


# Common ways speech recognition mangles "Jarvis".
_JARVIS_VARIANTS = {"jarvis", "jarvi", "jervis", "jarwis", "jarves", "jarvus", "javis",
                    "jarvis's", "jarvish", "jaarvis", "garvis", "harvis", "charvis", "जार्विस",
                    "जारविस"}


def addressed_by_name(text: str, name: str, aliases=()) -> bool:
    name = (name or "jarvis").lower().replace(".", "").strip()
    targets = {name, name.replace(" ", "")} | {str(a).lower().strip() for a in aliases if a}
    if name == "jarvis":
        targets |= _JARVIS_VARIANTS
    ws = words(text)
    joined = " ".join(ws)
    for t in targets:
        if " " in t and t in joined:
            return True
    for w in ws:
        for t in targets:
            if " " not in t and _near(w, t, 0.8):
                return True
    return False


def strip_name(text: str, name: str) -> str:
    """'Jarvis, open notepad' → 'open notepad' (keeps the rest untouched)."""
    pat = re.compile(r"^\s*(hey|hi|ok|okay|yo|hello|oye|arre)?\s*,?\s*" + re.escape(name or "jarvis")
                     + r"\s*[,.!?:]*\s*", re.I)
    out = pat.sub("", text or "", count=1).strip()
    return out or (text or "").strip()


def echo_fraction(heard: str, spoken_recently: list[str]) -> float:
    """Share of the heard words that also occur in what we just said."""
    hw = [w for w in words(heard) if len(w) > 1]
    if not hw:
        return 1.0
    pool = set()
    for s in spoken_recently:
        pool.update(words(s))
    if not pool:
        return 0.0
    hit = 0
    for w in hw:
        if w in pool or any(_near(w, p, 0.85) for p in pool if abs(len(p) - len(w)) <= 2):
            hit += 1
    return hit / len(hw)


_STOP = {"stop", "wait", "enough", "quiet", "silence", "pause", "hold", "cancel", "shut",
         "ruko", "ruk", "bas", "chup", "rukiye", "रुको", "बस", "चुप", "dur", "yeter", "sus",
         "arrête", "halt", "basta", "para", "stopp"}


def is_stop_command(text: str) -> bool:
    ws = words(text)
    return bool(ws) and len(ws) <= 5 and any(w in _STOP for w in ws)


def is_self_echo(heard: str, spoken_recently: list[str]) -> bool:
    """True when a transcript is clearly a replay of our own recent words.

    Short answers ("confirm", "yes confirm") are never treated as echo even if
    those words were just said — the timing checks (nothing heard while
    speaking or during the echo tail counts) are what keep echo out; this only
    catches a longer phrase that slipped through."""
    return len(words(heard)) >= 3 and echo_fraction(heard, spoken_recently) >= 0.8


_YES = {"yes", "yeah", "yep", "yup", "confirm", "confirmed", "sure", "ok", "okay", "go", "proceed",
        "do", "affirmative", "correct", "haan", "han", "ha", "haa", "ji", "theek", "thik", "chalo",
        "हाँ", "हां", "जी", "ठीक", "evet", "tamam", "sí", "si", "oui", "ja", "da"}
_NO = {"no", "nope", "cancel", "don't", "dont", "stop", "abort", "negative", "never", "wait",
       "nahi", "nahin", "mat", "ruko", "नहीं", "मत", "रुको", "hayır", "hayir", "iptal", "non",
       "nein", "net"}


def confirm_answer(text: str) -> bool | None:
    """True = confirmed, False = refused, None = not an answer to a yes/no question."""
    ws = words(text)
    if not ws or len(ws) > 8:
        return None
    has_no = any(w in _NO for w in ws) or "not" in ws
    has_yes = any(w in _YES for w in ws)
    if has_no:
        return False
    if has_yes:
        return True
    return None
