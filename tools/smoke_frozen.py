"""Smoke test of the frozen exe: `python tools/smoke_frozen.py dist/Convert/Convert.exe`. Exit 0 only if every family converts.

Runs `Convert.exe --cli` in a throw-away profile (APPDATA and LOCALAPPDATA point to a temp folder), so the user's settings,
log and registry are not touched. Audio and video are checked only when ffmpeg is found; the report says when they were skipped.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import docx
import pymupdf
from PIL import Image


def main(exe):
    exe = Path(exe).resolve()
    if not exe.is_file():
        print(f"smoke: {exe} not found")
        return 1
    work = Path(tempfile.mkdtemp(prefix="convert-smoke-"))
    env = {**os.environ, "APPDATA": str(work / "a"), "LOCALAPPDATA": str(work / "l")}
    ffmpeg = next((Path(d) / "ffmpeg.exe" for d in env["PATH"].split(os.pathsep) if (Path(d) / "ffmpeg.exe").is_file()), None)

    Image.new("RGB", (64, 48), (200, 30, 30)).save(work / "pic.png")
    (work / "note.txt").write_text("Bonjour café €\nsecond line\n", "utf-8")
    (work / "page.md").write_text("# Titre\n\ntexte **fort**\n", "utf-8")
    d = docx.Document()
    d.add_paragraph("Rapport")
    d.save(work / "rapport.docx")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello pdf")
    doc.save(work / "in.pdf")
    doc.close()
    jobs = [("webp", "pic.png"), ("pdf", "note.txt"), ("docx", "page.md"), ("pdf", "rapport.docx"), ("png", "in.pdf"),
            ("txt", "in.pdf")]
    if ffmpeg:
        subprocess.run([str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "testsrc=s=96x64:d=1", "-f", "lavfi", "-i", "sine=d=1",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(work / "clip.mp4")], check=True)
        jobs += [("mp3", "clip.mp4"), ("mkv", "clip.mp4"), ("gif", "clip.mp4")]
    else:
        print("smoke: ffmpeg not found, audio and video skipped")

    bad = 0
    for fid, name in jobs:
        before = set(work.iterdir())
        r = subprocess.run([str(exe), "--cli", fid, str(work / name)], capture_output=True, text=True, env=env, timeout=300)
        made = [p for p in set(work.iterdir()) - before if p.is_file() and p.stat().st_size > 0]
        ok = r.returncode == 0 and bool(made)
        print(f"{'ok  ' if ok else 'FAIL'} {name} -> {fid}: exit {r.returncode}, {len(made)} file(s) {(r.stdout + r.stderr).strip()[:120]}")
        bad += not ok

    logs = list((work / "l").rglob("*.log"))
    text = "\n".join(p.read_text("utf-8", "replace") for p in logs)
    if "Frozen: True" not in text or "Traceback" in text or " ERROR " in text:
        print("FAIL runtime log: missing 'Frozen: True' or has errors")
        print(text[-1500:])
        bad += 1
    else:
        print(f"ok   runtime log: {len(logs)} file(s), frozen, no errors")
    print("smoke: " + ("FAILED" if bad else "all passed"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) > 1 else 2)
