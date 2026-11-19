"""Remembered options and the app log, in %APPDATA%\\Convert and %LOCALAPPDATA%\\Convert."""
import json
import logging
import math
import os
import sys
import time
from datetime import date
from pathlib import Path

from .formats import DEFAULTS, OUTPUTS


LOG_DAYS = 14
THEMES = ("system", "dark", "light")  # the "theme" setting; anything else loads as "system"


def _dir(var):
    d = Path(os.environ.get(var) or Path.home()) / "Convert"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _coerce(val, default):
    """Keep `val` only when it has the type of `default` (a bool is not an int); else the default."""
    if isinstance(default, bool):
        ok = isinstance(val, bool)
    elif isinstance(default, int):
        ok = isinstance(val, int) and not isinstance(val, bool)
    else:
        ok = isinstance(val, type(default))
    return val if ok else default


# Valid values of the numeric options: the same numbers as ui.py (RANGE, CHOICES). Not imported from ui: that module loads Qt.
RANGES = {"bitrate": (32, 512), "fps": (0, 120), "width": (64, 3840), "quality": (1, 100), "max_size": (0, 16000)}
CHOICES = {"sample_rate": (0, 22050, 44100, 48000), "channels": (0, 1, 2), "bit_depth": (16, 24),
           "height": (0, 2160, 1440, 1080, 720, 480), "dpi": (72, 150, 300), "audio_track": (1, 2, 3, 4)}


def _valid(group, key, val, default):
    """A number outside its range is clamped to it; a value that is not one of the choices gives the default."""
    if key in RANGES:
        lo, hi = RANGES[key]
        if group == "gif" and key == "fps":
            lo = 1
        return min(max(val, lo), hi)
    if key in CHOICES:
        return val if val in CHOICES[key] else default
    return val


def _last_formats(saved):
    """Last output format per file type; an id is kept only if that type offers it (video also takes audio ids)."""
    raw = saved.get("last_format")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for t, fid in raw.items():
        offered = OUTPUTS.get(t, {}).keys() | (OUTPUTS["audio"].keys() if t == "video" else set())
        if isinstance(fid, str) and fid in offered:
            out[t] = fid
    return out


def load():
    try:
        saved = json.loads((_dir("APPDATA") / "settings.json").read_text("utf-8-sig"))
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    saved_opts = saved.get("options") if isinstance(saved.get("options"), dict) else {}
    options = {}
    for group, defaults in DEFAULTS.items():
        mine = saved_opts.get(group) if isinstance(saved_opts.get(group), dict) else {}
        options[group] = {k: _valid(group, k, _coerce(mine.get(k, d), d), d) for k, d in defaults.items()}
    last = saved.get("last_update_check")
    return {"trash_originals": saved.get("trash_originals") is True, "options": options, "last_format": _last_formats(saved),
            "update_check": saved.get("update_check", True) is True,  # on when absent; any other value than true means off
            "theme": saved.get("theme") if saved.get("theme") in THEMES else "system",
            "last_update_check": last if isinstance(last, (int, float)) and not isinstance(last, bool) and math.isfinite(last) else 0}


def save(settings):
    path = _dir("APPDATA") / "settings.json"
    tmp = path.with_name("settings.json.tmp")
    tmp.write_text(json.dumps(settings, indent=2), "utf-8")
    os.replace(tmp, path)  # atomic: a crash never leaves half a file (which would reset the update switch)


def prune_logs(logs, days=LOG_DAYS):
    """Retention: delete logs older than `days` (they hold file names)."""
    cutoff = time.time() - days * 86400
    for old in logs.glob("convert_*.log"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def log_dir():
    d = _dir("LOCALAPPDATA") / "logs"
    d.mkdir(exist_ok=True)
    return d


def setup_logging():
    log = logging.getLogger("convert")
    if not log.handlers:
        logs = log_dir()
        h = logging.FileHandler(logs / f"convert_{date.today():%Y%m%d}.log", encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.info("Frozen: %s", getattr(sys, "frozen", False))
        prune_logs(logs)
    return log
