"""FR #8195: progress heartbeat while agent/tool process is alive with no log output."""
from __future__ import annotations

import bob_worker as bw


def test_fr8195_alive_process_counts_as_progress_without_log_move():
    assert bw.progress_alive_counts_as_seen(moved=False, agent_alive=True) is True
    assert bw.progress_alive_counts_as_seen(moved=True, agent_alive=False) is True
    assert bw.progress_alive_counts_as_seen(moved=False, agent_alive=False) is False


def test_fr8195_default_tool_alive_phase_is_safe():
    phase = bw.progress_phase_for_alive_heartbeat(prior="")
    assert phase == "tool:alive"
    assert "password" not in phase
    assert "--" not in phase
    assert bw.progress_phase_for_alive_heartbeat(prior="tool:pytest") == "tool:pytest"
