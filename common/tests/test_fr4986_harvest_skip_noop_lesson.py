"""FR #4986: Invoke-BobiverseHarvest must not open tips when lesson is skip/empty.

Class of euroflo#24 lesson(harvest): skip after MRB Duplicate disposition.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST.is_file():
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
        timeout=90,
        cwd=str(ROOT),
    )


def test_fr4986_script_documents_noop_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #4986" in text
    assert "Test-HarvestNoopOrEmptyLesson" in text
    assert "SKIPPED harvest noop/empty lesson" in text


def test_fr4986_skip_bare_skip_lesson(tmp_path: Path):
    """euroflo#24 class: Lessons: - skip after Duplicate disposition."""
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/euroflo",
        "-Summary",
        "MRB PASS CLOSED Duplicate disposition; no new playbook this session",
        "-Lesson",
        "skip",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest noop/empty lesson" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_fr4986_skip_empty_lesson_array(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "Session closeout with no new playbook",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest noop/empty lesson" in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr4986_skip_placeholder_lesson(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "Nothing new this session",
        "-Lesson",
        "(no new playbook line)",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest noop/empty lesson" in r.stdout


def test_fr4986_real_playbook_still_attempts_post(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "Pack stage: SkipAircNetworkInstallerExe with SkipMsi for disposable airc stage tests",
        "-Lesson",
        "Pack-BobiverseRelease: -SkipAircNetworkInstallerExe requires -SkipMsi so disposable stages skip UAC installer PyInstaller.",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest noop/empty lesson" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout or "SKIPPED harvest" in r.stdout


def test_fr4986_intake_extract_drops_skip_and_none():
    import intake

    assert intake.extract_harvest_lessons(
        "Session summary:\nMRB Duplicate\n\nLessons:\n- skip\n"
    ) == []
    assert intake.extract_harvest_lessons(
        "Session summary:\nx\n\nLessons:\n- none\n- n/a\n- (no new playbook line)\n"
    ) == []
    assert intake.extract_harvest_lessons(
        "Session summary:\nx\n\nLessons:\n- skip\n- Real durable playbook about ear keepalive\n"
    ) == ["Real durable playbook about ear keepalive"]
    assert intake.is_noop_harvest_lesson("skip")
    assert intake.is_noop_harvest_lesson("N/A")
    assert not intake.is_noop_harvest_lesson(
        "Pack-BobiverseRelease: -SkipAircNetworkInstallerExe requires -SkipMsi"
    )
