"""Images through Pillow (HEIC and AVIF through plugins). Multi-frame input is kept for PDF, TIFF, GIF and WebP."""
from PIL import Image, ImageOps

import pillow_avif  # noqa: F401  registers AVIF
from pillow_heif import register_heif_opener

from .process import Cancelled

register_heif_opener()

PIL_NAME = {"jpg": "JPEG", "png": "PNG", "heic": "HEIF", "avif": "AVIF", "webp": "WEBP", "tiff": "TIFF",
            "gif": "GIF", "bmp": "BMP", "pdf": "PDF"}
NO_ALPHA = {"jpg", "bmp", "pdf"}
MULTI = {"pdf", "tiff", "gif", "webp"}  # formats that can hold several frames
META = {"jpg", "png", "webp", "tiff"}  # formats that get EXIF and the colour profile back
ORIENTATION = 274
MAX_FRAMES = 500  # an animation kept as several frames is held in memory: refuse the ones that would not fit
MAX_FRAME_PIXELS = 400_000_000  # frames x width x height, about 1.6 GB as RGBA
MAX_IMAGE_PIXELS = 178_000_000  # one image (one frame) in pixels, read from the header before any decoding
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS  # Pillow's own bomb guard uses the same limit (it refuses at twice this)


def _open(src):
    try:
        im = Image.open(src)
    except Image.DecompressionBombError as e:
        raise RuntimeError(f"image too large (limit {MAX_IMAGE_PIXELS // 1_000_000} million pixels)") from e
    if im.width * im.height > MAX_IMAGE_PIXELS:
        im.close()
        raise RuntimeError(f"image too large: {im.width}x{im.height} "
                           f"(limit {MAX_IMAGE_PIXELS // 1_000_000} million pixels)")
    return im


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


def still_count(src, fmt):
    """Images in a multi-image HEIC for a single-image target (one output each); 1 for everything else.
    Header only, before anything is written. Refused above MAX_FRAMES or the total pixel budget."""
    if fmt.id in MULTI:
        return 1
    try:
        im = Image.open(src)
    except Image.DecompressionBombError as e:
        raise RuntimeError(f"image too large (limit {MAX_IMAGE_PIXELS // 1_000_000} million pixels)") from e
    with im:
        n = getattr(im, "n_frames", 1)
        if im.format != "HEIF" or n < 2:  # AVIF and GIF/WebP/TIFF keep the first-frame behaviour
            return 1
        if n > MAX_FRAMES:
            raise RuntimeError(f"too many images in this HEIC: {n} (limit {MAX_FRAMES})")
        pixels = 0
        for i in range(n):
            im.seek(i)
            pixels += im.width * im.height
        if pixels > MAX_FRAME_PIXELS:
            raise RuntimeError(f"too many pixels in this HEIC: over {MAX_FRAME_PIXELS // 1_000_000} million in all")
    return n


def _save_kw(fmt, opts, exif, icc):
    """Quality, EXIF (orientation removed: the pixels are upright) and colour profile for one saved file."""
    kw = {"quality": opts["quality"]} if fmt.id in ("jpg", "heic", "avif", "webp", "pdf") else {}
    if ORIENTATION in exif:
        del exif[ORIENTATION]
    if fmt.id in META:
        if len(exif):
            kw["exif"] = exif
        if icc:
            kw["icc_profile"] = icc
    return kw


def convert_stills(src, fmt, opts, cancel, new_path):
    """One file per image of a multi-image HEIC. new_path(i) reserves and returns the file for image i (1-based), so
    numbering follows the file order. An image over MAX_IMAGE_PIXELS is skipped and named in the warning. Any failure
    or cancel removes every file written. Returns (paths, warning or None)."""
    written, skipped = [], []
    try:
        with Image.open(src) as im:
            total = im.n_frames
            for i in range(total):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                im.seek(i)
                if im.width * im.height > MAX_IMAGE_PIXELS:
                    skipped.append(str(i + 1))
                    continue
                icc = im.info.get("icc_profile") if im.mode in ("RGB", "RGBA", "L", "LA", "P") else None
                exif = Image.Exif()  # a fresh one per image: getexif() would keep the tags of an earlier image when this one has none
                if im.info.get("exif"):
                    exif.load(im.info["exif"])
                frame = _prep(ImageOps.exif_transpose(im), fmt, opts)
                kw = _save_kw(fmt, opts, exif, icc)
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                dst = new_path(i + 1)
                written.append(dst)
                frame.save(dst, PIL_NAME[fmt.id], **kw)
                if not dst.exists() or dst.stat().st_size == 0:
                    raise RuntimeError("converter wrote no output")
    except BaseException:
        for p in written:
            p.unlink(missing_ok=True)
        raise
    if not written:
        raise RuntimeError(f"no image could be converted: all {total} over the limit "
                           f"({MAX_IMAGE_PIXELS // 1_000_000} million pixels)")
    warn = None
    if skipped:
        warn = (f"images {', '.join(skipped)} of {total} skipped: over "
                f"{MAX_IMAGE_PIXELS // 1_000_000} million pixels")
    return written, warn


def convert(src, dst, fmt, opts, cancel=None):
    """Returns a warning string when the output is not the whole input, else None. Cancel is checked between frames."""
    with _open(src) as im:
        total = getattr(im, "n_frames", 1)
        icc = im.info.get("icc_profile") if im.mode in ("RGB", "RGBA", "L", "LA", "P") else None
        exif = im.getexif()
        take = total if fmt.id in MULTI else 1
        if take > 1 and (take > MAX_FRAMES or take * im.width * im.height > MAX_FRAME_PIXELS):
            raise RuntimeError(f"animation too large: {take} frames of {im.width}x{im.height} "
                               f"(limit {MAX_FRAMES} frames and {MAX_FRAME_PIXELS // 1_000_000} million pixels in all)")
        frames, durations, frame_pixels = [], [], 0
        for i in range(take):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            im.seek(i)
            if im.width * im.height > MAX_IMAGE_PIXELS:  # every frame, before it is decoded: _open() only sees the first
                raise RuntimeError(f"image too large: {im.width}x{im.height} "
                                   f"(limit {MAX_IMAGE_PIXELS // 1_000_000} million pixels)")
            frame_pixels += im.width * im.height  # each frame's own size, not the first one's
            if frame_pixels > MAX_FRAME_PIXELS:
                raise RuntimeError(f"animation too large: over {MAX_FRAME_PIXELS // 1_000_000} million pixels in all")
            durations.append(im.info.get("duration", 100))
            frames.append(_prep(ImageOps.exif_transpose(im), fmt, opts))
        loop = im.info.get("loop", 0)
    kw = _save_kw(fmt, opts, exif, icc)
    if len(frames) > 1:
        kw.update(save_all=True, append_images=frames[1:])
        if fmt.id in ("gif", "webp"):
            kw.update(duration=durations, loop=loop)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    frames[0].save(dst, PIL_NAME[fmt.id], **kw)
    if total > take:
        return f"only the first frame of {total} was converted"
    return None
