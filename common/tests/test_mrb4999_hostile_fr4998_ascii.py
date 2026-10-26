"""Hostile pin for FR #4998 / MRB #4999: FR #4988 ps1 stay pure ASCII.

Pins the exact ASCII replacements so a later edit cannot reintroduce U+2014
or U+2026 into these BOM-less scripts.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
CLEAR = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def test_fr4988_comment_needles_are_ascii_replacements():
    common = COMMON.read_text(encoding="utf-8")
    clear = CLEAR.read_text(encoding="utf-8")
    assert 'Returns e.g. "D:\\" --- callers append ai\\worktrees (FR #4988).' in common
    assert "configured job worktree base (...\\ai\\worktrees\\...)." in clear
    for label, text in (("Bobiverse-Common.ps1", common), ("Clear-BobiverseJobWorktrees.ps1", clear)):
        assert "\u2014" not in text, f"em dash in {label}"
        assert "\u2026" not in text, f"ellipsis in {label}"
        raw = text.encode("utf-8")
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {label}"
        assert all(b < 128 for b in raw), f"non-ASCII byte in {label}"
