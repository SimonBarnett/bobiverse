"""FR #6970: dirty .bobiverse/build.yml must not block install ff (flamingo stall).

Park into untracked build.local.yml, restore tracked recipe, ff to tip.
Residual ff failures include dirty path names (never file bodies / secrets).
"""
from __future__ import annotations

import json
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

BUILD_YML = """# FR #4006 recipe
machine: testbox
baseline: last_release_tag
channel: "#bobiverse"
max_parallel_builds: 1
cache_dirs: []
suites: []
pack:
  cmd: echo pack
  artifacts: []
"""


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
    write(seed / ".bobiverse/build.yml", BUILD_YML)
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

    def sync(product="bob", extra_env=None, root_dir=None):
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


def test_fr6970_wiring_parks_build_yml_and_names_dirty_paths():
    text = COMMON.read_text(encoding="utf-8")
    assert ".bobiverse/build.yml" in text
    assert "build.local.yml" in text
    assert "Get-BobiverseSyncDirtyPathSummary" in text
    body = _fn_body(text, "Sync-BobiverseWorkTree")
    assert "Get-BobiverseSyncDirtyPathSummary" in body
    excl = _fn_body(text, "Get-BobiverseInstallGitExcludeText")
    assert "build.local.yml" in excl
    for forbidden in ("reset --hard", "'stash'", "checkout', '-f'"):
        assert forbidden not in body, forbidden


def test_fr6970_dirty_build_yml_ffs_and_keeps_local_overlay(world):
    r = world.root("bob")
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")
    assert world.sync().returncode == 0
    # Sparse bob install is /bob/+/common/ only; BUILD hosts (flamingo) also materialise /.bobiverse/.
    git(r, "sparse-checkout", "set", "--no-cone", "/bob/", "/common/", "/.bobiverse/")
    git(r, "checkout", "-q", "HEAD", "--", ".bobiverse/build.yml")
    tracked = r / ".bobiverse" / "build.yml"
    assert tracked.is_file()
    # Machine rewrite (JSON one-liner) must not block ff — same class as flamingo #6970.
    local = '{"machine":"flamingo","baseline":"last_release_tag","channel":"#bobiverse","max_parallel_builds":1,"cache_dirs":[],"suites":[],"pack":{"cmd":"echo pack","artifacts":[]}}\n'
    write(tracked, local)
    world.upstream("bob/scripts/b1.ps1", "# bob tip\n", msg="tip ahead")
    world.upstream("common/scripts/c1.ps1", "# common tip\n", msg="common tip")
    out = world.sync()
    text = out.text
    assert out.returncode == 0, text
    assert "sync-ff-failed" not in text, text
    head = git(r, "rev-parse", "HEAD").stdout.strip()
    tip = git(r, "rev-parse", "origin/main").stdout.strip()
    assert head == tip, (head, tip, text)
    overlay = r / ".bobiverse" / "build.local.yml"
    assert overlay.is_file(), text
    assert "flamingo" in overlay.read_text(encoding="utf-8")
    st = git(r, "status", "--porcelain", "--", ".bobiverse/build.yml")
    assert not st.stdout.strip(), st.stdout


def test_fr6970_ff_fail_reason_lists_dirty_path_names(world, tmp_path):
    r = world.root("bob")
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")
    assert world.sync().returncode == 0
    # Unique local commit blocks ff; leave an unparkable dirty path too.
    write(r / "bob" / "scripts" / "b1.ps1", "# LOCAL COMMIT\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "local only")
    write(r / "bob" / "scripts" / "extra-dirty.ps1", "# dirty uncommitted\n")
    world.upstream("bob/scripts/b2.ps1", "# upstream b2\n", msg="remote tip")
    env = {
        "BOB_SYNC_STATUS_DIR": str(tmp_path / "sync-status"),
        "BOB_SYNC_STALL_DIR": str(tmp_path / "sync-stall"),
        "BOB_MACHINE_ID": "testbox-fr6970",
    }
    out = world.sync(extra_env=env)
    text = out.text
    assert out.returncode == 0, text
    assert "sync-ff-failed" in text or "ff-only not possible" in text, text
    assert "dirty:" in text, text
    # Path name only — no file body from the dirty script.
    assert "# dirty uncommitted" not in text, text
    assert "FAKE_secret" not in text, text
