"""MRB #7069 hostile pin: harvest lesson for LocalSystem OpenCode AUTH_PATH delenv."""
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


def test_mrb7069_harvested_lessons_pins_localsystem_auth_delenv():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("## Harvested lessons (intake)")
    nxt = text.find("\n## ", idx + 1)
    section = text[idx:] if nxt < 0 else text[idx:nxt]
    needle = "AUTH_PATH"
    lines = [
        ln
        for ln in section.splitlines()
        if needle in ln and "LocalSystem" in ln and "delenv" in ln
    ]
    assert lines, "harvest lesson missing from Harvested lessons"
    assert lines[0].lstrip().startswith("- "), f"orphan/splice: {lines[0]!r}"
    assert "load_opencode_go_key_from_auth" in lines[0]
    assert "BOB_OPENCODE_AUTH_PATH" in lines[0]
