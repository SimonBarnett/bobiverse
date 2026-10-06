"""MRB #2734 hostile: frozen !status lesson lives in jeeves-commands, not harvest."""
from __future__ import annotations

from pathlib import Path

JEEVES_CMD = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-jeeves-commands"
    / "SKILL.md"
)
HARVEST = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
    / "SKILL.md"
)


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2734_jeeves_commands_has_frozen_status_lesson():
    text = _utf8_no_bom(JEEVES_CMD)
    assert "Frozen chair" in text
    idx = text.index("Frozen chair")
    window = text[idx : idx + 420]
    assert "JEEVES_INSTALL_ROOT" in window
    assert "_MEIPASS" in window
    assert "_process_started" in window or "construct time" in window
    assert "_cc()" in window
    assert "2728" in window or "2733" in window or "2734" in window


def test_mrb2734_harvest_lacks_raw_frozen_status_bullet():
    text = _utf8_no_bom(HARVEST)
    assert "Frozen chair" not in text
    assert "- Frozen chair !status" not in text
