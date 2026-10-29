"""euroflo#15: harvest for SimonBarnett/euroflo must use harvest-agent-skills.

Never invent common/.grok/skills/harvest/ (bobiverse layout) on the customer repo.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
import intake  # noqa: E402

HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"


def _dry_run_text(*, job_repo: str, lesson: str) -> str:
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HARVEST_PS1),
        "-Repo",
        job_repo,
        "-Summary",
        f"euroflo#15 harvest book path pin {uuid.uuid4().hex[:8]}",
        "-Lesson",
        lesson,
        "-DryRun",
    ]
    run = subprocess.run(args, capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    assert run.returncode == 0, run.stdout + run.stderr
    return (run.stdout or "") + "\n" + (run.stderr or "")


def test_euroflo15_product_default_map():
    assert "simonbarnett/euroflo" not in intake.PRODUCT_DEFAULT_SKILL_BOOK
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/euroflo",
        topic_repos={"simonbarnett/euroflo"},
    )
    assert book == "harvest-agent-skills"
    assert path == ".grok/skills/harvest-agent-skills/SKILL.md"


def test_euroflo15_resolve_skill_book_never_bobiverse_harvest_path():
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/euroflo",
        skill_book="harvest",
        title="lesson(harvest): euroflo tip",
        body="Lessons:\n- euroflo saas-access\n",
    )
    assert book == "harvest-agent-skills"
    assert path == ".grok/skills/harvest-agent-skills/SKILL.md"
    assert "common/.grok/skills/harvest/" not in path.replace("\\", "/")


def test_euroflo15_harvest_ps1_pin():
    text = HARVEST_PS1.read_text(encoding="utf-8")
    # FR #4990 folded euroflo into priority-customer set (euroflo|lynton|trutex|rees).
    assert "FR #4990" in text or "euroflo#15" in text
    assert "euroflo|lynton|trutex|rees" in text or r"(?i)^SimonBarnett/euroflo$" in text
    assert "skill_book=harvest-agent-skills" in text


def test_euroflo15_harvest_dryrun_book_path():
    nonce = uuid.uuid4().hex
    lesson = f"euroflo#15 unique dryrun pin {nonce}: never invent common harvest path"
    text = _dry_run_text(job_repo="SimonBarnett/euroflo", lesson=lesson)
    assert "skill_book=harvest-agent-skills" in text
    assert "SimonBarnett/euroflo" in text
    # Prefer JSON payload; twin/dedup SKIP still proves the product-default branch ran.
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(text[start : end + 1])
        assert payload["repo"] == "SimonBarnett/euroflo"
        book = (payload.get("source") or {}).get("skill_book") or ""
        path = (payload.get("source") or {}).get("skill_book_path") or payload.get(
            "skill_book_path"
        ) or ""
        assert book == "harvest-agent-skills"
        assert path.replace("\\", "/") == ".grok/skills/harvest-agent-skills/SKILL.md"
    else:
        assert (
            "skill_book_path=.grok/skills/harvest-agent-skills/SKILL.md" in text
            or "SKIPPED harvest" in text
        )
