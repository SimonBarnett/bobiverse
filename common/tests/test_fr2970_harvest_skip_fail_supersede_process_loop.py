"""FR #2970: do not re-promote FAIL-supersede / wrong-book MRB process lessons into harvest."""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
MRB_SKILL = "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

PROCESS_LESSON = (
    "Harvest-lesson MRB: process playbooks (merge origin/main first, docs/mrb-N after "
    "skill merge) belong in bobiverse-bob-job-mrb — if intake parks them under harvest "
    "while that coverage is on main, FAIL-supersede and close; never merge a second "
    "copy that says keep MRB process in harvest"
)

HARVEST_COVERED = """# Harvest

## Harvested lessons (intake)

- Harvest-lesson MRB playbooks (fold duplicates into behind-main #1647) belong in `bobiverse-bob-job-mrb`. If intake files them under `harvest`, MRB moves/folds them there - do not land a second copy in this book (MRB #2740 / #2749).
"""

MRB_COVERED = """# bobiverse bob - MRB job

**Behind-main:** merge origin/main into the tip before merge.
**Harvest promote order:** merge the skill/promote PR first, then open docs/mrb-N from the new origin/main tip.
## Harvest-lesson intake PRs (FR #2705)
Twin harvest-lesson PRs: FAIL-superseded the later one.
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


def test_fr2970_detects_mrb_process_routing_lesson():
    assert intake.is_mrb_process_routing_lesson(PROCESS_LESSON)
    assert intake.is_mrb_process_routing_lesson(
        "FAIL-supersede wrong-book lesson parked under harvest"
    )
    assert intake.is_mrb_process_routing_lesson(
        "FAIL-supersede wrong-book tip; keep MRB process out of harvest"
    )
    assert not intake.is_mrb_process_routing_lesson(
        "MSI RunInstall: Copy-BobiverseVersion must honour -MsiProductVersion"
    )
    # MRB #2973: bare FAIL-supersede in a session summary is not process-routing.
    assert not intake.is_mrb_process_routing_lesson(
        "MRB #2967 FAIL-superseded: closed unmerged; filed covering PR"
    )


def test_fr2970_filter_new_lessons_drops_already_present():
    existing = HARVEST_COVERED + f"\n- {PROCESS_LESSON}\n"
    assert intake.filter_new_lessons(existing, [PROCESS_LESSON]) == []
    assert intake.filter_new_lessons(existing, ["Brand new tip about outbox"]) == [
        "Brand new tip about outbox"
    ]


def test_fr2970_process_lesson_with_coverage_skips_pr(tmp_path: Path):
    """Chair must not open lesson(harvest) when process routing is already on main."""
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = HARVEST_COVERED
    filer.repo_files[MRB_SKILL] = MRB_COVERED
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #2967 FAIL-superseded: process under harvest",
            "body": (
                "Session summary:\n"
                "MRB #2967 FAIL-superseded: harvest-lesson MRB process playbook "
                "parked under harvest; job-mrb + harvest #2740/#2749 already cover; "
                "closed unmerged\n\n"
                f"Lessons:\n- {PROCESS_LESSON}\n"
            ),
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
                "seat": "win-mpre8vi4u6u-11748",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_2970_skip")
    assert rec["state"] == "lesson_already_covered"
    assert filer.prs == []
    assert filer.issues == []


def test_fr2970_explicit_harvest_book_reroutes_process_lesson_when_not_covered(
    tmp_path: Path,
):
    """If coverage is missing, open lesson(bobiverse-bob-job-mrb) — never lesson(harvest)."""
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n\nIntro only.\n"
    filer.repo_files[MRB_SKILL] = "# MRB\n\nThin book without promote order.\n"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB process tip",
            "body": (
                "Session summary:\nprocess tip\n\n"
                f"Lessons:\n- {PROCESS_LESSON}\n"
            ),
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_2970_reroute")
    assert rec["state"] == "filed"
    assert rec.get("skill_book") == "bobiverse-bob-job-mrb"
    assert filer.prs
    pr = filer.prs[-1]
    assert str(pr["title"]).startswith("lesson(bobiverse-bob-job-mrb):")
    paths = [f.get("path") for f in pr.get("files") or []]
    assert MRB_SKILL in paths
    assert HARVEST_SKILL not in paths


def test_fr2970_duplicate_lesson_already_in_target_skips(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    tip = "Prefer durable worktree paths under a roomy drive"
    filer.repo_files[HARVEST_SKILL] = (
        f"# Harvest\n\n## Harvested lessons (intake)\n\n- {tip}\n"
    )
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: same tip again",
            "body": f"Session summary:\nagain\n\nLessons:\n- {tip}\n",
            "source": {"skill_book": "harvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_2970_dup")
    assert rec["state"] == "lesson_already_covered"
    assert filer.prs == []


def test_fr2970_harvest_script_skips_fail_supersede_process_loop(tmp_path: Path):
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "FR #2970" in text
    assert "Test-HarvestFailSupersedeProcessLoop" in text
    assert "SKIPPED harvest FAIL-supersede process loop" in text

    r = _run_harvest(
        "-Summary",
        "MRB #2967 FAIL-superseded: harvest-lesson MRB process playbook parked under harvest; closed unmerged",
        "-Lesson",
        PROCESS_LESSON,
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_fr2970_harvest_still_posts_real_product_lesson(tmp_path: Path):
    r = _run_harvest(
        "-Summary",
        "FR #2948: MSI Copy-BobiverseVersion must honour ProductVersion",
        "-Lesson",
        "MSI RunInstall: Copy-BobiverseVersion must honour -MsiProductVersion and must not clobber InstallRoot\\VERSION",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout


def test_fr2970_bare_fail_supersede_summary_keeps_product_on_harvest(tmp_path: Path):
    """MRB #2973: FAIL-superseded in the summary alone must not re-route a product tip."""
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n\nIntro only.\n"
    filer.repo_files[MRB_SKILL] = MRB_COVERED
    tip = "MSI RunInstall: Copy-BobiverseVersion must honour -MsiProductVersion"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MSI ProductVersion after prior FAIL-supersede",
            "body": (
                "Session summary:\n"
                "Earlier MRB #2967 FAIL-superseded a twin; this tip is product MSI.\n\n"
                f"Lessons:\n- {tip}\n"
            ),
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_2970_product")
    assert rec["state"] == "filed"
    assert rec.get("skill_book") == "harvest"
    assert filer.prs
    pr = filer.prs[-1]
    assert str(pr["title"]).startswith("lesson(harvest):")
    paths = [f.get("path") for f in pr.get("files") or []]
    assert HARVEST_SKILL in paths
    assert MRB_SKILL not in paths
