"""FR #7187: persist low effort; Grok --reasoning-effort; OpenCode default free."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import worker_start_model as wsm


def test_save_effort_survives_reread(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "simon"))
    p = wsm.save_worker_start_settings(effort={"grok": "low"}, env={"LOCALAPPDATA": str(tmp_path)})
    cfg = wsm.load_worker_start_config(env={"LOCALAPPDATA": str(tmp_path)})
    assert cfg["workerStartEffort"]["grok"] == "low"
    assert wsm.configured_start_effort("grok", cfg) == "low"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["workerStartEffort"]["grok"] == "low"


def test_save_effort_keeps_existing_models(tmp_path):
    p = tmp_path / "tray-models.json"
    p.write_text(
        json.dumps({"workerStartModels": {"grok": "EXAMPLE_GROK_MIN"}, "keep": True}),
        encoding="utf-8",
    )
    wsm.save_worker_start_settings(path=p, effort={"grok": "low"})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["workerStartModels"]["grok"] == "EXAMPLE_GROK_MIN"
    assert data["keep"] is True
    assert data["workerStartEffort"]["grok"] == "low"


def test_default_effort_is_low_not_high():
    cfg = wsm.load_worker_start_config({}, env={})
    assert wsm.configured_start_effort("grok", cfg) == "low"
    assert wsm.configured_start_effort("grok", cfg) != "high"


def test_grok_launch_argv_carries_low_effort():
    argv = wsm.launch_argv_with_effort("grok", ["grok.exe", "--cwd", "x"], "")
    assert "--reasoning-effort" in argv
    assert argv[argv.index("--reasoning-effort") + 1] == "low"


def test_system_and_tray_user_tray_models_path(tmp_path, monkeypatch):
    for name, folder in (("SYSTEM", tmp_path / "systemprofile"), ("simon", tmp_path / "simon")):
        local = folder / "AppData" / "Local"
        local.mkdir(parents=True)
        monkeypatch.setenv("LOCALAPPDATA", str(local))
        monkeypatch.setenv("USERNAME", name)
        monkeypatch.setenv("USERPROFILE", str(folder))
        got = wsm.tray_models_path()
        assert got == local / "Bobiverse" / "tray-models.json"


def test_describe_grok_launch_record_and_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    wsm.save_worker_start_settings(effort={"grok": "low"})
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / ".grok" / "skills").mkdir(parents=True)
    (worker / "AGENTS.md").write_text("x", encoding="utf-8")
    (tmp_path / "common" / "scripts").mkdir(parents=True)
    (tmp_path / "common" / "scripts" / "skill_dag_mcp.py").write_text("#\n", encoding="utf-8")
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="grok",
        mode="agent",
        cwd=str(worker),
        run_dir=run_dir,
        machine="flamingo",
        nick="flamingo-1",
        agent_exe=r"C:\fake\agent.exe",
    )
    assert "--reasoning-effort" in child["argv"]
    assert child["argv"][child["argv"].index("--reasoning-effort") + 1] == "low"
    rec = json.loads((run_dir / "launch-record.json").read_text(encoding="utf-8"))
    assert rec["effort"] == "low"
    assert rec["kind"] == "grok"
    assert child["env"].get("BOB_WORKER_ACTUAL_EFFORT") == "low"


def test_hello_uses_actual_not_configured_on_mismatch():
    line = bw.worker_hello_line("opencode", model="opencode-go/deepseek-v4-pro", build="abc")
    assert "opencode-go/deepseek-v4-pro" in line
    assert "actual=$model" not in line


def test_opencode_default_is_flash_free_not_go():
    assert wsm.default_opencode_free_model({}) == "opencode/deepseek-v4.1-flash-free"
    assert wsm.opencode_is_go_or_paid("opencode-go/deepseek-v4-pro") is True
    assert wsm.opencode_is_go_or_paid("opencode/deepseek-v4.1-flash-free") is False


def test_mismatch_log_interpolates_actual():
    logs: list[str] = []
    bw.report_configured_start_model_unavailable(
        kind="opencode",
        configured="opencode/deepseek-v4.1-flash-free",
        actual="opencode-go/deepseek-v4-pro",
        machine="redqueen",
        nick="redqueen-1",
        log=logs.append,
        filer_post=lambda *_a, **_k: {"ok": True},
    )
    joined = " ".join(logs)
    assert "opencode-go/deepseek-v4-pro" in joined
    assert "actual=$model" not in joined


def test_tray_cs_pins_effort_persist():
    from repo_layout import ROOT

    text = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    assert "workerStartEffort" in text
    assert "TrayModelsJsonPath" in text
    assert "FR #7187" in text


def test_digest_fields_include_low_effort():
    fields = wsm.digest_seat_model_fields(cli="grok", actual="EXAMPLE_GROK_MIN", cfg={}, effort="low")
    assert fields["start_effort"] == "low"


def test_bound_grok_home_config_has_low_effort(tmp_path):
    import skill_dag_bound as bound

    user = tmp_path / "user-grok"
    user.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    home = bound.prepare_seat_grok_home(run_dir, user_grok_home=user)
    cfg = (home / "config.toml").read_text(encoding="utf-8")
    assert "reasoning_effort" in cfg
    assert "low" in cfg
