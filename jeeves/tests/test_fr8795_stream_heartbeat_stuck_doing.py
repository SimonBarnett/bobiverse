"""FR #8795 / #8796: stream heartbeats must not mask stuck doing.

OpenCode seats refresh last_progress / state_ts / updated while making no
GitHub or wire progress. Age the accept stamp, ignore heartbeat fields.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"


def _run(name: str, chair: Path, digest: Path) -> tuple[int, dict]:
    py = MONITOR / f"{name}.py"
    r = subprocess.run(
        [
            sys.executable,
            str(py),
            "--chair-home",
            str(chair),
            "--digest-home",
            str(digest),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MONITOR),
    )
    line = (r.stdout or "").strip().splitlines()[-1]
    return r.returncode, json.loads(line)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_fr8795_stream_heartbeat_fresh_last_progress_still_stuck(tmp_path: Path):
    """accepted_ts old + progress_phase=stream + fresh last_progress => finding."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    now = datetime.now(timezone.utc)
    accepted = _iso(now - timedelta(minutes=50))
    heartbeat = _iso(now - timedelta(seconds=30))
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [],
                "accepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#8750",
                        "nick": "redqueen-2356",
                        "accepted_ts": accepted,
                    }
                ],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "redqueen": {
                        "workers": {
                            "2356": {
                                "state": "doing",
                                "nick": "redqueen-2356",
                                "kind": "opencode",
                                "model": "opencode/deepseek-v4.1-flash-free",
                                "working_on": "FR SimonBarnett/bobiverse#8750",
                                "accepted_ts": accepted,
                                "progress_phase": "stream",
                                "last_progress": heartbeat,
                                "state_ts": heartbeat,
                                "updated": heartbeat,
                                "ts": heartbeat,
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (chair / "cmd-trace.log").write_text("noise only\n", encoding="utf-8")
    code, payload = _run("seats_stuck_doing", chair, digest)
    assert code == 1, payload
    assert any(
        s.get("reason") in ("aged_no_wire", "stream_heartbeat_no_wire") for s in payload["stuck"]
    ), payload
    assert any("redqueen-2356" in f for f in payload["findings"]), payload
    # Heartbeat freshness must not clear the finding
    assert payload.get("ok") is False


def test_fr8795_fresh_accept_with_stream_heartbeat_ok(tmp_path: Path):
    """Recent accept + stream phase stays green (under max age)."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    now = datetime.now(timezone.utc)
    accepted = _iso(now - timedelta(minutes=2))
    heartbeat = _iso(now - timedelta(seconds=5))
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [],
                "accepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#1",
                        "nick": "redqueen-1",
                        "accepted_ts": accepted,
                    }
                ],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "redqueen": {
                        "workers": {
                            "1": {
                                "state": "doing",
                                "nick": "redqueen-1",
                                "kind": "opencode",
                                "working_on": "FR SimonBarnett/bobiverse#1",
                                "accepted_ts": accepted,
                                "progress_phase": "stream",
                                "last_progress": heartbeat,
                                "updated": heartbeat,
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (chair / "cmd-trace.log").write_text("noise\n", encoding="utf-8")
    code, payload = _run("seats_stuck_doing", chair, digest)
    assert code == 0, payload
    assert payload.get("ok") is True
    assert not any(
        s.get("reason") in ("aged_no_wire", "stream_heartbeat_no_wire") for s in payload["stuck"]
    ), payload
