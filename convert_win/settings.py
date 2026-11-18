"""Remembered options and the app log, in %APPDATA%\\Convert and %LOCALAPPDATA%\\Convert."""
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from .formats import DEFAULTS


def _dir(var):
    d = Path(os.environ.get(var) or Path.home()) / "Convert"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load():
    try:
        saved = json.loads((_dir("APPDATA") / "settings.json").read_text("utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {"trash_originals": bool(saved.get("trash_originals", False)),
            "options": {k: {**d, **saved.get("options", {}).get(k, {})} for k, d in DEFAULTS.items()}}


def save(settings):
    (_dir("APPDATA") / "settings.json").write_text(json.dumps(settings, indent=2), "utf-8")


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
    return log
