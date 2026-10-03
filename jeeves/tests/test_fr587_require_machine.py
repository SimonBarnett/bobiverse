"""FR #587: infer require_machine=ce-priority-dev1 for WP0 live; skip other seats."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def test_infer_wp0_live_cues():
    assert (
        gitclaim.infer_require_machine(
            title="FR: WP0 live proof",
            body="PRIORITY_WP0_INSTANCE=ce-priority-dev on AllowedComputer CE-PRIORITY-DEV1",
        )
        == "ce-priority-dev1"
    )
    assert (
        gitclaim.infer_require_machine(
            title="WP0 live §15 proof (shell compile/install on ce-priority-dev)",
            body="",
        )
        == "ce-priority-dev1"
    )
    assert gitclaim.infer_require_machine(title="plain FR", body="no cues") == ""


def test_infer_needs_ionos_label_and_cue():
    assert (
        gitclaim.infer_require_machine(title="x", body="y", labels=("needs-ionos",))
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(title="chair-outbox drain fix", body="")
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="x", body="", labels=("require_machine:ce-priority-dev1",)
        )
        == "ce-priority-dev1"
    )


def test_enqueue_stamps_require_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "ce-priority-dev1"})
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/agentic_fomprep"},
            "issue": {
                "number": 56,
                "title": "FR: WP0 live §15 proof (shell compile/install on ce-priority-dev)",
                "body": "PRIORITY_WP0_INSTANCE=ce-priority-dev",
                "state": "open",
                "labels": [{"name": "feature-request"}],
            },
        },
    )
    assert claim is not None
    assert gitclaim.apply_queue_event(home, claim) in ("added", "updated", "duplicate")
    rows = gitclaim.load_unaccepted(home)
    assert len(rows) == 1
    assert rows[0]["require_machine"] == "ce-priority-dev1"


def test_offer_skips_marchhare_offers_dev1(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(
        home, {"marchhare", "ce-priority-dev1", "ionos"}
    )
    digest = bobreport.empty_digest()
    for mid in ("marchhare", "ce-priority-dev1", "ionos"):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {"1": {"state": "idle"}}
    bobreport.save_digest(home, digest)

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
                    "require_machine": "ce-priority-dev1",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, "ce-priority-dev1-1", "#ce-priority-dev1")
    assert st2 == "ok" and job2["id"] == "#56"


def test_seat_matches_require_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "ce-priority-dev1", "ionos"})
    assert gitclaim.seat_matches_require_machine("ce-priority-dev1-99", "ce-priority-dev1")
    assert not gitclaim.seat_matches_require_machine("marchhare-1", "ce-priority-dev1")
    assert gitclaim.seat_matches_require_machine("ionos-1", "")
