"""FR #7315: powershell.exe 5.1 Get-FileHash under a pwsh-7 PSModulePath."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import winps51
import bob.scripts.bob_worker as bw

PS = shutil.which("powershell.exe")
PWSH7_SHADOW = r"C:\Program Files\PowerShell\7\Modules"


def test_fr7315_helper_forces_51_modules():
    poisoned = {"PSModulePath": PWSH7_SHADOW + os.pathsep + winps51.WINPS51_MODULE_PATH, "KEEP": "1"}
    got = winps51.env_for_powershell_exe(poisoned)
    assert got["PSModulePath"] == winps51.WINPS51_MODULE_PATH
    assert got["KEEP"] == "1"
    assert PWSH7_SHADOW not in got["PSModulePath"]


def test_fr7315_prepare_seat_child_env_scrubs_psmodulepath():
    out = bw.prepare_seat_child_env(
        {"PSModulePath": PWSH7_SHADOW, "PATH": "C:\\Windows", "KEEP": "z"}
    )
    assert out["PSModulePath"] == winps51.WINPS51_MODULE_PATH
    assert out["KEEP"] == "z"


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows powershell.exe")
def test_fr7315_get_filehash_works_with_helper_env():
    env = winps51.env_for_powershell_exe(
        {**os.environ, "PSModulePath": PWSH7_SHADOW + os.pathsep + winps51.WINPS51_MODULE_PATH}
    )
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-Command Get-FileHash | Select-Object -ExpandProperty Name",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert "Get-FileHash" in (r.stdout or "")


def test_fr7315_read_fuel_passes_winps_env(tmp_path: Path, monkeypatch):
    helper = tmp_path / "tools" / "Get-BobAgentFuel.ps1"
    helper.parent.mkdir(parents=True)
    helper.write_text("# fuel\n", encoding="utf-8")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs.get("env") or {}
        class R:
            stdout = "{}"
        return R()

    monkeypatch.setattr(bw, "CREATE_NO_WINDOW", 0, raising=False)
    bw.read_fuel(tmp_path, run=fake_run)
    assert seen["env"].get("PSModulePath") == winps51.WINPS51_MODULE_PATH


def test_fr7315_conftest_and_docs_pin():
    conf = Path(__file__).resolve().parent / "conftest.py"
    text = conf.read_text(encoding="utf-8")
    assert "FR #7315" in text
    assert "apply_winps51_module_path" in text
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "env_for_powershell_exe" in src
    docs = Path(__file__).resolve().parents[1] / "docs" / "bob-worker.md"
    assert "FR #7315" in docs.read_text(encoding="utf-8")
