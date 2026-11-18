"""The only place that starts a subprocess: no console window, cancellable."""
import shutil
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
    return shutil.which(name)


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
