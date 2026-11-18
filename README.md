<p align="center"><img src="assets/logo.png" alt="Convert logo" width="128"></p>

# Convert for Windows

Right-click files in Explorer, choose **Convert**, pick a format. Everything runs on your PC: nothing is uploaded,
there is no network code, no account, no analytics.

Inspired by the macOS app [Convert](https://github.com/newtonstudios/convert) by newtonstudios: this is a Windows take on the same idea,
written from scratch (nothing copied).
Untested on other machines: keep your originals until you trust it.

## What it does

- Output goes **next to the original**, numbered if the name exists (`song 2.mp3`). Nothing is overwritten.
- Batches: many files of one kind at once, one progress bar. Audio and video can be mixed (audio targets).
- Optional switch: move originals to the Recycle Bin after each successful conversion.
- Drag files onto the window, or use the right-click menu.

| Input | Output |
|---|---|
| Audio | MP3, M4A (AAC), WAV, AIFF, FLAC, ALAC, Opus, OGG, WMA, AC3, WavPack, MP2 |
| Video | MP4 (H.264, HEVC, AV1), MOV (ProRes 422), WebM (VP9), MKV, animated GIF, or any audio format |
| Images | JPEG, PNG, HEIC, AVIF, WebP, TIFF, GIF, BMP, PDF |
| Documents (TXT, MD, HTML, RTF, DOCX, ODT) | PDF, DOCX, ODT, RTF, TXT, HTML |
| PDF | PNG or JPEG (one per page), TXT |

Advanced options per format (bitrate, resolution, quality, dpi, page size...) are remembered.

## Install

Run `Convert-Setup-vX.Y.Z.exe` (per-user, no admin). It adds **Convert** to the right-click menu.
Audio and video need **ffmpeg**: `winget install Gyan.FFmpeg`. Images, documents and PDF work without it.

Windows 11 shows the entry under **Show more options** (or Shift+F10), not in the short menu.
Windows SmartScreen may warn: the installer is not code-signed.

## Uninstall

Windows Settings, Apps, Convert. It removes the program and the menu entry, and asks whether to keep your settings.

## Known limits

- Legacy `.doc` is not supported. RTF and ODT inputs keep text only; Markdown covers common syntax.
- Animated GIF and multi-page TIFF keep every frame only for PDF, TIFF, GIF and WebP outputs; other formats keep the first frame, and the original is then kept even if the Recycle Bin switch is on.
- Hardware encoders (NVENC, QSV, AMF) are used only when ffmpeg lists them and a test encode works.

## Develop

```
py -3.13 -m venv .venv-win
.venv-win\Scripts\python.exe -m pip install -r requirements.txt
.venv-win\Scripts\python.exe convert.pyw [files]              # window
.venv-win\Scripts\python.exe -m convert_win.main --cli mp3 song.opus
.venv-win\Scripts\python.exe -m convert_win.main --cli        # list format ids
.venv-win\Scripts\python.exe -m unittest discover -s tests -t .
powershell -File build.ps1 v0.1.0                            # exe, plus installer if Inno Setup is installed
```

Project notes: `docs\`. The agent setup (`.claude\`, `CLAUDE.md`) is kept local.

## License

MIT, see `LICENSE`. ffmpeg is not bundled and keeps its own license.

## Support

If Convert is useful to you, you can buy me a coffee.

<a href="https://www.buymeacoffee.com/TheCreator0169"><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=TheCreator0169&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff" /></a>
