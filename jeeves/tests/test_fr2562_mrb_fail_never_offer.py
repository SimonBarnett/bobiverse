"""FR #2562 / #2677: mrb-fail verdict boards and MRB FAIL: titles are never offerable FRs."""
from __future__ import annotations

import json
from pathlib import Path

import gitclaim


def test_mrb_fail_labels_are_skip_fr():
    assert "mrb-fail" in gitclaim.SKIP_FR_LABELS
    assert "mrb_fail" in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="x", labels=("mrb-fail",)).startswith("label:")
    assert gitclaim.issue_skip_fr_reason(
        title="MRB FAIL board",
        labels=("mrb", "mrb-fail"),
    ).startswith("label:")


def test_mrb_verdict_title_skip_even_without_labels():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB FAIL: formlimited-audit-in-clause 7db4bcc",
            labels=(),
        )
        == "mrb_verdict_title"
    )
    assert (
        gitclaim.issue_skip_fr_reason(title="MRB PASS: nits only", labels=())
        == "mrb_verdict_title"
    )


def test_fomprep11_hard_pinned():
    pins = {(r, i) for r, i in gitclaim._SKIP_FR_ISSUE_PINS}
    assert ("simonbarnett/agentic_fomprep", "#11") in pins
    assert (
        gitclaim.row_skip_fr_reason(
            {
                "repo": "SimonBarnett/agentic_fomprep",
                "id": "#11",
                "title": "MRB FAIL: formlimited",
                "labels": [],
            }
        )
        == "hard_pin_umbrella"
    )


def test_mrb_fail_claim_from_payload_is_none():
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
            "issue": {
                "number": 11,
                "title": "MRB FAIL: formlimited-audit-in-clause 7db4bcc",
                "body": "verdict board",
                "state": "open",
                "labels": [
                    {"name": "mrb"},
                    {"name": "mrb-fail"},
                ],
            },
        },
    )
    assert claim is None


def test_needs_human_global_after_giveup_threshold():
    # FR #3277: with giveup_seats set, only those seats stay blocked at threshold.
    row = {
        "needs_human": True,
        "giveup_count": 2,
        "giveup_seats": "marchhare-111,marchhare-222",
    }
    assert gitclaim.row_needs_human(row, "marchhare-111") is True
    assert gitclaim.row_needs_human(row, "marchhare-333") is False
    assert gitclaim.row_needs_human(row, "ionos-1") is False
    # Bare needs_human (no giveup_seats) remains global at/above threshold.
    bare = {"needs_human": True, "giveup_count": 2}
    assert gitclaim.row_needs_human(bare, "marchhare-333") is True
    # Below threshold with seats: still per-seat
    early = {
        "needs_human": True,
        "giveup_count": 1,
        "giveup_seats": "marchhare-111",
    }
    assert gitclaim.row_needs_human(early, "marchhare-111") is True
    assert gitclaim.row_needs_human(early, "marchhare-333") is False


def test_stale_unaccepted_mrb_fail_pruned_on_resync(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = Path(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/agentic_fomprep",
                    "task": "FR",
                    "id": "#11",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/agentic_fomprep#11",
                    "title": "MRB FAIL: formlimited-audit-in-clause 7db4bcc",
                    "labels": ["mrb", "mrb-fail"],
                    "state": "open",
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2562",
                    "seq": 2,
                    "ts": "t",
                    "line": "FR: keep",
                    "title": "FR: keep real work",
                    "labels": ["feature-request"],
                    "state": "open",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    assert gitclaim.row_skip_fr_reason(
        json.loads(gitclaim.queue_path(home).read_text(encoding="utf-8"))["unaccepted"][0]
    )

    def fetch(url: str):
        if "/issues?" in url and "agentic_fomprep" in url:
            return [
                {
                    "number": 11,
                    "title": "MRB FAIL: formlimited-audit-in-clause 7db4bcc",
                    "body": "verdict",
                    "state": "open",
                    "labels": [{"name": "mrb"}, {"name": "mrb-fail"}],
                    "pull_request": None,
                }
            ]
        if "/issues?" in url:
            return [
                {
                    "number": 2562,
                    "title": "FR: keep real work",
                    "body": "x",
                    "state": "open",
                    "labels": [{"name": "feature-request"}],
                    "pull_request": None,
                }
            ]
        if "/pulls?" in url:
            return []
        raise AssertionError(url)

    gitclaim.resync_from_github(
        home,
        ["SimonBarnett/agentic_fomprep", "SimonBarnett/bobiverse"],
        fetch_json=fetch,
    )
    doc = gitclaim._load_queue_unlocked(home)
    ids = {
        (str(r.get("repo") or "").lower(), gitclaim._norm_row_id(r.get("id")))
        for r in (doc.get("unaccepted") or [])
        if str(r.get("task") or "").upper() == "FR"
    }
    assert ("simonbarnett/agentic_fomprep", "#11") not in ids
    assert ("simonbarnett/bobiverse", "#2562") in ids
    assert gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")[0] == "ok"


def test_closed_done_row_not_desired_or_offered(tmp_path, monkeypatch):
    assert gitclaim.issue_skip_fr_reason(title="anything", labels=("feature-request",), state="closed") == "closed"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = Path(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/agentic_fomprep",
                    "task": "FR",
                    "id": "#11",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR #11",
                    "title": "MRB FAIL: formlimited",
                    "labels": ["mrb", "mrb-fail"],
                    "state": "closed",
                }
            ],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "empty" and job is None
