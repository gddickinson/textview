"""python_envs: discovery + conda parse helper + Runner interpreter override."""
import json
import pytest
from src.python_envs import (
    PythonEnv, parse_conda_envs_json, discover_system, discover_all,
)
from src.runner import Runner


def test_pythonenv_display_format():
    e = PythonEnv(name="base", path="/opt/x/bin/python", source="conda")
    assert e.display() == "base  (/opt/x/bin/python)"


def test_parse_conda_envs_json_basic():
    blob = json.dumps({
        "envs": ["/Users/x/miniconda3", "/Users/x/miniconda3/envs/data"],
        "root_prefix": "/Users/x/miniconda3",
    })
    out = parse_conda_envs_json(blob)
    assert len(out) == 2
    assert out[0].name == "base"
    assert out[1].name == "data"
    assert all(e.source == "conda" for e in out)


def test_parse_conda_envs_json_malformed_returns_empty():
    assert parse_conda_envs_json("not json {[") == []
    assert parse_conda_envs_json('{"envs": null}') == []


def test_discover_system_includes_python3(qapp):
    """python3 should be on PATH in any environment that runs this test."""
    out = discover_system()
    assert any("python3" in e.path or e.name == "python3" for e in out)


def test_discover_all_dedupes_by_path(qapp):
    """If a conda or pyenv discovery returns the same interpreter as
    discover_system, the merged list should keep only one entry."""
    out = discover_all()
    paths = [e.path for e in out]
    assert len(paths) == len(set(paths))


def test_runner_set_python_interpreter_updates_mapping(qapp):
    r = Runner()
    assert r.languages["py"] == ["python3", "$FILE"]
    r.set_python_interpreter("/opt/conda/envs/foo/bin/python")
    assert r.languages["py"] == ["/opt/conda/envs/foo/bin/python", "$FILE"]


def test_runner_set_python_interpreter_ignores_empty(qapp):
    r = Runner()
    before = list(r.languages["py"])
    r.set_python_interpreter("")
    assert r.languages["py"] == before
