"""FR #5480: harvest tip overlay skips a missing origin intake.py (does not fail Sync)."""
from __future__ import annotations

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


def _fn_body(text: str, name: str) -> str:
    m = re.search(r"function\s+" + re.escape(name) + r"\b", text)
    assert m, name
    rest = text[m.start() :]
    m2 = re.search(r"\nfunction\s+\w+", rest[1:])
    return rest if not m2 else rest[: m2.start() + 1]


def test_fr5480_pins_intake_overlay_optional():
    body = _fn_body(COMMON.read_text(encoding="utf-8"), "Sync-BobiverseHarvestScriptsFromOrigin")
    assert "intake.py" in body
    assert "Optional" in body or "skip missing" in body.lower()
    assert "FR #5480" in body
    src = COMMON.read_text(encoding="utf-8")
    tip = _fn_body(src, "Sync-BobiverseScriptTipFromOrigin")
    assert "[switch]$Optional" in tip or "Optional" in tip
    assert not COMMON.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr5480_overlay_ok_when_origin_lacks_intake_py(tmp_path: Path):
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
    write(seed / "common/VERSION", "0.1.24\n")
    write(
        seed / "common/scripts/Invoke-BobiverseHarvest.ps1",
        "# stale harvest\n# no ExistingPrUrl skip\n",
    )
    write(
        seed / "common/scripts/Report-BobiverseIntakeIssue.ps1",
        "# stale intake\n# Report-BobiverseIntakeIssue stub\n",
    )
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "stale")

    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))

    tip = tmp_path / "tip"
    git(tmp_path, "clone", "-q", str(bare), str(tip))
    write(
        tip / "common/scripts/Invoke-BobiverseHarvest.ps1",
        "# tip harvest\n# FR #4288: -ExistingPrUrl fail-closes tip filing\n"
        "param([string]$ExistingPrUrl = '')\n",
    )
    write(
        tip / "common/scripts/Report-BobiverseIntakeIssue.ps1",
        "# tip intake\n# Report-BobiverseIntakeIssue posts /bob/v1/intake\n",
    )
    git(tip, "add", "-A")
    git(tip, "commit", "-q", "-m", "tip-4288")
    git(tip, "push", "-q", "origin", "main")

    install = tmp_path / "install-bob"
    git(tmp_path, "clone", "-q", str(bare), str(install))
    git(install, "remote", "set-url", "origin", str(bare))
    git(install, "fetch", "-q", "origin")
    write(install / "scripts/Invoke-BobiverseHarvest.ps1", "# stale flat harvest\n")
    write(install / "common/scripts/Invoke-BobiverseHarvest.ps1", "# stale common harvest\n")

    common_ps1 = COMMON.as_posix()
    install_ps = str(install).replace("'", "''")
    ps = f"""
    . '{common_ps1}'
    $r = Sync-BobiverseHarvestScriptsFromOrigin -InstallRoot '{install_ps}' -Branch main
    if (-not $r.Ok) {{ Write-Output ("FAIL:" + $r.Reason); exit 2 }}
    Write-Output ("OK:" + $r.Reason)
    """
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    out = r.stdout or ""
    assert "OK:" in out
    assert "does not exist" not in out.lower() or "skip" in out.lower()
    flat_h = (install / "scripts/Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8")
    assert "FR #4288" in flat_h
    assert not (install / "scripts/intake.py").exists()
