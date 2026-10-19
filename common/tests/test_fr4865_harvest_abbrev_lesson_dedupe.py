"""FR #4865: intake must not open a tip for an abbreviated restatement of a main lesson."""
from __future__ import annotations

from pathlib import Path

import intake

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"

FULL_402_LESSON = (
    "After agent 402 usage balance exhausted, keep out-of-fuel held until "
    "BOB_WORKER_OUT_OF_FUEL_MIN_HOLD_S and grok pct above "
    "BOB_WORKER_OUT_OF_FUEL_CLEAR_FLOOR_PCT (or turn_ended); never clear on "
    "soft available with pct at or below the floor."
)

# Exact abbreviated twin from closed tip #4863 (after #4860 merged the full bullet).
ABBREV_402_LESSON = (
    "After agent 402 usage balance exhausted, keep out-of-fuel held until "
    "MIN_HOLD_S and pct above CLEAR_FLOOR_PCT (or turn_ended); never clear on "
    "soft available at or below the floor"
)

HARVEST_WITH_FULL = f"""# Harvest

## Harvested lessons (intake)

- {FULL_402_LESSON}
"""


def test_fr4865_filter_drops_abbreviated_402_twin():
    assert intake.filter_new_lessons(HARVEST_WITH_FULL, [ABBREV_402_LESSON]) == []
    assert intake.filter_new_lessons(HARVEST_WITH_FULL, [FULL_402_LESSON]) == []


def test_fr4865_filter_keeps_unrelated_lesson():
    fresh = "Prefer D: job worktrees and write .bobiverse-seat right after worktree add"
    assert intake.filter_new_lessons(HARVEST_WITH_FULL, [fresh]) == [fresh]


def test_fr4865_filter_keeps_more_specific_when_only_abbrev_on_main():
    """Full env-named lesson is not dropped when main only has the short form."""
    existing = f"# Harvest\n\n- {ABBREV_402_LESSON}\n"
    assert intake.filter_new_lessons(existing, [FULL_402_LESSON]) == [FULL_402_LESSON]


def test_fr4865_intake_harvest_abbrev_is_lesson_already_covered(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = HARVEST_WITH_FULL
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: abbreviated 402 out-of-fuel twin",
            "body": (
                "Session summary:\n"
                "MRB #4860 harvest tip PASS unique 402 out-of-fuel min-hold+pct-floor "
                "lesson; MERGED @ fcf6d560\n\n"
                f"Lessons:\n- {ABBREV_402_LESSON}\n"
            ),
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
                "seat": "win-mpre8vi4u6u-23216",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_4865_abbrev")
    assert rec["state"] == "lesson_already_covered"
    assert filer.prs == []
