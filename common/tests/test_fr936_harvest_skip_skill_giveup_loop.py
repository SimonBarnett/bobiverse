"""FR #936: harvest must not file skill issues for GIVEUP-of-skill sessions."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            *extra,
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )


def test_harvest_script_documents_skill_giveup_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #936" in text
    assert "Test-HarvestSkillGiveupLoop" in text
    assert "SKIPPED harvest skill GIVEUP loop" in text


def test_harvest_skips_giveup_skill_summary(tmp_path: Path):
    r = _run_harvest(
        "-Summary",
        "GIVEUP #935 skill harvest of #913; already merged",
        "-Lesson",
        "Skill harvest offered as FR: GIVEUP.",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest skill GIVEUP loop" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    assert not list((tmp_path / "harvest-outbox").glob("*.json")) if (tmp_path / "harvest-outbox").exists() else True


def test_harvest_still_posts_real_summary(tmp_path: Path):
    """Non-GIVEUP skill lessons still attempt POST (or queue on failure) — not skipped."""
    r = _run_harvest(
        "-Summary",
        "FR #866: ensure_outbox recreates empty outbox after drain; PR #914",
        "-Lesson",
        "Drain must recreate empty outbox.txt after atomic move.",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest skill GIVEUP loop" not in r.stdout
    # 127.0.0.1:9 should fail → QUEUED
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
