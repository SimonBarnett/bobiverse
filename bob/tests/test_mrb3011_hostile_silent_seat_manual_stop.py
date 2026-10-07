"""Hostile MRB pins for FR #3010 / PR #3011: silent FR #2996 seat needs manual stop."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
PRODUCT = ROOT / "tests" / "test_fr3010_silent_seat_manual_stop.py"


def _text(p: Path) -> str:
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), p
    return raw.decode("utf-8")


def test_mrb3011_product_test_module_present():
    assert PRODUCT.is_file()
    t = _text(PRODUCT)
    assert "FR #3010" in t
    assert "FR #2996" in t
    assert "post_bored" in t
    assert "seat-heal" in t.lower() or "seat heal" in t.lower()


def test_mrb3011_skill_stale_build_fr3010_contiguous():
    t = _text(SKILL)
    i = t.index("Stale build recycle (FR #2782)")
    window = t[i : i + 900]
    assert "FR #3010" in window
    assert "FR #2996" in window
    assert "post_bored" in window
    assert "PID" in window or "pid" in window
    assert "seat-heal" in window.lower() or "seat heal" in window.lower()
    assert "will **not**" in window or "will not" in window.lower() or "never reaches" in window.lower()


def test_mrb3011_troubleshooting_row_fr3010_contiguous():
    t = _text(SKILL)
    row = [ln for ln in t.splitlines() if "`!bored` never posts" in ln]
    assert row, "missing troubleshooting row for !bored never posts"
    body = row[0]
    assert "FR #2996" in body
    assert "FR #3010" in body
    assert "stop" in body.lower()
    assert "PID" in body or "pid" in body
    assert "seat-heal" in body.lower() or "seat heal" in body.lower()
    assert "post_bored" in body
    assert "never reaches" in body.lower() or "never fires" in body.lower()


def test_mrb3011_harvested_lesson_fr3010():
    t = _text(SKILL)
    lessons = [ln for ln in t.splitlines() if "done-miss release must set" in ln and "FR #2996" in ln]
    assert lessons, "missing FR #2996 harvested lesson bullet"
    body = lessons[-1]
    assert "FR #3010" in body
    assert "post_bored" in body
    assert "PID" in body or "pid" in body
    assert "seat-heal" in body.lower() or "seat heal" in body.lower()
