"""FR #4514: an explicit skill-book name beats FR #3004 keyword inference.

Incident: lesson text said the playbook belongs in bobiverse-bob-job-irc, but
done-miss inferred bobiverse-bob-worker and opened pull 4513. The durable
sentence was already in job-irc. That must be lesson_already_covered.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

REPO = "SimonBarnett/bobiverse"
IRC_SKILL = "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
WORKER_SKILL = "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST_PS1.is_file():
    HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

LESSON = (
    "A done-miss re-append rule belongs in bobiverse-bob-job-irc after the "
    "#2875 drained-outbox paragraph: re-append the same DONE only when the "
    "board is posted, the head SHA is unchanged, and the tip is 0 behind; "
    "if the head moved or the tip is behind, re-verify. A drained outbox is "
    "not a missing board. When the unqualified predecessor PR closed unmerged, "
    "the regression pin is that the absolute do-not-re-review sentence is absent."
)
SUMMARY = (
    "MRB PASS bobiverse#4509 merged. Re-append DONE on a done-miss reminder "
    "only when the board is already posted, the head SHA is unchanged, and "
    "the tip is 0 behind."
)
IRC_COVERED = """# job-irc

When bob-worker says the turn ended ACKed but no DONE/NACK/GIVEUP, re-append the same DONE only when this seat already posted the board, the head SHA is unchanged, and the tip is 0 behind. If the head moved or the tip is behind, re-verify. A drained outbox is not a missing board.
"""


def _payload():
    return {
        "kind": "harvest",
        "repo": REPO,
        "title": "harvest: done-miss re-append",
        "body": f"Session summary:\n{SUMMARY}\n\nLessons:\n- {LESSON}\n",
        "source": {
            "skill_book": "bobiverse-bob-worker",
            "agent": "Invoke-BobiverseHarvest",
            "seat": "marchhare-12216",
        },
    }


def test_fr4514_explicit_book_beats_keyword_inference():
    book, path = intake.resolve_skill_book(
        skill_book="bobiverse-bob-worker",
        title="harvest: done-miss re-append",
        body=f"Lessons:\n- {LESSON}\n",
    )
    assert book == "bobiverse-bob-job-irc"
    assert path == IRC_SKILL


def test_fr4514_intake_skips_when_named_book_already_has_the_sentence(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[IRC_SKILL] = IRC_COVERED
    filer.repo_files[WORKER_SKILL] = "# bob-worker\n\nNo re-append rule.\n"
    err, norm = intake.validate_payload(_payload())
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_4514_skip")
    assert rec["state"] == "lesson_already_covered"
    assert rec.get("skill_book") == "bobiverse-bob-job-irc"
    assert filer.prs == []


def test_fr4514_intake_files_on_named_book_when_sentence_is_absent(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[IRC_SKILL] = "# job-irc\n\nNo re-append rule yet.\n"
    filer.repo_files[WORKER_SKILL] = "# bob-worker\n\nNo re-append rule.\n"
    err, norm = intake.validate_payload(_payload())
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_4514_file")
    assert rec["state"] == "filed"
    assert rec.get("skill_book") == "bobiverse-bob-job-irc"
    paths = [f.get("path") for f in (filer.prs[-1].get("files") or [])]
    assert IRC_SKILL in paths
    assert WORKER_SKILL not in paths


def test_fr4514_ps1_does_not_infer_worker_over_explicit_book():
    if not HARVEST_PS1.is_file():
        return
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST_PS1),
            "-Repo",
            REPO,
            "-Summary",
            SUMMARY,
            "-Lesson",
            LESSON,
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert "skill_book=bobiverse-bob-job-irc" in out
    assert "inferred skill_book=bobiverse-bob-worker" not in out
    assert "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md" in out
