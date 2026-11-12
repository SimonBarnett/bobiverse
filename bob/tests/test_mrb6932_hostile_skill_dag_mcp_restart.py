"""MRB #6932 hostile: MCP restart stays in this agent tree (FR #6928)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_mrb6932_prefix_seat_marker_does_not_kill_non_descendant():
    killed: list[int] = []
    seat1 = r"C:\run\worker-flamingo-1\bound-cwd"
    seat10 = r"C:\run\worker-flamingo-10\bound-cwd"
    rows = [
        (10, 1, "agent.exe"),
        (20, 10, "python.exe"),
        (11, 1, "agent.exe"),
        (30, 11, "python.exe"),
    ]
    cmds = {
        20: rf"python C:\bob\scripts\skill_dag_mcp.py --root {seat1}\.grok\skills",
        30: rf"python C:\bob\scripts\skill_dag_mcp.py --root {seat10}\.grok\skills",
        10: r"C:\fake\agent.exe",
    }
    got = bw.restart_skill_dag_mcp_stdio_children(
        10,
        [seat1],
        snapshot=lambda: rows,
        cmdline_of=lambda pid: cmds.get(pid, ""),
        kill=lambda pid: killed.append(pid) or True,
    )
    assert got == [20]
    assert 30 not in killed
    assert 10 not in killed


def test_mrb6932_skill_mentions_fr6928_restart_not_sibling():
    raw = (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-bob-worker"
        / "SKILL.md"
    ).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "FR #6928" in text
    assert "skill_dag_mcp.py" in text
    assert "sibling" in text.lower()
