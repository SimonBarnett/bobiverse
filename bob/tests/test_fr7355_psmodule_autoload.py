"""FR #7355: PSModuleAutoLoadingPreference=None must not hide Get-FileHash."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import winps51
import bob.scripts.bob_worker as bw

PS = shutil.which("powershell.exe")


def test_fr7355_helper_clears_autoload_none():
    poisoned = {
        "PSModulePath": winps51.WINPS51_MODULE_PATH,
        "PSModuleAutoLoadingPreference": "None",
        "KEEP": "1",
    }
    got = winps51.env_for_powershell_exe(poisoned)
    assert got.get("PSModuleAutoLoadingPreference", "").lower() != "none"
    assert got.get("PSModuleAutoLoadingPreference") == "All"
    assert got["KEEP"] == "1"


def test_fr7355_prepare_seat_child_env_scrubs_autoload_none():
    out = bw.prepare_seat_child_env(
        {
            "PSModuleAutoLoadingPreference": "None",
            "PATH": "C:\\Windows",
            "KEEP": "z",
        }
    )
    assert out.get("PSModuleAutoLoadingPreference") == "All"
    assert out["KEEP"] == "z"


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows powershell.exe")
def test_fr7355_get_filehash_works_when_parent_autoload_none():
    env = winps51.env_for_powershell_exe({**os.environ, "PSModuleAutoLoadingPreference": "None"})
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


def test_fr7355_docs_pin():
    docs = Path(__file__).resolve().parents[1] / "docs" / "bob-worker.md"
    text = docs.read_text(encoding="utf-8")
    assert "FR #7355" in text
    helper = Path(winps51.__file__).read_text(encoding="utf-8")
    assert "PSModuleAutoLoadingPreference" in helper
    assert "FR #7355" in helper
