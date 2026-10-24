"""FR #4953: harvest twin-check open+recent harvest-lesson PRs by title stem.

Cross-seat reworded tips that restated the same a-search /selftest playbook
(#4866/#4876 vendor secrets; #4871/#4873/#4874/#4877 MSSQL) must skip with
lesson_already_covered (or open_lesson_twin) and cite the existing PR.
HTTP vendor-secrets and MSSQL connect gates stay distinct.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import intake

REPO = "SimonBarnett/a-search"
SKILL = ".grok/skills/harvest-agent-skills/SKILL.md"

VENDOR_A = (
    "Fixture-only /selftest probes must not require vendor secrets on the entry box"
)
VENDOR_B = (
    "Fixture-only /selftest probes must not require vendor secrets on entry; "
    "gate assertCreds behind httpRequest"
)
MSSQL_A = (
    "Local provider /selftest: gate MSSQL/feed checks behind injectable connect "
    "so entry fixture probes stay green without madeiradb secrets"
)
MSSQL_B = (
    "Impact entry /selftest must not require MSSQL_* unless deps.connect is injected"
)
MSSQL_C = (
    "MSSQL /selftest fixture probes must skip mssqlConfigFromEnv when connect is absent"
)


def _pr(
    number: int,
    title: str,
    lesson: str,
    seat: str,
    *,
    closed: bool = False,
    hours_ago: float = 1.0,
) -> dict:
    created = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "repo": REPO,
        "number": number,
        "title": title,
        "body": (
            f"Lessons:\n- {lesson}\n\n---\n"
            f"_source machine=`flamingo` agent=`Invoke-BobiverseHarvest` "
            f"book=`harvest-agent-skills` ver=`-` seat=`{seat}`_\n"
        ),
        "labels": ["via-intake", "harvest-lesson"],
        "url": f"https://github.com/{REPO}/pull/{number}",
        "closed": closed,
        "createdAt": created.isoformat().replace("+00:00", "Z"),
    }


def test_title_stems_match_vendor_secret_truncation():
    a = "lesson(harvest-agent-skills): Fixture-only /selftest probes must not require vendor secrets on the ent..."
    b = "lesson(harvest-agent-skills): Fixture-only /selftest probes must not require vendor secrets on entry; gate"
    assert intake.harvest_lesson_title_stems_match(a, b)
    assert intake.harvest_pr_covers_new_lesson(
        a, VENDOR_A, VENDOR_B, new_title=b
    )


def test_title_stems_do_not_merge_http_and_mssql():
    http_t = "lesson(harvest-agent-skills): Fixture-only /selftest probes must not require vendor secrets"
    mssql_t = "lesson(harvest-agent-skills): Local provider /selftest: gate MSSQL/feed checks behind injectable"
    assert not intake.harvest_lesson_title_stems_match(http_t, mssql_t)
    assert not intake.harvest_pr_covers_new_lesson(
        http_t, VENDOR_A, MSSQL_A, new_title=mssql_t
    )


def test_mssql_reword_twins_match_via_lesson_text():
    t1 = "lesson(harvest-agent-skills): Local provider /selftest: gate MSSQL/feed checks behind injectable conne..."
    t2 = "lesson(harvest-agent-skills): Impact entry /selftest must not require MSSQL_* unless deps.connect is i..."
    t3 = "lesson(harvest-agent-skills): MSSQL /selftest fixture probes must skip mssqlConfigFromEnv..."
    assert intake.harvest_pr_covers_new_lesson(t1, MSSQL_A, MSSQL_B, new_title=t2)
    assert intake.harvest_pr_covers_new_lesson(t1, MSSQL_A, MSSQL_C, new_title=t3)


def test_cross_seat_open_twin_is_found():
    filer = intake.FakeGitHubFiler()
    filer.prs.append(
        _pr(
            4866,
            "lesson(harvest-agent-skills): Fixture-only /selftest probes must not require vendor secrets on the ent...",
            VENDOR_A,
            "flamingo-15516",
        )
    )
    hit = intake.find_open_harvest_lesson_twin(
        filer, REPO, [VENDOR_B], seat="flamingo-36472"
    )
    assert hit is not None
    assert hit["number"] == 4866


def test_recent_closed_twin_is_found():
    filer = intake.FakeGitHubFiler()
    filer.prs.append(
        _pr(
            4871,
            "lesson(harvest-agent-skills): Local provider /selftest: gate MSSQL/feed checks behind injectable conne...",
            MSSQL_A,
            "win-mpre8vi4u6u-21924",
            closed=True,
            hours_ago=2.0,
        )
    )
    hit = intake.find_recent_harvest_lesson_twin(
        filer, REPO, [MSSQL_B], new_title="lesson(harvest-agent-skills): Impact entry /selftest must not require MSSQL_*"
    )
    assert hit is not None
    assert hit["number"] == 4871


def test_file_submission_cross_seat_links_open_twin(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[SKILL] = "# harvest-agent-skills\n\n## Harvested lessons (intake)\n"
    filer.prs.append(
        _pr(
            4866,
            "lesson(harvest-agent-skills): Fixture-only /selftest probes must not require vendor secrets on the ent...",
            VENDOR_A,
            "flamingo-15516",
        )
    )
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: fixture selftest vendor secrets again",
            "body": f"Session summary:\nfixture selftest vendor secrets\n\nLessons:\n- {VENDOR_B}\n",
            "source": {
                "skill_book": "harvest-agent-skills",
                "agent": "Invoke-BobiverseHarvest",
                "seat": "flamingo-36472",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_4953_open")
    assert rec["state"] in ("open_lesson_twin", "lesson_already_covered")
    assert rec.get("url") == "https://github.com/SimonBarnett/a-search/pull/4866"
    assert len([p for p in filer.prs if not p.get("closed")]) == 1


def test_file_submission_recent_closed_is_already_covered(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[SKILL] = "# harvest-agent-skills\n\n## Harvested lessons (intake)\n"
    filer.prs.append(
        _pr(
            4871,
            "lesson(harvest-agent-skills): Local provider /selftest: gate MSSQL/feed checks behind injectable conne...",
            MSSQL_A,
            "win-mpre8vi4u6u-21924",
            closed=True,
            hours_ago=1.5,
        )
    )
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: impact mssql selftest again",
            "body": f"Session summary:\nimpact fixture selftest skip mssql without connect\n\nLessons:\n- {MSSQL_B}\n",
            "source": {
                "skill_book": "harvest-agent-skills",
                "agent": "Invoke-BobiverseHarvest",
                "seat": "flamingo-15516",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_4953_closed")
    assert rec["state"] == "lesson_already_covered"
    assert rec.get("url") == "https://github.com/SimonBarnett/a-search/pull/4871"
    assert [p for p in filer.prs if not p.get("closed")] == []


def test_unrelated_lesson_still_files(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[SKILL] = "# harvest-agent-skills\n\n## Harvested lessons (intake)\n"
    filer.prs.append(
        _pr(
            4866,
            "lesson(harvest-agent-skills): Fixture-only /selftest probes must not require vendor secrets on the ent...",
            VENDOR_A,
            "flamingo-15516",
        )
    )
    fresh = "Prefer D: job worktrees and write .bobiverse-seat right after worktree add"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: job worktree seat marker",
            "body": f"Session summary:\nFR work\n\nLessons:\n- {fresh}\n",
            "source": {
                "skill_book": "harvest-agent-skills",
                "agent": "Invoke-BobiverseHarvest",
                "seat": "flamingo-36472",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_4953_fresh")
    assert rec["state"] == "filed"
    assert len([p for p in filer.prs if not p.get("closed")]) == 2
