"""FR #8911: skill-dag MCP handshake failure uses the --once CLI, not another worktree."""
from repo_layout import REPO

SEAT = REPO / "bob" / "agents" / "worker" / ".grok" / "skills" / "bobiverse-worker-seat" / "SKILL.md"
WORKER = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "lessons.md"


def test_handshake_fallback_is_once_cli_not_foreign_worktree():
    seat = SEAT.read_text(encoding="utf-8-sig")
    worker = WORKER.read_text(encoding="utf-8-sig")
    assert "FR #8911" in seat
    assert "connection closed: initialize response" in seat
    assert "skill_dag_mcp.py --once resolve" in seat
    assert "skill-dag-mcp-down" in seat
    assert "another job worktree" in seat
    assert "/ #8911" in worker, str(WORKER.resolve())
    assert "skill_dag_mcp.py --once resolve" in worker
    assert "another job worktree" in worker
