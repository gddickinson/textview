"""Templates registry + audio format detection."""
from __future__ import annotations

import pytest

from src import templates
from src.file_loader import (
    detect_format, AUDIO_FORMATS, MEDIA_FORMATS, is_audio, is_media,
    is_video, FILENAME_MAP,
)
from pygments.lexers import get_lexer_by_name


# -- templates --------------------------------------------------------------

def test_templates_have_unique_ids():
    ids = [t.id for t in templates.list_templates()]
    assert len(ids) == len(set(ids)), f"duplicate template ids: {ids}"


def test_templates_use_real_formats():
    """Every template's `format` must round-trip through FORMAT_MAP or
    Pygments — otherwise the renderer will fall back to plain."""
    from src.file_loader import FORMAT_MAP
    formats = set(FORMAT_MAP.values())
    # Non-code "renderable" formats handled elsewhere; treat as valid.
    extra = {"notebook", "markdown", "csv", "plain"}
    for t in templates.list_templates():
        if t.format in (formats | extra): continue
        # Otherwise must resolve as a Pygments lexer alias.
        try: get_lexer_by_name(t.format)
        except Exception as e:
            pytest.fail(f"template {t.id!r}: bad format {t.format!r} ({e})")


def test_templates_have_non_empty_bodies():
    for t in templates.list_templates():
        assert t.body, f"empty body for {t.id}"
        # All templates end with a trailing newline so saved files are well-formed.
        assert t.body.endswith("\n"), f"{t.id} body should end with \\n"


def test_by_id_and_categories():
    cats = templates.categories()
    assert "Code" in cats and "Data" in cats and "Prose / docs" in cats
    assert templates.by_id("python-script").extension == ".py"
    assert templates.by_id("nope") is None


# -- audio routing ----------------------------------------------------------

@pytest.mark.parametrize("name", [
    "song.mp3", "track.WAV", "lossless.flac", "podcast.m4a",
    "voice.opus", "stream.aac", "memo.aiff", "tone.mid", "loop.ogg",
])
def test_audio_extensions_detected(name):
    assert detect_format(name) == "audio"
    assert is_audio(name)
    assert is_media(name)
    assert not is_video(name)


def test_video_still_works():
    assert detect_format("clip.mp4") == "video"
    assert is_video("clip.mp4")
    assert is_media("clip.mp4")
    assert not is_audio("clip.mp4")


def test_media_formats_union():
    assert AUDIO_FORMATS <= MEDIA_FORMATS
    assert "video" in MEDIA_FORMATS and "audio" in MEDIA_FORMATS


# -- filename-by-name lookups -----------------------------------------------

@pytest.mark.parametrize("name,fmt", [
    (".gitignore", "ini"),
    (".editorconfig", "ini"),
    (".env", "bash"),
    ("package-lock.json", "json"),
    ("Cargo.lock", "toml"),
    ("poetry.lock", "toml"),
    ("yarn.lock", "yaml"),
])
def test_known_dotfiles_and_lockfiles(name, fmt):
    assert detect_format(name) == fmt
