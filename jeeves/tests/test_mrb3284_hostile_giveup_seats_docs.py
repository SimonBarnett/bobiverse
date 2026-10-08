"""MRB #3284 hostile: FR #3277 seat-scoped needs_human stays documented + coded."""
from __future__ import annotations

from pathlib import Path

import gitclaim

ROOT = Path(__file__).resolve().parents[2]
CMD = ROOT / "jeeves/docs/jeeves-commands.md"
TS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_mrb3284_docs_seat_scoped_not_all_seats():
    text = CMD.read_text(encoding="utf-8")
    _no_bom(CMD)
    assert "3277" in text
    assert "only those seats" in text
    # Stale FR #2562 "blocks all seats" wording must not remain for the threshold.
    assert "blocks **all** seats" not in text


def test_mrb3284_troubleshooting_mentions_self_mrb_strand():
    text = TS.read_text(encoding="utf-8")
    _no_bom(TS)
    assert "3277" in text
    assert "author_seat" in text
    assert "only those seats" in text.lower() or "only those seats" in text


def test_mrb3284_row_needs_human_seat_scoped_at_threshold():
    row = {
        "needs_human": True,
        "giveup_count": gitclaim.GIVEUP_NEEDS_HUMAN_COUNT,
        "giveup_seats": "marchhare-40596",
    }
    assert gitclaim.row_needs_human(row, "marchhare-40596") is True
    assert gitclaim.row_needs_human(row, "marchhare-22372") is False
    bare = {"needs_human": True, "giveup_count": gitclaim.GIVEUP_NEEDS_HUMAN_COUNT}
    assert gitclaim.row_needs_human(bare, "marchhare-22372") is True


def test_mrb3284_files_end_with_newline():
    for p in (CMD, TS, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
