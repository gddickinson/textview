"""Coverage for language extensions: format detection + Pygments resolution.

Each entry asserts:
1. `detect_format(name)` returns the expected format string.
2. `get_lexer_by_name(format)` succeeds (the renderer relies on this).
"""
import pytest
from src.file_loader import detect_format, FORMAT_MAP


# -- (filename, expected_format) ------------------------------------------

CASES = [
    # R
    ("script.r", "r"), ("script.R", "r"),
    ("doc.Rmd", "markdown"), ("doc.rmd", "markdown"),
    # Julia / Lua / Perl / Haskell / OCaml
    ("a.jl", "julia"), ("a.lua", "lua"),
    ("a.pl", "perl"), ("Module.pm", "perl"),
    ("a.hs", "haskell"), ("a.lhs", "haskell"),
    ("a.ml", "ocaml"), ("a.mli", "ocaml"),
    # Elixir / Erlang
    ("a.ex", "elixir"), ("a.exs", "elixir"),
    ("a.erl", "erlang"),
    # JVM family
    ("a.scala", "scala"), ("a.sc", "scala"),
    ("a.groovy", "groovy"), ("build.gradle", "groovy"),
    ("a.clj", "clojure"), ("a.cljs", "clojure"),
    ("a.edn", "clojure"),
    ("a.kts", "kotlin"),
    # .NET
    ("a.cs", "csharp"), ("a.csx", "csharp"),
    ("a.fs", "fsharp"), ("a.fsx", "fsharp"), ("a.fsi", "fsharp"),
    ("a.vb", "vbnet"),
    # Systems-y
    ("a.nim", "nim"), ("a.zig", "zig"),
    ("a.d", "d"), ("a.cr", "crystal"),
    ("a.vala", "vala"), ("a.dart", "dart"),
    ("a.ps1", "powershell"), ("Module.psm1", "powershell"),
    # Hardware / embedded
    ("sketch.ino", "cpp"),                          # Arduino
    ("art.pde", "java"),                            # Processing
    ("Token.sol", "solidity"),
    ("a.v", "verilog"), ("a.sv", "verilog"),
    ("a.vhd", "vhdl"), ("a.vhdl", "vhdl"),
    # Shaders
    ("shader.glsl", "glsl"), ("a.vert", "glsl"), ("a.frag", "glsl"),
    ("post.hlsl", "hlsl"),
    # Assembly
    ("boot.asm", "nasm"), ("startup.s", "gas"),
    # Fortran
    ("solver.f90", "fortran"), ("legacy.f", "fortran"),
    # Build / config files (by name)
    ("Dockerfile", "dockerfile"), ("dockerfile", "dockerfile"),
    ("Containerfile", "dockerfile"),
    ("Makefile", "make"), ("makefile", "make"),
    ("GNUmakefile", "make"),
    ("CMakeLists.txt", "cmake"),
    ("Justfile", "make"),
    ("Rakefile", "ruby"), ("Gemfile", "ruby"),
    # Build by extension
    ("build.cmake", "cmake"), ("rules.mk", "make"),
    # LaTeX
    ("paper.tex", "latex"), ("article.latex", "latex"), ("doc.ltx", "latex"),
]


@pytest.mark.parametrize("name,fmt", CASES)
def test_detect_format(name, fmt):
    assert detect_format(name) == fmt, f"{name} → {detect_format(name)!r}"


def test_pygments_can_resolve_every_format():
    """Every format we emit must round-trip through Pygments."""
    from pygments.lexers import get_lexer_by_name
    formats = set(FORMAT_MAP.values())
    # Non-code formats handled elsewhere (no lexer needed).
    skip = {"image", "video", "audio", "notebook",
            "pdf", "docx", "rtf", "epub", "odt",
            "plain", "csv", "xlsx", "sqlite",     # extracted to CSV
            "mat", "parquet", "hdf5",             # also extracted to CSV
            "archive", "cert", "blend",           # rendered as markdown
            "font",                               # rendered as HTML
            "mesh"}                               # dedicated 3D view
    for fmt in formats - skip:
        try: get_lexer_by_name(fmt)
        except Exception as e: pytest.fail(f"no Pygments lexer for {fmt!r}: {e}")


def test_supported_extensions_includes_new_ones():
    from src.file_loader import supported_extensions
    exts = supported_extensions()
    for must in (".r", ".jl", ".lua", ".cs", ".ino", ".pde", ".sol",
                 ".asm", ".f90", ".tex", ".latex", ".ltx"):
        assert must in exts, f"{must} missing from supported_extensions()"


def test_runner_languages_includes_new_ones():
    from src.runner import DEFAULT_LANGUAGES
    for lang in ("r", "jl", "hs", "ml", "csx", "fsx", "nim", "zig",
                 "dart", "cr", "d", "kts", "c", "cpp", "f90"):
        assert lang in DEFAULT_LANGUAGES, f"{lang} missing from runner"
