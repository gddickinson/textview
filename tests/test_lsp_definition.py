"""LSP go-to-definition + find-references: result-shape parsing."""
from src.lsp_controller import _first_location, _all_locations, SERVERS, FORMAT_TO_LANG


def test_first_location_single_dict():
    res = {"uri": "file:///x.py",
           "range": {"start": {"line": 5, "character": 4},
                     "end":   {"line": 5, "character": 9}}}
    assert _first_location(res) == ("file:///x.py", 5, 4)


def test_first_location_list_takes_first():
    res = [
        {"uri": "file:///a.py", "range": {"start": {"line": 1, "character": 0}}},
        {"uri": "file:///b.py", "range": {"start": {"line": 9, "character": 9}}},
    ]
    assert _first_location(res) == ("file:///a.py", 1, 0)


def test_first_location_locationlink_shape():
    """LSP also allows LocationLink[] with `targetUri` + `targetSelectionRange`."""
    res = [{
        "targetUri": "file:///c.py",
        "targetSelectionRange": {
            "start": {"line": 12, "character": 6},
            "end":   {"line": 12, "character": 14},
        },
    }]
    assert _first_location(res) == ("file:///c.py", 12, 6)


def test_first_location_null():
    assert _first_location(None) is None


def test_first_location_empty_list():
    assert _first_location([]) is None


def test_first_location_malformed_dict():
    assert _first_location({"uri": "file:///x"}) is None  # no range
    assert _first_location({"range": {"start": {"line": 1}}}) is None  # no uri


def test_first_location_defaults_zero_position():
    res = {"uri": "file:///x", "range": {"start": {}}}
    assert _first_location(res) == ("file:///x", 0, 0)


# ---- find-references --------------------------------------------------------

def test_all_locations_extracts_every_hit():
    res = [
        {"uri": "file:///a.py", "range": {"start": {"line": 1, "character": 0}}},
        {"uri": "file:///b.py", "range": {"start": {"line": 9, "character": 9}}},
        {"uri": "file:///c.py", "range": {"start": {"line": 0, "character": 4}}},
    ]
    out = _all_locations(res)
    assert len(out) == 3
    assert out[0] == ("file:///a.py", 1, 0)
    assert out[2] == ("file:///c.py", 0, 4)


def test_all_locations_handles_locationlink_shape():
    res = [{
        "targetUri": "file:///c.py",
        "targetSelectionRange": {"start": {"line": 5, "character": 2}},
    }]
    assert _all_locations(res) == [("file:///c.py", 5, 2)]


def test_all_locations_skips_malformed_entries():
    res = [
        {"uri": "file:///ok.py", "range": {"start": {"line": 1, "character": 0}}},
        {"uri": "no-range.py"},                     # missing range
        "not a dict",
        {"range": {"start": {"line": 0}}},          # missing uri
    ]
    out = _all_locations(res)
    assert len(out) == 1
    assert out[0][0] == "file:///ok.py"


def test_all_locations_empty_returns_empty():
    assert _all_locations([]) == []


# ---- multi-language SERVERS table -------------------------------------------

def test_servers_includes_python_pyright():
    assert SERVERS["python"][0] == "pyright-langserver"


def test_servers_includes_typescript_javascript_via_tsserver():
    assert SERVERS["typescript"][0] == "typescript-language-server"
    assert SERVERS["javascript"][0] == "typescript-language-server"


def test_servers_includes_go_rust_clangd():
    assert SERVERS["go"][0] == "gopls"
    assert SERVERS["rust"][0] == "rust-analyzer"
    assert SERVERS["c"][0] == "clangd"
    assert SERVERS["cpp"][0] == "clangd"


def test_format_to_lang_covers_each_server():
    """Every language id we register a server for should be reachable from
    a TextView format identifier."""
    reachable = set(FORMAT_TO_LANG.values())
    assert reachable >= set(SERVERS)
