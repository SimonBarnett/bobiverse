"""MRB #2757 hostile: !assign fixture lesson lives in jeeves-commands, not harvest."""
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


def test_mrb2757_jeeves_commands_has_assign_fixture_lesson():
    text = _utf8_no_bom(JEEVES_CMD)
    assert "## Testing a command as the bob ear" in text
    idx = text.index("Chair pytest:")
    window = text[idx : idx + 520]
    assert "fr_row_offerable" in window
    assert "github_is_pull_checker" in window
    assert "github_issue_open_checker" in window
    assert "github_pr_exists_checker" in window
    assert "state=open" in window or "open" in window
    assert "2730" in window or "2756" in window or "2757" in window
    # Sits before Harvested resync section
    assert text.index("Chair pytest:") < text.index("## Harvested resync")


def test_mrb2757_harvest_lacks_raw_assign_fixture_bullet():
    text = _utf8_no_bom(HARVEST)
    assert "fr_row_offerable" not in text
    assert "github_issue_open_checker" not in text
    assert "- Chair !assign tests" not in text
