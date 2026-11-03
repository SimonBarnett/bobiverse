"""FR #6063: ticket_closure monitor (detect closes; no queue / !assign)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"


def _run(chair: Path, digest: Path, env: dict | None = None) -> tuple[int, dict]:
    import os

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
    (chair / "focus.json").write_text(
        json.dumps({"v": 1, "repos": {"SimonBarnett/bobiverse": {"priority": 1}}}),
        encoding="utf-8",
    )
    return chair, digest


def _fixture(path: Path) -> Path:
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
                    {
                        "kind": "pr",
                        "event": "closed",
                        "merged": False,
                        "repo": "SimonBarnett/bobiverse",
                        "number": 13,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fr6063_synthetic_closes_exit_1(tmp_path: Path):
    chair, digest = _homes(tmp_path)
    fx = _fixture(tmp_path / "events.json")
    code, payload = _run(chair, digest, {"JEEVES_TICKET_CLOSURE_FIXTURE": str(fx)})
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["check"] == "ticket_closure"
    closed = payload.get("closed") or []
    assert len(closed) == 3
    kinds = {c.get("event") for c in closed}
    assert "closed" in kinds
    assert "merged" in kinds
    assert not (chair / "queue.json").exists()
    src = (MONITOR / "ticket_closure.py").read_text(encoding="utf-8")
    assert "!assign" not in src
    assert "Never writes queue.json" in src


def test_fr6063_no_new_closes_exit_0(tmp_path: Path):
    chair, digest = _homes(tmp_path)
    fx = _fixture(tmp_path / "events.json")
    env = {"JEEVES_TICKET_CLOSURE_FIXTURE": str(fx)}
    first, _ = _run(chair, digest, env)
    assert first == 1
    q_before = (chair / "queue.json").exists()
    code, payload = _run(chair, digest, env)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload.get("closed") == []
    assert (chair / "queue.json").exists() is q_before
