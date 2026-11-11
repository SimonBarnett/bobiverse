"""docs/mrb-6708: harvest OpenCode LocalSystem fuel lesson contiguous pin."""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_docs_mrb6708_harvest_opencode_localsystem_fuel_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    needle = (
        "OpenCode fuel under LocalSystem: PATH pin can still hit WindowsApps alias; "
        "set BOB_OPENCODE_PYTHON to a real interpreter and name empty-stats as "
        "stats_failed (not parser_missing)."
    )
    assert needle in text
    idx = text.index(needle)
    window = text[max(0, idx - 200) : idx + len(needle) + 120]
    assert "OpenCode start_agent tests that spawn must stub probe_gh_auth" in window
    assert "## Harvest digest" in text[idx:]