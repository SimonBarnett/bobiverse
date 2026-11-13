"""docs/mrb-7137 hostile: skill/docs pin FR #7120 keep-stdio, not restart-on-rewrite."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mrb7137_worker_skill_pins_fr7120_keep_stdio_not_restart():
    text = (ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").read_text(encoding="utf-8")
    assert "FR #7120" in text
    assert "--job-worktree-file" in text
    assert "Do not restart mid-job" in text
    # Contiguous keep-stdio window (not the superseded restart-on-rewrite product sentence).
    window = "stable `--job-worktree-file` so Grok does not replace the stdio child mid-job"
    assert window in text
    assert "restart that seat's skill-dag stdio child" not in text


def test_mrb7137_bob_worker_docs_pin_pointer_not_terminate():
    text = (ROOT / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "FR #6918 / #7120" in text
    assert "skill-dag-job-worktree" in text
    assert "--job-worktree-file" in text
    assert "terminates this agent tree's `skill_dag_mcp.py` stdio child" not in text
