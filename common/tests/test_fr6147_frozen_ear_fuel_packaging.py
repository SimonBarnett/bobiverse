"""Frozen bob-ear.exe packaging for the OpenCode fuel publisher.

prefer_install_scripts_path runs before import bobreport, so an existing
scripts/bobreport.py shadows the PyInstaller embed even after a rebuild.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import bobreport
from repo_layout import ROOT

BUILD = ROOT / "bob" / "scripts" / "Build-BobEar.ps1"
AGENT = ROOT / "common" / "scripts" / "irc_agent.py"


def _ear_import_snippet() -> str:
    """The real startup lines: prefer_install_scripts_path, then import bobreport."""
    src = AGENT.read_text(encoding="utf-8")
    fn_start = src.index("FROZEN_SCRIPT_OVERLAY")
    fn_end = src.index("\n# FR #6237:", fn_start)
    boot_start = src.index("_mei_scripts = str(Path(__file__).resolve().parent)")
    boot_end = src.index("import bobreport", boot_start)
    boot = src[boot_start:boot_end] + "import bobreport\n"
    boot = "\n".join(
        line for line in boot.splitlines() if "bob_recycle" not in line
    )
    return src[fn_start:fn_end] + "\n" + boot + "\n"


def _run_frozen_import(install: Path, mei: Path, exe: Path, *, gitclaim: bool = False) -> str:
    (mei / "irc_agent.py").write_text("# embed stand-in\n", encoding="utf-8")
    tail = (
        "print(bobreport.MARKER)\n"
        "print(bobreport.OPENCODE_FUEL_HELPER_DEADLINE_S)\n"
    )
    if gitclaim:
        tail += (
            "import gitclaim\n"
            "print('gitclaim=' + str(callable(getattr(gitclaim, 'shop_line_resets_bored_clock', None))))\n"
            "fn = getattr(gitclaim, 'shop_line_resets_bored_clock', None)\n"
            "print('call=' + str(bool(fn('DONE job')) if fn else 'missing'))\n"
        )
    driver = textwrap.dedent(
        f"""
        import os, sys
        from pathlib import Path
        os.environ["BOB_INSTALL_ROOT"] = {str(install)!r}
        sys.frozen = True
        sys._MEIPASS = {str(mei)!r}
        sys.executable = {str(exe)!r}
        sys.path.insert(0, {str(mei)!r})
        __file__ = {str(mei / "irc_agent.py")!r}
        """
    ) + _ear_import_snippet() + tail
    proc = subprocess.run(
        [sys.executable, "-c", driver],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout


def test_deploy_manifest_installs_disk_bobreport_when_present():
    spec = bobreport.FROZEN_EAR_FUEL_DEPLOY
    assert spec["overlay_modules"] == ("bobreport",)
    assert spec["disk_module_shadows_embed"] is False
    assert spec["do_not_delete_disk_module"] is True
    assert spec["script_copy_sufficient"] is False
    present = spec["when_disk_module_present"]
    assert present[0] == "scripts/bob-ear.exe"
    assert "scripts/bobreport.py" in present
    assert "tools/Get-BobOpencodeFuel.ps1" in present
    assert "scripts/opencode_fuel.py" in present
    absent = spec["when_disk_module_absent"]
    assert "scripts/bob-ear.exe" in absent
    assert "scripts/bobreport.py" not in absent
    assert "tools/Get-BobOpencodeFuel.ps1" in absent
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


def test_old_disk_bobreport_falls_back_to_embed(tmp_path: Path):
    """Old on-disk bobreport stays put and is not the module the ear imports."""
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    mei = tmp_path / "_MEI"
    mei.mkdir()
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    (scripts / "bobreport.py").write_text(
        "MARKER = 'disk'\nOPENCODE_FUEL_HELPER_DEADLINE_S = 5.0\n",
        encoding="utf-8",
    )
    (mei / "bobreport.py").write_text(
        "MARKER = 'embed'\nOPENCODE_FUEL_HELPER_DEADLINE_S = 120.0\n",
        encoding="utf-8",
    )
    out = _run_frozen_import(install, mei, exe)
    assert out.splitlines()[:2] == ["embed", "120.0"]
    assert (scripts / "bobreport.py").is_file()


def test_pinned_disk_bobreport_overlays_embed(tmp_path: Path):
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    mei = tmp_path / "_MEI"
    mei.mkdir()
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    (scripts / "bobreport.py").write_text(
        "MARKER = 'disk'\nOPENCODE_FUEL_HELPER_DEADLINE_S = 120.0\n"
        "def opencode_install_root(env=None):\n    return None\n",
        encoding="utf-8",
    )
    (mei / "bobreport.py").write_text(
        "MARKER = 'embed'\nOPENCODE_FUEL_HELPER_DEADLINE_S = 5.0\n",
        encoding="utf-8",
    )
    out = _run_frozen_import(install, mei, exe)
    assert out.splitlines()[:2] == ["disk", "120.0"]


def test_old_disk_gitclaim_does_not_shadow_embed(tmp_path: Path):
    """Installed gitclaim without shop_line_resets_bored_clock must not be imported."""
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    mei = tmp_path / "_MEI"
    mei.mkdir()
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    (scripts / "bobreport.py").write_text(
        "MARKER = 'disk'\nOPENCODE_FUEL_HELPER_DEADLINE_S = 120.0\n"
        "def opencode_install_root(env=None):\n    return None\n",
        encoding="utf-8",
    )
    (scripts / "gitclaim.py").write_text(
        "def is_bored_command(body):\n    return False\n",
        encoding="utf-8",
    )
    (mei / "bobreport.py").write_text(
        "MARKER = 'embed'\nOPENCODE_FUEL_HELPER_DEADLINE_S = 5.0\n",
        encoding="utf-8",
    )
    (mei / "gitclaim.py").write_text(
        "def shop_line_resets_bored_clock(body):\n"
        "    return str(body).startswith('DONE')\n",
        encoding="utf-8",
    )
    out = _run_frozen_import(install, mei, exe, gitclaim=True)
    lines = out.splitlines()
    assert lines[:2] == ["disk", "120.0"]
    assert "gitclaim=True" in lines
    assert "call=True" in lines
    assert (scripts / "gitclaim.py").is_file()


def test_absent_disk_bobreport_imports_embed(tmp_path: Path):
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    mei = tmp_path / "_MEI"
    mei.mkdir()
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    assert not (scripts / "bobreport.py").exists()
    (mei / "bobreport.py").write_text(
        "MARKER = 'embed'\nOPENCODE_FUEL_HELPER_DEADLINE_S = 120.0\n",
        encoding="utf-8",
    )
    out = _run_frozen_import(install, mei, exe)
    assert out.splitlines()[:2] == ["embed", "120.0"]


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
