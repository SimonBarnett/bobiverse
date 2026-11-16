"""FR #7911: a later FIX job must not reuse an earlier job's outbox."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import opencode_seat_contract as c


def test_fix_job_outbox_is_not_the_previous_worktree(tmp_path: Path):
    base = tmp_path / "worktrees"
    env = {"BOB_JOB_WORKTREE_BASE": str(base)}
    old = base / "bobiverse" / "fr-7903" / ".bob" / "outbox.txt"
    line_a = "FROM jeeves #redqueen redqueen-6044: FR SimonBarnett/bobiverse#7903 https://x"
    line_b = (
        "FROM jeeves #redqueen redqueen-6044: FIX SimonBarnett/bobiverse#7885 https://x "
        "[outbox: %s]" % old
    )
    path_a = c.project_dir_for_assign(line_a, env)
    path_b = c.project_dir_for_assign(line_b, env)
    assert path_a.replace("/", "\\").lower().endswith("\\bobiverse\\fr-7903")
    assert path_b.replace("/", "\\").lower().endswith("\\bobiverse\\fix-7885")
    assert Path(path_a) != Path(path_b)
    ob = c.ensure_opencode_bob_outbox(path_b)
    assert c.outbox_is_writable(ob)
    stamped = bw.opencode_stamp_outbox_footer(line_b, ob)
    assert "fr-7903" not in stamped
    assert str(ob) in stamped
    assert ob.parent.parent == Path(path_b)


def test_opencode_json_allows_job_worktree_and_bob(tmp_path: Path):
    worker = tmp_path / "worker"
    (worker / ".grok" / "skills").mkdir(parents=True)
    job = tmp_path / "worktrees" / "bobiverse" / "fix-7885"
    cfg = bw.write_opencode_skill_dag_mcp_config(
        job, worker_cwd=str(worker), job_worktree=job
    )
    allow = json.loads(cfg.read_text(encoding="utf-8"))["permission"]["external_directory"]
    root = str(job.resolve())
    assert allow.get(root + "/**") == "allow"
    assert allow.get(str((job / ".bob").resolve()) + "/**") == "allow"
    assert str(worker.resolve()) not in allow


def test_unwritable_outbox_is_not_reachable(tmp_path: Path):
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("x", encoding="utf-8")
    assert c.outbox_is_writable(blocked / ".bob" / "outbox.txt") is False
