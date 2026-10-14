"""FR #4231: tip-loop meta FAIL-supersede harvests must SKIP for any -Book.

Class of a-search#1839: after MRB FAIL-supersede of tip-loop meta (#1771/#1837),
Invoke-BobiverseHarvest -Book harvest-agent-skills with Lesson restating
Thin FAIL-supersede / twin-close already on main still opened a twin tip.
FR #2970/#2991 cues missed tip-loop meta + already-on-main wording.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

# Exact class from issue #4231 / a-search tip #1839
TIP_LOOP_SUMMARY = (
    "MRB #1771 FAIL-superseded tip-loop meta; closed twin #1837; "
    "Thin FAIL-supersede already on main"
)
TIP_LOOP_LESSON = (
    "a-search harvest tip-loop meta: FAIL-supersede tips that only restate "
    "Thin FAIL-supersede / twin-close already on main; cite main bullets; "
    "DONE FAIL; do not reopen"
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


def test_fr4231_script_documents_tip_loop_meta_skip():
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "FR #4231" in text
    assert "tip-loop" in text.lower() or "tip[- ]?loop" in text
    assert "Test-HarvestFailSupersedeProcessLoop" in text


def test_fr4231_intake_detects_tip_loop_meta_thin_twin():
    blob = TIP_LOOP_SUMMARY + "\n" + TIP_LOOP_LESSON
    assert intake.is_fail_supersede_thin_twin_lesson(blob)
    assert intake.is_fail_supersede_thin_twin_lesson(
        "FAIL-supersede tip-loop meta; Thin FAIL-supersede already on main"
    )
    assert intake.is_fail_supersede_thin_twin_lesson(
        "FAIL-superseded; only restate Thin FAIL-supersede twin-close already on main"
    )
    # Bare FAIL-supersede + product lesson must NOT match (MRB #2973 spirit).
    assert not intake.is_fail_supersede_thin_twin_lesson(
        "Earlier MRB FAIL-superseded a twin; MSI RunInstall: Copy-BobiverseVersion "
        "must honour -MsiProductVersion"
    )


def test_fr4231_harvest_skips_tip_loop_meta_with_book_harvest_agent_skills(
    tmp_path: Path,
):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Book",
        "harvest-agent-skills",
        "-Summary",
        TIP_LOOP_SUMMARY,
        "-Lesson",
        TIP_LOOP_LESSON,
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_fr4231_harvest_skips_tip_loop_meta_default_book(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        TIP_LOOP_SUMMARY,
        "-Lesson",
        TIP_LOOP_LESSON,
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr4231_product_lesson_still_posts_with_fail_supersede_mention(tmp_path: Path):
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
