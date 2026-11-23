"""FR #8863: diverged installs overlay allowlisted runtime scripts without ff.

sync-skip-diverged (FR #7301) stays. Sync-BobiverseTipFile copies
bob/scripts/bob_worker.py and skill_dag_mcp.py from origin tip onto the
install path and flat scripts\\. VERSION and HEAD are left alone.
A frozen bob-worker.exe is not replaced.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("git") or not shutil.which("powershell"),
    reason="windows powershell+git",
)

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")


def test_fr8863_allowlist_and_skip_diverged_call():
    common = COMMON.read_text(encoding="utf-8")
    assert "function Sync-BobiverseTipFile" in common
    assert "function Get-BobiverseTipFileAllowlist" in common
    assert "bob/scripts/bob_worker.py" in common
    assert "bob/scripts/skill_dag_mcp.py" in common
    assert "not allowlisted (FR #8863)" in common
    skip = common.split("sync-skip-diverged FR#7301", 1)[1][:800]
    assert "Sync-BobiverseAllowlistedTipFiles" in skip
    sync = SYNC.read_text(encoding="utf-8")
    assert "FR #8863" in sync
    assert "Sync-BobiverseAllowlistedTipFiles" in sync
    assert "bob-worker.exe" in sync


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )
    if check:
        assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_fr8863_tip_file_overlays_allowlist_keeps_head_and_version(tmp_path: Path):
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    marker = "line\n" * 8
    _write(seed / "common/VERSION", "0.1.25\n")
    _write(seed / "bob/scripts/bob_worker.py", marker + "# stale bob_worker FR #7000\n")
    _write(seed / "bob/scripts/skill_dag_mcp.py", marker + "# stale skill-dag-mcp\n")
    _write(seed / "VERSION", "2.0.0\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "stale")
    bare = tmp_path / "remote.git"
    _git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    tip = tmp_path / "tip"
    _git(tmp_path, "clone", "-q", str(bare), str(tip))
    _write(tip / "bob/scripts/bob_worker.py", marker + "# tip bob_worker FR #7000 FR #8863\n")
    _write(tip / "bob/scripts/skill_dag_mcp.py", marker + "# tip skill-dag-mcp FR #7000\n")
    _git(tip, "add", "-A")
    _git(tip, "commit", "-q", "-m", "tip")
    _git(tip, "push", "-q", "origin", "main")

    install = tmp_path / "install"
    _git(tmp_path, "clone", "-q", str(bare), str(install))
    _git(install, "fetch", "-q", "origin")
    head = _git(install, "rev-parse", "HEAD").stdout.strip()
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0"

    script = tmp_path / "run-tip.ps1"
    script.write_text(
        "\n".join(
            [
                f". '{COMMON}'",
                f"$r = Sync-BobiverseAllowlistedTipFiles -InstallRoot '{install}' -Branch 'main'",
                "if (-not $r.Ok) { Write-Output $r.Reason; exit 1 }",
                "Write-Output $r.Reason",
                f"$bad = Sync-BobiverseTipFile -InstallRoot '{install}' -RelPath 'common/scripts/evil.py'",
                "if ($bad.Ok) { exit 2 }",
                "if ($bad.Reason -notmatch 'not allowlisted') { Write-Output $bad.Reason; exit 3 }",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    p = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out
    assert "FR #8863" in (install / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "tip skill-dag-mcp" in (install / "bob" / "scripts" / "skill_dag_mcp.py").read_text(encoding="utf-8")
    assert "FR #8863" in (install / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "tip skill-dag-mcp" in (install / "scripts" / "skill_dag_mcp.py").read_text(encoding="utf-8")
    assert (install / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0"
    assert _git(install, "rev-parse", "HEAD").stdout.strip() == head
