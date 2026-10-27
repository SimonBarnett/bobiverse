"""docs/mrb-5071: pin FR #5066 stage preserve + troubleshooting skill cue."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mrb5071_join_shop_preserves_escalation_stage_phrase():
    src = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert "FR #5066" in src
    assert "prev_stage >= 1" in src
    assert "keep stage" in src.lower() or "preserve" in src.lower()


def test_mrb5071_troubleshooting_skill_names_watch_stage():
    skill = (
        ROOT
        / "airc"
        / ".grok"
        / "skills"
        / "bobiverse-airc-troubleshooting"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #5066" in skill
    assert "_names_watch_stage" in skill
    assert "preserve" in skill.lower()
