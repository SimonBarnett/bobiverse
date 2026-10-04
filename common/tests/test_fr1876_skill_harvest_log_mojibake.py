"""FR #1876: skill-harvest-log.md must stay UTF-8 without mojibake; FR #1878 job-irc hygiene."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "common/docs/skill-harvest-log.md"
IRC = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"

MOJIBAKE_NEEDLES = (
    "\u00c3\u00a2",  # Ã¢
    "\u00e2\u20ac",  # â€ prefix
    "\u251c\u00e2",  # ├â
    "\ufffd",
    "â€",
    "â†’",
    "â€”",
    "â€¦",
    "├â",
    "┬ó",
    "ΓÇ",
)


def test_fr1876_skill_harvest_log_no_mojibake():
    raw = LOG.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    for needle in MOJIBAKE_NEEDLES:
        assert needle not in text, f"mojibake needle {needle!r} found in skill-harvest-log.md"
    assert "2026-09-29" in text


def test_fr1878_job_irc_no_backspace_or_bbobiverse():
    raw = IRC.read_bytes()
    assert b"\x08" not in raw
    text = raw.decode("utf-8")
    assert "bbobiverse" not in text
