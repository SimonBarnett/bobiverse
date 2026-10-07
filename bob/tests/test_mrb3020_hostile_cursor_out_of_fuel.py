"""Hostile MRB pins for FR #3019 / PR #3020: Cursor out-of-fuel parity."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_PY = ROOT / "scripts" / "bob_worker.py"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
PRODUCT = ROOT / "tests" / "test_fr3019_cursor_out_of_fuel.py"


def _text(p: Path) -> str:
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), p
    return raw.decode("utf-8")


def test_mrb3020_product_test_module_present():
    assert PRODUCT.is_file()
    t = _text(PRODUCT)
    assert "FR #3019" in t
    assert "cursor" in t.lower()
    assert "NEEDS_AUTH" in t or "fuel_lost" in t
    assert "should_start_fuel_watcher" in t


def test_mrb3020_watcher_gate_and_fuel_lost_symbols():
    text = _text(WORKER_PY)
    assert "FR #3019" in text
    assert "def should_start_fuel_watcher" in text
    assert "def default_out_of_fuel_log_path" in text
    assert "def _fuel_lost_mid_job" in text
    assert "fuel_lost_check_fn" in text
    assert "NEEDS_AUTH" in text
    i = text.index("def _start_fuel_watcher")
    window = text[i : i + 1400]
    assert "should_start_fuel_watcher" in window
    assert '!= "grok"' not in window


def test_mrb3020_mid_job_poll_contiguous():
    text = _text(WORKER_PY)
    assert "mid-job fuel reading exhausted" in text or "mid-job fuel-lost" in text
    assert "fuel_lost_check_fn" in text
    i = text.index("def _fuel_lost_mid_job")
    window = text[i : i + 700]
    assert "cursor" in window.lower()
    assert "cursor_has_tokens" in window or "not cursor_has_tokens" in window


def test_mrb3020_skill_fr3019_contiguous():
    t = _text(SKILL)
    assert "FR #3019" in t
    assert "cursor" in t.lower()
    assert "NEEDS_AUTH" in t or "fuel-reading" in t
    assert "out-of-fuel" in t.lower() or "out of fuel" in t.lower()
