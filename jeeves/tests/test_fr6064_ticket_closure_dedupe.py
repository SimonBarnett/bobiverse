"""FR #6064: one wake per close (closed_at / delivery id) in ops-home state."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
STATE = "monitor-ticket-closure.json"


def _run(chair: Path, digest: Path, env: dict | None = None) -> tuple[int, dict]:
    e = os.environ.copy()
    if env:
        e.update(env)
    r = subprocess.run(
        [
            sys.executable,
            str(MONITOR / "ticket_closure.py"),
            "--chair-home",
            str(chair),
            "--digest-home",
            str(digest),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MONITOR),
        env=e,
    )
    line = (r.stdout or "").strip().splitlines()[-1]
    return r.returncode, json.loads(line)


def _homes(tmp_path: Path) -> tuple[Path, Path]:
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "focus.json").write_text(
        json.dumps({"v": 1, "repos": {"SimonBarnett/bobiverse": {"priority": 1}}}),
        encoding="utf-8",
    )
    return chair, digest


def _fx(path: Path, rows: list[dict]) -> Path:
    path.write_text(json.dumps({"closed": rows}), encoding="utf-8")
    return path


def test_fr6064_same_close_twice_then_distinct_close(tmp_path: Path):
    chair, digest = _homes(tmp_path)
    first = {
        "kind": "issue",
        "event": "closed",
        "repo": "SimonBarnett/bobiverse",
        "number": 77,
        "closed_at": "2026-11-03T14:00:00Z",
        "delivery_id": "del-77a",
    }
    fx = _fx(tmp_path / "events.json", [first])
    env = {"JEEVES_TICKET_CLOSURE_FIXTURE": str(fx)}
    c1, p1 = _run(chair, digest, env)
    assert c1 == 1, p1
    assert len(p1.get("closed") or []) == 1
    state = digest / STATE
    assert state.is_file()
    assert not (chair / "ticket_closure_state.json").exists()
    body = json.loads(state.read_text(encoding="utf-8"))
    keys = list((body.get("seen") or {}).keys()) + list((body.get("pending") or {}).keys())
    assert any("77" in k and ("del-77a" in k or "2026-11-03T14:00:00Z" in k) for k in keys)

    c2, p2 = _run(chair, digest, env)
    assert c2 == 0, p2
    assert p2.get("closed") == []
    assert not (digest / "queue.json").exists()

    second = dict(first)
    second["closed_at"] = "2026-11-03T15:00:00Z"
    second["delivery_id"] = "del-77b"
    _fx(fx, [first, second])
    c3, p3 = _run(chair, digest, env)
    assert c3 == 1, p3
    closed = p3.get("closed") or []
    assert len(closed) == 1
    assert closed[0]["number"] == 77
    assert closed[0].get("delivery_id") == "del-77b"
