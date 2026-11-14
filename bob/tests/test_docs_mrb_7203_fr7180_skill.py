"""docs/mrb-7203: pin FR #7180 ready-without-first-turn skill text."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT


def test_docs_mrb_7203_fr7180_skill_phrases():
    skill = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #7180" in text
    assert "needs sign-in" in text
    assert "BOB_WORKER_STARTUP_WAIT_READY=1" in text
    assert "without a first turn" in text or "without waiting for a first turn" in text
    # default is no longer wait-ready-on
    assert "wait-ready default" not in text or "FR #7180" in text
    bom = skill.read_bytes()[:3]
    assert bom != b"\xef\xbb\xbf"
