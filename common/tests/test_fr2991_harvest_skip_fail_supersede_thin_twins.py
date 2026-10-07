"""FR #2991: FAIL-supersede skip must catch thin already-covered harvest twins.

FR #2970 / PR #2973 required process cues (job-mrb / wrong-book). Thin tips like
'fleet-ops already cover … close thin Harvested-lessons twins' after FAIL-supersede
still opened lesson(harvest) (#2990 after #2988). Extend client + intake gates.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
MRB_SKILL = "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
FLEET_SKILL = "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

# Exact class from issue #2991 / tip #2990
THIN_TWIN_LESSON = (
    "When fleet-ops known-failure + harvested rule already cover MSI "
    "SkipCopy/sync-skip-stale-worktree (FR #2982), close thin Harvested-lessons "
    "intake twins unmerged citing the product/move PRs"
)
THIN_TWIN_SUMMARY = (
    "MRB #2988 FAIL-superseded: thin harvest twin of fleet-ops FR #2982 SkipCopy "
    "already on main via #2983/#2984; closed unmerged"
)

HARVEST_COVERED = """# Harvest

## Harvested lessons (intake)

- Harvest-lesson MRB playbooks belong in `bobiverse-bob-job-mrb`. If intake files them under `harvest`, MRB moves/folds them there - do not land a second copy in this book (MRB #2740 / #2749).
"""

MRB_COVERED = """# bobiverse bob - MRB job

**Behind-main:** merge origin/main into the tip before merge.
**Harvest promote order:** merge the skill/promote PR first, then open docs/mrb-N from the new origin/main tip.
## Harvest-lesson intake PRs (FR #2705)
Twin harvest-lesson PRs: FAIL-superseded the later one.
"""

FLEET_COVERED = """# fleet-ops

| Quiet MSI upgrade loses heat-laid scripts/tools/skills (FR #2982) | dirty/behind | SkipCopy + sync-skip-stale-worktree |
- MSI RunInstall (FR #2982): when `-MsiProductVersion` is set, SkipCopy; Sync must sync-skip-stale-worktree.
"""


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


def test_fr2991_detects_thin_already_covered_twin_lesson():
    blob = THIN_TWIN_SUMMARY + "\n" + THIN_TWIN_LESSON
    assert intake.is_fail_supersede_thin_twin_lesson(blob)
    assert intake.is_fail_supersede_thin_twin_lesson(
        "FAIL-superseded; already cover SkipCopy; close thin twins unmerged"
    )
    # Process-routing path still works (FR #2970).
    assert intake.is_mrb_process_routing_lesson(
        "FAIL-supersede wrong-book lesson parked under harvest"
    )
    # Bare FAIL-supersede + product MSI tip must NOT match thin-twin (MRB #2973 spirit).
    assert not intake.is_fail_supersede_thin_twin_lesson(
        "Earlier MRB FAIL-superseded a twin; MSI RunInstall: Copy-BobiverseVersion "
        "must honour -MsiProductVersion"
    )
    assert not intake.is_fail_supersede_thin_twin_lesson(
        "MSI RunInstall: Copy-BobiverseVersion must honour -MsiProductVersion"
    )


def test_fr2991_intake_skips_thin_twin_when_coverage_present(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = HARVEST_COVERED
    filer.repo_files[MRB_SKILL] = MRB_COVERED
    filer.repo_files[FLEET_SKILL] = FLEET_COVERED
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #2988 FAIL-superseded thin twin",
            "body": (
                f"Session summary:\n{THIN_TWIN_SUMMARY}\n\n"
                f"Lessons:\n- {THIN_TWIN_LESSON}\n"
            ),
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
                "seat": "win-mpre8vi4u6u-11748",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_2991_skip")
    assert rec["state"] == "lesson_already_covered"
    assert filer.prs == []
    assert filer.issues == []


def test_fr2991_harvest_script_skips_thin_twin_fail_supersede(tmp_path: Path):
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "FR #2991" in text
    assert "thin" in text.lower() and "already cover" in text.lower()

    r = _run_harvest(
        "-Summary",
        THIN_TWIN_SUMMARY,
        "-Lesson",
        THIN_TWIN_LESSON,
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_fr2991_product_msi_lesson_still_posts_after_fail_supersede_mention(tmp_path: Path):
    """FAIL-superseded in summary alone + product lesson must still queue (MRB #2973)."""
    r = _run_harvest(
        "-Summary",
        "Earlier MRB #2988 FAIL-superseded a twin; this tip is product MSI SkipCopy",
        "-Lesson",
        "MSI RunInstall: when -MsiProductVersion is set, SkipCopy so heat-laid scripts win",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
