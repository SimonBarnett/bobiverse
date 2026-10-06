"""MRB #2789 hostile: bob_worker pytest tip-shadow lesson lives in job-mrb Pytest section."""
from __future__ import annotations

from pathlib import Path

JOB_MRB = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-mrb"
    / "SKILL.md"
)
HARVEST = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
    / "SKILL.md"
)


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2789_job_mrb_pytest_section_has_tip_shadow():
    text = _utf8_no_bom(JOB_MRB)
    assert "## Pytest / sparse worktrees (FR #963)" in text
    assert "**bob_worker tip shadow" in text
    idx = text.index("**bob_worker tip shadow")
    window = text[idx : idx + 520]
    assert "PYTHONPATH" in window
    assert "bob\\scripts" in window or r"bob\scripts" in window or "bob/scripts" in window
    assert "flat copy" in window
    assert "bob_worker.py" in window
    assert "2782" in window or "2789" in window
    # Contiguous under Pytest section, before Evidence
    pytest_h = text.index("## Pytest / sparse worktrees (FR #963)")
    evidence = text.index("## Evidence required")
    assert pytest_h < idx < evidence


def test_mrb2789_tip_shadow_pins_cwd_and_shadow_failure():
    text = _utf8_no_bom(JOB_MRB)
    idx = text.index("**bob_worker tip shadow")
    window = text[idx : idx + 520]
    assert "cwd" in window.lower() or "worktree" in window
    assert "shadow" in window
    assert "main failures" in window or "look like main" in window


def test_mrb2789_harvest_lacks_raw_tip_shadow_bullet():
    text = _utf8_no_bom(HARVEST)
    assert "bob_worker tip shadow" not in text
    assert "flat copy shadows" not in text
    assert "FR #2782 tip tests look like main failures" not in text
    # Placement rule that sent the lesson to job-mrb must remain
    assert "Harvest-lesson MRB playbooks" in text
    assert "bobiverse-bob-job-mrb" in text
