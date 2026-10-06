"""MRB #2818 hostile pins: harvest-lesson Supervisor path_fn → events.jsonl."""
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


def test_mrb2818_harvested_lessons_has_path_fn_events_jsonl_bullet():
    raw = _skill_path().read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "## Harvested lessons (intake)" in text
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    assert "path_fn" in section
    assert "events.jsonl" in section
    assert "GrokTurnWatcher" in section
    lines = [ln for ln in section.splitlines() if "path_fn" in ln and "events.jsonl" in ln]
    assert lines, "path_fn/events.jsonl lesson missing"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "session dir" in lines[0].lower() or "is_file" in lines[0]


def test_mrb2818_keeps_prior_intake_bullets():
    text = _skill_path().read_text(encoding="utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    assert "2790" in section or "BOB_NICK" in section
    assert "BoredEmitter.turn_ended" in section
    assert "path_fn" in section
