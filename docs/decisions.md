# Decisions

One entry per decision: date, what, why.

- **2026-11-18: no website, no server, no analytics.** The macOS repo's `site/` folder is not reproduced. Why: the user wants a purely local app.
- **2026-11-18: Windows stack = Python 3.13 + PySide6, ffmpeg external, Inno Setup installer.** Why: Python 3.13 is installed (3.14 is too new for native packages), PyInstaller builds an exe, the user accepted the recommendation. ffmpeg is not bundled (licence, size); decision on bundling stays open.
- **2026-11-18: Explorer entry is a registry verb under HKCU.** Why: no admin needed, clean uninstall. Limit: Windows 11 shows it under "Show more options"; top-level needs a sparse MSIX with `IExplorerCommand` (separate mission, not started).
- **2026-11-18: Omega structure reproduced from TURMO's `.claude\` and `docs\` (read only, nothing copied verbatim, nothing else in that repo read).** Same 8 Haiku agents (roles adapted), `omega-delegate`, `reflect`, `release`, build/test/GUI skills renamed `convert-*`, same settings and escalation ladder. The Tk and theme skills became `convert-qt-gui` and `convert-formats`; the LCD and CPU-helper specifics were dropped. Why: the user asked for the same structure for this project.
- **2026-11-18: single instance uses an atomic named mutex, then a local pipe.** The first version (try to connect, else listen) let simultaneous Explorer launches all become windows (seen with three launches of the installed exe). Why mutex: connect-then-listen is a race. The first instance listens before it builds its window; the others retry for 10 s.
- **2026-11-18: the uninstaller removes `%LOCALAPPDATA%\Convert` (logs) without asking and asks before removing `%APPDATA%\Convert` (settings, default keep).** Why: logs are not user data; the first uninstall left a log file.
- **2026-11-18: Memory lives in `docs\`.** `progress.md`, `decisions.md`, `known-issues.md`. No second memory system.
- **2026-11-18: Git is strictly local.** Same rule as TURMO; no remote, no push.
