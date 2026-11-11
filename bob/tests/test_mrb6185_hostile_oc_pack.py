"""docs/mrb-6185: hostile pins for FR #6159 OpenCode flat pack (PR #6185).

Pins empty common\\scripts directory must not block Get-BobOpencodeFuel,
worker Shared ships bob-setup-opencode, and pack stage lists OpenCode paths.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT
from test_fr6159_oc_pack_layout import _opencode_fuel_fixture_env

OPENCODE_FUEL_PS1 = ROOT / "bob" / "tray" / "tools" / "Get-BobOpencodeFuel.ps1"
OPENCODE_FUEL_PY = ROOT / "common" / "scripts" / "opencode_fuel.py"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
PACK = ROOT / "bob" / "tests" / "test_bob_worker_pack_020.py"
WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"


def test_mrb6185_ps1_source_leaf_not_container_break():
    src = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "PathType Leaf" in src
    assert "FR #6159" in src
    # Must not stop on empty common\\scripts directory alone (old bug: PathType Container).
    assert "PathType Container" not in src


def test_mrb6185_worker_shared_includes_setup_skill():
    text = COMMON.read_text(encoding="utf-8-sig")
    assert "'bob-setup-opencode'" in text
    assert "Name = 'worker'" in text


def test_mrb6185_pack_stage_pins_opencode_paths():
    src = PACK.read_text(encoding="utf-8")
    assert 'tools" / "Get-BobOpencodeFuel.ps1"' in src or "Get-BobOpencodeFuel.ps1" in src
    assert 'scripts" / "opencode_fuel.py"' in src or "opencode_fuel.py" in src
    assert "bob-setup-opencode" in src


def test_mrb6185_build_launch_threads_install_root():
    src = WORKER.read_text(encoding="utf-8")
    assert "install_root=install_root" in src or "install_root=self.install_root" in src
    assert 'root / "scripts" / "opencode_fuel.py"' in src


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell")
@pytest.mark.skipif(not shutil.which("python"), reason="python.exe required")
def test_mrb6185_empty_common_scripts_dir_does_not_block_flat_helper(tmp_path: Path):
    """Empty common\\scripts must not win; flat scripts\\opencode_fuel.py resolves."""
    install = tmp_path / "bob"
    tools = install / "tools"
    scripts = install / "scripts"
    elsewhere = tmp_path / "elsewhere"
    tools.mkdir(parents=True)
    scripts.mkdir(parents=True)
    elsewhere.mkdir(parents=True)
    (install / "common" / "scripts").mkdir(parents=True)  # empty dir trap
    shutil.copy(OPENCODE_FUEL_PS1, tools / "Get-BobOpencodeFuel.ps1")
    shutil.copy(OPENCODE_FUEL_PY, scripts / "opencode_fuel.py")
    # FR #6676: same USAGE_URL scrub as FR #6670 / test_fr6159 (else go stays null).
    env = _opencode_fuel_fixture_env()
    py_dir = str(Path(sys.executable).resolve().parent)
    env["PATH"] = py_dir + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tools / "Get-BobOpencodeFuel.ps1"),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(elsewhere),
        timeout=60,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    parsed = json.loads(result.stdout.strip().splitlines()[-1])
    assert parsed["free"] == 100
    assert parsed["go"] == 50
