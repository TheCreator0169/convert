"""Images through Pillow (HEIC and AVIF through plugins). First frame only for animated input."""
from PIL import Image

import pillow_avif  # noqa: F401  registers AVIF
from pillow_heif import register_heif_opener

register_heif_opener()

PIL_NAME = {"jpg": "JPEG", "png": "PNG", "heic": "HEIF", "avif": "AVIF", "webp": "WEBP", "tiff": "TIFF",
            "gif": "GIF", "bmp": "BMP", "pdf": "PDF"}
NO_ALPHA = {"jpg", "bmp", "pdf"}


def convert(src, dst, fmt, opts):
    with Image.open(src) as im:
        im.seek(0)
        im = im.copy()
    if opts["max_size"]:
        im.thumbnail((opts["max_size"], opts["max_size"]))
    if fmt.id in NO_ALPHA and im.mode in ("RGBA", "LA", "P", "PA"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    elif fmt.id in NO_ALPHA and im.mode != "RGB":
        im = im.convert("RGB")
    kw = {"quality": opts["quality"]} if fmt.id in ("jpg", "heic", "avif", "webp", "pdf") else {}
    im.save(dst, PIL_NAME[fmt.id], **kw)
