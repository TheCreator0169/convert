"""Headless quick convert for the Windows 11 Explorer flyout: `Convert.exe --quick <fmt_id> files...`.
No window and no console output: the start (long jobs only) and the result are Windows toasts, see `notify`."""
import sys
from pathlib import Path

from . import settings
from .formats import QUICK, file_type, quick_fmt

TITLE = "Convert"
LONG_FILES = 3  # more files than this, or any video: the job can take long, so it announces its start
AUMID = "Convert.QuickConvert"  # the toast sender name Windows shows; its key is removed by shell_integration.uninstall
AUMID_KEY = r"Software\Classes\AppUserModelId" + "\\" + AUMID

# Text comes through the environment, never into the script text: no quoting or injection issue.
_TOAST = r"""
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml('<toast><visual><binding template="ToastGeneric"><image placement="appLogoOverride"/><text/><text/></binding></visual></toast>')
$i = $x.GetElementsByTagName('image').Item(0)
if ($env:CONVERT_TOAST_ICON -and (Test-Path -LiteralPath $env:CONVERT_TOAST_ICON)) { $i.SetAttribute('src', ([System.Uri]$env:CONVERT_TOAST_ICON).AbsoluteUri) } else { [void]$i.ParentNode.RemoveChild($i) }
$t = $x.GetElementsByTagName('text')
$t.Item(0).InnerText = $env:CONVERT_TOAST_TITLE
$t.Item(1).InnerText = $env:CONVERT_TOAST_TEXT
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:CONVERT_TOAST_AUMID).Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def _icon():
    """The logo shown in the toast: bundled data folder when frozen, the repo otherwise."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(root / "assets" / "logo.png")


def _register_sender():
    """HKCU only: gives the toast its name (Convert) in the notification and in Settings."""
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, AUMID_KEY, 0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, TITLE)
        winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, _icon())


def notify(title, text, error=False):
    """Show a Windows toast through PowerShell (the Qt tray balloon never reached the notification center on Windows 11).
    Best effort: any failure is logged and swallowed, a notification must never fail a conversion."""
    import base64
    import os
    import subprocess
    try:
        _register_sender()
        ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        enc = base64.b64encode(_TOAST.encode("utf-16-le")).decode()
        env = dict(os.environ, CONVERT_TOAST_TITLE=title, CONVERT_TOAST_TEXT=text, CONVERT_TOAST_AUMID=AUMID, CONVERT_TOAST_ICON=_icon())
        subprocess.run([ps, "-NoProfile", "-NonInteractive", "-EncodedCommand", enc], env=env, timeout=20,
                       creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)  # 0x08000000 = CREATE_NO_WINDOW
    except Exception as e:
        settings.setup_logging().warning("notification failed: %s", type(e).__name__)


def _fail(text):
    notify(TITLE, text, error=True)
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
    return code
