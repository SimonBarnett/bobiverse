"""FR #10219: intake twin for #10117 — inject_console submit gap already on main (PR #1608)."""
from __future__ import annotations

import bob_worker as bw


def test_fr10219_twin_10117_acceptance_criteria_on_main(monkeypatch):
    """#10117 acceptance: default 0.20s gap, env override, double Enter in inject_console source."""
    monkeypatch.delenv("BOB_WORKER_SUBMIT_GAP_S", raising=False)
    assert bw._submit_gap_s() == 0.20
    src = open(bw.__file__, encoding="utf-8").read()
    assert "BOB_WORKER_SUBMIT_GAP_S" in src
    assert src.count("build_enter_records()") >= 2
    assert "submit_gap_s: float = 0.06" not in src
