"""MRB #7096 hostile pin: FR #7094 tests-only stays in chair help and skip_blockers."""
from __future__ import annotations

from repo_layout import ROOT

import bobiverse_build as bb


def test_mrb7096_chair_help_lists_tests_only():
    t = (ROOT / "common" / "scripts" / "chair_commands.py").read_text(encoding="utf-8")
    assert "--tests-only" in t
    assert "tests-only" in t


def test_mrb7096_file_blocker_skip_when_tests_only():
    filer = bb.FakeGitHubFiler()
    filer.skip_blockers = True
    out = bb.file_blocker_or_dedupe(
        filer,
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        ref="HEAD",
        failure=bb.classify_step_failure("release"),
        log_excerpt="x",
    )
    assert out.get("action") == "skipped"
    assert not any(filer.issues.values())
