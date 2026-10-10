"""FR #3880: product docs/*.md must decode as UTF-8 (no lone cp1252 0x97).

Commit a23df418 left a Windows-1252 em dash (0x97) in skill-harvest-log.md;
25 harvest-log readers failed with UnicodeDecodeError. The byte was rewritten
on main in e6eca0d9 (docs/mrb-3871). This gate keeps every product docs tree
UTF-8 so it cannot recur.
"""
from __future__ import annotations

from pathlib import Path

import repo_layout

# Legacy ROOT remaps paths and breaks Path.rglob; use concrete REPO.
REPO = Path(repo_layout.REPO)

PRODUCT_DOCS = (
    REPO / "common" / "docs",
    REPO / "bob" / "docs",
    REPO / "jeeves" / "docs",
    REPO / "airc" / "docs",
)

LOG = REPO / "common" / "docs" / "skill-harvest-log.md"


def _docs_md_files() -> list[Path]:
    out: list[Path] = []
    for base in PRODUCT_DOCS:
        if not base.is_dir():
            continue
        out.extend(sorted(base.rglob("*.md")))
    return out


def _is_utf8_continuation(byte: int) -> bool:
    return 0x80 <= byte <= 0xBF


def _lone_cp1252_0x97_offsets(raw: bytes) -> list[int]:
    """Offsets of 0x97 that are not UTF-8 continuation bytes of a prior lead."""
    hits: list[int] = []
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if 0xC2 <= b <= 0xDF and i + 1 < n and _is_utf8_continuation(raw[i + 1]):
            i += 2
            continue
        if 0xE0 <= b <= 0xEF and i + 2 < n and all(
            _is_utf8_continuation(raw[j]) for j in (i + 1, i + 2)
        ):
            i += 3
            continue
        if 0xF0 <= b <= 0xF4 and i + 3 < n and all(
            _is_utf8_continuation(raw[j]) for j in (i + 1, i + 2, i + 3)
        ):
            i += 4
            continue
        if b == 0x97:
            hits.append(i)
        i += 1
    return hits


def test_fr3880_product_docs_md_decode_utf8():
    files = _docs_md_files()
    assert files, "expected product docs/*.md under common/bob/jeeves/airc"
    bad: list[str] = []
    for path in files:
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            bad.append(f"{path.relative_to(REPO)}: {exc}")
    assert not bad, "non-UTF-8 docs:\n" + "\n".join(bad)


def test_fr3880_no_lone_cp1252_em_dash_0x97():
    bad: list[str] = []
    for path in _docs_md_files():
        for off in _lone_cp1252_0x97_offsets(path.read_bytes()):
            bad.append(f"{path.relative_to(REPO)}:@{off}")
    assert not bad, "lone cp1252 0x97 (em dash) in docs:\n" + "\n".join(bad)


def test_fr3880_skill_harvest_log_utf8_no_bom():
    raw = LOG.read_bytes()
    assert LOG.is_file()
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")
    assert not _lone_cp1252_0x97_offsets(raw)
