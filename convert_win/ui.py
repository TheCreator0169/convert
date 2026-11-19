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

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QActionGroup, QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLayout, QLineEdit, QListView, QListWidget, QListWidgetItem,
                               QMenu, QProgressBar, QPushButton, QSpinBox, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from . import settings, theme, update_check
from .converter import _is_network_path, convert_file, describe, scrub
from .formats import DEFAULTS, file_type, option_key, outputs_for, output_fmt, picker_filter, selection_type
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
        self.setAccessibleName("A new version is available")
        self.setAccessibleDescription("Press Enter to open the release page.")
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

    def _open(self):
        """The one way to open the page, by click or by key: only a page of this project's releases."""
        if update_check.safe_page(self.url):
            webbrowser.open(self.url)

    def showEvent(self, e):
        self.setFocusPolicy(Qt.TabFocus)  # reachable by Tab only while it is shown; a click does not draw the outline
        super().showEvent(e)

    def hideEvent(self, e):
        self.setFocusPolicy(Qt.NoFocus)
        super().hideEvent(e)

    def event(self, e):
        if e.type() == QEvent.ShortcutOverride and e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            e.accept()  # the window's Enter shortcut (Convert) must not fire while this has the focus
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._open()
        else:
            super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.hasFocus():  # a 1 px accent outline; the text does not move
            p = QPainter(self)
            p.setPen(QPen(QColor(theme.PALETTE["accent"]), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
            p.end()

    def enterEvent(self, e):
        self._underline(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._underline(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._open()


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


def _refresh_palette(app, setting):
    """Picks dark or light for `setting` and the Windows scheme, updates PALETTE in place and rebuilds the stylesheet.
    Never sets the Qt colour scheme (the scheme-changed handler relies on that)."""
    scheme = "dark" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
    chosen = theme.resolve(setting, scheme)
    theme.PALETTE.clear()
    theme.PALETTE.update(theme.LIGHT if chosen == "light" else theme.DARK)
    # the arrows: pale grey on dark, dark grey on light (assets\chevron-dark.png and chevron-up-dark.png)
    arrow, arrow_up = ("chevron.png", "chevron-up.png") if chosen == "dark" else ("chevron-dark.png", "chevron-up-dark.png")
    app.setStyleSheet(theme.stylesheet(chevron=_asset(arrow), chevron_up=_asset(arrow_up)))


def _repaint(win):
    """The tiles paint from PALETTE at paint time: repaint them with the new colours."""
    win.update()
    win.list.viewport().update()
    win.update_notice.update()


def apply_theme(app, setting, win=None):
    """Applies "system", "dark" or "light": the Qt colour scheme (system = follow Windows), then the palette and stylesheet."""
    hints = QGuiApplication.styleHints()
    if setting == "system":
        hints.unsetColorScheme()
    else:
        hints.setColorScheme(Qt.ColorScheme.Dark if setting == "dark" else Qt.ColorScheme.Light)
    _refresh_palette(app, setting)
    if win is not None:
        _repaint(win)


def _on_scheme_changed(app, win):
    """Windows switched between dark and light. Only "system" follows it; a fixed choice ignores it. Never sets the scheme."""
    if win.st["theme"] == "system":
        _refresh_palette(app, "system")
        _repaint(win)


TILE = QSize(88, 64)   # one file: type badge on top, name below
GRID = QSize(94, 70)   # tile plus 3 px around it
PER_ROW, MAX_ROWS = 4, 3
STATE_ROLE = Qt.UserRole + 1  # the file's state on its tile: waiting, working, done or failed
STATE_TEXT = {"waiting": ("Waiting", "muted"), "working": ("Working", "accent"), "done": ("Done", "ok"),
              "failed": ("Failed", "error")}  # label and palette token of each state


def _kind(path):
    """The type badge of a tile: the extension in capitals, FILE when there is none."""
    return (Path(path).suffix[1:5] or "FILE").upper()


def _close_rect(cell):
    """The × of a tile: 16x16, 8 px from the tile's top and right edges. `cell` is the item's rect (the tile is it inset by 3 px)."""
    r = cell.adjusted(3, 3, -3, -3)
    return QRect(r.left() + r.width() - 24, r.top() + 8, 16, 16)


class TileDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return TILE

    def paint(self, p, option, index):
        pal = theme.PALETTE
        r = option.rect.adjusted(3, 3, -3, -3)
        hot = bool(option.state & (QStyle.State_MouseOver | QStyle.State_Selected))
        state = index.data(STATE_ROLE) or "waiting"
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(pal["tile"]))
        edge = pal["accent"] if hot else pal["error"] if state == "failed" else pal["tile"]  # hover/selection wins over failed
        p.setPen(QPen(QColor(edge), 1))
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
        close = _close_rect(option.rect)
        x_hot = self.parent().close_hot == index.row()
        if x_hot:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal["hot"]))
            p.drawRoundedRect(close, 4, 4)
        p.setPen(QColor(pal["error"] if x_hot else pal["muted"]))
        font.setPixelSize(12)
        font.setBold(False)
        p.setFont(font)
        p.drawText(close, Qt.AlignCenter, "×")
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(QColor(pal["text"]))
        name = QFontMetrics(font).elidedText(index.data(Qt.DisplayRole), Qt.ElideMiddle, r.width() - 16)
        p.drawText(QRect(r.left() + 8, r.top() + 26, r.width() - 16, 16), Qt.AlignLeft | Qt.AlignVCenter, name)  # the tile body is 58 px high: badge 8-24, name 26-42, state 42-54
        label, colour = STATE_TEXT.get(state, STATE_TEXT["waiting"])
        font.setPixelSize(9)
        p.setFont(font)
        p.setPen(QColor(pal[colour]))
        p.drawText(QRect(r.left() + 8, r.top() + 42, r.width() - 16, 12), Qt.AlignLeft | Qt.AlignVCenter, label)
        p.restore()


class DropBox(QListWidget):
    """The file list as tiles that wrap like text. While it is empty, a hint sits in the middle of it."""
    remove_requested = Signal(int)  # the × of a tile was clicked, or Delete on the selected tile
    add_requested = Signal()  # a left click on empty space (no tile, no ×): the file picker opens

    def __init__(self, hint_text):
        super().__init__()
        self.setObjectName("drop")
        self.setToolTip("Click to add files (Ctrl+O)")  # shown on empty space; a tile shows its own path
        self._empty_press = False  # the left button went down on empty space
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)  # the × turns hot under the pointer without a click
        self.viewport().setCursor(Qt.PointingHandCursor)  # empty space; over a tile it is the arrow
        self.close_hot = -1  # row whose × the pointer is over
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

    def _close_at(self, pos):
        """Row of the tile whose × is under `pos` (viewport coordinates), else -1."""
        idx = self.indexAt(pos)
        if idx.isValid() and _close_rect(self.visualRect(idx)).contains(pos):
            return idx.row()
        return -1

    def _set_hot(self, row):
        if row != self.close_hot:
            self.close_hot = row
            self.viewport().update()

    def _empty_at(self, pos):
        """True on the viewport where no tile is (viewport coordinates)."""
        return self.viewport().rect().contains(pos) and not self.indexAt(pos).isValid()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        self._set_hot(self._close_at(pos))
        self.viewport().setCursor(Qt.PointingHandCursor if self._empty_at(pos) else Qt.ArrowCursor)
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        row = self._close_at(pos) if e.button() == Qt.LeftButton else -1
        if row >= 0:
            self.remove_requested.emit(row)  # the click removes the tile and does not also select it
            return
        self._empty_press = e.button() == Qt.LeftButton and self._empty_at(pos)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        # The picker opens on release, and only when the press also began on empty space: a drag that ends there does not.
        opened = self._empty_press and e.button() == Qt.LeftButton and self._empty_at(e.position().toPoint())
        self._empty_press = False
        super().mouseReleaseEvent(e)
        if opened:
            self.add_requested.emit()

    def mouseDoubleClickEvent(self, e):
        pos = e.position().toPoint()
        if self._close_at(pos) >= 0:
            return  # a fast second click on the × must not remove the next tile too
        if self._empty_at(pos):
            self._empty_press = False  # the first click already opened the picker: the second one does nothing
            return
        super().mouseDoubleClickEvent(e)

    def viewportEvent(self, e):
        if e.type() == QEvent.Leave:
            self._set_hot(-1)
        return super().viewportEvent(e)

    def keyPressEvent(self, e):
        sel = self.selectedIndexes()  # the selected tile, not the "current" one (which stays after a click on empty space)
        if e.key() == Qt.Key_Delete and sel:
            self.remove_requested.emit(sel[0].row())
            return
        super().keyPressEvent(e)


def _choice_text(key, c):
    return ZERO.get(key, "Keep") if c == 0 else {2: "Stereo", 1: "Mono"}.get(c, str(c)) if key == "channels" else str(c)


class Worker(QThread):
    progress = Signal(int, str)  # index in the batch, file name: this file is being converted now
    converted = Signal(int)  # index in the batch: this file was written
    failed = Signal(int, str)  # index in the batch, message: this file failed (the batch goes on)
    done = Signal(list, list, list)  # outputs, errors as (name, message), notes: the status line, as before

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
                msg = describe(e)
                log.error("failed %s: %s", Path(f).name, scrub(msg, f))
                errs.append((Path(f).name, msg))
                self.failed.emit(i, msg)
            else:
                self.converted.emit(i)
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
        self.states = {}  # full path -> "waiting" | "working" | "done" | "failed"; a missing path is waiting
        self.fail_msgs = {}  # full path -> the message of its failure
        self.save_error = ""
        self.st = settings.load()
        self.opt_widgets = {}

        self.list = DropBox("Drop files here, or right-click files in Explorer and choose Convert.")
        self.list.remove_requested.connect(self._remove)
        self.list.add_requested.connect(self._pick)
        self.list.setAccessibleName("Files to convert")
        self.list.setAccessibleDescription("Drop files here or click an empty area to add files. Ctrl+O also adds files. "
                                           "Select a file and press Delete to remove it.")
        self.hint = self.list.hint
        self.fmt = QComboBox()
        self.fmt.setObjectName("fmt")
        self.fmt.setPlaceholderText("Add files first")
        self.fmt.setAccessibleName("Convert to")
        self.fmt.setAccessibleDescription("Output format")
        self.fmt.currentIndexChanged.connect(self._build_options)
        self.fmt_label = QLabel("Convert to")
        self.fmt_label.setBuddy(self.fmt)
        self.adv = QGroupBox("Advanced")
        self.adv.setAccessibleName("Advanced")
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
        self.bar.setAccessibleName("Conversion progress")
        self.go = QPushButton("Convert")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self._start)
        self.go.setAccessibleName("Convert")
        self.go.setAccessibleDescription("Convert the listed files to the chosen format")
        self.stop = QPushButton("Cancel")
        self.stop.clicked.connect(self._cancel)
        self.stop.setAccessibleName("Cancel")
        self.stop.setAccessibleDescription("Stop after the current file")
        self.stop.hide()
        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(self._open_folder)
        self.open_btn.setAccessibleName("Open folder")
        self.open_btn.setAccessibleDescription("Open the folder with the converted files")
        self.open_btn.hide()
        self.folder_menu = QMenu(self)  # one entry per output folder, shown when there are two or more
        self.logs_btn = QPushButton("Open log folder")
        self.logs_btn.clicked.connect(lambda: os.startfile(str(settings.log_dir())))
        self.logs_btn.setAccessibleName("Open log folder")
        self.logs_btn.setAccessibleDescription("Open the folder with the log file")
        self.logs_btn.hide()
        self.clear = QPushButton("Clear")
        self.clear.clicked.connect(self._clear)
        self.clear.setAccessibleName("Clear")
        self.clear.setAccessibleDescription("Remove all files from the list")

        for b in (self.clear, self.go):
            b.setFixedSize(80, 31)  # both bottom buttons as big as Convert; the text stays centred and keeps its size
        self.version = QLabel(f"v{CONVERT_VERSION}")
        self.version.setObjectName("version")
        self.version.setAlignment(Qt.AlignCenter)
        self.version.setContextMenuPolicy(Qt.CustomContextMenu)  # right-click: the Theme menu
        self.version.customContextMenuRequested.connect(self._theme_menu)
        self.version.setFocusPolicy(Qt.TabFocus)  # keyboard: Tab to it, then the Menu key or Shift+F10 opens the Theme menu
        self.version.setAccessibleName("Theme")
        self.version.setAccessibleDescription("Version number. Right-click, or press the Menu key, to choose System, Dark or Light theme")
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
        lay.addWidget(self.fmt_label)
        lay.addWidget(self.fmt)
        lay.addWidget(self.adv)
        lay.addWidget(self.trash)
        lay.addWidget(self.bar)
        lay.addWidget(self.msg)
        lay.addLayout(row)
        lay.setContentsMargins(11, 11, 11, 11)
        lay.setSizeConstraint(QLayout.SetFixedSize)  # 440 px wide (the box is 418 px), as high as its content, always
        self.shortcuts = []  # kept alive here; the window is their parent anyway
        for seq, slot in ((Qt.Key_Return, self._enter), (Qt.Key_Enter, self._enter), (Qt.Key_Escape, self._escape),
                          ("Ctrl+O", self._pick)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(slot)
            self.shortcuts.append(sc)
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
        self.updater.found.connect(self.update_notice.show_for, Qt.QueuedConnection)  # the label is only touched on the GUI thread
        self.updater.start()
        return True

    def _theme_menu(self, pos):
        """Right-click on the version: System, Dark or Light. The choice applies at once and is saved."""
        menu = QMenu(self.version)
        menu.addAction("Theme").setEnabled(False)  # a label, not a choice (addSection is not drawn with the stylesheet)
        menu.addSeparator()
        group = QActionGroup(menu)
        group.setExclusive(True)
        for value, label in (("system", "System"), ("dark", "Dark"), ("light", "Light")):
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.st["theme"] == value)
            act.setActionGroup(group)
            act.triggered.connect(lambda _checked=False, v=value: self._set_theme(v))
        menu.exec(self.version.mapToGlobal(pos))
        menu.deleteLater()

    def _set_theme(self, value):
        self.st["theme"] = value
        try:
            settings.save(self.st)
        except OSError as e:  # the theme still applies for this session
            log.warning("settings not saved: %s", e)
        apply_theme(QApplication.instance(), value, self)

    def eventFilter(self, obj, event):
        if obj is self.open_btn and event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress) and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.type() == QEvent.KeyPress:
                self._open_folder()  # Enter on the focused button: the same as a click, the menu when there are several
            event.accept()
            return True
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
        skipped = []
        for p in paths:
            p = str(Path(p))
            ok = not _is_network_path(p) and Path(p).is_file() and file_type(p) in SUPPORTED
            if not ok:
                skipped.append(Path(p).name or p)
            elif p not in self.files:
                self.files.append(p)
        if len(self.files) > before:
            self._reset_bar()  # a new batch: the bar of the last one is stale
        self._refresh()
        if skipped and not self.msg.text():  # the ffmpeg and mixed-kinds messages come first
            names = ", ".join(skipped[:3]) + (", ..." if len(skipped) > 3 else "")
            self._say(f"Skipped (not a supported file type): {names}", "muted")

    def _reset_bar(self):
        self.bar.setRange(0, 1)
        self.bar.setValue(0)

    def _pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add files", "", picker_filter())
        if paths:
            self.add_files(paths)

    def _drag(self, on):
        """The drop box shows a dashed accent border while a drag with files is over the window."""
        self.list.setProperty("drag", on)
        self.list.style().unpolish(self.list)
        self.list.style().polish(self.list)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag(True)

    def dragLeaveEvent(self, e):
        self._drag(False)

    def dropEvent(self, e):
        self._drag(False)
        self.add_files(u.toLocalFile() for u in e.mimeData().urls())

    def _remove(self, row):
        """Drops one file. Blocked while a batch runs. The selection moves to the same index, or the previous tile."""
        if self.worker or not 0 <= row < len(self.files):
            return
        fid = self.fmt.currentData()  # the format chosen now stays, if the rest still offers it
        path = self.files.pop(row)
        self.states.pop(path, None)
        self.fail_msgs.pop(path, None)
        self._refresh(keep=fid)
        if self.files:
            self.list.setCurrentRow(min(row, len(self.files) - 1))

    def _enter(self):
        """Enter = Convert, unless a list popup is open or a field (spin box, combo box, text) has the focus."""
        focus = QApplication.focusWidget()
        if QApplication.activePopupWidget() or isinstance(focus, (QSpinBox, QComboBox, QLineEdit)):
            return
        if isinstance(focus, QAbstractButton) and focus is not self.go:  # Enter on Clear, Cancel... is not "Convert"
            return
        if self.go.isEnabled() and not self.worker:
            self._start()

    def _escape(self):
        if self.worker and not self.stop.isHidden():
            self._cancel()

    def _clear(self):
        if self.worker:  # the list is in use by the running batch
            return
        self.files, self.outs = [], []
        self.states, self.fail_msgs = {}, {}
        self._reset_bar()  # Clear after a finished batch: the bar goes back to empty, not full blue
        self._refresh()

    def _tile(self, item, path):
        """Sets the state (for the delegate) and the tooltip of one tile from self.states and self.fail_msgs."""
        state = self.states.get(path, "waiting")
        item.setData(STATE_ROLE, state)
        item.setData(Qt.AccessibleTextRole, f"{Path(path).name}, {_kind(path)}, {state}")  # kept in step with the state
        item.setToolTip(f"{path}\n{self.fail_msgs.get(path, '')}" if state == "failed" else path)

    def _set_state(self, i, state, msg=None):
        """Changes one running file's tile in place: no rebuild of the list during a run."""
        if not 0 <= i < len(self.files) or self.list.item(i) is None:
            return
        path = self.files[i]
        self.states[path] = state
        if msg is not None:
            self.fail_msgs[path] = msg
        self._tile(self.list.item(i), path)
        self.list.viewport().update()

    def _missing_ffmpeg(self):
        return any(file_type(f) in ("audio", "video") for f in self.files) and not find_tool("ffmpeg")

    def _refresh(self, keep=None):
        """Rebuilds the list and the format choice. `keep`: the format to keep if still offered (after a removal)."""
        self.list.clear()
        self.list.close_hot = -1  # the pointer may be over a different tile now
        for f in self.files:
            item = QListWidgetItem(Path(f).name)
            item.setData(Qt.UserRole, _kind(f))
            self._tile(item, f)
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
        if self.fmt.count():  # with a placeholder text Qt no longer selects the first item by itself
            saved = self.st["last_format"].get(selection_type(self.files))  # the format last used for this type of file
            idx = self.fmt.findData(keep) if keep else -1
            if idx < 0 and saved:
                idx = self.fmt.findData(saved)
            self.fmt.setCurrentIndex(max(idx, 0))  # index 0 when neither is offered; the saved value itself is not changed
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
            self._set_tab_order()
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
            w.setAccessibleName(LABEL[key])
            self.form.addRow(LABEL[key], w)
            self.form.labelForField(w).setBuddy(w)  # the row's label names its field for screen readers
            w.setVisible(self.adv.isChecked())
        self._set_tab_order()

    def _set_tab_order(self):
        """Tab goes: update notice, drop box, format, Advanced, option fields, trash, Clear, log folder, Open folder, Cancel, Convert.
        Hidden widgets are skipped by Qt. Called again after each rebuild of the option fields."""
        chain = [self.update_notice, self.list, self.fmt, self.adv, *self.opt_widgets.values(), self.trash, self.clear,
                 self.logs_btn, self.open_btn, self.stop, self.go]
        for before, after in zip(chain, chain[1:]):
            QWidget.setTabOrder(before, after)

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
        self.st["last_format"][selection_type(self.files)] = self.fmt.currentData()  # remembered per file type
        self._say("", "muted")  # a skipped-files or other old message does not stay during the run
        try:
            settings.save(self.st)
        except OSError as e:  # the conversion still runs; the status line shows it after the first file
            log.warning("settings not saved: %s", e)
            self.save_error = f"Settings could not be saved ({e})."
        self.states, self.fail_msgs = {f: "waiting" for f in self.files}, {}  # a new run: every file waits again
        for i, f in enumerate(self.files):
            self._tile(self.list.item(i), f)
        self.list.viewport().update()
        self.worker = Worker(list(self.files), self.fmt.currentData(), self.st["options"], self.trash.isChecked())
        self.worker.progress.connect(self._progress)
        self.worker.converted.connect(self._converted)
        self.worker.failed.connect(self._failed)
        self.worker.done.connect(self._done)
        self.go.setEnabled(False)
        self.clear.setEnabled(False)
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
        self._set_state(i, "working")
        self._say(f"Converting {name}  ({i + 1}/{len(self.files)})", "muted")

    def _converted(self, i):
        self._set_state(i, "done")

    def _failed(self, i, msg):
        self._set_state(i, "failed", msg)

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
        for f, s in self.states.items():  # interrupted or not reached by Cancel: waiting again
            if s == "working":
                self.states[f] = "waiting"
        self.states = {f: s for f, s in self.states.items() if f in self.files}  # moved to the Recycle Bin: gone
        self.fail_msgs = {f: m for f, m in self.fail_msgs.items() if f in self.files}
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
        """One output folder: opened directly. Two to eight: a menu under the button lists them. More: the first eight and a count."""
        folders = []
        for o in self.outs:  # distinct folders, in the order the files were written
            d = str(Path(o).parent)
            if d not in folders:
                folders.append(d)
        if not folders:
            return
        folders = [d for d in folders if os.path.isdir(d) and not _is_network_path(d)]  # gone or remote by now: not opened
        if not folders:
            self._say("The output folder no longer exists.", "muted")
            return
        if len(folders) == 1:
            os.startfile(folders[0])
            return
        self.folder_menu.clear()
        for d in folders[:8]:
            act = self.folder_menu.addAction(d.replace("&", "&&"))  # & would make a mnemonic in a menu
            act.triggered.connect(lambda _checked=False, d=d: os.startfile(d))
        if len(folders) > 8:
            self.folder_menu.addAction(f"... and {len(folders) - 8} more").setEnabled(False)
        self.folder_menu.popup(self.open_btn.mapToGlobal(QPoint(0, self.open_btn.height())))

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
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # windll cannot take use_last_error
    _mutex = kernel32.CreateMutexW(None, False, f"Local\\{name}")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def run(files):
    app = QApplication(sys.argv[:1])
    if not claim_first():
        for _ in range(100):  # the first instance may still be starting: wait for its pipe (10 s)
            if _forward(files):
                return 0
            QThread.msleep(100)
        # it never answered (crashed?): carry on as the first instance
    st = settings.load()  # once, and before the window: the theme is applied first, so the window never opens in the wrong one
    apply_theme(app, st["theme"])
    QLocalServer.removeServer(PIPE)  # stale pipe name after a crash
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)  # only this Windows user may connect
    if not server.listen(PIPE):  # before the window exists, so the others can connect while it builds
        log.warning("single-instance pipe not available: %s", server.errorString())
    win = Window()
    QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: _on_scheme_changed(app, win))  # "system" follows Windows

    def on_connection():
        c = server.nextPendingConnection()
        c.setReadBufferSize(MAX_MESSAGE + 1)  # the socket buffers at most one byte past the limit, so a flood is not held
        buf = bytearray()

        def read():
            buf.extend(c.read(MAX_MESSAGE + 1).data())  # bounded: a peer cannot make us hold more than the limit
            if len(buf) > MAX_MESSAGE:  # a list of file names is never this big: drop the peer
                c.abort()

        c.readyRead.connect(read)

        def finish():
            buf.extend(c.read(MAX_MESSAGE + 1).data())  # bounded too: the rest of a big message is not read here
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
