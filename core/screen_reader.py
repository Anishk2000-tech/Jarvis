"""
Seeing the screen the way the automation needs to: as a numbered list of
things that can be clicked or typed into, each with exact coordinates.

Two sources, merged:

  UI Automation   Windows' accessibility tree — every button, field, menu item,
                  tab and link of the foreground window with its name, type and
                  rectangle. Exact, cheap, and needs no vision model at all.
  OCR             Text read from a screenshot (RapidOCR, bundled, offline). Fills
                  in apps whose accessibility tree is empty — games, some
                  Electron apps, remote desktops, images of text.

A model that cannot see still operates the computer from this list ("click
[12]"); a model that can see also gets the screenshot with the same numbers
drawn on it (set-of-marks), which is far more reliable for small vision models
than asking them for raw pixel coordinates.
"""
from __future__ import annotations

import ctypes
import io
import platform
import threading
import time
from dataclasses import dataclass

import numpy as np

_IS_WIN = platform.system() == "Windows"

_CT = {50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox", 50004: "Edit",
       50005: "Link", 50006: "Image", 50007: "ListItem", 50008: "List", 50009: "Menu",
       50010: "MenuBar", 50011: "MenuItem", 50012: "ProgressBar", 50013: "RadioButton",
       50014: "ScrollBar", 50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
       50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip", 50023: "Tree",
       50024: "TreeItem", 50025: "Custom", 50026: "Group", 50027: "Thumb", 50028: "DataGrid",
       50029: "DataItem", 50030: "Document", 50031: "SplitButton", 50032: "Window",
       50033: "Pane", 50034: "Header", 50035: "HeaderItem", 50036: "Table", 50037: "TitleBar",
       50038: "Separator", 50039: "SemanticZoom", 50040: "AppBar"}
_INTERACTIVE = {"Button", "CheckBox", "ComboBox", "Edit", "Link", "ListItem", "MenuItem",
                "RadioButton", "Slider", "Spinner", "TabItem", "TreeItem", "DataItem",
                "SplitButton", "HeaderItem", "Document", "Calendar"}
_READABLE = {"Text", "Image", "Custom", "Group"}


@dataclass
class Element:
    idx: int
    kind: str
    name: str
    x: int
    y: int
    w: int
    h: int
    value: str = ""
    source: str = "uia"

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def line(self) -> str:
        cx, cy = self.center
        val = f' value="{self.value[:60]}"' if self.value else ""
        name = self.name.replace("\n", " ")[:80]
        return f'[{self.idx}] {self.kind} "{name}"{val} @({cx},{cy})'


# ── screenshots ──────────────────────────────────────────────────────────────

def screenshot(monitor: int = 1):
    """(PIL image, left, top) of a monitor in physical pixels."""
    import mss
    from PIL import Image
    with mss.mss() as sct:
        mons = sct.monitors
        mon = mons[monitor] if len(mons) > monitor else mons[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        return img, mon["left"], mon["top"]


def jpeg_bytes(img, max_w: int = 1280, quality: int = 80) -> bytes:
    im = img.copy()
    if im.width > max_w:
        im.thumbnail((max_w, int(im.height * max_w / im.width)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ── OCR ──────────────────────────────────────────────────────────────────────

_ocr = None
_ocr_lock = threading.Lock()


def _ocr_engine():
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        return _ocr


def ocr(img) -> list[tuple[str, int, int, int, int, float]]:
    """[(text, x, y, w, h, score)] in the image's pixel space."""
    arr = np.asarray(img.convert("RGB"))
    result, _ = _ocr_engine()(arr)
    out = []
    for box, text, score in result or []:
        try:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            out.append((str(text), x0, y0, x1 - x0, y1 - y0, float(score)))
        except Exception:
            continue
    return out


def ocr_image_bytes(data: bytes, max_lines: int = 120) -> str:
    """Plain text of an image, top-to-bottom — the no-vision-model fallback."""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    rows = sorted(ocr(img), key=lambda r: (round(r[2] / 12), r[1]))
    return "\n".join(r[0] for r in rows[:max_lines] if r[5] > 0.5)


# ── UI Automation (Windows) ──────────────────────────────────────────────────

def foreground_window() -> tuple[int, str]:
    if not _IS_WIN:
        return 0, ""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return int(hwnd), buf.value


def top_windows(limit: int = 25) -> list[tuple[int, str]]:
    if not _IS_WIN:
        return []
    import win32gui
    out: list[tuple[int, str]] = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and title not in ("Program Manager", "Settings") and not win32gui.GetParent(hwnd):
                out.append((hwnd, title))
    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return out[:limit]


def uia_elements(hwnd: int | None = None, max_items: int = 150, budget_s: float = 2.5) -> list[Element]:
    if not _IS_WIN:
        return []
    try:
        from pywinauto.uia_defines import IUIA
        uia = IUIA()
        iuia = uia.iuia
        mod = uia.UIA_dll
        if not hwnd:
            hwnd, _ = foreground_window()
        root = iuia.ElementFromHandle(hwnd)
        cr = iuia.CreateCacheRequest()
        for pid in (30005, 30003, 30001, 30022, 30010, 30045):
            cr.AddProperty(pid)       # Name, ControlType, Rect, Offscreen, Enabled, Value
        cond = iuia.ControlViewCondition
        t0 = time.monotonic()
        arr = root.FindAllBuildCache(getattr(mod, "TreeScope_Descendants", 4), cond, cr)
        out: list[Element] = []
        n = arr.Length if arr else 0
        for i in range(n):
            if time.monotonic() - t0 > budget_s or len(out) >= max_items * 2:
                break
            try:
                el = arr.GetElement(i)
                if el.CachedIsOffscreen or not el.CachedIsEnabled:
                    continue
                kind = _CT.get(int(el.CachedControlType), "Other")
                name = str(el.CachedName or "").strip()
                r = el.CachedBoundingRectangle
                w, h = int(r.right - r.left), int(r.bottom - r.top)
                if w <= 2 or h <= 2:
                    continue
                if kind not in _INTERACTIVE and not (kind in _READABLE and name):
                    continue
                value = ""
                try:
                    value = str(el.GetCachedPropertyValue(30045) or "")
                except Exception:
                    pass
                out.append(Element(0, kind, name, int(r.left), int(r.top), w, h, value[:120]))
            except Exception:
                continue
        # Interactive first, then readable text; drop exact duplicates.
        seen, ranked = set(), []
        for e in sorted(out, key=lambda e: (e.kind not in _INTERACTIVE, e.y, e.x)):
            key = (e.kind, e.name, e.x // 4, e.y // 4)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(e)
        return ranked[:max_items]
    except Exception as e:
        print(f"[ScreenReader] UIA unavailable: {e}")
        return []


# ── merged view ──────────────────────────────────────────────────────────────

@dataclass
class Observation:
    title: str
    windows: list[str]
    elements: list[Element]
    image: object = None          # PIL image of the screen
    offset: tuple[int, int] = (0, 0)

    def text(self, max_chars: int = 7000) -> str:
        lines = [f'Foreground window: "{self.title}"']
        if self.windows:
            lines.append("Open windows: " + " | ".join(w[:50] for w in self.windows[:15]))
        if self.image is not None:
            lines.append(f"Screen size: {self.image.width}x{self.image.height}")
        lines.append("Elements (use their [number]):")
        body = "\n".join(e.line() for e in self.elements) or "(none found)"
        out = "\n".join(lines) + "\n" + body
        return out[:max_chars]

    def find(self, idx: int) -> Element | None:
        for e in self.elements:
            if e.idx == idx:
                return e
        return None

    def annotated(self, max_w: int = 1280):
        """The screenshot with each element's number drawn on it."""
        from PIL import ImageDraw
        if self.image is None:
            return None
        im = self.image.copy()
        d = ImageDraw.Draw(im)
        ox, oy = self.offset
        for e in self.elements:
            x, y = e.x - ox, e.y - oy
            col = (255, 60, 60) if e.source == "uia" else (60, 160, 255)
            d.rectangle([x, y, x + e.w, y + e.h], outline=col, width=2)
            label = str(e.idx)
            d.rectangle([x, y, x + 8 * len(label) + 4, y + 14], fill=col)
            d.text((x + 2, y + 1), label, fill=(255, 255, 255))
        return im


def observe(with_image: bool = True, with_ocr: bool = True, max_items: int = 140) -> Observation:
    hwnd, title = foreground_window()
    windows = [t for _, t in top_windows()]
    elements = uia_elements(hwnd, max_items=max_items) if _IS_WIN else []
    img, left, top = (None, 0, 0)
    if with_image or with_ocr:
        try:
            img, left, top = screenshot()
        except Exception as e:
            print(f"[ScreenReader] screenshot failed: {e}")
    if with_ocr and img is not None and len(elements) < max_items:
        try:
            for text, x, y, w, h, score in ocr(img):
                if score < 0.6 or len(text.strip()) < 2:
                    continue
                ax, ay = x + left, y + top
                cx, cy = ax + w // 2, ay + h // 2
                # Skip text already covered by an accessibility element.
                if any(e.x <= cx <= e.x + e.w and e.y <= cy <= e.y + e.h and e.name
                       and text.strip().lower()[:12] in e.name.lower() for e in elements):
                    continue
                elements.append(Element(0, "Text", text.strip(), ax, ay, w, h, source="ocr"))
                if len(elements) >= max_items:
                    break
        except Exception as e:
            print(f"[ScreenReader] OCR failed: {e}")
    for i, e in enumerate(elements, 1):
        e.idx = i
    return Observation(title, windows, elements, img if with_image else None, (left, top))


def find_on_screen(description: str) -> tuple[int, int] | None:
    """Best element matching a description, by name — no model call."""
    import difflib
    def norm(t: str) -> str:
        return "".join(ch for ch in (t or "").lower() if ch.isalnum())

    want = norm(description)
    if not want:
        return None
    obs = observe(with_image=False, with_ocr=True)
    best, score = None, 0.0
    for e in obs.elements:
        name = norm(e.name)
        if not name:
            continue
        s = 1.0 if want == name else (0.9 if want in name or name in want else
                                      difflib.SequenceMatcher(None, want, name).ratio())
        if e.kind in _INTERACTIVE:
            s += 0.05
        if s > score:
            best, score = e, s
    if best is not None and score >= 0.72:
        return best.center
    return None
