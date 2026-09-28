"""
Turning a model's streamed text into sentences worth saying out loud.

A voice assistant must start talking before the model has finished writing, so
text is cut into sentences as it arrives and each one goes to the voice while
the next is still being generated. Along the way three kinds of text must never
be spoken:

  * reasoning       <think>…</think>, which some local models always emit
  * tool calls      <tool_call>{…}</tool_call> or a bare JSON object, which the
                    prompted-tools mode and many small models write as text
  * code / markdown code fences, table pipes, bullets, **bold**, # headers

`SpeechStream.feed()` takes raw deltas and returns the complete, cleaned
sentences that are ready; `flush()` returns whatever remains at the end.
"""
from __future__ import annotations

import re

_SENT_END = re.compile(r"([.!?।。！？]+[\"')\]]*)\s+|\n+")
_URL = re.compile(r"https?://\S+")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_EMPH = re.compile(r"(\*\*|__|\*|_|~~|`)(?=\S)(.+?)(?<=\S)\1")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.M)
_HEADER = re.compile(r"^\s*#{1,6}\s*", re.M)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")

# Gemma 4 writes its reasoning as <|channel>thought…<channel|> and raw calls as
# <|tool_call>call:name{…}<tool_call|> when a server does not parse them.
_OPENERS = ("<think>", "<tool_call>", "```", "<tool_result", "<|channel>", "<|tool_call>",
            "<|tool_response>")
_CLOSERS = {"<think>": "</think>", "<tool_call>": "</tool_call>", "```": "```",
            "<tool_result": "</tool_result>", "<|channel>": "<channel|>",
            "<|tool_call>": "<tool_call|>", "<|tool_response>": "<tool_response|>"}


def clean_for_speech(text: str) -> str:
    t = text or ""
    t = _MD_LINK.sub(r"\1", t)
    t = _URL.sub("the link", t)
    t = _HEADER.sub("", t)
    t = _BULLET.sub("", t)
    for _ in range(2):
        t = _EMPH.sub(r"\2", t)
    t = t.replace("|", " ").replace("#", "").replace("*", "")
    t = _EMOJI.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


class SpeechStream:
    """Incremental sentence splitter with hidden-region suppression."""

    def __init__(self, first_chunk_chars: int = 60, max_chars: int = 220):
        self._buf = ""           # visible text not yet emitted
        self._hold = ""          # text that might be the start of a hidden tag
        self._hidden: str | None = None   # closer we are waiting for
        self._hidden_buf = ""
        self._emitted_any = False
        self._first = first_chunk_chars
        self._max = max_chars
        self.code_seen = False
        self._json_guard = None   # None = undecided, True = looks like JSON

    # -- region handling ------------------------------------------------------
    def _route(self, text: str) -> None:
        """Split incoming text into visible/hidden according to tags."""
        s = self._hold + text
        self._hold = ""
        while s:
            if self._hidden:
                idx = s.find(self._hidden)
                if idx < 0:
                    # Hidden text is discarded; only a tail that could be the
                    # first characters of the closer is kept for next time.
                    keep = len(self._hidden) - 1
                    self._hold = s[-keep:] if len(s) > keep else s
                    return
                self._hidden_buf += s[:idx]
                s = s[idx + len(self._hidden):]
                if self._hidden == "```":
                    self.code_seen = True
                self._hidden = None
                self._hidden_buf = ""
                continue
            # find earliest opener
            best, best_i = None, len(s)
            for op in _OPENERS:
                i = s.find(op)
                if 0 <= i < best_i:
                    best, best_i = op, i
            if best is None:
                # hold back a suffix that could be the start of an opener
                hold = 0
                for op in _OPENERS:
                    for k in range(min(len(op) - 1, len(s)), 0, -1):
                        if s.endswith(op[:k]):
                            hold = max(hold, k)
                            break
                if hold:
                    self._buf += s[:-hold]
                    self._hold = s[-hold:]
                else:
                    self._buf += s
                return
            self._buf += s[:best_i]
            s = s[best_i + len(best):]
            self._hidden = _CLOSERS[best]
            if best == "<tool_result":
                self._hidden = "</tool_result>"

    # -- public ---------------------------------------------------------------
    def feed(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._route(delta)
        # A reply that opens with "{" or "[" is almost certainly a tool call
        # or data written as text — hold everything until the end.
        if self._json_guard is None:
            head = self._buf.lstrip()
            if head:
                self._json_guard = head[0] in "{["
        if self._json_guard:
            return []
        return self._drain(final=False)

    def flush(self) -> list[str]:
        if self._hidden is None and self._hold:
            self._buf += self._hold
            self._hold = ""
        if self._json_guard:
            # Emit only if it did not turn out to be JSON after all.
            txt = self._buf.strip()
            if txt[:1] in "{[":
                self._buf = ""
                return []
        out = self._drain(final=True)
        if self.code_seen and not self._emitted_any and not out:
            out = ["I've put the code on screen."]
        return out

    def _drain(self, final: bool) -> list[str]:
        out: list[str] = []
        while True:
            m = _SENT_END.search(self._buf)
            limit = self._first if not self._emitted_any else self._max
            if m:
                end = m.end()
                piece = self._buf[:end]
                self._buf = self._buf[end:]
                self._emit(piece, out)
                continue
            if len(self._buf) > limit:
                # No sentence end yet; break early on a clause boundary so the
                # voice can start — the first chunk especially.
                win = min(len(self._buf), limit * 2)
                cut = max(self._buf.rfind(", ", 0, win), self._buf.rfind("; ", 0, win),
                          self._buf.rfind(" — ", 0, win), self._buf.rfind(": ", 0, win))
                if cut > 20:
                    piece = self._buf[:cut + 1]
                    self._buf = self._buf[cut + 1:]
                    self._emit(piece, out)
                    continue
                if len(self._buf) > self._max * 1.5:
                    sp = self._buf.rfind(" ", 0, self._max)
                    if sp > 20:
                        piece = self._buf[:sp]
                        self._buf = self._buf[sp:]
                        self._emit(piece, out)
                        continue
            break
        if final and self._buf.strip():
            self._emit(self._buf, out)
            self._buf = ""
        return out

    def _emit(self, piece: str, out: list[str]) -> None:
        txt = clean_for_speech(piece)
        if txt and re.search(r"\w", txt):
            out.append(txt)
            self._emitted_any = True


def visible_text(text: str) -> str:
    """The part of a full reply a person should read in the log."""
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I)
    t = re.sub(r"<tool_call>.*?(</tool_call>|$)", "", t, flags=re.S)
    return t.strip()
