"""MRB #1538 nits: focus_redundant_items monitor (FR #1520)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"


def _run(chair: Path, digest: Path) -> tuple[int, dict]:
    r = subprocess.run(
        [
            sys.executable,
            str(MONITOR / "focus_redundant_items.py"),
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


def test_monitor_finds_redundant_item_under_repo_focus(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "focus.json").write_text(
        json.dumps(
            {
                "v": 1,
                "strict": True,
                "repos": {"SimonBarnett/bobiverse": {"priority": 1}},
                "items": {
                    "SimonBarnett/bobiverse#1102": {
                        "repo": "SimonBarnett/bobiverse",
                        "id": "#1102",
                        "rank": 6,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    code, payload = _run(chair, digest)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["redundant_count"] == 1
    assert any("1102" in x for x in payload["redundant"])


def test_monitor_ok_when_no_redundant_items(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "focus.json").write_text(
        json.dumps(
            {
                "v": 1,
                "strict": True,
                "repos": {"SimonBarnett/bobiverse": {"priority": 1}},
                "items": {
                    "SimonBarnett/Club-Madeira#9": {
                        "repo": "SimonBarnett/Club-Madeira",
                        "id": "#9",
                        "rank": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    code, payload = _run(chair, digest)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["redundant_count"] == 0


def test_monitor_handles_list_form_repos(tmp_path: Path):
    chair = tmp_path / "jeeves"
    digest = tmp_path / "bobiverse"
    chair.mkdir()
    digest.mkdir()
    (chair / "focus.json").write_text(
        json.dumps(
            {
                "v": 1,
                "strict": True,
                "repos": ["SimonBarnett/bobiverse"],
                "items": {
                    "SimonBarnett/bobiverse#42": {
                        "repo": "SimonBarnett/bobiverse",
                        "id": "#42",
                        "rank": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (digest / "digest.json").write_text("{}", encoding="utf-8")
    code, payload = _run(chair, digest)
    assert code == 1, payload
    assert payload["redundant_count"] == 1
