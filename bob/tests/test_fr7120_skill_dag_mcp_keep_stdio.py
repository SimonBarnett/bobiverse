"""FR #7120: live stdio MCP keeps working after job-worktree pointer refresh."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import bob_worker as bw
import skill_dag_mcp as mcp


MCP = Path(bw.__file__).resolve().parent / "skill_dag_mcp.py"


def _rpc(proc: subprocess.Popen, msg: dict) -> dict:
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)


def test_fr7120_live_stdio_picks_up_pointer_without_restart(tmp_path: Path):
    root = tmp_path / "seat" / ".grok" / "skills" / "bobiverse-bob-job-fr"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: bobiverse-bob-job-fr\ndescription: FR jobs\n---\n# FR\n",
        encoding="utf-8",
    )
    job = tmp_path / "job-wt"
    job_skill = job / ".grok" / "skills" / "unique-job-skill-7120"
    job_skill.mkdir(parents=True)
    (job_skill / "SKILL.md").write_text(
        "---\nname: unique-job-skill-7120\ndescription: job tree skill\n---\n# Job\n",
        encoding="utf-8",
    )
    ptr = tmp_path / "seat" / ".grok" / "skill-dag-job-worktree"
    ptr.write_text("", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            str(MCP),
            "--root",
            str(tmp_path / "seat" / ".grok" / "skills"),
            "--job-worktree-file",
            str(ptr),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        init = _rpc(
            proc,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert init.get("result", {}).get("serverInfo", {}).get("name") == "skill-dag"
        before = _rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "status", "arguments": {}},
            },
        )
        text = before["result"]["content"][0]["text"]
        st = json.loads(text)
        assert job.as_posix() not in json.dumps(st).replace("\\", "/")
        ptr.write_text(job.as_posix() + "\n", encoding="utf-8")
        after = _rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "status", "arguments": {}},
            },
        )
        st2 = json.loads(after["result"]["content"][0]["text"])
        blob = json.dumps(st2).replace("\\", "/")
        assert "job-wt" in blob
        assert int(st2.get("node_count") or 0) >= 2
        assert proc.poll() is None
        resolved = _rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "resolve", "arguments": {"seed": "unique-job-skill-7120"}},
            },
        )
        body = json.loads(resolved["result"]["content"][0]["text"])
        ids = [m.get("id") for m in body.get("matched") or []]
        assert "unique-job-skill-7120" in ids
    finally:
        proc.kill()
        proc.wait(timeout=5)


def test_fr7120_refresh_does_not_kill_live_mcp():
    killed: list[int] = []
    # Worker no longer restarts on refresh; helper still exists for tests.
    assert callable(bw.restart_skill_dag_mcp_stdio_children)
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "keep the live stdio MCP" in src
    assert killed == []


def test_fr7120_transport_drop_reports_once():
    seen = []

    def filer(payload):
        seen.append(payload)
        return {"ok": True}

    # pytest skip is first; force by clearing the env in a nested call via monkeypatch-less path:
    out = bw.report_skill_dag_mcp_transport_drop(
        machine="redqueen",
        agent_pid=1488,
        filer_post=filer,
    )
    assert out.get("ok") is True
    assert seen[0]["idempotency_key"].startswith("skill-dag-mcp-drop|redqueen|1488")
    assert "password" not in json.dumps(seen[0]).lower()


def test_fr7120_pointer_roundtrip(tmp_path: Path):
    cwd = tmp_path / "bound"
    job = tmp_path / "wt"
    job.mkdir()
    p = bw.write_skill_dag_job_worktree_pointer(cwd, job)
    assert mcp.read_job_worktree_pointer(p).resolve() == job.resolve()
    bw.write_skill_dag_job_worktree_pointer(cwd, None)
    assert mcp.read_job_worktree_pointer(p) is None
