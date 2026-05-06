"""Image adjustment pipeline.

Pure-Python helpers that apply brightness / contrast / saturation / gamma
to a `PIL.Image` and convert the result to a `QImage`. No Qt widgets here,
no MainWindow coupling — the same chain is reused by `ImageView` for live
preview and could be reused by the Save-As path later.

All multipliers default to 1.0 (identity). Gamma uses the standard
power-law `out = (in/255) ** (1/gamma) * 255`.
"""
from PIL import Image, ImageEnhance
from PyQt6.QtGui import QImage


# PIL's ImageEnhance / blend / point operations only work on a small set
# of modes. 16-bit and 32-bit-float TIFFs (I;16, I;16B, F), 1-bit images,
# and palette-with-alpha (PA) all raise `ValueError: image has wrong mode`.
# Normalize at the entry point — every adjustment chain works on RGB(A).
_SAFE_MODES = {"RGB", "RGBA", "L", "LA"}


def _coerce_to_blendable(img: Image.Image) -> Image.Image:
    """Return a copy in a mode that PIL's enhancement primitives accept."""
    if img.mode in _SAFE_MODES: return img
    # 16-bit grayscale / float / palette / 1-bit / etc. → RGB (or RGBA).
    if "A" in img.mode or img.mode == "PA":
        return img.convert("RGBA")
    return img.convert("RGB")


def adjust(img: Image.Image,
           brightness: float = 1.0,
           contrast: float = 1.0,
           saturation: float = 1.0,
           gamma: float = 1.0) -> Image.Image:
    """Apply the full adjustment chain. Skips no-op stages."""
    out = _coerce_to_blendable(img)
    if brightness != 1.0:
        out = ImageEnhance.Brightness(out).enhance(brightness)
    if contrast != 1.0:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    if saturation != 1.0 and out.mode not in ("L", "LA", "1"):
        out = ImageEnhance.Color(out).enhance(saturation)
    if gamma != 1.0 and gamma > 0:
        out = _apply_gamma(out, gamma)
    return out


def _apply_gamma(img: Image.Image, gamma: float) -> Image.Image:
    inv = 1.0 / gamma
    table = [min(255, max(0, int(((i / 255.0) ** inv) * 255 + 0.5)))
             for i in range(256)]
    if img.mode in ("RGB", "RGBA"):
        bands = list(img.split())
        for i in range(3):
            bands[i] = bands[i].point(table)
        return Image.merge(img.mode, bands)
    if img.mode == "LA":
        l, a = img.split()
        return Image.merge("LA", (l.point(table), a))
    if img.mode == "L":
        return img.point(table)
    # Anything else (already coerced upstream, but keep safe).
    return img.convert("RGB").point(table * 3)


def pil_to_qimage(img: Image.Image) -> QImage:
    """Convert a PIL image to a QImage with no shared buffers (`.copy()`)."""
    # 16-bit / 32-bit-float modes can't be byte-copied straight to QImage —
    # promote to 8-bit RGB(A) first. PIL's convert() autoscales 16-bit
    # samples down to 8-bit, which is what every Qt format expects.
    if img.mode in {"I", "I;16", "I;16B", "I;16L", "I;16N", "F"}:
        img = img.convert("RGB")
    if img.mode == "RGBA":
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height,
                      img.width * 4, QImage.Format.Format_RGBA8888)
        return qimg.copy()
    if img.mode == "L":
        data = img.tobytes("raw", "L")
        qimg = QImage(data, img.width, img.height,
                      img.width, QImage.Format.Format_Grayscale8)
        return qimg.copy()
    if img.mode == "LA":
        # No direct LA→Qt format; promote to RGBA.
        img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height,
                      img.width * 4, QImage.Format.Format_RGBA8888)
        return qimg.copy()
    rgb = img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height,
                  rgb.width * 3, QImage.Format.Format_RGB888)
    return qimg.copy()
