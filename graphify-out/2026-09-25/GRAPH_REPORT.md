# Graph Report - Mark-LIV  (2026-09-25)

## Corpus Check
- 63 files · ~117,393 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 3, .ico 1, .obj 1)

## Summary
- 1656 nodes · 3193 edges · 100 communities (77 shown, 23 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 176 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `58192701`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- game_updater.py
- system_monitor.py
- file_processor.py
- file_controller.py
- tts.py
- avatar_mesh.py
- MainWindow
- web_search.py
- .__init__
- gemini.py
- llm_client.py
- code_helper.py
- HoloAvatar
- memory_manager.py
- _BrowserSession
- computer_control.py
- dev_agent.py
- KokoroTTSEngine
- tech_font
- EchoGuard
- JarvisUI
- ⚙️ MARK LIV (54)
- main.py
- JarvisLive
- audio_devices.py
- crypto-js.min.js
- config_manager.py
- screen_processor.py
- send_message.py
- load_api_keys
- server.py
- setup.py
- WakeWordDetector
- computer_settings
- .run
- get_input_device
- discover_plugins
- MemoryOverlay
- gmail_manager.py
- background_monitor.py
- ._wake_state
- pathlib
- PluginSettingsOverlay
- ui.py
- confirm.py
- ._build_app
- .__init__
- _SysMetrics
- ._tuning_config
- wake_word.py
- HudCanvas
- DashboardServer
- ._play_audio
- get_push_to_talk_enabled
- ._build_jarvis_icon
- setter
- ._apply_ptt_shortcut
- CustomizeOverlay
- ActionRegistry
- QColor
- ._aes_key
- ._build_right_panel
- Graphify + Antigravity Project Workflow & Setup Guide
- 🔄 The Foundation Update — in every Mark from LII
- WhisperSTT
- _ensure_network_access
- rules/graphify.md
- VoskSTT
- workflows/graphify.md
- _detect_action
- daily_brief.py
- get_base_dir
- ._decrypt
- .glance
- ._receive_audio
- .hide_confirm
- ._send_startup_briefing
- .hide_quiz
- _template.py
- _get_base_dir
- _make_uploads_dir
- .prompt_reconfig
- .set_audio_level
- .show_camera_frame
- .show_quiz
- .start_camera_stream
- Path
- get_hud_style
- calendar_sync.py
- json
- Daily Brief Protocol
- Email Handling Rules
- Executive Assistant Persona & Behavioral Standards
- QPainter
- /email-triage Workflow
- get_plugin_config

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 82 edges
2. `JarvisLive` - 51 edges
3. `tech_font()` - 41 edges
4. `JarvisUI` - 40 edges
5. `_BrowserSession` - 32 edges
6. `is_mac()` - 21 edges
7. `_resolve_path()` - 21 edges
8. `is_windows()` - 19 edges
9. `computer_control()` - 19 edges
10. `mono_font()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `🩹 Fixes that came with it` --references--> `computer_settings()`  [INFERRED]
  readme.md → actions/computer_settings.py
- `Steps` --references--> `computer_control()`  [INFERRED]
  .agents/workflows/deep_work.md → actions/computer_control.py
- `Steps` --references--> `daily_brief()`  [INFERRED]
  .agents/workflows/daily_brief.md → actions/daily_brief.py
- `Steps` --references--> `reminder()`  [INFERRED]
  .agents/workflows/daily_brief.md → actions/reminder.py
- `Steps` --references--> `open_app()`  [INFERRED]
  .agents/workflows/deep_work.md → actions/open_app.py

## Import Cycles
- None detected.

## Communities (100 total, 23 thin omitted)

### Community 0 - "game_updater.py"
Cohesion: 0.07
Nodes (74): _cancel_scheduled_update(), _click_button(), _click_first_profile_by_screenshot(), _ensure_steam_running(), _epic_manifests_path(), _find_best_drive(), _find_epic_exe(), _find_epic_exe_linux() (+66 more)

### Community 1 - "system_monitor.py"
Cohesion: 0.18
Nodes (11): _get_cpu_temp(), _get_gpu_usage(), get_system_status(), _nvml_gpu(), System Monitor — background metric checks with voice alert support. Zero…, Snapshot of current system metrics for the system_status tool., Stateful monitor — cooldown state persists across session reconnections. Call…, GPU utilisation via NVML — zero subprocess on all platforms. (+3 more)

### Community 3 - "file_processor.py"
Cohesion: 0.07
Nodes (53): _ask_gemini_for_desktop_action(), _build_sandbox(), clean_desktop(), desktop_control(), _execute_generated_code(), _get_api_key(), _get_base_dir(), get_current_wallpaper() (+45 more)

### Community 4 - "file_controller.py"
Cohesion: 0.09
Nodes (49): copy_file(), create_file(), create_folder(), delete_file(), file_controller(), find_files(), _format_size(), _get_desktop() (+41 more)

### Community 5 - "tts.py"
Cohesion: 0.11
Nodes (13): asyncio, create_tts_player(), EdgeTTSEngine, ElevenLabsTTSEngine, _play_audio_bytes(), Text-to-Speech engines for MARK XL. EdgeTTS – free Microsoft TTS (internet…, Microsoft EdgeTTS – free, requires internet., ElevenLabs cloud TTS – API key required. (+5 more)

### Community 6 - "avatar_mesh.py"
Cohesion: 0.07
Nodes (32): collections, _add_cranium(), _add_neck(), _boundary_loop(), build_head(), _check_landmarks(), get_head_mesh(), _load_obj() (+24 more)

### Community 7 - "MainWindow"
Cohesion: 0.06
Nodes (8): QMainWindow, MainWindow, Slot — display camera preview overlay (main thread)., Slot — runs on Qt main thread. Updates and shows the content panel., Slot — Qt main thread. Lays a document review into the content panel., Slot — Qt main thread. Puts a fresh quiz on the board., Returns True if auto-start is currently registered on this OS., Place a floating overlay in the middle of the HUD and show it.

### Community 8 - "web_search.py"
Cohesion: 0.06
Nodes (44): _compare(), _ddg_news(), _ddg_search(), _format_ddg(), _format_news(), _gemini_available(), _gemini_headlines(), _gemini_search() (+36 more)

### Community 9 - ".__init__"
Cohesion: 0.08
Nodes (7): QApplication, QDragEnterEvent, QDropEvent, ClipboardPanel, FileDropZone, Floating panel shown when text is copied — offers quick Jarvis actions., _RootShim

### Community 10 - "gemini.py"
Cohesion: 0.08
Nodes (34): _build_google_flights_url(), flight_finder(), _format_spoken(), _format_text_report(), _get_base_dir(), _parse_date(), _parse_flights_with_gemini(), Path (+26 more)

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
Cohesion: 0.13
Nodes (25): _do_shutdown(), Summarise the current session in 1-2 sentences and save to long_term.json., _all_entries(), all_entries_for_ui(), _empty_memory(), _entry_value(), forget(), get_base_dir() (+17 more)

### Community 15 - "_BrowserSession"
Cohesion: 0.05
Nodes (23): browser_control(), _BrowserSession, _detect_default_browser(), _find_exe_windows(), _find_opera_windows(), _firefox_profile_dir(), _log(), _normalize_url() (+15 more)

### Community 16 - "computer_control.py"
Cohesion: 0.18
Nodes (27): _base_dir(), _clear_field(), _click(), _clipboard_get(), _clipboard_paste(), computer_control(), _drag(), _focus_window() (+19 more)

### Community 17 - "dev_agent.py"
Cohesion: 0.16
Nodes (21): _build_project(), _classify_error(), dev_agent(), _fix_files(), _get_model(), _has_error(), _install_dependencies(), _is_rate_limit() (+13 more)

### Community 18 - "KokoroTTSEngine"
Cohesion: 0.14
Nodes (12): _compress_silence(), _import_kokoro_pipeline(), KokoroTTSEngine, _synth(), _play_np(), ndarray, Import KPipeline, auto-upgrading kokoro if a version mismatch is found. Old…, Fully offline Kokoro neural TTS. Model (~330 MB) is downloaded from HuggingFace… (+4 more)

### Community 19 - "tech_font"
Cohesion: 0.09
Nodes (17): QFont, QWidget, _CameraPreview, _fl(), MetricBar, mono_font(), Floating overlay that briefly shows what the camera captured., Floating overlay — QR code for instant phone pairing + manual key fallback. (+9 more)

### Community 20 - "EchoGuard"
Cohesion: 0.08
Nodes (14): band_energies(), EchoGuard, ndarray, Classifies microphone blocks while the assistant is speaking. Usage:…, True once the estimate rests on enough real echo to be trusted., Residual left by this room's own echo. Higher = harder to separate., False when the acoustics are too poor to judge on content alone. Speakers…, The residual a block must clear right now to count as a voice. (+6 more)

### Community 21 - "JarvisUI"
Cohesion: 0.10
Nodes (8): main(), runner(), JarvisUI, Thread-safe: raise the irreversible-action gate. Called from action handlers…, Thread-safe: post a schedule of (level, openness, width) mouth frames for…, Thread-safe: display content in the panel below the HUD., Thread-safe: lay a document review into the panel below the HUD. `findings` is…, Thread-safe: stop the live camera feed.

### Community 22 - "⚙️ MARK LIV (54)"
Cohesion: 0.07
Nodes (28): 🧑‍🎤 A real head, rendered in software, 🚀 Capabilities, 👤 Connect with the Creator, Core Features, 🩹 Fixes, How it understands itself, 🙂 It acts while it talks, 🗣️ It answers before it works (+20 more)

### Community 23 - "main.py"
Cohesion: 0.10
Nodes (16): ProactiveEngine, ProactiveEngine 2.0 — context-aware, time-aware, non-repetitive background…, Decides when JARVIS should speak unprompted and builds a context-rich prompt.…, Build a context snapshot for Gemini. Rotates through three focus areas so…, google, google_genai, LiveConnectConfig, _describe_limits() (+8 more)

### Community 24 - "JarvisLive"
Cohesion: 0.08
Nodes (14): JarvisLive, Load the detector once (model loads on first start). Idempotent., Called from the detector thread when 'Hey Jarvis' is heard., Auto-sleep after the configured silence window (wake-word mode only)., Enable/disable wake word from the settings UI. Returns a status token:…, Manual sleep/wake button in the UI., Download openwakeword + the model (runs in a UI worker thread)., Thread-safe: ask the run loop to tear down and rebuild the Live session. Called… (+6 more)

### Community 25 - "audio_devices.py"
Cohesion: 0.12
Nodes (20): configure(), _display_name(), _is_pseudo(), list_devices(), prefetch(), _work(), _query(), _collect() (+12 more)

### Community 27 - "config_manager.py"
Cohesion: 0.14
Nodes (19): ensure_config_dir(), get_brief_enabled(), Read-modify-write one key without disturbing the rest of the config., Merge `values` into a namespace's stored config (read-modify-write, like every…, Persist assistant name and user name to config., Persist the chosen Live voice. Unknown names collapse to the default so a bad…, save_api_keys(), save_assistant_config() (+11 more)

### Community 28 - "screen_processor.py"
Cohesion: 0.16
Nodes (19): _base_dir(), _capture_camera(), _capture_screen(), _compress(), _cv2_backend(), _detect_camera_index(), _get_camera_index(), _get_os() (+11 more)

### Community 29 - "send_message.py"
Cohesion: 0.25
Nodes (19): _base_dir(), _clear_and_paste(), _desktop_send(), _get_os(), _open_app(), _open_browser_url(), _paste_text(), Path (+11 more)

### Community 30 - "load_api_keys"
Cohesion: 0.18
Nodes (11): get_assistant_name(), get_gemini_key(), get_proactive_audio_enabled(), get_voice(), get_wake_word_enabled(), is_configured(), load_api_keys(), Whether local wake-word gating is on (assistant sleeps until 'Hey Jarvis'). (+3 more)

### Community 31 - "server.py"
Cohesion: 0.12
Nodes (14): base64, _ensure_certs(), _local_ip(), dashboard/server.py — JARVIS Local HTTP Dashboard Plain HTTP on port 8000 (no…, Return the best LAN-facing IPv4 address, no internet required., Make sure config/certs holds a TLS key pair, generating a self-signed one the…, _read(), fastapi (+6 more)

### Community 32 - "setup.py"
Cohesion: 0.36
Nodes (7): _check_assets(), _check_python(), main(), MARK LIV — one-time setup. Installs the Python dependencies for THIS operating…, Fail immediately and clearly rather than deep inside a pip resolver. A wrong…, The avatar's face is a shipped file; a truncated clone should say so., _run()

### Community 33 - "WakeWordDetector"
Cohesion: 0.20
Nodes (4): Runs the wake model in a dedicated thread. The mic thread calls feed() with raw…, Load the model and spawn the inference thread. Returns True on success. Safe to…, Called from the mic callback (real-time thread). Must stay cheap and never…, WakeWordDetector

### Community 34 - "computer_settings"
Cohesion: 0.12
Nodes (16): brightness_get(), brightness_set(), computer_settings(), dark_mode(), paste(), press_key(), Current brightness 0-100, or None where it cannot be read., Set brightness to an absolute percentage. Only used to restore a value captured… (+8 more)

### Community 35 - ".run"
Cohesion: 0.12
Nodes (12): BaseException, _get_api_key(), _is_reconnect_signal(), _keep_context_of(), Background task: voice alerts when metrics exceed thresholds., Check user-configured topics once per day; speak alerts when new headlines…, Background task: periodically checks if the user has been silent long enough,…, Forward phone mic PCM chunks from dashboard queue into the Gemini Live session. (+4 more)

### Community 36 - "get_input_device"
Cohesion: 0.25
Nodes (8): get_input_device(), get_output_device(), _patch_config(), Read-modify-write one or more keys in api_keys.json. Every setter in this file…, Microphone device name, or '' for the system default., Speaker device name, or '' for the system default., save_input_device(), save_output_device()

### Community 37 - "discover_plugins"
Cohesion: 0.11
Nodes (17): _call_run(), discover_plugins(), _load_error(), _opt_upper(), PluginRecord, PluginRegistry, Exception, Path (+9 more)

### Community 38 - "MemoryOverlay"
Cohesion: 0.11
Nodes (11): AudioDeviceOverlay, _row(), ConfirmBanner, _HudOverlay, MemoryOverlay, Base for the floating panels placed by hand over the HUD. They are children of…, The gate in front of an action that cannot be taken back. The old confirmation…, Choose which microphone JARVIS listens to and which speakers it uses. Both… (+3 more)

### Community 39 - "gmail_manager.py"
Cohesion: 0.10
Nodes (24): _clean_header_str(), _extract_body_snippet(), fetch_unread_emails(), gmail_manager(), _load_gmail_creds(), Gmail Manager Action for JARVIS Mark-LIV. Provides full Gmail connectivity: -…, Send an email using Gmail SMTP SSL., Action entry point for Gmail interaction. (+16 more)

### Community 40 - "background_monitor.py"
Cohesion: 0.29
Nodes (12): add_monitor(), check_all(), _is_blocked(), list_monitors(), _load(), BackgroundMonitor — user-configured topic watching. Checks DDG news once per…, Run all pending topic checks (once per day per topic). Returns a list of…, remove_monitor() (+4 more)

### Community 42 - "pathlib"
Cohesion: 0.17
Nodes (16): Action discovery, validation, and dispatch — the built-in twin of…, _available(), install_for_config(), _pip(), MARK XL — Dependency auto-installer. Called automatically on first launch and…, Return True if the module can be imported (no actual import)., Install all missing packages required by *config*. Blocking — always call from…, Plugin discovery, validation, collision detection, and dispatch. Discovery runs… (+8 more)

### Community 43 - "PluginSettingsOverlay"
Cohesion: 0.17
Nodes (6): QPushButton, QVBoxLayout, PluginManagerOverlay, PluginSettingsOverlay, Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles., Floating overlay — renders per-plugin settings forms. Fully generic: it…

### Community 44 - "ui.py"
Cohesion: 0.10
Nodes (21): Holographic AI head for the HUD centre — the thing that used to be a ring stack…, math, Path, pyqt6_qtcore, pyqt6_qtgui, pyqt6_qtwidgets, random, apply_ui_accent() (+13 more)

### Community 45 - "confirm.py"
Cohesion: 0.21
Nodes (12): bind(), _log(), _Pending, pending_title(), core/confirm.py — a confirmation the model cannot forge. THE PROBLEM WITH THE…, Called by the UI when the user presses CONFIRM or CANCEL. Runs the stored…, when nothing is waiting. Lets an action avoid stacking two banners., Wire this module to the HUD. Called once from main.py at startup. (+4 more)

### Community 46 - "._build_app"
Cohesion: 0.24
Nodes (6): _auth(), list_files(), revoke_devices(), _safe_filename(), upload_file(), wake_ep()

### Community 47 - ".__init__"
Cohesion: 0.17
Nodes (7): _Popen, Exception, Raised inside the session TaskGroup to force a clean, voluntary reconnect (e.g.…, Session-scoped task: when a voluntary reconnect is requested, raise a signal…, Turn hold-to-talk on or off. Returns the scope actually achieved., _ReconnectSignal, _OrigPopen

### Community 48 - "_SysMetrics"
Cohesion: 0.21
Nodes (4): Thread-safe speech channel for plugins: lets a plugin ask JARVIS to say…, _nvml_gpu_windows(), Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess., _SysMetrics

### Community 49 - "._tuning_config"
Cohesion: 0.22
Nodes (7): The optional knobs, kept apart so one bad field can be dropped wholesale. Every…, get_media_resolution(), get_thinking_enabled(), get_turn_tuning(), Whether the Live model may spend tokens thinking before it answers. Off by…, How eagerly the server decides you have stopped speaking. OFF by default, and…, How finely the model tokenises the screenshots and camera frames it is sent.…

### Community 50 - "wake_word.py"
Cohesion: 0.31
Nodes (8): install_and_download(), is_installed(), is_ready(), Local wake-word detection for JARVIS ("Hey Jarvis"). Design goals: • ZERO cost…, True if the openwakeword package is importable (no model check)., True if openwakeword is installed AND its model files are present on disk. This…, One-click setup for the UI button: pip-install openwakeword if missing, then…, queue

### Community 51 - "HudCanvas"
Cohesion: 0.11
Nodes (12): QColor, QPainter, QPixmap, _DropCanvas, HudCanvas, qcol(), Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)., Thread-safe: hand over a schedule of (level, openness, width) frames. The… (+4 more)

### Community 52 - "DashboardServer"
Cohesion: 0.25
Nodes (3): DashboardServer, URL for manual browser entry. When HTTPS active, points to alias port (also…, Second HTTPS server on PORT+1 sharing the same app and in-memory state. Chrome…

### Community 53 - "._play_audio"
Cohesion: 0.22
Nodes (7): callback(), _open_mic(), _pcm_level(), _pcm_visemes(), Map a block of int16 PCM samples to a 0.0–1.0 loudness level for the HUD…, Slice a PCM block into (level, openness, width) frames, one per 20 ms. Returns…, True while the speakers may still be finishing our last sentence.

### Community 54 - "get_push_to_talk_enabled"
Cohesion: 0.40
Nodes (3): get_push_to_talk_enabled(), Hold-a-key-to-speak. When on, the mic is closed unless the chord is held., Repaint the push-to-talk row from the saved setting.

### Community 55 - "._build_jarvis_icon"
Cohesion: 0.22
Nodes (4): Render a JARVIS arc-reactor icon at 4× resolution and downsample for crisp…, Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd. Tries…, Resolve the user's REAL desktop directory instead of assuming ~/Desktop, which…, Create a desktop shortcut on Windows / macOS / Linux. Never opens a terminal,…

### Community 57 - "._apply_ptt_shortcut"
Cohesion: 0.29
Nodes (5): qt_sequence(), The same chord as a QKeySequence string., _press(), Bind the chord inside the window when no global hook is available. On macOS and…, Report a windowed press/release to whoever owns the microphone.

### Community 58 - "CustomizeOverlay"
Cohesion: 0.11
Nodes (9): QPointF, QRectF, CustomizeOverlay, _lbl(), HueWheel, Circular colour picker. The user drags the handle (small white circle) around…, Floating overlay — change assistant name, user name, UI colour and voice., Highlight the selected voice pill; dim the rest. (+1 more)

### Community 59 - "ActionRegistry"
Cohesion: 0.13
Nodes (11): ActionRecord, ActionRegistry, _call_handler(), discover_actions(), _opt_upper(), Path, Invoke the handler passing only the context kwargs it actually declares (or all…, Returns an ActionRecord; .valid=False + .error set on any problem. Never raises. (+3 more)

### Community 61 - "._aes_key"
Cohesion: 0.32
Nodes (6): auto_login(), device_login_ep(), login(), phone_audio_ws(), _derive_key(), SHA-256(sessionKey‖salt) → 32-byte AES-256 key (microseconds, no PBKDF2 needed).

### Community 62 - "._build_right_panel"
Cohesion: 0.20
Nodes (4): QHBoxLayout, QTextEdit, LogWidget, _sec()

### Community 64 - "🔄 The Foundation Update — in every Mark from LII"
Cohesion: 0.22
Nodes (9): _get_macos_wifi_interface(), toggle_wifi(), ⚠️ A confirmation the model can't forge, 🧠 A memory that actually remembers, 🩹 Fixes that came with it, 🎧 It finally asks which microphone, 🔗 It stops forgetting the conversation when the connection drops, 🔄 The Foundation Update — in every Mark from LII (+1 more)

### Community 65 - "WhisperSTT"
Cohesion: 0.33
Nodes (4): ndarray, Offline transcription using faster-whisper., Transcribe a float32 mono 16 kHz numpy array. Returns transcript string., WhisperSTT

### Community 68 - "VoskSTT"
Cohesion: 0.40
Nodes (3): Streaming transcription using Vosk., Feed raw int16 LE PCM bytes. Returns (text, is_final)., VoskSTT

### Community 70 - "_detect_action"
Cohesion: 0.40
Nodes (5): _detect_action(), _normalise(), Resolve a free-text description to an action name, locally. Returns {"action":…, What to tell the model when nothing matched. Names real actions so its retry…, _suggest()

### Community 71 - "daily_brief.py"
Cohesion: 0.16
Nodes (16): daily_brief(), _get_gmail_brief(), _get_greeting(), _get_live_weather(), _get_reminders_brief(), _get_system_vitals(), Daily Brief Action for JARVIS Mark-LIV. Provides the ultimate morning and daily…, Inspect core CPU, RAM, and Battery vitals. (+8 more)

### Community 73 - "._decrypt"
Cohesion: 0.40
Nodes (4): command(), ws_ep(), _decrypt_cbc(), Decrypt base64(IV[16] ‖ ciphertext) with AES-256-CBC + PKCS7.

### Community 75 - "._receive_audio"
Cohesion: 0.29
Nodes (4): _clean_transcript(), _is_repeat_chunk(), Send a captured frame immediately after its tool response. The frame is already…, True if this transcript chunk has already been seen this turn. Guards against…

### Community 77 - "._send_startup_briefing"
Cohesion: 0.33
Nodes (3): Two-phase briefing optimized for speed: Phase 1 — instant greeting (no tools) →…, pop_last_session(), Return AND remove the most recent session entry. Calling this consumes the…

### Community 79 - "_template.py"
Cohesion: 0.50
Nodes (3): Drop-in JARVIS plugin template. Copy this file, rename it (no leading…, parameters: dict of the args Gemini extracted, matching PLUGIN['parameters'].…, run()

### Community 80 - "_get_base_dir"
Cohesion: 0.67
Nodes (3): _get_api_key(), _get_base_dir(), Path

### Community 81 - "_make_uploads_dir"
Cohesion: 0.67
Nodes (3): _make_uploads_dir(), Path, Return (and create) the cross-platform uploads folder.

### Community 88 - "get_hud_style"
Cohesion: 0.40
Nodes (3): get_hud_style(), Which centrepiece the HUD draws: the animated head, or the reactor core. Taste,…, Swap the centrepiece. Both objects stay in memory, so the change is instant and…

### Community 89 - "calendar_sync.py"
Cohesion: 0.47
Nodes (5): _load_events(), Calendar Sync Plugin for JARVIS Mark-LIV. Tracks agenda, meetings,…, Execute calendar action., run(), _save_events()

### Community 93 - "json"
Cohesion: 0.19
Nodes (10): Telling the user's voice apart from our own coming back through the speakers.…, Speech-to-Text engines for MARK XL. Whisper – offline transcription via faster-…, json, numpy, Focus Protocol Plugin for JARVIS Mark-LIV. Manages deep work intervals,…, Execute focus protocol actions., _read_state(), run() (+2 more)

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
- **39 isolated node(s):** `C`, `🧑‍🎤 A real head, rendered in software`, `👤 Connect with the Creator`, `🩹 Fixes`, `🙂 It acts while it talks` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 649 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `MainWindow` to `MemoryOverlay`, `config_manager.py`, `.__init__`, `._wake_state`, `ui.py`, `tech_font`, `get_push_to_talk_enabled`, `._build_jarvis_icon`, `setter`, `._apply_ptt_shortcut`, `get_hud_style`, `._build_right_panel`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Why does `JarvisUI` connect `JarvisUI` to `.__init__`, `.glance`, `._wake_state`, `ui.py`, `.hide_confirm`, `.hide_quiz`, `.__init__`, `.prompt_reconfig`, `.set_audio_level`, `.show_camera_frame`, `.show_quiz`, `get_push_to_talk_enabled`, `main.py`, `JarvisLive`, `._apply_ptt_shortcut`, `setter`, `.start_camera_stream`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Why does `JarvisLive` connect `JarvisLive` to `system_monitor.py`, `WakeWordDetector`, `.run`, `avatar_mesh.py`, `web_search.py`, `background_monitor.py`, `._receive_audio`, `._send_startup_briefing`, `memory_manager.py`, `.__init__`, `_SysMetrics`, `._tuning_config`, `EchoGuard`, `DashboardServer`, `._play_audio`, `main.py`, `JarvisUI`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `JarvisLive` (e.g. with `ProactiveEngine` and `SystemMonitor`) actually correct?**
  _`JarvisLive` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `C`, `🧑‍🎤 A real head, rendered in software`, `👤 Connect with the Creator` to the rest of the system?**
  _39 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `game_updater.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06518987341772152 - nodes in this community are weakly interconnected._
- **Should `computer_settings.py` be split into smaller, more focused modules?**
  _Cohesion score 0.041666666666666664 - nodes in this community are weakly interconnected._