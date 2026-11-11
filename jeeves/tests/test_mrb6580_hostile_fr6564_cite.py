"""MRB #6580 hostile: FR #6564 cite false BUILD attribution for fr3717."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "bobiverse-build.md"
PIN = ROOT / "jeeves" / "tests" / "test_fr3717_clear_cdkout_rmdir.py"


def test_mrb6580_docs_warn_shared_excerpt_pollution():
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #6564" in docs
    assert "FR #6561" in docs
    assert "solo" in docs.lower()
    assert "traceback" in docs.lower() or "excerpt" in docs.lower()
    assert "do not open product fixes from the shared traceback alone" in docs
    assert not DOCS.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6580_fr3717_pin_isolates_job_worktree_base():
    pin = PIN.read_text(encoding="utf-8")
    assert "BOB_JOB_WORKTREE_BASE" in pin
    assert "monkeypatch.setenv" in pin
    assert "FR #6564" in pin
    assert "test_mrb5604" in pin
    assert "Remove-BobiverseDeepWorktreeDirs" in pin
    assert "test_fr6564_build_docs_cite_solo_pollution" in pin
    assert not PIN.read_bytes().startswith(b"\xef\xbb\xbf")
