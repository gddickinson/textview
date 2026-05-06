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


def adjust(img: Image.Image,
           brightness: float = 1.0,
           contrast: float = 1.0,
           saturation: float = 1.0,
           gamma: float = 1.0) -> Image.Image:
    """Apply the full adjustment chain. Skips no-op stages."""
    out = img
    if brightness != 1.0:
        out = ImageEnhance.Brightness(out).enhance(brightness)
    if contrast != 1.0:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    if saturation != 1.0 and out.mode not in ("L", "1"):
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
    if img.mode == "L":
        return img.point(table)
    # Other modes: convert to RGB first.
    return img.convert("RGB").point(table * 3)


def pil_to_qimage(img: Image.Image) -> QImage:
    """Convert a PIL image to a QImage with no shared buffers (`.copy()`)."""
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
    rgb = img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height,
                  rgb.width * 3, QImage.Format.Format_RGB888)
    return qimg.copy()
