# -*- coding: utf-8 -*-
"""FR #9108 / BOB-G3: Digest flag recognition (label + Kind:), no title heuristics."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import gitclaim  # noqa: E402

REPO = "SimonBarnett/bobiverse"


def _fr(num: int, **kw) -> dict:
    row = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "title": f"Digest: batch {num}",
        "body": "",
        "state": "open",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "event": "issues",
        "labels": [],
    }
    row.update(kw)
    return row


def test_fr9108_digest_label_variants():
    assert gitclaim.digest_issue_reason(_fr(1, labels=["digest"]))
    assert gitclaim.digest_issue_reason(_fr(2, labels=["FR-DIGEST"]))
    assert gitclaim.digest_issue_reason(
        _fr(3, labels=[{"name": "Digest"}])
    )
    assert gitclaim.digest_issue_reason(_fr(4, labels="fr-digest, feature-request"))
    assert gitclaim.row_is_digest_issue(_fr(5, labels=["digest"]))


def test_fr9108_kind_body_plain_and_bold():
    assert gitclaim.digest_issue_reason(_fr(6, body="Kind: fr-digest\n"))
    assert gitclaim.digest_issue_reason(_fr(7, body="**Kind:** digest\nMore\n"))
    assert gitclaim.digest_issue_reason(_fr(8, body="`Kind:` FR-DIGEST\n"))


def test_fr9108_title_and_prose_do_not_match():
    assert gitclaim.digest_issue_reason(_fr(9, title="Digest: umbrella")) is None
    assert (
        gitclaim.digest_issue_reason(
            _fr(10, body="This digests the plan Kind of work\n")
        )
        is None
    )
    assert (
        gitclaim.digest_issue_reason(
            _fr(11, body="See Kind: fr-digest inline is prose only\n")
        )
        is None
    )


def test_fr9108_mrb_and_pr_shaped_excluded():
    mrb = _fr(12, labels=["digest"])
    mrb["task"] = "MRB"
    assert gitclaim.digest_issue_reason(mrb) is None
    pr = _fr(13, labels=["fr-digest"], url=f"https://github.com/{REPO}/pull/13")
    pr["event"] = "pull_request"
    assert gitclaim.digest_issue_reason(pr) is None


def test_fr9108_body_for_queue_preserves_kind_past_limit():
    pad = "x" * 520
    body = pad + "\nKind: fr-digest\n"
    out = gitclaim._body_for_queue(body)
    assert "Kind: fr-digest" in out
    assert len(out) < len(body) or "Kind: fr-digest" in out[-40:]


def test_fr9108_fr_row_offerable_keeps_digest_as_real_issue():
    # Digests must remain structurally offerable so purge paths keep the gate row.
    assert gitclaim.fr_row_offerable(_fr(20, labels=["digest"])) is True
    assert gitclaim.fr_row_offerable(_fr(21, body="Kind: digest\n")) is True
    assert gitclaim.digest_issue_reason(_fr(20, labels=["digest"]))


def test_fr9108_list_line_marks_digest():
    line = gitclaim.format_list_line(1, _fr(30, labels=["fr-digest"]))
    assert "[digest]" in line


def test_fr9108_g1_gate_accepts_digest_label_and_kind():
    digest = _fr(40, labels=["digest"], body="Depends-on: (none)\n")
    held = _fr(41, labels=["digest", "hold"])
    kind_only = _fr(42, body="Kind: fr-digest\n")
    child = _fr(50, body="Depends-on: #40\n")
    child_held = _fr(51, body="Depends-on: #41\n")
    child_kind = _fr(52, body="Depends-on: #42\n")
    doc = {
        "unaccepted": [digest, held, kind_only, child, child_held, child_kind],
        "accepted": [],
        "done": [],
    }
    assert gitclaim.row_fr_depends_blocked_reason(child, doc) is None
    why = gitclaim.row_fr_depends_blocked_reason(child_held, doc)
    assert why and "depends-held" in why
    assert gitclaim.row_fr_depends_blocked_reason(child_kind, doc) is None


def test_fr9108_strip_digest_labels_for_pr():
    assert gitclaim.strip_issues_only_digest_labels(
        ["digest", "feature-request", "FR-DIGEST", "via-intake"]
    ) == ["feature-request", "via-intake"]
    assert gitclaim.pr_forbidden_digest_labels(["Digest", "hold"]) == ["digest"]
