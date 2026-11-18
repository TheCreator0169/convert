"""Remembered options and the app log, in %APPDATA%\\Convert and %LOCALAPPDATA%\\Convert."""
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

from .formats import DEFAULTS


LOG_DAYS = 14


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
        options[group] = {k: _coerce(mine.get(k, d), d) for k, d in defaults.items()}
    return {"trash_originals": saved.get("trash_originals") is True, "options": options}


def save(settings):
    (_dir("APPDATA") / "settings.json").write_text(json.dumps(settings, indent=2), "utf-8")


def prune_logs(logs, days=LOG_DAYS):
    """Retention: delete logs older than `days` (they hold file names)."""
    cutoff = time.time() - days * 86400
    for old in logs.glob("convert_*.log"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def setup_logging():
    log = logging.getLogger("convert")
    if not log.handlers:
        logs = _dir("LOCALAPPDATA") / "logs"
        logs.mkdir(exist_ok=True)
        h = logging.FileHandler(logs / f"convert_{date.today():%Y%m%d}.log", encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.info("Frozen: %s", getattr(sys, "frozen", False))
        prune_logs(logs)
    return log
