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
    row = {
        "repo": "SimonBarnett/agentic_fomprep",
        "task": "FR",
        "id": "#56",
        "title": "FR: WP0 live §15 on ce-priority-dev",
        "body": "PRIORITY_WP0_INSTANCE=ce-priority-dev",
        "line": "WP0 live",
        "labels": ["feature-request"],
        # intentionally no require_machine stamp
    }
    assert gitclaim.row_machine_mismatch(row, "marchhare-35600")
    assert not gitclaim.row_machine_mismatch(row, "ce-priority-dev1-1")


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
    _digest(home, {"marchhare": [35600], "ce-priority-dev1": [1], "ionos": [1]})
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
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, why = gitclaim.assign_row(
        home, "marchhare-35600", "SimonBarnett/agentic_fomprep", "FR", "#56"
    )
    assert st == "refused"
    assert "machine" in str(why).lower() or "pinned" in str(why).lower()
    st2, job = gitclaim.assign_row(
        home, "ce-priority-dev1-1", "SimonBarnett/agentic_fomprep", "FR", "#56"
    )
    assert st2 == "ok" and job["id"] == "#56"
