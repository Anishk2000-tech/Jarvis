"""
Face recognition — knowing who is in front of the computer.

Models: OpenCV's YuNet face detector (0.2 MB) and SFace recogniser (37 MB),
both built into opencv-python, running on the CPU in a few milliseconds per
frame. They are downloaded once into models/faces/ (the installer bundles them
when it can). Nothing leaves the machine: a face is kept as a 128-number
embedding in memory/faces/, never as a photo.

What it enables
  * enrol the owner ("remember my face") and other people ("this is Rahul")
  * "who is in front of the camera?"
  * presence: greet the owner on return, optionally lock the PC when they
    leave, optionally alert (HUD + Telegram photo) when a stranger sits down
  * owner-only mode: voice commands are obeyed only while the owner is in view

Limits, stated plainly: this is identification, not security-grade
authentication — there is no liveness check, so a good photo of the owner can
fool it. Lighting and angle matter; enrol in the light you normally sit in.
"""
from __future__ import annotations

import json
import platform
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from core import brain_config, runtime
from core.camera import hub

MODELS = brain_config.MODELS_DIR / "faces"
FACES_DIR = brain_config.BASE_DIR / "memory" / "faces"
_YUNET = "face_detection_yunet_2023mar.onnx"
_SFACE = "face_recognition_sface_2021dec.onnx"
_URLS = {
    _YUNET: [
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/" + _YUNET,
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/" + _YUNET,
        "https://huggingface.co/opencv/face_detection_yunet/resolve/main/" + _YUNET,
    ],
    _SFACE: [
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/" + _SFACE,
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/" + _SFACE,
        "https://huggingface.co/opencv/face_recognition_sface/resolve/main/" + _SFACE,
    ],
}
MATCH_THRESHOLD = 0.40        # cosine; OpenCV's reference threshold is 0.363


def ensure_models(log: Callable[[str], None] = print) -> tuple[Path, Path]:
    from core.downloader import fetch
    det = fetch(_URLS[_YUNET], MODELS / _YUNET, 100_000, progress=log)
    rec = fetch(_URLS[_SFACE], MODELS / _SFACE, 10_000_000, progress=log, timeout=180)
    return det, rec


class FaceEngine:
    def __init__(self, log: Callable[[str], None] = print):
        import cv2
        det, rec = ensure_models(log)
        self._cv2 = cv2
        self._det = cv2.FaceDetectorYN.create(str(det), "", (320, 320), 0.85, 0.3, 5000)
        self._rec = cv2.FaceRecognizerSF.create(str(rec), "")
        self._lock = threading.Lock()
        self.people: dict[str, dict] = {}
        self.load_people()

    # ── storage ──────────────────────────────────────────────────────────────
    def load_people(self) -> None:
        self.people.clear()
        FACES_DIR.mkdir(parents=True, exist_ok=True)
        for meta in FACES_DIR.glob("*.json"):
            try:
                info = json.loads(meta.read_text(encoding="utf-8"))
                emb = np.load(meta.with_suffix(".npy"))
                info["emb"] = emb.astype(np.float32)
                self.people[info["name"]] = info
            except Exception as e:
                print(f"[FaceID] could not load {meta.name}: {e}")

    def owner(self) -> str | None:
        for name, info in self.people.items():
            if info.get("owner"):
                return name
        return None

    def forget(self, name: str) -> bool:
        key = self._key(name)
        found = False
        for ext in (".json", ".npy"):
            f = FACES_DIR / f"{key}{ext}"
            if f.exists():
                f.unlink()
                found = True
        self.load_people()
        return found

    @staticmethod
    def _key(name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum() or ch in "-_") or "person"

    # ── vision ───────────────────────────────────────────────────────────────
    def detect(self, frame) -> np.ndarray:
        h, w = frame.shape[:2]
        with self._lock:
            self._det.setInputSize((w, h))
            _, faces = self._det.detect(frame)
        return faces if faces is not None else np.zeros((0, 15), dtype=np.float32)

    def embed(self, frame, face_row) -> np.ndarray:
        with self._lock:
            aligned = self._rec.alignCrop(frame, face_row)
            feat = self._rec.feature(aligned)
        v = np.asarray(feat, dtype=np.float32).reshape(-1)
        return v / (np.linalg.norm(v) + 1e-9)

    def identify(self, frame) -> list[dict]:
        """[{name, score, box}] for every face in the frame ('unknown' if unmatched)."""
        out = []
        for row in self.detect(frame):
            v = self.embed(frame, row)
            best, best_s = "unknown", 0.0
            for name, info in self.people.items():
                s = float(np.max(info["emb"] @ v))
                if s > best_s:
                    best, best_s = name, s
            if best_s < MATCH_THRESHOLD:
                best = "unknown"
            x, y, w, h = [int(c) for c in row[:4]]
            out.append({"name": best, "score": round(best_s, 3), "box": (x, y, w, h),
                        "size": w * h})
        out.sort(key=lambda d: -d["size"])
        return out

    def enroll(self, name: str, owner: bool = False, samples: int = 12, seconds: float = 8.0,
               log: Callable[[str], None] = print) -> str:
        name = name.strip() or "owner"
        embs: list[np.ndarray] = []
        cam = hub()
        cam.acquire()
        try:
            if cam.wait_frame(timeout=6.0) is None:
                return f"No camera image — {cam.error or 'is a webcam connected?'}"
            time.sleep(0.8)
            deadline = time.monotonic() + seconds
            last_ts = 0.0
            while time.monotonic() < deadline and len(embs) < samples:
                frame = cam.wait_frame(timeout=1.0, fresh_after=last_ts)
                last_ts = time.monotonic()
                if frame is None:
                    continue
                faces = self.detect(frame)
                if len(faces) != 1 or faces[0][-1] < 0.9:
                    continue
                embs.append(self.embed(frame, faces[0]))
                time.sleep(0.25)
        finally:
            cam.release()
        if len(embs) < 4:
            return ("I could not see one clear face for long enough. Sit facing the camera in "
                    "good light, alone in view, and try again.")
        key = self._key(name)
        if owner:
            for other in list(self.people.values()):
                if other.get("owner") and other["name"] != name:
                    other_meta = FACES_DIR / f"{self._key(other['name'])}.json"
                    info = {k: v for k, v in other.items() if k != "emb"}
                    info["owner"] = False
                    other_meta.write_text(json.dumps(info), encoding="utf-8")
        existing = self.people.get(name)
        arr = np.stack(embs)
        if existing is not None:
            arr = np.concatenate([existing["emb"], arr])[-40:]
        FACES_DIR.mkdir(parents=True, exist_ok=True)
        np.save(FACES_DIR / f"{key}.npy", arr)
        (FACES_DIR / f"{key}.json").write_text(json.dumps({
            "name": name, "owner": bool(owner or (existing or {}).get("owner")),
            "enrolled": time.strftime("%Y-%m-%d %H:%M"), "samples": int(arr.shape[0])}),
            encoding="utf-8")
        self.load_people()
        return f"Learned {name}'s face from {len(embs)} views" + (" as the owner." if owner else ".")


_engine: FaceEngine | None = None
_engine_lock = threading.Lock()


def engine(log: Callable[[str], None] = print) -> FaceEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = FaceEngine(log)
        return _engine


class Presence:
    """Background watcher. Looks about once a second while enabled."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._log: Callable[[str], None] = print
        self.owner_seen = 0.0
        self.away_since = time.monotonic()
        self.last_greet = 0.0
        self.last_alert = 0.0
        self.locked = False
        self.in_view: list[str] = []

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, log: Callable[[str], None] = print) -> None:
        self._log = log
        if self.running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="face-presence")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        runtime.set_state("owner_present", None)

    def _loop(self) -> None:
        try:
            eng = engine(self._log)
        except Exception as e:
            self._log(f"ERR: Face ID unavailable — {str(e)[:160]}")
            return
        owner = eng.owner()
        if not owner:
            self._log("SYS: Face presence is on, but no owner face is enrolled yet — "
                      "say 'remember my face'.")
        cam = hub()
        cam.acquire()
        self._log("SYS: Face presence watching.")
        was_present = False
        try:
            while not self._stop.wait(1.0):
                frame = cam.latest(max_age=2.0)
                if frame is None:
                    continue
                small = frame
                h, w = frame.shape[:2]
                if w > 960:
                    import cv2
                    small = cv2.resize(frame, (w // 2, h // 2))
                try:
                    seen = eng.identify(small)
                except Exception as e:
                    print(f"[FaceID] {e}")
                    continue
                owner = eng.owner()
                now = time.monotonic()
                names = [s["name"] for s in seen]
                self.in_view = names
                runtime.set_state("people_in_view", names)
                if owner and owner in names:
                    self.owner_seen = now
                present = bool(owner) and (now - self.owner_seen) < 20
                runtime.set_state("owner_present", present if owner else None)
                senses = brain_config.get_senses()
                if present and not was_present:
                    away = now - self.away_since
                    if senses.get("greet_on_arrival", True) and away > 300 and now - self.last_greet > 1800:
                        self.last_greet = now
                        mins = int(away // 60)
                        runtime.inject(f"[PRESENCE] {owner} has just come back to the computer after about "
                                       f"{mins} minutes away. Welcome them back in one short, natural sentence.")
                    self.locked = False
                if not present and was_present:
                    self.away_since = now
                if (not present and owner and senses.get("lock_on_leave") and not self.locked
                        and now - self.owner_seen > 120 and platform.system() == "Windows"):
                    self.locked = True
                    try:
                        import ctypes
                        ctypes.windll.user32.LockWorkStation()
                        self._log("SYS: Owner left — workstation locked.")
                    except Exception:
                        pass
                if ("unknown" in names and not present and senses.get("alert_unknown_faces")
                        and now - self.last_alert > 600):
                    self.last_alert = now
                    self._alert_stranger(frame)
                was_present = present
        finally:
            cam.release()

    def _alert_stranger(self, frame) -> None:
        self._log("SYS: ⚠ An unknown person is at the computer.")
        try:
            import cv2
            from core import telegram_bridge
            if telegram_bridge.configured():
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    telegram_bridge.send_photo(buf.tobytes(), "Unknown person at your computer")
        except Exception as e:
            print(f"[FaceID] alert failed: {e}")


_presence = Presence()


def presence() -> Presence:
    return _presence
