"""FR #4297: Sync overlays harvest scripts from origin tip when ff blocked.

Dirty install worktrees leave Sync on a stale HEAD; robocopy then composes a
pre-#4288 Invoke-BobiverseHarvest.ps1 that still opens tip lesson PRs under
-ExistingPrUrl. Overlay tip blob into flat scripts\\ and common\\scripts\\.
"""
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
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
DOC = REPO / "common" / "docs" / "post-install.md"
HARVEST_SKILL = REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def _fn_body(text: str, name: str) -> str:
    m = re.search(r"function\s+" + re.escape(name) + r"\b", text)
    assert m, name
    rest = text[m.start() :]
    m2 = re.search(r"\nfunction\s+\w+", rest[1:])
    return rest if not m2 else rest[: m2.start() + 1]


def test_fr4297_common_defines_harvest_overlay():
    body = _fn_body(COMMON.read_text(encoding="utf-8"), "Sync-BobiverseHarvestScriptsFromOrigin")
    assert "Invoke-BobiverseHarvest.ps1" in body
    assert "Report-BobiverseIntakeIssue.ps1" in body
    assert "FR #4297" in body or "FR #4288" in body
    assert "ExistingPrUrl" in body
    assert "Sync-BobiverseScriptTipFromOrigin" in body


def test_fr4297_sync_calls_harvest_overlay_after_scripts_robocopy():
    t = SYNC.read_text(encoding="utf-8")
    assert "Sync-BobiverseHarvestScriptsFromOrigin" in t
    robocopy_idx = t.find("foreach ($d in @('scripts', 'third_party'))")
    call_idx = t.find("Sync-BobiverseHarvestScriptsFromOrigin")
    assert robocopy_idx >= 0 and call_idx > robocopy_idx
    # After updater overlay (same tip-overlay family as FR #2581)
    upd_idx = t.find("Sync-BobiverseUpdaterFromOrigin")
    assert upd_idx >= 0 and call_idx > upd_idx


def test_fr4297_compose_only_still_reaches_harvest_overlay():
    """ComposeOnly skips fetch/ff but must not exit before harvest tip overlay."""
    t = SYNC.read_text(encoding="utf-8")
    compose = t.find("if ($ComposeOnly)")
    call = t.find("Sync-BobiverseHarvestScriptsFromOrigin")
    assert compose >= 0 and call > compose
    robocopy = t.find("foreach ($d in @('scripts', 'third_party'))")
    between = t[robocopy:call]
    assert "exit " not in between.lower() or "exitcode" in between.lower()
    dry = t.find("if ($DryRun)")
    assert dry >= 0 and dry < call


def test_fr4297_post_install_docs_mention_harvest_overlay():
    text = DOC.read_text(encoding="utf-8")
    assert "FR #4297" in text
    assert "Sync-BobiverseHarvestScriptsFromOrigin" in text
    assert "Invoke-BobiverseHarvest.ps1" in text


def test_fr4297_harvest_skill_prefers_common_scripts():
    text = HARVEST_SKILL.read_text(encoding="utf-8")
    assert "common" in text.lower() and "scripts" in text.lower()
    assert "FR #4297" in text or "tip overlay" in text.lower() or "ComposeOnly" in text


def test_fr4297_overlay_writes_tip_when_local_harvest_stale(tmp_path: Path):
    """Local common/scripts lacks FR #4288; origin/main tip has it — overlay restores tip."""
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
    write(seed / "bob/scripts/b1.ps1", "# b\n")
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
    write(install / "bob/scripts/bob_worker.py", "# dirty hotpatch\n")
    write(install / "scripts/Invoke-BobiverseHarvest.ps1", "# stale flat harvest\n")
    write(install / "common/scripts/Invoke-BobiverseHarvest.ps1", "# stale common harvest\n")
    write(install / "scripts/Report-BobiverseIntakeIssue.ps1", "# stale flat intake\n")
    write(install / "common/scripts/Report-BobiverseIntakeIssue.ps1", "# stale common intake\n")

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
    assert "OK:" in (r.stdout or "")
    flat_h = (install / "scripts/Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8")
    common_h = (install / "common/scripts/Invoke-BobiverseHarvest.ps1").read_text(
        encoding="utf-8"
    )
    assert "FR #4288" in flat_h
    assert "ExistingPrUrl" in flat_h
    assert "FR #4288" in common_h
    flat_i = (install / "scripts/Report-BobiverseIntakeIssue.ps1").read_text(encoding="utf-8")
    assert "/bob/v1/intake" in flat_i or "Report-BobiverseIntakeIssue" in flat_i
    assert "stale" not in flat_h.lower() or "tip" in flat_h.lower()
