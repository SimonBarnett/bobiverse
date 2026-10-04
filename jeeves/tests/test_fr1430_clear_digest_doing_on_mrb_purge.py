"""FR #1430: purging accepted MERGED MRB clears seat digest doing/working_on."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_clear_seat_doing_idles_worker_list_and_workers(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "worker_list": [
            {
                "nick": "win-mpre8vi4u6u-15656",
                "state": "doing",
                "work": "bobiverse MRB #1422",
                "updated": "2026-10-04T04:33:39Z",
            }
        ],
        "workers": {
            "15656": {
                "pid": "15656",
                "nick": "w-io-15656",
                "state": "doing",
                "working_on": "bobiverse MRB #1422",
            }
        },
    }
    bobreport.save_digest(tmp_path, doc)
    out = bobreport.clear_seat_doing(
        tmp_path, "win-mpre8vi4u6u-15656", only_if_work_contains="1422"
    )
    assert out.ok
    assert gitclaim.worker_working_on(tmp_path, "win-mpre8vi4u6u-15656") == ""
    d2 = bobreport.load_digest(tmp_path)
    wl = ((d2.get("machines") or {}).get("win-mpre8vi4u6u") or {}).get("worker_list") or []
    assert wl[0]["state"] == "idle"
    assert wl[0]["work"] == ""


def test_purge_dead_mrb_accepted_clears_digest_doing(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    doc = bobreport.empty_digest()
    doc["machines"]["win-mpre8vi4u6u"] = {
        "id": "win-mpre8vi4u6u",
        "online": True,
        "worker_list": [
            {
                "nick": "win-mpre8vi4u6u-15656",
                "state": "doing",
                "work": "bobiverse MRB #1422",
                "updated": "2026-10-04T04:33:39Z",
            }
        ],
        "workers": {
            "15656": {
                "pid": "15656",
                "nick": "w-io-15656",
                "state": "doing",
                "working_on": "bobiverse MRB #1422",
            }
        },
    }
    bobreport.save_digest(tmp_path, doc)

    q = {
        "unaccepted": [],
        "accepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#1422",
                "event": "pull_request",
                "nick": "win-mpre8vi4u6u-15656",
                "url": "https://github.com/SimonBarnett/bobiverse/pull/1422",
            }
        ],
        "done": [],
    }

    def pr_exists(repo, num):
        return False  # merged/closed → dead

    n = gitclaim._purge_dead_mrb_accepted(q, pr_exists=pr_exists, home=tmp_path)
    assert n == 1
    assert q["accepted"] == []
    assert gitclaim.worker_working_on(tmp_path, "win-mpre8vi4u6u-15656") == ""
