# Progress

Read at session start with `CLAUDE.md`, `decisions.md` and `known-issues.md`. Update at session end.
Build details (hashes, archives) live in `BUILD_HISTORY.md`; do not copy them here.

## Current work

**v0.1.0 built (2026-11-18), nothing committed or tagged.** Core converters, CLI, PySide6 window, Explorer menu code, `build.ps1`
and `installer\convert.iss` exist. Image, document and PDF conversions are verified in source and frozen. ffmpeg and Inno Setup are installed (user's OK); real audio/video tests pass in source and frozen; `Convert-Setup-v0.1.0.exe` is built.
Installed on the user's PC; the real right-click entry works and a .jpg to .webp conversion was confirmed by the user. The real-registry uninstall
and reinstall round trip is clean (`BUILD_HISTORY.md`). Open: the copyright holder name in `LICENSE`; the real hardware encoders were not tested.

**Next: the plan in `docs\ROADMAP.md` (v0.1.1 safety, v0.1.2 security, v0.1.3 documents, v0.2.0 window, v0.3.0 installer, v0.4.0 tests/CI).**
Four Haiku agents (scout x2, reviewer, security-auditor) produced it on 2026-11-18; Sonnet reproduced S1-S6 and the settings crash. Seven decisions (D1-D7) wait for the user.

## Done

- Omega structure (`.claude\`: 8 Haiku agents, 7 skills, settings; `CLAUDE.md`; `docs\`).
- v0.1.0 core + CLI, window (v0.2.0 scope of the roadmap) and menu code (v0.3.0 scope) written together; versions in the roadmap are not tagged separately.

## Log

- 2026-11-18: environment: Python 3.13 present; ffmpeg and Inno Setup missing. 46 tests green; frozen smoke OK for image, doc, PDF.
- 2026-11-18: all work this session was done by Sonnet directly; no Haiku agent was invoked (agents created mid-session, not loaded). Next session they exist.
- 2026-11-18: v0.1.3 done by Sonnet directly: DOCX reader (links, content controls, pictures, lists, nested and merged tables, FR/DE/ES/IT heading names), ffmpeg warns on extra audio tracks and subtitles. 104 tests green (1 skipped). Version string unchanged (0.1.1); not built, not committed.
