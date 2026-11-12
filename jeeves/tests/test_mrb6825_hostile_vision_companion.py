"""Hostile pins for MRB #6825 / FR #6785 vision hybrid note."""
from __future__ import annotations

from pathlib import Path

VISION = Path(__file__).resolve().parents[1] / "VISION.md"
ROOT = Path(__file__).resolve().parents[2]


def _shape() -> str:
    text = VISION.read_text(encoding="utf-8")
    return text[text.index("## Shape") : text.index("## Stack")]


def test_mrb6825_shape_locked_and_names_status_page():
    shape = _shape()
    assert "LOCKED" in shape
    assert "Primary (one): service" in shape
    assert "appliance status page" in shape.lower()
    assert "chair companions" in shape.lower() or "companions" in shape.lower()
    assert "ircJeeves" in shape
    assert "(not a website)" not in shape
    # Docs-only slice must not claim token graph / ledger in Shape
    assert "by_model" not in shape
    assert "token graph" not in shape.lower()


def test_mrb6825_fr005_mirror_does_not_close_other_slices():
    mirror = (
        ROOT
        / "bob"
        / "docs"
        / "fr"
        / "cli-token-compare"
        / "FR-005-vision-hybrid-note.md"
    )
    assert mirror.is_file()
    text = mirror.read_text(encoding="utf-8")
    assert "Do not close #6781 #6782 #6783 #6784" in text or "Do not close" in text
