"""MRB #3284 / FR #4336: needs_human is global for auto-offer; docs cite FR #4336."""
from __future__ import annotations

from pathlib import Path

import gitclaim

ROOT = Path(__file__).resolve().parents[2]
CMD = ROOT / "jeeves/docs/jeeves-commands.md"
TS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_mrb3284_docs_needs_human_global_fr4336():
    text = CMD.read_text(encoding="utf-8")
    _no_bom(CMD)
    assert "4336" in text
    assert "every" in text.lower() or "auto-offer" in text.lower()
    # FR #4336 supersedes seat-scoped carve-out wording.
    assert "only those seats" not in text


def test_mrb3284_troubleshooting_mentions_self_mrb_and_fr4336():
    text = TS.read_text(encoding="utf-8")
    _no_bom(TS)
    assert "3277" in text or "4336" in text
    assert "author_seat" in text
    assert "4336" in text


def test_mrb3284_row_needs_human_global_at_threshold():
    row = {
        "needs_human": True,
        "giveup_count": gitclaim.GIVEUP_NEEDS_HUMAN_COUNT,
        "giveup_seats": "marchhare-40596",
    }
    assert gitclaim.row_needs_human(row, "marchhare-40596") is True
    assert gitclaim.row_needs_human(row, "marchhare-22372") is True
    bare = {"needs_human": True, "giveup_count": gitclaim.GIVEUP_NEEDS_HUMAN_COUNT}
    assert gitclaim.row_needs_human(bare, "marchhare-22372") is True


def test_mrb3284_files_end_with_newline():
    for p in (CMD, TS, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
