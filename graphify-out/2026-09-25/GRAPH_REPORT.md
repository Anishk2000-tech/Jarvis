# Graph Report - Mark-LIV  (2026-09-25)

## Corpus Check
- 66 files · ~124,702 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 3, .ico 1, .obj 1)

## Summary
- 1710 nodes · 3328 edges · 104 communities (81 shown, 23 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 155 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `fc6c17f0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- game_updater.py
- background_monitor.py
- computer_settings.py
- file_processor.py
- file_controller.py
- tts.py
- avatar_mesh.py
- MainWindow
- gemini.py
- FileDropZone
- daily_brief.py
- llm_client.py
- code_helper.py
- HoloAvatar
- memory_manager.py
- _BrowserSession
- computer_control.py
- dev_agent.py
- desktop.py
- tech_font
- EchoGuard
- JarvisUI
- ⚙️ MARK LIV (54)
- .__init__
- JarvisLive
- audio_devices.py
- crypto-js.min.js
- ensure_config_dir
- screen_processor.py
- send_message.py
- load_api_keys
- server.py
- ._apply_name_update
- WakeWordDetector
- computer_settings
- .run
- get_input_device
- get_plugin_enabled
- PushToTalk
- gmail_manager.py
- ActionRegistry
- time
- main.py
- PluginSettingsOverlay
- ui.py
- confirm.py
- ._build_app
- ._build_config
- _SysMetrics
- ._tuning_config
- NotesTerminalWidget
- HudCanvas
- DashboardServer
- ._play_audio
- ._ui_wake_toggle
- ._build_jarvis_icon
- setter
- ._apply_ptt_shortcut
- CustomizeOverlay
- RemoteKeyOverlay
- datetime
- ._aes_key
- MemoryOverlay
- Graphify + Antigravity Project Workflow & Setup Guide
- 🔄 The Foundation Update — in every Mark from LII
- WhisperSTT
- _ensure_network_access
- rules/graphify.md
- ._wake_state
- workflows/graphify.md
- _detect_action
- ProactiveEngine
- intel_notes.py
- ._decrypt
- ._build_right_panel
- ._receive_audio
- .request_reconnect
- VoskSTT
- _RootShim
- _template.py
- _get_base_dir
- _make_uploads_dir
- ._send_startup_briefing
- Steps
- config_manager.py
- .hide_confirm
- .hide_quiz
- type_text
- get_hud_style
- .add_intel_note
- json
- Daily Brief Protocol
- Email Handling Rules
- Executive Assistant Persona & Behavioral Standards
- .set_audio_level
- /email-triage Workflow
- get_plugin_config
- .stop_camera_stream
- .show_camera_frame
- .show_content
- .start_camera_stream

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 87 edges
2. `JarvisLive` - 51 edges
3. `tech_font()` - 45 edges
4. `JarvisUI` - 42 edges
5. `_BrowserSession` - 32 edges
6. `_resolve_path()` - 23 edges
7. `is_mac()` - 21 edges
8. `file_controller()` - 20 edges
9. `computer_control()` - 19 edges
10. `is_windows()` - 19 edges

## Surprising Connections (you probably didn't know these)
- `🩹 Fixes that came with it` --references--> `computer_settings()`  [INFERRED]
  readme.md → actions/computer_settings.py
- `3. Dedicated Intel & Notes Terminal (`intel_notes`)` --references--> `intel_notes()`  [INFERRED]
  .agents/rules/file_exploration.md → actions/intel_notes.py
- `Steps` --references--> `computer_control()`  [INFERRED]
  .agents/workflows/deep_work.md → actions/computer_control.py
- `Steps` --references--> `daily_brief()`  [INFERRED]
  .agents/workflows/daily_brief.md → actions/daily_brief.py
- `1. File Opening (`open`)` --references--> `file_controller()`  [INFERRED]
  .agents/rules/file_exploration.md → actions/file_controller.py

## Import Cycles
- None detected.

## Communities (104 total, 23 thin omitted)

### Community 0 - "game_updater.py"
Cohesion: 0.06
Nodes (82): _build_google_flights_url(), flight_finder(), _format_spoken(), _format_text_report(), _get_base_dir(), _parse_date(), _parse_flights_with_gemini(), Path (+74 more)

### Community 1 - "background_monitor.py"
Cohesion: 0.23
Nodes (13): add_monitor(), check_all(), _is_blocked(), list_monitors(), _load(), BackgroundMonitor — user-configured topic watching. Checks DDG news once per…, Run all pending topic checks (once per day per topic). Returns a list of…, remove_monitor() (+5 more)

### Community 3 - "file_processor.py"
Cohesion: 0.13
Nodes (25): _detect_type(), file_processor(), _file_size_str(), _gemini_client(), _output_path(), _process_archive(), _process_audio(), _process_code() (+17 more)

### Community 4 - "file_controller.py"
Cohesion: 0.09
Nodes (52): copy_file(), create_file(), create_folder(), delete_file(), explore_folder(), file_controller(), find_files(), _format_size() (+44 more)

### Community 5 - "tts.py"
Cohesion: 0.07
Nodes (26): asyncio, _compress_silence(), create_tts_player(), EdgeTTSEngine, ElevenLabsTTSEngine, _import_kokoro_pipeline(), KokoroTTSEngine, _synth() (+18 more)

### Community 6 - "avatar_mesh.py"
Cohesion: 0.07
Nodes (32): collections, _add_cranium(), _add_neck(), _boundary_loop(), build_head(), _check_landmarks(), get_head_mesh(), _load_obj() (+24 more)

### Community 7 - "MainWindow"
Cohesion: 0.05
Nodes (10): QMainWindow, MainWindow, Slot — display camera preview overlay (main thread)., Slot — runs on Qt main thread. Updates and shows the content panel., Slot — Qt main thread. Lays a document review into the content panel., Slot — Qt main thread. Puts a fresh quiz on the board., Returns True if auto-start is currently registered on this OS., Repaint the push-to-talk row from the saved setting. (+2 more)

### Community 8 - "gemini.py"
Cohesion: 0.06
Nodes (58): _compare(), _ddg_news(), _ddg_search(), _format_ddg(), _format_news(), _gemini_available(), _gemini_headlines(), _gemini_search() (+50 more)

### Community 9 - "FileDropZone"
Cohesion: 0.18
Nodes (3): QDragEnterEvent, QDropEvent, FileDropZone

### Community 10 - "daily_brief.py"
Cohesion: 0.15
Nodes (17): daily_brief(), _get_gmail_brief(), _get_greeting(), _get_live_weather(), _get_reminders_brief(), _get_system_vitals(), Daily Brief Action for JARVIS Mark-LIV. Provides the ultimate morning and daily…, Inspect core CPU, RAM, and Battery vitals. (+9 more)

### Community 11 - "llm_client.py"
Cohesion: 0.14
Nodes (22): call_llm(), call_llm_stream(), call_llm_text(), check_model_available(), ensure_ollama_running(), get_base_dir(), get_llm_provider(), get_llm_settings() (+14 more)

### Community 12 - "code_helper.py"
Cohesion: 0.18
Nodes (25): _build(), _clean_code(), code_helper(), _detect_intent(), _edit_action(), _explain_action(), _fix_code(), _get_gemini() (+17 more)

### Community 13 - "HoloAvatar"
Cohesion: 0.12
Nodes (19): _blend(), _c(), HoloAvatar, QColor, QPainter, _rate(), `col` at alpha `a` pre-mixed onto `bg`, returned fully **opaque**. Qt's raster…, Animated holographic head. One instance per HUD canvas. Lifecycle: av =… (+11 more)

### Community 14 - "memory_manager.py"
Cohesion: 0.10
Nodes (31): _do_shutdown(), Summarise the current session in 1-2 sentences and save to long_term.json., _all_entries(), all_entries_for_ui(), _empty_memory(), _entry_value(), forget(), format_memory_for_prompt() (+23 more)

### Community 15 - "_BrowserSession"
Cohesion: 0.05
Nodes (23): browser_control(), _BrowserSession, _detect_default_browser(), _find_exe_windows(), _find_opera_windows(), _firefox_profile_dir(), _log(), _normalize_url() (+15 more)

### Community 16 - "computer_control.py"
Cohesion: 0.18
Nodes (27): _base_dir(), _clear_field(), _click(), _clipboard_get(), _clipboard_paste(), computer_control(), _drag(), _focus_window() (+19 more)

### Community 17 - "dev_agent.py"
Cohesion: 0.17
Nodes (20): _build_project(), _classify_error(), dev_agent(), _fix_files(), _get_model(), _has_error(), _install_dependencies(), _is_rate_limit() (+12 more)

### Community 18 - "desktop.py"
Cohesion: 0.08
Nodes (36): _ask_gemini_for_desktop_action(), _build_sandbox(), clean_desktop(), desktop_control(), _execute_generated_code(), _get_api_key(), _get_base_dir(), get_current_wallpaper() (+28 more)

### Community 19 - "tech_font"
Cohesion: 0.08
Nodes (18): QFont, QWidget, _row(), _CameraPreview, CapabilitiesOverlay, ClipboardPanel, _fl(), MetricBar (+10 more)

### Community 20 - "EchoGuard"
Cohesion: 0.08
Nodes (14): band_energies(), EchoGuard, ndarray, Classifies microphone blocks while the assistant is speaking. Usage:…, True once the estimate rests on enough real echo to be trusted., Residual left by this room's own echo. Higher = harder to separate., False when the acoustics are too poor to judge on content alone. Speakers…, The residual a block must clear right now to count as a voice. (+6 more)

### Community 21 - "JarvisUI"
Cohesion: 0.09
Nodes (8): JarvisUI, Thread-safe: raise the irreversible-action gate. Called from action handlers…, Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)., Thread-safe: post a schedule of (level, openness, width) mouth frames for…, Thread-safe: clear the dedicated Notes Terminal., Thread-safe: put an interactive quiz on the board. `grade(question, given)`…, Thread-safe: lay a document review into the panel below the HUD. `findings` is…, Thread-safe: show the API key setup overlay (e.g. after an auth error).

### Community 22 - "⚙️ MARK LIV (54)"
Cohesion: 0.07
Nodes (28): 🧑‍🎤 A real head, rendered in software, 🚀 Capabilities, 👤 Connect with the Creator, Core Features, 🩹 Fixes, How it understands itself, 🙂 It acts while it talks, 🗣️ It answers before it works (+20 more)

### Community 23 - ".__init__"
Cohesion: 0.17
Nodes (7): _Popen, Exception, Raised inside the session TaskGroup to force a clean, voluntary reconnect (e.g.…, Session-scoped task: when a voluntary reconnect is requested, raise a signal…, Turn hold-to-talk on or off. Returns the scope actually achieved., _ReconnectSignal, _OrigPopen

### Community 24 - "JarvisLive"
Cohesion: 0.10
Nodes (10): JarvisLive, main(), runner(), Called from the detector thread when 'Hey Jarvis' is heard., Auto-sleep after the configured silence window (wake-word mode only)., Manual sleep/wake button in the UI., Download openwakeword + the model (runs in a UI worker thread)., Called from Qt main thread when user presses Remote Control. (+2 more)

### Community 25 - "audio_devices.py"
Cohesion: 0.12
Nodes (18): configure(), _display_name(), _is_pseudo(), prefetch(), _work(), _query(), _collect(), core/audio_devices.py — pick which microphone and which speakers JARVIS uses.… (+10 more)

### Community 27 - "ensure_config_dir"
Cohesion: 0.14
Nodes (12): ensure_config_dir(), get_brief_enabled(), Merge `values` into a namespace's stored config (read-modify-write, like every…, Persist assistant name and user name to config., Persist the chosen Live voice. Unknown names collapse to the default so a bad…, save_api_keys(), save_assistant_config(), save_brief_enabled() (+4 more)

### Community 28 - "screen_processor.py"
Cohesion: 0.16
Nodes (19): _base_dir(), _capture_camera(), _capture_screen(), _compress(), _cv2_backend(), _detect_camera_index(), _get_camera_index(), _get_os() (+11 more)

### Community 29 - "send_message.py"
Cohesion: 0.25
Nodes (19): _base_dir(), _clear_and_paste(), _desktop_send(), _get_os(), _open_app(), _open_browser_url(), _paste_text(), Path (+11 more)

### Community 30 - "load_api_keys"
Cohesion: 0.18
Nodes (11): get_assistant_name(), get_proactive_audio_enabled(), get_push_to_talk_enabled(), get_voice(), get_wake_word_enabled(), load_api_keys(), Whether local wake-word gating is on (assistant sleeps until 'Hey Jarvis')., Hold-a-key-to-speak. When on, the mic is closed unless the chord is held. (+3 more)

### Community 31 - "server.py"
Cohesion: 0.12
Nodes (14): base64, _ensure_certs(), _local_ip(), dashboard/server.py — JARVIS Local HTTP Dashboard Plain HTTP on port 8000 (no…, Return the best LAN-facing IPv4 address, no internet required., Make sure config/certs holds a TLS key pair, generating a self-signed one the…, _read(), fastapi (+6 more)

### Community 32 - "._apply_name_update"
Cohesion: 0.20
Nodes (8): apply_ui_accent(), current_palette(), Re-derives the whole teal-family palette from the chosen accent colour (hue…, A snapshot of the accent-linked colours currently on class C., LIVE full theme change. Replaces the old palette colours with the new ones in…, Live preview — paints the whole interface the new colour (does NOT write to…, Update all name/theme-dependent UI elements and persist to config., retheme_all_widgets()

### Community 33 - "WakeWordDetector"
Cohesion: 0.20
Nodes (4): Runs the wake model in a dedicated thread. The mic thread calls feed() with raw…, Load the model and spawn the inference thread. Returns True on success. Safe to…, Called from the mic callback (real-time thread). Must stay cheap and never…, WakeWordDetector

### Community 34 - "computer_settings"
Cohesion: 0.12
Nodes (16): brightness_get(), brightness_set(), computer_settings(), dark_mode(), press_key(), Current brightness 0-100, or None where it cannot be read., Set brightness to an absolute percentage. Only used to restore a value captured…, Current master volume 0-100, or None if this platform will not say. Undo needs… (+8 more)

### Community 35 - ".run"
Cohesion: 0.16
Nodes (9): BaseException, _get_api_key(), _is_reconnect_signal(), _keep_context_of(), Background task: voice alerts when metrics exceed thresholds., Check user-configured topics once per day; speak alerts when new headlines…, Forward phone mic PCM chunks from dashboard queue into the Gemini Live session., True if `exc` is a _ReconnectSignal, or a(n) (Base)ExceptionGroup that wraps… (+1 more)

### Community 36 - "get_input_device"
Cohesion: 0.25
Nodes (8): get_input_device(), get_output_device(), _patch_config(), Read-modify-write one or more keys in api_keys.json. Every setter in this file…, Microphone device name, or '' for the system default., Speaker device name, or '' for the system default., save_input_device(), save_output_device()

### Community 37 - "get_plugin_enabled"
Cohesion: 0.11
Nodes (17): _call_run(), discover_plugins(), _load_error(), _opt_upper(), PluginRecord, PluginRegistry, Exception, Path (+9 more)

### Community 38 - "PushToTalk"
Cohesion: 0.15
Nodes (7): chord_label(), PushToTalk, Begin watching. Returns the scope actually achieved., Feed a press/release from a Qt shortcut (non-Windows, or no hook)., Human-readable name of the chord, for the UI and the logs., Calls `on_change(held: bool)` whenever the chord is pressed or released. Start…, global' once a system-wide hook is running, else 'window'.

### Community 39 - "gmail_manager.py"
Cohesion: 0.12
Nodes (21): _clean_header_str(), _extract_body_snippet(), fetch_unread_emails(), gmail_manager(), _load_gmail_creds(), Gmail Manager Action for JARVIS Mark-LIV. Provides full Gmail connectivity: -…, Send an email using Gmail SMTP SSL., Action entry point for Gmail interaction. (+13 more)

### Community 40 - "ActionRegistry"
Cohesion: 0.13
Nodes (11): ActionRecord, ActionRegistry, _call_handler(), discover_actions(), _opt_upper(), Path, Invoke the handler passing only the context kwargs it actually declares (or all…, Returns an ActionRecord; .valid=False + .error set on any problem. Never raises. (+3 more)

### Community 41 - "time"
Cohesion: 0.12
Nodes (13): ProactiveEngine 2.0 — context-aware, time-aware, non-repetitive background…, Push-to-talk — hold a key, speak, release. Why this exists ---------------…, clear(), history(), peek(), core/undo.py — one shared undo stack for every action that changes state. WHY…, Forget the stack. Called when the app shuts down so closures holding old file…, Label of the operation that `undo_last()` would reverse, or ''. (+5 more)

### Community 42 - "main.py"
Cohesion: 0.11
Nodes (26): Action discovery, validation, and dispatch — the built-in twin of…, _available(), install_for_config(), _pip(), MARK XL — Dependency auto-installer. Called automatically on first launch and…, Return True if the module can be imported (no actual import)., Install all missing packages required by *config*. Blocking — always call from…, Plugin discovery, validation, collision detection, and dispatch. Discovery runs… (+18 more)

### Community 43 - "PluginSettingsOverlay"
Cohesion: 0.17
Nodes (6): QPushButton, QVBoxLayout, PluginManagerOverlay, PluginSettingsOverlay, Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles., Floating overlay — renders per-plugin settings forms. Fully generic: it…

### Community 44 - "ui.py"
Cohesion: 0.13
Nodes (14): list_devices(), Device names for 'input' or 'output'. Falls back to a synchronous query if the…, Holographic AI head for the HUD centre — the thing that used to be a ring stack…, math, pyqt6_qtcore, pyqt6_qtgui, pyqt6_qtwidgets, random (+6 more)

### Community 45 - "confirm.py"
Cohesion: 0.25
Nodes (10): bind(), _log(), _Pending, core/confirm.py — a confirmation the model cannot forge. THE PROBLEM WITH THE…, Called by the UI when the user presses CONFIRM or CANCEL. Runs the stored…, Wire this module to the HUD. Called once from main.py at startup., Park an irreversible action behind the on-screen gate. Returns the sentence the…, request() (+2 more)

### Community 46 - "._build_app"
Cohesion: 0.24
Nodes (6): _auth(), list_files(), revoke_devices(), _safe_filename(), upload_file(), wake_ep()

### Community 47 - "._build_config"
Cohesion: 0.22
Nodes (8): LiveConnectConfig, _describe_limits(), _describe_tools(), _load_system_prompt(), One line per capability, straight from the live tool declarations. Derived…, The other half of self-knowledge: what is out of reach, and why. Derived from…, Fill {tokens} in the prompt template. A plain replace rather than str.format:…, _render_prompt()

### Community 48 - "_SysMetrics"
Cohesion: 0.21
Nodes (4): Thread-safe speech channel for plugins: lets a plugin ask JARVIS to say…, _nvml_gpu_windows(), Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess., _SysMetrics

### Community 49 - "._tuning_config"
Cohesion: 0.22
Nodes (7): The optional knobs, kept apart so one bad field can be dropped wholesale. Every…, get_media_resolution(), get_thinking_enabled(), get_turn_tuning(), Whether the Live model may spend tokens thinking before it answers. Off by…, How eagerly the server decides you have stopped speaking. OFF by default, and…, How finely the model tokenises the screenshots and camera frames it is sent.…

### Community 51 - "HudCanvas"
Cohesion: 0.11
Nodes (11): QPixmap, HudCanvas, QPainter, If a custom emblem/logo file exists in config/, draw it with smooth holographic…, Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)., Thread-safe: hand over a schedule of (level, openness, width) frames. The…, Thread-safe entry point for the audio threads. Stores the louder of the…, Pre-render the static grid-dot background into a transparent pixmap so… (+3 more)

### Community 52 - "DashboardServer"
Cohesion: 0.25
Nodes (3): DashboardServer, URL for manual browser entry. When HTTPS active, points to alias port (also…, Second HTTPS server on PORT+1 sharing the same app and in-memory state. Chrome…

### Community 53 - "._play_audio"
Cohesion: 0.22
Nodes (7): callback(), _open_mic(), _pcm_level(), _pcm_visemes(), Map a block of int16 PCM samples to a 0.0–1.0 loudness level for the HUD…, Slice a PCM block into (level, openness, width) frames, one per 20 ms. Returns…, True while the speakers may still be finishing our last sentence.

### Community 54 - "._ui_wake_toggle"
Cohesion: 0.40
Nodes (3): Load the detector once (model loads on first start). Idempotent., Enable/disable wake word from the settings UI. Returns a status token:…, save_wake_word_enabled()

### Community 55 - "._build_jarvis_icon"
Cohesion: 0.20
Nodes (6): _base_dir(), Path, Render a JARVIS arc-reactor icon at 4× resolution and downsample for crisp…, Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd. Tries…, Resolve the user's REAL desktop directory instead of assuming ~/Desktop, which…, Create a desktop shortcut on Windows / macOS / Linux. Never opens a terminal,…

### Community 57 - "._apply_ptt_shortcut"
Cohesion: 0.22
Nodes (5): qt_sequence(), The same chord as a QKeySequence string., _press(), Bind the chord inside the window when no global hook is available. On macOS and…, Report a windowed press/release to whoever owns the microphone.

### Community 58 - "CustomizeOverlay"
Cohesion: 0.11
Nodes (9): QPointF, QRectF, CustomizeOverlay, _lbl(), HueWheel, Circular colour picker. The user drags the handle (small white circle) around…, Floating glassmorphic overlay for configuring Assistant Persona, Commander…, Highlight the selected voice pill; dim the rest. (+1 more)

### Community 59 - "RemoteKeyOverlay"
Cohesion: 0.27
Nodes (4): Floating overlay — QR code for instant phone pairing + manual key fallback., Call from any thread when a phone successfully connects., RemoteKeyOverlay, _lbl()

### Community 60 - "datetime"
Cohesion: 0.41
Nodes (11): _base_dir(), _get_os(), Path, reminder(), _sanitise(), _schedule_linux(), _schedule_mac(), _schedule_windows() (+3 more)

### Community 61 - "._aes_key"
Cohesion: 0.32
Nodes (6): auto_login(), device_login_ep(), login(), phone_audio_ws(), _derive_key(), SHA-256(sessionKey‖salt) → 32-byte AES-256 key (microseconds, no PBKDF2 needed).

### Community 62 - "MemoryOverlay"
Cohesion: 0.12
Nodes (11): AudioDeviceOverlay, ConfirmBanner, _HudOverlay, MemoryOverlay, Base for the floating panels placed by hand over the HUD. They are children of…, The gate in front of an action that cannot be taken back. The old confirmation…, Choose which microphone JARVIS listens to and which speakers it uses. Both…, Everything JARVIS has stored about you, and when it learned it. Memory used to… (+3 more)

### Community 64 - "🔄 The Foundation Update — in every Mark from LII"
Cohesion: 0.22
Nodes (9): _get_macos_wifi_interface(), toggle_wifi(), ⚠️ A confirmation the model can't forge, 🧠 A memory that actually remembers, 🩹 Fixes that came with it, 🎧 It finally asks which microphone, 🔗 It stops forgetting the conversation when the connection drops, 🔄 The Foundation Update — in every Mark from LII (+1 more)

### Community 65 - "WhisperSTT"
Cohesion: 0.33
Nodes (4): ndarray, Offline transcription using faster-whisper., Transcribe a float32 mono 16 kHz numpy array. Returns transcript string., WhisperSTT

### Community 70 - "_detect_action"
Cohesion: 0.40
Nodes (5): _detect_action(), _normalise(), Resolve a free-text description to an action name, locally. Returns {"action":…, What to tell the model when nothing matched. Names real actions so its retry…, _suggest()

### Community 71 - "ProactiveEngine"
Cohesion: 0.29
Nodes (3): ProactiveEngine, Decides when JARVIS should speak unprompted and builds a context-rich prompt.…, Build a context snapshot for Gemini. Rotates through three focus areas so…

### Community 72 - "intel_notes.py"
Cohesion: 0.31
Nodes (8): _auto_detect_type(), _config_dir(), intel_notes(), _load_notes(), Path, actions/intel_notes.py — Dedicated Intel & Notes Terminal Action. Provides a…, Action handler called by Gemini / action_loader., _save_notes()

### Community 73 - "._decrypt"
Cohesion: 0.40
Nodes (4): command(), ws_ep(), _decrypt_cbc(), Decrypt base64(IV[16] ‖ ciphertext) with AES-256-CBC + PKCS7.

### Community 74 - "._build_right_panel"
Cohesion: 0.20
Nodes (4): QHBoxLayout, QTextEdit, LogWidget, _sec()

### Community 75 - "._receive_audio"
Cohesion: 0.29
Nodes (4): _clean_transcript(), _is_repeat_chunk(), Send a captured frame immediately after its tool response. The frame is already…, True if this transcript chunk has already been seen this turn. Guards against…

### Community 76 - ".request_reconnect"
Cohesion: 0.33
Nodes (3): Thread-safe: ask the run loop to tear down and rebuild the Live session. Called…, Voice picker applied. The voice is baked into the session at connect time, so a…, Microphone or speaker changed. Both streams are opened inside the session…

### Community 77 - "VoskSTT"
Cohesion: 0.40
Nodes (3): Streaming transcription using Vosk., Feed raw int16 LE PCM bytes. Returns (text, is_final)., VoskSTT

### Community 79 - "_template.py"
Cohesion: 0.50
Nodes (3): Drop-in JARVIS plugin template. Copy this file, rename it (no leading…, parameters: dict of the args Gemini extracted, matching PLUGIN['parameters'].…, run()

### Community 80 - "_get_base_dir"
Cohesion: 0.67
Nodes (3): _get_api_key(), _get_base_dir(), Path

### Community 81 - "_make_uploads_dir"
Cohesion: 0.67
Nodes (3): _make_uploads_dir(), Path, Return (and create) the cross-platform uploads folder.

### Community 83 - "Steps"
Cohesion: 0.50
Nodes (3): /daily-brief Workflow, Objective, Steps

### Community 84 - "config_manager.py"
Cohesion: 0.23
Nodes (11): get_base_dir(), get_gemini_key(), is_configured(), Path, Read-modify-write one key without disturbing the rest of the config., _save_flag(), save_hud_style(), save_media_resolution() (+3 more)

### Community 88 - "get_hud_style"
Cohesion: 0.40
Nodes (3): get_hud_style(), Which centrepiece the HUD draws: the animated head, or the reactor core. Taste,…, Swap the centrepiece. Both objects stay in memory, so the change is instant and…

### Community 93 - "json"
Cohesion: 0.14
Nodes (14): Telling the user's voice apart from our own coming back through the speakers.…, Speech-to-Text engines for MARK XL. Whisper – offline transcription via faster-…, json, numpy, _load_events(), Calendar Sync Plugin for JARVIS Mark-LIV. Tracks agenda, meetings,…, Execute calendar action., run() (+6 more)

### Community 94 - "Daily Brief Protocol"
Cohesion: 0.50
Nodes (3): Daily Brief Protocol, Purpose, Rules

### Community 95 - "Email Handling Rules"
Cohesion: 0.50
Nodes (3): Email Handling Rules, Purpose, Rules

### Community 96 - "Executive Assistant Persona & Behavioral Standards"
Cohesion: 0.50
Nodes (3): Core Operational Rules, Executive Assistant Persona & Behavioral Standards, Persona & Demeanor

### Community 98 - "/email-triage Workflow"
Cohesion: 0.50
Nodes (3): /email-triage Workflow, Objective, Steps

### Community 99 - "get_plugin_config"
Cohesion: 0.50
Nodes (4): get_plugin_config(), get_plugin_setting(), All stored values for a namespace (empty dict if none set yet)., A single value from a namespace, or `default` if unset.

## Knowledge Gaps
- **41 isolated node(s):** `C`, `Purpose`, `Rules`, `Purpose`, `Rules` (+36 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 668 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `MainWindow` to `._apply_name_update`, `._wake_state`, `ensure_config_dir`, `._build_right_panel`, `ui.py`, `tech_font`, `._build_jarvis_icon`, `setter`, `._apply_ptt_shortcut`, `get_hud_style`, `MemoryOverlay`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Why does `JarvisUI` connect `JarvisUI` to `._apply_name_update`, `.set_audio_level`, `._wake_state`, `.stop_camera_stream`, `.show_camera_frame`, `.show_content`, `main.py`, `.start_camera_stream`, `ui.py`, `tech_font`, `.hide_confirm`, `.hide_quiz`, `.__init__`, `JarvisLive`, `.add_intel_note`, `setter`, `._apply_ptt_shortcut`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `DashboardServer` connect `DashboardServer` to `.run`, `._decrypt`, `main.py`, `._build_app`, `JarvisLive`, `._aes_key`, `server.py`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `JarvisLive` (e.g. with `ProactiveEngine` and `SystemMonitor`) actually correct?**
  _`JarvisLive` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `C`, `Purpose`, `Rules` to the rest of the system?**
  _41 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `game_updater.py` be split into smaller, more focused modules?**
  _Cohesion score 0.056679151061173536 - nodes in this community are weakly interconnected._
- **Should `computer_settings.py` be split into smaller, more focused modules?**
  _Cohesion score 0.04081632653061224 - nodes in this community are weakly interconnected._