"""FR #6067: ticket-closure wake brief contract."""
from __future__ import annotations

import json
import sys

import pytest

from repo_layout import REPO

from test_fr6063_ticket_closure_monitor import _fixture, _homes, _run

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
    for bad_repo in ("/", "/repo", "owner/", "bobiverse"):
        with pytest.raises(wb.WakeBriefError):
            wb.build_wake_brief({**base, "repo": bad_repo})
    with pytest.raises(wb.WakeBriefError):
        wb.build_wake_brief({**base, "number": True})
    with pytest.raises(wb.WakeBriefError):
        wb.build_wake_brief({**base, "number": 1.9})


def test_fr6067_ticket_closure_attaches_brief(tmp_path):
    chair, digest = _homes(tmp_path)
    fx = _fixture(tmp_path / "events.json")
    code, payload = _run(chair, digest, {"JEEVES_TICKET_CLOSURE_FIXTURE": str(fx)})
    assert code == 1, payload
    closed = payload.get("closed") or []
    assert len(closed) == 3
    for row in closed:
        brief = row.get("brief") or ""
        assert brief
        assert f"{row['repo']}#{row['number']}" in brief
        assert "Continue waiting work" in brief
        assert wb.build_wake_brief(row) == brief


def test_fr6067_short_repo_resolves_when_focus_unique(tmp_path):
    chair, digest = _homes(tmp_path)
    fx = tmp_path / "short.json"
    fx.write_text(
        json.dumps(
            {
                "closed": [
                    {
                        "kind": "issue",
                        "event": "closed",
                        "repo": "bobiverse",
                        "number": 6067,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    code, payload = _run(chair, digest, {"JEEVES_TICKET_CLOSURE_FIXTURE": str(fx)})
    assert code == 1, payload
    row = (payload.get("closed") or [])[0]
    assert row["repo"] == "SimonBarnett/bobiverse"
    assert "SimonBarnett/bobiverse#6067" in row["brief"]
