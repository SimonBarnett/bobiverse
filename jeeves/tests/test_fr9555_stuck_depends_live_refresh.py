# -*- coding: utf-8 -*-
"""FR #9555: stuck/depends digest must refresh from live queue (no stale ACC).

Class of #9403: after Depends-on was stripped and the FR was ACC on flamingo,
digest ``stuck`` still showed ``rule=depends_unresolved`` from a prior sweep
snapshot. Paint must recompute against the live row body + bucket.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import stuck_job_sweep as sweep


REPO = "SimonBarnett/bobiverse"


def _digest(home: Path) -> None:
    registered_machines.save_registered(home, {"flamingo"})
    doc = bobreport.empty_digest()
    doc["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    doc["machines"]["flamingo"]["worker_list"] = [
        {
            "nick": "flamingo-17160",
            "state": "doing",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-24T10:30:00Z",
        }
    ]
    bobreport.save_digest(home, doc)


def _row(*, body: str, num: int = 9403, **kw) -> dict:
    r = {
        "task": "FR",
        "repo": REPO,
        "id": f"#{num}",
        "seq": 1,
        "ts": "2026-11-24T09:00:00Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": "BOB-TRAY-UI-11",
        "body": body,
        "labels": ["feature-request"],
        "state": "open",
        "event": "issues",
    }
    r.update(kw)
    return r


def test_fr9555_digest_drops_depends_unresolved_when_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home)
    # Stale report: held depends_unresolved while row is already ACC.
    stale = {
        "v": 1,
        "ts": "2026-11-24T10:00:00Z",
        "stuck": [],
        "held": [
            {
                "repo": REPO,
                "number": "9403",
                "task": "FR",
                "state": "held",
                "rule": "depends_unresolved",
                "age_s": 4000,
                "holder": "",
            }
        ],
        "classified": [],
    }
    sweep.write_stuck_report(home, stale)
    acc = _row(body="Depends-on: #9259 Digest: BOB-TRAY-UI\n")
    acc["nick"] = "flamingo-17160"
    acc["accepted_ts"] = "2026-11-24T10:25:00Z"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [acc], "done": []},
    )
    painted = sweep.digest_stuck_section(home)
    rules = [str(x.get("rule") or "") for x in painted if isinstance(x, dict)]
    assert not any(r.startswith("depends_") for r in rules)
    assert not any(
        str(x.get("number") or "") in {"9403", "#9403"}
        and str(x.get("rule") or "").startswith("depends_")
        for x in painted
        if isinstance(x, dict)
    )


def test_fr9555_digest_clears_when_depends_on_stripped(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home)
    stale = {
        "v": 1,
        "ts": "t",
        "stuck": [],
        "held": [
            {
                "repo": REPO,
                "number": "9403",
                "task": "FR",
                "state": "held",
                "rule": "depends_unresolved",
                "age_s": 100,
                "holder": "",
            }
        ],
        "classified": [],
    }
    sweep.write_stuck_report(home, stale)
    # Live unaccepted body no longer has Depends-on.
    live = _row(body="## What\nImplement tray watcher.\n")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [live], "accepted": [], "done": []},
    )
    painted = sweep.digest_stuck_section(home)
    assert not any(
        str(x.get("rule") or "").startswith("depends_") for x in painted if isinstance(x, dict)
    )


def test_fr9555_refresh_helper_keeps_live_depends_held(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    child = _row(body="Depends-on: #9999\n", num=100)
    parent = _row(
        body="Depends-on: (none)\n",
        num=9999,
        title="ordinary parent still open",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [child, parent], "accepted": [], "done": []},
    )
    entries = [
        {
            "repo": REPO,
            "number": "100",
            "task": "FR",
            "state": "held",
            "rule": "depends_unresolved",
            "age_s": 10,
            "holder": "",
        }
    ]
    out = sweep.refresh_stuck_depends_from_live_queue(home, entries)
    assert len(out) == 1
    assert out[0]["rule"] == "depends_on_open"


def test_fr9555_marker():
    text = Path(sweep.__file__).read_text(encoding="utf-8")
    assert "FR #9555" in text or "bob_stuck_depends_live_refresh" in text
