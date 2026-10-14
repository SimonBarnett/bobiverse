"""Hostile pin MRB #4220: bobiverse-airc skill FR #4215 says airc.exe not irc.exe."""
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_mrb4220_skill_fr4215_says_airc_not_irc():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4215" in text
    # Contiguous pin on the AV bullet
    idx = text.index("Antivirus exclusions (FR #4215)")
    window = text[idx : idx + 280]
    assert "airc.exe" in window or "laying airc.exe" in window
    assert "laying irc.exe" not in window
