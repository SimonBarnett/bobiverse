"""gh_filer: Fake path for tests; GhCliFiler shells to gh."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gh_filer  # noqa: E402
import intake  # noqa: E402


def test_fake_filer_reexported() -> None:
    assert gh_filer.FakeGitHubFiler is intake.FakeGitHubFiler
    f = gh_filer.FakeGitHubFiler()
    out = f.create_issue("SimonBarnett/bobiverse", "t", "b", ["via-intake"])
    assert out["number"]
    assert "github.com" in out["url"]


def test_gh_cli_draft_pr_falls_back_path() -> None:
    f = gh_filer.GhCliFiler()
    try:
        f.create_draft_pr("SimonBarnett/bobiverse", "t", "b", "branch", [], [])
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "draft PR" in str(exc)
