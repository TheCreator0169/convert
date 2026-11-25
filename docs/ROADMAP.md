# Convert for Windows: roadmap

Status 2026-11-25: **v0.2.3 is the latest published release** (v0.2.4 Windows 11 menu and v0.2.5 quick-convert submenu: not published, see `docs\progress.md`) (public on `github.com/TheCreator0169/convert`, MIT). This file is the plan as it was written, kept as history: each table says what was built, released or dropped. Release dates are in `docs\progress.md`. The versions did not ship in the order below (v0.1.9 brought the installer pages, the window came in v0.1.11, v0.1.10 was never published); see progress.md for what each release contains.

Goal stays the same: right-click a file, choose Convert, done. 100 % local, no account, no telemetry.

## How each version is built (same loop every time)

1. **scout** (read-only) maps the files the item touches.
2. **tester** writes the test first; it must fail without the fix.
3. **builder** (or **ui-designer** for the window) makes the smallest change, one item per brief, writers never share a file.
4. **reviewer** reads the diff; Sonnet re-checks every report itself (counts, cited lines, a re-run).
5. All suites green, then local commit. **security-auditor** re-audits after v0.1.2. **windows-builder** builds and smoke-tests the frozen exe.
6. Push and release only on the user's word. Escalation: Haiku x3, Sonnet, Opus 5.5 medium for a blocker only.

Evidence labels: **reproduced** = Sonnet ran it and saw the failure; **read** = an agent read the code, not run yet.

## Release plan 0.1.4 to 0.2.0 (agreed 2026-11-18)

Every version ends the same way: tests first, all suites green, local commit, `build.ps1`, frozen smoke test, **you test**, then on your word: push, tag, GitHub release with the setup and its SHA256, download and compare the hash. One version, one release, no bundling.

| Version | Theme | Items | You test |
|---|---|---|---|
| v0.1.4 (released) | Output quality of documents | DOCX writer keeps lists, tables, links, images (today it writes text and bold/italic only); DOCX reader: footnotes, nested list levels, headers/footers; remove the page number Qt prints on PDFs; ODT and RTF read with structure (tables, bold) instead of text only | convert your own .docx / .odt / .rtf to PDF and DOCX and look |
| v0.1.5 (released) | Cancel and limits | Cancel interrupts a running image/document/PDF job (known issue); GIF/WebP/TIFF frame cap instead of a memory error; "Open log folder" and a copyable error per file (U3, text only, no restyle) | cancel a big job; convert a long GIF |
| v0.1.6 (published) | Audio and video | Choose which audio track and keep or drop subtitles (instead of warning only); ffprobe-based info; argument-level tests for every encoder; real conversion for every audio id (WMA, AC3, WavPack, MP2, ALAC 24-bit), HEVC, AV1, ProRes | convert a film with 2 audio tracks; a hardware encoder if your GPU has one |
| v0.1.7 (released; the H9 hashes came in the v0.1.14 build) | Tests and CI | Coverage list below (120+ tests); GitHub Actions on `windows-latest` (D6); frozen smoke test inside `build.ps1`; H9 hashes (`pip-tools`, a download: your OK) | nothing visible; CI badge green |
| v0.1.8 (released as the unique_path fix; the installer pages came in v0.1.9) | Installer | I1-I9: license page, optional desktop shortcut, French and English, `InstallDelete`, `AppMutex`, ffmpeg hint page (D3), real install / upgrade / uninstall in **your** terminal | install over v0.1.3, right-click, uninstall |
| v0.1.9 (released: the installer pages; the window came in v0.1.11) | Window behaviour (no restyle) | U7 remember size, position and last format; U8 keyboard; U9 accessibility; U10 Add files, Reset options; U12 ffmpeg-missing helper | use the window with the keyboard only |
| v0.2.0 (released as the HEIC multi-image change; the window work came in v0.1.11 to v0.1.18 and v0.2.1) | Window look | U1, U2, U4, U5, U6, U11. Before any code: I list each element with position, size, colour, alignment and wait for your OK | **you look at it** (I cannot judge looks) |

### Added from your feedback (2026-11-18): planned only, nothing built

| For | Item | Detail |
|---|---|---|
| v0.1.8 installer | **Compact installer window** | Much smaller window: today there is a lot of empty space. Default view shows only the essentials (progress, one status line). A **Show details** link expands a terminal-style log (files being copied, registry entries written) with a drop-down animation; collapsed by default. Inno Setup has no such page built in, so this is the one item that may need a custom wizard page (Pascal script) or a small helper window; I will say which before building. Same ordinary install, same files, same uninstall. |
| v0.2.0 window | **Smaller drop zone** | The "drop files here" area is too big. Shrink it to a compact strip; once files are added it shrinks further or turns into the file list. Exact size, position and colour go in the element list you approve first. |
| v0.2.0 window | **Layout inspired by the macOS app** (reference only, not copied) | From its README: a small window that shows only the output formats that fit the chosen files; one **Convert** button; **Advanced** collapsed by default, settings remembered per format; one progress bar for the whole batch; a "Move original to Trash" checkbox; an **Install** button for the right-click entry (also in a menu). I will turn this into a proposed layout (element list with position, size, colour, alignment) and a mock image for you to accept, change or reject before any code. |

Order stays: your review of the mock before v0.2.0 starts; then you test the new window and tell me what to change.

Order rationale: data quality first (a bad conversion is worse than an ugly window), then safety nets, then installer, then the window, so the window work lands on a tested base.
Decisions (status 2026-11-20): D2 update check = answered yes, built in v0.1.13; D3 ffmpeg bundling = external (still the default); D4 signing = none (README says so); D5 light theme = done in v0.2.1 (System, Dark or Light); D6 CI = yes, runs on every push; D7 reflog cleanup = still open, ask first.

## Decisions needed from the user

| # | Question | Default if no answer |
|---|---|---|
| D1 | Publish v0.1.0 as a GitHub Release now, or wait for v0.1.1 (safety fixes)? | Wait for v0.1.1 |
| D2 | Optional "check for a newer version" (one request to GitHub, off by default, opens the download page, installs nothing)? | Answered yes (2026-11-19). Built in v0.1.13; on unless `update_check` is `false` in settings.json |
| D3 | Bundle ffmpeg in the installer (GPL build, +80 MB) or keep it external with a hint? | External |
| D4 | Code signing (paid certificate) so SmartScreen does not warn? | No signing, README says so |
| D5 | Light theme and "follow Windows"? | Done in v0.2.1: a Theme choice, System (follows Windows), Dark or Light |
| D6 | GitHub Actions CI on every push (needs a token that may push workflow files)? | Yes, if the login allows it |
| D7 | Delete the old local reflog entries that still hold your personal email (`git reflog expire` + `gc`)? | Ask first |

## v0.1.1: safety fixes (no visible change). Release candidate #1

Rule: **an original is never sent to the Recycle Bin unless the output is complete and correct.**

| ID | Problem | Evidence | Where | Fix | Agent |
|---|---|---|---|---|---|
| S1 | Scanned PDF to TXT writes an empty file, reports success, trashes the PDF | reproduced | converter.py:19-20, pdf_conv.py:13-16 | PDF branch goes through the same checks: no outputs or a 0-byte output raises "no text found (scanned PDF?)", partial files removed, no trash | tester, builder |
| S2 | Multi-page TIFF to PDF keeps page 1 only; animated GIF/WebP keep frame 1; original trashed | reproduced (3 pages gave 1) | image_conv.py:15-17 | `save_all` for multi-frame inputs to PDF/TIFF/GIF/WebP; otherwise warn and do not trash | tester, builder |
| S3 | Camera photos come out sideways, EXIF date and GPS lost | reproduced (orientation) | image_conv.py:14-28 | `ImageOps.exif_transpose`, pass `exif` and `icc_profile` | tester, builder |
| S4 | Recycle Bin fails after a good conversion: file counted as failed though the output exists | reproduced | converter.py:36-37, ui.py:60-62 | catch it, report "converted, but the original could not be moved" | tester, builder |
| S5 | `settings.json` not an object (`[]`) crashes the window at start; UTF-8 BOM resets everything; `"false"` string turns trashing ON; wrong-type or unknown option crashes the window or makes every video fail | reproduced (crash, BOM, "false", wrong type kept); read (RANGE KeyError) | settings.py:20-24, ui.py:187-203, ffmpeg_conv.py:84,94 | `load()` reads `utf-8-sig`, checks types at each level, keeps only keys of DEFAULTS, coerces to the default's type, `trash_originals is True`; `save()` guarded with a visible message | tester, builder |
| S6 | UTF-16 text file becomes mojibake, then is trashed | reproduced | doc_conv.py:10-15 | BOM check first (UTF-16/32), then UTF-8, then cp1252 | tester, builder |
| S7 | RTF and ODT are read as text only, the message says "Done" | read | doc_conv.py:70,74, ui.py:253 | warning line for RTF/ODT sources, never trash them automatically | builder |
| S8 | Files added while a batch runs are dropped silently (right-click in Explorer, drop) | read | ui.py:125-126 | queue them and add when the batch ends, with a message | tester, builder |
| S9 | Cancel does nothing for image, document and PDF jobs; PDF failure at page 7 leaves pages 1-6; closing the window can abort the Qt thread | read | converter.py:20, pdf_conv.py:17-22, ui.py:266-270 | pass `cancel` through, check per page, unlink partial outputs, wait for the worker before closing | tester, builder |
| S10 | "Cancelled." shown when Cancel was pressed during the last file; "Converting..." keeps the previous green/red colour | read | ui.py:250-251, 225-230 | decide from real results; re-polish the label | builder |
| S11 | GIF frame rate can be set to 0 | read | ui.py:27, ffmpeg_conv.py:75 | minimum 1 for the GIF group | builder |

Done when: every ID has a test that failed before; 60+ tests green; frozen exe re-checked on S1-S4; reviewer reports no data-loss finding.

## v0.1.2: security hardening

| ID | Problem | Evidence | Where | Fix | Agent |
|---|---|---|---|---|---|
| H1 | `shutil.which` looks in the current folder first on Windows: a planted `ffmpeg.exe` next to your files could run | agent reproduced it; Explorer's working folder not checked | process.py:15-21 | walk `PATH` yourself, skip empty and relative entries; test with a planted exe | tester, builder |
| H2 | The single-instance pipe: default permissions unverified, `listen()` result ignored, no size cap, `RecursionError` escapes on deep JSON | read | ui.py:23,307-321 | `UserAccessOption`, check `listen()`, 1 MB cap, catch `Exception` | tester, builder |
| H3 | `--cli` takes URLs (ffmpeg would fetch them: breaks "no network"); relative names starting with `-` fail | read | main.py:19-25, ffmpeg_conv.py:71 | absolute paths, `is_file()`, `-protocol_whitelist file` | tester, builder |
| H4 | `unique_path` follows dangling links and `-y` overwrites; two CLI processes can pick the same name | read | formats.py:96-101 | `lexists`, exclusive create, `-n` | tester, builder |
| H5 | PDF to images has no limit on pixels or pages | read | pdf_conv.py:17-21 | cap pixels per page and page count, clear message | builder |
| H6 | HTML/Markdown with `<img src=file:///...>` may embed local files in the output | not tested | doc_conv.py:64-67 | test it, then turn resource loading off | tester, builder |
| H7 | Logs hold full file paths, no retention | read | converter.py:18, ui.py:61, settings.py:31-41 | log file names only, keep 14 days | builder |
| H8 | Uninstall leaves the empty `SystemFileAssociations` key, and deletes a `.ext` key that has values but no subkeys | read | shell_integration.py:49-55 | delete only when empty (no values, no subkeys); test with a foreign value | tester, builder |
| H9 | Dependencies unpinned, venv has extras | read | requirements.txt | hash-pinned lock file, build from a fresh venv | builder, windows-builder |
| H10 | `build.ps1` ignores the icon step's exit code | read | build.ps1:26 | check `$LASTEXITCODE` | builder |

Done when: **security-auditor** re-runs the same brief and returns no HIGH or MEDIUM; H1, H2, H4, H8 have tests.

**Release v0.1.1 here** (S + H items), unless D1 says otherwise.

## v0.1.3: document fidelity (DONE 2026-11-18, not committed; also extra audio tracks and subtitles now warn)

DOCX reader gaps (all **read**, doc_conv.py:26-40): hyperlink text dropped, content controls and table of contents skipped, images dropped, nested tables dropped, merged cells repeated, lists lose bullets, only English "Heading N" styles become headings (a French "Titre 1" does not). Plan: handle each with a test file, warn when something is dropped, never trash a source that lost content. Also: PDF "Titre/Heading" detection for FR styles, UTF-16 and BOM text round trips.
Agents: tester (builds sample docx), builder, reviewer. Done when: a French docx with a link, a list, a picture and a table converts to PDF and every element is present.

## v0.2.0 (window polish): items U1-U12 (needs the user's OK on the element list first)

From the UI survey (ui.py, theme.py). Nothing changes until you approve the list of elements with position, size, colour.

| ID | Item | Today | Agent |
|---|---|---|---|
| U1 | Per-file rows: name, type icon, state (waiting, converting, done, failed), remove button | names only (ui.py:149), no per-item remove | ui-designer |
| U2 | Per-file progress, smooth bar animation | bar moves per file only (ui.py:224-230) | ui-designer |
| U3 | Errors: one line per file, wrapped, text selectable, "Open log folder" | one joined label, no wrap, not copyable (ui.py:90,249) | ui-designer |
| U4 | Drag and drop: highlight while over the window, message for rejected files | accepts anything, silent skips (ui.py:133-138,125-129) | ui-designer |
| U5 | Transitions: fade between empty, files, converting, done; status text cross-fade | none | ui-designer |
| U6 | Light and dark theme, follows Windows (D5) | dark only (theme.py:2-3) | ui-designer |
| U7 | Remember window size and position, and the last format per file type | neither saved (settings.py:23-24) | builder |
| U8 | Keyboard: Enter converts, Esc cancels, Delete removes a row, Ctrl+O adds files | none | ui-designer |
| U9 | Accessibility: label buddies, tooltips, tab order, visible focus | none | ui-designer |
| U10 | "Reset options", "Add files" button and file picker | none | ui-designer |
| U11 | After success rows show "done" instead of staying as if not converted | list unchanged (ui.py:245-246) | ui-designer |
| U12 | ffmpeg missing: copyable command and a button that opens the download page (no silent install) | text only (ui.py:155) | ui-designer |

Done when: offscreen smoke test builds every state, frozen exe launches, **you** look at it (I cannot judge looks).

## v0.1.8 (installer): items I1-I9

| ID | Item | Today (convert.iss) | Agent |
|---|---|---|---|
| I1 | License page (MIT) | none | builder |
| I2 | Optional desktop shortcut, unchecked | none | builder |
| I3 | French and English installer | English only | builder |
| I4 | Upgrade removes files that no longer exist (`InstallDelete`), `AppMutex` so a running Convert is detected | files left behind | builder |
| I5 | Final page: ffmpeg status and how to install it (D3) | none | builder |
| I6 | `build.ps1` also writes `SHA256SUMS.txt` ready to attach to a GitHub Release | partly | windows-builder |
| I7 | Code signing (D4) | none | user |
| I8 | Optional update check (D2) | none | builder |
| I9 | Real install, right-click, uninstall check in **your terminal** (the agent shell hides the real registry) | done for v0.1.0 | windows-builder via run_in_terminal |

Done when: install, upgrade over the previous version, and uninstall are clean in the real registry; the release page has the setup and its SHA256.

## v0.1.7 (tests and CI)

Gaps from the coverage survey (54 tests today): real conversion for every audio id (WMA, AC3, WavPack, MP2, WAV, M4A, ALAC 24-bit), HEVC, AV1, ProRes, fps, keep_audio, hardware-encoder flags (argument level), every image input type (JPG, HEIC, AVIF, TIFF, GIF, BMP, WebP, palette, CMYK), document inputs (HTML, RTF, ODT, UTF-8 and UTF-16 text, `.markdown`), multi-page PDF naming, JPEG pages, dpi, encrypted and corrupt PDF, a corrupt file per family, a silent video to audio, CLI (exit codes, format listing, unknown id, install/uninstall dispatch), settings (corrupt, wrong type, BOM), UI (cancel, drag, ffmpeg missing with a mock, pipe success path, closing during a run), shell (foreign verb, `installed()`, values-only key), build refusals, a scripted frozen-exe smoke test run by `build.ps1`.
CI (D6): GitHub Actions on `windows-latest` running the suite on every push.
Agents: scout (list), tester (writes), reviewer. Done when: >= 120 tests, CI green, frozen smoke test part of the build.

## Not planned unless you ask

Excel/PowerPoint, a website, telemetry. Legacy `.doc` input was added in v0.2.2 (text only).
