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
- 2026-11-18: v0.1.4 coded by Sonnet directly: PDF drawn page by page (no Qt page number, narrower side margins), DOCX writer (lists, tables, links, pictures), DOCX reader footnotes and nested lists, own ODT and RTF readers (odfpy and striprtf removed). 121 tests green. A pixel check caught white text in Windows dark mode; an ODT zip handle left open was caught by the temp cleanup.
- 2026-11-18: v0.1.5 coded by Sonnet directly: cancel checked between frames and pages (image, document), frame cap (500 frames / 400 million pixels) for animations, one line per failed file (selectable, wrapped), "Open log folder" button, "Cancelling..." message. 132 tests green. Real window check: 200-frame 60 MB GIF to WebP cancelled after 0.4 s, nothing left.
- 2026-11-18: v0.1.5 pushed and released (hash checked). v0.1.6 coded: "Audio track" (1-4) and "Keep subtitles" options, clear error for a missing track, picture-subtitle warning; new `tests/test_encoders.py` converts every audio id (12) and every video format for real and checks the codec. 145 tests green (run without `QT_QPA_PLATFORM=offscreen`, PDF text is empty under it). Not built, not committed.
- 2026-11-19: v0.1.6 pushed and released (hash checked). v0.1.7 coded: `tests/test_coverage_gaps.py` (every image input, palette/CMYK/grayscale, UTF-16/BOM text, PDF page naming/dpi/encrypted, a corrupt file per family, silent video, CLI exit codes), `tools/smoke_frozen.py` called by `build.ps1`, `.github/workflows/tests.yml` plus README badge. The smoke test found a real bug: NVENC refuses tiny videos and the conversion failed; now retried in software with a warning. H9 hashes not done (needs pip-tools download OK).
- 2026-11-19: v0.1.7 pushed and released (hash checked). The first CI run failed 2 tests: a real `unique_path` bug (dangling symlink followed on Windows, skipped on this PC for lack of a link privilege) and an encoding-dependent test. Both fixed locally and committed; the fix is not in the published v0.1.7, it goes in the next version. CI rerun needs a push.
- 2026-11-19: v0.1.8 built (fix for the dangling link in unique_path, version bump); 164 tests, frozen smoke OK. Not tagged, not pushed: waits for the user's word.
