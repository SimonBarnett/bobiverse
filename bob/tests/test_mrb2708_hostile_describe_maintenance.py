"""MRB #2708 hostile: FR #2698 describe-launch maintenance must never silently become agent."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import pytest
from repo_layout import ROOT, resolve


def _bob_root(tmp_path: Path) -> Path:
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "plan").mkdir()
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ")
    return root


def test_mrb2708_no_silent_agent_fallback_in_source():
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert 'mode_l = "agent"' not in src or "unknown bob-worker mode" in src
    # Old whitelist that dropped maintenance must be gone.
    assert 'if mode_l not in ("agent", "plan", "monitor"):' not in src
    assert '_WORKER_EXE_MODES = ("agent", "plan", "monitor", "maintenance")' in src
    assert "never silently map to agent" in src or "FR #2698" in src


def test_mrb2708_monitor_uses_work_root_not_worker_cwd(tmp_path):
    root = _bob_root(tmp_path)
    jeeves = tmp_path / "jeeves"
    jeeves.mkdir()
    local = tmp_path / "la"
    local.mkdir()
    plan = bw.describe_worker_exe_launch(
        str(root), "monitor", work_root=str(jeeves), local_app_data=str(local)
    )
    assert plan["mode"] == "monitor"
    assert plan["cwd"] == str(jeeves)
    assert plan["cwd"] != str(root / "worker")
    assert "--work-root" in plan["argv"]
    assert plan["argv"][plan["argv"].index("--work-root") + 1] == str(jeeves)


def test_mrb2708_maintenance_tray_cli_remote_equal(tmp_path):
    root = _bob_root(tmp_path)
    jeeves = tmp_path / "jeeves"
    jeeves.mkdir()
    local = tmp_path / "la"
    local.mkdir()
    kwargs = dict(
        install_root=str(root),
        mode="maintenance",
        machine_id="marchhare",
        work_root=str(jeeves),
        local_app_data=str(local),
    )
    a = bw.describe_worker_exe_launch(**kwargs, source="tray")
    b = bw.describe_worker_exe_launch(**kwargs, source="cli")
    c = bw.describe_worker_exe_launch(**kwargs, source="remote")
    assert a == b == c
    assert a["mode"] == "maintenance"
    assert a["title"] == bw.MAINTENANCE_TITLE


def test_mrb2708_cli_unknown_mode_exits_nonzero(tmp_path, monkeypatch, capsys):
    root = _bob_root(tmp_path)
    local = tmp_path / "la"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    # argparse choices reject before describe; must not print an agent plan JSON.
    with pytest.raises(SystemExit) as ei:
        bw.main(
            [
                "--describe-launch",
                "--mode",
                "not-a-mode",
                "--install-root",
                str(root),
            ]
        )
    assert ei.value.code == 2
    out = capsys.readouterr().out.strip()
    assert '"mode": "agent"' not in out


def test_mrb2708_ps1_and_py_keep_handbuilt_fallback_when_describe_stale():
    ps1 = resolve("jeeves/scripts/Start-JeevesMaintenance.ps1").read_text(encoding="utf-8")
    py = resolve("common/scripts/jeeves_maintenance.py").read_text(encoding="utf-8")
    assert "fallback" in ps1.lower() or "hand-built" in ps1.lower()
    assert "[string]$plan.mode -eq 'maintenance'" in ps1
    assert "fall back" in py.lower() or "FR #2698" in py
    assert 'plan.get("mode") or "") == "maintenance"' in py or "mode\") or \"\") == \"maintenance\"" in py


def test_mrb2708_agent_and_plan_unchanged_without_work_root(tmp_path):
    root = _bob_root(tmp_path)
    local = tmp_path / "la"
    local.mkdir()
    agent = bw.describe_worker_exe_launch(str(root), "agent", local_app_data=str(local))
    plan = bw.describe_worker_exe_launch(str(root), "plan", local_app_data=str(local))
    assert agent["mode"] == "agent" and agent["cwd"].endswith("worker")
    assert plan["mode"] == "plan" and plan["cwd"].endswith("plan")
    assert "--work-root" not in agent["argv"]
    assert "--work-root" not in plan["argv"]
