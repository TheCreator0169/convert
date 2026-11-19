# Update notice: plan (built in v0.1.13)

Goal: when Convert is open, once a day, ask GitHub whether a newer release exists. If so, show a plain text line above the
drop box. Nothing is downloaded or installed by Convert.

## Decisions taken (by the user, 2026-11-19)

- Check automatically while the app is used; never when it is not running.
- At most **one attempt per day**, success or failure.
- A notice, not a button: text only, blue underline when the mouse is over it. It does not say "update" or "download" as an
  action. Clicking it opens the release page in the browser; the user installs by hand as today.

## Conflict to settle first

`CLAUDE.md` ("Preserve") and the README say: no network call, no telemetry. This feature is one network call. Before coding:
the user confirms the rule changes to "one anonymous request per day to GitHub, nothing else", and `CLAUDE.md`, the README
("no network code") and `docs\decisions.md` (D2, now answered yes) are updated in the same change. Nothing is sent about the
user: GitHub sees the IP address of the request, like any download page.

## Design

| Part | Choice |
|---|---|
| Request | `GET https://api.github.com/repos/TheCreator0169/convert/releases/latest`, standard library `urllib` only (no new dependency), 5 s timeout, no token, no cookies |
| Identity sent | a generic `User-Agent` (`Convert-update-check`), no version, no machine name, no user name |
| When | on a background thread started after the window is shown, never blocking the window; at most once per 24 h, stored as a timestamp in `%APPDATA%\Convert\settings.json` (`last_update_check`); the timestamp is written **before** the request, so a failure or a crash still counts as the day's attempt |
| Compare | tag `vX.Y.Z` to `CONVERT_VERSION`, as integer tuples; newer means notice; a malformed tag, a draft, a prerelease or any error means nothing is shown and nothing is logged to the user |
| Notice | one `QLabel` above the drop box, accent colour `#4c8dff`, 13 px, left aligned, underlined only on hover, pointing-hand cursor, hidden when there is nothing to say (no gap, the window height already follows its content); text: "A new version is available" |
| Click | opens the release page URL; the URL is **checked** to start with `https://github.com/TheCreator0169/convert/releases/` before opening, never taken blindly from the answer |
| Off switch | `update_check: true` in `settings.json`, no checkbox in the window; the README says how to turn it off |
| Never | no download, no install, no restart, no telemetry, no retry loop, no check at Explorer launches that only forward files to a running window |

## Steps

1. Settle the rule above with the user; update `CLAUDE.md`, README and `decisions.md`.
2. `convert_win\update_check.py`: `newer(tag, current)`, `due(last, now)`, `fetch_latest()` returning a tag and a URL or `None`.
3. `settings.py`: the two new keys with defaults and the usual corrupt-file handling.
4. `ui.py`: the notice label and a daemon thread (`UpdateCheck`), started by `run()` after `show()`, never by the tests.
5. Tests (no real network, `urllib` mocked): version comparison (`0.1.9` < `0.1.10`), once-a-day throttle, timestamp written before the request, timeout and bad JSON and 403 rate limit show nothing, a foreign URL is refused, switch off means no thread, the label takes no room while hidden.
6. Real check once by hand against the public release list, from the user's terminal, with the user's OK.
7. Frozen check: the frozen exe can reach GitHub (TLS certificates are bundled), and shows the notice when `CONVERT_VERSION` is lowered for the test.
8. README: one sentence about the daily check and how to turn it off. Release as its own version.

## Not verified until built

How the notice looks, whether GitHub's unauthenticated limit (60 requests per hour per address) matters behind a shared office
address (one request a day: it should not), and behaviour offline or behind a proxy that blocks GitHub (expected: silence).
