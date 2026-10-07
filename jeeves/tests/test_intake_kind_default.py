"""intake: missing/empty kind defaults to issue; bobiverse allowlisted."""

from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
sys.path.insert(0, str(ROOT / "scripts"))

import intake  # noqa: E402


def _base(**over):
    p = {
        "repo": "SimonBarnett/bobiverse",
        "title": "test title",
        "body": "body",
    }
    p.update(over)
    return p


def test_missing_kind_defaults_to_issue():
    err, norm = intake.validate_payload(_base())
    assert err is None
    assert norm["kind"] == "issue"


def test_empty_kind_defaults_to_issue():
    err, norm = intake.validate_payload(_base(kind=""))
    assert err is None
    assert norm["kind"] == "issue"


def test_whitespace_kind_defaults_to_issue():
    err, norm = intake.validate_payload(_base(kind="  "))
    assert err is None
    assert norm["kind"] == "issue"


def test_explicit_fr_kept():
    err, norm = intake.validate_payload(_base(kind="fr"))
    assert err is None
    assert norm["kind"] == "fr"


def test_bobiverse_repo_allowed():
    assert "SimonBarnett/bobiverse" in intake.DEFAULT_ALLOW_REPOS
    err, norm = intake.validate_payload(_base(kind="issue"))
    assert err is None
    assert norm["repo"] == "SimonBarnett/bobiverse"


def test_agentic_fomprep_repo_allowed():
    """FR #94: Priority formprep harvests must intake to SimonBarnett/agentic_fomprep."""
    assert "SimonBarnett/agentic_fomprep" in intake.DEFAULT_ALLOW_REPOS
    err, norm = intake.validate_payload(
        _base(repo="SimonBarnett/agentic_fomprep", kind="fr", title="VISION.md")
    )
    assert err is None
    assert norm["repo"] == "SimonBarnett/agentic_fomprep"
    assert norm["kind"] == "fr"


def test_a_search_repo_allowed():
    """FR #3023: Plan product a-search must intake (Flush must not drop)."""
    assert "SimonBarnett/a-search" in intake.DEFAULT_ALLOW_REPOS
    err, norm = intake.validate_payload(
        _base(repo="SimonBarnett/a-search", kind="fr", title="scaffold")
    )
    assert err is None
    assert norm["repo"] == "SimonBarnett/a-search"
    assert norm["kind"] == "fr"


def test_trutex_repo_allowed():
    """FR #3050: private Plan product trutex must intake (visibility not a gate)."""
    assert "SimonBarnett/trutex" in intake.DEFAULT_ALLOW_REPOS
    err, norm = intake.validate_payload(
        _base(repo="SimonBarnett/trutex", kind="fr", title="deposco mapping")
    )
    assert err is None
    assert norm["repo"] == "SimonBarnett/trutex"
    assert norm["kind"] == "fr"


def test_unknown_simonbarnett_repo_allowed():
    """FR #3135: any SimonBarnett/* matching _REPO_RE is allowed (no per-repo churn)."""
    err, norm = intake.validate_payload(_base(repo="SimonBarnett/not-a-fleet-repo"))
    assert err is None
    assert norm["repo"] == "SimonBarnett/not-a-fleet-repo"


def test_repo_not_allowed_is_http_403():
    filer = intake.FakeGitHubFiler()
    rate = intake.RateLimiter(per_min=30)
    home = ROOT / "tests" / "_tmp_intake_home_fr94"
    home.mkdir(parents=True, exist_ok=True)
    result = intake.process_intake(
        home,
        {"repo": "evil/x", "title": "t", "body": "b"},
        filer=filer,
        rate=rate,
        client_ip="127.0.0.1",
    )
    assert result.status == 403
    assert result.body.get("error") == "repo_not_allowed"


def test_bad_kind_still_rejected():
    err, norm = intake.validate_payload(_base(kind="nope"))
    assert err == "bad_kind"
    assert norm == {}


def test_missing_repo_rejected():
    err, norm = intake.validate_payload(_base(repo=""))
    assert err == "missing_repo"
    assert norm == {}


def test_omitted_repo_rejected():
    p = {"title": "t", "body": "b"}
    err, norm = intake.validate_payload(p)
    assert err == "missing_repo"
    assert norm == {}
