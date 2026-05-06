"""Multimodal chat: image encoding, content-block construction, OpenAI translation."""
import base64
import pytest

from src.chat_attachments import (
    encode_image, build_user_content, to_openai_content,
    transcript_html_for_content,
)


def _make_png(tmp_path):
    """Tiny valid 1x1 transparent PNG bytes."""
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDAT"
        b"\x08\x99c\xfc\xff\xff?\x03\x00\x05\xfe\x02\xfe\xa3\xb4\xfd\xa6"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / "tiny.png"; p.write_bytes(png_bytes)
    return p


def test_encode_image_returns_anthropic_block(tmp_path):
    p = _make_png(tmp_path)
    block = encode_image(str(p))
    assert block["type"] == "image"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "image/png"
    # Round-trip the base64 to confirm the bytes are intact.
    decoded = base64.standard_b64decode(block["source"]["data"])
    assert decoded == p.read_bytes()


def test_encode_image_rejects_unsupported_extension(tmp_path):
    p = tmp_path / "x.txt"; p.write_text("not an image")
    with pytest.raises(ValueError):
        encode_image(str(p))


def test_encode_image_missing_file_raises(tmp_path):
    with pytest.raises(ValueError):
        encode_image(str(tmp_path / "no-such-file.png"))


def test_build_user_content_no_attachments_returns_string():
    assert build_user_content("hello", []) == "hello"
    assert build_user_content("hello", None) == "hello"


def test_build_user_content_with_image_returns_block_list(tmp_path):
    p = _make_png(tmp_path)
    out = build_user_content("describe this", [str(p)])
    assert isinstance(out, list)
    assert out[0] == {"type": "text", "text": "describe this"}
    assert out[1]["type"] == "image"


def test_build_user_content_image_only(tmp_path):
    p = _make_png(tmp_path)
    out = build_user_content("", [str(p)])
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0]["type"] == "image"


def test_to_openai_content_translates_image_blocks(tmp_path):
    p = _make_png(tmp_path)
    anth = build_user_content("describe", [str(p)])
    oai = to_openai_content(anth)
    assert oai[0] == {"type": "text", "text": "describe"}
    assert oai[1]["type"] == "image_url"
    url = oai[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


def test_to_openai_content_passes_strings_through():
    assert to_openai_content("hello") == "hello"


def test_transcript_html_for_string_escapes():
    html = transcript_html_for_content("<script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_transcript_html_for_blocks_includes_text_and_img(tmp_path):
    p = _make_png(tmp_path)
    blocks = build_user_content("hi", [str(p)])
    html = transcript_html_for_content(blocks)
    assert "hi" in html
    assert '<img src="data:image/png;base64,' in html
