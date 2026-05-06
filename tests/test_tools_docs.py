"""LLM doc tools — list / read / search the bundled docs/."""
from src.llm.tools_docs import DOC_TOOLS, _list_docs, _read_doc, _search_docs


def _by_name(name):
    return next(t for t in DOC_TOOLS if t.name == name)


def test_list_docs_returns_index_pages():
    out = _list_docs(window=None)
    assert "INDEX" in out
    assert "file-formats" in out
    assert "agent-api" in out


def test_read_doc_index_has_table_of_contents():
    out = _read_doc(None, name="INDEX")
    assert "TextView documentation" in out
    assert "[file-formats.md]" in out


def test_read_doc_strips_md_extension():
    out = _read_doc(None, name="overview.md")
    assert "Overview" in out


def test_read_doc_unknown_lists_alternatives():
    out = _read_doc(None, name="not-a-real-doc")
    assert "Available:" in out
    assert "INDEX" in out


def test_read_doc_blank_name_errors():
    assert _read_doc(None, name="").startswith("ERROR")


def test_search_docs_finds_keyword():
    out = _search_docs(None, query="ipykernel")
    assert ":" in out  # path:line: snippet shape
    # Should match either troubleshooting or notebook docs.
    assert "troubleshooting" in out or "notebook" in out


def test_search_docs_blank_errors():
    assert _search_docs(None, query="").startswith("ERROR")


def test_search_docs_no_match_returns_message():
    out = _search_docs(None, query="zzzzzznothingmatchesthis")
    assert "no matches" in out


def test_doc_tools_are_registered_in_read_only_set():
    """The chat panel pulls READ_ONLY_TOOLS — DOC_TOOLS must be in there
    or the agent won't see them."""
    from src.llm.tools import READ_ONLY_TOOLS
    names = {t.name for t in READ_ONLY_TOOLS}
    assert {"list_docs", "read_doc", "search_docs"} <= names


def test_each_doc_tool_has_callable_with_correct_signature():
    """Tool.call must accept (window, **kwargs) — the chat dispatcher
    invokes them that way. Smoke-check no TypeError on a real call."""
    for tool in DOC_TOOLS:
        # list_docs takes only window
        if tool.name == "list_docs":
            tool.call(window=None)
        elif tool.name == "read_doc":
            tool.call(window=None, name="INDEX")
        elif tool.name == "search_docs":
            tool.call(window=None, query="docs")
