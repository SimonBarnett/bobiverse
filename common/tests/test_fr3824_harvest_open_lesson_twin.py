"""FR #3824: harvest must not open twin lesson PRs for the same seat+lesson.

When an open harvest-lesson PR already carries the same lesson text from the
same seat, intake links that PR instead of filing a second tip. Early idem
claim (state=filing) also blocks same-key races during create_pr.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
# Product playbook (no FAIL-supersede / thin-harvest process cues). FR #3827
# skips tip-#3826-class FAIL-supersede restatements before the open-twin gate;
# this fixture must stay a real product lesson so open_lesson_twin is exercised.
LESSON = (
    "FR-3817: queue _repo_key case-fold; collapse_case_variant_twins prefers "
    "mixed-case + non-empty GIT line; discover_repos dedupes casing"
)


def _norm(*, summary: str, lesson: str, seat: str, idem: str):
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": f"harvest: {summary}"[:200],
            "body": (
                f"Session summary:\n{summary}\n\n"
                f"Lessons:\n- {lesson}\n"
            ),
            "idempotency_key": idem,
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
                "machine": "marchhare",
                "seat": seat,
            },
        }
    )
    assert err is None, err
    return norm


def test_find_open_harvest_lesson_twin_matches_seat_and_lesson():
    filer = intake.FakeGitHubFiler()
    filer.prs.append(
        {
            "repo": REPO,
            "number": 3822,
            "title": f"lesson(harvest): {LESSON[:72]}...",
            "body": (
                "Lessons:\n"
                f"- {LESSON}\n\n"
                "---\n"
                "_via-intake id=`in_aaa` ts=`2026-10-09T22:40:22Z`_\n"
                "_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` "
                "book=`harvest` ver=`-` seat=`marchhare-42664`_\n"
            ),
            "labels": ["via-intake", "harvest-lesson"],
            "url": f"https://github.com/{REPO}/pull/3822",
            "branch": "intake/in_aaa",
            "draft": False,
        }
    )
    hit = intake.find_open_harvest_lesson_twin(
        filer, REPO, [LESSON], seat="marchhare-42664"
    )
    assert hit is not None
    assert hit["number"] == 3822

    miss_seat = intake.find_open_harvest_lesson_twin(
        filer, REPO, [LESSON], seat="marchhare-960"
    )
    assert miss_seat is None

    miss_lesson = intake.find_open_harvest_lesson_twin(
        filer, REPO, ["totally different playbook line"], seat="marchhare-42664"
    )
    assert miss_lesson is None


def test_second_file_submission_links_open_lesson_twin(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n\n## Harvested lessons (intake)\n"
    summary = "MRB bobiverse#3818 PASS: FR-3817 case-insensitive queue repo dedupe"
    norm1 = _norm(
        summary=summary,
        lesson=LESSON,
        seat="marchhare-42664",
        idem="hv-fr3824-a",
    )
    rec1 = intake.file_submission(tmp_path, norm1, filer, intake_id="in_fr3824a")
    assert rec1["state"] == "filed"
    assert len(filer.prs) == 1

    # Different idempotency key + slightly different summary (DONE retry),
    # same seat + same lesson -> must link the open tip, not open #3823.
    norm2 = _norm(
        summary=summary + " (retry)",
        lesson=LESSON,
        seat="marchhare-42664",
        idem="hv-fr3824-b",
    )
    rec2 = intake.file_submission(tmp_path, norm2, filer, intake_id="in_fr3824b")
    assert rec2["state"] == "open_lesson_twin"
    assert rec2["url"] == filer.prs[0]["url"]
    assert rec2.get("number") == filer.prs[0]["number"]
    assert len(filer.prs) == 1, "must not open a twin lesson PR"


def test_filing_state_blocks_same_idem_key_race(tmp_path: Path):
    """FR #3824: claim idem while state=filing so a second POST cannot twin."""
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n"
    payload = {
        "kind": "harvest",
        "repo": REPO,
        "title": "harvest: race",
        "body": "Session summary:\nrace\n\nLessons:\n- unique race lesson line for 3824\n",
        "idempotency_key": "hv-fr3824-race",
        "source": {"skill_book": "harvest", "seat": "marchhare-1"},
    }
    # Simulate in-flight claim (create_pr still running).
    intake._save_record(
        tmp_path,
        {
            "intake_id": "in_racing",
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: race",
            "idempotency_key": "hv-fr3824-race",
            "state": "filing",
            "url": None,
            "queued": False,
        },
    )
    result = intake.process_intake(tmp_path, payload, filer=filer)
    assert result.status == 202
    assert result.body.get("duplicate") is True
    assert result.body.get("intake_id") == "in_racing"
    assert filer.prs == []


def test_harvest_script_documents_open_lesson_twin_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #3824" in text
    assert "Test-HarvestOpenLessonTwin" in text or "open lesson twin" in text.lower()
    assert "SKIPPED harvest open lesson twin" in text


def test_harvest_idem_key_prefers_seat_and_lesson():
    """Same seat+lesson must share an idempotency key even when Summary drifts."""
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #3824" in text
    assert "seatNick" in text or "BOB_NICK" in text
    # Prefer lesson-stable key material over raw Summary title/body alone.
    assert "lessonKey" in text or "normalized lesson" in text.lower() or (
        "Repo|book" in text or "bookName|$seatNick" in text or "$lessonKey" in text
    )


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
        env={
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "BOB_NICK": "marchhare-42664",
        },
    )


def test_harvest_ps_skip_helper_exists_for_open_twin():
    # Source pin: function or skip string must exist (behaviour covered in intake tests).
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "SKIPPED harvest open lesson twin (FR #3824)" in text
