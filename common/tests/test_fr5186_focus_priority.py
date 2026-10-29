"""FR #5186: only the approved repositories can have high focus priority."""
from __future__ import annotations

import json

import focus_ignore as fi


def _write_focus(home, payload):
    path = fi._root(home) / fi.FOCUS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_non_high_default_and_external_high_commands(tmp_path):
    assert fi.DEFAULT_PRIORITY > fi.NAMED_PRIORITY["high"]

    fi.handle_focus_cmd(tmp_path, "SimonBarnett/trutex")
    fi.handle_focus_cmd(tmp_path, "high SimonBarnett/ce-priority")
    fi.handle_focus_cmd(tmp_path, "1 SimonBarnett/agentic_fomprep")

    doc = fi.load_focus(tmp_path)
    for repo in (
        "SimonBarnett/trutex",
        "SimonBarnett/ce-priority",
        "SimonBarnett/agentic_fomprep",
    ):
        assert fi.repo_priority(doc, repo) == fi.DEFAULT_PRIORITY

    fi.handle_focus_cmd(tmp_path, "high SimonBarnett/bobiverse")
    fi.handle_focus_cmd(tmp_path, "1 SimonBarnett/a-search")
    doc = fi.load_focus(tmp_path)
    assert fi.repo_priority(doc, "SimonBarnett/bobiverse") == 1
    assert fi.repo_priority(doc, "SimonBarnett/a-search") == 1


def test_loaded_legacy_or_invalid_focus_cannot_make_other_repo_high(tmp_path):
    repo = "SimonBarnett/trutex"
    cases = (
        ({"repos": [repo]}, fi.DEFAULT_PRIORITY),
        ({"repos": {repo: {}}}, fi.DEFAULT_PRIORITY),
        ({"repos": {repo: {"priority": "invalid", "label": "high"}}}, fi.DEFAULT_PRIORITY),
        ({"repos": {repo: {"priority": 1, "label": "high"}}}, fi.DEFAULT_PRIORITY),
        ({"repos": {"SimonBarnett/bobiverse": {"priority": 1}}}, 1),
        ({"repos": {"SimonBarnett/a-search": {"priority": 1}}}, 1),
    )
    for payload, expected in cases:
        _write_focus(tmp_path, payload)
        doc = fi.load_focus(tmp_path)
        assert doc["repos"]
        loaded_repo = next(iter(doc["repos"]))
        assert doc["repos"][loaded_repo]["priority"] == expected


def test_unqualified_repo_cannot_become_high(tmp_path):
    fi.handle_focus_cmd(tmp_path, "high bobiverse")
    doc = fi.load_focus(tmp_path)
    assert fi.repo_priority(doc, "SimonBarnett/bobiverse") == fi.DEFAULT_PRIORITY
