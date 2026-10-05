"""FR #2486: heal_require_machine_all_gave_up must not clear Living FR / Refs-only umbrellas."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines
import pytest


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(
        tmp_path, {"ionos", "win-mpre8vi4u6u", "marchhare"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _digest_seats(home, machines: dict[str, tuple[str, ...]]):
    doc = bobreport.empty_digest()
    for mid, pids in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {p: {"state": "idle"} for p in pids}
        doc["machines"][mid]["worker_list"] = [
            {"nick": f"{mid}-{p}", "state": "idle"} for p in pids
        ]
    bobreport.save_digest(home, doc)


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )


def _row(num, **kw):
    r = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": f"#{num}",
        "seq": 1,
        "ts": "t",
        "line": "x",
        "require_machine": "ionos",
        "title": f"FR #{num}",
        "body": "",
        "labels": [],
    }
    r.update(kw)
    return r


def test_fr2486_living_fr_body_skips_heal(home):
    _digest_seats(home, {"ionos": ("100", "200")})
    _queue(
        home,
        [
            _row(
                1993,
                body="Living FR — keep appending WP notes. require_machine: ionos\nRefs only.",
            )
        ],
    )
    gitclaim.ledger_giveup(home, "ionos-100", "SimonBarnett/bobiverse", "FR", "#1993")
    gitclaim.ledger_giveup(home, "ionos-200", "SimonBarnett/bobiverse", "FR", "#1993")
    live = gitclaim.live_seat_nicks(home)
    assert gitclaim.require_machine_all_live_gave_up(
        home,
        _row(1993, body="Living FR — keep appending"),
        live,
    )
    assert gitclaim.row_skip_pin_ledger_heal_reason(
        _row(1993, body="Living FR — keep appending")
    )
    assert gitclaim.heal_require_machine_all_gave_up(home, live) == []
    # giveups still present
    assert gitclaim.ledger_clear_giveup(home, "SimonBarnett/bobiverse", "#1993") >= 1


def test_fr2486_refs_only_label_skips_heal(home):
    _digest_seats(home, {"ionos": ("100",)})
    _queue(home, [_row(50, labels=["refs-only", "feature-request"])])
    gitclaim.ledger_giveup(home, "ionos-100", "SimonBarnett/bobiverse", "FR", "#50")
    live = gitclaim.live_seat_nicks(home)
    assert gitclaim.heal_require_machine_all_gave_up(home, live) == []


def test_fr2486_ordinary_pin_fr_still_heals(home):
    _digest_seats(home, {"ionos": ("100", "200")})
    _queue(home, [_row(2446, title="FR: pin starve ordinary", body="require_machine: ionos")])
    gitclaim.ledger_giveup(home, "ionos-100", "SimonBarnett/bobiverse", "FR", "#2446")
    gitclaim.ledger_giveup(home, "ionos-200", "SimonBarnett/bobiverse", "FR", "#2446")
    live = gitclaim.live_seat_nicks(home)
    healed = gitclaim.heal_require_machine_all_gave_up(home, live)
    assert healed
    assert gitclaim.ledger_clear_giveup(home, "SimonBarnett/bobiverse", "#2446") == 0


def test_fr2486_operator_doc_mentions_living_skip():
    from pathlib import Path
    from repo_layout import ROOT

    text = (ROOT / "jeeves" / "docs" / "empty-offer-operator.md").read_text(encoding="utf-8")
    assert "Living FR" in text or "Refs-only" in text or "refs-only" in text
    assert "2486" in text or "auto-heal" in text.lower()

def test_mrb2497_issue_1993_exact_blob_skips_heal(home):
    """Hostile: real #1993 title/body Living FR cue must skip heal after dual GIVEUP."""
    title = "jeeves.exe: chair+BobCallback one process, self-test/heal, rock-solid webhooks"
    body = (
        "## Summary\n\n"
        "Ship **ircJeeves as a frozen Windows executable** that runs **chair + BobCallback "
        "in one process**, fully deterministic (no LLM), rock-solid IIS→`:7700` webhooks, "
        "and a built-in diagnose/heal test matrix.\n\n"
        "Operator approved 2026-10-04. **Living FR — keep appending** WP notes, test names, "
        "and cutover evidence here (and in `jeeves/docs/jeeves-exe-self-heal.md` when opened).\n\n"
        "`require_machine: ionos`\n"
    )
    _digest_seats(home, {"ionos": ("100", "200")})
    _queue(home, [_row(1993, title=title, body=body, labels=["feature-request", "priority/critical"])])
    gitclaim.ledger_giveup(home, "ionos-100", "SimonBarnett/bobiverse", "FR", "#1993")
    gitclaim.ledger_giveup(home, "ionos-200", "SimonBarnett/bobiverse", "FR", "#1993")
    live = gitclaim.live_seat_nicks(home)
    assert gitclaim.row_skip_pin_ledger_heal_reason(_row(1993, title=title, body=body)) == "living_tracking_body"
    assert gitclaim.heal_require_machine_all_gave_up(home, live) == []
    assert gitclaim.ledger_clear_giveup(home, "SimonBarnett/bobiverse", "#1993") >= 1


def test_mrb2497_truncated_queue_body_keeps_living_cue():
    """Hostile: queue body truncate must not drop Living FR cue near top of #1993."""
    body = (
        "## Summary\n\n"
        "Ship ircJeeves as a frozen Windows executable.\n\n"
        "Operator approved 2026-10-04. **Living FR — keep appending** WP notes.\n\n"
        "`require_machine: ionos`\n"
        + ("x" * 800)
    )
    stored = gitclaim._body_for_queue(body)
    assert "Living FR" in stored
    assert gitclaim.row_skip_pin_ledger_heal_reason(
        _row(1993, body=stored)
    ) == "living_tracking_body"
