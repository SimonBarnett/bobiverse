"""FR #9827: TipForm-restore / online_zero_workers escalate receipts are not FR work.

Class of #9824 / #9378 / #9103: via-intake ops filings for online shops with
workers=[] stay visible on GitHub but must not be offered or !assign'ed.
Real product FRs like #9462 (feature-request) stay offerable.
"""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


ESCALATE_BODY_9824 = (
    "Monitor 2026-11-24T19:37:45Z: live report redqueen online=true workers=[] "
    "running=0 while offerable~67. TipForm-only seat start (#3180/#9462) — "
    "monitor will not Start-BobWorker. Operator: TipForm Agents on redqueen "
    "to restore cap.\n"
)


def test_tipform_restore_title_is_skip_fr():
    why = gitclaim.issue_skip_fr_reason(
        title="redqueen online workers=[] while offerable>0 (TipForm restore)",
        body=ESCALATE_BODY_9824,
        labels=("via-intake",),
        state="open",
    )
    assert why == "tipform_restore_escalate"


def test_online_zero_workers_title_shapes_skip_without_feature_request():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="marchhare online with zero worker seats while offerable>0",
            labels=("via-intake",),
        )
        == "tipform_restore_escalate"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="marchhare online with zero workers (weekly~5%) blocks GATE assign",
            labels=("via-intake",),
        )
        == "tipform_restore_escalate"
    )
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MarchHare idle seats while offerable>0 (TipForm-only start; report-only)",
            body="monitor snapshot, not a product FR",
            labels=("via-intake",),
        )
        == "tipform_restore_escalate"
    )


def test_stall_online_zero_workers_still_stall_receipt():
    # Existing FR #8376 ^stall: path — fingerprint titles stay stall_receipt.
    assert (
        gitclaim.issue_skip_fr_reason(
            title="stall:online-zero-workers:redqueen",
            labels=("via-intake",),
        )
        == "stall_receipt"
    )


def test_product_fr_9462_shape_not_skipped():
    why = gitclaim.issue_skip_fr_reason(
        title=(
            "FR: online_zero_workers + offerable must TipForm-alert and "
            "monitor escalate (marchhare/redqueen)"
        ),
        body=(
            "Product work: TipForm alert + monitor EXIT 1 with fingerprint "
            "stall:online-zero-workers:<machine>."
        ),
        labels=("via-intake", "feature-request"),
        state="open",
    )
    assert why is None


def test_via_intake_body_cues_skip_without_feature_request():
    why = gitclaim.issue_skip_fr_reason(
        title="redqueen shop empty while work waits",
        body=ESCALATE_BODY_9824,
        labels=("via-intake",),
        state="open",
    )
    assert why == "tipform_restore_escalate"


def test_feature_request_blocks_body_only_tipform_skip():
    # Body cues alone must not skip a stamped product FR.
    why = gitclaim.issue_skip_fr_reason(
        title="chair: improve TipForm Agents restore UX",
        body=ESCALATE_BODY_9824,
        labels=("via-intake", "feature-request"),
        state="open",
    )
    assert why is None


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"redqueen", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {
            "nick": "redqueen-6400",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "updated": "2026-11-24T19:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_offer_skips_tipform_restore_escalate(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#9824",
        "seq": 1,
        "title": "redqueen online workers=[] while offerable>0 (TipForm restore)",
        "body": ESCALATE_BODY_9824,
        "labels": ["via-intake"],
        "state": "open",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/9824",
        "event": "issues",
        "line": "FR",
        "ts": "t",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st, job = gitclaim.offer_focus_top(
        home,
        "redqueen-6400",
        "#redqueen",
        issue_open=lambda *_a, **_k: True,
        is_pull=lambda *_a, **_k: False,
        pr_exists=lambda *_a, **_k: False,
    )
    assert st == "empty"
    assert job is None
    doc = gitclaim.load_queue(home)
    assert doc["unaccepted"] == []

def test_assign_refuses_tipform_restore_escalate(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#9824",
        "seq": 1,
        "title": "redqueen online workers=[] while offerable>0 (TipForm restore)",
        "body": ESCALATE_BODY_9824,
        "labels": ["via-intake"],
        "state": "open",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/9824",
        "event": "issues",
        "line": "FR",
        "ts": "t",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st, why = gitclaim.assign_row(
        home,
        "redqueen-6400",
        "SimonBarnett/bobiverse",
        "FR",
        "#9824",
        issue_open=lambda *_a, **_k: True,
        is_pull=lambda *_a, **_k: False,
        pr_exists=lambda *_a, **_k: False,
    )
    assert st == "refused"
    assert "tipform_restore_escalate" in str(why).lower()

