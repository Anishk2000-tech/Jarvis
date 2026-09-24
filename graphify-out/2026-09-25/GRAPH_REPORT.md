# Graph Report - Mark-LIV  (2026-09-25)

## Corpus Check
- 63 files · ~117,290 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 3, .ico 1, .obj 1)

## Summary
- 1653 nodes · 3220 edges · 106 communities (82 shown, 24 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 149 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5db5c453`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- game_updater.py
- system_monitor.py
- file_processor.py
- file_controller.py
- KokoroTTSEngine
- avatar_mesh.py
- MainWindow
- gemini.py
- HudCanvas
- PushToTalk
- llm_client.py
- code_helper.py
- HoloAvatar
- memory_manager.py
- _BrowserSession
- computer_control.py
- dev_agent.py
- HueWheel
- tech_font
- EchoGuard
- JarvisUI
- ⚙️ MARK LIV (54)
- ._build_config
- JarvisLive
- audio_devices.py
- crypto-js.min.js
- config_manager.py
- screen_processor.py
- send_message.py
- ._tuning_config
- server.py
- pathlib
- _SessionRegistry
- computer_settings
- .run
- get_input_device
- plugin_loader.py
- MemoryOverlay
- gmail_manager.py
- background_monitor.py
- _RootShim
- sys
- PluginSettingsOverlay
- ui.py
- confirm.py
- ._build_app
- .__init__
- _SysMetrics
- browser_control.py
- main.py
- WakeWordDetector
- DashboardServer
- ._play_audio
- get_brief_enabled
- ._build_jarvis_icon
- RemoteKeyOverlay
- ._apply_ptt_shortcut
- CustomizeOverlay
- action_loader.py
- setter
- ._aes_key
- ._wake_state
- Graphify + Antigravity Project Workflow & Setup Guide
- 🔄 The Foundation Update — in every Mark from LII
- json
- _ensure_network_access
- rules/graphify.md
- desktop.py
- workflows/graphify.md
- _detect_action
- daily_brief.py
- FileDropZone
- ._decrypt
- ._launch
- ._receive_audio
- datetime
- ._send_startup_briefing
- .glance
- _template.py
- _get_base_dir
- _make_uploads_dir
- weather_report.py
- .hide_confirm
- .hide_quiz
- .show_review
- .__init__
- undo.py
- load_api_keys
- calendar_sync.py
- focus_protocol.py
- Daily Brief Protocol
- Email Handling Rules
- Executive Assistant Persona & Behavioral Standards
- Steps
- /email-triage Workflow
- get_plugin_config
- get_base_dir
- .prompt_reconfig
- .show_camera_frame
- .show_confirm
- .show_quiz
- .stop_camera_stream

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 82 edges
2. `JarvisLive` - 51 edges
3. `tech_font()` - 41 edges
4. `JarvisUI` - 40 edges
5. `_BrowserSession` - 32 edges
6. `_resolve_path()` - 21 edges
7. `is_mac()` - 21 edges
8. `computer_control()` - 19 edges
9. `is_windows()` - 19 edges
10. `mono_font()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `🩹 Fixes that came with it` --references--> `computer_settings()`  [INFERRED]
  readme.md → actions/computer_settings.py
- `Steps` --references--> `computer_control()`  [INFERRED]
  .agents/workflows/deep_work.md → actions/computer_control.py
- `Steps` --references--> `daily_brief()`  [INFERRED]
  .agents/workflows/daily_brief.md → actions/daily_brief.py
- `Steps` --references--> `gmail_manager()`  [INFERRED]
  .agents/workflows/daily_brief.md → actions/gmail_manager.py
- `Steps` --references--> `reminder()`  [INFERRED]
  .agents/workflows/daily_brief.md → actions/reminder.py

## Import Cycles
- None detected.

## Communities (106 total, 24 thin omitted)

### Community 0 - "game_updater.py"
Cohesion: 0.06
Nodes (80): _build_google_flights_url(), flight_finder(), _format_spoken(), _format_text_report(), _get_base_dir(), _parse_date(), _parse_flights_with_gemini(), Path (+72 more)

### Community 1 - "system_monitor.py"
Cohesion: 0.20
Nodes (10): _get_cpu_temp(), _get_gpu_usage(), get_system_status(), _nvml_gpu(), System Monitor — background metric checks with voice alert support. Zero…, Snapshot of current system metrics for the system_status tool., Stateful monitor — cooldown state persists across session reconnections. Call…, GPU utilisation via NVML — zero subprocess on all platforms. (+2 more)

### Community 3 - "file_processor.py"
Cohesion: 0.13
Nodes (25): _detect_type(), file_processor(), _file_size_str(), _gemini_client(), _output_path(), _process_archive(), _process_audio(), _process_code() (+17 more)

### Community 4 - "file_controller.py"
Cohesion: 0.13
Nodes (40): copy_file(), create_file(), create_folder(), delete_file(), file_controller(), find_files(), _format_size(), _get_desktop() (+32 more)

### Community 5 - "KokoroTTSEngine"
Cohesion: 0.06
Nodes (22): _compress_silence(), create_tts_player(), EdgeTTSEngine, ElevenLabsTTSEngine, _import_kokoro_pipeline(), KokoroTTSEngine, _synth(), _play_audio_bytes() (+14 more)

### Community 6 - "avatar_mesh.py"
Cohesion: 0.07
Nodes (32): collections, _add_cranium(), _add_neck(), _boundary_loop(), build_head(), _check_landmarks(), get_head_mesh(), _load_obj() (+24 more)

### Community 7 - "MainWindow"
Cohesion: 0.06
Nodes (9): QMainWindow, MainWindow, Slot — display camera preview overlay (main thread)., Slot — runs on Qt main thread. Updates and shows the content panel., Slot — Qt main thread. Lays a document review into the content panel., Slot — Qt main thread. Puts a fresh quiz on the board., Returns True if auto-start is currently registered on this OS., Repaint the push-to-talk row from the saved setting. (+1 more)

### Community 8 - "gemini.py"
Cohesion: 0.06
Nodes (58): _compare(), _ddg_news(), _ddg_search(), _format_ddg(), _format_news(), _gemini_available(), _gemini_headlines(), _gemini_search() (+50 more)

### Community 9 - "HudCanvas"
Cohesion: 0.10
Nodes (12): get_hud_style(), Which centrepiece the HUD draws: the animated head, or the reactor core. Taste,…, QPixmap, HudCanvas, QPainter, Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)., Thread-safe: hand over a schedule of (level, openness, width) frames. The…, Swap the centrepiece. Both objects stay in memory, so the change is instant and… (+4 more)

### Community 10 - "PushToTalk"
Cohesion: 0.15
Nodes (7): chord_label(), PushToTalk, Begin watching. Returns the scope actually achieved., Feed a press/release from a Qt shortcut (non-Windows, or no hook)., Human-readable name of the chord, for the UI and the logs., Calls `on_change(held: bool)` whenever the chord is pressed or released. Start…, global' once a system-wide hook is running, else 'window'.

### Community 11 - "llm_client.py"
Cohesion: 0.14
Nodes (22): call_llm(), call_llm_stream(), call_llm_text(), check_model_available(), ensure_ollama_running(), get_base_dir(), get_llm_provider(), get_llm_settings() (+14 more)

### Community 12 - "code_helper.py"
Cohesion: 0.17
Nodes (26): _build(), _clean_code(), code_helper(), _detect_intent(), _edit_action(), _explain_action(), _fix_code(), _get_gemini() (+18 more)

### Community 13 - "HoloAvatar"
Cohesion: 0.12
Nodes (19): _blend(), _c(), HoloAvatar, QColor, QPainter, _rate(), `col` at alpha `a` pre-mixed onto `bg`, returned fully **opaque**. Qt's raster…, Animated holographic head. One instance per HUD canvas. Lifecycle: av =… (+11 more)

### Community 14 - "memory_manager.py"
Cohesion: 0.12
Nodes (27): _do_shutdown(), Summarise the current session in 1-2 sentences and save to long_term.json., _all_entries(), all_entries_for_ui(), _empty_memory(), _entry_value(), forget(), format_memory_for_prompt() (+19 more)

### Community 16 - "computer_control.py"
Cohesion: 0.18
Nodes (27): _base_dir(), _clear_field(), _click(), _clipboard_get(), _clipboard_paste(), computer_control(), _drag(), _focus_window() (+19 more)

### Community 17 - "dev_agent.py"
Cohesion: 0.17
Nodes (20): _build_project(), _classify_error(), dev_agent(), _fix_files(), _get_model(), _has_error(), _install_dependencies(), _is_rate_limit() (+12 more)

### Community 18 - "HueWheel"
Cohesion: 0.24
Nodes (4): QPointF, QRectF, HueWheel, Circular colour picker. The user drags the handle (small white circle) around…

### Community 19 - "tech_font"
Cohesion: 0.08
Nodes (18): QFont, QHBoxLayout, QVBoxLayout, QWidget, _CameraPreview, ClipboardPanel, _fl(), _sec() (+10 more)

### Community 20 - "EchoGuard"
Cohesion: 0.08
Nodes (14): band_energies(), EchoGuard, ndarray, Classifies microphone blocks while the assistant is speaking. Usage:…, True once the estimate rests on enough real echo to be trusted., Residual left by this room's own echo. Higher = harder to separate., False when the acoustics are too poor to judge on content alone. Speakers…, The residual a block must clear right now to count as a voice. (+6 more)

### Community 21 - "JarvisUI"
Cohesion: 0.12
Nodes (7): main(), runner(), JarvisUI, Thread-safe: feed a 0.0–1.0 live audio level to the HUD waveform. Called from…, Thread-safe: post a schedule of (level, openness, width) mouth frames for…, Thread-safe: display content in the panel below the HUD., Thread-safe: start live camera feed in the full HUD area.

### Community 22 - "⚙️ MARK LIV (54)"
Cohesion: 0.07
Nodes (28): 🧑‍🎤 A real head, rendered in software, 🚀 Capabilities, 👤 Connect with the Creator, Core Features, 🩹 Fixes, How it understands itself, 🙂 It acts while it talks, 🗣️ It answers before it works (+20 more)

### Community 23 - "._build_config"
Cohesion: 0.15
Nodes (12): LiveConnectConfig, _describe_limits(), _describe_tools(), _load_system_prompt(), One line per capability, straight from the live tool declarations. Derived…, The other half of self-knowledge: what is out of reach, and why. Derived from…, Fill {tokens} in the prompt template. A plain replace rather than str.format:…, _render_prompt() (+4 more)

### Community 24 - "JarvisLive"
Cohesion: 0.08
Nodes (14): JarvisLive, Load the detector once (model loads on first start). Idempotent., Called from the detector thread when 'Hey Jarvis' is heard., Auto-sleep after the configured silence window (wake-word mode only)., Enable/disable wake word from the settings UI. Returns a status token:…, Manual sleep/wake button in the UI., Download openwakeword + the model (runs in a UI worker thread)., Thread-safe: ask the run loop to tear down and rebuild the Live session. Called… (+6 more)

### Community 25 - "audio_devices.py"
Cohesion: 0.12
Nodes (19): configure(), _display_name(), _is_pseudo(), prefetch(), _work(), _query(), _collect(), core/audio_devices.py — pick which microphone and which speakers JARVIS uses.… (+11 more)

### Community 27 - "config_manager.py"
Cohesion: 0.18
Nodes (17): ensure_config_dir(), Read-modify-write one key without disturbing the rest of the config., Merge `values` into a namespace's stored config (read-modify-write, like every…, Persist assistant name and user name to config., Persist the chosen Live voice. Unknown names collapse to the default so a bad…, save_api_keys(), save_assistant_config(), _save_flag() (+9 more)

### Community 28 - "screen_processor.py"
Cohesion: 0.16
Nodes (19): _base_dir(), _capture_camera(), _capture_screen(), _compress(), _cv2_backend(), _detect_camera_index(), _get_camera_index(), _get_os() (+11 more)

### Community 29 - "send_message.py"
Cohesion: 0.25
Nodes (19): _base_dir(), _clear_and_paste(), _desktop_send(), _get_os(), _open_app(), _open_browser_url(), _paste_text(), Path (+11 more)

### Community 30 - "._tuning_config"
Cohesion: 0.22
Nodes (7): The optional knobs, kept apart so one bad field can be dropped wholesale. Every…, get_media_resolution(), get_thinking_enabled(), get_turn_tuning(), Whether the Live model may spend tokens thinking before it answers. Off by…, How eagerly the server decides you have stopped speaking. OFF by default, and…, How finely the model tokenises the screenshots and camera frames it is sent.…

### Community 31 - "server.py"
Cohesion: 0.12
Nodes (14): base64, _ensure_certs(), _local_ip(), dashboard/server.py — JARVIS Local HTTP Dashboard Plain HTTP on port 8000 (no…, Return the best LAN-facing IPv4 address, no internet required., Make sure config/certs holds a TLS key pair, generating a self-signed one the…, _read(), fastapi (+6 more)

### Community 32 - "pathlib"
Cohesion: 0.16
Nodes (16): install_and_download(), is_installed(), is_ready(), Local wake-word detection for JARVIS ("Hey Jarvis"). Design goals: • ZERO cost…, True if the openwakeword package is importable (no model check)., True if openwakeword is installed AND its model files are present on disk. This…, One-click setup for the UI button: pip-install openwakeword if missing, then…, pathlib (+8 more)

### Community 33 - "_SessionRegistry"
Cohesion: 0.15
Nodes (5): _detect_default_browser(), Manages all active browser sessions., Is there an active automation session for this browser (or any)?, Returns the last natively-opened URL once (consumed to avoid repeats)., _SessionRegistry

### Community 34 - "computer_settings"
Cohesion: 0.11
Nodes (18): brightness_get(), brightness_set(), computer_settings(), dark_mode(), paste(), press_key(), Current brightness 0-100, or None where it cannot be read., Set brightness to an absolute percentage. Only used to restore a value captured… (+10 more)

### Community 35 - ".run"
Cohesion: 0.12
Nodes (12): BaseException, _get_api_key(), _is_reconnect_signal(), _keep_context_of(), Background task: voice alerts when metrics exceed thresholds., Check user-configured topics once per day; speak alerts when new headlines…, Background task: periodically checks if the user has been silent long enough,…, Forward phone mic PCM chunks from dashboard queue into the Gemini Live session. (+4 more)

### Community 36 - "get_input_device"
Cohesion: 0.25
Nodes (8): get_input_device(), get_output_device(), _patch_config(), Read-modify-write one or more keys in api_keys.json. Every setter in this file…, Microphone device name, or '' for the system default., Speaker device name, or '' for the system default., save_input_device(), save_output_device()

### Community 37 - "plugin_loader.py"
Cohesion: 0.12
Nodes (18): _call_run(), discover_plugins(), _load_error(), _opt_upper(), PluginRecord, PluginRegistry, Exception, Path (+10 more)

### Community 38 - "MemoryOverlay"
Cohesion: 0.16
Nodes (8): ConfirmBanner, _HudOverlay, MemoryOverlay, Base for the floating panels placed by hand over the HUD. They are children of…, The gate in front of an action that cannot be taken back. The old confirmation…, Everything JARVIS has stored about you, and when it learned it. Memory used to…, Take every item out of the layout and detach it from the widget tree in this…, Size the panel to its content, re-centre it, and repaint what the old size…

### Community 39 - "gmail_manager.py"
Cohesion: 0.12
Nodes (21): _clean_header_str(), _extract_body_snippet(), fetch_unread_emails(), gmail_manager(), _load_gmail_creds(), Gmail Manager Action for JARVIS Mark-LIV. Provides full Gmail connectivity: -…, Send an email using Gmail SMTP SSL., Action entry point for Gmail interaction. (+13 more)

### Community 40 - "background_monitor.py"
Cohesion: 0.29
Nodes (12): add_monitor(), check_all(), _is_blocked(), list_monitors(), _load(), BackgroundMonitor — user-configured topic watching. Checks DDG news once per…, Run all pending topic checks (once per day per topic). Returns a list of…, remove_monitor() (+4 more)

### Community 42 - "sys"
Cohesion: 0.28
Nodes (8): _available(), install_for_config(), _pip(), MARK XL — Dependency auto-installer. Called automatically on first launch and…, Return True if the module can be imported (no actual import)., Install all missing packages required by *config*. Blocking — always call from…, importlib_util, sys

### Community 43 - "PluginSettingsOverlay"
Cohesion: 0.20
Nodes (5): QPushButton, PluginManagerOverlay, PluginSettingsOverlay, Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles., Floating overlay — renders per-plugin settings forms. Fully generic: it…

### Community 44 - "ui.py"
Cohesion: 0.09
Nodes (22): list_devices(), Device names for 'input' or 'output'. Falls back to a synchronous query if the…, Holographic AI head for the HUD centre — the thing that used to be a ring stack…, math, pyqt6_qtcore, pyqt6_qtgui, pyqt6_qtwidgets, random (+14 more)

### Community 45 - "confirm.py"
Cohesion: 0.25
Nodes (10): bind(), _log(), _Pending, core/confirm.py — a confirmation the model cannot forge. THE PROBLEM WITH THE…, Called by the UI when the user presses CONFIRM or CANCEL. Runs the stored…, Wire this module to the HUD. Called once from main.py at startup., Park an irreversible action behind the on-screen gate. Returns the sentence the…, request() (+2 more)

### Community 46 - "._build_app"
Cohesion: 0.24
Nodes (6): _auth(), list_files(), revoke_devices(), _safe_filename(), upload_file(), wake_ep()

### Community 47 - ".__init__"
Cohesion: 0.11
Nodes (10): ProactiveEngine, Decides when JARVIS should speak unprompted and builds a context-rich prompt.…, Build a context snapshot for Gemini. Rotates through three focus areas so…, _Popen, Exception, Raised inside the session TaskGroup to force a clean, voluntary reconnect (e.g.…, Session-scoped task: when a voluntary reconnect is requested, raise a signal…, Turn hold-to-talk on or off. Returns the scope actually achieved. (+2 more)

### Community 48 - "_SysMetrics"
Cohesion: 0.21
Nodes (4): Thread-safe speech channel for plugins: lets a plugin ask JARVIS to say…, _nvml_gpu_windows(), Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess., _SysMetrics

### Community 49 - "browser_control.py"
Cohesion: 0.24
Nodes (11): browser_control(), _find_exe_windows(), _find_opera_windows(), _log(), _normalize_url(), _open_native(), Bare words like "instagram" → "https://instagram.com" Domains like…, Opens the user's REAL browser normally — with their own profile, logged-in… (+3 more)

### Community 50 - "main.py"
Cohesion: 0.14
Nodes (12): ProactiveEngine 2.0 — context-aware, time-aware, non-repetitive background…, asyncio, Telling the user's voice apart from our own coming back through the speakers.…, Push-to-talk — hold a key, speak, release. Why this exists ---------------…, Text-to-Speech engines for MARK XL. EdgeTTS – free Microsoft TTS (internet…, google, google_genai, numpy (+4 more)

### Community 51 - "WakeWordDetector"
Cohesion: 0.20
Nodes (4): Runs the wake model in a dedicated thread. The mic thread calls feed() with raw…, Load the model and spawn the inference thread. Returns True on success. Safe to…, Called from the mic callback (real-time thread). Must stay cheap and never…, WakeWordDetector

### Community 52 - "DashboardServer"
Cohesion: 0.25
Nodes (3): DashboardServer, URL for manual browser entry. When HTTPS active, points to alias port (also…, Second HTTPS server on PORT+1 sharing the same app and in-memory state. Chrome…

### Community 53 - "._play_audio"
Cohesion: 0.22
Nodes (7): callback(), _open_mic(), _pcm_level(), _pcm_visemes(), Map a block of int16 PCM samples to a 0.0–1.0 loudness level for the HUD…, Slice a PCM block into (level, openness, width) frames, one per 20 ms. Returns…, True while the speakers may still be finishing our last sentence.

### Community 55 - "._build_jarvis_icon"
Cohesion: 0.20
Nodes (6): _base_dir(), Path, Render a JARVIS arc-reactor icon at 4× resolution and downsample for crisp…, Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd. Tries…, Resolve the user's REAL desktop directory instead of assuming ~/Desktop, which…, Create a desktop shortcut on Windows / macOS / Linux. Never opens a terminal,…

### Community 56 - "RemoteKeyOverlay"
Cohesion: 0.27
Nodes (4): Floating overlay — QR code for instant phone pairing + manual key fallback., Call from any thread when a phone successfully connects., RemoteKeyOverlay, _lbl()

### Community 57 - "._apply_ptt_shortcut"
Cohesion: 0.22
Nodes (5): qt_sequence(), The same chord as a QKeySequence string., _press(), Bind the chord inside the window when no global hook is available. On macOS and…, Report a windowed press/release to whoever owns the microphone.

### Community 58 - "CustomizeOverlay"
Cohesion: 0.21
Nodes (5): CustomizeOverlay, _lbl(), Floating overlay — change assistant name, user name, UI colour and voice., Highlight the selected voice pill; dim the rest., Updates the selected colour; hex box + wheel stay in sync, theme is live-…

### Community 59 - "action_loader.py"
Cohesion: 0.12
Nodes (15): ActionRecord, ActionRegistry, _call_handler(), discover_actions(), _opt_upper(), Path, Action discovery, validation, and dispatch — the built-in twin of…, Invoke the handler passing only the context kwargs it actually declares (or all… (+7 more)

### Community 61 - "._aes_key"
Cohesion: 0.32
Nodes (6): auto_login(), device_login_ep(), login(), phone_audio_ws(), _derive_key(), SHA-256(sessionKey‖salt) → 32-byte AES-256 key (microseconds, no PBKDF2 needed).

### Community 64 - "🔄 The Foundation Update — in every Mark from LII"
Cohesion: 0.22
Nodes (9): _get_macos_wifi_interface(), toggle_wifi(), ⚠️ A confirmation the model can't forge, 🧠 A memory that actually remembers, 🩹 Fixes that came with it, 🎧 It finally asks which microphone, 🔗 It stops forgetting the conversation when the connection drops, 🔄 The Foundation Update — in every Mark from LII (+1 more)

### Community 65 - "json"
Cohesion: 0.14
Nodes (9): ndarray, Speech-to-Text engines for MARK XL. Whisper – offline transcription via faster-…, Offline transcription using faster-whisper., Transcribe a float32 mono 16 kHz numpy array. Returns transcript string., Streaming transcription using Vosk., Feed raw int16 LE PCM bytes. Returns (text, is_final)., VoskSTT, WhisperSTT (+1 more)

### Community 68 - "desktop.py"
Cohesion: 0.21
Nodes (18): _ask_gemini_for_desktop_action(), _build_sandbox(), clean_desktop(), desktop_control(), _execute_generated_code(), _get_api_key(), _get_base_dir(), get_current_wallpaper() (+10 more)

### Community 70 - "_detect_action"
Cohesion: 0.40
Nodes (5): _detect_action(), _normalise(), Resolve a free-text description to an action name, locally. Returns {"action":…, What to tell the model when nothing matched. Names real actions so its retry…, _suggest()

### Community 71 - "daily_brief.py"
Cohesion: 0.16
Nodes (16): daily_brief(), _get_gmail_brief(), _get_greeting(), _get_live_weather(), _get_reminders_brief(), _get_system_vitals(), Daily Brief Action for JARVIS Mark-LIV. Provides the ultimate morning and daily…, Inspect core CPU, RAM, and Battery vitals. (+8 more)

### Community 72 - "FileDropZone"
Cohesion: 0.18
Nodes (3): QDragEnterEvent, QDropEvent, FileDropZone

### Community 73 - "._decrypt"
Cohesion: 0.40
Nodes (4): command(), ws_ep(), _decrypt_cbc(), Decrypt base64(IV[16] ‖ ciphertext) with AES-256-CBC + PKCS7.

### Community 74 - "._launch"
Cohesion: 0.29
Nodes (5): _firefox_profile_dir(), launch_persistent_context already opens a starting tab. Instead of opening a…, Launches the browser with the real user profile. Does nothing if the context is…, _real_profile_dir(), Page

### Community 75 - "._receive_audio"
Cohesion: 0.29
Nodes (4): _clean_transcript(), _is_repeat_chunk(), Send a captured frame immediately after its tool response. The frame is already…, True if this transcript chunk has already been seen this turn. Guards against…

### Community 76 - "datetime"
Cohesion: 0.41
Nodes (11): _base_dir(), _get_os(), Path, reminder(), _sanitise(), _schedule_linux(), _schedule_mac(), _schedule_windows() (+3 more)

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

### Community 82 - "weather_report.py"
Cohesion: 0.50
Nodes (4): _log(), weather_action(), urllib_parse, webbrowser

### Community 86 - ".__init__"
Cohesion: 0.13
Nodes (7): QTextEdit, _DropCanvas, _file_category(), _fmt_size(), LogWidget, QColor, qcol()

### Community 87 - "undo.py"
Cohesion: 0.17
Nodes (10): clear(), history(), peek(), core/undo.py — one shared undo stack for every action that changes state. WHY…, Forget the stack. Called when the app shuts down so closures holding old file…, Label of the operation that `undo_last()` would reverse, or ''., Most recent first — used by the UI panel and the `undo` tool's list mode., Reverse the most recent reversible operation. The entry is popped *before*… (+2 more)

### Community 88 - "load_api_keys"
Cohesion: 0.22
Nodes (9): get_assistant_name(), get_gemini_key(), get_push_to_talk_enabled(), get_wake_word_enabled(), is_configured(), load_api_keys(), Whether local wake-word gating is on (assistant sleeps until 'Hey Jarvis')., Hold-a-key-to-speak. When on, the mic is closed unless the chord is held. (+1 more)

### Community 89 - "calendar_sync.py"
Cohesion: 0.47
Nodes (5): _load_events(), Calendar Sync Plugin for JARVIS Mark-LIV. Tracks agenda, meetings,…, Execute calendar action., run(), _save_events()

### Community 93 - "focus_protocol.py"
Cohesion: 0.47
Nodes (5): Focus Protocol Plugin for JARVIS Mark-LIV. Manages deep work intervals,…, Execute focus protocol actions., _read_state(), run(), _write_state()

### Community 94 - "Daily Brief Protocol"
Cohesion: 0.50
Nodes (3): Daily Brief Protocol, Purpose, Rules

### Community 95 - "Email Handling Rules"
Cohesion: 0.50
Nodes (3): Email Handling Rules, Purpose, Rules

### Community 96 - "Executive Assistant Persona & Behavioral Standards"
Cohesion: 0.50
Nodes (3): Core Operational Rules, Executive Assistant Persona & Behavioral Standards, Persona & Demeanor

### Community 97 - "Steps"
Cohesion: 0.50
Nodes (3): /daily-brief Workflow, Objective, Steps

### Community 98 - "/email-triage Workflow"
Cohesion: 0.50
Nodes (3): /email-triage Workflow, Objective, Steps

### Community 99 - "get_plugin_config"
Cohesion: 0.50
Nodes (4): get_plugin_config(), get_plugin_setting(), All stored values for a namespace (empty dict if none set yet)., A single value from a namespace, or `default` if unset.

## Knowledge Gaps
- **39 isolated node(s):** `C`, `Purpose`, `Rules`, `Purpose`, `Rules` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 646 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JarvisUI` connect `JarvisUI` to `.prompt_reconfig`, `.show_camera_frame`, `.show_confirm`, `.show_quiz`, `.stop_camera_stream`, `ui.py`, `.glance`, `.__init__`, `main.py`, `.hide_confirm`, `.hide_quiz`, `.show_review`, `.__init__`, `JarvisLive`, `._apply_ptt_shortcut`, `setter`, `._wake_state`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Why does `MainWindow` connect `MainWindow` to `HudCanvas`, `ui.py`, `tech_font`, `.__init__`, `._build_jarvis_icon`, `get_brief_enabled`, `._apply_ptt_shortcut`, `setter`, `._wake_state`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Why does `JarvisLive` connect `JarvisLive` to `system_monitor.py`, `.run`, `avatar_mesh.py`, `background_monitor.py`, `PushToTalk`, `._receive_audio`, `._send_startup_briefing`, `memory_manager.py`, `.__init__`, `_SysMetrics`, `main.py`, `WakeWordDetector`, `EchoGuard`, `DashboardServer`, `._play_audio`, `._build_config`, `JarvisUI`, `._tuning_config`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `JarvisLive` (e.g. with `ProactiveEngine` and `SystemMonitor`) actually correct?**
  _`JarvisLive` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `C`, `Purpose`, `Rules` to the rest of the system?**
  _39 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `game_updater.py` be split into smaller, more focused modules?**
  _Cohesion score 0.060144346431435444 - nodes in this community are weakly interconnected._
- **Should `computer_settings.py` be split into smaller, more focused modules?**
  _Cohesion score 0.041666666666666664 - nodes in this community are weakly interconnected._