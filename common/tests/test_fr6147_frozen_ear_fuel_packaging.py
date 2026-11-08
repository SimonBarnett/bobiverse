"""Frozen bob-ear.exe packaging for the OpenCode fuel publisher.

Copying scripts/bobreport.py is not enough: the ear imports bobreport at
startup from the PyInstaller embed. The cache must be the install run dir,
not _MEIPASS.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
from repo_layout import ROOT

BUILD = ROOT / "bob" / "scripts" / "Build-BobEar.ps1"
AGENT = ROOT / "common" / "scripts" / "irc_agent.py"


def test_deploy_manifest_requires_rebuilt_ear_not_a_script_copy():
    spec = bobreport.FROZEN_EAR_FUEL_DEPLOY
    assert spec["script_copy_sufficient"] is False
    assert spec["required_frozen"] == ("scripts/bob-ear.exe",)
    assert "tools/Get-BobOpencodeFuel.ps1" in spec["helper_outside_exe"]
    assert "scripts/opencode_fuel.py" in spec["helper_outside_exe"]
    assert spec["cache_rel"] == "run/opencode-fuel.json"
    assert spec["builder"] == "bob/scripts/Build-BobEar.ps1"
    assert spec["entry"] == "scripts/irc_agent.py"
    assert bobreport.on_disk_bobreport_replaces_embed(
        exe_calls_prefer_install_scripts=False
    ) is False
    assert bobreport.on_disk_bobreport_replaces_embed(
        exe_calls_prefer_install_scripts=True
    ) is True


def test_build_bob_ear_onefile_embeds_irc_agent_and_does_not_exclude_bobreport():
    text = BUILD.read_text(encoding="utf-8-sig")
    assert "--onefile" in text
    assert "irc_agent.py" in text
    assert "bob-ear.exe" in text or "--name', 'bob-ear'" in text or "'bob-ear'" in text
    # Excludes are tkinter/numpy/pandas/matplotlib only. bobreport must be collected.
    assert "--exclude-module', 'bobreport'" not in text
    assert "--exclude-module\", 'bobreport'" not in text
    agent = AGENT.read_text(encoding="utf-8")
    call = agent.find("_install_scripts = prefer_install_scripts_path(")
    imp = agent.find("import bobreport")
    assert call > 0 and imp > call


def test_frozen_meipass_file_uses_exe_install_root_for_helper_and_cache(
    tmp_path: Path, monkeypatch
):
    """__file__ under _MEIPASS must not become the cache or helper directory."""
    install = tmp_path / "ai" / "bob"
    tools = install / "tools"
    scripts = install / "scripts"
    tools.mkdir(parents=True)
    scripts.mkdir(parents=True)
    helper = tools / "Get-BobOpencodeFuel.ps1"
    helper.write_text("# helper\n", encoding="utf-8")
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    mei = tmp_path / "Temp" / "_MEI999"
    mei.mkdir(parents=True)
    (mei / "bobreport.py").write_text("# embedded old publisher\n", encoding="utf-8")

    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_CACHE_FILE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_HELPER", raising=False)
    monkeypatch.setattr(bobreport, "__file__", str(mei / "bobreport.py"), raising=False)
    monkeypatch.setattr(bobreport.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bobreport.sys, "_MEIPASS", str(mei), raising=False)
    monkeypatch.setattr(bobreport.sys, "executable", str(exe), raising=False)

    assert bobreport._path_under_meipass(mei / "bobreport.py") is True
    root = bobreport.opencode_install_root({})
    assert root == install.resolve()
    assert "MEI" not in str(root)
    found = bobreport._resolve_opencode_fuel_helper_ps1({})
    assert found == helper.resolve()
    cache = bobreport._opencode_fuel_cache_file({})
    assert cache == root / "run" / "opencode-fuel.json"
    assert "_MEI" not in str(cache)
    assert cache.parent.name == "run"


def test_bob_install_root_wins_over_frozen_exe_layout(tmp_path: Path, monkeypatch):
    install = tmp_path / "real"
    other = tmp_path / "other"
    (install / "tools").mkdir(parents=True)
    helper = install / "tools" / "Get-BobOpencodeFuel.ps1"
    helper.write_text("# helper\n", encoding="utf-8")
    (other / "scripts").mkdir(parents=True)
    exe = other / "scripts" / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    mei = tmp_path / "_MEI"
    mei.mkdir()
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setattr(bobreport.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bobreport.sys, "_MEIPASS", str(mei), raising=False)
    monkeypatch.setattr(bobreport.sys, "executable", str(exe), raising=False)
    monkeypatch.setattr(bobreport, "__file__", str(mei / "bobreport.py"), raising=False)
    assert bobreport.opencode_install_root() == Path(install)
    assert bobreport._resolve_opencode_fuel_helper_ps1() == helper.resolve()
    cache = bobreport._opencode_fuel_cache_file(None)
    assert cache == Path(install) / "run" / "opencode-fuel.json"


def test_deadline_kill_uses_windows_process_tree(monkeypatch):
    """120s deadline must taskkill /T the powershell, not leave opencode children."""
    calls: list[tuple] = []

    class Proc:
        pid = 4242

        def poll(self):
            return None

        def kill(self):
            calls.append(("kill",))

    def fake_run(argv, **kwargs):  # noqa: ARG001
        calls.append(tuple(argv))

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setattr(bobreport.os, "name", "nt")
    monkeypatch.setattr("subprocess.run", fake_run)
    bobreport._kill_opencode_fuel_process(Proc())
    assert ("taskkill", "/T", "/F", "/PID", "4242") in calls
    assert ("kill",) in calls


def test_deadline_kill_without_pid_does_not_taskkill(monkeypatch):
    calls: list[tuple] = []

    class Proc:
        def poll(self):
            return None

        def kill(self):
            calls.append(("kill",))

    def fake_run(argv, **kwargs):  # noqa: ARG001
        calls.append(tuple(argv))

    monkeypatch.setattr(bobreport.os, "name", "nt")
    monkeypatch.setattr("subprocess.run", fake_run)
    bobreport._kill_opencode_fuel_process(Proc())
    assert calls == [("kill",)]
