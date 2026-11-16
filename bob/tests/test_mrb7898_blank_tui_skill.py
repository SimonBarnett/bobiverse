"""MRB #7898: FR #7868 blank-console playbook stays in bobiverse-bob-worker."""
from __future__ import annotations

from pathlib import Path


def test_fr7868_worker_skill_bullet_is_contiguous():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").read_text(encoding="utf-8")
    needle = (
        "**FR #7868:** a blank Grok console (no letters or digits) for 120 seconds "
        "is a wedge. Report grok-blank-tui once. Do not kill the seat and do not "
        "start another kind until same-kind recycle is approved."
    )
    assert needle in text
    assert "Do not park this playbook under harvest/SKILL.md (moved from harvest tip #7883)." in text
