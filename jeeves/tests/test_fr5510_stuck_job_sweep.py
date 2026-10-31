"""FR #5510: stuck-job sweep — three 2026-10-31 cases + protections."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gitclaim
import stuck_job_sweep as sweep


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _queue(home: Path, *, unaccepted=None, accepted=None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    doc = {
        "unaccepted": list(unaccepted or []),
        "accepted": list(accepted or []),
        "done": [],
    }
    gitclaim.queue_path(home).write_text(json.dumps(doc), encoding="utf-8")


def test_fr5510_silent_accepted_released_within_40_min(tmp_path: Path):
    """#5505 class: ACKed accepted row, holder silent 30+ min → release + re-offer."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    accepted_ts = _iso(now - 2000.0)  # ~33 min
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#5484",
                "nick": "redqueen-12864",
                "accepted_ts": accepted_ts,
                "title": "MRB #5484",
                "line": "MRB SimonBarnett/bobiverse#5484",
            }
        ],
    )
    live = {"redqueen-12864"}
    activity = {"redqueen-12864": now - 2000.0}
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live=live,
        idle=set(),
        activity=activity,
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] == 1
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    assert len(doc["unaccepted"]) == 1
    row = doc["unaccepted"][0]
    assert row["id"] in ("#5484", "5484") or str(row["id"]).endswith("5484")
    assert row.get("retry") is True
    assert "stuck-sweep" in str(row.get("note") or "")


def test_fr5510_copilot_holder_gone_released(tmp_path: Path):
    """#5267 class: accepted by nick=copilot when that seat is not live → release."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#5267",
                "nick": "copilot",
                "accepted_ts": _iso(now - 2000.0),
                "line": "FR SimonBarnett/bobiverse#5267",
            }
        ],
    )
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={"redqueen-1"},  # copilot not live
        idle={"redqueen-1"},
        activity={},
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] == 1
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    assert any(
        str(r.get("id")).endswith("5267") for r in doc["unaccepted"]
    )


def test_fr5510_untracked_offerable_lesson_enqueued(tmp_path: Path):
    """#5506 class: open offerable via-intake+skill lesson PR missing from queue → enqueue."""
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    _queue(home, unaccepted=[], accepted=[])
    open_items = [
        {
            "repo": "SimonBarnett/bobiverse",
            "kind": "pr",
            "id": "#4967",
            "title": "lesson(bobiverse-bob-worker): harvest hold flush",
            "body": "## Lesson\n\nMRB (light triage)\n\nKeep harvest across ACK.",
            "labels": ["via-intake", "skill"],
            "draft": True,
        }
    ]
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={"redqueen-1"},
        idle={"redqueen-1"},
        activity={},
        open_items=open_items,
        act=True,
    )
    assert report["actions"]["enqueued"] >= 1
    doc = gitclaim.load_queue(home)
    assert any(
        str(r.get("task")).upper() == "MRB" and str(r.get("id")).endswith("4967")
        for r in (doc.get("unaccepted") or [])
    )


def test_fr5510_needs_human_not_released(tmp_path: Path):
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#9",
                "nick": "gone-seat",
                "accepted_ts": _iso(now - 5000.0),
                "needs_human": True,
                "line": "FR SimonBarnett/bobiverse#9",
            }
        ],
    )
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live=set(),
        idle=set(),
        activity={},
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] == 0
    doc = gitclaim.load_queue(home)
    assert len(doc["accepted"]) == 1
    held = [c for c in report["classified"] if c.get("state") == "held"]
    assert any(c.get("rule") == "needs_human" for c in held)


def test_fr5510_receipt_listed_not_enqueued(tmp_path: Path):
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    _queue(home)
    open_items = [
        {
            "repo": "SimonBarnett/bobiverse",
            "kind": "pr",
            "id": "#4444",
            "title": "harvest: DONE twin",
            "body": "Invoke-BobiverseHarvest\nSession summary: x",
            "labels": ["via-intake", "skill"],
            "draft": True,
        }
    ]
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live=set(),
        idle=set(),
        open_items=open_items,
        act=True,
    )
    assert report["actions"]["enqueued"] == 0
    assert any(c.get("rule") == "receipt" for c in report.get("held") or [])


def test_fr5510_stuck_command_lines(tmp_path: Path):
    home = tmp_path / "digest"
    sweep.write_stuck_report(
        home,
        {
            "v": 1,
            "ts": _iso(1_700_000_000.0),
            "stuck": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "number": "#5484",
                    "task": "MRB",
                    "state": "accepted",
                    "stuck_reason": "accepted_silent",
                    "holder": "redqueen-1",
                    "age_s": 2000,
                }
            ],
            "held": [],
            "classified": [],
        },
    )
    lines = sweep.format_stuck_lines(home)
    assert lines[0].startswith("stuck:")
    assert "5484" in lines[1]
    assert "accepted_silent" in lines[1]


def test_fr5510_announce_only_on_change(tmp_path: Path):
    home = tmp_path / "digest"
    now = 1_700_000_000.0
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#1",
                "nick": "copilot",
                "accepted_ts": _iso(now - 2000.0),
                "line": "FR #1",
            }
        ],
    )
    notes: list[str] = []
    sweep.run_stuck_sweep(
        home,
        now=now,
        live=set(),
        idle=set(),
        open_items=[],
        act=False,
        announce=notes.append,
    )
    assert notes and "stuck-sweep" in notes[0]
    n0 = len(notes)
    sweep.run_stuck_sweep(
        home,
        now=now,
        live=set(),
        idle=set(),
        open_items=[],
        act=False,
        announce=notes.append,
    )
    assert len(notes) == n0  # fingerprint unchanged
