"""Draws assets/convert.ico (rounded square, two arrows). Run by build.ps1 when the icon is missing."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets" / "convert.ico"


def draw(n=512):
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, n - 1, n - 1), n // 5, fill="#4c8dff")
    u = n / 10
    d.rectangle((2 * u, 3.6 * u, 6.2 * u, 4.6 * u), fill="white")
    d.polygon([(6 * u, 2.4 * u), (8.2 * u, 4.1 * u), (6 * u, 5.8 * u)], fill="white")
    d.rectangle((3.8 * u, 5.4 * u, 8 * u, 6.4 * u), fill="white")
    d.polygon([(4 * u, 4.2 * u), (1.8 * u, 5.9 * u), (4 * u, 7.6 * u)], fill="white")
    return im


if __name__ == "__main__":
    if not OUT.exists():
        OUT.parent.mkdir(exist_ok=True)
        draw().save(OUT, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print(OUT)
