"""FR #860: skill/harvest intake issues are never FR jobs; ionos recycle cues stay pinned."""
from __future__ import annotations

import gitclaim


def test_skill_label_skips_fr860_shape():
    why = gitclaim.issue_skip_fr_reason(
        title="FR852 ionos recycle cues",
        body=(
            "infer_require_machine stamps ionos for recycle/recompose Jeeves "
            "and prune queue.json cues"
        ),
        labels=("via-intake", "skill"),
    )
    assert why == "label:skill"


def test_row_skip_fr_reason_skill_label():
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#860",
        "title": "FR852 ionos recycle cues",
        "body": "playbook lesson",
        "labels": ["skill", "via-intake"],
        "line": "FR852 ionos recycle cues",
    }
    assert gitclaim.row_skip_fr_reason(row) == "label:skill"


def test_offer_focus_top_skips_skill_labeled_row(tmp_path, monkeypatch):
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
                    "title": "FR852 ionos recycle cues",
                    "body": "skill harvest body",
                    "labels": ["skill", "via-intake"],
                    "line": "FR852 ionos recycle cues",
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#900",
                    "seq": 2,
                    "ts": "t",
                    "title": "FR: real implementable work",
                    "body": "Do the thing.",
                    "labels": ["via-intake", "feature-request"],
                    "line": "real work",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-35600", "#marchhare")
    assert st == "ok" and job is not None and job["id"] == "#900"


def test_ionos_recycle_cues_still_stamp_after_skill_harvest():
    """Playbook from #860: recycle/recompose Jeeves / prune queue.json → ionos."""
    assert (
        gitclaim.infer_require_machine(
            title="x",
            body="Recycle/recompose Jeeves on ionos; prune leftover rows from queue.json.",
        )
        == "ionos"
    )
