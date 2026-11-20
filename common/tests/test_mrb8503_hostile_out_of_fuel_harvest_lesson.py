"""MRB #8503: pin the out-of-fuel digest harvest lesson in harvest/SKILL.md."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb8503_out_of_fuel_lesson_in_harvested_section():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "## Harvested lessons (intake)" in text
    idx = text.index("## Harvested lessons (intake)")
    chunk = text[idx:]
    needle = (
        "While a seat is in out-of-fuel hold, digest worker_list must paint "
        "state=out_of_fuel and keep updated fresh; idle_quiet_offerable must skip that seat."
    )
    assert needle in chunk
    assert "<<<<<<<" not in text
    assert ">>>>>>>" not in text
