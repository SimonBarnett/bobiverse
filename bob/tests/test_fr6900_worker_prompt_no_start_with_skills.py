"""FR #6900: worker_prompt does not name three SKILL.md files to open first."""
from __future__ import annotations

import bob_worker as bw


def test_fr6900_worker_prompt_has_no_start_with_skill_list():
    text = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "flamingo", "flamingo-1")
    assert "start with bobiverse-worker-seat" not in text
    assert "resolve" in text
    assert "Report-BobiverseIntakeIssue.ps1" in text
    assert "get_skill" in text
