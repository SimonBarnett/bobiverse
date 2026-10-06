"""MRB #2810 hostile pins: harvest-lesson for BoredEmitter.turn_ended (FR #2802)."""
from __future__ import annotations

from pathlib import Path


def _skill_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-bob-worker"
        / "SKILL.md"
    )


def test_mrb2810_harvested_lessons_section_has_turn_ended_bullet():
    raw = _skill_path().read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "## Harvested lessons (intake)" in text
    idx = text.index("## Harvested lessons (intake)")
    # Through next ## heading or EOF.
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    assert "BoredEmitter.turn_ended" in section
    assert "harvest_hold_s" in section
    assert "fallback" in section.lower()
    assert "2802" in section
    # Contiguous bullet: phrase lives on a line that starts with "- "
    lines = [ln for ln in section.splitlines() if "BoredEmitter.turn_ended" in ln]
    assert lines, "turn_ended lesson missing"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "events.jsonl" in lines[0] or "turn_ended" in lines[0]


def test_mrb2810_keeps_prior_intake_bullet_2790():
    text = _skill_path().read_text(encoding="utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    assert "BOB_NICK" in section or "2790" in section
    assert "BoredEmitter.turn_ended" in section
