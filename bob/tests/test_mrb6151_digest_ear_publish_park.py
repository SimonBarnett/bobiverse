"""Hostile pin: digest ear-publish docs park (MRB #6151)."""
from __future__ import annotations

from pathlib import Path

import pytest

from repo_layout import ROOT

PARK = ROOT / "bob" / "docs"
VISION = PARK / "vision-digest-ear-publish.md"
ISSUED = PARK / "fr" / "digest-ear-publish" / "ISSUED.tsv"
MOCKS = PARK / "mocks" / "digest-fuel"


def _park_files() -> list[Path]:
    files = []
    files.extend(PARK.glob("*digest-ear-publish*"))
    files.extend((PARK / "fr" / "digest-ear-publish").rglob("*"))
    files.extend(MOCKS.rglob("*"))
    return [p for p in files if p.is_file()]


def test_mrb6151_vision_park_locked_success_rows() -> None:
    text = VISION.read_text(encoding="utf-8")
    assert "LOCKED" in text
    for sid in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        assert f"| {sid} " in text or f"| {sid}|" in text
    assert "Ear owns fuel publish" in text or "Ear-only fuel publish" in text
    assert "https://bob.ntsa.uk/bob/v1/report" in text


def test_mrb6151_issued_tsv_maps_fr001_to_6150() -> None:
    rows = ISSUED.read_text(encoding="utf-8").strip().splitlines()
    assert rows[0].startswith("fr\tgithub")
    mapping = {}
    for line in rows[1:]:
        fr, gh, *_ = line.split("\t")
        mapping[fr] = int(gh)
    assert mapping["FR-001"] == 6141
    assert mapping["FR-010"] == 6150
    assert len(mapping) == 10


def test_mrb6151_park_docs_ascii_no_bom_no_closes() -> None:
    for path in _park_files():
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        text = raw.decode("utf-8")
        non = [c for c in text if ord(c) > 127]
        assert not non, f"{path} non-ascii {[hex(ord(c)) for c in non[:5]]}"
        # Park must not Closes implementation issues (Refs only)
        for line in text.splitlines():
            assert not line.strip().startswith("Closes "), path


def test_mrb6151_mocks_present() -> None:
    for name in ("home.html", "empty.html", "error.html"):
        assert (MOCKS / name).is_file()