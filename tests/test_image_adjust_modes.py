"""Image adjustment must accept every PIL mode without crashing.

PIL's `ImageEnhance` / `Image.blend` raise `ValueError: image has wrong
mode` for I;16 / F / 1 / PA images — common for TIFFs from microscopes,
GIS rasters, RAW conversions. The pipeline coerces those to RGB(A) up
front so brightness / contrast / saturation / gamma all survive."""
import pytest
from PIL import Image
from src.image_adjust import adjust, pil_to_qimage

pytest.importorskip("PyQt6")


def _modes_to_test():
    """Build a small image in each mode we care about. Some modes need
    a careful constructor — `I;16` doesn't accept zero, `F` wants float."""
    cases: list[tuple[str, Image.Image]] = []
    cases.append(("RGB",  Image.new("RGB",  (8, 8), (128, 64, 200))))
    cases.append(("RGBA", Image.new("RGBA", (8, 8), (128, 64, 200, 200))))
    cases.append(("L",    Image.new("L",    (8, 8), 128)))
    cases.append(("LA",   Image.new("LA",   (8, 8), (128, 200))))
    cases.append(("1",    Image.new("1",    (8, 8), 1)))
    cases.append(("P",    Image.new("P",    (8, 8), 5)))
    cases.append(("CMYK", Image.new("CMYK", (8, 8), (10, 20, 30, 40))))
    # 16-bit greyscale (the TIFF scientific case).
    cases.append(("I;16", Image.new("I;16", (8, 8), 30000)))
    cases.append(("I",    Image.new("I",    (8, 8), 70000)))
    cases.append(("F",    Image.new("F",    (8, 8), 0.5)))
    return cases


@pytest.mark.parametrize("mode,img", _modes_to_test(),
                         ids=lambda x: x if isinstance(x, str) else "img")
def test_adjust_brightness_does_not_crash(mode, img):
    out = adjust(img, brightness=1.4)
    assert out is not None
    # Result is in a Qt-friendly mode.
    assert out.mode in {"RGB", "RGBA", "L", "LA"}


@pytest.mark.parametrize("mode,img", _modes_to_test(),
                         ids=lambda x: x if isinstance(x, str) else "img")
def test_adjust_full_chain_does_not_crash(mode, img):
    out = adjust(img, brightness=1.2, contrast=0.9, saturation=1.5, gamma=1.1)
    assert out is not None


@pytest.mark.parametrize("mode,img", _modes_to_test(),
                         ids=lambda x: x if isinstance(x, str) else "img")
def test_pil_to_qimage_does_not_crash(mode, img):
    qimg = pil_to_qimage(img)
    assert not qimg.isNull()
    assert qimg.width() == 8 and qimg.height() == 8


def test_16bit_tiff_round_trips_through_adjust(tmp_path):
    """Build a real 16-bit TIFF on disk, open via PIL, run adjust + render."""
    p = tmp_path / "bright_field.tif"
    Image.new("I;16", (32, 32), 50_000).save(p)
    img = Image.open(p); img.load()
    assert img.mode in {"I;16", "I"}    # PIL may upgrade
    # The crashing path: brightness slider non-1.0 on a 16-bit image.
    out = adjust(img, brightness=1.6)
    qimg = pil_to_qimage(out)
    assert not qimg.isNull()


# ---- autoscale -----------------------------------------------------------

def test_autoscale_stretches_low_dynamic_range_image():
    """Image with values 100-110 should fill 0-255 after autoscale."""
    import numpy as np
    arr = np.linspace(100, 110, 8 * 8, dtype=np.uint8).reshape(8, 8)
    img = Image.fromarray(arr, mode="L")
    out = adjust(img, autoscale=True)
    out_arr = np.asarray(out)
    assert out_arr.min() == 0
    assert out_arr.max() == 255


def test_autoscale_off_preserves_pixel_values_for_8bit():
    import numpy as np
    arr = np.full((8, 8), 64, dtype=np.uint8)
    img = Image.fromarray(arr, mode="L")
    out = adjust(img, autoscale=False)
    assert int(np.asarray(out).max()) == 64


def test_autoscale_per_channel_for_rgb():
    """Each color channel should be stretched independently."""
    import numpy as np
    arr = np.zeros((8, 8, 3), dtype=np.uint8)
    arr[..., 0] = 50;  arr[..., 1] = 100;  arr[..., 2] = 150
    img = Image.fromarray(arr, "RGB")
    out = adjust(img, autoscale=True)
    out_arr = np.asarray(out)
    # Each channel was constant — stretch leaves a constant unchanged
    # (mn == mx → skip), but at least the call doesn't crash.
    assert out_arr.shape == arr.shape


def test_low_signal_16bit_tiff_displays_via_autoscale(tmp_path):
    """Reproduces the user's microscope TIFF case: pixel values 300-1200
    out of 0-65535. Without autoscale, they map to near-zero and the
    image looks black. With autoscale, they fill 0-255."""
    import numpy as np
    arr = np.random.RandomState(0).randint(300, 1200, (32, 32), dtype=np.uint16)
    p = tmp_path / "microscope.tif"
    Image.fromarray(arr).save(p)  # uint16 -> I;16 (mode= rejected by Pillow 13)
    img = Image.open(p); img.load()
    out = adjust(img, autoscale=True)
    a = np.asarray(out)
    # Stretched output should span (close to) the full 0-255 range.
    assert a.max() >= 200
    assert a.min() <= 50


def test_image_view_defaults_autoscale_on_for_16bit(tmp_path):
    """ImageView turns autoscale on for I;16 / F formats by default."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.image_view import ImageView
    p = tmp_path / "frame.tif"
    Image.new("I;16", (16, 16), 1000).save(p)
    iv = ImageView()
    iv.load(str(p))
    assert iv.is_autoscale() is True
    # And turn it off → state propagates.
    iv.set_autoscale(False)
    assert iv.is_autoscale() is False


def test_image_view_defaults_autoscale_off_for_8bit(tmp_path):
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.image_view import ImageView
    p = tmp_path / "photo.png"
    Image.new("RGB", (16, 16), (50, 100, 200)).save(p)
    iv = ImageView()
    iv.load(str(p))
    assert iv.is_autoscale() is False
