# Next versions (plan only, nothing built)

Written 2026-11-19 from three read-only agent reports (scout, security-auditor, tester). The claims re-checked in code
then (PATHEXT .bat, DOCX size cap, UNC paths, `readAll()` before the size check, single-image pixel cap) are fixed in
v0.1.15; re-checked 2026-11-20.

Every version: builder codes, tester adds tests, reviewer reads the diff, windows-builder builds + frozen smoke test.
Push / tag / release: only on the user's word, each time. Visual change: element list first, wait for OK.

## v0.1.15: safety hardening (no visible change). DONE, released
| Item | Agent |
|---|---|
| DOCX/ODT: cap total unzipped size; ODT image budget + cache per href | builder |
| Pixel cap for single images (explicit `MAX_IMAGE_PIXELS`) | builder |
| find_tool: `.exe` only (no .bat/.cmd) | builder |
| Refuse UNC paths `\\server\...` (decision below) | builder |
| Pipe: `read(MAX+1)` instead of `readAll()`; mutex `use_last_error` | builder |
| settings.json numbers clamped to their ranges | builder |
| Installer: HKCU verbs removed by Pascal code (`RegDeleteKeyIncludingSubkeys`), not by `[Registry] uninsdeletekey` | builder |
| ODT loss warning (S7): original not trashed if drawings/text boxes | builder |
| Tests for each, plus: cancel during ffmpeg, disk full, zero-byte, long/non-ASCII names, remote images not fetched, ffmpeg missing, read-only folder | tester |
Check: full suite, security-auditor re-audit of the diff, frozen smoke. Size M.
D8 answered by the code: UNC paths are refused (decisions.md, 2026-11-20).

## v0.1.16: add and remove files (window, visible)
Add files button + file picker (U10), remove one file (U1), drop highlight and "unsupported file" message (U4),
keyboard: Enter = Convert, Esc = Cancel, Delete = remove, Ctrl+O (U8), remember last format (U7).
Agent: ui-designer lists every element first (position, size, colour, alignment); user OKs; builder; tester (Qt offscreen).
Check: tests, user's eyes on a real screenshot. Size M.

## v0.1.17: progress and accessibility
Per-file state in tiles (waiting / working / done / failed) (U1, U11), accessible names, label buddies, tab order (U9),
update notice reachable by keyboard, button to open the release page (U12), "Open folder" for every output folder.
Agent: ui-designer, builder, tester, reviewer. Check: tests + user. Size M.

## v0.1.18: installer polish
Compact installer window (no wizard pages beyond the needed), AppMutex (I4), seen-by-the-user check of every
installer page (I9), upgrade + uninstall round trip through `run_in_terminal`.
Agent: windows-builder, security-auditor on convert.iss. Needs the user for the real install. Size M-L.

## v0.2.0: bigger features (each only after the user chooses)
- ~~Light theme + system choice (U6, D5). ui-designer. M.~~ Done in v0.2.1: System, Dark or Light.
- Windows 11 top-level menu via sparse MSIX: needs signing (I7), so decide signing first. L.
- QSV / AMF encoders: no hardware here; ask the user to test on a PC that has it. S.
- ~~Legacy .doc input. L / S.~~ Done in v0.2.2: text only (own reader on olefile, no LibreOffice). (HEIC multi-frame: done in v0.2.0.)

## Doc fixes (any time, no version)
Done: ROADMAP.md D2 (built in v0.1.13); known-issues GIF line gone; H9 done (v0.1.14); convert-testing `test_process` wording fixed (2026-11-20).
Open, planned in v0.2.3 (in progress, not built): refuse network and device paths; write the lossy `.doc` warning to the log; replace the fixed 6 s sleep in test_single_instance (still `time.sleep(6)`, flaky); docs.
Windows 11 top-level menu: open, deferred (would be v0.2.4); the signing route and C++ toolchain are undecided.
Agent: builder, then reviewer.

## Decisions for the user
- D8: refuse `\\server\share` files (my advice) or accept?
- Order: hardening first (my advice), or the window first?
- Signing (I7): yes/no. It costs money and blocks the Windows 11 menu.
- Anything not listed above is not planned.
