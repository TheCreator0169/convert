"""The window: drop files, pick a format, convert. Conversion runs on a worker thread."""
import ctypes
import getpass
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLayout, QListView, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
                               QSpinBox, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from . import settings, theme, update_check
from .converter import convert_file, describe, scrub
from .formats import DEFAULTS, file_type, option_key, outputs_for, output_fmt
from .process import Cancelled, find_tool
from .version import CONVERT_VERSION

log = logging.getLogger("convert")
PIPE = f"Convert-GUI-{getpass.getuser()}"
MAX_MESSAGE = 1 << 20  # bytes accepted on the pipe
CHOICES = {"video_quality": ["high", "medium", "low"], "page": ["A4", "Letter"], "height": [0, 2160, 1440, 1080, 720, 480],
           "channels": [0, 1, 2], "bit_depth": [16, 24], "dpi": [72, 150, 300],
           "sample_rate": [0, 22050, 44100, 48000], "audio_track": [1, 2, 3, 4]}
RANGE = {"bitrate": (32, 512), "fps": (0, 120), "width": (64, 3840), "quality": (1, 100), "max_size": (0, 16000)}
LABEL = {"bitrate": "Bitrate (kbps)", "sample_rate": "Sample rate (Hz)", "channels": "Channels", "bit_depth": "Bit depth",
         "quality": "Quality (1-100)", "video_quality": "Quality", "height": "Max height", "fps": "Frame rate", "keep_audio": "Keep audio",
         "hw": "Hardware encoding", "width": "Width (px)", "max_size": "Max size (px)", "page": "Page size",
         "dpi": "Resolution (dpi)", "audio_track": "Audio track", "subtitles": "Keep subtitles"}
ZERO = {"sample_rate": "Keep", "channels": "Keep", "height": "Keep", "fps": "Keep", "max_size": "Keep",
        "bitrate": "", "width": ""}
SUPPORTED = ("audio", "video", "image", "doc", "pdf")


class MessageLabel(QLabel):
    """Takes no room while it has no text, so there is no gap under the progress bar."""
    def __init__(self):
        super().__init__("")
        self.hide()

    def setText(self, text):
        super().setText(text)
        self.setVisible(bool(text))


class UpdateNotice(QLabel):
    """A plain line of text above the drop box: blue, underlined on hover. Not a button; a click opens the release page."""
    def __init__(self):
        super().__init__("A new version is available")
        self.setObjectName("update")
        self.setAlignment(Qt.AlignRight)  # on the right, above the drop box
        self.setCursor(Qt.PointingHandCursor)
        self.url = ""
        self.hide()

    def show_for(self, url):
        if update_check.safe_page(url):  # only a page of this project's releases
            self.url = url
            self.show()

    def _underline(self, on):
        f = self.font()
        f.setUnderline(on)
        self.setFont(f)

    def enterEvent(self, e):
        self._underline(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._underline(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and update_check.safe_page(self.url):
            webbrowser.open(self.url)


class UpdateCheck(QObject):
    """Runs the check on a daemon thread, so closing the window never waits for the network."""
    found = Signal(str)

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        url = update_check.newer_release_url(CONVERT_VERSION)
        if url:
            self.found.emit(url)  # delivered on the GUI thread


def _asset(name):
    """Path (forward slashes, for a stylesheet url) of a bundled image; empty when it is missing."""
    p = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets" / name
    return p.as_posix() if p.is_file() else ""


TILE = QSize(88, 64)   # one file: type badge on top, name below
GRID = QSize(94, 70)   # tile plus 3 px around it
PER_ROW, MAX_ROWS = 4, 3


class TileDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return TILE

    def paint(self, p, option, index):
        pal = theme.PALETTE
        r = option.rect.adjusted(3, 3, -3, -3)
        hot = bool(option.state & QStyle.State_MouseOver)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(pal["tile"]))
        p.setPen(QPen(QColor(pal["accent"] if hot else pal["tile"]), 1))
        p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        font = QFont(option.font)
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        kind = str(index.data(Qt.UserRole) or "")
        badge = QRect(r.left() + 8, r.top() + 8, QFontMetrics(font).horizontalAdvance(kind) + 12, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["accent"]))
        p.drawRoundedRect(badge, 4, 4)
        p.setPen(QColor(pal["accent_text"]))
        p.drawText(badge, Qt.AlignCenter, kind)
        font.setBold(False)
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(QColor(pal["text"]))
        name = QFontMetrics(font).elidedText(index.data(Qt.DisplayRole), Qt.ElideMiddle, r.width() - 16)
        p.drawText(QRect(r.left() + 8, r.top() + 32, r.width() - 16, 22), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.restore()


class DropBox(QListWidget):
    """The file list as tiles that wrap like text. While it is empty, a hint sits in the middle of it."""
    def __init__(self, hint_text):
        super().__init__()
        self.setObjectName("drop")
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setGridSize(GRID)
        self.setSpacing(0)
        self.setItemDelegate(TileDelegate(self))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setFixedWidth(418)
        self.hint = QLabel(hint_text, self)
        self.hint.setObjectName("hint")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setAttribute(Qt.WA_TransparentForMouseEvents)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.hint.setGeometry(16, 8, self.width() - 32, self.height() - 16)


def _choice_text(key, c):
    return ZERO.get(key, "Keep") if c == 0 else {2: "Stereo", 1: "Mono"}.get(c, str(c)) if key == "channels" else str(c)


class Worker(QThread):
    progress = Signal(int, str)
    done = Signal(list, list, list)

    def __init__(self, files, fmt_id, options, trash):
        super().__init__()
        self.files, self.fmt_id, self.options, self.trash = files, fmt_id, options, trash
        self.cancel = threading.Event()
        self.cancelled = False  # True only when some file was skipped or interrupted

    def run(self):
        outs, errs, notes = [], [], []
        for i, f in enumerate(self.files):
            if self.cancel.is_set():
                self.cancelled = True
                break
            self.progress.emit(i, Path(f).name)
            try:
                outs += convert_file(f, self.fmt_id, self.options, self.trash, self.cancel, notes)
            except Cancelled:
                self.cancelled = True
                break
            except Exception as e:  # one bad file must not stop the batch
                log.error("failed %s: %s", Path(f).name, scrub(describe(e), f))
                errs.append((Path(f).name, describe(e)))
        self.done.emit([str(o) for o in outs], errs, notes)


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Convert")  # the version is shown once, at the bottom of the window
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # frozen: bundled data folder
        self.setWindowIcon(QIcon(str(root / "assets" / "logo.png")))
        self.setAcceptDrops(True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)  # the height follows the content; the user never resizes
        self.files, self.worker, self.outs, self.pending = [], None, [], []
        self.save_error = ""
        self.st = settings.load()
        self.opt_widgets = {}

        self.list = DropBox("Drop files here, or right-click files in Explorer and choose Convert.")
        self.hint = self.list.hint
        self.fmt = QComboBox()
        self.fmt.setObjectName("fmt")
        self.fmt.setPlaceholderText("Add files first")
        self.fmt.currentIndexChanged.connect(self._build_options)
        self.adv = QGroupBox("Advanced")
        self.adv.setCheckable(True)
        self.adv.setChecked(False)
        self.form = QFormLayout()
        self.form.setVerticalSpacing(10)
        self.form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.adv.setLayout(self.form)
        # Unchecked: the option names stay visible as a preview, only the fields are hidden. Checked: fields shown.
        self.adv.toggled.connect(lambda on: [w.setVisible(on) for w in self.opt_widgets.values()])
        self.trash = QCheckBox("Move originals to the Recycle Bin after a successful conversion")
        self.trash.setChecked(self.st["trash_originals"])
        self.msg = MessageLabel()
        self.msg.setWordWrap(True)  # one line per failed file, wrapped, and the text can be selected and copied
        self.msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
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
        self.logs_btn = QPushButton("Open log folder")
        self.logs_btn.clicked.connect(lambda: os.startfile(str(settings.log_dir())))
        self.logs_btn.hide()
        self.clear = QPushButton("Clear")
        self.clear.clicked.connect(self._clear)

        for b in (self.clear, self.go):
            b.setFixedSize(80, 31)  # both bottom buttons as big as Convert; the text stays centred and keeps its size
        self.version = QLabel(f"v{CONVERT_VERSION}")
        self.version.setObjectName("version")
        self.version.setAlignment(Qt.AlignCenter)
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        for b in (self.logs_btn, self.open_btn, self.stop, self.go):
            right.addWidget(b)
            b.installEventFilter(self)
        row = QGridLayout()  # Clear | version, centred in the window | the other buttons; the side columns are equal
        row.setContentsMargins(0, 2, 0, 0)  # 6 px layout spacing + 2 = 8 px under the progress bar
        row.addWidget(self.clear, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(self.version, 0, 1, Qt.AlignCenter)
        row.addLayout(right, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(2, 1)
        row.setColumnMinimumWidth(0, 80)
        row.setColumnMinimumWidth(2, 80)
        self.update_notice = UpdateNotice()
        self.updater = None
        lay = QVBoxLayout(self)
        lay.addWidget(self.update_notice)
        lay.addWidget(self.list)
        lay.addWidget(QLabel("Convert to"))
        lay.addWidget(self.fmt)
        lay.addWidget(self.adv)
        lay.addWidget(self.trash)
        lay.addWidget(self.bar)
        lay.addWidget(self.msg)
        lay.addLayout(row)
        lay.setContentsMargins(11, 11, 11, 11)
        lay.setSizeConstraint(QLayout.SetFixedSize)  # 440 px wide (the box is 418 px), as high as its content, always
        self._refresh()

    def start_update_check(self):
        """At most one attempt a day, while the app is in use. Called by run(), never by tests or by --cli."""
        if not self.st["update_check"] or not update_check.due(self.st["last_update_check"]):
            return False
        self.st["last_update_check"] = time.time()  # recorded first: a failed or crashed attempt still counts as today's
        try:
            settings.save(self.st)
        except OSError:
            return False  # cannot record the attempt: better no check than one at every launch
        self.updater = UpdateCheck()
        self.updater.found.connect(self.update_notice.show_for)
        self.updater.start()
        return True

    def eventFilter(self, obj, event):
        # The version is hidden while Cancel / Open folder / Open log folder are shown: they would not fit beside it.
        if event.type() in (QEvent.ShowToParent, QEvent.HideToParent):
            extra = (self.logs_btn, self.open_btn, self.stop)
            self.version.setVisible(not any(not b.isHidden() for b in extra))
        return False

    # --- files -------------------------------------------------------------------------------------------------
    def add_files(self, paths):
        if self.worker:  # a batch is running: add these when it ends
            self.pending += [str(p) for p in paths]
            self.msg.setText("New files will be added when the current batch ends.")
            return
        before = len(self.files)
        for p in paths:
            p = str(Path(p))
            if Path(p).is_file() and file_type(p) in SUPPORTED and p not in self.files:
                self.files.append(p)
        if len(self.files) > before:
            self._reset_bar()  # a new batch: the bar of the last one is stale
        self._refresh()

    def _reset_bar(self):
        self.bar.setRange(0, 1)
        self.bar.setValue(0)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_files(u.toLocalFile() for u in e.mimeData().urls())

    def _clear(self):
        self.files, self.outs = [], []
        self._reset_bar()  # Clear after a finished batch: the bar goes back to empty, not full blue
        self._refresh()

    def _missing_ffmpeg(self):
        return any(file_type(f) in ("audio", "video") for f in self.files) and not find_tool("ffmpeg")

    def _refresh(self):
        self.list.clear()
        for f in self.files:
            item = QListWidgetItem(Path(f).name)
            item.setData(Qt.UserRole, (Path(f).suffix[1:5] or "FILE").upper())
            item.setToolTip(f)
            self.list.addItem(item)
        self.hint.setVisible(not self.files)
        rows = -(-len(self.files) // PER_ROW)  # tiles per row: 4; the box grows one row at a time up to 3 rows, then scrolls
        self.list.setFixedHeight(max(110, min(rows, MAX_ROWS) * GRID.height() + 18))
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
        if self.fmt.count():
            self.fmt.setCurrentIndex(0)  # with a placeholder text Qt no longer selects the first item by itself
        self.fmt.blockSignals(False)
        self.fmt.setProperty("empty", not self.fmt.count())  # grey placeholder while there is nothing to pick
        self.fmt.style().unpolish(self.fmt)
        self.fmt.style().polish(self.fmt)
        self.go.setEnabled(bool(self.fmt.count()) and not self.worker)
        self.clear.setEnabled(not self.worker)
        self.open_btn.hide()
        self.logs_btn.hide()
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
                lo, hi = RANGE[key]
                lo = 1 if group == "gif" and key == "fps" else lo
                w.setRange(lo, hi)
                w.setValue(max(lo, min(hi, val)))  # a hand-edited huge number must not overflow the spin box
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
        try:
            settings.save(self.st)
        except OSError as e:  # the conversion still runs; the status line shows it after the first file
            log.warning("settings not saved: %s", e)
            self.save_error = f"Settings could not be saved ({e})."
        self.worker = Worker(list(self.files), self.fmt.currentData(), self.st["options"], self.trash.isChecked())
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._done)
        self.go.setEnabled(False)
        self.stop.show()
        self.bar.setRange(0, len(self.files) if len(self.files) > 1 else 0)
        self.worker.start()

    def _say(self, text, kind):
        """Set the status line and re-polish it so the colour of `kind` (muted, ok, error) applies."""
        self.msg.setObjectName(kind)
        self.msg.setText(text)
        self.msg.style().unpolish(self.msg)
        self.msg.style().polish(self.msg)

    def _progress(self, i, name):
        self.bar.setValue(i)
        self._say(f"Converting {name}  ({i + 1}/{len(self.files)})", "muted")

    def _cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.stop.setEnabled(False)
            self._say("Cancelling: the current file is stopped at its next page or frame...", "muted")

    def _done(self, outs, errs, notes=()):
        w, self.worker = self.worker, None
        w.wait()
        self.outs = outs
        self.bar.setRange(0, 1)
        self.bar.setValue(0 if w.cancelled else 1)
        self.stop.hide()
        self.stop.setEnabled(True)
        if w.trash:
            self.files = [f for f in self.files if Path(f).exists()]
        if errs:
            text = f"{len(outs)} file(s) written, {len(errs)} failed:\n" + "\n".join(f"- {n}: {m}" for n, m in errs)
        elif w.cancelled:
            text = "Cancelled."
        else:
            text = f"Done: {len(outs)} file(s) written next to the originals."
        notes = list(notes) + ([self.save_error] if self.save_error else [])
        self.save_error = ""
        if notes:
            text += "\n" + "\n".join(notes)
        kind = "error" if errs or notes else "ok"
        pending, self.pending = self.pending, []
        self._refresh()
        before = len(self.files)
        self.add_files(pending)
        added = len(self.files) - before
        self._say(text + (f"\n{added} new file(s) added." if added else ""), kind)
        self.open_btn.setVisible(bool(outs))
        self.logs_btn.setVisible(bool(errs))

    def _open_folder(self):
        if self.outs:
            os.startfile(str(Path(self.outs[0]).parent))

    def closeEvent(self, e):
        if self.worker:
            self.worker.cancel.set()
            self.worker.wait(30000)  # let the job stop before Qt destroys the thread
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
    app.setStyleSheet(theme.stylesheet(chevron=_asset("chevron.png"), chevron_up=_asset("chevron-up.png")))
    QLocalServer.removeServer(PIPE)  # stale pipe name after a crash
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)  # only this Windows user may connect
    if not server.listen(PIPE):  # before the window exists, so the others can connect while it builds
        log.warning("single-instance pipe not available: %s", server.errorString())
    win = Window()

    def on_connection():
        c = server.nextPendingConnection()
        buf = bytearray()

        def read():
            buf.extend(c.readAll().data())
            if len(buf) > MAX_MESSAGE:  # a list of file names is never this big: drop the peer
                c.abort()

        c.readyRead.connect(read)

        def finish():
            buf.extend(c.readAll().data())
            if len(buf) > MAX_MESSAGE:
                return
            try:
                paths = json.loads(buf.decode())
            except (ValueError, RecursionError):  # bad JSON, or nested so deep that parsing overflows
                return
            try:
                if isinstance(paths, list):
                    win.add_files(p for p in paths if isinstance(p, str))  # add_files keeps only real, supported files
            except Exception:  # a hostile message must not take the window down
                log.exception("bad pipe message")
            win.showNormal()
            win.raise_()
            win.activateWindow()
        c.disconnected.connect(finish)

    server.newConnection.connect(on_connection)
    while server.hasPendingConnections():  # connections that arrived while the window was being built
        on_connection()
    # Explorer starts one process per selected file: wait a moment so the others can forward theirs first.
    QTimer.singleShot(300, lambda: (win.add_files(files), win.show(), win.start_update_check()))
    return app.exec()
