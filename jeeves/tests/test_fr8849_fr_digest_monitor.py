"""FR #8849: token-free fr_digest monitor (child offered while digest held)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
START = REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
INVOKE = REPO / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"


def _run(chair: Path | None, digest: Path | None) -> tuple[int, dict]:
    argv = [sys.executable, str(MONITOR / "fr_digest.py")]
    if chair is not None and digest is not None:
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


def _child(body: str, offered: bool = True) -> dict:
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#20",
        "number": 20,
        "body": body,
    }
    if offered:
        row["offered_to"] = "marchhare-1"
    return row


def test_child_offered_while_digest_held_exits_1(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#11",
                    "number": 11,
                    "labels": ["fr-digest", "hold"],
                    "body": "Depends-on: (none)\n",
                },
                _child("Depends-on: #11\n"),
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 1
    assert payload["violations"][0]["held_digest"] == ["SimonBarnett/bobiverse#11"]


def test_unhold_allows_offer_exits_0(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#11",
                    "number": 11,
                    "labels": ["fr-digest"],
                    "body": "Depends-on: (none)\n",
                },
                _child("Depends-on: #11\n"),
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["ok"] is True
    assert payload["violations"] == []


def test_hold_without_fr_digest_is_not_this_check(tmp_path: Path):
    chair, digest = _queue(
        tmp_path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "id": "#11",
                    "number": 11,
                    "labels": ["hold"],
                },
                _child("Depends-on: #11\n"),
            ],
            "accepted": [],
            "done": [],
        },
    )
    code, payload = _run(chair, digest)
    assert code == 0
    assert payload["violations"] == []


def test_live_homes_soft_ok_when_product_not_on_tip():
    code, payload = _run(None, None)
    assert code == 0
    # FR #9455: BOB-G1 shared gate is on tip — never soft_ok=product_not_on_tip.
    # Empty live homes soft-ok as no_fr_digest_rows (or fr_digest_clear).
    assert payload["soft_ok"] != "product_not_on_tip"
    assert payload["soft_ok"] in ("no_fr_digest_rows", "fr_digest_clear")


def test_monitor_start_lists_fr_digest():
    assert "`fr_digest`" in START.read_text(encoding="utf-8")
    assert "fr_digest" in INVOKE.read_text(encoding="utf-8")
    assert (REPO / "jeeves" / "scripts" / "Test-JeevesMonitorFrDigest.ps1").is_file()
    skill = (
        REPO
        / "jeeves"
        / ".grok"
        / "skills"
        / "bobiverse-jeeves-agent-fr-digest"
        / "SKILL.md"
    )
    assert "fr_digest" in skill.read_text(encoding="utf-8")
