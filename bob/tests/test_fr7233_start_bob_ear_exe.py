"""FR #7233: Start-Bob runs installed bob-ear.exe even when bobreport.py is newer."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from repo_layout import ROOT

START = ROOT / "bob" / "scripts" / "Start-Bob.ps1"
SELECT = ROOT / "bob" / "scripts" / "Select-BobEarLaunch.ps1"
PS = "powershell"


def _ps(script: str, env: dict[str, str] | None = None) -> str:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged,
        check=False,
    )
    if r.returncode != 0:
        raise AssertionError(f"powershell failed rc={r.returncode}\n{r.stdout}\n{r.stderr}")
    return (r.stdout or "").strip()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Start-Bob")
def test_fr7233_older_exe_wins_over_newer_bobreport(tmp_path: Path) -> None:
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    exe = scripts / "bob-ear.exe"
    payload = b"MZ-fr7233-ear\n"
    exe.write_bytes(payload)
    (scripts / "bobreport.py").write_text("# newer than exe by mtime\n", encoding="utf-8")
    (scripts / "irc_agent.py").write_text("# agent\n", encoding="utf-8")
    (install / "VERSION").write_text("0.9.test\n", encoding="utf-8")
    (install / "MANIFEST.json").write_text(
        '{"source_commit":"abcdef1234567890"}\n', encoding="utf-8"
    )
    os.utime(exe, (1_000_000_000, 1_000_000_000))
    os.utime(scripts / "bobreport.py", (2_000_000_000, 2_000_000_000))
    want_sha = hashlib.sha256(payload).hexdigest().upper()
    cmd = (
        f". '{SELECT}'; "
        f"$r = Select-BobEarLaunch -ScriptDir '{scripts}' -InstallRoot '{install}'; "
        "$r.UseExe; $r.Reason; $r.Sha256; $r.SourceCommit; $r.ProductVersion"
    )
    out = _ps(cmd, env={"BOB_EAR_PYTHON": ""})
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    assert lines[0] in ("True", "true")
    assert lines[1] == "installed-exe"
    assert lines[2].upper() == want_sha
    assert lines[3].startswith("abcdef123456")
    assert lines[4] == "0.9.test"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Start-Bob")
def test_fr7233_dev_flag_forces_python(tmp_path: Path) -> None:
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bob-ear.exe").write_bytes(b"MZ")
    (scripts / "irc_agent.py").write_text("# agent\n", encoding="utf-8")
    cmd = (
        f". '{SELECT}'; "
        f"$r = Select-BobEarLaunch -ScriptDir '{scripts}' -InstallRoot '{install}'; "
        "$r.UseExe; $r.Reason"
    )
    out = _ps(cmd, env={"BOB_EAR_PYTHON": "1"})
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    assert lines[0] in ("False", "false")
    assert lines[1] == "BOB_EAR_PYTHON"


def test_fr7233_start_bob_does_not_compare_mtimes() -> None:
    t = START.read_text(encoding="utf-8-sig")
    assert "Select-BobEarLaunch" in t
    assert "FR #7233" in t
    assert "bobreport.py newer than bob-ear.exe" not in t
    assert "LastWriteTimeUtc" not in t
    i_sel = t.find("Select-BobEarLaunch")
    i_launch = t.find("& $earExe")
    if i_launch < 0:
        i_launch = t.find("via=bob-ear.exe")
    assert i_sel > 0 and i_launch > i_sel
    assert "sha256=" in t.lower() or "Sha256" in t


def test_fr6237_start_bob_no_mtime_bridge() -> None:
    """FR #6237 hotpatch is prefer_install_scripts_path, not Start-Bob mtime (FR #7233)."""
    t = START.read_text(encoding="utf-8-sig")
    assert "bobreport.py newer than bob-ear.exe" not in t
