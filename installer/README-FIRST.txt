JARVIS — QUICK START
====================

1. CHOOSE A BRAIN (first launch)
   JARVIS asks which AI model should power it:

   * Ollama (recommended, free, private, offline)
       - Install Ollama from https://ollama.com/download/windows
       - In JARVIS pick "Ollama", keep the suggested model and press
         INITIALISE. The model downloads automatically the first time
         (a few GB — watch the progress in the log on the right).
       - For a laptop with 32 GB RAM and a 4 GB GPU:
           gemma4:e4b    talks, SEES and uses tools in one model — the
                         best choice for live vision and CCTV (leave the
                         vision model empty)
           qwen2.5:7b    most dependable with tools; add qwen2.5vl:3b as
                         the vision model
           qwen2.5:3b    fastest replies, fits the GPU
         Set these in  ⚙ SETUP → 🧠 AI BRAIN & VOICE.

   * LM Studio (free, private): load a model, open the Developer tab,
     start the server, then pick "LM Studio" in JARVIS.

   * Gemini Live (most natural real-time voice, free key from
     https://aistudio.google.com/app/apikey), OpenAI-compatible APIs
     (OpenAI, Groq, OpenRouter, DeepSeek…), Anthropic Claude, or Gemini text.

2. TALK TO IT
   Just speak. Say "stop" or talk over it to interrupt. Type in the box if
   you prefer. In AMBIENT mode (⚙ CONTROLS → LISTEN) it hears the whole room
   and only answers when you say its name.

   The first time, speech recognition (Whisper) downloads its model
   (~480 MB for "small"). The voice uses Microsoft Edge neural voices
   (internet) and falls back to the built-in Windows voice when offline.

3. EYES, CAMERAS, WEB, MEMORY, VOLUME
   * LIVE VISION (⚙ CONTROLS → LIVE VISION): the webcam stays on and it
     sees who and what is in front of it — "what am I holding?", "how do I
     look?". It greets people it knows; say "remember my face" first. How
     often it speaks up by itself: ⚙ SETUP → AI BRAIN & VOICE → LIVE VISION.
   * CCTV (⚙ CONTROLS → CCTV CAMERAS): add WiFi cameras by brand + IP +
     the camera's user/password, or press DISCOVER for ONVIF cameras. Tapo:
     create a "Camera Account" in the Tapo app first. EZVIZ: user admin,
     password = the verification code on the label. Modes: home (announces
     visitors), night / away (photos to your phone via Telegram).
     Say "I'm leaving" to switch to away, "what happened at the gate?".
   * WEB: it looks up anything current by itself. For Google's own AI
     answer, add a free Gemini key (aistudio.google.com) in the settings.
   * LEARNING: it remembers what it learns from what it sees and hears.
     "What have you learned about me?" — "forget that".
   * VOLUME: ⚙ CONTROLS → VOICE slider goes to 200 %, or say "speak louder".

4. THINGS TO TRY
   "Open Notepad and write a shopping list, then save it on the desktop"
   "What's using all my memory?"                    (terminal / PowerShell)
   "Look at my screen and tell me what's wrong"     (vision)
   "Remember my face" … later "who's in front of the camera?"
   "Every weekday at 8:30 tell me the weather and the news"
   "Turn off all the lights" / "start the robot vacuum"
     (connect Home Assistant, SmartThings, Tuya, Hue… in
      ⚙ SETUP → PLUGIN SETTINGS → Smart Home, then say "import my devices")
   "Discover my boards" / "set the servo on pin 13 to 90 degrees"
     (flash app\firmware\jarvis_esp32 or jarvis_arduino with the Arduino IDE)
   "Summarise what we talked about this morning"   (ambient transcript)
   "Read my unread e-mail"   (⚙ PLUGIN SETTINGS → E-mail, app password)
   "Create a tool that checks a web page for price drops"   (new skill)

5. FROM YOUR PHONE
   ⚙ SETUP → REMOTE CONTROL shows a QR code for the local dashboard.
   For anywhere-access, create a Telegram bot with @BotFather, paste the
   token in ⚙ SETUP → 🧠 AI BRAIN & VOICE → REMOTE, and send /pair <code>.

6. SAFETY
   Shutdown, restart, WiFi, destructive commands, sending e-mail and
   installing new skills always wait for you: press CONFIRM or say "confirm".
   Say "undo" to reverse file moves and setting changes.
   Move the mouse hard into a screen corner to stop the computer agent.

7. IF SOMETHING DOESN'T WORK
   * It doesn't hear you / face ID sees nothing: Windows Settings → Privacy →
     Microphone (and Camera) → turn on "Allow desktop apps to access your
     microphone/camera". Pick the right microphone in ⚙ SETUP → AUDIO DEVICES.
   * A CCTV camera stays "error": check the IP, the camera's own user and
     password, and that RTSP/ONVIF is switched on in the camera's app. The
     camera and the PC must be on the same network.
   * Start menu → JARVIS → "JARVIS self-test" checks every component.
   * Start menu → "JARVIS (with log console)" shows the live log.
   * The log file is  app\logs\jarvis.log  in the install folder.
   * Windows SmartScreen may warn about an unrecognised app the first time:
     click "More info" → "Run anyway" (the installer is not code-signed).

Your data (settings, API keys, memories, face data, transcripts, models) stays
in the install folder on this PC:  %LOCALAPPDATA%\Programs\JARVIS\app

License: CC BY-NC 4.0 (personal, non-commercial use). Based on MARK LV by
FatihMakes — https://www.youtube.com/@FatihMakes
