"""docs/mrb-4913: pin harvest tip coupling gitclaim.ID_RE and shop_listen _VERB_RE."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_harvest_pins_id_re_verb_re_same_turn():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    needle = (
        "Jeeves FR: when gitclaim.ID_RE widens to synthetic #main/#main-red, "
        "widen shop_listen _VERB_RE the same turn"
    )
    i = text.index(needle)
    window = text[i : i + 280]
    assert "DONE is silent" in window
    assert "nak-busy" in window
    assert "BUSY_STALE_S" in window
    assert "\u2014" not in window
