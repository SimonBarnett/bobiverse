"""docs/mrb-7597: hostile pin for harvest Install-BobEarExe stage-before-smoke lesson."""
from __future__ import annotations

from repo_layout import REPO

SKILL = REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
NEEDLE = (
    "Install-BobEarExe: stage exe + companions + provenance before --help smoke; "
    "refuse smoke if a planned companion is missing; keep .bak rollback for companions"
)


def test_docs_mrb_7597_harvest_lesson_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "harvest SKILL.md must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert NEEDLE in text
    # Contiguous bullet: needle sits on one harvested-lessons line.
    lines = [ln.strip() for ln in text.splitlines() if NEEDLE[:40] in ln]
    assert any(ln.startswith("- ") and NEEDLE in ln for ln in lines)


def test_docs_mrb_7597_related_companion_ship_bullet_still_present():
    """Prior companion-ship lesson remains; new bullet is additive, not a splice."""
    text = SKILL.read_text(encoding="utf-8")
    assert "Install-BobEarExe copies them beside the exe" in text
    assert NEEDLE in text
    assert text.index("Install-BobEarExe copies them beside the exe") < text.index(NEEDLE)
