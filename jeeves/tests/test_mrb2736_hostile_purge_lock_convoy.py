"""MRB #2736 hostile: report MRB purge never holds queue lock across GitHub (FR #2729)."""
from __future__ import annotations

import inspect
from pathlib import Path

import bobreport
import gitclaim

REPO = Path(__file__).resolve().parents[2]
GITCLAIM = REPO / "common" / "scripts" / "gitclaim.py"
BOBREPORT = REPO / "common" / "scripts" / "bobreport.py"
PRODUCT = REPO / "jeeves" / "tests" / "test_fr2729_mrb_purge_lock_convoy.py"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2736_purge_signature_has_lock_timeout():
    sig = inspect.signature(gitclaim.purge_dead_mrb_rows)
    assert "lock_timeout" in sig.parameters


def test_mrb2736_shared_cache_and_single_flight_symbols():
    assert hasattr(gitclaim, "TTLCache")
    assert hasattr(gitclaim, "PR_EXISTS_SHARED_CACHE")
    assert isinstance(gitclaim.PR_EXISTS_SHARED_CACHE, gitclaim.TTLCache)
    text = _utf8_no_bom(GITCLAIM)
    assert "_PURGE_INFLIGHT" in text
    assert "never call GitHub" in text or "never call GitHub" in text.lower() or "Outside the lock" in text or "outside the lock" in text


def test_mrb2736_report_passes_short_lock_wait_and_shared_cache():
    text = _utf8_no_bom(BOBREPORT)
    assert "REPORT_PURGE_LOCK_WAIT_S" in text
    assert "0.2" in text
    assert "PR_EXISTS_SHARED_CACHE" in text
    assert "lock_timeout=" in text
    src = inspect.getsource(bobreport._public_queue)
    assert "PR_EXISTS_SHARED_CACHE" in src
    assert "lock_timeout" in src


def test_mrb2736_product_tests_pin_lock_free_and_row_survive():
    text = _utf8_no_bom(PRODUCT)
    assert "GitHub check ran while the queue lock was held" in text
    assert "row_added_during_github_check_is_not_lost" in text
    assert "ten_plus_open_mrb_rows_slow_github_do_not_starve_queue" in text
    assert "shared_60s_cache" in text or "60s" in text


def test_mrb2736_ttl_cache_single_get_in_checker():
    text = _utf8_no_bom(GITCLAIM)
    # One lookup path — not ``in`` then ``[]`` (TTL race).
    assert "store.get(key, _CACHE_MISS)" in text
