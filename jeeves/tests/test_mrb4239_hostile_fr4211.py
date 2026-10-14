"""MRB #4239 hostile pins for FR #4211 ghost legacy workers + prose ionos pin.

Contiguous needles so a mid-function splice cannot drop pid-alive / stale
heartbeat filtering or re-open mere-ionos text pinning.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GITCLAIM = REPO / "common" / "scripts" / "gitclaim.py"
FR_TEST = REPO / "jeeves" / "tests" / "test_fr4211_ghost_workers_machine_pin.py"


def test_legacy_worker_live_helpers_contiguous():
    text = GITCLAIM.read_text(encoding="utf-8")
    assert "LIVE_LEGACY_WORKER_STALE_S = 900.0" in text
    assert "def _legacy_worker_live_nick(" in text
    assert "if not bobreport._pid_alive(pid_i):" in text
    assert "if (float(now) - float(ts)) > float(LIVE_LEGACY_WORKER_STALE_S):" in text
    assert "def live_seat_nicks(home: Path, *, now: float | None = None) -> set[str]:" in text
    assert "Fall back to ``workers`` only when ``worker_list`` is empty" in text


def test_fr4211_suite_covers_ghost_and_prose_pin():
    text = FR_TEST.read_text(encoding="utf-8")
    assert "ghost legacy workers must not block same-machine reviews" in text
    assert "test_infer_require_machine_mere_ionos_mention_does_not_pin" in text
    assert "test_infer_require_machine_dedicated_pin_line_and_needs_label_still_pin" in text
    assert "test_ghost_legacy_workers_do_not_block_same_machine_uat_sibling" in text
