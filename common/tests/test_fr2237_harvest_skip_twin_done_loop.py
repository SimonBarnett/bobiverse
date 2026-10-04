"""FR #2237: harvest must not file skill issues for twin-DONE-only sessions."""
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


def test_harvest_script_documents_twin_done_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #2237" in text
    assert "Test-HarvestTwinDoneLoop" in text
    assert "SKIPPED harvest twin-DONE loop" in text


def test_harvest_skips_twin_done_summary(tmp_path: Path):
    r = _run_harvest(
        "-Summary",
        "FR #2204 closed Duplicate of #2020; DONE citing merged #2080 MSI Node soft-fail",
        "-Lesson",
        "Closed skill-harvest twin: ACK, confirm Duplicate close, DONE with covering PR URL",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest twin-DONE loop" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    assert not list((tmp_path / "harvest-outbox").glob("*.json")) if (tmp_path / "harvest-outbox").exists() else True


def test_harvest_skips_nested_twin_summary(tmp_path: Path):
    r = _run_harvest(
        "-Summary",
        "FR #2235 nested twin of #2111/#2161; DONE citing #2161",
        "-Lesson",
        "ACK then DONE citing covering PR; close as Duplicate of #N as part of DONE",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest twin-DONE loop" in r.stdout


def test_harvest_still_posts_real_new_playbook(tmp_path: Path):
    """Real new playbooks still attempt POST (or queue) — not skipped."""
    r = _run_harvest(
        "-Summary",
        "FR #2237: skip twin-DONE harvest loop so nested skill twins stop stacking",
        "-Lesson",
        "Invoke-BobiverseHarvest skips twin-DONE-only summaries (FR #2237).",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest twin-DONE loop" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
