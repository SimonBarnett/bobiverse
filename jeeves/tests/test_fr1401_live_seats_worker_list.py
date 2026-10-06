"""FR #1401: live_seat_nicks prefers worker_list; ghost workers must not strand repo UAT."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare","win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest_with_ghosts(home: Path) -> None:
    _roster(home)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        # Ghost seats: in legacy workers, absent from worker_list (never !bored).
        "workers": {
            "16564": {"pid": "16564", "state": "idle"},
            "41912": {"pid": "41912", "state": "idle"},
            "35600": {"pid": "35600", "state": "idle"},
            "41928": {"pid": "41928", "state": "doing"},
        },
        "worker_list": [
            {
                "nick": "marchhare-35600",
                "state": "idle",
                "work": "",
                "updated": "2026-10-04T00:11:14Z",
            },
            {
                "nick": "marchhare-41928",
                "state": "doing",
                "work": "bobiverse MRB #1390",
                "updated": "2026-10-04T01:33:18Z",
            },
        ],
    }
    bobreport.save_digest(home, doc)


def test_live_seat_nicks_ignores_worker_dict_ghosts(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_with_ghosts(tmp_path)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "marchhare-35600" in live
    assert "marchhare-41928" in live
    assert "marchhare-16564" not in live
    assert "marchhare-41912" not in live


def test_repo_uat_live_seats_ignore_ghosts_and_self_uat_stays_blocked(tmp_path, monkeypatch):
    """FR #1401 live seats + FR #2939: ghosts ignored; self-UAT never escaped."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest_with_ghosts(home)

    uat = {
        "repo": "SimonBarnett/bobiverse",
        "task": "UAT",
        "id": "#0",
        "repo_uat": True,
        "title": "UAT SimonBarnett/bobiverse",
        "line": "UAT SimonBarnett/bobiverse: all issues closed",
        "merged_prs": ["#1390"],
        "refs": ["#1390"],
    }
    # Stamp FR on every real live seat. Ghosts never touched and must not count as live.
    for nick in ("marchhare-35600", "marchhare-41928"):
        gitclaim.ledger_touch(
            home,
            nick,
            "SimonBarnett/bobiverse",
            "FR",
            ["simonbarnett/bobiverse#0", "simonbarnett/bobiverse#1390"],
        )

    led = gitclaim.ledger_load(home)
    live = gitclaim.live_seat_nicks(home)
    assert "marchhare-16564" not in live
    assert "marchhare-41912" not in live
    assert live

    # FR #2939: every real live seat is self-UAT — stay blocked (escalate, no escape).
    why356 = gitclaim.ledger_blocks(led, uat, "marchhare-35600", live)
    assert why356 and "self-UAT" in why356
    why419 = gitclaim.ledger_blocks(led, uat, "marchhare-41928", live)
    assert why419 and "self-UAT" in why419
    assert gitclaim.repo_uat_no_eligible_live_seat(led, uat, live)


def test_live_seat_nicks_falls_back_to_workers_when_list_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "workers": {"42": {"pid": "42", "state": "idle"}},
        "worker_list": [],
    }
    bobreport.save_digest(tmp_path, doc)
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "marchhare-42" in live
