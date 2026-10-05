"""gh_filer: Fake path for tests; GhCliFiler shells to gh."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
sys.path.insert(0, str(ROOT / "scripts"))

import gh_filer  # noqa: E402
import intake  # noqa: E402


def test_fake_filer_reexported() -> None:
    assert gh_filer.FakeGitHubFiler is intake.FakeGitHubFiler
    f = gh_filer.FakeGitHubFiler()
    out = f.create_issue("SimonBarnett/bobiverse", "t", "b", ["via-intake"])
    assert out["number"]
    assert "github.com" in out["url"]


def test_gh_cli_draft_pr_is_implemented_method() -> None:
    """FR #2579: create_draft_pr is a real GhCliFiler method (no stub RuntimeError)."""
    f = gh_filer.GhCliFiler()
    assert callable(getattr(f, "create_draft_pr", None))
    src = Path(gh_filer.__file__).read_text(encoding="utf-8")
    assert "draft PR not implemented" not in src
    assert '"draft": True' in src
