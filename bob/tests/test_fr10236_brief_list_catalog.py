"""FR #10236: job brief must name the MCP tools the skill-dag server really exposes.

The public skill-dag MCP exposes ``list_catalog`` and ``get_skill``. The brief
used to tell OpenCode to call ``resolve`` first, which that server does not
list, so the seat wasted a turn or invented the skill step.
"""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def _finish_text(tmp_path: Path) -> str:
    return bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#10236",
        worktree=tmp_path / "fr-10236",
        outbox=tmp_path / "outbox.txt",
    )


def test_fr10236_finish_brief_names_list_catalog_then_get_skill(tmp_path):
    text = _finish_text(tmp_path)
    assert "skill-dag MCP get_skill (list_catalog optional)" in text
    assert "list_catalog" in text
    assert "skill-dag MCP resolve then get_skill" not in text


def test_fr10236_skill_line_names_list_catalog_then_get_skill():
    worker = r"C:\ai\bob\worker"
    txt = bw.rules_text(worker, "agent")
    assert "(resolve, then get_skill)" not in txt
    assert "resolve, then get_skill" not in txt
