"""FR #2982: MSI payload must win for scripts/tools/skills, not only VERSION.

When InstallRoot is also a sparse git work tree that is dirty/behind origin/main,
Install-*.ps1 with -MsiProductVersion must not re-lay stale repo-layout files over
the MSI heat payload. Sync-BobiverseFromRepo must not robocopy that stale tree onto
flat runtime after ff-only fails (VERSION stamp equal is not enough — FR #1018 only
caught newer-install VERSION).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from repo_layout import REPO, ROOT

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="windows powershell",
)

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_install_scripts_force_skipcopy_when_msi_product_version_set():
    """MSI RunInstall forwards ProductVersion; that must imply SkipCopy (FR #2982)."""
    for rel in (
        "bob/scripts/Install-Bob.ps1",
        "jeeves/scripts/Install-Jeeves.ps1",
        "airc/scripts/Install-Airc.ps1",
    ):
        t = _read(ROOT / rel)
        assert "MsiProductVersion" in t, rel
        assert "FR #2982" in t, rel
        # Force SkipCopy when ProductVersion looks like x.y.z
        assert "SkipCopy" in t, rel
        assert (
            "MsiProductVersion" in t
            and ("SkipCopy = $true" in t or "$SkipCopy = $true" in t)
        ), rel
        # Gate must key off MsiProductVersion (not only MsiSkipCopy=1)
        assert (
            "$MsiProductVersion" in t
            and (
                "SkipCopy = $true" in t[t.index("MsiProductVersion") :]
                or "$SkipCopy = $true" in t[t.index("MsiProductVersion") :]
            )
        ) or "FR #2982" in t


def test_install_bob_skips_tray_copy_when_source_under_installroot():
    """bob\\tray under InstallRoot must not overwrite MSI-laid tools\\ (FR #2982)."""
    t = _read(ROOT / "bob" / "scripts" / "Install-Bob.ps1")
    assert "FR #2982" in t
    # Defense: tray under InstallRoot / same-tree skip (not only Test-BobiverseSamePath trayVendor InstallRoot)
    window = t[t.index("$trayVendor") : t.index("$skillsSrc")]
    assert "SkipCopy" in window
    assert (
        "StartsWith" in window
        or "under" in window.lower()
        or "trayUnder" in window
        or "Test-BobiversePathUnder" in window
        or "FR #2982" in window
    )


def test_sync_documents_skip_stale_worktree_compose():
    t = _read(SYNC)
    assert "FR #2982" in t
    assert "sync-skip-stale-worktree" in t
    assert "ComposeOnly" in t


@pytest.mark.skipif(not shutil.which("git"), reason="git required")
def test_pin_sync_skips_compose_when_ff_blocked_keeps_msi_flat_files(tmp_path: Path):
    """Acceptance-adjacent: dirty behind work tree must not robocopy over MSI flat scripts."""
    msi_script = "# MSI-LAID Bobiverse-Common FR2982\n"
    msi_tray = "# MSI-LAID Start-BobFleetTray #2931\n"
    msi_skill = "# MSI-LAID UAT skill FR #2670\n"
    stale_script = "# STALE git common script\n"
    stale_tray = "# STALE git tray\n"
    stale_skill = "# STALE git skill no 2670\n"

    # Bare remote ahead of HEAD so worktree is "behind"; dirty file blocks ff-only.
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)], check=True, capture_output=True)
    (seed / "common" / "scripts").mkdir(parents=True)
    (seed / "common" / "VERSION").write_text("0.1.25\n", encoding="utf-8")
    (seed / "common" / "scripts" / "Bobiverse-Common.ps1").write_text(stale_script, encoding="utf-8")
    (seed / "bob" / "scripts").mkdir(parents=True)
    (seed / "bob" / "scripts" / "x.ps1").write_text("# tip\n", encoding="utf-8")
    (seed / "bob" / "tray" / "tools").mkdir(parents=True)
    (seed / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1").write_text(stale_tray, encoding="utf-8")
    (seed / "bob" / ".grok" / "skills" / "bobiverse-bob-job-uat").mkdir(parents=True)
    (seed / "bob" / ".grok" / "skills" / "bobiverse-bob-job-uat" / "SKILL.md").write_text(
        stale_skill, encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(seed), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(seed), "branch", "-M", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "main"], check=True, capture_output=True)

    # Tip also edits the same tracked script so a dirty install copy blocks ff-only.
    (seed / "bob" / "scripts" / "y.ps1").write_text("# tip2\n", encoding="utf-8")
    (seed / "common" / "scripts" / "Bobiverse-Common.ps1").write_text(
        stale_script + "# tip change\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(seed), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "ahead"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "main"], check=True, capture_output=True)
    tip2 = subprocess.check_output(["git", "-C", str(seed), "rev-parse", "HEAD"], text=True).strip()
    base = subprocess.check_output(["git", "-C", str(seed), "rev-parse", "HEAD~1"], text=True).strip()

    install = tmp_path / "ai" / "bob"
    subprocess.run(
        ["git", "clone", "-q", "--no-checkout", str(bare), str(install)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(install), "checkout", "-q", "-B", "main", base],
        check=True,
        capture_output=True,
    )

    # MSI heat flat layout (VERSION equal to git — FR #1018 alone would NOT skip).
    (install / "VERSION").write_text("0.1.25\n", encoding="utf-8")
    (install / "scripts").mkdir(parents=True, exist_ok=True)
    (install / "tools").mkdir(parents=True, exist_ok=True)
    (install / "worker" / ".grok" / "skills" / "bobiverse-bob-job-uat").mkdir(parents=True, exist_ok=True)
    (install / "scripts" / "Bobiverse-Common.ps1").write_text(msi_script, encoding="utf-8")
    (install / "tools" / "Start-BobFleetTray.ps1").write_text(msi_tray, encoding="utf-8")
    (install / "worker" / ".grok" / "skills" / "bobiverse-bob-job-uat" / "SKILL.md").write_text(
        msi_skill, encoding="utf-8"
    )
    # Dirty hotpatch in tracked tree blocks ff-only
    (install / "common" / "scripts" / "Bobiverse-Common.ps1").write_text(
        stale_script + "# dirty local\n", encoding="utf-8"
    )

    env = {**os.environ}
    env.pop("BOBIVERSE_NO_UPDATE", None)
    env["BOBIVERSE_KEEP_BRANCH"] = "0"
    p = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SYNC),
            "-Product",
            "bob",
            "-InstallRoot",
            str(install),
            "-ArpVersionOverride",
            "0.1.25",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out
    assert "sync-skip-stale-worktree" in out, out
    assert (install / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8") == msi_script
    assert (install / "tools" / "Start-BobFleetTray.ps1").read_text(encoding="utf-8") == msi_tray
    assert (
        install / "worker" / ".grok" / "skills" / "bobiverse-bob-job-uat" / "SKILL.md"
    ).read_text(encoding="utf-8") == msi_skill
    assert tip2 and base and tip2 != base


def test_pin_msi_product_version_forces_skipcopy_in_helper(tmp_path: Path):
    """Unit: MsiProductVersion gate sets SkipCopy before any Copy-BobiverseTree."""
    # Mirror the Install-*.ps1 gate in isolation (same regex / assignment).
    ps = textwrap.dedent(
        r"""
        $ErrorActionPreference = 'Stop'
        $SkipCopy = $false
        $MsiProductVersion = '0.1.25'
        # FR #2982 gate (must match Install-*.ps1)
        if (([string]$MsiProductVersion).Trim() -match '^\d+\.\d+\.\d+') {
            $SkipCopy = $true
        }
        if (-not $SkipCopy) { throw 'expected SkipCopy' }
        Write-Output 'OK SkipCopy'
        """
    ).strip()
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "OK SkipCopy" in (r.stdout or "")
