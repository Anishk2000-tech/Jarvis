"""
The AI BRAIN & VOICE screen — which model thinks, how it hears and speaks, and
what it pays attention to.

Shown in two situations:
  * first launch (first_run=True): the only thing between a fresh install and a
    working assistant, so it asks for the minimum — pick a brain, press
    INITIALISE — and fills every other field with a sensible default;
  * later, from ⚙ SETUP → AI BRAIN & VOICE, with everything editable.

It only reads and writes config/api_keys.json through core.brain_config; the
running engine picks the changes up on its next reconnect (or, when switching
between Gemini Live and a local brain, after an automatic restart).
"""
from __future__ import annotations

import os
import sys
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from core import brain_config
from ui import C

_FONT = "Courier New"

_STT_MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo", "base.en", "small.en", "distil-large-v3"]
_LANGS = ["auto", "en", "hi", "bn", "ta", "te", "mr", "gu", "ur", "es", "fr", "de", "it", "pt", "tr",
          "ru", "ar", "ja", "zh", "ko", "id"]
_TTS = ["edge", "sapi", "piper", "kokoro", "elevenlabs", "openai"]
_TTS_LABELS = {"edge": "edge — Microsoft neural voices (free, online)",
               "sapi": "sapi — Windows built-in voices (offline)",
               "piper": "piper — offline neural voices (~60 MB)",
               "kokoro": "kokoro — offline, most natural (~330 MB)",
               "elevenlabs": "elevenlabs — cloud, API key",
               "openai": "openai — OpenAI speech API"}
_PIPER = ["en_GB-alan-medium", "en_GB-northern_english_male-medium", "en_US-ryan-high",
          "en_US-lessac-medium", "en_US-amy-medium", "hi_IN-pratham-medium", "hi_IN-priyamvada-medium"]
_KOKORO = ["bm_george", "bm_lewis", "bm_fable", "am_michael", "am_adam", "af_heart", "bf_emma",
           "hm_omega", "hf_alpha"]


class BrainSettingsOverlay(QWidget):
    saved = pyqtSignal(bool)                  # True = the app must restart to apply
    _models_sig = pyqtSignal(list, str)       # models, error
    _status_sig = pyqtSignal(str, str, bool)  # which label, text, ok

    def __init__(self, parent=None, first_run: bool = False, message: str = ""):
        super().__init__(parent)
        self._first = first_run
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("BrainOverlay")
        self.setStyleSheet(f"""
            QWidget#BrainOverlay {{ background: rgba(0, 6, 10, 248);
                border: 1px solid {C.BORDER_B}; border-radius: 6px; }}
        """)
        self._w: dict[str, QWidget] = {}
        self._rows: dict[str, QWidget] = {}
        self._status: dict[str, QLabel] = {}
        self._models_sig.connect(self._on_models)
        self._status_sig.connect(self._on_status)
        self._pull_cancel = threading.Event()

        self._fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; border: 1px solid {C.BORDER}; "
                    f"border-radius: 3px; padding: 3px 7px; }} QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")
        self._cs = (f"QComboBox {{ background: #000d12; color: {C.TEXT}; border: 1px solid {C.BORDER}; "
                    f"border-radius: 3px; padding: 2px 7px; }} QComboBox QAbstractItemView {{ background: #000d12; "
                    f"color: {C.TEXT}; selection-background-color: {C.PRI_GHO}; }}")

        b = brain_config.get_brain()
        v = brain_config.get_voice_cfg()
        s = brain_config.get_senses()
        self._hw = {}
        self._rec = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(6)
        if first_run:
            root.addWidget(self._lbl("◈  INITIALISATION REQUIRED", 13, True, align=Qt.AlignmentFlag.AlignCenter))
            root.addWidget(self._lbl(message or "Choose the brain that powers the assistant. Local brains run "
                                     "privately on this PC; cloud brains need an API key.", 8, color=C.TEXT_DIM,
                                     align=Qt.AlignmentFlag.AlignCenter))
        else:
            root.addWidget(self._lbl("🧠  AI BRAIN & VOICE", 12, True))
            if message:
                root.addWidget(self._lbl(message, 8, color=C.ACC2))
        root.addWidget(self._sep())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            f"QScrollBar:vertical {{ background: {C.DARK}; width: 8px; margin: 0; border: none; }}"
            f"QScrollBar::handle:vertical {{ background: {C.PRI_DIM}; min-height: 30px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {C.PRI}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._form = QVBoxLayout(inner)
        self._form.setContentsMargins(0, 0, 8, 0)
        self._form.setSpacing(4)

        # ── brain ────────────────────────────────────────────────────────────
        self._section("BRAIN")
        prov = QComboBox()
        prov.setStyleSheet(self._cs)
        prov.setFont(QFont(_FONT, 9))
        order = ["ollama", "lmstudio", "gemini_live", "openai", "anthropic", "gemini"]
        for p in order:
            prov.addItem(brain_config.PROVIDER_LABELS[p], p)
        cur = b.get("provider") or "ollama"
        prov.setCurrentIndex(max(0, order.index(cur) if cur in order else 0))
        prov.currentIndexChanged.connect(self._on_provider)
        self._w["provider"] = prov
        self._field("provider_row", "Brain", prov)

        self._hint = self._lbl("", 8, color=C.ACC2)
        self._form.addWidget(self._hint)

        preset = QComboBox()
        preset.setStyleSheet(self._cs)
        preset.setFont(QFont(_FONT, 8))
        preset.addItem("— choose a service —", "")
        for name, url in brain_config.OPENAI_COMPAT_PRESETS.items():
            preset.addItem(name, url)
        preset.currentIndexChanged.connect(lambda _i: self._apply_preset())
        self._w["preset"] = preset
        self._field("preset_row", "Service", preset)

        self._line("base_url", str(b.get("base_url") or ""), "Server address")
        key_default = brain_config.gemini_key() if cur in ("gemini_live", "gemini") and not b.get("api_key") \
            else str(b.get("api_key") or "")
        self._line("api_key", key_default, "API key", password=True)

        models_row = QWidget()
        mr = QHBoxLayout(models_row)
        mr.setContentsMargins(0, 0, 0, 0)
        mr.setSpacing(4)
        chat = self._combo_edit(str(b.get("model") or ""))
        self._w["model"] = chat
        mr.addWidget(chat, 1)
        refresh = self._small_btn("↻", "List the models on the server")
        refresh.clicked.connect(self._refresh_models)
        mr.addWidget(refresh)
        pull = self._small_btn("⬇", "Download this model into Ollama")
        pull.clicked.connect(self._pull_model)
        self._w["pull_btn"] = pull
        mr.addWidget(pull)
        self._field("model_row", "Conversation model", models_row)
        self._w["smart_model"] = self._combo_edit(str(b.get("smart_model") or ""), "same as conversation")
        self._field("smart_row", "Agent / long-task model (optional)", self._w["smart_model"])
        self._w["vision_model"] = self._combo_edit(str(b.get("vision_model") or ""), "same, if it can see")
        self._field("vision_row", "Vision model (screen & camera)", self._w["vision_model"])
        self._status["brain"] = self._lbl("", 8, color=C.TEXT_DIM)
        self._form.addWidget(self._status["brain"])

        test = self._btn("TEST CONNECTION")
        test.clicked.connect(self._test_brain)
        self._rows["test_row"] = test
        self._form.addWidget(test)

        self._choice("num_ctx", "Context window (tokens)", ["8192", "16384", "32768"], str(b.get("num_ctx", 16384)))
        self._choice("tool_profile", "Tool set", ["auto", "full", "lean"], str(b.get("tool_profile", "auto")))

        # ── speech in ────────────────────────────────────────────────────────
        self._section("HEARING  (local brains)")
        self._choice("stt_engine", "Speech recognition", ["whisper", "openai"], v.get("stt_engine", "whisper"),
                     labels={"whisper": "whisper — on this PC (private)",
                             "openai": "API — Groq / OpenAI (fastest)"})
        self._choice("stt_model", "Whisper model", _STT_MODELS, v.get("stt_model", "small"))
        self._choice("stt_device", "Whisper runs on", ["cpu", "cuda", "auto"], v.get("stt_device", "cpu"))
        self._choice("stt_language", "Language", _LANGS, v.get("stt_language", "auto"))
        self._line("stt_base_url", v.get("stt_base_url", ""), "Transcription API URL")
        self._line("stt_api_key", v.get("stt_api_key", ""), "Transcription API key", password=True)
        self._line("stt_api_model", v.get("stt_api_model", ""), "Transcription model")
        self._choice("end_silence_ms", "Pause that ends your sentence (ms)",
                     ["400", "550", "700", "900", "1200"], str(v.get("end_silence_ms", 700)))

        # ── speech out ───────────────────────────────────────────────────────
        self._section("VOICE  (local brains)")
        self._choice("tts_engine", "Voice engine", _TTS, v.get("tts_engine", "edge"), labels=_TTS_LABELS)
        from core.tts_engine import EDGE_VOICES
        tv = self._combo_edit(v.get("tts_voice", "en-GB-RyanNeural"))
        for name, desc in EDGE_VOICES:
            tv.addItem(f"{name}", name)
        tv.setCurrentText(v.get("tts_voice", "en-GB-RyanNeural"))
        self._w["tts_voice"] = tv
        self._field("tts_voice_row", "Edge voice", tv)
        self._choice("piper_voice", "Piper voice", _PIPER, v.get("piper_voice", _PIPER[0]), editable=True)
        self._choice("kokoro_voice", "Kokoro voice", _KOKORO, v.get("kokoro_voice", _KOKORO[0]), editable=True)
        self._line("elevenlabs_api_key", v.get("elevenlabs_api_key", ""), "ElevenLabs API key", password=True)
        self._line("elevenlabs_voice_id", v.get("elevenlabs_voice_id", ""), "ElevenLabs voice id")
        self._choice("tts_rate", "Speaking speed (%)", ["-20", "-10", "0", "10", "20", "30"],
                     str(v.get("tts_rate", 0)))
        self._slider("voice_volume", "Voice volume (above 100% = boost, like VLC)", 0, 200,
                     int(v.get("voice_volume", 100)), "%")
        tv_btn = self._btn("▶  TEST VOICE")
        tv_btn.clicked.connect(self._test_voice)
        self._form.addWidget(tv_btn)
        self._status["voice"] = self._lbl("", 8, color=C.TEXT_DIM)
        self._form.addWidget(self._status["voice"])

        # ── senses ───────────────────────────────────────────────────────────
        self._section("ATTENTION")
        self._choice("listen_mode", "Listening", ["active", "ambient"], s.get("listen_mode", "active"),
                     labels={"active": "active — answers everything it hears",
                             "ambient": "ambient — hears the room, answers its name"})
        self._toggle("barge_in", "Interrupt it by talking over it", s.get("barge_in", True))
        self._toggle("voice_confirm", "Confirm dangerous actions by voice", s.get("voice_confirm", True))
        self._toggle("journal", "Keep a local transcript of what it hears", s.get("journal", True))
        self._toggle("face_presence", "Face recognition watching (webcam)", s.get("face_presence", False))
        self._toggle("owner_only", "Obey only while my face is in view", s.get("owner_only", False))
        self._toggle("greet_on_arrival", "Greet me when I come back", s.get("greet_on_arrival", True))
        self._toggle("lock_on_leave", "Lock the PC when I walk away", s.get("lock_on_leave", False))
        self._toggle("alert_unknown_faces", "Alert me about strangers at the PC", s.get("alert_unknown_faces", False))

        # ── live vision ──────────────────────────────────────────────────────
        self._section("LIVE VISION  (always-on webcam)")
        self._form.addWidget(self._lbl(
            "The webcam stays on: people, faces and objects are recognised on the CPU a few times a "
            "second, and the vision model describes the scene when it changes. Best with a brain that "
            "can see (gemma4:e4b, qwen2.5vl, gemma3) so no second model is loaded.", 8, color=C.TEXT_DIM))
        self._toggle("live_vision", "Live vision on", s.get("live_vision", False))
        self._choice("vision_proactive", "Speaks up about what it sees", ["off", "low", "normal", "chatty"],
                     s.get("vision_proactive", "low"),
                     labels={"off": "off — only when asked", "low": "low — greets people, notices strangers",
                             "normal": "normal — also reacts to notable changes",
                             "chatty": "chatty — also comments now and then"})
        self._choice("vision_fps", "Looks per second (CPU)", ["1", "2", "3", "5"], str(s.get("vision_fps", 2)))
        self._toggle("vision_captions", "Describe the scene with the vision model", s.get("vision_captions", True))
        self._choice("vision_caption_seconds", "At most one description every (s)", ["30", "60", "120", "300"],
                     str(s.get("vision_caption_seconds", 60)))
        self._toggle("vision_attach", "Show it the live frame for visual questions", s.get("vision_attach", True))
        self._toggle("vision_preview", "Small live view in the HUD", s.get("vision_preview", True))
        self._choice("live_video_seconds", "Gemini Live: send a frame every (s)", ["2", "3", "5", "10"],
                     str(s.get("live_video_seconds", 3)))

        # ── cctv ─────────────────────────────────────────────────────────────
        self._section("CCTV CAMERAS")
        self._form.addWidget(self._lbl(
            "WiFi / IP cameras (RTSP, ONVIF, MJPEG, Home Assistant). Home mode announces people by voice, "
            "night and away modes send alerts with photos to Telegram.", 8, color=C.TEXT_DIM))
        wall = self._btn("📹  OPEN CAMERA WALL — ADD / VIEW CAMERAS")
        wall.clicked.connect(self._open_cctv)
        self._form.addWidget(wall)

        # ── web search ───────────────────────────────────────────────────────
        sc = brain_config.get_search_cfg()
        self._section("WEB SEARCH")
        self._toggle("auto_search", "Look things up by itself (news, prices, anything it doesn't know)",
                     sc.get("auto_search", True))
        self._toggle("google_ai", "Include Google's AI answer (uses the Gemini key, free tier)",
                     sc.get("google_ai", True))
        self._choice("search_provider", "Search engine", ["auto", "duckduckgo", "tavily", "brave", "serper",
                                                          "searxng"], sc.get("provider", "auto"),
                     labels={"auto": "auto — several free engines at once",
                             "duckduckgo": "free meta-search only",
                             "tavily": "Tavily (AI answer, free key: tavily.com)",
                             "brave": "Brave Search API (free key)",
                             "serper": "Serper — Google results (free key: serper.dev)",
                             "searxng": "SearXNG — your own search server"})
        self._line("tavily_key", sc.get("tavily_key", ""), "Tavily API key", password=True)
        self._line("brave_key", sc.get("brave_key", ""), "Brave Search API key", password=True)
        self._line("serper_key", sc.get("serper_key", ""), "Serper API key", password=True)
        self._line("searxng_url", sc.get("searxng_url", ""), "SearXNG address",
                   placeholder="http://localhost:8888")
        self._line("search_region", sc.get("region", "auto"), "Region (auto, in-en, us-en, uk-en…)")
        self._toggle("read_pages", "Open and read the top pages", sc.get("read_pages", True))
        self._w["search_provider"].currentIndexChanged.connect(lambda _i: self._on_search_provider())
        self._on_search_provider()

        # ── learning ─────────────────────────────────────────────────────────
        lc = brain_config.get_learning_cfg()
        self._section("LEARNING")
        self._form.addWidget(self._lbl(
            "While you are not talking to it, it distils what it saw, heard and did into lasting facts "
            "(memory/knowledge.jsonl on this PC) and uses them in every conversation.", 8, color=C.TEXT_DIM))
        self._toggle("learn_enabled", "Learn on its own", lc.get("enabled", True))
        self._toggle("learn_room", "…from conversations it overhears", lc.get("from_room", True))
        self._toggle("learn_camera", "…from what its cameras see", lc.get("from_camera", True))
        self._toggle("learn_screen", "…from which apps and windows you use", lc.get("from_screen", True))
        self._toggle("learn_tools", "…from which of its actions worked or failed", lc.get("from_tools", True))
        self._choice("consolidate_minutes", "Think it over every (min)", ["5", "10", "20", "30", "60"],
                     str(lc.get("consolidate_minutes", 10)))
        self._line("embed_model", lc.get("embed_model", ""), "Embedding model for recall (optional, Ollama)",
                   placeholder="e.g. nomic-embed-text")
        lrow = QWidget()
        ll = QHBoxLayout(lrow)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        show = self._btn("WHAT HAS IT LEARNED?")
        show.clicked.connect(self._show_learned)
        forget = self._btn("FORGET ALL LEARNED")
        forget.clicked.connect(self._forget_learned)
        ll.addWidget(show)
        ll.addWidget(forget)
        self._form.addWidget(lrow)
        self._status["learn"] = self._lbl("", 8, color=C.TEXT_DIM)
        self._form.addWidget(self._status["learn"])

        # ── integrations ─────────────────────────────────────────────────────
        self._section("REMOTE & EXTENSIONS")
        tg = {}
        try:
            import json
            tg = json.loads(brain_config.CONFIG_FILE.read_text(encoding="utf-8")).get("telegram", {}) or {}
        except Exception:
            pass
        self._line("telegram_token", tg.get("bot_token", ""), "Telegram bot token (from @BotFather)", password=True)
        mcp = self._btn("OPEN MCP SERVERS FILE")
        mcp.clicked.connect(self._open_mcp)
        self._form.addWidget(mcp)

        self._form.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        ok = self._btn("▸  INITIALISE SYSTEMS" if first_run else "▸  SAVE && APPLY", primary=True)
        ok.clicked.connect(self._save)
        row.addWidget(ok)
        if not first_run:
            close = self._btn("CLOSE")
            close.clicked.connect(self.hide)
            row.addWidget(close)
        root.addLayout(row)
        self._status["save"] = self._lbl("", 8, color=C.RED)
        root.addWidget(self._status["save"])

        self._on_provider()
        threading.Thread(target=self._detect_hw, daemon=True).start()

    # ── widget helpers ───────────────────────────────────────────────────────
    def _lbl(self, txt, fs=9, bold=False, color=None, align=Qt.AlignmentFlag.AlignLeft):
        w = QLabel(txt)
        w.setAlignment(align)
        w.setWordWrap(True)
        # Wrapped text in a scroll area: let the label grow to its wrapped
        # height instead of being squeezed to the first lines.
        w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        w.setFont(QFont(_FONT, fs, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        w.setStyleSheet(f"color: {color or C.PRI}; background: transparent;")
        return w

    def _sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        return s

    def _section(self, title: str):
        self._form.addSpacing(6)
        self._form.addWidget(self._lbl(title, 10, True))

    def _field(self, key: str, label: str, widget: QWidget):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self._lbl(label.upper(), 7, color=C.TEXT_DIM))
        lay.addWidget(widget)
        self._rows[key] = box
        self._form.addWidget(box)

    def _line(self, key: str, value: str, label: str, password=False, placeholder=""):
        w = QLineEdit(value or "")
        w.setFont(QFont(_FONT, 9))
        w.setFixedHeight(28)
        w.setStyleSheet(self._fs)
        if password:
            w.setEchoMode(QLineEdit.EchoMode.Password)
        if placeholder:
            w.setPlaceholderText(placeholder)
        self._w[key] = w
        self._field(key + "_row", label, w)
        return w

    def _combo_edit(self, value: str, placeholder: str = "") -> QComboBox:
        c = QComboBox()
        c.setEditable(True)
        c.setStyleSheet(self._cs)
        c.setFont(QFont(_FONT, 9))
        c.setFixedHeight(28)
        c.setCurrentText(value)
        if placeholder and c.lineEdit():
            c.lineEdit().setPlaceholderText(placeholder)
        return c

    def _choice(self, key, label, options, current, labels=None, editable=False):
        c = QComboBox()
        c.setEditable(editable)
        c.setStyleSheet(self._cs)
        c.setFont(QFont(_FONT, 9))
        c.setFixedHeight(28)
        for o in options:
            c.addItem((labels or {}).get(o, o), o)
        idx = c.findData(current)
        if idx >= 0:
            c.setCurrentIndex(idx)
        elif editable:
            c.setCurrentText(str(current))
        self._w[key] = c
        self._field(key + "_row", label, c)
        return c

    def _toggle(self, key, label, value):
        b = QPushButton()
        b.setCheckable(True)
        b.setChecked(bool(value))
        b.setFixedHeight(26)
        b.setFont(QFont(_FONT, 8, QFont.Weight.Bold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_toggle(b)
        b.toggled.connect(lambda _=False, x=b: self._style_toggle(x))
        self._w[key] = b
        self._field(key + "_row", label, b)

    def _style_toggle(self, btn):
        on = btn.isChecked()
        btn.setText("ON" if on else "OFF")
        if on:
            btn.setStyleSheet(f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI}; "
                              f"border: 1px solid {C.PRI}; border-radius: 3px; }}")
        else:
            btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; "
                              f"border: 1px solid {C.BORDER}; border-radius: 3px; }}")

    def _slider(self, key, label, lo, hi, value, suffix=""):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setSingleStep(5)
        sl.setPageStep(25)
        sl.setValue(int(value))
        sl.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 4px; background: {C.BORDER}; border-radius: 2px; }}"
            f"QSlider::sub-page:horizontal {{ background: {C.PRI_DIM}; border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ background: {C.PRI}; width: 12px; margin: -5px 0; border-radius: 6px; }}")
        val = self._lbl(f"{int(value)}{suffix}", 9, True)
        val.setFixedWidth(52)
        sl.valueChanged.connect(lambda v, l=val: l.setText(f"{v}{suffix}"))
        lay.addWidget(sl, 1)
        lay.addWidget(val)
        self._w[key] = sl
        self._field(key + "_row", label, box)
        return sl

    def _on_search_provider(self):
        prov = self._val("search_provider") or "auto"
        for key, owner in (("tavily_key", "tavily"), ("brave_key", "brave"), ("serper_key", "serper"),
                           ("searxng_url", "searxng")):
            row = self._rows.get(key + "_row")
            if row is not None:
                row.setVisible(prov == owner)

    def _open_cctv(self):
        win = self.window()
        if hasattr(win, "_open_cctv"):
            self.hide()
            win._open_cctv()

    def _show_learned(self):
        try:
            from core import knowledge
            st = knowledge.store()
            st.load()
            facts = st.recent(400)
            if not facts:
                self._on_status("learn", "Nothing learned yet — it learns while idle, every few minutes.", True)
                return
            text = "\n".join(f"• {f['text']}  [{f.get('kind', 'fact')}, ×{f.get('count', 1)}, "
                             f"{f.get('last', '')[:10]}]" for f in facts)
            win = self.window()
            if hasattr(win, "_content_sig"):
                win._content_sig.emit(f"LEARNED — {len(st.facts)} FACTS", text)
            self._on_status("learn", f"{len(st.facts)} facts — shown in the content panel.", True)
        except Exception as e:
            self._on_status("learn", f"Could not read the knowledge: {e}", False)

    def _forget_learned(self):
        if not getattr(self, "_forget_armed", False):
            self._forget_armed = True
            self._on_status("learn", "Press FORGET ALL LEARNED again to erase everything it learned.", False)
            return
        self._forget_armed = False
        try:
            from core import knowledge
            n = knowledge.store().clear()
            self._on_status("learn", f"Forgot {n} learned facts.", True)
        except Exception as e:
            self._on_status("learn", f"Could not clear: {e}", False)

    def _btn(self, text, primary=False):
        b = QPushButton(text)
        b.setFixedHeight(32 if primary else 28)
        b.setFont(QFont(_FONT, 9 if primary else 8, QFont.Weight.Bold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        col = C.PRI if primary else C.TEXT_MED
        border = C.PRI_DIM if primary else C.BORDER
        b.setStyleSheet(f"QPushButton {{ background: transparent; color: {col}; border: 1px solid {border}; "
                        f"border-radius: 3px; }} QPushButton:hover {{ background: {C.PRI_GHO}; "
                        f"border: 1px solid {C.PRI}; color: {C.PRI}; }}")
        return b

    def _small_btn(self, text, tip):
        b = QPushButton(text)
        b.setFixedSize(30, 28)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton {{ background: #000d12; color: {C.PRI}; border: 1px solid {C.BORDER}; "
                        f"border-radius: 3px; }} QPushButton:hover {{ border-color: {C.PRI}; }}")
        return b

    def _val(self, key):
        w = self._w.get(key)
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QComboBox):
            if w.isEditable():
                return w.currentText().strip()
            data = w.currentData()
            return data if data is not None else w.currentText()
        if isinstance(w, QPushButton):
            return w.isChecked()
        if isinstance(w, QSlider):
            return w.value()
        return None

    # ── behaviour ────────────────────────────────────────────────────────────
    def _provider(self) -> str:
        return self._w["provider"].currentData() or "ollama"

    def _on_provider(self, *_a):
        p = self._provider()
        prev = getattr(self, "_last_provider", None)
        self._last_provider = p
        if prev is not None and prev != p:
            # A model name belongs to one provider; carry none across a switch.
            for key in ("model", "smart_model", "vision_model"):
                self._w[key].clear()
                self._w[key].setCurrentText("")
        cloud_key = p in ("gemini_live", "openai", "anthropic", "gemini")
        self._rows["preset_row"].setVisible(p == "openai")
        self._rows["base_url_row"].setVisible(
            p != "gemini_live" and not (self._first and p in ("gemini", "anthropic")))
        self._rows["api_key_row"].setVisible(cloud_key)
        for r in ("model_row", "smart_row", "vision_row", "test_row", "num_ctx_row", "tool_profile_row"):
            self._rows[r].setVisible(p != "gemini_live")
        self._w["pull_btn"].setVisible(p == "ollama")
        url = self._w["base_url"]
        known = set(brain_config.DEFAULT_URLS.values())
        if not url.text().strip() or url.text().strip() in known:
            url.setText(brain_config.DEFAULT_URLS.get(p, ""))
        lbl = self._rows["api_key_row"].findChild(QLabel)
        if lbl:
            lbl.setText("GEMINI API KEY  (aistudio.google.com)" if p in ("gemini_live", "gemini")
                        else "ANTHROPIC API KEY" if p == "anthropic" else "API KEY")
        if p in ("gemini_live", "gemini") and not self._w["api_key"].text():
            self._w["api_key"].setText(brain_config.gemini_key())
        if not self._w["model"].currentText().strip() or self._w["model"].currentText() in \
                brain_config.DEFAULT_MODELS.values():
            default = self._rec.get("model") if p == "ollama" and self._rec else brain_config.DEFAULT_MODELS.get(p, "")
            self._w["model"].setCurrentText(default or "")
        hints = {
            "gemini_live": "Realtime voice from Google — the most natural conversation. Needs a free key "
                           "from aistudio.google.com. Audio is processed by Google.",
            "ollama": "Private and free. Install Ollama from ollama.com — the model downloads automatically "
                      "on first start (or press ⬇).",
            "lmstudio": "Private and free. In LM Studio: load a model, open the Developer tab and start the "
                        "server (port 1234).",
            "openai": "Any OpenAI-compatible service. Groq and OpenRouter have free tiers.",
            "anthropic": "Claude models. Needs an API key from console.anthropic.com.",
            "gemini": "Gemini text models with this app's own speech pipeline (free tier available).",
        }
        extra = f"\nRecommended here: {self._rec.get('why', '')}" if p == "ollama" and self._rec else ""
        hw = f"\n{self._hw_line}" if getattr(self, "_hw_line", "") else ""
        self._hint.setText(hints.get(p, "") + extra + hw)

    def _apply_preset(self):
        url = self._w["preset"].currentData()
        if url:
            self._w["base_url"].setText(url)

    def _detect_hw(self):
        try:
            self._hw = brain_config.detect_hardware()
            self._rec = brain_config.recommend(self._hw)
            gpu = f", GPU {self._hw['gpu']} {self._hw['vram_gb']:.0f} GB" if self._hw.get("vram_gb") else ""
            self._status_sig.emit("hw", f"This PC: {self._hw.get('ram_gb', 0):.0f} GB RAM{gpu}.", True)
        except Exception:
            pass

    def _settings(self):
        from core import llm
        p = self._provider()
        prov = "gemini" if p == "gemini_live" else p
        return llm.Settings(provider=prov, base_url=self._val("base_url") or brain_config.DEFAULT_URLS.get(prov, ""),
                            api_key=self._val("api_key") or "", model=self._val("model") or "")

    def _refresh_models(self):
        self._status_sig.emit("brain", "Asking the server for its models…", True)

        def work():
            from core import llm
            try:
                names = llm.list_models(self._settings())
                self._models_sig.emit(names, "")
            except Exception as e:
                self._models_sig.emit([], str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_models(self, names: list, err: str):
        if err:
            self._on_status("brain", err, False)
            return
        for key in ("model", "smart_model", "vision_model"):
            c = self._w[key]
            cur = c.currentText()
            c.clear()
            c.addItems(names)
            c.setCurrentText(cur)
        if self._provider() == "ollama" and self._rec:
            missing = [m for m in (self._rec["model"], self._rec["vision_model"]) if m and m not in names]
            tail = f" Suggested but not downloaded: {', '.join(missing)} (type one and press ⬇)." if missing else ""
        else:
            tail = ""
        self._on_status("brain", f"{len(names)} model(s) found.{tail}", True)

    def _test_brain(self):
        self._status_sig.emit("brain", "Testing…", True)

        def work():
            from core import llm
            s = self._settings()
            if s.provider == "ollama":
                llm.ensure_ollama_running(s)
            ok, msg = llm.ping(s)
            self._status_sig.emit("brain", ("✓ " if ok else "✗ ") + msg, ok)
        threading.Thread(target=work, daemon=True).start()

    def _pull_model(self):
        model = self._val("model")
        if not model:
            self._on_status("brain", "Type a model name first, e.g. qwen2.5:7b", False)
            return
        self._status_sig.emit("brain", f"Downloading {model}…", True)

        def work():
            from core import llm
            s = self._settings()
            if not llm.ensure_ollama_running(s):
                self._status_sig.emit("brain", "Ollama is not installed or not running — get it from "
                                               "ollama.com/download", False)
                return
            last = [-5]

            def prog(status, frac):
                pct = int(frac * 100)
                if pct >= last[0] + 2 or status in ("success",):
                    last[0] = pct
                    self._status_sig.emit("brain", f"{model}: {status} {pct}%", True)
            ok, msg = llm.ollama_pull(model, prog, s, self._pull_cancel)
            self._status_sig.emit("brain", f"✓ {model} downloaded." if ok else f"✗ {msg}", ok)
        threading.Thread(target=work, daemon=True).start()

    def _test_voice(self):
        self._save_voice()
        self._status_sig.emit("voice", "Speaking…", True)

        def work():
            try:
                import numpy as np
                import sounddevice as sd
                from core.tts_engine import create_tts
                tts = create_tts(log=lambda m: self._status_sig.emit("voice", m, "ERR" not in m))
                tts.load()
                name = brain_config.assistant_name().title()
                audio = np.concatenate(list(tts.synth(f"Hello, I am {name}. All systems are online.")))
                from core import audio_fx
                audio = audio_fx.apply_gain(audio.astype(np.int16), float(self._val("voice_volume") or 100))
                sd.play(audio.astype(np.float32) / 32768.0, 24000)
                sd.wait()
                self._status_sig.emit("voice", f"✓ {tts.name} voice works.", True)
            except Exception as e:
                self._status_sig.emit("voice", f"✗ {e}", False)
        threading.Thread(target=work, daemon=True).start()

    def _open_mcp(self):
        try:
            from core import mcp_client
            mcp_client.load_config()
            path = str(mcp_client.CONFIG_FILE)
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self._on_status("save", f"Could not open the MCP file: {e}", False)

    def _on_status(self, which: str, text: str, ok: bool):
        if which == "hw":
            self._hw_line = text
            self._on_provider()
            return
        lbl = self._status.get(which)
        if lbl is None:
            return
        lbl.setText(text)
        lbl.setStyleSheet(f"color: {C.GREEN if ok else C.RED}; background: transparent;")

    # ── saving ───────────────────────────────────────────────────────────────
    def _save_voice(self):
        brain_config.save_voice_cfg({
            "stt_engine": self._val("stt_engine"), "stt_model": self._val("stt_model"),
            "stt_device": self._val("stt_device"), "stt_language": self._val("stt_language"),
            "stt_base_url": self._val("stt_base_url"), "stt_api_key": self._val("stt_api_key"),
            "stt_api_model": self._val("stt_api_model"),
            "end_silence_ms": int(self._val("end_silence_ms") or 700),
            "tts_engine": self._val("tts_engine"), "tts_voice": self._val("tts_voice"),
            "piper_voice": self._val("piper_voice"), "kokoro_voice": self._val("kokoro_voice"),
            "elevenlabs_api_key": self._val("elevenlabs_api_key"),
            "elevenlabs_voice_id": self._val("elevenlabs_voice_id"),
            "tts_rate": int(self._val("tts_rate") or 0),
            "voice_volume": int(self._val("voice_volume") if self._val("voice_volume") is not None else 100),
        })
        try:
            from core import audio_fx
            audio_fx.set_volume_percent(self._val("voice_volume") if self._val("voice_volume") is not None else 100)
        except Exception:
            pass

    def _save(self):
        p = self._provider()
        key = self._val("api_key")
        url = self._val("base_url")
        if p in ("gemini_live", "gemini", "anthropic") and not key:
            self._on_status("save", "This brain needs an API key.", False)
            return
        if p == "openai" and not key and not any(h in (url or "") for h in ("localhost", "127.0.0.1")):
            self._on_status("save", "This service needs an API key.", False)
            return
        was_local = brain_config.uses_local_engine()
        had_provider = bool(brain_config.provider())
        if p in ("gemini_live", "gemini") and key:
            brain_config.save_top(gemini_api_key=key)
        brain_config.save_brain({
            "provider": p,
            "base_url": url if p not in ("gemini_live",) else "",
            "api_key": key if p not in ("gemini_live", "gemini") else "",
            "model": self._val("model") or "",
            "smart_model": self._val("smart_model") or "",
            "vision_model": self._val("vision_model") or "",
            "num_ctx": int(self._val("num_ctx") or 16384),
            "tool_profile": self._val("tool_profile") or "auto",
        })
        self._save_voice()
        brain_config.save_senses({k: self._val(k) for k in (
            "listen_mode", "barge_in", "voice_confirm", "journal", "face_presence", "owner_only",
            "greet_on_arrival", "lock_on_leave", "alert_unknown_faces", "live_vision", "vision_proactive",
            "vision_captions", "vision_attach", "vision_preview")})
        brain_config.save_senses({"vision_fps": float(self._val("vision_fps") or 2),
                                  "vision_caption_seconds": int(self._val("vision_caption_seconds") or 60),
                                  "live_video_seconds": int(self._val("live_video_seconds") or 3)})
        brain_config.save_search_cfg({
            "auto_search": self._val("auto_search"), "google_ai": self._val("google_ai"),
            "provider": self._val("search_provider") or "auto",
            "tavily_key": self._val("tavily_key"), "brave_key": self._val("brave_key"),
            "serper_key": self._val("serper_key"), "searxng_url": self._val("searxng_url"),
            "region": self._val("search_region") or "auto", "read_pages": self._val("read_pages")})
        brain_config.save_learning_cfg({
            "enabled": self._val("learn_enabled"), "from_room": self._val("learn_room"),
            "from_camera": self._val("learn_camera"), "from_screen": self._val("learn_screen"),
            "from_tools": self._val("learn_tools"),
            "consolidate_minutes": int(self._val("consolidate_minutes") or 10),
            "embed_model": self._val("embed_model") or ""})
        token = self._val("telegram_token")
        try:
            from core import telegram_bridge
            import json
            tg = json.loads(brain_config.CONFIG_FILE.read_text(encoding="utf-8")).get("telegram", {}) or {}
            if token and token != tg.get("bot_token"):
                telegram_bridge.save_cfg(bot_token=token, owner_chat_id="", enabled=True)
                from core import runtime
                telegram_bridge.start(log=runtime.log)
            elif not token and tg.get("bot_token"):
                telegram_bridge.save_cfg(bot_token="", enabled=False)
        except Exception:
            pass
        brain_config.ensure_os_field()
        now_local = brain_config.uses_local_engine()
        needs_restart = (not self._first) and had_provider and (was_local != now_local)
        self.saved.emit(needs_restart)
