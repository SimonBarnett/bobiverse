"""FR #8384: paint accepted work, demote blank LOST_ACK, flag empty seats."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import bobreport
import gitclaim

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "monitor"))
import stuck_accepted  # noqa: E402

NICK = "flamingo-10852"
REPO = "SimonBarnett/bobiverse"


def _seed(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _queue(home: Path, accepted: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": accepted, "done": []},
    )


def _row(**extra) -> dict:
    base = {
        "task": "FR",
        "repo": REPO,
        "id": "#8384",
        "nick": NICK,
        "title": "accepted paint",
        "accepted_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30)),
    }
    base.update(extra)
    return base


def test_ack_worker_work_paints_accepted_job(tmp_path: Path) -> None:
    _seed(tmp_path)
    _queue(tmp_path, [_row()])
    out = bobreport._apply_worker_op(
        tmp_path,
        "worker-work",
        "flamingo",
        {"nick": NICK, "state": "doing", "work": ""},
    )
    assert out.ok
    doc = bobreport.load_digest(tmp_path)
    row = doc["machines"]["flamingo"]["worker_list"][0]
    assert "8384" in row["work"]
    assert row["working_on"] == row["work"]
    assert row["state"] == "doing"


def test_lost_ack_demotes_when_work_blank_even_with_ledger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(tmp_path, [_row(reconcile="LOST_ACK_RESTART")])
    gitclaim.ledger_note_event(tmp_path, NICK, "ACK", "FR", REPO, "#8384", _row())
    assert gitclaim.release_unacked_lost_ack(tmp_path, NICK, log=lambda _l: None) is True
    q = gitclaim.load_queue(tmp_path)
    assert q["accepted"] == []
    assert any(str(r.get("reconcile")) == "requeue:LOST_ACK_NO_ACK" for r in q["unaccepted"])


def test_monitor_flags_accepted_with_blank_working_on(tmp_path: Path) -> None:
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 900))
    rows = [_row(accepted_ts=old)]
    shop = [{"nick": NICK, "state": "doing", "work": "", "working_on": ""}]
    text = stuck_accepted._blank_accepted_finding(rows, shop)
    assert "empty working_on" in text
    painted = [{"nick": NICK, "state": "doing", "work": "bobiverse FR #8384", "working_on": ""}]
    assert stuck_accepted._blank_accepted_finding(rows, painted) == ""


def test_holder_bored_clears_placeholder_doing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOB_HOLDER_BORED_N", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _seed(tmp_path)
    _queue(tmp_path, [_row()])
    bobreport._apply_worker_op(
        tmp_path,
        "worker-work",
        "flamingo",
        {"nick": NICK, "state": "doing", "work": "working"},
    )
    released = gitclaim.release_holder_on_bored(tmp_path, NICK)
    assert released
    doc = bobreport.load_digest(tmp_path)
    row = doc["machines"]["flamingo"]["worker_list"][0]
    assert row["state"] == "idle"
    assert row["work"] == ""
