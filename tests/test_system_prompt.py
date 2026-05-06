"""System prompt assembly: overview is inlined, doc names are listed,
the 'don't just list titles' instruction is present."""
from src.llm.system_prompt import app_context_prompt


def test_prompt_inlines_overview_text():
    p = app_context_prompt()
    # Pull a phrase from docs/overview.md that's unlikely to appear elsewhere.
    assert "viewer is a stack widget" in p


def test_prompt_lists_other_doc_names():
    p = app_context_prompt()
    for name in ("INDEX", "agent-api", "file-formats", "notebook", "lsp"):
        assert name in p


def test_prompt_excludes_overview_from_list_to_avoid_redundancy():
    """'overview' itself shouldn't appear in the read_doc(name) list since
    it's already inlined."""
    p = app_context_prompt()
    # The block listing names is in `{...}` braces.
    import re
    m = re.search(r"\{([^}]+)\}", p)
    assert m is not None
    listed = {n.strip() for n in m.group(1).split(",")}
    assert "overview" not in listed


def test_prompt_tells_model_not_to_list_titles():
    p = app_context_prompt()
    assert "DO NOT" in p
    assert "list document titles" in p


def test_prompt_directs_to_agent_api_for_tools():
    p = app_context_prompt()
    assert "agent-api" in p
