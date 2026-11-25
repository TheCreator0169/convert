"""Headless quick convert for the Windows 11 Explorer flyout: `Convert.exe --quick <fmt_id> files...`.
No window and no console output: the start (long jobs only) and the result are tray balloons, see `notify`."""
import sys
from pathlib import Path

from . import settings
from .formats import QUICK, file_type, quick_fmt

TITLE = "Convert"
MSECS = 6000  # how long a tray message stays up (also how long the process waits for it)
LONG_FILES = 3  # more files than this, or any video: the job can take long, so it announces its start

_app = None  # kept referenced for the whole run
_tray = None  # the tray icon; its balloon is shown by Windows while the process lives


def notify(title, text, error=False):
    """Show a tray balloon. The QApplication and the tray icon are created once; nothing waits here (see `_linger`).
    Without a system tray nothing is shown."""
    global _app, _tray
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    if QApplication.instance() is None:
        _app = QApplication(sys.argv[:1] or ["Convert"])
    if _tray is None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # frozen: bundled data folder
        _tray = QSystemTrayIcon(QIcon(str(root / "assets" / "logo.png")))
        _tray.show()
    icon = QSystemTrayIcon.MessageIcon.Critical if error else QSystemTrayIcon.MessageIcon.Information
    _tray.showMessage(title, text, icon, MSECS)


def _linger():
    """Process events until the last message has had its time, then hide the icon. No-op when nothing was shown."""
    global _tray
    if _tray is None:
        return
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(MSECS, loop.quit)
    loop.exec()
    _tray.hide()
    _tray = None


def _fail(text):
    notify(TITLE, text, error=True)
    _linger()
    return 2


def run(argv):
    """`argv` is [fmt_id, *files]. Returns 0 when every file converted, 1 when some failed, 2 for a usage error."""
    from .converter import convert_file, describe, scrub
    fmt_id, files = (argv[0], list(argv[1:])) if argv else ("", [])
    if not files:
        return _fail("No files to convert")
    unknown = [Path(f).name for f in files if file_type(f) is None]
    if unknown:
        return _fail(f"Not a supported file type: {unknown[0]}")
    kinds = {file_type(f) for f in files}
    if kinds == {"audio", "video"}:  # an audio + video mix converts to audio, like selection_type
        type_ = "audio"
    elif len(kinds) == 1:
        type_ = next(iter(kinds))
    else:
        return _fail("Mixed file types: pick files of one type")
    if fmt_id not in QUICK[type_]:
        return _fail(f"{fmt_id} is not offered for {type_} files")
    fmt = quick_fmt(type_, fmt_id)
    n = len(files)
    if "video" in kinds or n > LONG_FILES:
        notify(TITLE, f"Converting {n} file(s) to {fmt.label}")
    st = settings.load()
    failures = []
    for f in files:
        try:
            convert_file(f, fmt_id, st["options"], st["trash_originals"], notes=[])
        except Exception as e:  # report each file, keep going
            text = scrub(describe(e), f)
            settings.setup_logging().error("failed %s: %s", Path(f).name, text)
            failures.append(text)
    if failures:
        notify(TITLE, f"{len(failures)} of {n} failed: {failures[0]}", error=True)
        code = 1
    else:
        notify(TITLE, f"Converted {n} file(s) to {fmt.label}")
        code = 0
    _linger()
    return code
