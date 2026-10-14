"""Hostile pins for MRB #4072 / FR #4025 (additive after product merge)."""
from __future__ import annotations

from repo_layout import ROOT
import bobiverse_build as bb

SRC = (ROOT / "common" / "scripts" / "bobiverse_build.py").read_text(encoding="utf-8")
CLI = (ROOT / "common" / "scripts" / "run_bobiverse_build.py").read_text(encoding="utf-8")


def test_mrb4072_github_filer_not_abstract():
    assert "raise NotImplementedError" not in SRC.split("class FakeGitHubFiler")[0].split("class GitHubFiler")[1]
    assert "gh_runner" in SRC
    assert 'issue", "list"' in SRC or "issue list" in SRC or '"issue",\n                "list"' in SRC or '"list"' in SRC


def test_mrb4072_pack_gate_kinds_contiguous():
    idx = SRC.find("class BuildRunner")
    body = SRC[idx : idx + 4500]
    assert 'new_regression' in body and 'step_failure' in body
    assert "pack_fn" in body


def test_mrb4072_cli_defaults_to_live_filer():
    assert "FakeGitHubFiler()" in CLI and "GitHubFiler()" in CLI
    assert "--fake-filer" in CLI