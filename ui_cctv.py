"""
The camera wall — every CCTV camera live, the monitoring mode, and a form to
add cameras (by brand + IP, by full URL, or found on the network via ONVIF).

Frames come straight from core.cctv's readers as numpy arrays and are turned
into QImages on the Qt thread twice a second; nothing is re-encoded.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from core import cctv
from ui import C

_FONT = "Courier New"


class _Tile(QFrame):
    clicked = pyqtSignal(str)       # double-click: enlarge / back to the grid
    selected = pyqtSignal(str)      # single click: select (for REMOVE)

    def __init__(self, cam_id: str, name: str):
        super().__init__()
        self.cam_id = cam_id
        self.setStyleSheet(f"QFrame {{ background: #000508; border: 1px solid {C.BORDER}; border-radius: 4px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.title = QLabel(name)
        self.title.setFont(QFont(_FONT, 8, QFont.Weight.Bold))
        self.title.setStyleSheet(f"color: {C.PRI}; border: none;")
        lay.addWidget(self.title)
        self.img = QLabel("connecting…")
        self.img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img.setMinimumSize(160, 90)
        self.img.setStyleSheet(f"color: {C.TEXT_DIM}; border: none;")
        lay.addWidget(self.img, 1)
        self.status = QLabel("")
        self.status.setFont(QFont(_FONT, 7))
        self.status.setStyleSheet(f"color: {C.TEXT_DIM}; border: none;")
        lay.addWidget(self.status)

    def mouseDoubleClickEvent(self, e):
        self.clicked.emit(self.cam_id)

    def mousePressEvent(self, e):
        self.selected.emit(self.cam_id)

    def show_frame(self, frame) -> None:
        import numpy as np
        frame = np.ascontiguousarray(frame)
        h, w = frame.shape[:2]
        img = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_BGR888)
        pw, ph = max(40, self.img.width()), max(30, self.img.height())
        self.img.setPixmap(QPixmap.fromImage(img).scaled(
            pw, ph, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class CameraWallOverlay(QWidget):
    _status_sig = pyqtSignal(str, bool)
    _found_sig = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("CctvWall")
        self.setStyleSheet(f"QWidget#CctvWall {{ background: rgba(0, 6, 10, 250); "
                           f"border: 1px solid {C.BORDER_B}; border-radius: 6px; }}")
        self._tiles: dict[str, _Tile] = {}
        self._solo = ""
        self._status_sig.connect(self._on_status)
        self._found_sig.connect(self._on_found)
        fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; border: 1px solid {C.BORDER}; "
              f"border-radius: 3px; padding: 2px 6px; }}")
        cs = (f"QComboBox {{ background: #000d12; color: {C.TEXT}; border: 1px solid {C.BORDER}; "
              f"border-radius: 3px; padding: 2px 6px; }} QComboBox QAbstractItemView {{ background: #000d12; "
              f"color: {C.TEXT}; selection-background-color: {C.PRI_GHO}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(6)
        top = QHBoxLayout()
        t = QLabel("📹  CCTV")
        t.setFont(QFont(_FONT, 12, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {C.PRI};")
        top.addWidget(t)
        top.addStretch(1)
        top.addWidget(self._lbl("MODE"))
        self.mode = QComboBox()
        self.mode.setStyleSheet(cs)
        for m, label in (("home", "home — announce people"), ("night", "night — strangers to phone"),
                         ("away", "away — alerts to phone"), ("off", "off")):
            self.mode.addItem(label, m)
        self.mode.setCurrentIndex(max(0, self.mode.findData(cctv.load_cfg()["mode"])))
        self.mode.currentIndexChanged.connect(self._set_mode)
        top.addWidget(self.mode)
        close = self._btn("CLOSE")
        close.clicked.connect(self.close_wall)
        top.addWidget(close)
        root.addLayout(top)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        root.addWidget(self.grid_host, 1)
        self.empty = self._lbl("No cameras yet — add one below, or press DISCOVER to find ONVIF cameras.")
        root.addWidget(self.empty)

        # add form
        form = QFrame()
        form.setStyleSheet(f"QFrame {{ border-top: 1px solid {C.BORDER}; }}")
        fl = QVBoxLayout(form)
        fl.setContentsMargins(0, 6, 0, 0)
        fl.setSpacing(4)
        r1 = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name, e.g. Front Door")
        self.brand = QComboBox()
        self.brand.setStyleSheet(cs)
        for key, (_, _, label) in cctv.BRANDS.items():
            self.brand.addItem(label.split(" (")[0], key)
        self.brand.addItem("ONVIF (ask the camera)", "onvif")
        self.ip = QLineEdit()
        self.ip.setPlaceholderText("IP, e.g. 192.168.1.40")
        for w in (self.name, self.ip):
            w.setStyleSheet(fs)
        r1.addWidget(self.name, 2)
        r1.addWidget(self.brand, 2)
        r1.addWidget(self.ip, 2)
        fl.addLayout(r1)
        r2 = QHBoxLayout()
        self.user = QLineEdit()
        self.user.setPlaceholderText("camera user (e.g. admin)")
        self.pw = QLineEdit()
        self.pw.setPlaceholderText("camera password")
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.ch = QLineEdit("1")
        self.ch.setFixedWidth(40)
        self.url = QLineEdit()
        self.url.setPlaceholderText("…or the full stream URL (rtsp://… / http://…)")
        for w in (self.user, self.pw, self.ch, self.url):
            w.setStyleSheet(fs)
        r2.addWidget(self.user, 2)
        r2.addWidget(self.pw, 2)
        r2.addWidget(self._lbl("CH"))
        r2.addWidget(self.ch)
        r2.addWidget(self.url, 4)
        fl.addLayout(r2)
        r3 = QHBoxLayout()
        add = self._btn("＋ ADD && TEST", primary=True)
        add.clicked.connect(self._add)
        disc = self._btn("DISCOVER (ONVIF)")
        disc.clicked.connect(self._discover)
        rem = self._btn("REMOVE SELECTED")
        rem.clicked.connect(self._remove)
        r3.addWidget(add)
        r3.addWidget(disc)
        r3.addWidget(rem)
        r3.addStretch(1)
        fl.addLayout(r3)
        self.found = QComboBox()
        self.found.setStyleSheet(cs)
        self.found.hide()
        self.found.activated.connect(lambda _i: self.ip.setText(self.found.currentData() or ""))
        fl.addWidget(self.found)
        self.msg = self._lbl("Double-click a camera to enlarge it.")
        fl.addWidget(self.msg)
        root.addWidget(form)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._selected = ""

    # helpers
    def _lbl(self, text):
        w = QLabel(text)
        w.setWordWrap(True)
        w.setFont(QFont(_FONT, 8))
        w.setStyleSheet(f"color: {C.TEXT_DIM}; border: none;")
        return w

    def _btn(self, text, primary=False):
        b = QPushButton(text)
        b.setFixedHeight(28)
        b.setFont(QFont(_FONT, 8, QFont.Weight.Bold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        col = C.PRI if primary else C.TEXT_MED
        b.setStyleSheet(f"QPushButton {{ background: transparent; color: {col}; border: 1px solid "
                        f"{C.PRI_DIM if primary else C.BORDER}; border-radius: 3px; padding: 0 10px; }} "
                        f"QPushButton:hover {{ background: {C.PRI_GHO}; color: {C.PRI}; border-color: {C.PRI}; }}")
        return b

    # lifecycle
    def open_wall(self) -> None:
        mgr = cctv.manager()
        mgr.viewers += 1
        mgr.sync()
        self._rebuild()
        self._timer.start(500)
        self.show()
        self.raise_()

    def close_wall(self) -> None:
        self._timer.stop()
        mgr = cctv.manager()
        mgr.viewers = max(0, mgr.viewers - 1)
        mgr.sync()
        self.hide()

    def _rebuild(self) -> None:
        for t in self._tiles.values():
            t.setParent(None)
        self._tiles.clear()
        cams = [c for c in cctv.load_cfg()["cameras"] if not self._solo or c["id"] == self._solo]
        self.empty.setVisible(not cams)
        cols = 1 if len(cams) <= 1 else 2 if len(cams) <= 4 else 3
        for i, c in enumerate(cams):
            tile = _Tile(c["id"], c["name"])
            tile.clicked.connect(self._toggle_solo)
            tile.selected.connect(self._select)
            self.grid.addWidget(tile, i // cols, i % cols)
            self._tiles[c["id"]] = tile

    def _select(self, cid: str) -> None:
        self._selected = cid
        for k, t in self._tiles.items():
            t.setStyleSheet(f"QFrame {{ background: #000508; border: 1px solid "
                            f"{C.PRI if k == cid else C.BORDER}; border-radius: 4px; }}")

    def _toggle_solo(self, cid: str) -> None:
        self._solo = "" if self._solo else cid
        self._rebuild()

    def _refresh(self) -> None:
        mgr = cctv.manager()
        status = {s["id"]: s for s in mgr.status()}
        for cid, tile in self._tiles.items():
            frame = mgr.latest(cid, max_age=15.0)
            if frame is not None:
                tile.show_frame(frame)
            st = status.get(cid, {})
            tile.status.setText(f"{st.get('status', '?')}" + (f" — {st['error'][:60]}" if st.get("error") else ""))

    # actions
    def _set_mode(self, _i) -> None:
        mode = self.mode.currentData()
        cctv.set_mode(mode)
        mgr = cctv.manager()
        mgr.sync()
        if mode != "off" and not mgr.running():
            from core import runtime
            mgr.start(runtime.log)
        self.msg.setText(f"Mode: {mode}.")

    def _add(self) -> None:
        name = self.name.text().strip()
        if not name:
            self._on_status("Give the camera a name.", False)
            return
        params = {"action": "add", "camera": name, "url": self.url.text().strip(),
                  "brand": self.brand.currentData(), "ip": self.ip.text().strip(),
                  "user": self.user.text().strip(), "password": self.pw.text(),
                  "channel": self.ch.text().strip() or "1"}
        self._on_status("Connecting to the camera…", True)

        def work():
            from actions.cctv import cctv_tool
            res = cctv_tool(params)
            self._status_sig.emit(res, "connected" in res.lower())
        threading.Thread(target=work, daemon=True).start()

    def _remove(self) -> None:
        if not self._selected:
            self._on_status("Click a camera first.", False)
            return
        data = cctv.load_cfg()
        cam = next((c for c in data["cameras"] if c["id"] == self._selected), None)
        if cam:
            cctv.remove_camera(cam["name"])
            cctv.manager().sync()
            self._selected = ""
            self._rebuild()
            self._on_status(f"Removed {cam['name']}.", True)

    def _discover(self) -> None:
        self._on_status("Looking for ONVIF cameras on the network…", True)

        def work():
            try:
                found = cctv.discover_onvif(timeout=3.0)
            except Exception as e:
                self._status_sig.emit(f"Discovery failed: {e}", False)
                return
            self._found_sig.emit(found)
        threading.Thread(target=work, daemon=True).start()

    def _on_found(self, found: list) -> None:
        self.found.clear()
        if not found:
            self.found.hide()
            self._on_status("No ONVIF cameras answered. Switch ONVIF on in the camera's app, or add by brand + IP.",
                            False)
            return
        for d in found:
            label = " ".join(x for x in (d.get("name"), d.get("hardware")) if x) or "camera"
            self.found.addItem(f"{d['ip']} — {label}", d["ip"])
        self.found.show()
        self.brand.setCurrentIndex(self.brand.findData("onvif"))
        self.ip.setText(found[0]["ip"])
        self._on_status(f"Found {len(found)}. Pick one, enter its user and password, name it, press ADD.", True)

    def _on_status(self, text: str, ok: bool) -> None:
        self.msg.setText(text)
        self.msg.setStyleSheet(f"color: {C.GREEN if ok else C.RED}; border: none;")
        if "Added" in text or "Saved" in text or "Removed" in text:
            self._rebuild()
