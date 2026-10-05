"""Hostile MRB #2417: FR #2413 shared launch must be consumable by tray/CLI, not only a Python helper."""
from __future__ import annotations

import json

import bob_worker as bw
from repo_layout import ROOT


def test_describe_launch_matches_helper(tmp_path, monkeypatch, capsys):
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "plan").mkdir()
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ-fake")
    local = tmp_path / "local"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    expected = bw.describe_worker_exe_launch(
        str(root), "plan", "marchhare", local_app_data=str(local), source="tray"
    )
    code = bw.main(
        [
            "--describe-launch",
            "--mode",
            "plan",
            "--install-root",
            str(root),
            "--machine-id",
            "marchhare",
        ]
    )
    assert code == bw.EXIT_OK
    got = json.loads(capsys.readouterr().out.strip())
    assert got == expected
    assert got["cwd"].endswith("plan")
    assert got["argv"][:4] == ["--mode", "plan", "--install-root", str(root)]


def test_watch_bob_tray_prefers_describe_launch():
    text = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    assert "--describe-launch" in text
    assert "ConvertFrom-Json" in text
    assert "Start-BobTrayWorkerExe" in text


def test_bob_tray_cs_keeps_argv_contract_aligned_with_describe(tmp_path):
    """TipForm still embeds launch; argv/cwd/hash tokens must match describe_worker_exe_launch."""
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    assert 'new string[] { "--mode", mode, "--install-root", root }' in cs
    assert 'mode == "plan" ? "plan" : "worker"' in cs
    assert "Bobiverse" in cs and "worker" in cs and "bin" in cs
    assert "bob-worker-" in cs
    assert "FR #2413 / MRB #2417" in cs
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "plan").mkdir()
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ")
    plan = bw.describe_worker_exe_launch(str(root), "agent", "x", local_app_data=str(tmp_path / "la"))
    assert plan["argv"][0:3] == ["--mode", "agent", "--install-root"]
    assert "Bobiverse" in plan["run_exe"] and "bob-worker-" in plan["run_exe"]


def test_source_tray_cli_remote_still_equal(tmp_path):
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ")
    la = tmp_path / "la"
    la.mkdir()
    a = bw.describe_worker_exe_launch(str(root), "agent", "m", local_app_data=str(la), source="tray")
    b = bw.describe_worker_exe_launch(str(root), "agent", "m", local_app_data=str(la), source="cli")
    c = bw.describe_worker_exe_launch(str(root), "agent", "m", local_app_data=str(la), source="remote")
    assert a == b == c
