"""Hostile MRB pins for FR #3012 / PR #3017: out-of-fuel on agent 402."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_PY = ROOT / "scripts" / "bob_worker.py"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
PRODUCT = ROOT / "tests" / "test_fr3012_out_of_fuel.py"


def _text(p: Path) -> str:
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), p
    return raw.decode("utf-8")


def test_mrb3017_product_test_module_present():
    assert PRODUCT.is_file()
    t = _text(PRODUCT)
    assert "FR #3012" in t
    assert "out_of_fuel" in t or "out-of-fuel" in t
    assert "402" in t
    assert "GIVEUP" in t


def test_mrb3017_detector_and_giveup_symbols():
    text = _text(WORKER_PY)
    assert "FR #3012" in text
    assert "def is_out_of_fuel_text" in text
    assert "def out_of_fuel_giveup_line" in text
    assert "class GrokOutOfFuelWatcher" in text
    assert "def note_out_of_fuel" in text
    assert "def clear_out_of_fuel" in text
    assert "def post_digest_out_of_fuel" in text
    assert "_start_fuel_watcher" in text
    assert "402" in text
    assert "out-of-fuel" in text


def test_mrb3017_note_out_of_fuel_sets_release_gen_contiguous():
    text = _text(WORKER_PY)
    i = text.index("def note_out_of_fuel")
    window = text[i : i + 1800]
    assert "_release_gen = self._turn_gen" in window
    assert "_clear_done_miss" in window
    assert "_out_of_fuel = True" in window
    assert "out_of_fuel_release_fn" in window


def test_mrb3017_skill_fr3012_contiguous():
    t = _text(SKILL)
    assert "FR #3012" in t
    assert "out-of-fuel" in t.lower() or "out of fuel" in t.lower()
    assert "402" in t
    assert "GIVEUP" in t
    assert "unified.jsonl" in t or "status=out_of_fuel" in t
