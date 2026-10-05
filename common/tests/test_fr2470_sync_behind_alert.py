"""FR #2470: Sync-BobiverseWorkTree ALERTs when HEAD stays behind origin/main; docs cover harvest tip hotpatch."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
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


def test_fr2470_sync_worktree_counts_behind_and_alerts():
    text = COMMON.read_text(encoding="utf-8")
    body = _fn_body(text, "Sync-BobiverseWorkTree")
    helper = _fn_body(text, "Get-BobiverseWorkTreeBehindCount")
    assert "Get-BobiverseWorkTreeBehindCount" in body
    assert "sync-behind" in body
    assert "FR #2470" in body or "FR#2470" in body or "#2470" in body
    assert "rev-list" in helper
    assert "--count" in helper


def test_fr2470_from_repo_surfaces_behind_stale():
    t = SYNC.read_text(encoding="utf-8")
    assert "ALERT" in t
    assert "behind" in t.lower()


def test_fr2470_readme_documents_harvest_tip_hotpatch():
    t = README.read_text(encoding="utf-8")
    assert "Invoke-BobiverseHarvest" in t or "harvest" in t.lower()
    assert "ComposeOnly" in t or "hotpatch" in t.lower()
    assert "sync-behind" in t or "behind origin" in t.lower()
    # Hostile MRB #2474: do not teach the Set-Content pipeline (WinPS utf8 = BOM).
    i = t.lower().find("hotpatch")
    hot = t[i : i + 1100] if i >= 0 else ""
    assert "WriteAllText" in hot or "UTF8Encoding" in hot
    assert "Set-Content -LiteralPath" not in hot
    assert "|\n  Set-Content" not in hot and "|\r\n  Set-Content" not in hot


def test_fr2470_ff_blocked_alerts_with_behind_count():
    tmp = Path(os.environ.get("TEMP", ".")) / ("fr2470-%s-%s" % (os.getpid(), int(time.time())))
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    seed = tmp / "seed"
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

    def write(p, text):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    git(seed, "init", "-q", "-b", "main")
    write(seed / "common/VERSION", "1.0.0\n")
    write(seed / "common/scripts/c1.ps1", "# c\n")
    write(seed / "common/scripts/Invoke-BobiverseHarvest.ps1", "# harvest v1\n")
    write(seed / "bob/scripts/b1.ps1", "# b\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "i")
    bare = tmp / "remote.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(seed), str(bare)],
        check=True,
        capture_output=True,
    )
    git(seed, "remote", "add", "origin", str(bare))
    ai = tmp / "ai"
    ai.mkdir()
    r = ai / "bob"
    r.mkdir()
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")

    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "BOBIVERSE_REPO",
            "BOBIVERSE_NO_UPDATE",
            "BOBIVERSE_KEEP_BRANCH",
            "BOBIVERSE_FETCH_TIMEOUT_SEC",
            "BOBIVERSE_FETCH_RETRIES",
            "BOB_AI_ROOT",
            "BOBIVERSE_REMOTE",
        )
    }
    env["BOB_AI_ROOT"] = str(ai)
    env["BOBIVERSE_REMOTE"] = str(bare)

    def sync():
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SYNC),
                "-Product",
                "bob",
                "-InstallRoot",
                str(r),
            ],
            capture_output=True,
            text=True,
            timeout=240,
            env=env,
        )

    out1 = sync()
    assert out1.returncode == 0, out1.stdout + out1.stderr
    # Block ff with a local edit, then push tip ahead so behind count is > 0.
    write(r / "bob/scripts/b1.ps1", "# LOCAL\n")
    write(seed / "bob/scripts/b1.ps1", "# UP\n")
    write(seed / "common/scripts/Invoke-BobiverseHarvest.ps1", "# harvest v2 tip\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "up")
    git(seed, "push", "-q", "origin", "main")
    out2 = sync()
    text = out2.stdout + out2.stderr
    assert out2.returncode == 0, text
    assert "ALERT" in text, text
    assert "ff-only not possible" in text or "sync-ff-failed" in text, text
    assert re.search(r"behind origin/\w+ by \d+", text, re.I), text
    shutil.rmtree(tmp, ignore_errors=True)
