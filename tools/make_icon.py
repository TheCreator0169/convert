"""Draws assets/convert.ico and assets/logo.png: blue gradient square, two white arrows, glass-like copies behind.
`python tools/make_icon.py --force` redraws both; without --force it draws only when the icon is missing."""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TOP, BOTTOM = (0x6A, 0xA8, 0xFF), (0x2F, 0x5B, 0xD8)  # gradient corners: top-left, bottom-right
SS = 2  # supersampling for smooth edges


def _arrows(u):
    """Right-pointing arrow on top, left-pointing below; polygons in pixels (u = 1/10 of the icon)."""
    right = [(2.4, 3.3), (6.0, 3.3), (6.0, 2.5), (7.8, 3.7), (6.0, 4.9), (6.0, 4.1), (2.4, 4.1)]
    left = [(7.6, 5.9), (4.0, 5.9), (4.0, 5.1), (2.2, 6.3), (4.0, 7.5), (4.0, 6.7), (7.6, 6.7)]
    return [[(x * u, y * u) for x, y in a] for a in (right, left)]


def _layer(n, polys, dx, dy, fill, outline=None, width=0):
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for p in polys:
        p = [(x + dx, y + dy) for x, y in p]
        d.polygon(p, fill=fill)
        if outline:
            d.line(p + [p[0], p[1]], fill=outline, width=width, joint="curve")
    return im


def draw(size=512):
    n = size * SS
    u = n / 10
    # diagonal gradient: weight = (x + y) / 2n
    horiz = Image.linear_gradient("L").rotate(90).resize((n, n))
    vert = Image.linear_gradient("L").resize((n, n))
    grad = Image.blend(horiz, vert, 0.5)
    bg = Image.composite(Image.new("RGB", (n, n), BOTTOM), Image.new("RGB", (n, n), TOP), grad).convert("RGBA")
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, n - 1, n - 1), n // 5, fill=255)

    polys = _arrows(u)
    off = 0.4 * u
    # glass copies: translucent fill, no outline, a faint soft shadow so they read as a pane
    shadow = _layer(n, polys, off, off + 0.15 * u, (10, 30, 100, 70)).filter(ImageFilter.GaussianBlur(0.18 * u))
    glass = _layer(n, polys, off, off, (255, 255, 255, 70))
    main_shadow = _layer(n, polys, 0, 0.12 * u, (10, 30, 100, 80)).filter(ImageFilter.GaussianBlur(0.15 * u))
    main = _layer(n, polys, 0, 0, (255, 255, 255, 255))

    for layer in (shadow, glass, main_shadow, main):
        bg = Image.alpha_composite(bg, layer)
    bg.putalpha(ImageChops.multiply(bg.getchannel("A"), mask))
    return bg.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    import sys

    ASSETS.mkdir(exist_ok=True)
    if "--force" in sys.argv or not (ASSETS / "convert.ico").exists():  # build.ps1 calls this without --force
        im = draw(512)
        im.save(ASSETS / "convert.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
        im.resize((256, 256), Image.LANCZOS).save(ASSETS / "logo.png")
    print(ASSETS)
