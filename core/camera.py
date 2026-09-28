"""
One webcam, shared.

On Windows a camera opened through DirectShow belongs to whoever opened it
first; a second VideoCapture on the same index simply fails. With face presence
watching in the background, the HUD's live camera view and the vision tool's
snapshot would both stop working. So every part of the app goes through this
hub: the first user opens the camera, everyone reads the latest frame, and the
last one to leave closes it again — the camera light is only on while something
actually needs it.
"""
from __future__ import annotations

import platform
import threading
import time


class CameraHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._users = 0
        self._frame = None
        self._ts = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._new = threading.Condition()
        self.error = ""

    def acquire(self) -> None:
        with self._lock:
            self._users += 1
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._loop, daemon=True, name="camera-hub")
                self._thread.start()

    def release(self) -> None:
        with self._lock:
            self._users = max(0, self._users - 1)
            if self._users == 0:
                self._stop.set()

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def latest(self, max_age: float = 1.0):
        if self._frame is None or time.monotonic() - self._ts > max_age:
            return None
        return self._frame

    def wait_frame(self, timeout: float = 4.0, fresh_after: float | None = None):
        """Block until a frame newer than `fresh_after` (monotonic) arrives."""
        deadline = time.monotonic() + timeout
        want = fresh_after if fresh_after is not None else 0.0
        with self._new:
            while time.monotonic() < deadline:
                if self._frame is not None and self._ts > want:
                    return self._frame
                self._new.wait(timeout=0.1)
        return None

    def snapshot(self, warmup: float = 0.8, timeout: float = 5.0):
        """A single, fresh frame; opens the camera just for it if nobody else has."""
        self.acquire()
        try:
            start = time.monotonic()
            if self._frame is None:
                # Freshly opened cameras deliver dark frames while exposure settles.
                self.wait_frame(timeout=timeout)
                time.sleep(warmup)
            return self.wait_frame(timeout=timeout, fresh_after=start)
        finally:
            self.release()

    def _open(self):
        import cv2
        try:
            from actions.screen_processor import _get_camera_index
            idx = _get_camera_index()
        except Exception:
            idx = 0
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        cap = cv2.VideoCapture(idx, backend)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(0)
        return cap

    def _loop(self) -> None:
        cap = None
        try:
            cap = self._open()
            if not cap.isOpened():
                self.error = "no camera could be opened"
                print("[Camera] no camera could be opened")
                return
            self.error = ""
            fails = 0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    fails += 1
                    if fails > 50:
                        self.error = "the camera stopped delivering frames"
                        break
                    time.sleep(0.05)
                    continue
                fails = 0
                with self._new:
                    self._frame = frame
                    self._ts = time.monotonic()
                    self._new.notify_all()
                time.sleep(0.02)
        except Exception as e:
            self.error = str(e)
            print(f"[Camera] {e}")
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            self._frame = None
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None


_hub = CameraHub()


def hub() -> CameraHub:
    return _hub
