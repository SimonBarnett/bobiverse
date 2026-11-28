"""FR #10241 / FR #10105: a resumed fr-N branch reuses its open PR instead of a second gh pr create."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw

FR = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"


def test_fr10241_job_fr_skill_documents_reuse_of_open_pr():
    text = FR.read_text(encoding="utf-8")
    assert "FR #10241" in text
    assert "gh pr list" in text
    assert "--head fr-N" in text
    assert "OPEN" in text
    assert "do not run `gh pr create`" in text.lower()


def test_fr10241_fr_finish_prompt_checks_existing_pr_before_create(monkeypatch):
    monkeypatch.setattr(
        "opencode_seat_contract.finish_reviewed_sha",
        lambda *a, **k: ("", "", ""),
    )
    text = bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#10241",
        worktree=r"D:\jobs\bobiverse\fr-10241",
        outbox=r"D:\jobs\bobiverse\fr-10241\.bob\outbox.txt",
    )
    assert "gh pr list --head" in text
    assert text.index("gh pr list --head") < text.index("gh pr create")
    assert "reuse it" in text
