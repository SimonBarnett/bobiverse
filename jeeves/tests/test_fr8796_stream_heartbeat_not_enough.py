"""FR #8796: OpenCode stream heartbeats must not mask stuck doing (no DONE)."""
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


def test_stream_heartbeat_fresh_last_progress_still_finding(tmp_path: Path):
    """doing + accepted >15m + progress_phase=stream + fresh last_progress + ACK but no DONE."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    now = datetime.now(timezone.utc)
    accepted_ts = _iso(now - timedelta(minutes=47))
    last_progress = _iso(now - timedelta(seconds=20))
    nick = "redqueen-2356"
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
                        "nick": nick,
                        "accepted_ts": accepted_ts,
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
                        "worker_list": [
                            {
                                "nick": nick,
                                "state": "doing",
                                "work": "FR SimonBarnett/bobiverse#8750",
                                "updated": last_progress,
                                "last_progress": last_progress,
                                "progress_phase": "stream",
                                "kind": "opencode",
                            }
                        ],
                        "workers": {
                            "2356": {
                                "nick": nick,
                                "state": "doing",
                                "working_on": "FR SimonBarnett/bobiverse#8750",
                                "updated": last_progress,
                                "last_progress": last_progress,
                                "progress_phase": "stream",
                                "kind": "opencode",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    # ACK present (wire_hits > 0) so the legacy aged_no_wire path alone would miss this.
    (chair / "cmd-trace.log").write_text(
        f"{accepted_ts} shop ACK from {nick} FR SimonBarnett/bobiverse#8750\n",
        encoding="utf-8",
    )
    code, payload = _run("seats_stuck_doing", chair, digest)
    assert code == 1, payload
    reasons = {s.get("reason") for s in payload.get("stuck") or []}
    assert "stream_heartbeat_no_substantive" in reasons, payload
    assert any("stream" in f.lower() or "substantive" in f.lower() for f in payload["findings"])
    assert payload.get("stream_heartbeat_max_age_sec") == 15 * 60


def test_stream_heartbeat_clears_when_done_present(tmp_path: Path):
    """Same shape but DONE in chair log -> not a stream-heartbeat hang."""
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    now = datetime.now(timezone.utc)
    accepted_ts = _iso(now - timedelta(minutes=47))
    last_progress = _iso(now - timedelta(seconds=5))
    nick = "redqueen-2356"
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
                        "nick": nick,
                        "accepted_ts": accepted_ts,
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
                                "nick": nick,
                                "state": "doing",
                                "working_on": "FR SimonBarnett/bobiverse#8750",
                                "last_progress": last_progress,
                                "progress_phase": "stream",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (chair / "cmd-trace.log").write_text(
        f"{accepted_ts} ACK {nick}\n"
        f"{last_progress} DONE FR SimonBarnett/bobiverse#8750 from {nick}\n",
        encoding="utf-8",
    )
    code, payload = _run("seats_stuck_doing", chair, digest)
    reasons = {s.get("reason") for s in payload.get("stuck") or []}
    assert "stream_heartbeat_no_substantive" not in reasons, payload
    assert "heartbeat_no_done" not in reasons, payload
    assert "accepted_no_done" not in reasons, payload
    # May still be ok==True (busy with accepted is fine once DONE was logged).
    assert code in (0, 1)
