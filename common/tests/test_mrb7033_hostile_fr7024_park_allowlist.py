"""MRB #7033 hostile pin: FR #7024 park allowlist (VISION 020 / #1074)."""
from __future__ import annotations

import json
import os
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
IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def _ps_hotpatch(rel: str) -> bool:
    script = (
        f". '{COMMON}'; "
        f"if (Test-BobiverseSyncParkHotpatchPath -Rel '{rel}') {{ 'YES' }} else {{ 'NO' }}"
    )
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    out = (r.stdout or "").strip().splitlines()[-1].strip()
    return out == "YES"


def test_mrb7033_hotpatch_allowlist_matrix():
    assert _ps_hotpatch("bob/tray/tools/BobTrayRecycleSeat.ps1") is True
    assert _ps_hotpatch("common/scripts/gitclaim.py") is True
    assert _ps_hotpatch("common/scripts/recycleseat.py") is True
    assert _ps_hotpatch("bob/scripts/b1.ps1") is False
    assert _ps_hotpatch("bob/VISION.md") is False
    assert _ps_hotpatch("common/scripts/Bobiverse-Common.ps1") is False


def test_mrb7033_common_pins_skip_not_hotpatch_contiguous():
    raw = COMMON.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "function Test-BobiverseSyncParkHotpatchPath" in text
    assert "skip-not-hotpatch" in text
    assert "FR#7024" in text


def git(cwd, *a, check=True):
    r = subprocess.run(
        ["git", *IDENT, "-c", "core.autocrlf=false", "-C", str(cwd), *a],
        capture_output=True,
        text=True,
    )
    if check:
        assert r.returncode == 0, (a, r.stdout, r.stderr)
    return r


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture()
def world(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    write(seed / "common/VERSION", "9.9.9\n")
    write(seed / "common/scripts/c1.ps1", "# common 1\n")
    write(seed / "bob/scripts/b1.ps1", "# bob 1\n")
    write(seed / "bob/tray/tools/Watch-BobTray.ps1", "# tray v1\n")
    write(seed / "bob/tray/src/BobBridge.psm1", "# bridge v1\n")
    write(seed / "bob/tray/src/VERSION", "0.0.0-tray\n")
    write(seed / "bob/tray/assets/icon.txt", "icon\n")
    write(
        seed / "bob/tray/config/bobiverse.json",
        json.dumps(
            {
                "channel": "#bobiverse",
                "host": "irc.example.test",
                "port": 6697,
                "reportUrl": "https://bob.example.test/bob/v1/report",
                "reportPort": 7700,
                "shortids": {},
                "nicks": {},
                "legacyAliases": {},
                "chairNick": "Jeeves",
            },
            indent=2,
        )
        + "\n",
    )
    write(seed / "jeeves/scripts/j1.ps1", "# j\n")
    write(seed / "airc/scripts/a1.ps1", "# a\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "init")
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(seed), str(bare)],
        check=True,
        capture_output=True,
    )
    git(seed, "remote", "add", "origin", str(bare))

    class W:
        pass

    w = W()
    w.tmp, w.seed, w.bare = tmp_path, seed, bare
    w.ai = tmp_path / "ai"
    w.ai.mkdir()

    def root(product="bob"):
        r = w.ai / product
        r.mkdir(exist_ok=True)
        return r

    def upstream(path, text, msg="up"):
        write(seed / path, text)
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", msg)
        git(seed, "push", "-q", "origin", "main")

    def sync(product="bob"):
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in (
                "BOBIVERSE_REPO",
                "BOBIVERSE_NO_UPDATE",
                "BOBIVERSE_KEEP_BRANCH",
                "BOB_AI_ROOT",
                "BOBIVERSE_REMOTE",
                "BOBIVERSE_SYNC_FROM_REPO",
                "BOB_SYNC_STATUS_DIR",
                "BOB_SYNC_STALL_DIR",
            )
        }
        env["BOB_AI_ROOT"] = str(w.ai)
        env["BOBIVERSE_REMOTE"] = str(bare)
        env["BOBIVERSE_SYNC_FROM_REPO"] = "1"
        env["BOB_SYNC_STATUS_DIR"] = str(tmp_path / "sync-status")
        env["BOB_SYNC_STALL_DIR"] = str(tmp_path / "sync-stall")
        env["BOB_SYNC_STALL_DRY"] = "1"
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SYNC),
                "-Product",
                product,
                "-InstallRoot",
                str(root(product)),
                "-ArpVersionOverride",
                "none",
            ],
            capture_output=True,
            text=True,
            timeout=240,
            env=env,
        )
        r.text = r.stdout + r.stderr
        return r

    w.root, w.upstream, w.sync = root, upstream, sync
    return w


def test_mrb7033_non_hotpatch_dirty_blocks_ff_and_keeps_edit(world):
    """Overlapping dirty bob/scripts/b1.ps1 must not be park-wiped (VISION 020)."""
    r = world.root("bob")
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")
    assert world.sync().returncode == 0
    write(r / "bob/scripts/b1.ps1", "# LOCAL EDIT MUST SURVIVE\n")
    world.upstream("bob/scripts/b1.ps1", "# upstream change\n", msg="up overlap")
    out = world.sync()
    text = out.text
    assert out.returncode == 0, text
    assert (r / "bob/scripts/b1.ps1").read_text(encoding="utf-8") == "# LOCAL EDIT MUST SURVIVE\n"
    assert "ff-only not possible" in text or "sync-ff-failed" in text, text
    assert "skip-not-hotpatch" in text, text
    parks = list((r / ".bobiverse-parked").rglob("b1.ps1")) if (r / ".bobiverse-parked").exists() else []
    assert not parks, parks
