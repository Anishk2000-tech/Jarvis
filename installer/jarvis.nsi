; JARVIS — Windows installer (NSIS 3)
;
; Built by installer/build_windows.py, which prepares STAGE:
;   STAGE\python\        a private Python 3.12 with every library pre-installed
;   STAGE\app\           the assistant
;   STAGE\JARVIS.exe, STAGE\JARVIS-Console.exe, STAGE\LICENSE.txt, STAGE\README-FIRST.txt
;
; Installs per user (no administrator rights needed) into
; %LOCALAPPDATA%\Programs\JARVIS, so the assistant can write its settings,
; memories and downloaded models next to itself.

Unicode true
!ifndef VERSION
  !define VERSION "56.0.0"
!endif
!ifndef STAGE
  !define STAGE "build\stage"
!endif
!ifndef OUTFILE
  !define OUTFILE "dist\JARVIS-Setup.exe"
!endif

!define APPNAME "JARVIS"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVIS"

Name "${APPNAME}"
Caption "${APPNAME} ${VERSION} Setup"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\JARVIS"
InstallDirRegKey HKCU "Software\JARVIS" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
BrandingText "JARVIS · Mark LVI"
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "JARVIS"
VIAddVersionKey "FileDescription" "JARVIS personal AI assistant — setup"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "CC BY-NC 4.0 — based on MARK LV by FatihMakes"

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define MUI_ICON "${STAGE}\app\config\jarvis.ico"
!define MUI_UNICON "${STAGE}\app\config\jarvis.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to JARVIS"
!define MUI_WELCOMEPAGE_TEXT "This installs JARVIS, a voice assistant that can see, hear, speak and operate this computer.$\r$\n$\r$\nIt runs on local AI models (Ollama or LM Studio — free and private) or on cloud models (Gemini, OpenAI-compatible, Claude).$\r$\n$\r$\nNo administrator rights and no Docker are needed. About 1.3 GB of disk space is used.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN "$INSTDIR\JARVIS.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Start JARVIS now"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README-FIRST.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Show the quick-start guide"
!define MUI_COMPONENTSPAGE_SMALLDESC

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${STAGE}\LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; Refuse to overwrite files that are in use: JARVIS holds a named mutex while running.
Function .onInit
  retry:
  System::Call 'kernel32::OpenMutexW(i 0x00100000, i 0, w "Local\JARVIS-Assistant") i .r0'
  ${If} $0 != 0
    System::Call 'kernel32::CloseHandle(i r0)'
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "JARVIS is running. Close it (right-click its taskbar icon → Close), then press Retry." /SD IDCANCEL IDRETRY retry
    Abort
  ${EndIf}
FunctionEnd

Section "JARVIS (required)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  DetailPrint "Removing the previous version's program files (your settings and memories are kept)…"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app\core"
  RMDir /r "$INSTDIR\app\actions"
  RMDir /r "$INSTDIR\app\dashboard"
  RMDir /r "$INSTDIR\app\firmware"
  Delete "$INSTDIR\app\*.py"
  Delete "$INSTDIR\app\plugins\_smart_home_backends.py"
  Delete "$INSTDIR\app\plugins\smart_home.py"
  Delete "$INSTDIR\app\plugins\maker_hardware.py"
  Delete "$INSTDIR\app\plugins\email_client.py"

  DetailPrint "Installing the private Python runtime and libraries (this takes a minute)…"
  SetOutPath "$INSTDIR\python"
  File /r "${STAGE}\python\*.*"
  DetailPrint "Installing JARVIS…"
  SetOutPath "$INSTDIR\app"
  File /r "${STAGE}\app\*.*"
  SetOutPath "$INSTDIR"
  File "${STAGE}\JARVIS.exe"
  File "${STAGE}\JARVIS-Console.exe"
  File "${STAGE}\LICENSE.txt"
  File "${STAGE}\README-FIRST.txt"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\JARVIS" "InstallDir" "$INSTDIR"

  CreateDirectory "$SMPROGRAMS\JARVIS"
  CreateShortcut "$SMPROGRAMS\JARVIS\JARVIS.lnk" "$INSTDIR\JARVIS.exe" "" "$INSTDIR\JARVIS.exe" 0
  CreateShortcut "$SMPROGRAMS\JARVIS\JARVIS (with log console).lnk" "$INSTDIR\JARVIS-Console.exe" "" "$INSTDIR\JARVIS.exe" 0
  CreateShortcut "$SMPROGRAMS\JARVIS\JARVIS self-test.lnk" "$INSTDIR\JARVIS-Console.exe" "--selftest" "$INSTDIR\JARVIS.exe" 0
  CreateShortcut "$SMPROGRAMS\JARVIS\Quick-start guide.lnk" "$INSTDIR\README-FIRST.txt"
  CreateShortcut "$SMPROGRAMS\JARVIS\Uninstall JARVIS.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "JARVIS — AI assistant"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "JARVIS (Mark LVI)"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\JARVIS.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" 1350000
SectionEnd

Section "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\JARVIS.lnk" "$INSTDIR\JARVIS.exe" "" "$INSTDIR\JARVIS.exe" 0
SectionEnd

Section /o "Start JARVIS when Windows starts" SecAutostart
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "JARVIS_AI" '"$INSTDIR\JARVIS.exe"'
SectionEnd

Section "Browser automation engine (downloads ~150 MB)" SecChromium
  DetailPrint "Downloading Chromium for browser automation (needs internet)…"
  nsExec::ExecToLog '"$INSTDIR\python\python.exe" -m playwright install chromium'
  Pop $0
  ${If} $0 != 0
    DetailPrint "Chromium was not downloaded (code $0). Browser automation will download it on first use."
  ${EndIf}
SectionEnd

Section /o "Open the Ollama download page (free local AI models)" SecOllama
  ExecShell "open" "https://ollama.com/download/windows"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "The assistant and its private Python runtime."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "A JARVIS icon on the desktop."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAutostart} "Always-on assistant: start with Windows."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecChromium} "Lets JARVIS click, type and fill forms on web pages."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecOllama} "Ollama runs free AI models on this PC. Install it to use JARVIS offline."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  Delete "$DESKTOP\JARVIS.lnk"
  RMDir /r "$SMPROGRAMS\JARVIS"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "JARVIS_AI"
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\JARVIS"

  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app\core"
  RMDir /r "$INSTDIR\app\actions"
  RMDir /r "$INSTDIR\app\dashboard"
  RMDir /r "$INSTDIR\app\firmware"
  Delete "$INSTDIR\app\*.py"
  Delete "$INSTDIR\JARVIS.exe"
  Delete "$INSTDIR\JARVIS-Console.exe"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\README-FIRST.txt"

  MessageBox MB_YESNO|MB_ICONQUESTION "Also delete your JARVIS settings, API keys, memories, face data, transcripts and downloaded models?$\r$\n$\r$\nChoose No to keep them for a later reinstall." /SD IDNO IDNO keep
    RMDir /r "$INSTDIR"
    Goto done
  keep:
    DetailPrint "Kept your data in $INSTDIR\app (config, memory, models, plugins)."
  done:
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
