# -*- coding: utf-8 -*-
"""FR #9554: auto require_machine after repeated tipform/tray host-heal GIVEUPs.

Class of #9526: flamingo/redqueen churned holder_bored / TipForm GIVEUPs all night
while product tips were already on main. Chair must pin deterministically to the
named host without stamping needs_human (infra/host console, not human park).
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen


REPO = "SimonBarnett/bobiverse"


def _digest(home: Path, machines: dict) -> None:
    registered_machines.save_registered(home, set(machines))
    doc = bobreport.empty_digest()
    for mid, pids in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{pid}",
                "state": "idle",
                "kind": "grok",
                "start_model": "grok-4",
                "configured_model": "grok-4",
                "updated": "2026-11-24T10:00:00Z",
            }
            for pid in pids
        ]
    bobreport.save_digest(home, doc)


def _host_heal_row(**kw) -> dict:
    r = {
        "task": "FR",
        "repo": REPO,
        "id": "#9526",
        "seq": 1,
        "ts": "2026-11-24T05:00:00Z",
        "line": f"FR {REPO}#9526",
        "url": f"https://github.com/{REPO}/issues/9526",
        "title": "marchhare: still NACK engine.alive stale after #9525 merge (host tray/ear not on tip)",
        "body": (
            "Host: marchhare bob-tray / ear startworker path\n"
            "NACK startworker: nobody logged in with the Bob tray running\n"
            "Interactive TipForm Restart engine needed.\n"
        ),
        "labels": ["feature-request", "via-intake"],
        "state": "open",
        "event": "issues",
    }
    r.update(kw)
    return r


def test_fr9554_classifier_and_infer_machine():
    assert gitclaim.is_host_heal_tipform_reason(
        "nobody logged in with the Bob tray running"
    )
    assert gitclaim.is_host_heal_tipform_reason("engine.alive stale; TipForm Restart")
    assert gitclaim.is_host_heal_tipform_reason("host-heal interactive TipForm")
    assert not gitclaim.is_host_heal_tipform_reason("out of fuel")
    row = _host_heal_row()
    assert gitclaim.row_is_host_heal_tipform(row) is True
    assert gitclaim.infer_host_heal_machine(row, reason="") == "marchhare"
    assert (
        gitclaim.infer_host_heal_machine(
            {"task": "FR", "repo": REPO, "id": "#1", "title": "x", "body": "", "labels": []},
            reason="require_machine=marchhare (interactive TipForm)",
        )
        == "marchhare"
    )


def test_fr9554_stamp_after_two_host_heal_giveups_no_needs_human():
    row = _host_heal_row()
    mid1 = gitclaim.apply_host_heal_require_machine_stamp(
        row, reason="holder_bored", nick="flamingo-1"
    )
    assert mid1 == ""  # first outcome only counts
    assert row.get("require_machine") in (None, "", "any")
    assert not row.get("needs_human")
    mid2 = gitclaim.apply_host_heal_require_machine_stamp(
        row, reason="tray-not-logged-in TipForm", nick="flamingo-2"
    )
    assert mid2 == "marchhare"
    assert row.get("require_machine") == "marchhare"
    assert row.get("require_machine_operator") in (True, "1", 1)
    assert row.get("require_machine_host_heal") in (True, "1", 1)
    assert not row.get("needs_human")
    assert "require_machine: marchhare" in str(row.get("body") or "")
    labs = [str(x).lower() for x in (row.get("labels") or [])]
    assert any(x == "needs-marchhare" or x.endswith("needs-marchhare") for x in labs)


def test_fr9554_product_giveup_count_diverts_from_needs_human():
    """giveup_count>=2 on tipform class stamps pin, never needs_human."""
    row = _host_heal_row()
    row["giveup_count"] = 2
    mid = gitclaim.apply_host_heal_require_machine_stamp(
        row, reason="engine.alive stale restart tray", nick="redqueen-1"
    )
    assert mid == "marchhare"
    assert row.get("require_machine") == "marchhare"
    assert not row.get("needs_human")


def test_fr9554_shop_return_job_pins_without_needs_human(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"flamingo": [17068], "marchhare": [1], "redqueen": [668]})
    row = _host_heal_row()
    row["nick"] = "flamingo-17068"
    row["accepted_ts"] = "2026-11-24T05:10:00Z"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [row], "done": [], "workers": {}},
    )
    # Two host-heal class GIVEUPs (second may be infra-soft holder_bored).
    st1, job1 = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="FR",
        ident="#9526",
        reason="interactive TipForm; engine.alive stale",
    )
    assert st1 == "ok", job1
    # Re-accept for second giveup
    doc = gitclaim.load_queue(home)
    u = doc["unaccepted"][0]
    u["nick"] = "redqueen-668"
    u["accepted_ts"] = "2026-11-24T05:20:00Z"
    doc["accepted"] = [u]
    doc["unaccepted"] = []
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    st2, job2 = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="FR",
        ident="#9526",
        reason="holder_bored",
    )
    assert st2 == "ok", job2
    assert job2.get("require_machine") == "marchhare"
    assert not job2.get("needs_human")
    # Stuck classify rule stays require_machine:<id>
    import stuck_job_sweep as sweep

    info = sweep.classify_queue_row(
        job2,
        bucket="unaccepted",
        now=1_700_000_000.0,
        live={"flamingo-17068"},
        idle={"flamingo-17068"},
        home=home,
    )
    assert str(info.get("rule") or "").startswith("require_machine:")


def test_fr9554_ack_from_pin_machine_clears_host_heal_pin(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"marchhare": [99], "flamingo": [1]})
    # Use a non-hard-pinned id so _REQUIRE_MACHINE_ISSUE_PINS #9526 cannot re-stick.
    row = _host_heal_row(id="#9600", url=f"https://github.com/{REPO}/issues/9600")
    row["require_machine"] = "marchhare"
    row["require_machine_operator"] = "1"
    row["require_machine_host_heal"] = "1"
    row["offered_to"] = "marchhare-99"
    row["offered_channel"] = "#marchhare"
    row["offered_ts"] = "2026-11-24T10:00:00Z"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st, job = gitclaim.accept_offered(home, "marchhare-99", "#marchhare")
    assert st == "ok"
    assert job.get("require_machine") in ("", "any", None) or job.get(
        "require_machine_host_heal"
    ) in (None, False, "", "0")
    # After clear, host-heal flag gone and pin released for auto class.
    assert not job.get("require_machine_host_heal")
    assert str(job.get("require_machine") or "").lower() in ("", "any")


def test_fr9554_marker():
    text = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "bob_host_heal_tipform_auto_pin" in text or "FR #9554" in text
