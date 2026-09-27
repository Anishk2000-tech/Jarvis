"""
Self-test for an installed JARVIS — run  JARVIS-Console.exe --selftest

Checks that the bundled Python has every library, that every tool and plugin
loads, that the offline models work, and that the interface can be built.
Nothing is changed on the machine; no microphone, camera or network is needed.
Exit code 0 = everything essential works. A report is written to
logs/selftest.txt.
"""
from __future__ import annotations

import os
import platform
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
_results: list[tuple[str, str, str]] = []     # (status, name, detail)


def check(name: str, critical: bool = True):
    def deco(fn):
        t0 = time.monotonic()
        try:
            detail = fn() or ""
            _results.append(("PASS", name, f"{detail} ({time.monotonic() - t0:.1f}s)"))
        except Exception as e:
            status = "FAIL" if critical else "WARN"
            _results.append((status, name, f"{type(e).__name__}: {str(e)[:300]}"))
            if critical:
                traceback.print_exc()
        return fn
    return deco


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen") if "--gui" not in sys.argv else None
    sys.path.insert(0, str(HERE))
    is_win = platform.system() == "Windows"

    @check("python")
    def _():
        return f"{sys.version.split()[0]} on {platform.platform()} ({sys.executable})"

    mods = ["PyQt6.QtWidgets", "PyQt6.QtMultimedia", "numpy", "sounddevice", "cv2", "onnxruntime",
            "faster_whisper", "ctranslate2", "edge_tts", "miniaudio", "soundfile", "piper", "kokoro_onnx",
            "rapidocr_onnxruntime", "playwright.async_api", "google.genai", "fastapi", "uvicorn",
            "cryptography", "pyautogui", "pyperclip", "mss", "PIL", "psutil", "requests", "bs4", "ddgs",
            "yt_dlp", "docx", "pptx", "pdfplumber", "PyPDF2", "openpyxl", "pandas", "tinytuya",
            "paho.mqtt.client", "kasa", "zeroconf", "serial", "qrcode", "send2trash", "pynvml",
            "youtube_transcript_api", "googleapiclient.discovery"]
    if is_win:
        mods += ["win32com.client", "win32gui", "pythoncom", "pywinauto", "pycaw.pycaw", "comtypes", "wmi",
                 "win10toast"]
    for m in mods:
        check(f"import {m}")(lambda m=m: __import__(m) and "")

    @check("face detector API")
    def _():
        import cv2
        assert hasattr(cv2, "FaceDetectorYN") and hasattr(cv2, "FaceRecognizerSF")
        return cv2.__version__

    @check("actions load")
    def _():
        import main
        from core.action_loader import discover_actions
        rejected = []
        reg = discover_actions(HERE / "actions", {t["name"] for t in main.TOOL_DECLARATIONS},
                               logger=lambda m: rejected.append(m) if m.startswith("Action rejected") else None)
        assert not rejected, "; ".join(rejected)
        return f"{len(reg.names())} actions"

    @check("plugins load")
    def _():
        from core.plugin_loader import discover_plugins
        msgs = []
        reg = discover_plugins(HERE / "plugins", set(), logger=msgs.append)
        bad = [m for m in msgs if m.startswith("Plugin rejected")]
        assert not bad, "; ".join(bad)
        return f"{len(reg.get_tool_declarations())} plugins"

    @check("tool schemas convert")
    def _():
        import main
        from core import tool_schema
        from core.action_loader import discover_actions
        from core.plugin_loader import discover_plugins
        decls = (main.TOOL_DECLARATIONS
                 + discover_actions(HERE / "actions", set(), logger=lambda m: None).get_tool_declarations()
                 + discover_plugins(HERE / "plugins", set(), logger=lambda m: None).get_tool_declarations())
        tools = tool_schema.to_openai_tools(decls, compact=True)
        tool_schema.to_anthropic_tools(decls)
        return f"{len(tools)} tools"

    @check("voice activity model")
    def _():
        import numpy as np
        from core import vad
        det, kind = vad.make_detector()
        det(np.zeros(vad.FRAME, dtype=np.float32))
        assert kind == "silero", f"fell back to {kind}"
        return kind

    @check("OCR (offline)")
    def _():
        from PIL import Image, ImageDraw
        from core import screen_reader
        im = Image.new("RGB", (400, 120), "white")
        ImageDraw.Draw(im).text((20, 40), "JARVIS SELF TEST", fill="black")
        found = screen_reader.ocr(im.resize((1200, 360)))
        return f"{len(found)} text boxes"

    @check("face models", critical=False)
    def _():
        from core import face_id
        det = face_id.MODELS / face_id._YUNET
        rec = face_id.MODELS / face_id._SFACE
        assert det.exists() and rec.exists(), "not bundled — they download on first use"
        import numpy as np
        eng = face_id.FaceEngine(log=lambda m: None)
        eng.detect(np.zeros((240, 320, 3), dtype=np.uint8))
        return "YuNet + SFace ready"

    @check("brain config")
    def _():
        from core import brain_config
        hw = brain_config.detect_hardware()
        rec = brain_config.recommend(hw)
        return f"RAM {hw['ram_gb']} GB, VRAM {hw['vram_gb']} GB → {rec['model']}"

    @check("interface builds")
    def _():
        from PyQt6.QtWidgets import QApplication
        import ui
        from ui_brain import BrainSettingsOverlay
        app = QApplication.instance() or QApplication(sys.argv)
        win = ui.MainWindow("face.png")
        ov = BrainSettingsOverlay(win.centralWidget(), first_run=True)
        ov.show()
        app.processEvents()
        win.close()
        return "main window + settings"

    if is_win:
        @check("PowerShell tool")
        def _():
            from actions.terminal import run_command
            out = run_command("Write-Output 'jarvis-ok'", "powershell", timeout=60)
            assert "jarvis-ok" in out, out
            return "ok"

        @check("Windows voices (SAPI)", critical=False)
        def _():
            from core.tts_engine import SapiTTS
            voices = SapiTTS.list_voices()
            import numpy as np
            t = SapiTTS()
            t.load()
            pcm = np.concatenate(list(t.synth("Self test.")))
            return f"{len(voices)} voices, {pcm.size / 24000:.1f}s rendered"

        @check("screen reading (UI Automation)", critical=False)
        def _():
            from core import screen_reader
            obs = screen_reader.observe(with_image=True, with_ocr=False)
            return f"'{obs.title[:40]}': {len(obs.elements)} elements"

        @check("audio devices", critical=False)
        def _():
            import sounddevice as sd
            return f"{len(sd.query_devices())} devices"

    lines = [f"JARVIS self-test — {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    for status, name, detail in _results:
        lines.append(f"[{status}] {name}: {detail}")
    fails = sum(1 for r in _results if r[0] == "FAIL")
    warns = sum(1 for r in _results if r[0] == "WARN")
    lines.append(f"\n{len(_results)} checks — {fails} failed, {warns} warnings.")
    report = "\n".join(lines)
    print(report)
    try:
        (HERE / "logs").mkdir(exist_ok=True)
        (HERE / "logs" / "selftest.txt").write_text(report, encoding="utf-8")
    except Exception:
        pass
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
