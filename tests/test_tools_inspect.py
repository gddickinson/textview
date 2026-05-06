"""LLM tools_inspect: analyze_file, register_format_handler, plugin
creation gate, install_package gate, web_search parser."""
import json
import pytest

from src.llm.tools_inspect import (
    INSPECT_TOOLS_RO, INSPECT_TOOLS_ACTION,
    _analyze_file, _register_format_handler, _list_format_handlers,
    _create_plugin, _install_package,
)


def _by_name(name):
    pool = INSPECT_TOOLS_RO + INSPECT_TOOLS_ACTION
    return next(t for t in pool if t.name == name)


class _FakeSettings:
    def __init__(self, **kw):
        self.agent_can_install = kw.get("agent_can_install", False)
        self.agent_can_create_plugins = kw.get("agent_can_create_plugins", False)


class _FakeWindow:
    def __init__(self, **kw):
        class _SM:
            def __init__(s, settings): s.display = settings
        self.settings_manager = _SM(_FakeSettings(**kw))


# -- analyze_file -----------------------------------------------------------

def test_analyze_file_returns_json(tmp_path):
    p = tmp_path / "x.parquet"; p.write_bytes(b"PAR1\x00\x01\x02\x03")
    out = _analyze_file(_FakeWindow(), path=str(p))
    data = json.loads(out)
    assert data["detected_kind"] == "parquet"
    assert "PAR1" in data["hex_preview"]


def test_analyze_file_missing_file(tmp_path):
    out = _analyze_file(_FakeWindow(), path=str(tmp_path / "nope"))
    assert out.startswith("ERROR")


# -- register_format_handler / list -----------------------------------------

def test_register_format_handler_requires_existing_script(tmp_path, monkeypatch):
    import src.format_handlers as fh
    monkeypatch.setattr(fh, "_registry_path", lambda: tmp_path / "fh.json")
    # no script with that name
    out = _register_format_handler(_FakeWindow(), extension=".pq",
                                   script="not_a_real_script")
    assert "ERROR" in out
    assert "create_script" in out


def test_register_format_handler_writes_when_script_exists(tmp_path, monkeypatch):
    import src.format_handlers as fh
    import src.agent_scripts as ascr
    monkeypatch.setattr(fh, "_registry_path", lambda: tmp_path / "fh.json")
    # Stub agent_scripts.read_script.
    monkeypatch.setattr(ascr, "read_script",
                        lambda name: type("S", (), {"body": "x"})() if name == "show_pq" else None)
    out = _register_format_handler(_FakeWindow(), extension=".pq",
                                   script="show_pq", description="head")
    assert "Registered" in out
    assert fh.lookup(".pq") is not None


def test_list_format_handlers(tmp_path, monkeypatch):
    import src.format_handlers as fh
    monkeypatch.setattr(fh, "_registry_path", lambda: tmp_path / "fh.json")
    fh.register(".pq", "x", description="head")
    out = _list_format_handlers(_FakeWindow())
    assert ".pq" in out
    assert "head" in out


# -- create_plugin gate ----------------------------------------------------

def test_create_plugin_blocked_without_setting(tmp_path, monkeypatch):
    monkeypatch.setattr("src.llm.tools_inspect._plugins_dir",
                        lambda: tmp_path / "plugins")
    out = _create_plugin(_FakeWindow(), name="foo",
                        body="def register(ctx): pass")
    assert "ERROR" in out
    assert "agent_can_create_plugins" in out


def test_create_plugin_writes_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr("src.llm.tools_inspect._plugins_dir",
                        lambda: tmp_path / "plugins")
    w = _FakeWindow(agent_can_create_plugins=True)
    out = _create_plugin(w, name="myplugin",
                        body="def register(ctx): pass",
                        description="my test plugin")
    assert "Created plugin" in out
    target = tmp_path / "plugins" / "myplugin.py"
    assert target.is_file()
    assert "def register(ctx):" in target.read_text()


def test_create_plugin_rejects_missing_register_function(tmp_path, monkeypatch):
    monkeypatch.setattr("src.llm.tools_inspect._plugins_dir",
                        lambda: tmp_path / "plugins")
    w = _FakeWindow(agent_can_create_plugins=True)
    out = _create_plugin(w, name="bad", body="x = 1")
    assert "ERROR" in out
    assert "register(" in out


def test_create_plugin_rejects_bad_name(tmp_path, monkeypatch):
    monkeypatch.setattr("src.llm.tools_inspect._plugins_dir",
                        lambda: tmp_path / "plugins")
    w = _FakeWindow(agent_can_create_plugins=True)
    out = _create_plugin(w, name="../escape",
                        body="def register(ctx): pass")
    assert "ERROR" in out


def test_create_plugin_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr("src.llm.tools_inspect._plugins_dir",
                        lambda: tmp_path / "plugins")
    w = _FakeWindow(agent_can_create_plugins=True)
    _create_plugin(w, name="dupe", body="def register(ctx): pass")
    out = _create_plugin(w, name="dupe", body="def register(ctx): pass")
    assert "already exists" in out


# -- install_package gate --------------------------------------------------

def test_install_package_blocked_without_setting():
    out = _install_package(_FakeWindow(), package="pyarrow", reason="parquet")
    assert "ERROR" in out
    assert "agent_can_install" in out


def test_install_package_rejects_bad_package_name():
    w = _FakeWindow(agent_can_install=True)
    out = _install_package(w, package="../etc/passwd")
    assert "ERROR" in out
    assert "regex" in out


def test_install_package_rejects_shell_meta():
    w = _FakeWindow(agent_can_install=True)
    out = _install_package(w, package="pkg; rm -rf /")
    assert "ERROR" in out


# -- web_search parser ------------------------------------------------------

def test_web_search_parser_extracts_results():
    """Parser unit-test (no network)."""
    from src.web_search import _parse_html
    body = """
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">
        Example <em>title</em>
    </a>
    <a class="result__snippet" href="x">A short snippet</a>
    """
    out = _parse_html(body, n=3)
    assert len(out) == 1
    assert out[0]["url"] == "https://example.com"
    assert "Example title" in out[0]["title"]
    assert "snippet" in out[0]["snippet"].lower()


def test_web_search_handles_passthrough_url():
    from src.web_search import _resolve_redirect
    assert _resolve_redirect("https://example.com/x") == "https://example.com/x"


def test_web_search_resolves_uddg():
    from src.web_search import _resolve_redirect
    assert _resolve_redirect(
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fx"
    ) == "https://example.com/x"


# -- registration -----------------------------------------------------------

def test_inspect_tools_registered():
    from src.llm.tools import READ_ONLY_TOOLS, ACTION_TOOLS
    ro = {t.name for t in READ_ONLY_TOOLS}
    act = {t.name for t in ACTION_TOOLS}
    assert {"analyze_file", "list_format_handlers", "list_plugins",
            "web_search"} <= ro
    assert {"register_format_handler", "unregister_format_handler",
            "create_plugin", "install_package"} <= act
