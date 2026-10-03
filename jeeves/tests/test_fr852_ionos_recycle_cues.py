"""FR #852: stamp require_machine=ionos for Jeeves recycle/recompose / queue prune cues."""
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


def test_infer_recycle_recompose_jeeves():
    assert (
        gitclaim.infer_require_machine(
            title="Chair still offered per-PR UAT",
            body="Recycle/recompose Jeeves on ionos so gitclaim gates are live",
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="recompose ircJeeves after gate merge",
            body="",
        )
        == "ionos"
    )


def test_infer_prune_queue_json_on_ionos():
    assert (
        gitclaim.infer_require_machine(
            title="x",
            body="prune any leftover non-#0 UAT rows from queue.json on ionos",
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="prune queue.json leftover UAT",
            body="Fix: prune queue.json on ionos",
        )
        == "ionos"
    )


def test_infer_ircjeeves_recycle():
    assert (
        gitclaim.infer_require_machine(
            title="x",
            body="install tree not recomposed / ircJeeves not recycled yet?",
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="ircJeeves recycle needed",
            body="",
        )
        == "ionos"
    )


def test_fr848_body_stamps_ionos():
    """Real FR #848 body that was wrongly offered to marchhare."""
    body = (
        "Recycle/recompose Jeeves on ionos so gitclaim gates from #828+#844 are live; "
        "prune any leftover non-#0 UAT rows from queue.json."
    )
    assert (
        gitclaim.infer_require_machine(
            title="Chair still offered per-PR UAT on mrb-fix #835 after #828/#844",
            body=body,
        )
        == "ionos"
    )


def test_plain_bob_recycle_does_not_pin_ionos():
    assert gitclaim.infer_require_machine(title="recycle bob ear", body="") == ""
    assert (
        gitclaim.infer_require_machine(
            title="Restart-BobEar after hotpatch",
            body="recycle the tray companion",
        )
        == ""
    )


def test_offer_skips_marchhare_for_unstamped_jeeves_recycle(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"marchhare": [35600], "ionos": [1]})
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#848",
                    "seq": 1,
                    "ts": "t",
                    "line": "recycle jeeves",
                    "title": "Chair still offered per-PR UAT on mrb-fix #835",
                    "body": (
                        "Recycle/recompose Jeeves on ionos; prune leftover "
                        "non-#0 UAT rows from queue.json."
                    ),
                    "labels": ["via-intake"],
                    # intentionally no require_machine stamp
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, _job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, "ionos-1", "#ionos")
    assert st2 == "ok" and job2["id"] == "#848"


def test_enqueue_stamps_ionos_from_recycle_jeeves(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "ionos"})
    claim = gitclaim.claim_from_payload(
        "issues",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "issue": {
                "number": 848,
                "title": "Chair still offered per-PR UAT after gate merge",
                "body": "Fix: Recycle/recompose Jeeves on ionos; prune queue.json.",
                "state": "open",
                "labels": [{"name": "via-intake"}],
            },
        },
    )
    assert claim is not None
    assert gitclaim.apply_queue_event(home, claim) in ("added", "updated", "duplicate")
    rows = gitclaim.load_unaccepted(home)
    assert len(rows) == 1
    assert rows[0]["require_machine"] == "ionos"
