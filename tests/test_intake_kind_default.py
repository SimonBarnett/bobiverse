"""intake: missing/empty kind defaults to issue; bobiverse allowlisted."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def test_bad_kind_still_rejected():
    err, norm = intake.validate_payload(_base(kind="nope"))
    assert err == "bad_kind"
    assert norm == {}
