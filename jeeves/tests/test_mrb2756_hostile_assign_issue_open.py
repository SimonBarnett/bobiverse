"""MRB #2756 hostile: !assign chair fixture deterministic vs FR #2340 issue_open."""
from __future__ import annotations

import ast
from pathlib import Path

TEST_FILE = Path(__file__).resolve().parent / "test_chair_commands_020.py"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2756_chair_fixture_stamps_open_issue_fr_row():
    text = _utf8_no_bom(TEST_FILE)
    # Fixture FR row must look like an open issue offline (FR #2340 structural gates).
    assert '"state": "open"' in text or "'state': 'open'" in text
    assert '"event": "issues"' in text or "'event': 'issues'" in text
    assert "https://github.com/o/a/issues/1" in text
    assert "https://github.com/o/b/pull/2" in text


def test_mrb2756_happy_path_stubs_live_github_checkers():
    text = _utf8_no_bom(TEST_FILE)
    idx = text.index("def test_assign_owner_and_ear_post_normal_line_as_jeeves")
    window = text[idx : idx + 900]
    assert "github_is_pull_checker" in window
    assert "github_issue_open_checker" in window
    assert "github_pr_exists_checker" in window
    assert "monkeypatch.setattr" in window


def test_mrb2756_refuse_tests_cover_closed_and_pull():
    text = _utf8_no_bom(TEST_FILE)
    assert "def test_fr2730_assign_refuses_when_issue_open_says_closed" in text
    assert "def test_fr2730_assign_refuses_when_is_pull_true" in text
    tree = ast.parse(text)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert "test_fr2730_assign_refuses_when_issue_open_says_closed" in names
    assert "test_fr2730_assign_refuses_when_is_pull_true" in names
