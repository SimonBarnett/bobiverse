"""FR #7008: tip-overlay Bobiverse-Common.ps1 then re-park when loaded Common lacks park.

Acceptance: install behind tip + dirty tracked non-secret file + loaded module without
Clear-BobiverseDirtyTrackedForSync still parks after tip-overlay retry and ff succeeds.
Existing #6989 / #6773 tests stay green.
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
IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def _fn_body(text: str, name: str) -> str:
    m = re.search(r"function\s+" + re.escape(name) + r"\b", text)
    assert m, name
    rest = text[m.start() :]
    m2 = re.search(r"\nfunction\s+\w+", rest[1:])
    return rest if not m2 else rest[: m2.start() + 1]


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


def _strip_park_function(common_text: str) -> str:
    """Leave Sync-BobiverseWorkTree (with #7008 tip-retry) but remove park helper."""
    # Remove Clear-BobiverseDirtyTrackedForSync so first park attempt is a missing command.
    m = re.search(
        r"\nfunction\s+Clear-BobiverseDirtyTrackedForSync\b",
        common_text,
    )
    assert m, "Clear-BobiverseDirtyTrackedForSync missing in tip Common"
    start = m.start() + 1
    rest = common_text[start:]
    m2 = re.search(r"\nfunction\s+\w+", rest[1:])
    assert m2, "next function after Clear-BobiverseDirtyTrackedForSync"
    end = start + m2.start() + 1
    stub = (
        "function Clear-BobiverseDirtyTrackedForSync {\n"
        "    # FR #7008 test stub: simulate pre-park Common (function absent at load).\n"
        "    throw 'Clear-BobiverseDirtyTrackedForSync not present in loaded module'\n"
        "}\n\n"
    )
    return common_text[:start] + stub + common_text[end:]


def test_fr7008_wiring_tip_overlay_on_ff_fail():
    text = COMMON.read_text(encoding="utf-8")
    body = _fn_body(text, "Sync-BobiverseWorkTree")
    assert "FR #7008" in body or "FR#7008" in body
    assert "Sync-BobiverseScriptTipFromOrigin" in body
    assert "sync-tip-overlay-common" in body
    assert "Clear-BobiverseDirtyTrackedForSync" in body
    assert "Bobiverse-Common.ps1" in body


@pytest.fixture()
def world(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    tip_common = COMMON.read_text(encoding="utf-8")
    write(seed / "common/VERSION", "9.9.9\n")
    write(seed / "common/scripts/c1.ps1", "# common 1\n")
    write(seed / "common/scripts/Bobiverse-Common.ps1", tip_common)
    write(seed / "bob/scripts/b1.ps1", "# bob 1\n")
    write(seed / "bob/tray/tools/Watch-BobTray.ps1", "# tray v1\n")
    write(seed / "bob/tray/src/BobBridge.psm1", "# bridge v1\n")
    write(seed / "bob/tray/src/VERSION", "0.0.0-tray\n")
    write(seed / "bob/tray/assets/icon.txt", "icon\n")
    write(seed / "bob/tray/config/bobiverse.json", '{"channel":"#bobiverse"}\n')
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

    stale_dir = tmp_path / "stale-sync"
    stale_dir.mkdir()
    shutil.copy2(SYNC, stale_dir / "Sync-BobiverseFromRepo.ps1")
    write(stale_dir / "Bobiverse-Common.ps1", _strip_park_function(tip_common))

    class W:
        pass

    w = W()
    w.tmp, w.seed, w.bare = tmp_path, seed, bare
    w.ai = tmp_path / "ai"
    w.ai.mkdir()
    w.stale_dir = stale_dir

    def root(product="bob"):
        r = w.ai / product
        r.mkdir(exist_ok=True)
        return r

    def upstream(path, text, msg="up"):
        write(seed / path, text)
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", msg)
        git(seed, "push", "-q", "origin", "main")

    def sync(product="bob", extra_env=None, root_dir=None, use_stale=False):
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
        env.update(extra_env or {})
        sync_file = (
            str(stale_dir / "Sync-BobiverseFromRepo.ps1") if use_stale else str(SYNC)
        )
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                sync_file,
                "-Product",
                product,
                "-InstallRoot",
                str(root_dir or root(product)),
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


def test_fr7008_stale_loaded_common_tip_overlay_parks_and_ffs(world):
    r = world.root("bob")
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")
    assert world.sync().returncode == 0
    world.upstream(
        "bob/tray/tools/BobTrayRecycleSeat.ps1",
        "# recycle v1\n",
        msg="add recycle",
    )
    assert world.sync().returncode == 0
    # Local dirty edit on a path tip will also change — blocks ff until parked.
    write(r / "bob/tray/tools/BobTrayRecycleSeat.ps1", "# LOCAL HOTPATCH no_secret_body\n")
    world.upstream(
        "bob/tray/tools/BobTrayRecycleSeat.ps1",
        "# recycle tip v2\n",
        msg="tip changes dirty path 7008",
    )
    # Stale loaded Common: park helper throws; tip-overlay must re-dot tip Common then park.
    out = world.sync(use_stale=True)
    text = out.text
    assert out.returncode == 0, text
    assert "sync-ff-failed" not in text, text
    assert "sync-tip-overlay-common" in text or "FR#7008" in text, text
    assert "no_secret_body" not in text, text
    assert "sync-park-dirty" in text or "FR#6989" in text, text
    head = git(r, "rev-parse", "HEAD").stdout.strip()
    tip = git(r, "rev-parse", "origin/main").stdout.strip()
    assert head == tip, (head, tip, text)
    assert (r / "bob/tray/tools/BobTrayRecycleSeat.ps1").read_text(encoding="utf-8").startswith(
        "# recycle tip v2"
    )
