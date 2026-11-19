"""Once a day, ask GitHub whether a newer release exists. One anonymous GET, standard library only.

Nothing is downloaded or installed here. The answer is trusted only as far as: a final (not draft, not prerelease) release,
a tag that looks like vX.Y.Z, and a page address inside this project's releases.
"""
import json
import logging
import re
import time
import urllib.request

log = logging.getLogger("convert")
API = "https://api.github.com/repos/TheCreator0169/convert/releases/latest"
PAGE_PREFIX = "https://github.com/TheCreator0169/convert/releases/"
DAY = 24 * 3600
TIMEOUT = 5  # seconds
MAX_BYTES = 1 << 20


def parse(tag):
    """'v0.1.12' or '0.1.12' -> (0, 1, 12); anything else -> None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag.strip()) if isinstance(tag, str) else None
    return tuple(int(x) for x in m.groups()) if m else None


def newer(tag, current):
    a, b = parse(tag), parse(current)
    return a is not None and b is not None and a > b


def due(last, now=None):
    """True when the last attempt is a day old or more, never happened, or lies in the future (clock moved back)."""
    now = time.time() if now is None else now
    return not (0 <= now - last < DAY)


def fetch_latest():
    """(tag, page address) of the latest release, or None on any problem (offline, rate limit, odd answer)."""
    req = urllib.request.Request(API, headers={"User-Agent": "Convert-update-check", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if r.status != 200:
                return None
            data = json.loads(r.read(MAX_BYTES).decode("utf-8"))
    except (OSError, ValueError) as e:  # URLError, HTTPError and timeouts are OSError; bad JSON and bad bytes are ValueError
        log.info("update check: no answer (%s)", type(e).__name__)
        return None
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag, url = data.get("tag_name"), data.get("html_url")
    if parse(tag) is None or not isinstance(url, str) or not url.startswith(PAGE_PREFIX):
        return None
    log.info("update check: latest release is %s", tag)
    return tag, url


def newer_release_url(current):
    """The release page to show when a newer version exists, else None."""
    found = fetch_latest()
    return found[1] if found and newer(found[0], current) else None


def safe_page(url):
    return isinstance(url, str) and url.startswith(PAGE_PREFIX)
