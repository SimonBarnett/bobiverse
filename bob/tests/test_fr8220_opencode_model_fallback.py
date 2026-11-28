"""FR #8220: OpenCode launch never throws when tray pin is empty; free default + env stamp."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import worker_start_model as wsm

FREE = "opencode/deepseek-v4.1-flash-free"
OP = r"C:\o\opencode.exe"


def test_fr8220_build_launch_empty_tray_bakes_free_default(tmp_path: Path, monkeypatch):
    """Hostile: empty configured_start_model must bake free default, never throw (flamingo-22516)."""
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    monkeypatch.delenv("BOB_WORKER_MODEL", raising=False)
    monkeypatch.setattr(wsm, "configured_start_model", lambda kind, cfg=None: "")
    monkeypatch.setattr(wsm, "load_worker_start_config", lambda env=None: {})
    monkeypatch.setattr(wsm, "env_model_pin", lambda kind, env=None: "")
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "Do work.", OP, tmp_path)
    script = next(v for k, v in spec.files.items() if k.endswith("launch-opencode.ps1"))
    assert "BOB_OPENCODE_MODEL is required" not in script
    assert "no exhausted glm-5.3 fallback" not in script
    assert "throw" not in script.lower() or "throw 'BOB_OPENCODE_MODEL" not in script
    assert "$model = $env:BOB_OPENCODE_MODEL" in script


def test_fr8220_build_launch_env_pin_wins_over_free_default(tmp_path: Path, monkeypatch):
    """Env pin is stamped into child env (wrapper reads $env:BOB_OPENCODE_MODEL at run time)."""
    go = "opencode-go/deepseek-v4-pro"
    monkeypatch.setenv("BOB_OPENCODE_MODEL", go)
    monkeypatch.setattr(wsm, "configured_start_model", lambda kind, cfg=None: "")
    monkeypatch.setattr(wsm, "load_worker_start_config", lambda env=None: {})
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / ".grok" / "skills").mkdir(parents=True)
    (worker / "AGENTS.md").write_text("x", encoding="utf-8")
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="opencode",
        mode="agent",
        cwd=str(worker),
        run_dir=run_dir,
        machine="redqueen",
        nick="redqueen-1",
        agent_exe=OP,
    )
    assert child["env"].get("BOB_OPENCODE_MODEL") == go
    script = next(v for k, v in child["files"].items() if k.endswith("launch-opencode.ps1"))
    assert "BOB_OPENCODE_MODEL is required" not in script


def test_fr8220_describe_stamps_env_and_launch_record(tmp_path: Path, monkeypatch):
    """Child env + launch-record.json get a concrete model when parent env and tray are empty."""
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    monkeypatch.delenv("BOB_WORKER_MODEL", raising=False)
    monkeypatch.setattr(wsm, "configured_start_model", lambda kind, cfg=None: "")
    monkeypatch.setattr(
        wsm,
        "load_worker_start_config",
        lambda env=None: {"models": {"opencodeFree": FREE}, "workerStartModels": {}},
    )
    monkeypatch.setattr(wsm, "env_model_pin", lambda kind, env=None: "")
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / ".grok" / "skills").mkdir(parents=True)
    (worker / "AGENTS.md").write_text("x", encoding="utf-8")
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="opencode",
        mode="agent",
        cwd=str(worker),
        run_dir=run_dir,
        machine="flamingo",
        nick="flamingo-22516",
        agent_exe=OP,
    )
    assert child["env"].get("BOB_OPENCODE_MODEL") == FREE
    rec = json.loads((run_dir / "launch-record.json").read_text(encoding="utf-8"))
    assert rec["kind"] == "opencode"
    assert rec["model"] == FREE
    script = next(v for k, v in child["files"].items() if k.endswith("launch-opencode.ps1"))
    assert "BOB_OPENCODE_MODEL is required" not in script
    assert "$model = $env:BOB_OPENCODE_MODEL" in script
