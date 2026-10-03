"""FR #1019: focus_present + seats_stuck_doing monitor checks."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
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


def test_focus_present_ok_when_bobiverse_listed(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "focus.json").write_text(
        json.dumps(
            {
                "v": 1,
                "strict": True,
                "repos": {
                    "SimonBarnett/bobiverse": {"priority": 1},
                    "SimonBarnett/agentic_fomprep": {"priority": 2},
                },
            }
        ),
        encoding="utf-8",
    )
    (chair / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [{"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#1"}], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    code, payload = _run("focus_present", chair, digest)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["has_bobiverse"] is True


def test_focus_present_finding_when_strict_missing_bobiverse_with_unaccepted(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "focus.json").write_text(
        json.dumps({"v": 1, "strict": True, "repos": {"SimonBarnett/Club-Madeira": {"priority": 1}}}),
        encoding="utf-8",
    )
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#99",
                        "url": "https://github.com/SimonBarnett/bobiverse/issues/99",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    code, payload = _run("focus_present", chair, digest)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["has_bobiverse"] is False
    assert any("bobiverse" in f.lower() for f in payload["findings"])


def test_focus_present_finding_when_strict_empty_repos_with_unaccepted(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "focus.json").write_text(
        json.dumps({"v": 1, "strict": True, "repos": {}}),
        encoding="utf-8",
    )
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [{"repo": "SimonBarnett/bobiverse", "task": "FR", "id": "#2"}],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    code, payload = _run("focus_present", chair, digest)
    assert code == 1, payload
    assert any("empty" in f.lower() or "missing" in f.lower() for f in payload["findings"])


def test_seats_stuck_doing_stale_busy_when_accepted_empty(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "marchhare": {
                        "workers": {
                            "35600": {
                                "state": "doing",
                                "nick": "marchhare-35600",
                                "working_on": "FR SimonBarnett/bobiverse#1",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    code, payload = _run("seats_stuck_doing", chair, digest)
    assert code == 1, payload
    assert payload["ok"] is False
    assert any("accepted is empty" in f.lower() or "stale" in f.lower() for f in payload["findings"])
    assert any("BobCallback" in f or "working_on" in f for f in payload.get("remediation", []) + payload["findings"])


def test_seats_stuck_doing_nak_busy_repeat(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps(
            {
                "machines": {
                    "marchhare": {
                        "workers": {"1": {"state": "doing", "nick": "marchhare-1"}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (chair / "cmd-trace.log").write_text(
        "\n".join(
            [
                "bored nak busy marchhare-1",
                "offer: bored nak busy marchhare-1",
                "shop: bored nak busy nick=marchhare-1",
                "other line",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    code, payload = _run("seats_stuck_doing", chair, digest)
    assert code == 1, payload
    assert any("nak busy" in f.lower() for f in payload["findings"])


def test_seats_stuck_doing_age_over_15_min_without_wire(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    old = datetime(2000, 1, 1, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (chair / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [],
                "accepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#7",
                        "nick": "marchhare-9",
                        "accepted_ts": old,
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
                    "marchhare": {
                        "workers": {
                            "9": {
                                "state": "doing",
                                "nick": "marchhare-9",
                                "working_on": "FR SimonBarnett/bobiverse#7",
                                "state_ts": old,
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
    assert any("15" in f or "age" in f.lower() or "no ACK" in f for f in payload["findings"])


def test_seats_stuck_doing_reports_permission_error_counts(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text(
        json.dumps({"machines": {"m": {"workers": {"1": {"state": "idle", "nick": "m-1"}}}}}),
        encoding="utf-8",
    )
    (chair / "stdout.log").write_text(
        "ok\nPermissionError: digest\nPermissionError again\nWinError 5 Access is denied\n",
        encoding="utf-8",
    )
    code, payload = _run("seats_stuck_doing", chair, digest)
    assert "permission_error_count" in payload
    assert payload["permission_error_count"] >= 2
    # idle-only + permission noise may still be ok==True unless threshold fires
    assert code in (0, 1)
