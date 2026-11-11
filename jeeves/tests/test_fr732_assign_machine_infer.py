"""FR #732: !assign uses cue inference (row_blocked_for_machine), not only stamped require_machine."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def _digest(home, machines):
    registered_machines.save_registered(home, set(machines))
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {str(w): {"state": "idle"} for w in workers}
    bobreport.save_digest(home, doc)


def test_row_machine_mismatch_infers_wp0_without_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [35600], "ce-priority-dev1": [1], "ionos": [1]})
    # FR #6407: WP0 cues no longer infer a pin - unstamped WP0 is ungated.
    wp0 = {
        "repo": "SimonBarnett/agentic_fomprep",
        "task": "FR",
        "id": "#56",
        "title": "FR: WP0 live §15 on ce-priority-dev",
        "body": "PRIORITY_WP0_INSTANCE=ce-priority-dev",
        "line": "WP0 live",
        "labels": ["feature-request"],
    }
    assert not gitclaim.row_machine_mismatch(wp0, "marchhare-35600")
    assert not gitclaim.row_machine_mismatch(wp0, "ce-priority-dev1-1")
    # FR #4512: bobiverse soft title cues never pin - use needs-ionos label.
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#9001",
        "title": "ops drain",
        "body": "",
        "line": "ops",
        "labels": ["feature-request", "needs-ionos"],
    }
    assert gitclaim.row_require_machine(row) == "ionos"
    assert gitclaim.row_machine_mismatch(row, "marchhare-35600")
    assert not gitclaim.row_machine_mismatch(row, "ionos-1")


def test_machine_colon_label_still_pins(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [5], "ionos": [5]})
    row = {"labels": ["machine:ionos"], "title": "x", "body": "", "line": "x"}
    assert gitclaim.row_require_machine(row) == "ionos"
    assert gitclaim.row_machine_mismatch(row, "marchhare-5")
    assert not gitclaim.row_machine_mismatch(row, "ionos-5")


def test_assign_row_refuses_marchhare_for_unstamped_wp0(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(
        home,
        {"marchhare": [35600], "ce-priority-dev1": [1], "ionos": [1], "flamingo": [1]},
    )
    # FR #6407: unstamped WP0 is ungated - flamingo may take it (keep marchhare free).
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/agentic_fomprep",
                    "task": "FR",
                    "id": "#56",
                    "seq": 1,
                    "ts": "t",
                    "line": "WP0 live",
                    "title": "FR: WP0 live §15 on ce-priority-dev",
                    "body": "PRIORITY_WP0_INSTANCE=ce-priority-dev",
                    "labels": ["feature-request"],
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#9001",
                    "seq": 2,
                    "ts": "t",
                    "line": "ops",
                    "title": "ops drain",
                    "body": "",
                    "labels": ["feature-request", "needs-ionos"],
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    st_wp0, job_wp0 = gitclaim.assign_row(
        home, "flamingo-1", "SimonBarnett/agentic_fomprep", "FR", "#56"
    )
    assert st_wp0 == "ok" and job_wp0["id"] == "#56"
    # Live ionos label still refuses the wrong seat (FR #732).
    st, why = gitclaim.assign_row(
        home, "marchhare-35600", "SimonBarnett/bobiverse", "FR", "#9001"
    )
    assert st == "refused"
    assert "machine" in str(why).lower() or "pinned" in str(why).lower()
    st2, job = gitclaim.assign_row(
        home, "ionos-1", "SimonBarnett/bobiverse", "FR", "#9001"
    )
    assert st2 == "ok" and job["id"] == "#9001"
