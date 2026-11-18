"""Explorer right-click entry: HKCU verbs under SystemFileAssociations, one per supported extension. No admin."""
import ctypes
import sys
import winreg
from pathlib import Path

from .formats import EXT_TYPE

BASE = r"Software\Classes"
ROOT = Path(__file__).resolve().parent.parent


def command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"', sys.executable
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pyw}" "{ROOT / "convert.pyw"}" "%1"', str(pyw)


def _notify():
    """Explorer caches verbs per file type: without this a running Explorer shows the change only after a restart."""
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED


def _verb(base, ext):
    return rf"{base}\SystemFileAssociations\.{ext}\shell\Convert"


def install(base=BASE, cmd=None, icon=None):
    cmd, icon = (cmd, icon or sys.executable) if cmd else command()
    for ext in EXT_TYPE:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _verb(base, ext), 0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Convert")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, f"{icon},0")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _verb(base, ext) + r"\command", 0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    _notify()


def _delete(path):
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        return True
    except OSError:  # missing, or still holds someone else's keys: leave it
        return False


def _delete_if_empty(path):
    """DeleteKey also removes a key that holds values: check for both subkeys and values first."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            subkeys, values, _ = winreg.QueryInfoKey(k)
    except OSError:
        return
    if not subkeys and not values:
        _delete(path)


def uninstall(base=BASE):
    """Removes only what install wrote; the shell, .ext and SystemFileAssociations containers go only if empty."""
    for ext in EXT_TYPE:
        verb = _verb(base, ext)
        _delete(verb + r"\command")
        if _delete(verb):
            _delete_if_empty(verb.rsplit("\\", 1)[0])
            _delete_if_empty(verb.rsplit("\\", 2)[0])
    _delete_if_empty(rf"{base}\SystemFileAssociations")
    _notify()


def installed(base=BASE):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, _verb(base, "mp3") + r"\command"))
        return True
    except OSError:
        return False
