"""FR #6384: regression test rejecting stray control characters in ``jeeves/docs`` Markdown.

FR #6379 was filed because a backslash escape had mangled a docs line into CR, LF
and BEL. Nothing caught it, so scan every Markdown file under ``jeeves/docs`` and
fail on the control bytes that should never appear there, naming file and line.

Allowed: tab (0x09), LF (0x0A) and CRLF (0x0D 0x0A). Any other CR is an offender.
"""
from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "jeeves" / "docs"

# 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F. CR (0x0D) is checked separately: it is only
# allowed directly before LF.
_BAD_BYTES = set(range(0x00, 0x09)) | {0x0B, 0x0C} | set(range(0x0E, 0x20))


def find_control_chars(root: Path) -> list[str]:
    """Return ``path:line: 0xNN`` for every stray control byte under *root*."""
    problems: list[str] = []
    for path in sorted(root.rglob("*.md")):
        raw = path.read_bytes()
        for i, byte in enumerate(raw):
            bad = byte in _BAD_BYTES
            if byte == 0x0D:
                bad = i + 1 >= len(raw) or raw[i + 1] != 0x0A
            if bad:
                line = raw.count(b"\n", 0, i) + 1
                problems.append(f"{path}:{line}: 0x{byte:02X}")
    return problems


def test_fr6384_docs_have_no_stray_control_chars():
    problems = find_control_chars(DOCS)
    assert not problems, "stray control characters in jeeves/docs:\n" + "\n".join(
        problems
    )


def test_fr6384_find_control_chars_reports_bel(tmp_path: Path):
    """Negative: BEL (0x07) is reported with file and line (FR #6384 / MRB #6385)."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "bel.md").write_bytes(b"a \x07 b\n")
    problems = find_control_chars(docs)
    assert problems, problems
    joined = "\n".join(problems).replace("\\", "/")
    assert "0x07" in joined and "bel.md" in joined, problems
    (docs / "ok.md").write_bytes(b"hello\r\nworld\n")
    ok_hits = [x for x in find_control_chars(docs) if "ok.md" in x.replace("\\", "/")]
    assert not ok_hits, ok_hits
