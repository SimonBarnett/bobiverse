"""FR #6069: Phase-2 waiting_on registry narrows ticket_closure wakes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
REGISTRY = "ticket-closure-waiting.json"


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


def _fx(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "closed": [
                    {
                        "kind": "issue",
                        "event": "closed",
                        "repo": "SimonBarnett/bobiverse",
                        "number": 11,
                    },
                    {
                        "kind": "pr",
                        "event": "merged",
                        "repo": "SimonBarnett/bobiverse",
                        "number": 12,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fr6069_empty_registry_is_phase1(tmp_path: Path):
    chair, digest = _homes(tmp_path)
    fx = _fx(tmp_path / "events.json")
    (digest / REGISTRY).write_text(json.dumps({"waiting_on": []}), encoding="utf-8")
    code, payload = _run(chair, digest, {"JEEVES_TICKET_CLOSURE_FIXTURE": str(fx)})
    assert code == 1, payload
    nums = {c["number"] for c in payload.get("closed") or []}
    assert nums == {11, 12}


def test_fr6069_nonempty_registry_only_matching_ids(tmp_path: Path):
    chair, digest = _homes(tmp_path)
    fx = _fx(tmp_path / "events.json")
    (digest / REGISTRY).write_text(
        json.dumps({"waiting_on": ["SimonBarnett/bobiverse#11"]}),
        encoding="utf-8",
    )
    code, payload = _run(chair, digest, {"JEEVES_TICKET_CLOSURE_FIXTURE": str(fx)})
    assert code == 1, payload
    closed = payload.get("closed") or []
    assert [c["number"] for c in closed] == [11]
    assert not (digest / "queue.json").exists()
