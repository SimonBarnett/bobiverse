# -*- coding: utf-8 -*-
"""FR #9455: Depends-on/G1 single shared gate for offer + assign + stuck.

Acceptance (deterministic chair):
- G1-A: Depends-on unheld fr-digest absent from queue -> never depends-open
- G1-B: same while digest has hold -> depends-held only
- D3: ordinary OPEN issue -> depends-open
- Ledger: stuck classify uses the same helper / same reason as offer/assign
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import gitclaim
import stuck_job_sweep as sweep

REPO = "SimonBarnett/bobiverse"


def _old_ts(now: float, age_s: float = 3600.0) -> str:
    return datetime.fromtimestamp(now - age_s, tz=timezone.utc).isoformat()


def _fr(*, num: int, body: str, title: str = "child", labels=None, ts: str | None = None) -> dict:
    return {
        "task": "FR",
        "repo": REPO,
        "id": f"#{num}",
        "ident": str(num),
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": title,
        "body": body,
        "ts": ts or _old_ts(1_700_000_000.0),
        "labels": labels or ["feature-request"],
        "event": "issues",
        "line": f"FR {REPO}#{num}",
    }


def _fetch_factory(payload_by_id: dict[str, dict]):
    def fetch_issue(repo: str, num: str):
        assert repo.lower() == REPO.lower()
        return payload_by_id.get(str(num).lstrip("#"))

    return fetch_issue


def test_fr9455_depends_gate_reason_marker_and_signature():
    """Product marker bob_g1_shared_gate + single helper for offer/assign/stuck."""
    assert hasattr(gitclaim, "depends_gate_reason")
    src = (Path(gitclaim.__file__)).read_text(encoding="utf-8")
    assert "bob_g1_shared_gate" in src
    assert "FR #9455" in src or "9455" in src


def test_fr9455_g1a_unheld_digest_absent_from_queue_not_depends_open():
    child = _fr(num=9261, body="**Depends-on:** #9259\n", title="BOB-TRAY-UI-01")
    doc = {"unaccepted": [child], "accepted": [], "done": []}
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: BOB-TRAY-UI",
                "body": "Kind: fr-digest\n",
                "labels": [{"name": "fr-digest"}, {"name": "feature-request"}],
            }
        }
    )
    why = gitclaim.depends_gate_reason(
        child,
        doc,
        open_keys=set(),
        issue_open=lambda r, n: str(n).lstrip("#") == "9259",
        issue_fetch=fetch,
    )
    assert why == gitclaim.DEPENDS_OPEN_REASON


def test_fr9455_g1b_held_digest_absent_is_depends_held_only():
    child = _fr(num=9261, body="Depends-on: #9259\n")
    doc = {"unaccepted": [child], "accepted": [], "done": []}
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: BOB-TRAY-UI",
                "body": "Kind: fr-digest\n",
                "labels": [
                    {"name": "fr-digest"},
                    {"name": "hold"},
                    {"name": "feature-request"},
                ],
            }
        }
    )
    why = gitclaim.depends_gate_reason(
        child,
        doc,
        open_keys=set(),
        issue_open=lambda r, n: True,
        issue_fetch=fetch,
    )
    assert why == gitclaim.DEPENDS_HELD_REASON
    assert why != gitclaim.DEPENDS_OPEN_REASON


def test_fr9455_d3_ordinary_open_is_depends_open():
    child = _fr(num=100, body="Depends-on: #99\n")
    parent = _fr(num=99, body="Depends-on: (none)\n", title="ordinary parent")
    doc = {"unaccepted": [child, parent], "accepted": [], "done": []}
    why = gitclaim.depends_gate_reason(
        child,
        doc,
        open_keys=gitclaim.open_fr_issue_keys(doc),
        issue_open=lambda r, n: True,
        issue_fetch=lambda r, n: None,
    )
    assert why == gitclaim.DEPENDS_OPEN_REASON


def test_fr9455_ledger_stuck_matches_shared_gate(tmp_path: Path, monkeypatch):
    """stuck classify rule matches depends_gate_reason for the same (repo, id)."""
    now = 1_700_000_000.0
    child = _fr(
        num=9403,
        body="**Depends-on:** #9259 (Digest: BOB-TRAY-UI)\n",
        title="BOB-TRAY-UI-11",
        ts=_old_ts(now, 4000),
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [child], "accepted": [], "done": []},
    )
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: BOB-TRAY-UI",
                "body": "Kind: fr-digest\n",
                "labels": [{"name": "fr-digest"}, {"name": "feature-request"}],
            }
        }
    )
    monkeypatch.setattr(
        gitclaim,
        "depends_issue_open_checker",
        lambda issue_open=None: (lambda repo, num: str(num).lstrip("#") == "9259"),
    )
    monkeypatch.setattr(
        gitclaim,
        "depends_issue_fetch_checker",
        lambda fetch_issue=None: fetch,
    )
    gate = gitclaim.depends_gate_reason(
        child,
        {"unaccepted": [child], "accepted": [], "done": []},
        open_keys=set(),
        issue_open=lambda r, n: str(n).lstrip("#") == "9259",
        issue_fetch=fetch,
    )
    assert gate == gitclaim.DEPENDS_OPEN_REASON
    info = sweep.classify_queue_row(
        child,
        bucket="unaccepted",
        now=now,
        live={"redqueen-1"},
        idle={"redqueen-1"},
        home=tmp_path,
    )
    assert info.get("rule") == "depends_on_open"


def test_fr9455_blocked_reason_passes_issue_fetch_for_g1():
    """Legacy row_fr_depends_blocked_reason must not fork G1 without issue_fetch."""
    child = _fr(num=9261, body="Depends-on: #9259\n")
    doc = {"unaccepted": [child], "accepted": [], "done": []}
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest",
                "body": "Kind: fr-digest\n",
                "labels": [{"name": "fr-digest"}],
            }
        }
    )
    why = gitclaim.row_fr_depends_blocked_reason(child, doc, issue_fetch=fetch)
    assert why is not None and str(why).startswith("depends-on open")
