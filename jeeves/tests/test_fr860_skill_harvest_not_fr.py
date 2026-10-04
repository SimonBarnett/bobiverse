"""FR #860 / #1682 / #1684: skill harvests are offerable promote jobs; ionos cues stay pinned."""
from __future__ import annotations

import gitclaim


def test_skill_label_is_offerable_fr1682():
    why = gitclaim.issue_skip_fr_reason(
        title="FR852 ionos recycle cues",
        body=(
            "infer_require_machine stamps ionos for recycle/recompose Jeeves "
            "and prune queue.json cues"
        ),
        labels=("via-intake", "skill"),
    )
    assert why is None


def test_row_skip_fr_reason_skill_label_offerable():
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#860",
        "title": "FR852 ionos recycle cues",
        "body": "playbook lesson",
        "labels": ["skill", "via-intake"],
        "line": "FR852 ionos recycle cues",
    }
    assert gitclaim.row_skip_fr_reason(row) is None


def test_offer_focus_top_can_offer_skill_labeled_row(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda home: {"marchhare-35600"})
    monkeypatch.setattr(gitclaim, "ledger_load", lambda home: {})
    monkeypatch.setattr(
        gitclaim,
        "ordered_unaccepted",
        lambda home, rows: sorted(rows, key=gitclaim._sort_key),
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#860",
                    "seq": 1,
                    "ts": "t",
                    "title": "harvest: FR852 ionos recycle cues",
                    "body": "skill harvest body",
                    "labels": ["skill", "via-intake"],
                    "line": "harvest: FR852 ionos recycle cues",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-35600", "#marchhare")
    assert st == "ok" and job is not None and job["id"] == "#860"


def test_skill_does_not_block_repo_uat():
    assert (
        gitclaim.issue_blocks_repo_uat(
            title="harvest: lesson",
            labels=("skill", "via-intake"),
        )
        is False
    )


def test_ionos_recycle_cues_still_stamp_after_skill_harvest():
    """Playbook from #860: recycle/recompose Jeeves / prune queue.json → ionos."""
    assert (
        gitclaim.infer_require_machine(
            title="x",
            body="Recycle/recompose Jeeves on ionos; prune leftover rows from queue.json.",
        )
        == "ionos"
    )
