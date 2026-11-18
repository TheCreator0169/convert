# Build history

## v0.1.0 (2026-11-18, not tagged, not committed)

- Final `build.ps1 v0.1.0`: PyInstaller one-folder + Inno Setup 6.7.3.
  - `Convert.exe` sha256 `a3da0c85534a257f7a5e7903b43df9387a305694a9363b06ad2afecdf585674f`
  - `Convert-Setup-v0.1.0.exe` sha256 `ddc3835cf07a619682d399bb0e2f0f28ef58090c4c40034e2a9c9f43aea690be`
  - Earlier builds of the same version are under `archives\`.
- Source tests: 60 (54 with ffmpeg off the PATH, 6 media tests skipped then), all pass, 9 suites.
- Frozen, `--cli`: image, document and PDF families, wav to mp3/flac, mp4 to mp4/webm/gif/mp3, all written, no Traceback.
- **Installer round trip on this PC (user's OK), per-user, silent:** install writes `%LOCALAPPDATA%\Programs\Convert`, a Start menu link, an uninstall entry and 45 HKCU verbs (command `"...\Convert.exe" "%1"`); upgrade over an existing install works; uninstall leaves 0 verbs, no install folder, no link, no uninstall entry, no logs. The silent uninstall keeps settings by default (`%APPDATA%\Convert`, never created in this run). The PC was left in its original state (app uninstalled).
- **Bug found by that test and fixed:** three Explorer-style simultaneous launches opened two or three windows (every process saw no server yet). Fixed with an atomic named mutex plus waiting for the first instance's pipe; after the fix three launches gave one process and one window. Guarded by `tests.test_single_instance`.
- Build script note: Inno Setup could not write into `dist\` ("file in use"); `build.ps1` compiles in `%TEMP%` and copies.
- Not verified: how Explorer shows the entry (Windows 11 "Show more options" expected), the window by eye, that all three forwarded files appear in the one window (process count only), hardware encoders on a real GPU, the "keep settings?" question answered by a person.
