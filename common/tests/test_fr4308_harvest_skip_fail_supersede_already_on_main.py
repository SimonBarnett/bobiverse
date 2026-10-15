"""FR #4308: FAIL-supersede + thinner tip + already on main must SKIP tip filing.

Class of a-search#1980 / tip-loop #2283: after MRB FAIL-superseded a thinner GBP hold
harvest tip (durable lesson already on main), Invoke-BobiverseHarvest -Repo a-search
still opened lesson tip #2283 for the FAIL-supersede playbook itself.

FR #2970/#2991/#3827/#4231 cues missed:
- "thinner ... harvest tip" (not contiguous "thin harvest tip")
- "FAIL-superseded: ... durable lesson already on main" (no "Thin FAIL-supersede" order)
- no tip-loop meta / belonging-in-job-mrb process cue

Bare FAIL-supersede + real product lesson must still post (MRB #2973).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

# Exact class from issue #4308 / a-search#1980 harvest that opened #2283
INCIDENT_SUMMARY = (
    "MRB #1980 FAIL-superseded: thinner GBP hold harvest tip closed unmerged; "
    "durable lesson already on main (mrb1739 pin / #1815; product #1668)"
)
INCIDENT_LESSON = (
    "a-search harvest-lesson MRB: FAIL-supersede thinner GBP/UK market-hold tip "
    "that only names session pins when harvest-agent-skills on main already has "
    "GBP/UK market-hold retarget floors + skip win32 synth FR#3717 (cite mrb1739 / #1815)"
)


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST_PS1),
            *extra,
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )


def test_fr4308_script_documents_already_on_main_thin_skip():
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "FR #4308" in text
    assert "Test-HarvestFailSupersedeProcessLoop" in text
    assert "already on main" in text.lower() or "already\\s+on\\s+main" in text


def test_fr4308_intake_detects_incident_thin_twin():
    blob = INCIDENT_SUMMARY + "\n" + INCIDENT_LESSON
    assert intake.is_fail_supersede_thin_twin_lesson(blob)
    assert intake.is_fail_supersede_thin_twin_lesson(
        "FAIL-superseded: thinner harvest tip; durable lesson already on main"
    )
    assert intake.is_fail_supersede_thin_twin_lesson(
        "MRB FAIL-supersede thinner tip closed unmerged; already on main"
    )
    # Bare FAIL-supersede + product lesson must NOT match (MRB #2973).
    assert not intake.is_fail_supersede_thin_twin_lesson(
        "Earlier MRB FAIL-superseded a twin; MSI RunInstall: Copy-BobiverseVersion "
        "must honour -MsiProductVersion"
    )


def test_fr4308_harvest_skips_incident_with_book_harvest_agent_skills(
    tmp_path: Path,
):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Book",
        "harvest-agent-skills",
        "-Summary",
        INCIDENT_SUMMARY,
        "-Lesson",
        INCIDENT_LESSON,
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_fr4308_harvest_skips_incident_default_book(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        INCIDENT_SUMMARY,
        "-Lesson",
        INCIDENT_LESSON,
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr4308_product_lesson_still_posts_with_fail_supersede_mention(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "Earlier MRB FAIL-superseded a twin; this tip is product MSI SkipCopy",
        "-Lesson",
        "MSI RunInstall: when -MsiProductVersion is set, SkipCopy so heat-laid scripts win",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
