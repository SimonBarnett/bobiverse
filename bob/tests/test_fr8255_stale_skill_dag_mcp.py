"""FR #8255: silent empty resolve is a stale MCP child; restart only when the script is newer."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr8255_silent_empty_resolve_is_stale():
    assert bw.skill_dag_resolve_is_stale_silent({"matched": [], "skipped": []}) is True
    assert bw.skill_dag_resolve_is_stale_silent(
        {"matched": [], "skipped": [], "unresolved": True, "reason": "no_seed_match"}
    ) is False
    assert bw.skill_dag_resolve_is_stale_silent(
        {"matched": [{"id": "bobiverse-bob-job-fr"}], "skipped": []}
    ) is False


def test_fr8255_restarts_child_only_when_script_is_newer(tmp_path: Path):
    script = tmp_path / "skill_dag_mcp.py"
    script.write_text("# tip\n", encoding="utf-8")
    mtime = script.stat().st_mtime
    seat = r"C:\seat-a\bound-cwd"
    rows = [(10, 1, "agent.exe"), (20, 10, "python.exe"), (21, 10, "python.exe")]
    cmds = {
        20: r"python C:\bob\scripts\skill_dag_mcp.py --root C:\seat-a\bound-cwd\.grok\skills",
        21: r"python C:\bob\scripts\skill_dag_mcp.py --root C:\seat-a\bound-cwd\.grok\skills",
        10: "agent",
    }
    killed: list[int] = []
    starts = {20: mtime - 60.0, 21: mtime + 60.0}
    got = bw.restart_stale_skill_dag_mcp_children(
        10,
        [seat],
        script,
        started_at=lambda pid: starts.get(pid),
        snapshot=lambda: rows,
        cmdline_of=lambda pid: cmds.get(pid, ""),
        kill=lambda pid: killed.append(pid) or True,
    )
    assert got == [20]
    assert killed == [20]
