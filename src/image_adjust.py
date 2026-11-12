"""Image adjustment pipeline.

Pure-Python helpers that apply brightness / contrast / saturation / gamma
to a `PIL.Image` and convert the result to a `QImage`. No Qt widgets here,
no MainWindow coupling — the same chain is reused by `ImageView` for live
preview and could be reused by the Save-As path later.

All multipliers default to 1.0 (identity). Gamma uses the standard
power-law `out = (in/255) ** (1/gamma) * 255`.
"""
from PIL import Image, ImageEnhance


# PIL's ImageEnhance / blend / point operations only work on a small set
# of modes. 16-bit and 32-bit-float TIFFs (I;16, I;16B, F), 1-bit images,
# and palette-with-alpha (PA) all raise `ValueError: image has wrong mode`.
# Normalize at the entry point — every adjustment chain works on RGB(A).
_SAFE_MODES = {"RGB", "RGBA", "L", "LA"}
_WIDE_DYNAMIC_MODES = {"I", "I;16", "I;16B", "I;16L", "I;16N", "F"}


def _autoscale_to_8bit(img: Image.Image) -> Image.Image:
    """Linearly stretch a wide-dynamic-range image to 8-bit `L`.

    PIL's `convert("L")` from `I;16` / `F` etc. truncates by an
    implementation-specific shift (`I;16` divides by 256). For scientific
    images that use only a fraction of the 16-bit range — e.g. a
    microscope frame with values 300–1200 out of 0–65535 — that maps
    everything to 1–4 and the image looks black. Autoscaling to the
    actual data range fixes that, matching ImageJ / Fiji's default
    'auto contrast' behavior."""
    import numpy as np
    arr = np.asarray(img, dtype=np.float64)
    if arr.size == 0: return img.convert("L")
    mn = float(arr.min()); mx = float(arr.max())
    if mx <= mn:
        return Image.new("L", img.size, int(max(0, min(255, mn))))
    scaled = (arr - mn) * (255.0 / (mx - mn))
    return Image.fromarray(scaled.astype(np.uint8), mode="L")


def _coerce_to_blendable(img: Image.Image, autoscale: bool = False) -> Image.Image:
    """Return a copy in a mode that PIL's enhancement primitives accept.

    Wide-dynamic-range modes (I;16, F, …) need 8-bit conversion. With
    `autoscale=True` the conversion is a min/max stretch so even
    low-signal microscope data is visible. With `autoscale=False` we
    do an honest right-shift to the high 8 bits — that's what most
    scientific viewers (ImageJ etc.) call 'raw' display. PIL's own
    `convert("L")` from `I;16` is buggy in current versions (clips to
    255), so we don't use it."""
    if img.mode in _SAFE_MODES: return img
    if img.mode in _WIDE_DYNAMIC_MODES:
        if autoscale: return _autoscale_to_8bit(img)
        return _truncate_to_8bit(img)
    if "A" in img.mode or img.mode == "PA":
        return img.convert("RGBA")
    return img.convert("RGB")


def _truncate_to_8bit(img: Image.Image) -> Image.Image:
    """Honest 16-bit → 8-bit truncation (high byte). Mirrors what
    ImageJ does when 'auto-contrast' is off."""
    import numpy as np
    arr = np.asarray(img)
    if arr.dtype == np.uint16:
        out = (arr >> 8).astype(np.uint8)
    elif arr.dtype == np.int32:
        out = np.clip(arr // 256, 0, 255).astype(np.uint8)
    elif arr.dtype.kind == "f":
        out = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    else:
        out = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="L")


def _stretch_8bit(img: Image.Image) -> Image.Image:
    """Linearly stretch min→0, max→255 across each channel (per-frame).
    Mirrors ImageJ / Fiji's 'Auto-contrast' default."""
    import numpy as np
    arr = np.asarray(img)
    if arr.size == 0: return img
    out = np.empty_like(arr) if arr.ndim == 3 else None
    if arr.ndim == 2:
        mn, mx = float(arr.min()), float(arr.max())
        if mx <= mn: return img
        return Image.fromarray(
            ((arr.astype(np.float64) - mn) * (255.0 / (mx - mn)))
            .clip(0, 255).astype(np.uint8), mode=img.mode)
    # RGB / RGBA: stretch each color channel; keep alpha untouched.
    n_color = 3 if arr.shape[2] >= 3 else arr.shape[2]
    for c in range(n_color):
        ch = arr[..., c].astype(np.float64)
        mn, mx = float(ch.min()), float(ch.max())
        out[..., c] = (((ch - mn) * (255.0 / (mx - mn))).clip(0, 255)
                       if mx > mn else ch).astype(np.uint8)
    if arr.shape[2] > n_color:
        out[..., n_color:] = arr[..., n_color:]
    return Image.fromarray(out, mode=img.mode)


def adjust(img: Image.Image,
           brightness: float = 1.0,
           contrast: float = 1.0,
           saturation: float = 1.0,
           gamma: float = 1.0,
           autoscale: bool = False) -> Image.Image:
    """Apply the full adjustment chain. Skips no-op stages.

    `autoscale=True` applies a per-frame min/max linear stretch BEFORE
    the multiplicative brightness/contrast — this is what makes a
    16-bit microscope TIFF (or any low-contrast 8-bit photo) actually
    display its content. The brightness/contrast/saturation/gamma
    sliders then act on the stretched image."""
    out = _coerce_to_blendable(img, autoscale=autoscale)
    if autoscale and out.mode in _SAFE_MODES and img.mode in _SAFE_MODES:
        # `_coerce_to_blendable` already autoscaled wide-dynamic input,
        # so only stretch when the source was already 8-bit. Avoids
        # double-stretching a 16-bit image.
        out = _stretch_8bit(out)
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


def pil_to_qimage(img: Image.Image) -> "QImage":
    """Convert a PIL image to a QImage with no shared buffers (`.copy()`)."""
    # Qt imported here so `adjust()` stays usable without PyQt6 (web interface).
    from PyQt6.QtGui import QImage
    # 16-bit / 32-bit-float modes can't be byte-copied straight to QImage —
    # autoscale to 8-bit `L` first (preserves dynamic range for scientific
    # imaging — see `_autoscale_to_8bit`).
    if img.mode in _WIDE_DYNAMIC_MODES:
        img = _autoscale_to_8bit(img)
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
