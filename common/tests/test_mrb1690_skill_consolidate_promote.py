"""Hostile MRB #1690: FR #1684 skill-consolidate → promote-PR contract stays in the books."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAS = ROOT / "common/.grok/skills/harvest-agent-skills/SKILL.md"
HARVEST = ROOT / "common/.grok/skills/harvest/SKILL.md"
WORKER = ROOT / "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
JOB_FR = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path


def _no_conflict_markers(text: str) -> None:
    for line in text.splitlines():
        if line.startswith("<<<<<<< ") or line.startswith(">>>>>>> "):
            raise AssertionError(f"conflict marker: {line!r}")
        if line == "=======":
            raise AssertionError("conflict marker: =======")


def test_mrb1690_harvest_agent_skills_has_consolidate_section():
    text = HAS.read_text(encoding="utf-8")
    _no_bom(HAS)
    _no_conflict_markers(text)
    assert "FR #1684" in text
    assert "consolidate open skill receipts" in text.lower() or "Consolidate by skill book" in text
    assert "Duplicates closed:" in text
    assert "harvest/" in text
    assert "one PR per receipt" in text.lower() or "one per harvest receipt" in text.lower()
    assert "Never" in text and "main" in text


def test_mrb1690_pointer_skills_and_job_fr_align():
    harvest = HARVEST.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    job = JOB_FR.read_text(encoding="utf-8")
    for path, text in ((HARVEST, harvest), (WORKER, worker), (JOB_FR, job)):
        _no_bom(path)
        _no_conflict_markers(text)
        assert "FR #1684" in text
    assert "SKIP_FR" in harvest or "SKIP_FR" in worker or "SKIP_FR" in job
    assert "do **not** GIVEUP" in job or "do not GIVEUP" in job.lower()
    # FR #1718: the old "offered by mistake: GIVEUP" bullet must be gone
    assert "If offered one by mistake: GIVEUP" not in job
    assert "deliberately offers" in job
    assert "Consolidate" in worker or "consolidate" in worker
    assert "MRB" in worker and "MRB" in harvest


def test_mrb1690_skill_harvest_log_line():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "FR #1684" in text
    assert "promote PR" in text.lower() or "consolidate" in text.lower()
