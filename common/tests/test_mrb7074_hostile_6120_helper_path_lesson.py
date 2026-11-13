"""MRB #7074 hostile pin: harvest lesson for 6120 helper-path LocalSystem isolation."""
from __future__ import annotations

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
    / "SKILL.md"
)


def test_mrb7074_harvested_lessons_pins_6120_helper_path_isolation():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    lines = [
        ln
        for ln in section.splitlines()
        if "6120" in ln and "helper-path" in ln and "load_opencode_go_key_from_auth" in ln
    ]
    assert lines, "harvest lesson missing from Harvested lessons"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "GO_USAGE" in lines[0] or "FUEL" in lines[0]
    assert "disk cache" in lines[0] or "Popen" in lines[0]
