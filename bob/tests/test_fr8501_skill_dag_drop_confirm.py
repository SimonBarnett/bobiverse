"""FR #8501: transport-drop report needs a confirmed dead PID, not a flaky cmdline."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr8501_pids_still_live_uses_snapshot_only():
    rows = [(10, 1, "agent"), (12, 10, "python"), (13, 10, "python")]

    def snap():
        return rows

    assert bw.skill_dag_mcp_pids_still_live([12, 99], snapshot=snap) == [12]
    assert bw.skill_dag_mcp_pids_still_live([], snapshot=snap) == []
    assert bw.skill_dag_mcp_pids_still_live([99], snapshot=snap) == []


def test_fr8501_drop_not_confirmed_when_pid_still_live():
    """A flaky empty cmdline after-sample must not file when the PID is still live."""
    live_rows = [(10, 1, "agent"), (12, 10, "python")]

    def snap_live():
        return live_rows

    assert not bw.skill_dag_mcp_transport_drop_confirmed([12], snapshot=snap_live)


def test_fr8501_drop_confirmed_when_pid_gone_twice():
    dead_rows = [(10, 1, "agent")]
    calls = {"n": 0}

    def snap_dead():
        calls["n"] += 1
        return dead_rows

    assert bw.skill_dag_mcp_transport_drop_confirmed([12], snapshot=snap_dead)
    assert calls["n"] >= 2


def test_fr8501_drop_not_confirmed_on_single_empty_race():
    """One empty Toolhelp sample is not enough (FR #8501 false-positive class)."""
    seq = [
        [(10, 1, "agent")],  # first still_live empty
        [(10, 1, "agent"), (12, 10, "python")],  # confirm sees pid again
    ]
    calls = {"n": 0}

    def snap():
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return seq[i]

    assert not bw.skill_dag_mcp_transport_drop_confirmed([12], snapshot=snap)
    assert calls["n"] >= 2


def test_fr8501_refresh_uses_pid_confirm_not_cmdline_after():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    i = src.index("def _refresh_live_skill_dag_mcp")
    chunk = src[i : i + 2200]
    assert "Snapshot before refresh" in chunk
    assert "skill_dag_mcp_transport_drop_confirmed" in chunk
    assert "FR #8501" in chunk
    # Must not treat a single cmdline after-sample as proof of drop.
    assert "if before and not after:" not in chunk
