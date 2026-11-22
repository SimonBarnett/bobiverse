"""FR #6865: Cursor worker seat writes project .cursor/mcp.json only; no user catalog drop."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import bob_worker as bw
from repo_layout import ROOT


def test_cursor_mcp_path_is_workspace_mcp_json():
    assert bw.CURSOR_SKILL_DAG_MCP_RELPATH.replace("\\", "/") == ".cursor/mcp.json"


def test_cursor_no_process_local_catalog_drop():
    assert bw.cursor_skill_catalog_process_local_drop() is None


def test_cursor_launch_files_include_mcp_and_resolve(tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    prompt = bw.worker_prompt(str(worker), str(run), "flamingo", "flamingo-1")
    spec = bw.build_launch(
        "cursor",
        "agent",
        str(worker),
        prompt,
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    mcp_path = str(worker / ".cursor" / "mcp.json")
    assert mcp_path in spec.files
    body = spec.files[mcp_path]
    data = json.loads(body)
    assert "skill-dag" in data.get("mcpServers", {})
    assert "resolve" in spec.files[str(run / "prompt.txt")]
    assert "get_skill" in spec.files[str(run / "prompt.txt")]
    assert spec.write_cursor_skill_dag_mcp is True
    # FR #8785 / #8846: prompt must not invent bob/bob/scripts; fail-closed GIVEUP named
    prompt_txt = spec.files[str(run / "prompt.txt")]
    assert "bob\\bob\\scripts" not in prompt_txt
    assert "bob/bob/scripts" not in prompt_txt
    assert ".cursor/mcp.json" in prompt_txt or ".cursor\\mcp.json" in prompt_txt
    assert "skill-dag-mcp-down" in prompt_txt


def test_cursor_launch_leaves_user_mcp_unchanged(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cursor_home = home / ".cursor"
    cursor_home.mkdir(parents=True)
    user_mcp = cursor_home / "mcp.json"
    user_mcp.write_text('{"mcpServers":{"keep":{"command":"true"}}}\n', encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))

    worker = tmp_path / "worker"
    worker.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    spec = bw.build_launch(
        "cursor",
        "agent",
        str(worker),
        "prompt",
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    bw.write_cursor_skill_dag_mcp_config_if_agent(spec)
    written = worker / ".cursor" / "mcp.json"
    assert written.is_file()
    data = json.loads(written.read_text(encoding="utf-8"))
    assert "skill-dag" in data["mcpServers"]
    assert user_mcp.read_text(encoding="utf-8") == '{"mcpServers":{"keep":{"command":"true"}}}\n'


def test_plan_cursor_does_not_write_mcp(tmp_path):
    worker = tmp_path / "plan"
    worker.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    spec = bw.build_launch(
        "cursor",
        "plan",
        str(worker),
        "prompt",
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert spec.write_cursor_skill_dag_mcp is False
    assert not any(p.replace("\\", "/").endswith(".cursor/mcp.json") for p in spec.files)
    bw.write_cursor_skill_dag_mcp_config_if_agent(spec)
    assert not (worker / ".cursor" / "mcp.json").exists()


def test_fr8785_flat_install_spaces_prompt_matches_mcp_and_once_resolve(
    tmp_path: Path, monkeypatch
):
    """Flat ``<root>\\scripts\\skill_dag_mcp.py`` + seat ``worker``; path may contain spaces."""
    root = tmp_path / "AI install with spaces"
    worker = root / "worker"
    scripts = root / "scripts"
    run = tmp_path / "run"
    worker.mkdir(parents=True)
    scripts.mkdir(parents=True)
    run.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    src_mcp = ROOT / "bob" / "scripts" / "skill_dag_mcp.py"
    src_idx = ROOT / "bob" / "scripts" / "skill_dag_index.py"
    flat_mcp = scripts / "skill_dag_mcp.py"
    shutil.copy2(src_mcp, flat_mcp)
    shutil.copy2(src_idx, scripts / "skill_dag_index.py")

    monkeypatch.setattr(
        bw, "skill_dag_mcp_script_path", lambda *_a, **_k: flat_mcp.resolve()
    )

    # Assigned worktree with a unique MRB skill for --once resolve
    job_wt = tmp_path / "job-wt"
    mrb_skill = job_wt / ".grok" / "skills" / "bobiverse-bob-job-mrb"
    mrb_skill.mkdir(parents=True)
    (mrb_skill / "SKILL.md").write_text(
        "---\nname: bobiverse-bob-job-mrb\ndescription: mrb job\ndepends_on: []\n---\n\n"
        "# FR8785-MRB-BODY\n",
        encoding="utf-8",
    )
    # build_launch reads BOB_JOB_WORKTREE into mcp.json --job-worktree-file pointer
    monkeypatch.setenv("BOB_JOB_WORKTREE", str(job_wt))

    prompt = bw.worker_prompt(str(worker), str(run), "marchhare", "marchhare-1")
    spec = bw.build_launch(
        "cursor",
        "agent",
        str(worker),
        prompt,
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    mcp_key = str(worker / ".cursor" / "mcp.json")
    assert mcp_key in spec.files
    cfg = json.loads(spec.files[mcp_key])["mcpServers"]["skill-dag"]
    args = list(cfg["args"])
    assert Path(args[0]).resolve() == flat_mcp.resolve()
    assert "--job-worktree-file" in args
    ptr_path = Path(args[args.index("--job-worktree-file") + 1])
    assert job_wt.as_posix() in ptr_path.read_text(encoding="utf-8").replace("\\", "/")
    prompt_txt = spec.files[str(run / "prompt.txt")]
    assert "bob\\bob\\scripts" not in prompt_txt
    assert "bob/bob/scripts" not in prompt_txt
    assert ".cursor/mcp.json" in prompt_txt or ".cursor\\mcp.json" in prompt_txt
    assert "job-worktree-file" in prompt_txt

    env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    resolve = subprocess.run(
        [sys.executable, *args, "--once", "resolve", "--seed", "MRB"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(worker),
    )
    assert resolve.returncode == 0, resolve.stderr
    data = json.loads(resolve.stdout)
    matched = data.get("matched") or []
    assert any(m.get("id") == "bobiverse-bob-job-mrb" for m in matched), data
    path = next(m["path"] for m in matched if m["id"] == "bobiverse-bob-job-mrb")
    assert "FR8785" in path or "job-wt" in path.replace("\\", "/")
    get_skill = subprocess.run(
        [sys.executable, *args, "--once", "get_skill", "--path", path],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(worker),
    )
    assert get_skill.returncode == 0, get_skill.stderr
    body = json.loads(get_skill.stdout)
    assert body.get("ok") is True
    assert "FR8785-MRB-BODY" in (body.get("body") or "")
