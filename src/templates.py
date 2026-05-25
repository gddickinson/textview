"""File-creation templates.

A small curated registry of starter files. The user opens
**File → New from template…** (Ctrl+Alt+N) which shows a list +
preview pane; clicking **Create** opens the body as an unsaved tab
(via `MainWindow._open_buffer`) and **Save to file…** writes it to a
chosen path first then opens that.

Templates live as data (no I/O) so the same registry can drive the
dialog and the LLM `create_from_template` tool later.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Template:
    id: str            # stable kebab-case key
    name: str          # display name
    format: str        # FORMAT_MAP value, drives syntax highlighting / view
    extension: str     # default extension (or full filename for build files)
    body: str          # initial content
    category: str = "General"
    description: str = ""


# Note on body content: each template ends with a trailing newline so the
# saved file is well-formed. Bodies kept intentionally minimal — the goal
# is "start here", not "write the whole file for you".

_TEMPLATES: list[Template] = [
    # -- Prose / docs ---------------------------------------------------------
    Template(
        id="markdown-doc", name="Markdown document",
        format="markdown", extension=".md",
        category="Prose / docs",
        description="Plain markdown with a title and one section.",
        body="# Title\n\n## Overview\n\nWrite here.\n",
    ),
    Template(
        id="readme", name="README.md",
        format="markdown", extension="README.md",
        category="Prose / docs",
        description="Standard README skeleton.",
        body=(
            "# Project\n\n"
            "## Overview\n\nOne-paragraph summary of what this is.\n\n"
            "## Install\n\n```\n\n```\n\n"
            "## Usage\n\n```\n\n```\n\n"
            "## License\n\n"
        ),
    ),
    Template(
        id="changelog", name="CHANGELOG.md",
        format="markdown", extension="CHANGELOG.md",
        category="Prose / docs",
        description="Keep-a-Changelog style.",
        body=(
            "# Changelog\n\n"
            "All notable changes to this project will be documented here.\n"
            "Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).\n\n"
            "## [Unreleased]\n\n### Added\n- \n\n### Changed\n- \n\n### Fixed\n- \n"
        ),
    ),
    Template(
        id="latex-article", name="LaTeX article",
        format="latex", extension=".tex",
        category="Prose / docs",
        description="Minimal `article` class document, ready for pdflatex.",
        body=(
            "\\documentclass{article}\n"
            "\\usepackage[T1]{fontenc}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{lmodern}\n\n"
            "\\title{Title}\n\\author{Author}\n\\date{\\today}\n\n"
            "\\begin{document}\n\\maketitle\n\n"
            "Write here.\n\n"
            "\\end{document}\n"
        ),
    ),
    Template(
        id="latex-xelatex", name="LaTeX article (XeLaTeX, system fonts)",
        format="latex", extension=".tex",
        category="Prose / docs",
        description="Uses fontspec — TextView auto-picks xelatex on compile.",
        body=(
            "\\documentclass{article}\n"
            "\\usepackage{fontspec}\n"
            "\\setmainfont{Helvetica Neue}\n\n"
            "\\title{Title}\n\\author{Author}\n\n"
            "\\begin{document}\n\\maketitle\n\nWrite here.\n\\end{document}\n"
        ),
    ),
    Template(
        id="html5", name="HTML5 page",
        format="html", extension=".html",
        category="Prose / docs",
        description="Modern HTML5 boilerplate.",
        body=(
            "<!doctype html>\n<html lang=\"en\">\n<head>\n"
            "  <meta charset=\"utf-8\">\n"
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "  <title>Title</title>\n</head>\n<body>\n  <h1>Title</h1>\n</body>\n</html>\n"
        ),
    ),
    # -- Data -----------------------------------------------------------------
    Template(
        id="json-object", name="JSON object",
        format="json", extension=".json",
        category="Data",
        body='{\n  "name": "value"\n}\n',
    ),
    Template(
        id="yaml-doc", name="YAML document",
        format="yaml", extension=".yaml",
        category="Data",
        body="name: value\nitems:\n  - one\n  - two\n",
    ),
    Template(
        id="toml-doc", name="TOML document",
        format="toml", extension=".toml",
        category="Data",
        body='title = "Example"\n\n[section]\nkey = "value"\n',
    ),
    Template(
        id="csv-table", name="CSV table",
        format="csv", extension=".csv",
        category="Data",
        body="name,age,city\nAlice,30,Boston\nBob,25,Seattle\n",
    ),
    Template(
        id="jsonl", name="JSONL (newline-delimited)",
        format="json", extension=".jsonl",
        category="Data",
        body='{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}\n',
    ),
    # -- Code -----------------------------------------------------------------
    Template(
        id="python-script", name="Python script",
        format="python", extension=".py",
        category="Code",
        body=(
            "#!/usr/bin/env python3\n"
            "\"\"\"Script description.\"\"\"\n\n"
            "def main():\n    pass\n\n\n"
            "if __name__ == \"__main__\":\n    main()\n"
        ),
    ),
    Template(
        id="python-test", name="pytest module",
        format="python", extension="test_thing.py",
        category="Code",
        body=(
            "\"\"\"Tests for <thing>.\"\"\"\n"
            "import pytest\n\n\n"
            "def test_smoke():\n    assert True\n"
        ),
    ),
    Template(
        id="js-script", name="JavaScript module",
        format="javascript", extension=".js",
        category="Code",
        body="export function main() {\n  console.log('hi');\n}\n\nmain();\n",
    ),
    Template(
        id="ts-script", name="TypeScript module",
        format="typescript", extension=".ts",
        category="Code",
        body="export function main(): void {\n  console.log('hi');\n}\n\nmain();\n",
    ),
    Template(
        id="bash-script", name="Bash script",
        format="bash", extension=".sh",
        category="Code",
        body=(
            "#!/usr/bin/env bash\nset -euo pipefail\n\n"
            "main() {\n  echo \"hello\"\n}\n\nmain \"$@\"\n"
        ),
    ),
    Template(
        id="rust-bin", name="Rust binary",
        format="rust", extension=".rs",
        category="Code",
        body="fn main() {\n    println!(\"hello, world\");\n}\n",
    ),
    Template(
        id="go-main", name="Go program",
        format="go", extension=".go",
        category="Code",
        body=(
            "package main\n\nimport \"fmt\"\n\n"
            "func main() {\n\tfmt.Println(\"hello, world\")\n}\n"
        ),
    ),
    # -- DevOps / build -------------------------------------------------------
    Template(
        id="dockerfile", name="Dockerfile",
        format="dockerfile", extension="Dockerfile",
        category="DevOps",
        body=(
            "FROM python:3.12-slim\n\nWORKDIR /app\nCOPY . .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "CMD [\"python\", \"main.py\"]\n"
        ),
    ),
    Template(
        id="gitignore", name=".gitignore (Python)",
        format="ini", extension=".gitignore",
        category="DevOps",
        body=(
            "__pycache__/\n*.py[cod]\n*.egg-info/\n.venv/\nvenv/\n"
            ".env\n.DS_Store\n.pytest_cache/\n.mypy_cache/\nbuild/\ndist/\n"
        ),
    ),
    Template(
        id="github-actions-py", name="GitHub Actions (Python tests)",
        format="yaml", extension=".github/workflows/tests.yml",
        category="DevOps",
        body=(
            "name: tests\n\n"
            "on:\n  push:\n    branches: [main]\n  pull_request:\n\n"
            "jobs:\n  pytest:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n"
            "      - run: pip install -r requirements.txt\n      - run: pytest -q\n"
        ),
    ),
    Template(
        id="editorconfig", name=".editorconfig",
        format="ini", extension=".editorconfig",
        category="DevOps",
        body=(
            "root = true\n\n[*]\nend_of_line = lf\ninsert_final_newline = true\n"
            "charset = utf-8\nindent_style = space\nindent_size = 4\n"
            "trim_trailing_whitespace = true\n\n[*.{js,ts,jsx,tsx,md,yml,yaml}]\nindent_size = 2\n"
        ),
    ),
    # -- Notebooks ------------------------------------------------------------
    Template(
        id="ipynb-blank", name="Jupyter notebook (empty)",
        format="notebook", extension=".ipynb",
        category="Notebooks",
        body=(
            '{\n'
            '  "cells": [\n'
            '    {"cell_type": "markdown", "metadata": {}, "source": ["# Title\\n", "\\n"]},\n'
            '    {"cell_type": "code", "metadata": {}, "execution_count": null, "outputs": [], "source": []}\n'
            '  ],\n'
            '  "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},\n'
            '  "nbformat": 4, "nbformat_minor": 5\n'
            '}\n'
        ),
    ),
]


def list_templates() -> list[Template]:
    return list(_TEMPLATES)


def by_id(template_id: str) -> Template | None:
    for t in _TEMPLATES:
        if t.id == template_id:
            return t
    return None


def categories() -> list[str]:
    seen: list[str] = []
    for t in _TEMPLATES:
        if t.category not in seen:
            seen.append(t.category)
    return seen
