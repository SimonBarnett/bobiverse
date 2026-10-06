"""FR #2698: --describe-launch --mode maintenance must not fall back to agent."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import pytest
from repo_layout import resolve


def _bob_root(tmp_path: Path) -> Path:
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "plan").mkdir()
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ")
    return root


def test_describe_maintenance_mode_work_root_title_and_argv(tmp_path):
    root = _bob_root(tmp_path)
    jeeves = tmp_path / "jeeves"
    jeeves.mkdir()
    (jeeves / "AGENTS.md").write_text("x", encoding="utf-8")
    (jeeves / "assets").mkdir()
    icon = jeeves / "assets" / "jeeves-butler.ico"
    icon.write_bytes(b"ico")
    local = tmp_path / "la"
    local.mkdir()
    plan = bw.describe_worker_exe_launch(
        str(root),
        "maintenance",
        "marchhare",
        work_root=str(jeeves),
        local_app_data=str(local),
        source="cli",
    )
    assert plan["mode"] == "maintenance"
    assert plan["cwd"] == str(jeeves)
    assert plan["title"] == bw.MAINTENANCE_TITLE
    assert plan["argv"][:4] == ["--mode", "maintenance", "--install-root", str(root)]
    assert "--work-root" in plan["argv"]
    assert plan["argv"][plan["argv"].index("--work-root") + 1] == str(jeeves)
    assert plan["argv"][plan["argv"].index("--machine-id") + 1] == "marchhare"
    assert plan.get("icon") == str(icon)


def test_describe_maintenance_default_work_root_sibling_jeeves(tmp_path):
    ai = tmp_path / "ai"
    root = ai / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ")
    jeeves = ai / "jeeves"
    jeeves.mkdir()
    (jeeves / "AGENTS.md").write_text("x", encoding="utf-8")
    local = tmp_path / "la"
    local.mkdir()
    plan = bw.describe_worker_exe_launch(
        str(root), "maintenance", local_app_data=str(local)
    )
    assert plan["mode"] == "maintenance"
    assert plan["cwd"] == str(jeeves)
    assert "--work-root" in plan["argv"]


def test_describe_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown"):
        bw.describe_worker_exe_launch("C:\\x", "not-a-mode")


def test_describe_launch_cli_maintenance_json(tmp_path, monkeypatch, capsys):
    root = _bob_root(tmp_path)
    jeeves = tmp_path / "jeeves"
    jeeves.mkdir()
    (jeeves / "AGENTS.md").write_text("x", encoding="utf-8")
    local = tmp_path / "la"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    expected = bw.describe_worker_exe_launch(
        str(root), "maintenance", work_root=str(jeeves), local_app_data=str(local), source="cli"
    )
    code = bw.main(
        [
            "--describe-launch",
            "--mode",
            "maintenance",
            "--install-root",
            str(root),
            "--work-root",
            str(jeeves),
        ]
    )
    assert code == bw.EXIT_OK
    got = json.loads(capsys.readouterr().out.strip())
    assert got == expected
    assert got["mode"] == "maintenance"
    assert got["cwd"] == str(jeeves)


def test_start_jeeves_maintenance_prefers_describe_launch():
    ps1 = resolve("jeeves/scripts/Start-JeevesMaintenance.ps1").read_text(encoding="utf-8")
    assert "--describe-launch" in ps1
    assert "ConvertFrom-Json" in ps1
    assert "maintenance" in ps1


def test_jeeves_maintenance_spawn_uses_describe_launch():
    src = resolve("common/scripts/jeeves_maintenance.py").read_text(encoding="utf-8")
    assert "describe-launch" in src or "describe_worker_exe_launch" in src
    assert "FR #2698" in src


def test_described_argv_matches_legacy_maintenance_contract(tmp_path):
    """Described argv equals the hand-built Start-JeevesMaintenance / spawn contract."""
    root = _bob_root(tmp_path)
    jeeves = tmp_path / "jeeves"
    jeeves.mkdir()
    local = tmp_path / "la"
    local.mkdir()
    plan = bw.describe_worker_exe_launch(
        str(root), "maintenance", work_root=str(jeeves), local_app_data=str(local)
    )
    # Legacy: --mode maintenance --install-root <bob> --work-root <jeeves>
    assert plan["argv"] == [
        "--mode",
        "maintenance",
        "--install-root",
        str(root),
        "--work-root",
        str(jeeves),
    ]
