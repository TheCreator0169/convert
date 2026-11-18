"""Images through Pillow (HEIC and AVIF through plugins). Multi-frame input is kept for PDF, TIFF, GIF and WebP."""
from PIL import Image, ImageOps

import pillow_avif  # noqa: F401  registers AVIF
from pillow_heif import register_heif_opener

register_heif_opener()

PIL_NAME = {"jpg": "JPEG", "png": "PNG", "heic": "HEIF", "avif": "AVIF", "webp": "WEBP", "tiff": "TIFF",
            "gif": "GIF", "bmp": "BMP", "pdf": "PDF"}
NO_ALPHA = {"jpg", "bmp", "pdf"}
MULTI = {"pdf", "tiff", "gif", "webp"}  # formats that can hold several frames
META = {"jpg", "png", "webp", "tiff"}  # formats that get EXIF and the colour profile back
ORIENTATION = 274


def _prep(im, fmt, opts):
    if opts["max_size"]:
        im.thumbnail((opts["max_size"], opts["max_size"]))
    if fmt.id in NO_ALPHA and im.mode in ("RGBA", "LA", "P", "PA"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    if fmt.id in NO_ALPHA and im.mode != "RGB":
        return im.convert("RGB")
    return im


def convert(src, dst, fmt, opts):
    """Returns a warning string when the output is not the whole input, else None."""
    with Image.open(src) as im:
        total = getattr(im, "n_frames", 1)
        icc = im.info.get("icc_profile") if im.mode in ("RGB", "RGBA", "L", "LA", "P") else None
        exif = im.getexif()
        take = total if fmt.id in MULTI else 1
        frames, durations = [], []
        for i in range(take):
            im.seek(i)
            durations.append(im.info.get("duration", 100))
            frames.append(_prep(ImageOps.exif_transpose(im), fmt, opts))
        loop = im.info.get("loop", 0)
    if ORIENTATION in exif:
        del exif[ORIENTATION]  # the pixels are already upright
    kw = {"quality": opts["quality"]} if fmt.id in ("jpg", "heic", "avif", "webp", "pdf") else {}
    if fmt.id in META:
        if len(exif):
            kw["exif"] = exif
        if icc:
            kw["icc_profile"] = icc
    if len(frames) > 1:
        kw.update(save_all=True, append_images=frames[1:])
        if fmt.id in ("gif", "webp"):
            kw.update(duration=durations, loop=loop)
    frames[0].save(dst, PIL_NAME[fmt.id], **kw)
    if total > take:
        return f"only the first frame of {total} was converted"
    return None
