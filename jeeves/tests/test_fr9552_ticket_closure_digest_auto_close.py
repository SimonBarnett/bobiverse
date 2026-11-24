"""FR #9552: ticket_closure wires fr-digest auto-close on issue closed webhook."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MONITOR = Path(__file__).resolve().parents[1] / "tools" / "monitor"
if str(MONITOR) not in sys.path:
    sys.path.insert(0, str(MONITOR))

import ticket_closure as tc  # noqa: E402


@pytest.fixture()
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    (digest / "focus.json").write_text(
        json.dumps({"repos": ["SimonBarnett/bobiverse"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    return chair, digest


def test_ingest_issue_closed_calls_auto_close(homes, monkeypatch):
    chair, digest = homes
    calls: list[tuple] = []

    def fake_on_closed(repo, number, body=None, **_kw):
        calls.append((repo, int(number), body))
        return [{"action": "closed", "repo": repo, "number": 9259}]

    monkeypatch.setattr(tc, "_maybe_auto_close_fr_digest", lambda row: fake_on_closed(
        row.get("repo"),
        row.get("number"),
        row.get("body"),
    ))

    payload = {
        "action": "closed",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "issue": {
            "number": 9403,
            "title": "child",
            "body": "Depends-on: #9259\n",
            "closed_at": "2026-11-24T10:40:00Z",
        },
    }
    out = tc.ingest_github_webhook(
        digest,
        "issues",
        payload,
        delivery_id="d1",
        chair_home=chair,
        digest_home=digest,
    )
    assert out.get("accepted") is True
    assert calls and calls[0][0] == "SimonBarnett/bobiverse"
    assert calls[0][1] == 9403
    assert "Depends-on: #9259" in str(calls[0][2] or "")
    assert out.get("fr_digest_auto_close")


def test_ingest_pr_closed_does_not_report_digest_close(homes):
    chair, digest = homes
    payload = {
        "action": "closed",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "pull_request": {
            "number": 9547,
            "merged": True,
            "merged_at": "2026-11-24T10:40:00Z",
            "title": "tip",
        },
    }
    out = tc.ingest_github_webhook(
        digest,
        "pull_request",
        payload,
        delivery_id="d2",
        chair_home=chair,
        digest_home=digest,
    )
    assert out.get("accepted") is True
    # Real helper no-ops for kind=pr; no fr_digest_auto_close key.
    assert not out.get("fr_digest_auto_close")


def test_real_helper_skips_pr_kind():
    assert tc._maybe_auto_close_fr_digest({"kind": "pr", "repo": "a/b", "number": 1}) == []
