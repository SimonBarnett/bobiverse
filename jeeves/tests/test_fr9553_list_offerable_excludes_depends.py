# -*- coding: utf-8 -*-
"""FR #9553: !list and offerable_count exclude depends_* (match !assign / stuck)."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import stuck_job_sweep


REPO = "SimonBarnett/bobiverse"


def _row(num: int, *, body: str = "", **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": num,
        "ts": f"2026-11-24T10:00:{num:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
        "body": body,
    }
    r.update(kw)
    return r


def _write(home: Path, unaccepted: list[dict], accepted: list[dict] | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted),
            "accepted": list(accepted or []),
            "done": [],
        },
    )


def _seat_home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"redqueen"})
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {
            "nick": "redqueen-1",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "updated": "2026-11-24T10:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_fr9553_list_omits_depends_open_keeps_offerable(tmp_path, monkeypatch):
    """OPEN Depends-on parent in queue → child absent from !list; free sibling stays."""
    _seat_home(tmp_path, monkeypatch)
    parent = _row(9001)
    blocked = _row(9403, body="Depends-on: #9001\n")
    free = _row(9553, body="Depends-on: (none)\n")
    _write(tmp_path, [parent, blocked, free])

    lines = gitclaim.format_unaccepted_list(tmp_path)
    text = "\n".join(lines)
    assert "#9403" not in text
    assert "#9553" in text
    # Parent remains listable (not depends-blocked itself).
    assert "#9001" in text

    why = gitclaim.depends_gate_reason(blocked, gitclaim.load_queue(tmp_path))
    assert why == gitclaim.DEPENDS_OPEN_REASON


def test_fr9553_offerable_count_excludes_depends_open():
    parent = _row(9001)
    blocked = _row(9403, body="Depends-on: #9001\n")
    free = _row(9553, body="Depends-on: (none)\n")
    rows = [parent, blocked, free]
    doc = {"v": 1, "unaccepted": rows, "accepted": [], "done": []}
    # parent + free offerable; blocked excluded
    assert stuck_job_sweep.ungated_unaccepted_count(rows, doc=doc) == 2
    pub = bobreport.summarize_public_queue(rows, [])
    assert pub["offerable_count"] == 2
    assert pub["unaccepted_count"] == 3


def test_fr9553_stuck_still_lists_depends_open(tmp_path, monkeypatch):
    _seat_home(tmp_path, monkeypatch)
    parent = _row(9001)
    blocked = _row(9403, body="Depends-on: #9001\n")
    _write(tmp_path, [parent, blocked])
    snap = stuck_job_sweep.classify_queue_row(
        blocked,
        bucket="unaccepted",
        home=tmp_path,
        now=1_800_000_000.0,
        live=set(),
        idle=set(),
        ledger={},
    )
    assert snap.get("rule") == "depends_on_open"
    assert snap.get("state") == "held"


def test_fr9553_assign_refuses_depends_open(tmp_path, monkeypatch):
    _seat_home(tmp_path, monkeypatch)
    parent = _row(9001)
    blocked = _row(9403, body="Depends-on: #9001\n")
    _write(tmp_path, [parent, blocked])
    st, why = gitclaim.assign_row(tmp_path, "redqueen-1", REPO, "FR", "#9403")
    assert st == "refused"
    assert "depends" in str(why).lower()
