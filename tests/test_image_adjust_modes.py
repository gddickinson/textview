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
