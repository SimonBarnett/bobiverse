"""FR #6898: OpenCode job runs load skill-dag MCP and see resolve + intake harvest cues."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import opencode_seat_contract as osc


def _repo_shaped(tmp_path: Path) -> tuple[Path, Path]:
    script = tmp_path / "bob" / "scripts" / "skill_dag_mcp.py"
    script.parent.mkdir(parents=True)
    script.write_text("# skill-dag mcp stub\n", encoding="utf-8")
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / ".grok" / "skills").mkdir(parents=True)
    return worker, script


def test_opencode_launch_writes_project_mcp_not_user_profile(tmp_path, monkeypatch):
    worker, script = _repo_shaped(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    user_cfg = home / ".config" / "opencode" / "opencode.json"
    user_cfg.parent.mkdir(parents=True)
    user_cfg.write_text('{"model":"keep"}\n', encoding="utf-8")
    before = user_cfg.read_bytes()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    run = tmp_path / "run"
    run.mkdir()
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(worker),
        "standing prompt",
        "opencode.exe",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert getattr(spec, "write_opencode_skill_dag_mcp", False) is True
    mcp_path = str(worker / bw.OPENCODE_SKILL_DAG_MCP_RELPATH)
    assert mcp_path in spec.files
    data = json.loads(spec.files[mcp_path])
    servers = (data.get("mcp") or {})
    # Flat mcp.skill-dag (OpenCode accepts this) or mcp.servers.skill-dag
    entry = servers.get("skill-dag") or (servers.get("servers") or {}).get("skill-dag")
    assert entry is not None, data
    cmd = entry.get("command") or []
    assert cmd and cmd[0] == "python"
    assert any(str(a).replace("\\", "/").endswith("skill_dag_mcp.py") for a in cmd)

    bw.write_opencode_skill_dag_mcp_config_if_agent(spec)
    assert (worker / "opencode.json").is_file()
    assert user_cfg.read_bytes() == before


def test_framed_fr_assign_line_has_resolve_and_intake(tmp_path):
    wt = tmp_path / "fr-6898"
    wt.mkdir()
    key = "FR SimonBarnett/bobiverse#6898"
    from_line = (
        "FROM jeeves #redqueen redqueen-1: FR SimonBarnett/bobiverse#6898 "
        "https://github.com/SimonBarnett/bobiverse/issues/6898"
    )
    steps = bw.opencode_job_finish_steps(
        job_key=key,
        worktree=str(wt),
        outbox=str(wt / ".bob" / "outbox.txt"),
    )
    enriched = f"{from_line} {steps}"
    wire = osc.frame_opencode_message(enriched, key, str(wt))
    parsed = osc.parse_opencode_frame(osc.console_text(wire, maxlen=2000))
    assert parsed is not None
    line = parsed["line"]
    assert "resolve" in line
    assert "Report-BobiverseIntakeIssue.ps1" in line


def test_finish_reprompt_has_resolve_and_intake(tmp_path):
    wt = tmp_path / "fr-6898"
    wt.mkdir()
    text = bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#6898",
        worktree=str(wt),
        outbox=str(wt / ".bob" / "outbox.txt"),
    )
    assert "resolve" in text
    assert "Report-BobiverseIntakeIssue.ps1" in text
    reminder = bw.opencode_done_miss_reminder_line(
        shop="#redqueen",
        outbox=str(wt / ".bob" / "outbox.txt"),
        job_key="FR SimonBarnett/bobiverse#6898",
        worktree=str(wt),
    )
    parsed = osc.parse_opencode_frame(osc.console_text(reminder, maxlen=2000))
    assert parsed is not None
    assert "resolve" in parsed["line"]
    assert "Report-BobiverseIntakeIssue.ps1" in parsed["line"]
