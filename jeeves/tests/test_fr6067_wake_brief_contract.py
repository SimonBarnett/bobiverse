"""FR #6067: ticket-closure wake brief contract."""
from __future__ import annotations

import sys

import pytest

from repo_layout import REPO

sys.path.insert(0, str(REPO / "jeeves" / "tools" / "monitor"))

import wake_brief as wb  # noqa: E402


EXAMPLE = (
    "closed issue SimonBarnett/bobiverse#6067 Continue waiting work."
)


def test_fr6067_example_matches_contract():
    text = wb.build_wake_brief(
        {
            "repo": "SimonBarnett/bobiverse",
            "number": 6067,
            "kind": "issue",
            "state": "closed",
        }
    )
    assert text == EXAMPLE
    assert "SimonBarnett/bobiverse#6067" in text
    assert "Continue waiting work" in text
    assert text.startswith("closed issue ")


def test_fr6067_optional_title_and_pr_merged():
    text = wb.build_wake_brief(
        {
            "repo": "SimonBarnett/bobiverse",
            "number": 12,
            "kind": "pr",
            "event": "merged",
            "title": "lock invent-harvest",
        }
    )
    assert text.startswith("merged pr SimonBarnett/bobiverse#12")
    assert "lock invent-harvest" in text
    assert "Continue waiting work" in text


def test_fr6067_rejects_missing_id_kind_state():
    base = {
        "repo": "SimonBarnett/bobiverse",
        "number": 1,
        "kind": "issue",
        "state": "closed",
    }
    with pytest.raises(wb.WakeBriefError):
        wb.build_wake_brief({**base, "repo": ""})
    with pytest.raises(wb.WakeBriefError):
        wb.build_wake_brief({**base, "number": ""})
    with pytest.raises(wb.WakeBriefError):
        wb.build_wake_brief({**base, "kind": "ticket"})
    with pytest.raises(wb.WakeBriefError):
        wb.build_wake_brief({**base, "state": "open"})
    src = (REPO / "jeeves" / "tools" / "monitor" / "ticket_closure.py").read_text(
        encoding="utf-8"
    )
    assert "build_wake_brief" in src or "wake_brief" in src
