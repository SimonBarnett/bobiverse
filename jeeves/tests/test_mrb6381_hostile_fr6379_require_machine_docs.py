"""MRB #6381 hostile pin: FR #6379 require_machine bullet in jeeves-commands.md.

Repaired garbled control escapes; documents dedicated body-line pin
(require_machine: / =) that gitclaim keeps when shortening the body.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "jeeves" / "docs" / "jeeves-commands.md"


def test_mrb6381_require_machine_bullet_one_clean_line():
    raw = DOCS.read_bytes()
    assert raw.count(bytes([7])) == 0  # no BEL
    # No CR except as part of CRLF line endings
    for i, b in enumerate(raw):
        if b == 13:
            assert i + 1 < len(raw) and raw[i + 1] == 10, f"orphan CR at {i}"
    text = DOCS.read_text(encoding="utf-8")
    assert not text.startswith("\ufeff")
    hits = [
        ln
        for ln in text.splitlines()
        if ln.startswith("* **require_machine**") and "FR #587" in ln
    ]
    assert len(hits) == 1, hits
    line = hits[0]
    assert "`require_machine`" in line
    assert "`needs-<machine>`" in line
    assert "`require_machine:<machine>`" in line
    assert "`machine:<machine>`" in line
    assert "`offer_focus_top`" in line
    assert "`!assign`" in line
    assert "`assign_row`" in line
    assert "`row_machine_mismatch`" in line
    assert "A dedicated body line" in line
    assert "`require_machine: <machine>`" in line or "require_machine: <machine>" in line
    assert "(or `=`)" in line or "(or =)" in line
    assert "shorten the body" in line
    # Must not still be the mangled split across lines (CR/BEL ate leading letters).
    bad_starts = (
        "equire_machine",
        "eeds-<machine>",
        "ssign_row",
        "ow_machine_mismatch",
    )
    for ln in text.splitlines():
        s = ln.lstrip()
        for bad in bad_starts:
            assert not s.startswith(bad), ln
    assert "enqueue infers `require_machine`" in line
