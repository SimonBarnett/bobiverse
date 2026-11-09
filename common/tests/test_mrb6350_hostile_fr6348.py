"""Hostile pins for FR #6348 / PR #6350: !assign refusal log wiring."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def test_mrb6350_irc_agent_refuse_uses_helper_not_slice():
    text = (ROOT / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "format_assign_refusal_log" in text
    # Old truncate must not remain on the refuse log path.
    assert 'info(f"INFO git-assign refused nick={src} worker={wnick} {repo}{ident} {task}: {res}"[:200])' not in text
    assert "gitclaim.format_assign_refusal_log" in text


def test_mrb6350_outcome_other_for_coderabbit_hold():
    line = gitclaim.format_assign_refusal_log(
        nick="simon",
        worker="flamingo-1",
        repo="SimonBarnett/bobiverse",
        ident="#6211",
        task="MRB",
        reason="coderabbit_hold repo#6211 stamp=pending age_s=10 rem_s=50",
        redact_fn=lambda s: s,
    )
    assert "outcome=other" in line
    assert "coderabbit_hold" in line
