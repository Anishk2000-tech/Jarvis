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
import re
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
            "paho.mqtt.client", "kasa", "zeroconf", "serial", "qrcode", "send2trash", "pynvml", "pkg_resources",
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

    @check("LLM streaming + tool call (local fake Ollama)")
    def _():
        import json as _json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from core import llm

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                if self.path == "/api/show":
                    body = _json.dumps({"capabilities": ["completion", "tools"]}).encode()
                else:
                    lines = [{"message": {"content": "Opening it. "}, "done": False},
                             {"message": {"content": "", "tool_calls": [{"function": {
                                 "name": "open_app", "arguments": {"app_name": "notepad"}}}]}, "done": False},
                             {"message": {"content": ""}, "done": True}]
                    body = "\n".join(_json.dumps(x) for x in lines).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            s = llm.Settings(provider="ollama", base_url=f"http://127.0.0.1:{srv.server_address[1]}",
                             model="selftest")
            decl = [{"name": "open_app", "description": "Open an app", "parameters": {
                "type": "OBJECT", "properties": {"app_name": {"type": "STRING"}}}}]
            ev = llm.chat([{"role": "user", "content": "open notepad"}], decl, s=s)
            assert ev.tool_calls and ev.tool_calls[0].arguments == {"app_name": "notepad"}, ev
            return "tool call parsed"
        finally:
            srv.shutdown()

    @check("object detection (live vision / CCTV)", critical=False)
    def _():
        import numpy as np
        from core import vision_detect
        assert vision_detect.model_path().exists(), "not bundled — it downloads on first use"
        det = vision_detect.Detector(log=lambda m: None)
        img = np.zeros((360, 640, 3), np.uint8)
        t0 = time.monotonic()
        det.detect(img)
        return f"NanoDet ready, {(time.monotonic() - t0) * 1000:.0f} ms per frame"

    @check("video decoding for IP cameras (FFmpeg)")
    def _():
        import threading
        import cv2
        import numpy as np
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        info = cv2.getBuildInformation()
        assert re.search(r"FFMPEG:\s+YES", info), "OpenCV was built without FFmpeg"
        jpg = cv2.imencode(".jpg", np.full((120, 160, 3), 90, np.uint8))[1].tobytes()

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                        time.sleep(0.05)
                except Exception:
                    pass
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            from core import cctv
            frame = cctv.grab_once(f"http://127.0.0.1:{srv.server_address[1]}/video.mjpg", timeout=10)
            assert frame is not None and frame.shape[:2] == (120, 160), "no frame from a local MJPEG stream"
        finally:
            srv.shutdown()
        return "FFmpeg reads network video"

    @check("voice volume boost")
    def _():
        import numpy as np
        from core import audio_fx
        t = np.arange(24000) / 24000
        x = (np.sin(2 * np.pi * 200 * t) * np.clip(np.sin(2 * np.pi * 3 * t), 0, 1) * 30000).astype(np.int16)
        y = audio_fx.apply_gain(x, 200)
        assert y.dtype == np.int16 and np.abs(y.astype(np.int32)).max() < 32767
        return "0-200 % with limiter"

    @check("web research (offline parse)")
    def _():
        from core import websearch
        text = websearch.html_to_text("<html><body><nav>menu</nav><article><p>The Eiffel Tower is 330 metres "
                                      "tall, measured in 2022 after a new antenna.</p></article></body></html>")
        best = websearch.best_passages("how tall is the eiffel tower", [("x", text)])
        assert best and "330" in best[0][1], best
        assert websearch.needs_fresh_info("What is the price of gold today?")
        return "page reading + ranking"

    @check("learning memory")
    def _():
        import tempfile
        from pathlib import Path as _P
        from core import knowledge
        with tempfile.TemporaryDirectory() as d:
            st = knowledge.KnowledgeStore(_P(d) / "k.jsonl")
            st.add("The owner's sister Priya visits on Sundays", "person")
            st.save()
            assert st.search("when does priya visit")
        return "store + recall"

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
        from ui_cctv import CameraWallOverlay
        app = QApplication.instance() or QApplication(sys.argv)
        win = ui.MainWindow("face.png")
        ov = BrainSettingsOverlay(win.centralWidget(), first_run=True)
        ov.show()
        wall = CameraWallOverlay(win.centralWidget())
        wall.show()
        app.processEvents()
        win.close()
        return "main window + settings + camera wall"

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
