"""The only place that starts a subprocess: no console window, cancellable."""
import os
import subprocess
import sys
import time
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Cancelled(Exception):
    pass


def find_tool(name):
    """ffmpeg/ffprobe next to the exe (bundled later) or on PATH; None when missing."""
    if getattr(sys, "frozen", False):
        local = Path(sys.executable).with_name(f"{name}.exe")
        if local.exists():
            return str(local)
    # shutil.which also tries the current folder on Windows (unless NoDefaultCurrentDirectoryInExePath is set, which an
    # Explorer launch does not have): a planted ffmpeg.exe beside the user's files would run. Walk PATH ourselves, absolute
    # entries only.
    exts = [e for e in os.environ.get("PATHEXT", ".EXE").lower().split(os.pathsep) if e] or [".exe"]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip('"')
        if not d or not os.path.isabs(d):
            continue
        for ext in exts:
            cand = Path(d) / f"{name}{ext}"
            if cand.is_file():
                return str(cand)
    return None


def run(args, cancel=None):
    """Run a list of args. Returns (returncode, stdout, stderr). `cancel` is a threading.Event."""
    p = subprocess.Popen([str(a) for a in args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    if cancel is None:
        out, err = p.communicate()
    else:
        import threading
        res = []
        t = threading.Thread(target=lambda: res.append(p.communicate()), daemon=True)
        t.start()
        while t.is_alive():
            if cancel.is_set():
                p.terminate()
                t.join(5)
                raise Cancelled()
            time.sleep(0.1)
        out, err = res[0]
    return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
