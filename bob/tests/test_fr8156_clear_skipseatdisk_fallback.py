"""FR #8156: Clear -SkipSeatDisk fallback when install script lacks the switch."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import worker_shipped_scripts as ship


CLEAR = "Clear-BobiverseJobWorktrees.ps1"

_OLD_CLEAR = """\
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$KeepPath = '',
    [double]$MinFreeGB = 2,
    [int]$MaxExtraJobTrees = 0,
    [switch]$Force
)
Write-Output ("Removing worktree {0}" -f (Join-Path $RepoRoot 'extra-fr'))
Write-Output 'Done removed=1'
"""

_NEW_CLEAR = """\
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$KeepPath = '',
    [int]$MaxExtraJobTrees = 0,
    [switch]$SkipSeatDisk,
    [switch]$Force
)
if ($SkipSeatDisk) { Write-Output 'skip-seat-disk=1' }
Write-Output ("Removing worktree {0}" -f (Join-Path $RepoRoot 'extra-fr'))
Write-Output 'Done removed=1'
"""


def test_ps1_declared_params_reads_skipseatdisk(tmp_path: Path):
    old = tmp_path / "old.ps1"
    old.write_text(_OLD_CLEAR, encoding="utf-8")
    new = tmp_path / "new.ps1"
    new.write_text(_NEW_CLEAR, encoding="utf-8")
    assert "SkipSeatDisk" not in bw.ps1_declared_params(old)
    assert "SkipSeatDisk" in bw.ps1_declared_params(new)
    assert "RepoRoot" in bw.ps1_declared_params(old)


def test_filter_omits_unsupported_skipseatdisk(tmp_path: Path):
    old = tmp_path / CLEAR
    old.write_text(_OLD_CLEAR, encoding="utf-8")
    argv = [
        "powershell",
        "-File",
        str(old),
        "-RepoRoot",
        "R",
        "-KeepPath",
        "K",
        "-SkipSeatDisk",
        "-MaxExtraJobTrees",
        "0",
    ]
    filtered, omitted = bw.filter_ps1_optional_switches(
        old, argv, optional=frozenset({"SkipSeatDisk"})
    )
    assert omitted == ["SkipSeatDisk"]
    assert "-SkipSeatDisk" not in filtered
    assert "-KeepPath" in filtered and "-RepoRoot" in filtered


def test_filter_keeps_skipseatdisk_when_declared(tmp_path: Path):
    new = tmp_path / CLEAR
    new.write_text(_NEW_CLEAR, encoding="utf-8")
    argv = ["powershell", "-File", str(new), "-SkipSeatDisk", "-KeepPath", "K"]
    filtered, omitted = bw.filter_ps1_optional_switches(
        new, argv, optional=frozenset({"SkipSeatDisk"})
    )
    assert omitted == []
    assert "-SkipSeatDisk" in filtered


def test_resolve_fleet_ps1_prefers_common_over_flat(tmp_path: Path, monkeypatch):
    install = tmp_path / "install"
    flat = install / "scripts"
    common = install / "common" / "scripts"
    flat.mkdir(parents=True)
    common.mkdir(parents=True)
    (flat / CLEAR).write_text(_OLD_CLEAR, encoding="utf-8")
    (common / CLEAR).write_text(_NEW_CLEAR, encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.delenv("BOB_SCRIPTS_DIR", raising=False)
    got = bw.resolve_fleet_ps1(CLEAR, install_root=install, source_file=tmp_path / "x.py")
    assert got is not None
    assert got.resolve() == (common / CLEAR).resolve()


def test_resolve_fleet_ps1_prefers_ship_dir(tmp_path: Path, monkeypatch):
    ship_dir = tmp_path / "worker" / "scripts"
    ship_dir.mkdir(parents=True)
    (ship_dir / CLEAR).write_text(_NEW_CLEAR, encoding="utf-8")
    install = tmp_path / "install"
    (install / "scripts").mkdir(parents=True)
    (install / "scripts" / CLEAR).write_text(_OLD_CLEAR, encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setenv("BOB_SCRIPTS_DIR", str(ship_dir))
    got = bw.resolve_fleet_ps1(CLEAR, install_root=install)
    assert got is not None
    assert got.resolve() == (ship_dir / CLEAR).resolve()


def test_cleanup_falls_back_without_skipseatdisk(tmp_path: Path, monkeypatch):
    """Older Clear without -SkipSeatDisk still runs and cleans."""
    job = tmp_path / "job"
    job.mkdir()
    (job / ".git").mkdir()
    install = tmp_path / "install"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    clear = scripts / CLEAR
    clear.write_text(_OLD_CLEAR, encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setenv("BOB_SCRIPTS_DIR", str(scripts))
    # Reset once-per-seat warn set between tests.
    bw._FLEET_PS1_MISMATCH_WARNED.clear()

    class _R:
        def __init__(self, code=0, out="", err=""):
            self.returncode = code
            self.stdout = out
            self.stderr = err

    seen: list[list[str]] = []
    logs: list[str] = []

    def run(argv, **kwargs):
        seen.append(list(argv))
        head = str(argv[0]).lower() if argv else ""
        if "powershell" in head:
            assert "-SkipSeatDisk" not in argv
            return _R(0, "Removing worktree X\nDone removed=1\n")
        if "rev-parse" in argv:
            return _R(0, str(job / ".git") + "\n")
        return _R(0, "")

    out = bw.opencode_cleanup_extra_worktrees(job, temp_root=tmp_path, run=run, log_fn=logs.append)
    assert any(CLEAR in " ".join(a) for a in seen)
    assert any("-KeepPath" in a for a in seen)
    assert all("-SkipSeatDisk" not in a for a in seen if any("powershell" in str(x).lower() for x in a))
    assert out
    assert any("result=ok" in ln for ln in logs)
    assert any("param-mismatch" in ln or "SkipSeatDisk" in ln for ln in logs)
    # Second call: mismatch warn once (no second skipped:param-mismatch from warn helper).
    logs2: list[str] = []
    bw.opencode_cleanup_extra_worktrees(job, temp_root=tmp_path, run=run, log_fn=logs2.append)
    assert not any("result=skipped:param-mismatch" in ln for ln in logs2)


def test_cleanup_keeps_skipseatdisk_on_new_script(tmp_path: Path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    (job / ".git").mkdir()
    install = tmp_path / "install"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / CLEAR).write_text(_NEW_CLEAR, encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setenv("BOB_SCRIPTS_DIR", str(scripts))
    bw._FLEET_PS1_MISMATCH_WARNED.clear()

    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    seen: list[list[str]] = []

    def run(argv, **kwargs):
        seen.append(list(argv))
        if "powershell" in str(argv[0]).lower():
            assert "-SkipSeatDisk" in argv
            return _R(0, "skip-seat-disk=1\nRemoving worktree X\n")
        if "rev-parse" in argv:
            return _R(0, str(job / ".git") + "\n")
        return _R(0, "")

    bw.opencode_cleanup_extra_worktrees(job, temp_root=tmp_path, run=run)
    assert any("-SkipSeatDisk" in a for a in seen)


def test_cleanup_retries_on_named_parameter_not_found(tmp_path: Path, monkeypatch):
    """Parser miss still recovers: first call fails, retry without -SkipSeatDisk."""
    job = tmp_path / "job"
    job.mkdir()
    (job / ".git").mkdir()
    install = tmp_path / "install"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    # Lie: declare SkipSeatDisk so filter keeps it, then PS rejects it.
    (scripts / CLEAR).write_text(_NEW_CLEAR, encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setenv("BOB_SCRIPTS_DIR", str(scripts))
    bw._FLEET_PS1_MISMATCH_WARNED.clear()

    class _R:
        def __init__(self, code=0, out="", err=""):
            self.returncode = code
            self.stdout = out
            self.stderr = err

    calls = {"n": 0}

    def run(argv, **kwargs):
        if "rev-parse" in argv:
            return _R(0, str(job / ".git") + "\n")
        if "powershell" in str(argv[0]).lower():
            calls["n"] += 1
            if calls["n"] == 1 and "-SkipSeatDisk" in argv:
                return _R(
                    1,
                    "",
                    "Clear-BobiverseJobWorktrees.ps1 : A parameter cannot be found that matches "
                    "parameter name 'SkipSeatDisk'.\nFullyQualifiedErrorId : NamedParameterNotFound\n",
                )
            assert "-SkipSeatDisk" not in argv
            return _R(0, "Removing worktree Y\nDone removed=1\n")
        return _R(0, "")

    logs: list[str] = []
    out = bw.opencode_cleanup_extra_worktrees(job, temp_root=tmp_path, run=run, log_fn=logs.append)
    assert calls["n"] == 2
    assert out
    assert any("result=ok" in ln for ln in logs)


def test_worker_shipped_scripts_lists_clear_ps1():
    names = ship.shipped_script_names(
        Path(__file__).resolve().parents[1] / "scripts" / "bob_worker.py",
        Path(__file__).resolve().parents[1] / "scripts",
    )
    assert CLEAR in names
    assert "Bobiverse-Common.ps1" in names
    assert CLEAR in ship.fleet_ps1_script_names()


def test_install_bob_probes_skipseatdisk_and_syncs():
    text = (
        Path(__file__).resolve().parents[1] / "scripts" / "Install-Bob.ps1"
    ).read_text(encoding="utf-8-sig")
    assert "FR #8156" in text
    assert "synced scripts\\Clear-BobiverseJobWorktrees.ps1 from common" in text or (
        "synced scripts" in text and "Clear-BobiverseJobWorktrees" in text
    )
    assert "$SkipSeatDisk" in text
    assert "Get-FileHash" in text
