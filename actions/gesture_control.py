# gesture_control.py
"""
Live hand-gesture control for the Voice + Gesture PC Agent.

Responsibilities:
- Track the user's index finger with MediaPipe.
- Move the Windows cursor using the index fingertip.
- Detect a thumb/index pinch as a click request.
- Route clicks through core.confirm instead of clicking immediately.
- Support an emergency-stop event that invalidates pending gesture actions.
"""

from __future__ import annotations

import math
import platform
import threading
import time
from typing import Optional

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    _MEDIAPIPE = True
except ImportError:
    _MEDIAPIPE = False

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

from core import confirm as confirm_gate


# ---------------------------------------------------------------------------
# Gesture tuning
# ---------------------------------------------------------------------------

# Normalized distance between thumb tip and index fingertip.
# Muskan can tune this against camera/lighting conditions.
_PINCH_DIST_THRESH = 0.055

# Cursor smoothing factor.
# Higher = follows the finger more closely.
# Lower = smoother but slower.
_SMOOTHING = 0.35

# Webcam is normally viewed like a mirror, so reverse X movement.
_MIRROR_X = True

# Minimum time between pinch-click requests.
_CLICK_COOLDOWN_S = 0.75

# Webcam processing rate.
_TARGET_FPS = 30.0

# MediaPipe Hand Landmarker model.
_MODEL_PATH = "models/hand_landmarker.task"


# MediaPipe hand landmark indexes.
_THUMB_TIP = 4
_INDEX_TIP = 8


def _require_dependencies() -> None:
    """Raise a clear error if gesture dependencies are unavailable."""
    missing = []

    if not _CV2:
        missing.append("opencv-python")

    if not _MEDIAPIPE:
        missing.append("mediapipe")

    if not _PYAUTOGUI:
        missing.append("pyautogui")

    if missing:
        raise RuntimeError(
            "Gesture control dependencies missing: "
            + ", ".join(missing)
        )


def _distance(a, b) -> float:
    """Return Euclidean distance between two MediaPipe landmarks."""
    return math.hypot(a.x - b.x, a.y - b.y)
class GestureController:
    """
    Runs live hand tracking in a background thread.

    Emergency-stop behavior:
    - stop() terminates the webcam thread.
    - emergency_stop() also invalidates any pending gesture action.
    - generation changes ensure an old confirmation callback cannot
      perform a click after an emergency stop.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self._lock = threading.Lock()
        self._generation = 0

        self._running = False
        self._last_click_time = 0.0

        # True while the thumb and index finger are held together.
        # This gives us edge-triggered clicking instead of repeated clicks.
        self._pinching = False

        self._camera = None

        # Smoothed cursor coordinates.
        self._cursor_x: Optional[float] = None
        self._cursor_y: Optional[float] = None

    @property
    def running(self) -> bool:
        """Return whether the gesture worker is currently running."""
        with self._lock:
            return self._running

    def start(self) -> None:
        """Start the gesture worker if it is not already running."""
        _require_dependencies()

        with self._lock:
            if self._running:
                return

            self._stop.clear()
            self._generation += 1
            generation = self._generation
            self._running = True

        self._thread = threading.Thread(
            target=self._run,
            args=(generation,),
            daemon=True,
            name="gesture-control",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the gesture worker and release its resources."""
        self._stop.set()

        camera = self._camera
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)

        with self._lock:
            self._generation += 1
            self._running = False

        self._thread = None
        self._camera = None
        self._cursor_x = None
        self._cursor_y = None

    def emergency_stop(self) -> None:
        """
        Immediately invalidate gesture control.

        This is deliberately stronger than an ordinary stop because
        it invalidates callbacks belonging to the previous generation.
        """
        with self._lock:
            self._generation += 1

        self._stop.set()

        camera = self._camera
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)

        with self._lock:
            self._running = False

        self._thread = None
        self._camera = None
        self._cursor_x = None
        self._cursor_y = None

    def _is_generation_valid(self, generation: int) -> bool:
        """Return False when this worker has been invalidated."""
        with self._lock:
            return (
                self._running
                and self._generation == generation
                and not self._stop.is_set()
            )

    def _screen_position(self, index_tip) -> tuple[int, int]:
        """Convert MediaPipe normalized coordinates to screen coordinates."""
        screen_width, screen_height = pyautogui.size()

        normalized_x = float(index_tip.x)
        normalized_y = float(index_tip.y)

        if _MIRROR_X:
            normalized_x = 1.0 - normalized_x

        target_x = max(
            0.0,
            min(float(screen_width - 1), normalized_x * screen_width),
        )
        target_y = max(
            0.0,
            min(float(screen_height - 1), normalized_y * screen_height),
        )

        return int(target_x), int(target_y)

    def _move_cursor(self, index_tip) -> tuple[int, int]:
        """Move the cursor toward the index fingertip using smoothing."""
        target_x, target_y = self._screen_position(index_tip)

        if self._cursor_x is None or self._cursor_y is None:
            self._cursor_x = float(target_x)
            self._cursor_y = float(target_y)
        else:
            self._cursor_x += (
                target_x - self._cursor_x
            ) * _SMOOTHING

            self._cursor_y += (
                target_y - self._cursor_y
            ) * _SMOOTHING

        x = int(self._cursor_x)
        y = int(self._cursor_y)

        pyautogui.moveTo(x, y, duration=0)
        return x, y

    def _request_click(
        self,
        x: int,
        y: int,
        generation: int,
    ) -> None:
        """Put a gesture click behind the human confirmation gate."""

        if not self._is_generation_valid(generation):
            return

        if confirm_gate.pending_title():
            return

        title = "Confirm gesture click"
        detail = (
            f"Gesture control detected a pinch click at "
            f"screen position ({x}, {y})."
        )

        def perform_click() -> str:
            # Emergency stop may have happened while the confirmation
            # banner was waiting for the user.
            if not self._is_generation_valid(generation):
                return "Gesture click cancelled because gesture control was stopped."

            pyautogui.click(x=x, y=y)
            return f"Gesture click executed at ({x}, {y})."

        result = confirm_gate.request(
            key="gesture_click",
            title=title,
            detail=detail,
            run=perform_click,
        )

        print(f"\n[GESTURE] {result}")

    def _handle_pinch(
        self,
        index_tip,
        thumb_tip,
        generation: int,
    ) -> None:
        """Detect a pinch and turn it into one confirmation request."""

        distance = _distance(index_tip, thumb_tip)
        pinching = distance < _PINCH_DIST_THRESH

        if not pinching:
            self._pinching = False
            return

        # Already holding the pinch. Do not generate another click request.
        if self._pinching:
            return

        # Mark the pinch before requesting confirmation.
        self._pinching = True

        now = time.monotonic()

        if now - self._last_click_time < _CLICK_COOLDOWN_S:
            return

        self._last_click_time = now

        if not self._is_generation_valid(generation):
            return

        x, y = self._move_cursor(index_tip)

        self._request_click(
            x=x,
            y=y,
            generation=generation,
        )

    def _run(self, generation: int) -> None:
        """Capture webcam frames and track one hand with MediaPipe."""
        cap = None
        hands = None

        try:
            print("[GESTURE] Gesture control thread started.")

            # Windows camera backend.
            backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY

            cap = cv2.VideoCapture(0, backend)

            if not cap.isOpened():
                raise RuntimeError("Could not open webcam.")

            self._camera = cap

            # Keep webcam processing reasonably light.
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, int(_TARGET_FPS))

            base_options = mp_python.BaseOptions(
                model_asset_path=_MODEL_PATH
            )

            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )

            hands = vision.HandLandmarker.create_from_options(options)

            print("[GESTURE] Webcam opened. Hand tracking active.")

            frame_delay = 1.0 / _TARGET_FPS

            while self._is_generation_valid(generation):
                started = time.monotonic()

                ret, frame = cap.read()

                if not ret or frame is None:
                    print("[GESTURE] Webcam frame read failed.")
                    time.sleep(0.05)
                    continue

                # MediaPipe expects RGB frames.
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                mp_image = mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=rgb,
                )

                timestamp_ms = int(time.monotonic() * 1000)

                result = hands.detect_for_video(
                    mp_image,
                    timestamp_ms,
                )

                if result.hand_landmarks:
                    hand = result.hand_landmarks[0]

                    index_tip = hand[_INDEX_TIP]
                    thumb_tip = hand[_THUMB_TIP]

                    # Move the Windows cursor using the index fingertip.
                    cursor_x, cursor_y = self._move_cursor(index_tip)

                    pinch_distance = _distance(index_tip, thumb_tip)

                    print(
                        f"\r[GESTURE] "
                        f"Cursor=({cursor_x}, {cursor_y}) "
                        f"PinchDist={pinch_distance:.3f}",
                        end="",
                        flush=True,
                    )

                    # Pinch becomes a confirmation-gated click.
                    self._handle_pinch(
                        index_tip=index_tip,
                        thumb_tip=thumb_tip,
                        generation=generation,
                    )
                else:
                    # Re-arm pinch detection after the hand disappears.
                    self._pinching = False

                elapsed = time.monotonic() - started
                remaining = frame_delay - elapsed

                if remaining > 0:
                    time.sleep(remaining)

        except Exception as exc:
            print(f"\n[GESTURE] Worker error: {exc}")

        finally:
            if hands is not None:
                try:
                    hands.close()
                except Exception:
                    pass

            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

            self._camera = None

            with self._lock:
                if self._generation == generation:
                    self._running = False

            print("\n[GESTURE] Gesture control thread stopped.")