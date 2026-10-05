"""FR #2480: hard-pin / body-signature skip for agentic_fomprep MRB-home umbrellas."""
from __future__ import annotations

import gitclaim


REPO = "SimonBarnett/agentic_fomprep"


def test_hard_pin_umbrella_ids_skip():
    # FR #2521: #11 is FAIL remediation (offerable), not an evergreen home — omit from pin set.
    for num in (3, 7, 8, 9, 20):
        row = {"repo": REPO, "task": "FR", "id": f"#{num}", "title": "FR: something", "labels": []}
        assert gitclaim.row_skip_fr_reason(row) == "hard_pin_umbrella"
        row2 = dict(row, id=str(num))  # hashless
        assert gitclaim.row_skip_fr_reason(row2) == "hard_pin_umbrella"


def test_fr2521_fomprep_11_not_hard_pinned_while_homes_stay():
    """#11 FAIL remediation must be offerable; #8/#9 evergreen homes stay skipped."""
    row11 = {
        "repo": REPO,
        "task": "FR",
        "id": "#11",
        "title": "MRB FAIL board",
        "labels": ["mrb", "mrb-fail", "feature-request"],
    }
    assert gitclaim.row_skip_fr_reason(row11) is None
    assert ("simonbarnett/agentic_fomprep", "#11") not in gitclaim._SKIP_FR_ISSUE_PINS
    for num in (8, 9):
        row = {"repo": REPO, "task": "FR", "id": f"#{num}", "title": "FR: home", "labels": []}
        assert gitclaim.row_skip_fr_reason(row) == "hard_pin_umbrella"
        assert ("simonbarnett/agentic_fomprep", f"#{num}") in gitclaim._SKIP_FR_ISSUE_PINS


def test_mrb_home_board_body_phrase_skips_without_labels():
    reason = gitclaim.issue_skip_fr_reason(
        title="FR: Priority agent skills catalog in v2",
        body="This issue is the MRB home for that feature request. Opened by the hostile MRB.",
        labels=(),
    )
    assert reason == "mrb_home_board_body"


def test_generic_mrb_home_prose_in_body_does_not_skip():
    # FR #987: real FRs may mention MRB home in prose without being boards.
    reason = gitclaim.issue_skip_fr_reason(
        title="FR: harden offer gates for board skip lag",
        body="See also the MRB home docs; implement the gate.",
        labels=(),
    )
    assert reason is None


def test_resync_drops_hard_pinned_umbrella_without_labels(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#8",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR: git as source",
                    "title": "FR: git as source",
                    "labels": [],  # stale — labels added on GitHub later
                }
            ],
            "accepted": [],
            "done": [],
        },
    )

    def fetch(url: str):
        if "/issues?" in url:
            # GitHub open issues: #8 present but labels omitted (empty) — hard pin still drops
            return [
                {
                    "number": 8,
                    "title": "FR: git as source",
                    "body": "x",
                    "state": "open",
                    "labels": [],
                    "pull_request": None,
                }
            ]
        if "/pulls?" in url:
            return []
        raise AssertionError(url)

    gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch)
    doc = gitclaim._load_queue_unlocked(tmp_path)
    ids = {
        gitclaim._norm_row_id(r.get("id"))
        for r in (doc.get("unaccepted") or [])
        if str(r.get("task") or "").upper() == "FR"
    }
    assert "#8" not in ids
