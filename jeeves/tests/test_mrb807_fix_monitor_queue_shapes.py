"""fix(mrb-807): monitor checks must read real bobiverse digest/queue shapes.

Hostile MRB of PR #807 found:
* idle_seats treated workers as a list; digest uses pid-keyed dict
* stuck_accepted required accepted_by; gitclaim accepted rows use nick + accepted bucket
* queue_flow looked at kind/type; gitclaim rows use task + url
"""
from __future__ import annotations

import json
import subprocess
import sys
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


def test_idle_seats_detects_pid_keyed_digest_workers(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#10",
                        "url": "https://github.com/SimonBarnett/bobiverse/issues/10",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "marchhare": {
                        "workers": {
                            "35600": {"state": "idle", "nick": "marchhare-35600"},
                            "1": {"state": "doing", "nick": "marchhare-1"},
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    code, payload = _run("idle_seats", chair, digest)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["unaccepted_count"] == 1
    assert len(payload["idle_seats"]) == 1
    assert payload["idle_seats"][0]["nick"] == "marchhare-35600"


def test_stuck_accepted_uses_nick_and_accepted_bucket(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [],
                "accepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#42",
                        "nick": "marchhare-35600",
                        "channel": "#marchhare",
                        "accepted_ts": "2000-01-01T00:00:00Z",
                        "url": "https://github.com/SimonBarnett/bobiverse/issues/42",
                    }
                ],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    code, payload = _run("stuck_accepted", chair, digest)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["stuck"]
    assert any("#42" in str(s.get("row")) for s in payload["stuck"])


def test_queue_flow_mrb_missing_pull_url_uses_task_field(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "MRB",
                        "id": "#99",
                        "line": "x",
                        # no url / pull url — must be flagged
                    },
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#11",
                        "url": "https://github.com/SimonBarnett/bobiverse/issues/11",
                    },
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    code, payload = _run("queue_flow", chair, digest)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["offerable_count"] >= 1
    assert payload["missing_pull_url_count"] >= 1
    assert any("missing pull url" in f for f in payload["findings"])
