"""FR #10110: a closed MRB/FIX PR idles every digest seat still doing it.

The merged-webhook path only cleared seats named by a matching ``done`` row. A seat
whose accepted row was already gone (or a closed PR with no queue row at all, which
returns ``noop`` early) kept ``doing bobiverse MRB #N`` and nak-busied every !bored.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim

REPO = "SimonBarnett/bobiverse"
MID = "win-mpre8vi4u6u"
PID = "15656"
NICK = f"{MID}-{PID}"


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["' + MID + '"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest(home: Path, work: str) -> None:
    doc = bobreport.empty_digest()
    doc["machines"][MID] = {
        "id": MID,
        "online": True,
        "worker_list": [
            {
                "nick": NICK,
                "state": "doing",
                "work": work,
                "updated": "2026-10-04T04:33:39Z",
            }
        ],
        "workers": {
            PID: {
                "pid": PID,
                "nick": f"w-io-{PID}",
                "state": "doing",
                "working_on": work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _closed(num: int, merged: bool, task: str = "MRB") -> gitclaim.GitClaim:
    return gitclaim.GitClaim(
        repo=REPO,
        task=task,
        id=f"#{num}",
        event="pull_request",
        action="closed",
        line="closed",
        merged=merged,
        title="t",
    )


def _seat_state(home: Path) -> tuple[str, str, str]:
    doc = bobreport.load_digest(home)
    ent = doc["machines"][MID]
    row = ent["worker_list"][0]
    wo = ent["workers"][PID]["working_on"]
    return str(row["state"]), str(row["work"]), str(wo)


def test_merged_mrb_webhook_idles_seat_with_no_queue_row(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    _digest(tmp_path, "bobiverse MRB #1476")

    gitclaim.apply_queue_event(tmp_path, _closed(1476, merged=True))

    state, work, wo = _seat_state(tmp_path)
    assert state == "idle"
    assert work == ""
    assert wo == ""


def test_closed_unmerged_fix_webhook_idles_seat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    _digest(tmp_path, "bobiverse FIX #1476")

    gitclaim.apply_queue_event(tmp_path, _closed(1476, merged=False, task="FIX"))

    state, work, _wo = _seat_state(tmp_path)
    assert state == "idle"
    assert work == ""


def test_closed_pr_sweep_leaves_other_pr_and_other_repo_busy(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    _digest(tmp_path, "bobiverse MRB #1477")

    gitclaim.apply_queue_event(tmp_path, _closed(1476, merged=True))

    state, work, _wo = _seat_state(tmp_path)
    assert state == "doing"
    assert work == "bobiverse MRB #1477"


def test_closed_pr_sweep_skips_other_repo_with_same_number(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    _digest(tmp_path, "a-search MRB #1476")

    gitclaim.apply_queue_event(tmp_path, _closed(1476, merged=True))

    state, work, _wo = _seat_state(tmp_path)
    assert state == "doing"
    assert work == "a-search MRB #1476"


def test_closed_pr_sweep_skips_fr_work_mentioning_same_number(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    _digest(tmp_path, "bobiverse FR #1476")

    gitclaim.apply_queue_event(tmp_path, _closed(1476, merged=True))

    state, work, _wo = _seat_state(tmp_path)
    assert state == "doing"
    assert work == "bobiverse FR #1476"
