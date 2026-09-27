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
           conversation:  qwen2.5:7b   (reliable with tools)
                          qwen2.5:3b   (fastest replies, fits the GPU)
           vision:        qwen2.5vl:3b (lets it see the screen/camera)
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

3. THINGS TO TRY
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

4. FROM YOUR PHONE
   ⚙ SETUP → REMOTE CONTROL shows a QR code for the local dashboard.
   For anywhere-access, create a Telegram bot with @BotFather, paste the
   token in ⚙ SETUP → 🧠 AI BRAIN & VOICE → REMOTE, and send /pair <code>.

5. SAFETY
   Shutdown, restart, WiFi, destructive commands, sending e-mail and
   installing new skills always wait for you: press CONFIRM or say "confirm".
   Say "undo" to reverse file moves and setting changes.
   Move the mouse hard into a screen corner to stop the computer agent.

6. IF SOMETHING DOESN'T WORK
   * Start menu → JARVIS → "JARVIS self-test" checks every component.
   * Start menu → "JARVIS (with log console)" shows the live log.
   * The log file is  app\logs\jarvis.log  in the install folder.
   * Windows SmartScreen may warn about an unrecognised app the first time:
     click "More info" → "Run anyway" (the installer is not code-signed).

Your data (settings, API keys, memories, face data, transcripts, models) stays
in the install folder on this PC:  %LOCALAPPDATA%\Programs\JARVIS\app

License: CC BY-NC 4.0 (personal, non-commercial use). Based on MARK LV by
FatihMakes — https://www.youtube.com/@FatihMakes
