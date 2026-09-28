"""
Object detection — what is in a camera frame, in about 20-50 ms on the CPU.

Model: NanoDet-Plus-m (416 px, COCO's 80 classes: people, vehicles, animals,
phones, cups, laptops, bags…) from the OpenCV model zoo, Apache-2.0, 3.8 MB.
It runs through onnxruntime, which the app already ships for speech detection
and OCR, on two CPU threads — the GPU stays free for the language model.

This is the cheap, always-on half of the assistant's eyesight: it notices that
a person walked in, that a car stopped at the gate, that the user is holding a
phone. The expensive half — a vision language model saying what is actually
happening — runs only when this half says something changed (see
core/perception.py and core/cctv.py).

Decoding follows the model zoo's reference implementation
(opencv_zoo/models/object_detection_nanodet): distribution-focal box regression
with reg_max 7 over strides 8/16/32, then non-maximum suppression.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import numpy as np

from core import brain_config

MODEL_DIR = brain_config.MODELS_DIR / "vision"
MODEL_FILE = "object_detection_nanodet_2022nov.onnx"
_URLS = [
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_nanodet/"
    + MODEL_FILE,
    "https://github.com/opencv/opencv_zoo/raw/main/models/object_detection_nanodet/" + MODEL_FILE,
    "https://huggingface.co/opencv/object_detection_nanodet/resolve/main/" + MODEL_FILE,
]
_SIZE = 416
_REG_MAX = 7
_STRIDES = (8, 16, 32)
_MEAN = np.array([103.53, 116.28, 123.675], dtype=np.float32)
_STD = np.array([57.375, 57.12, 58.395], dtype=np.float32)

CLASSES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
    "teddy bear", "hair drier", "toothbrush",
)

# Groups used by the watchers: what counts as a "vehicle" at the gate, etc.
VEHICLES = {"bicycle", "car", "motorcycle", "bus", "truck", "boat"}
ANIMALS = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}
# Furniture and fixtures: always in a room, never news.
BACKGROUND = {"chair", "couch", "bed", "dining table", "tv", "potted plant", "refrigerator",
              "oven", "microwave", "sink", "toilet", "clock", "vase", "bench", "keyboard",
              "mouse", "laptop", "book", "traffic light", "parking meter", "fire hydrant",
              "stop sign"}


def model_path() -> Path:
    return MODEL_DIR / MODEL_FILE


def ensure_model(log: Callable[[str], None] = print) -> Path:
    from core.downloader import fetch
    return fetch(_URLS, model_path(), 1_000_000, progress=log, timeout=120)


def _anchors() -> list[np.ndarray]:
    out = []
    for st in _STRIDES:
        fs = _SIZE // st
        ys, xs = np.mgrid[0:fs, 0:fs]
        cx = xs.ravel() * st + 0.5 * (st - 1)
        cy = ys.ravel() * st + 0.5 * (st - 1)
        out.append(np.stack([cx, cy], axis=1).astype(np.float32))
    return out


class Detector:
    def __init__(self, path: Path | None = None, threads: int = 2,
                 log: Callable[[str], None] = print):
        import onnxruntime as ort
        path = Path(path) if path else ensure_model(log)
        so = ort.SessionOptions()
        so.log_severity_level = 3                 # the zoo export lists weights as inputs
        so.intra_op_num_threads = max(1, int(threads))
        so.inter_op_num_threads = 1
        self._sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self._input = self._sess.get_inputs()[0].name
        self._anchors = _anchors()
        self._proj = np.arange(_REG_MAX + 1, dtype=np.float32)
        self._lock = threading.Lock()

    @staticmethod
    def _letterbox(img: np.ndarray):
        import cv2
        h, w = img.shape[:2]
        r = min(_SIZE / h, _SIZE / w)
        nh, nw = max(1, int(round(h * r))), max(1, int(round(w * r)))
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        top, left = (_SIZE - nh) // 2, (_SIZE - nw) // 2
        canvas = np.zeros((_SIZE, _SIZE, 3), dtype=np.uint8)
        canvas[top:top + nh, left:left + nw] = resized
        return canvas, r, top, left

    def detect(self, frame_bgr: np.ndarray, min_conf: float = 0.4, nms: float = 0.6,
               classes: set[str] | None = None) -> list[dict]:
        """[{label, conf, box: (x, y, w, h)}] in the frame's own pixels."""
        import cv2
        if frame_bgr is None or frame_bgr.size == 0:
            return []
        if frame_bgr.ndim == 2:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
        canvas, r, top, left = self._letterbox(frame_bgr)
        x = ((canvas.astype(np.float32) - _MEAN) / _STD).transpose(2, 0, 1)[None]
        with self._lock:
            outs = self._sess.run(None, {self._input: x})
        cls_by_n, box_by_n = {}, {}
        for a in outs:
            a = a[0]
            (cls_by_n if a.shape[1] == len(CLASSES) else box_by_n)[a.shape[0]] = a
        boxes, scores = [], []
        for st, anchors in zip(_STRIDES, self._anchors):
            n = anchors.shape[0]
            if n not in cls_by_n or n not in box_by_n:
                continue
            d = box_by_n[n].reshape(-1, 4, _REG_MAX + 1)
            d = np.exp(d - d.max(axis=-1, keepdims=True))
            d /= d.sum(axis=-1, keepdims=True)
            dist = (d * self._proj).sum(axis=-1) * st
            b = np.stack([anchors[:, 0] - dist[:, 0], anchors[:, 1] - dist[:, 1],
                          anchors[:, 0] + dist[:, 2], anchors[:, 1] + dist[:, 3]], axis=1)
            boxes.append(np.clip(b, 0, _SIZE))
            scores.append(cls_by_n[n])
        if not boxes:
            return []
        boxes = np.concatenate(boxes)
        scores = np.concatenate(scores)
        ids = scores.argmax(axis=1)
        conf = scores.max(axis=1)
        keep = conf >= min_conf
        if classes:
            wanted = np.array([CLASSES[i] in classes for i in range(len(CLASSES))])
            keep &= wanted[ids]
        if not np.any(keep):
            return []
        boxes, ids, conf = boxes[keep], ids[keep], conf[keep]
        xywh = [[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])] for b in boxes]
        idx = cv2.dnn.NMSBoxes(xywh, conf.tolist(), min_conf, nms)
        idx = np.array(idx).reshape(-1) if len(idx) else []
        h, w = frame_bgr.shape[:2]
        out = []
        for i in idx:
            x1, y1, x2, y2 = boxes[i]
            x1 = max(0.0, (x1 - left) / r)
            y1 = max(0.0, (y1 - top) / r)
            x2 = min(float(w), (x2 - left) / r)
            y2 = min(float(h), (y2 - top) / r)
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            out.append({"label": CLASSES[int(ids[i])], "conf": round(float(conf[i]), 3),
                        "box": (int(x1), int(y1), int(x2 - x1), int(y2 - y1))})
        out.sort(key=lambda d: -d["conf"])
        return out


_det: Detector | None = None
_det_lock = threading.Lock()
_det_error = ""


def detector(log: Callable[[str], None] = print) -> Detector | None:
    """The shared detector, or None when the model cannot be loaded."""
    global _det, _det_error
    with _det_lock:
        if _det is None and not _det_error:
            try:
                _det = Detector(log=log)
            except Exception as e:
                _det_error = str(e)
                log(f"ERR: Object detection unavailable — {str(e)[:160]}")
        return _det


def summarize(dets: list[dict], skip: set[str] | None = None) -> str:
    """'2 persons, a dog, a car' — for logs, prompts and alerts."""
    counts: dict[str, int] = {}
    for d in dets:
        if skip and d["label"] in skip:
            continue
        counts[d["label"]] = counts.get(d["label"], 0) + 1
    parts = []
    for label, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if n == 1:
            parts.append(("an " if label[0] in "aeiou" else "a ") + label)
        else:
            parts.append(f"{n} {'people' if label == 'person' else label + 's'}")
    return ", ".join(parts)


def draw(frame: np.ndarray, dets: list[dict], names: list[dict] | None = None) -> np.ndarray:
    """A copy of the frame with boxes and labels, for the HUD and alerts."""
    import cv2
    img = frame.copy()
    for d in dets:
        x, y, w, h = d["box"]
        col = (0, 200, 255) if d["label"] == "person" else (0, 255, 120)
        cv2.rectangle(img, (x, y), (x + w, y + h), col, 2)
        cv2.putText(img, f"{d['label']} {d['conf']:.0%}", (x, max(12, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    for f in names or []:
        x, y, w, h = f["box"]
        col = (80, 255, 80) if f["name"] != "unknown" else (60, 60, 255)
        cv2.rectangle(img, (x, y), (x + w, y + h), col, 2)
        cv2.putText(img, f["name"], (x, y + h + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
    return img
