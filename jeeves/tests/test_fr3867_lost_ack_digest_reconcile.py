"""FR #3867: offer lost across chair restart — digest working_on promotes unaccepted to accepted."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim

NICK = "marchhare-960"
WORK = "a-search FR #1018"
REPO = "SimonBarnett/a-search"


def _setup(home: Path, monkeypatch, *, work: str = WORK, list_idle: bool = True) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare","win-mpre8vi4u6u"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    worker_list = []
    if list_idle:
        worker_list = [
            {
                "nick": NICK,
                "state": "idle",
                "work": "",
                "updated": "2026-10-10T06:01:13Z",
            }
        ]
    else:
        worker_list = [
            {
                "nick": NICK,
                "state": "doing",
                "work": work,
                "updated": "2026-10-10T06:01:13Z",
            }
        ]
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": work,
        "worker_list": worker_list,
        "workers": {
            "960": {
                "pid": "960",
                "nick": NICK,
                "state": "running",
                "working_on": work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home: Path, *, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": list(unaccepted), "accepted": list(accepted or [])},
    )


def _row(**extra) -> dict:
    base = {
        "repo": REPO,
        "task": "FR",
        "id": "#1018",
        "seq": 1018,
        "url": f"https://github.com/{REPO}/issues/1018",
    }
    base.update(extra)
    return base


def test_fr3867_parse_digest_work_short_form():
    parsed = gitclaim.parse_digest_work(WORK)
    assert parsed is not None
    assert parsed["task"] == "FR"
    assert parsed["id"] == "#1018"
    assert parsed["repo_short"] == "a-search"


def test_fr3867_reconcile_promotes_unaccepted_when_digest_working(tmp_path, monkeypatch):
    """Incident: offer before restart, no ACK after, digest workers.960 still running #1018."""
    _setup(tmp_path, monkeypatch, list_idle=True)
    offer_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    _queue(
        tmp_path,
        unaccepted=[
            _row(offered_to=NICK, offered_ts=offer_ts, offered_channel="#marchhare"),
        ],
    )
    logs: list[str] = []
    n = gitclaim.reconcile_lost_ack_from_digest(tmp_path, log=logs.append)
    assert n == 1
    q = gitclaim.load_queue(tmp_path)
    assert q["unaccepted"] == []
    assert len(q["accepted"]) == 1
    acc = q["accepted"][0]
    assert acc["repo"] == REPO
    assert str(acc["id"]) == "#1018"
    assert acc["nick"] == NICK
    assert str(acc.get("reconcile") or "") == "LOST_ACK_RESTART"
    assert any("seat-reconcile" in line and "LOST_ACK_RESTART" in line for line in logs)


def test_fr3867_offer_after_restart_does_not_reoffer(tmp_path, monkeypatch):
    """After reconcile, another seat must not be offered the same row."""
    _setup(tmp_path, monkeypatch, list_idle=True)
    offer_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    _queue(
        tmp_path,
        unaccepted=[
            _row(offered_to=NICK, offered_ts=offer_ts, offered_channel="#marchhare"),
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#7",
                "seq": 7,
                "url": "https://github.com/SimonBarnett/bobiverse/issues/7",
            },
        ],
    )
    # Simulate chair restart then !bored from a free sibling seat.
    other = "marchhare-42664"
    doc = bobreport.load_digest(tmp_path)
    ent = doc["machines"]["marchhare"]
    ent["worker_list"].append(
        {"nick": other, "state": "idle", "work": "", "updated": "2026-10-10T07:20:00Z"}
    )
    ent["workers"]["42664"] = {
        "pid": "42664",
        "nick": other,
        "state": "idle",
        "working_on": "",
    }
    bobreport.save_digest(tmp_path, doc)

    st, job = gitclaim.offer_focus_top(tmp_path, other, "#marchhare")
    assert st == "ok"
    assert job is not None
    assert str(job.get("id")) == "#7"
    q = gitclaim.load_queue(tmp_path)
    # #1018 must be accepted by NICK, not re-offered.
    assert any(
        str(r.get("id")) == "#1018" and str(r.get("nick") or "") == NICK
        for r in (q.get("accepted") or [])
    )
    assert not any(str(r.get("id")) == "#1018" for r in (q.get("unaccepted") or []))


def test_fr3867_worker_working_on_keeps_map_when_unaccepted_matches(tmp_path, monkeypatch):
    """Do not FR #1714-clear map working_on that still matches an unaccepted queue row."""
    _setup(tmp_path, monkeypatch, list_idle=True)
    _queue(tmp_path, unaccepted=[_row()])
    wo = gitclaim.worker_working_on(tmp_path, NICK)
    assert wo == WORK
    # Map must still hold the work (not healed away).
    dig = bobreport.load_digest(tmp_path)
    assert dig["machines"]["marchhare"]["workers"]["960"]["working_on"] == WORK


def test_fr3867_irc_agent_wires_session_reconcile():
    agent = Path(__file__).resolve().parents[2] / "common/scripts/irc_agent.py"
    text = agent.read_text(encoding="utf-8")
    assert "reconcile_lost_ack_from_digest" in text
    assert "FR #3867" in text
