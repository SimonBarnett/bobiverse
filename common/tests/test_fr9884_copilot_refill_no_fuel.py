"""FR #9884: pause Haiku CCA refill on digest soft/hard exhaust (zero POSTs)."""
from __future__ import annotations

import copilot_dispatch as cd
import copilot_haiku_refill as refill


def test_digest_soft_exhausted_blocks_refill():
    block = {
        "state": "exhausted",
        "remaining": 0,
        "unlimited": False,
        "tasks_exhausted": True,
    }
    assert refill.digest_blocks_cca_refill(block) == refill.REFILL_NO_FUEL
    assert cd.cca_refill_no_fuel_reason(block) == refill.REFILL_NO_FUEL


def test_digest_ok_with_fuel_allows_refill():
    block = {
        "state": "ok",
        "remaining": 3,
        "unlimited": False,
        "tasks_exhausted": False,
    }
    assert refill.digest_blocks_cca_refill(block) is None
    assert cd.cca_refill_no_fuel_reason(block) is None


def test_tasks_exhausted_flag_blocks_even_when_state_ok():
    block = {
        "state": "ok",
        "remaining": 5,
        "unlimited": False,
        "tasks_exhausted": True,
    }
    assert refill.digest_blocks_cca_refill(block) == refill.REFILL_NO_FUEL


def test_allowance_from_pool_denial_blocks_refill():
    """Finite remaining=0 paints exhausted in pool rules — no CCA spend."""
    block = {
        "state": "exhausted",
        "remaining": 0,
        "unlimited": False,
        "percent_remaining": 0,
    }
    assert not cd.allowance_from_pool(block)
    assert refill.digest_blocks_cca_refill(block) == refill.REFILL_NO_FUEL


def test_no_fuel_when_copilot_missing():
    assert refill.digest_blocks_cca_refill(None) == refill.REFILL_NO_FUEL