"""FR #4371: CLOSED-duplicate harvest-lesson MRB must not open a new tip; strip Closes #N."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
# compose may live under common/scripts
if not HARVEST.is_file():
    HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"


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


# FR #5481: lesson-review (FR #4780/#4917) runs before the FR #4371 CLOSED-duplicate gate.
_LESSON_SKIP = (
    "SKIPPED harvest CLOSED-duplicate lesson loop",
    "SKIPPED harvest lesson-review loop (FR #4780/#4917)",
    "SKIPPED harvest lesson/pin job (FR #4917)",
)


def _assert_harvest_skipped(stdout: str) -> None:
    assert any(m in stdout for m in _LESSON_SKIP), stdout


def test_harvest_script_documents_fr4371_skip_and_closes_strip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #4371" in text
    assert "Test-HarvestClosedDuplicateLessonLoop" in text
    assert "SKIPPED harvest CLOSED-duplicate lesson loop" in text
    assert "SKIPPED harvest lesson-review loop (FR #4780/#4917)" in text
    assert "Protect-HarvestBodyClosesKeywords" in text or "Neutralize-HarvestClosesKeywords" in text


def test_harvest_skips_closed_duplicate_already_merged_mrb(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "MRB bobiverse#4366 harvest-lesson CLOSED duplicate: already-merged MRB playbook already in job-mrb digest; tip wrongly Closes #4363",
        "-Lesson",
        "Harvest-lesson MRB: if job-mrb Harvest digest already has Re-offered or already-merged MRB, CLOSE the harvest/SKILL.md tip as duplicate (CAST IRON already covers); never Closes a product FR from a harvest tip.",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_harvest_skipped(r.stdout)
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_harvest_skips_cast_iron_already_covers_closed(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "MRB #4370 CLOSED: CAST IRON already covers Re-offered or already-merged MRB in job-mrb",
        "-Lesson",
        "do not merge weaker harvest/SKILL.md copy of already-merged MRB playbook",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_harvest_skipped(r.stdout)


def test_harvest_neutralizes_closes_in_queued_body(tmp_path: Path):
    """Real new playbook still queues, but Closes #N must not survive in the body."""
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "FR #5481: pack client keep.ps1 count; tip wrongly Closes #4363 in narrative",
        "-Lesson",
        "Invoke-BobiverseHarvest neutralizes Closes #N in harvest tip bodies (FR #4371).",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert not any(m in r.stdout for m in _LESSON_SKIP), r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
    files = list((tmp_path / "harvest-outbox").glob("*.json"))
    assert files, r.stdout + r.stderr
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    body = payload.get("body") or ""
    # GitHub closing keyword must not appear as Closes #N / Fixes #N
    import re

    assert not re.search(r"(?i)\b(Closes|Fixes)\s+#\d+", body), body
    assert not re.search(r"(?i)\b(Closes|Fixes)\s+[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+", body), body
    # Narrative still recoverable without the keyword
    assert "4363" in body or "Close" in body
