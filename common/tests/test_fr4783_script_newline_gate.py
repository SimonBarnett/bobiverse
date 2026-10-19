"""FR #4783: refuse zero-lf .ps1 publish; Sync tip overlay must not strip newlines.

Root cause class: WinPS `$x = git show ...` yields String[] and WriteAllText($x)
joins with spaces (lf=0). Safe path: RedirectStandardOutput then WriteAllBytes,
or Sync-BobiverseScriptTipFromOrigin / Sync-BobiverseHarvestScriptsFromOrigin.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("git"),
    reason="windows + git",
)

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
README = REPO / "README.md"


def _fn_body(text: str, name: str) -> str:
    m = re.search(r"function\s+" + re.escape(name) + r"\b", text)
    assert m, name
    rest = text[m.start() :]
    m2 = re.search(r"\nfunction\s+\w+", rest[1:])
    return rest if not m2 else rest[: m2.start() + 1]


def test_fr4783_common_defines_newline_assert_and_refuse():
    text = COMMON.read_text(encoding="utf-8")
    assert "FR #4783" in text
    assert "Test-BobiverseScriptNewlines" in text or "Assert-BobiverseScriptsHaveNewlines" in text
    tip = _fn_body(text, "Sync-BobiverseScriptTipFromOrigin")
    assert "lf=0" in tip or "lf -eq 0" in tip or "NewlineCount" in tip or "zero-lf" in tip.lower() or "lf_count" in tip.lower() or "[byte]10" in tip
    # must refuse publishing tip with no LF
    assert "refuse" in tip.lower() or "Ok = $false" in tip or "return [pscustomobject]@{ Ok = $false" in tip


def test_fr4783_sync_calls_newline_assert_after_compose():
    t = SYNC.read_text(encoding="utf-8")
    assert "Assert-BobiverseScriptsHaveNewlines" in t or "Test-BobiverseScriptNewlines" in t
    assert "FR #4783" in t
    # after tip overlays
    tip_idx = t.find("Sync-BobiverseHarvestScriptsFromOrigin")
    assert_idx = max(t.find("Assert-BobiverseScriptsHaveNewlines"), t.find("Test-BobiverseScriptNewlines"))
    assert tip_idx >= 0 and assert_idx > tip_idx


def test_fr4783_readme_hotpatch_uses_safe_harvest_overlay():
    t = README.read_text(encoding="utf-8")
    assert "Sync-BobiverseHarvestScriptsFromOrigin" in t
    # broken space-join WriteAllText of git-show capture must not remain as the hotpatch recipe
    bad = re.search(
        r"WriteAllText\([\s\S]{0,200}?git\s+-C[^\n]*show[^\n]*Invoke-BobiverseHarvest",
        t,
        re.I,
    )
    assert bad is None, "README still shows WriteAllText of git-show capture"
    # variable capture of git show into WriteAllText is the lf=0 footgun
    assert "$blob = git" not in t or "RedirectStandardOutput" in t or "Sync-BobiverseHarvestScriptsFromOrigin" in t


def test_fr4783_assert_fails_zero_lf_ps1(tmp_path: Path):
    common_ps1 = COMMON.as_posix()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    # collapsed one-line script (lf=0)
    flat = b"#Requires -Version 5.1 <# .SYNOPSIS  Harvest step... #> [CmdletBinding()] param() Write-Host hi"
    (scripts / "Invoke-BobiverseHarvest.ps1").write_bytes(flat)
    assert flat.count(b"\n") == 0
    install_ps = str(tmp_path).replace("'", "''")
    ps = f"""
    . '{common_ps1}'
    $r = Assert-BobiverseScriptsHaveNewlines -InstallRoot '{install_ps}'
    if ($r.Ok) {{ Write-Output 'UNEXPECTED_OK'; exit 2 }}
    Write-Output ('FAIL_OK:' + $r.Reason)
    """
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "FAIL_OK:" in (r.stdout or "")
    assert "lf=0" in (r.stdout or "").lower() or "newline" in (r.stdout or "").lower()


def test_fr4783_tip_overlay_refuses_zero_lf_blob(tmp_path: Path):
    """Sync-BobiverseScriptTipFromOrigin must not write a tip blob with lf=0."""
    seed = tmp_path / "seed"
    seed.mkdir()
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]

    def git(cwd, *a, check=True):
        r = subprocess.run(
            ["git", *ident, "-c", "core.autocrlf=false", "-C", str(cwd), *a],
            capture_output=True,
            text=True,
        )
        if check:
            assert r.returncode == 0, (a, r.stdout, r.stderr)
        return r

    def write(p: Path, text: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    git(seed, "init", "-q", "-b", "main")
    write(seed / "common/VERSION", "0.1.99\n")
    # tip blob intentionally collapsed (no newlines) - overlay must refuse
    collapsed = "#Requires -Version 5.1 <# SYNOPSIS #> param() function Invoke-BobiverseHarvest {} Protect-HarvestBodyClosesKeywords"
    (seed / "common/scripts").mkdir(parents=True)
    (seed / "common/scripts/Invoke-BobiverseHarvest.ps1").write_bytes(collapsed.encode("utf-8"))
    assert collapsed.encode("utf-8").count(b"\n") == 0
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "collapsed")

    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    install = tmp_path / "install-bob"
    git(tmp_path, "clone", "-q", str(bare), str(install))
    # healthy local that must not be overwritten by collapsed tip
    good = "#Requires -Version 5.1\nparam()\nWrite-Host good\n"
    write(install / "scripts/Invoke-BobiverseHarvest.ps1", good)
    write(install / "common/scripts/Invoke-BobiverseHarvest.ps1", good)

    common_ps1 = COMMON.as_posix()
    install_ps = str(install).replace("'", "''")
    ps = f"""
    . '{common_ps1}'
    $r = Sync-BobiverseScriptTipFromOrigin -InstallRoot '{install_ps}' -Branch main `
      -RelPath 'common/scripts/Invoke-BobiverseHarvest.ps1' `
      -ContentMustMatch 'Invoke-BobiverseHarvest|Protect-HarvestBodyClosesKeywords'
    if ($r.Ok) {{ Write-Output ('UNEXPECTED_OK:' + $r.Reason); exit 2 }}
    Write-Output ('REFUSED:' + $r.Reason)
    """
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "REFUSED:" in (r.stdout or "")
    # local healthy file must remain
    left = (install / "scripts/Invoke-BobiverseHarvest.ps1").read_bytes()
    assert left.count(b"\n") >= 2
    assert b"good" in left


def test_fr4783_harvest_overlay_includes_intake_py():
    body = _fn_body(COMMON.read_text(encoding="utf-8"), "Sync-BobiverseHarvestScriptsFromOrigin")
    assert "intake.py" in body
    assert "FR #4783" in body or "FR #4780" in body or "is_lesson_review_meta_loop" in body
