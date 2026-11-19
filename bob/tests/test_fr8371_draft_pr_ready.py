"""FR #8371: agents must set their PRs ready for review (never leave it draft)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw

FR = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
IRC = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"


def test_fr8371_fr_finish_prompt_marks_pr_ready_for_review(monkeypatch):
    monkeypatch.setattr(
        "opencode_seat_contract.finish_reviewed_sha",
        lambda *a, **k: ("", "", ""),
    )
    text = bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#8371",
        worktree=r"D:\jobs\bobiverse\fr-8371",
        outbox=r"D:\jobs\bobiverse\fr-8371\.bob\outbox.txt",
    )
    low = text.lower()
    assert "gh pr create" in low
    assert "ready for review" in low
    assert "gh pr ready" in low
    assert "draft" in low


def test_fr8371_fix_prompt_does_not_open_or_mark_pr(monkeypatch):
    monkeypatch.setattr(
        "opencode_seat_contract.finish_reviewed_sha",
        lambda *a, **k: ("", "", ""),
    )
    fix = bw.opencode_job_finish_steps(
        job_key="FIX SimonBarnett/bobiverse#8371",
        worktree=r"D:\jobs\bobiverse\fr-8371",
        outbox=r"D:\jobs\bobiverse\fr-8371\.bob\outbox.txt",
    )
    low = fix.lower()
    assert "gh pr ready" not in low
    assert "ready for review" not in low


def test_fr8371_job_fr_skill_documents_ready_for_review():
    text = FR.read_text(encoding="utf-8")
    assert "FR #8371" in text
    assert "ready for review" in text.lower()
    assert "gh pr ready" in text


def test_fr8371_job_irc_skill_documents_ready_for_review():
    text = IRC.read_text(encoding="utf-8")
    assert "FR #8371" in text
    assert "ready for review" in text.lower()
