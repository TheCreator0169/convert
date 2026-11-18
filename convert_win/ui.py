"""The window: drop files, pick a format, convert. Conversion runs on a worker thread."""
import ctypes
import getpass
import json
import logging
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from . import settings, theme
from .converter import convert_file
from .formats import DEFAULTS, file_type, option_key, outputs_for, output_fmt
from .process import Cancelled, find_tool
from .version import CONVERT_VERSION

log = logging.getLogger("convert")
PIPE = f"Convert-GUI-{getpass.getuser()}"
CHOICES = {"video_quality": ["high", "medium", "low"], "page": ["A4", "Letter"], "height": [0, 2160, 1440, 1080, 720, 480],
           "channels": [0, 1, 2], "bit_depth": [16, 24], "dpi": [72, 150, 300],
           "sample_rate": [0, 22050, 44100, 48000]}
RANGE = {"bitrate": (32, 512), "fps": (0, 120), "width": (64, 3840), "quality": (1, 100), "max_size": (0, 16000)}
LABEL = {"bitrate": "Bitrate (kbps)", "sample_rate": "Sample rate (Hz)", "channels": "Channels", "bit_depth": "Bit depth",
         "quality": "Quality (1-100)", "video_quality": "Quality", "height": "Max height", "fps": "Frame rate", "keep_audio": "Keep audio",
         "hw": "Hardware encoding", "width": "Width (px)", "max_size": "Max size (px)", "page": "Page size",
         "dpi": "Resolution (dpi)"}
ZERO = {"sample_rate": "Keep", "channels": "Keep", "height": "Keep", "fps": "Keep", "max_size": "Keep",
        "bitrate": "", "width": ""}
SUPPORTED = ("audio", "video", "image", "doc", "pdf")


def _choice_text(key, c):
    return ZERO.get(key, "Keep") if c == 0 else {2: "Stereo", 1: "Mono"}.get(c, str(c)) if key == "channels" else str(c)


class Worker(QThread):
    progress = Signal(int, str)
    done = Signal(list, list)

    def __init__(self, files, fmt_id, options, trash):
        super().__init__()
        self.files, self.fmt_id, self.options, self.trash = files, fmt_id, options, trash
        self.cancel = threading.Event()

    def run(self):
        outs, errs = [], []
        for i, f in enumerate(self.files):
            if self.cancel.is_set():
                break
            self.progress.emit(i, Path(f).name)
            try:
                outs += convert_file(f, self.fmt_id, self.options, self.trash, self.cancel)
            except Cancelled:
                break
            except Exception as e:  # one bad file must not stop the batch
                log.exception("failed %s", f)
                errs.append((Path(f).name, str(e)))
        self.done.emit([str(o) for o in outs], errs)


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Convert {CONVERT_VERSION}")
        self.setAcceptDrops(True)
        self.setMinimumSize(520, 560)
        self.files, self.worker, self.outs = [], None, []
        self.st = settings.load()
        self.opt_widgets = {}

        self.list = QListWidget()
        self.hint = QLabel("Drop files here, or right-click files in Explorer and choose Convert.")
        self.hint.setObjectName("muted")
        self.fmt = QComboBox()
        self.fmt.currentIndexChanged.connect(self._build_options)
        self.adv = QGroupBox("Advanced")
        self.adv.setCheckable(True)
        self.adv.setChecked(False)
        self.form = QFormLayout()
        self.adv.setLayout(self.form)
        self.adv.toggled.connect(lambda on: [self.form.itemAt(i).widget().setVisible(on)
                                             for i in range(self.form.count()) if self.form.itemAt(i).widget()])
        self.trash = QCheckBox("Move originals to the Recycle Bin after a successful conversion")
        self.trash.setChecked(self.st["trash_originals"])
        self.msg = QLabel("")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.go = QPushButton("Convert")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self._start)
        self.stop = QPushButton("Cancel")
        self.stop.clicked.connect(self._cancel)
        self.stop.hide()
        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(self._open_folder)
        self.open_btn.hide()
        self.clear = QPushButton("Clear")
        self.clear.clicked.connect(self._clear)

        row = QHBoxLayout()
        row.addWidget(self.clear)
        row.addStretch()
        row.addWidget(self.open_btn)
        row.addWidget(self.stop)
        row.addWidget(self.go)
        lay = QVBoxLayout(self)
        lay.addWidget(self.hint)
        lay.addWidget(self.list, 1)
        lay.addWidget(QLabel("Convert to"))
        lay.addWidget(self.fmt)
        lay.addWidget(self.adv)
        lay.addWidget(self.trash)
        lay.addWidget(self.bar)
        lay.addWidget(self.msg)
        lay.addLayout(row)
        self._refresh()

    # --- files -------------------------------------------------------------------------------------------------
    def add_files(self, paths):
        if self.worker:
            return
        for p in paths:
            p = str(Path(p))
            if Path(p).is_file() and file_type(p) in SUPPORTED and p not in self.files:
                self.files.append(p)
        self._refresh()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_files(u.toLocalFile() for u in e.mimeData().urls())

    def _clear(self):
        self.files, self.outs = [], []
        self._refresh()

    def _missing_ffmpeg(self):
        return any(file_type(f) in ("audio", "video") for f in self.files) and not find_tool("ffmpeg")

    def _refresh(self):
        self.list.clear()
        self.list.addItems([Path(f).name for f in self.files])
        self.hint.setVisible(not self.files)
        self.fmt.blockSignals(True)
        self.fmt.clear()
        if self._missing_ffmpeg():
            self.msg.setObjectName("error")
            self.msg.setText("ffmpeg not found. Install it (winget install Gyan.FFmpeg) and restart Convert.")
        else:
            self.msg.setObjectName("muted")
            self.msg.setText("")
            for f in outputs_for(self.files):
                self.fmt.addItem(f.label, f.id)
            if self.files and not self.fmt.count():
                self.msg.setText("These files cannot be converted together: pick files of one kind.")
        self.msg.style().unpolish(self.msg)
        self.msg.style().polish(self.msg)
        self.fmt.blockSignals(False)
        self.go.setEnabled(bool(self.fmt.count()) and not self.worker)
        self.clear.setEnabled(not self.worker)
        self.open_btn.hide()
        self._build_options()

    # --- options -----------------------------------------------------------------------------------------------
    def _group(self):
        fid = self.fmt.currentData()
        if not self.files or fid is None:
            return None
        kind, _ = output_fmt(self.files[0], fid)
        return option_key(kind, fid)

    def _build_options(self):
        while self.form.count():
            self.form.takeAt(0).widget().deleteLater()
        self.opt_widgets = {}
        group = self._group()
        self.adv.setVisible(group is not None)
        if group is None:
            return
        for key, val in self.st["options"][group].items():
            if isinstance(val, bool):
                w = QCheckBox()
                w.setChecked(val)
            elif key in CHOICES:
                w = QComboBox()
                for c in CHOICES[key]:
                    w.addItem(_choice_text(key, c), c)
                if val not in CHOICES[key]:
                    w.addItem(str(val), val)
                w.setCurrentIndex(w.findData(val))
            else:
                w = QSpinBox()
                w.setRange(*RANGE[key])
                w.setValue(val)
            self.opt_widgets[key] = w
            self.form.addRow(LABEL[key], w)
            w.setVisible(self.adv.isChecked())

    def _collect(self):
        out = {}
        for k, w in self.opt_widgets.items():
            out[k] = (w.isChecked() if isinstance(w, QCheckBox) else w.currentData() if isinstance(w, QComboBox)
                      else w.value())
        return out

    # --- run ---------------------------------------------------------------------------------------------------
    def _start(self):
        group = self._group()
        self.st["options"][group] = self._collect()
        self.st["trash_originals"] = self.trash.isChecked()
        settings.save(self.st)
        self.worker = Worker(list(self.files), self.fmt.currentData(), self.st["options"], self.trash.isChecked())
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._done)
        self.go.setEnabled(False)
        self.stop.show()
        self.bar.setRange(0, len(self.files) if len(self.files) > 1 else 0)
        self.msg.setObjectName("muted")
        self.worker.start()

    def _progress(self, i, name):
        self.bar.setValue(i)
        self.msg.setText(f"Converting {name}  ({i + 1}/{len(self.files)})")

    def _cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.stop.setEnabled(False)

    def _done(self, outs, errs):
        w, self.worker = self.worker, None
        w.wait()
        self.outs = outs
        self.bar.setRange(0, 1)
        self.bar.setValue(1 if not w.cancel.is_set() else 0)
        self.stop.hide()
        self.stop.setEnabled(True)
        if w.trash:
            self.files = [f for f in self.files if Path(f).exists()]
        self.msg.setObjectName("error" if errs else "ok")
        if errs:
            self.msg.setText(f"{len(outs)} file(s) written, {len(errs)} failed: " + "; ".join(f"{n}: {m}" for n, m in errs))
        elif w.cancel.is_set():
            self.msg.setText("Cancelled.")
        else:
            self.msg.setText(f"Done: {len(outs)} file(s) written next to the originals.")
        text, name = self.msg.text(), self.msg.objectName()
        self._refresh()
        self.msg.setObjectName(name)
        self.msg.setText(text)
        self.msg.style().unpolish(self.msg)
        self.msg.style().polish(self.msg)
        self.open_btn.setVisible(bool(outs))

    def _open_folder(self):
        if self.outs:
            os.startfile(str(Path(self.outs[0]).parent))

    def closeEvent(self, e):
        if self.worker:
            self.worker.cancel.set()
            self.worker.wait(5000)
        super().closeEvent(e)


def _forward(files):
    """True if another Convert window is running and took the files."""
    s = QLocalSocket()
    s.connectToServer(PIPE)
    if not s.waitForConnected(300):
        return False
    s.write(json.dumps(files).encode())
    s.waitForBytesWritten(1000)
    s.disconnectFromServer()
    if s.state() != QLocalSocket.UnconnectedState:
        s.waitForDisconnected(1000)
    return True


_mutex = None


def claim_first(name=PIPE):
    """Atomic: True for exactly one process. Two Explorer launches at the same instant must not both win."""
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, f"Local\\{name}")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def run(files):
    app = QApplication(sys.argv[:1])
    if not claim_first():
        for _ in range(100):  # the first instance may still be starting: wait for its pipe (10 s)
            if _forward(files):
                return 0
            QThread.msleep(100)
        # it never answered (crashed?): carry on as the first instance
    app.setStyleSheet(theme.stylesheet())
    QLocalServer.removeServer(PIPE)  # stale pipe name after a crash
    server = QLocalServer()
    server.listen(PIPE)  # before the window exists, so the others can connect while it builds
    win = Window()

    def on_connection():
        c = server.nextPendingConnection()
        buf = bytearray()
        c.readyRead.connect(lambda: buf.extend(c.readAll().data()))

        def finish():
            buf.extend(c.readAll().data())
            try:
                paths = json.loads(buf.decode())
            except ValueError:
                return
            if isinstance(paths, list):
                win.add_files(p for p in paths if isinstance(p, str))  # add_files keeps only real, supported files
            win.showNormal()
            win.raise_()
            win.activateWindow()
        c.disconnected.connect(finish)

    server.newConnection.connect(on_connection)
    while server.hasPendingConnections():  # connections that arrived while the window was being built
        on_connection()
    # Explorer starts one process per selected file: wait a moment so the others can forward theirs first.
    QTimer.singleShot(300, lambda: (win.add_files(files), win.show()))
    return app.exec()
