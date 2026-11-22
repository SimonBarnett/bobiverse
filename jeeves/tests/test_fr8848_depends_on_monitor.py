"""FR #8848: token-free depends_on monitor (offer while depend OPEN)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
START = REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
INVOKE = REPO / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"


def _run(chair: Path, digest: Path, extra: list[str] | None = None) -> tuple[int, dict]:
    argv = [sys.executable, str(MONITOR / "depends_on.py"), *(extra or [])]
    if chair is not None:
        argv += ["--chair-home", str(chair), "--digest-home", str(digest)]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MONITOR),
    )
    line = (proc.stdout or "").strip().splitlines()[-1]
    return proc.returncode, json.loads(line)


def _queue(tmp: Path, doc: dict) -> tuple[Path, Path]:
    chair = tmp / "chair"
    digest = tmp / "digest"
    chair.mkdir()
    digest.mkdir()
    (chair / "queue.json").write_text(json.dumps(doc), encoding="utf-8")
    return chair, digest


def test_offered_while_depend_open_exits_1(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#9",
                    "number": 9,
                    "body": "Depends-on: (none)\n",
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "number": 10,
                    "offered_to": "marchhare-1",
                    "body": "Depends-on: #9\n",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 1
    assert payload["ok"] is False
    assert payload["violations"][0]["open"] == ["SimonBarnett/bobiverse#9"]


def test_skipped_with_depends_open_exits_0(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#9",
                    "number": 9,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "number": 10,
                    "status": "skipped",
                    "body": "Depends-on: #9\n",
                },
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["ok"] is True
    assert payload["violations"] == []


def test_no_depends_rows_soft_ok(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#3",
                    "labels": ["hold"],
                    "offered_to": "marchhare-1",
                    "body": "HOLD: waiting on a human\n",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["soft_ok"] == "no_depends_on_rows"


def test_closed_depend_in_done_is_ok(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "number": 10,
                    "offered_to": "marchhare-1",
                    "body": "Depends-on: #9\n",
                }
            ],
            "accepted": [],
            "done": [
                {"repo": "SimonBarnett/bobiverse", "id": "#9", "number": 9},
            ],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["ok"] is True


def test_live_homes_soft_ok_when_product_not_on_tip():
    code, payload = _run(None, None, extra=[])
    assert code == 0
    assert payload["soft_ok"] == "product_not_on_tip"


def test_monitor_start_lists_depends_on():
    text = START.read_text(encoding="utf-8")
    assert "`depends_on`" in text
    invoke = INVOKE.read_text(encoding="utf-8")
    assert "depends_on" in invoke
    assert (REPO / "jeeves" / "scripts" / "Test-JeevesMonitorDependsOn.ps1").is_file()
    skill = (
        REPO
        / "jeeves"
        / ".grok"
        / "skills"
        / "bobiverse-jeeves-agent-depends-on"
        / "SKILL.md"
    )
    assert skill.is_file()
    assert "depends_on" in skill.read_text(encoding="utf-8")
