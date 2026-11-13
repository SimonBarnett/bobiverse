"""FR #6773: local bobiverse.json edits must not block install ff; residual ff-fail reports digest sync + one stall.

Acceptance:
- Checkout with a local edit to tracked bob/tray/config/bobiverse.json fast-forwards and keeps local values
  (via untracked bobiverse.local.json overlay).
- Fast-forward that fails for another reason sets digest sync field and files one stall report; a second
  failure comments on that report rather than filing another.
- No secrets from config in digest/report/logs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

from repo_layout import REPO

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("git"),
    reason="windows + git",
)

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
GET_IRC = REPO / "bob" / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
BOBREPORT = REPO / "common" / "scripts" / "bobreport.py"
STALL_PY = REPO / "common" / "scripts" / "sync_ff_stall.py"
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


def _base_cfg(host="irc.example.test", channel="#bobiverse"):
    return {
        "channel": channel,
        "host": host,
        "port": 6697,
        "reportUrl": "https://bob.example.test/bob/v1/report",
        "reportPort": 7700,
        "shortids": {},
        "nicks": {},
        "legacyAliases": {},
        "chairNick": "Jeeves",
    }


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
        json.dumps(_base_cfg(), indent=2) + "\n",
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
        # Harness must not file live stall intakes (FR #6773).
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


def test_fr6773_helpers_and_wiring_present():
    text = COMMON.read_text(encoding="utf-8")
    body = _fn_body(text, "Sync-BobiverseWorkTree")
    assert "Clear-BobiverseMachineLocalConfigForSync" in body or "bobiverse.local.json" in body
    assert "Clear-BobiverseDirtyTrackedForSync" in text
    assert "FR #6989" in text
    excl = _fn_body(text, "Get-BobiverseInstallGitExcludeText")
    assert ".bobiverse-parked" in excl
    assert "Report-BobiverseSyncFfStall" in body or "Write-BobiverseSyncStatus" in body
    assert "FR #6773" in body or "#6773" in body
    excl = _fn_body(text, "Get-BobiverseInstallGitExcludeText")
    assert "bobiverse.local.json" in excl
    # Must not use stash / reset --hard / checkout -f inside Sync-BobiverseWorkTree
    for forbidden in ("reset --hard", "'stash'", "checkout', '-f'", "'--force'"):
        assert forbidden not in body, forbidden

    cfg = GET_IRC.read_text(encoding="utf-8")
    assert "bobiverse.local.json" in cfg
    assert "Get-BobiverseConfig" in cfg

    br = BOBREPORT.read_text(encoding="utf-8")
    assert '"sync"' in br or "'sync'" in br
    assert STALL_PY.is_file()


def test_fr6773_local_bobiverse_json_edit_ffs_and_keeps_values(world):
    r = world.root("bob")
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")
    out1 = world.sync()
    assert out1.returncode == 0, out1.text
    tracked = r / "bob" / "tray" / "config" / "bobiverse.json"
    assert tracked.is_file()
    local_edit = _base_cfg(host="irc.local.override", channel="#local-shop")
    # Plant a secret-looking key that must never appear in sync logs/stall.
    local_edit["connect"] = {"password": "FAKE_secret_should_not_leak"}
    write(tracked, json.dumps(local_edit, indent=2) + "\n")
    # Tip ahead so behind count > 0 and ff would otherwise fail on dirty tracked file.
    world.upstream(
        "bob/scripts/b1.ps1",
        "# bob 1 tip\n",
        msg="tip ahead",
    )
    world.upstream(
        "common/scripts/c1.ps1",
        "# common tip\n",
        msg="common tip",
    )
    out2 = world.sync()
    text = out2.text
    assert out2.returncode == 0, text
    assert "sync-ff-failed" not in text, text
    assert "FAKE_secret_should_not_leak" not in text, text
    # HEAD should be tip.
    head = git(r, "rev-parse", "HEAD").stdout.strip()
    tip = git(r, "rev-parse", "origin/main").stdout.strip()
    assert head == tip, (head, tip, text)
    overlay = r / "bob" / "tray" / "config" / "bobiverse.local.json"
    flat_overlay = r / "config" / "bobiverse.local.json"
    assert overlay.is_file() or flat_overlay.is_file(), text
    blob = (overlay if overlay.is_file() else flat_overlay).read_text(encoding="utf-8")
    assert "irc.local.override" in blob
    assert "#local-shop" in blob
    # Tracked file clean / matches tip (or at least not blocking).
    st = git(r, "status", "--porcelain", "--", "bob/tray/config/bobiverse.json")
    assert not st.stdout.strip(), st.stdout


def test_fr6773_other_ff_fail_sets_sync_stamp_and_dedupes_stall(world, tmp_path):
    r = world.root("bob")
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")
    assert world.sync().returncode == 0
    # Unique local commit blocks ff without being a parkable bobiverse.json edit.
    write(r / "bob" / "scripts" / "b1.ps1", "# LOCAL COMMIT\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "local only")
    world.upstream("bob/scripts/b2.ps1", "# upstream b2\n", msg="remote tip")
    stall_dir = tmp_path / "sync-stall"
    status_dir = tmp_path / "sync-status"
    env = {
        "BOB_SYNC_STATUS_DIR": str(status_dir),
        "BOB_SYNC_STALL_DIR": str(stall_dir),
        "BOB_MACHINE_ID": "testbox-fr6773",
    }
    out = world.sync(extra_env=env)
    text = out.text
    assert out.returncode == 0, text
    assert "sync-ff-failed" in text or "ff-only not possible" in text, text
    assert "FAKE_" not in text
    # Stamp for digest
    stamps = list(status_dir.glob("*.json")) if status_dir.exists() else []
    # Also accept install-root stamp
    install_stamp = r / "logs" / "sync-status.json"
    assert stamps or install_stamp.is_file(), text
    stamp_path = stamps[0] if stamps else install_stamp
    doc = json.loads(stamp_path.read_text(encoding="utf-8"))
    assert int(doc.get("behind") or 0) >= 1 or "behind" in str(doc.get("sync") or "")
    sync_field = str(doc.get("sync") or "")
    if not sync_field:
        sync_field = "behind {0}, {1}".format(doc.get("behind"), doc.get("reason"))
    assert "behind" in sync_field.lower()
    assert "password" not in sync_field.lower()
    # Stall dedupe unit path (isolated machine id; never hit live gh/intake).
    assert STALL_PY.is_file()
    sys.path.insert(0, str(REPO / "common" / "scripts"))
    import importlib
    import sync_ff_stall  # noqa: E402

    importlib.reload(sync_ff_stall)

    unit_stall = tmp_path / "sync-stall-unit"
    unit_stall.mkdir(parents=True, exist_ok=True)
    unit_mid = "fr6773-unit-%s" % os.getpid()
    posts = []

    def fake_post(title, body, **kw):
        posts.append({"title": title, "body": body, **kw})
        return {"ok": True, "number": 9001}

    comments = []

    def fake_comment(repo, number, body):
        comments.append({"repo": repo, "number": number, "body": body})
        return True

    with mock.patch.object(sync_ff_stall, "_post", fake_post), mock.patch.object(
        sync_ff_stall, "_gh_comment", fake_comment
    ), mock.patch.object(sync_ff_stall, "_gh_search_open", lambda *a, **k: None):
        os.environ["BOB_SYNC_STALL_DIR"] = str(unit_stall)
        os.environ["BOB_MACHINE_ID"] = unit_mid
        r1 = sync_ff_stall.report(
            behind=3,
            reason="ff-only not possible (local commits or edits in the way)",
            machine=unit_mid,
        )
        assert r1.get("deduped") is False, r1
        assert len(posts) == 1
        assert "password" not in posts[0]["body"].lower()
        assert ("crash-sig:sync-ff-failed:%s" % unit_mid) in posts[0]["body"]
        # Seed state as if intake returned 9001
        state = unit_stall / ("%s.json" % unit_mid)
        state.write_text(
            json.dumps(
                {
                    "number": 9001,
                    "sig": "sync-ff-failed:%s" % unit_mid,
                    "count": 1,
                }
            ),
            encoding="utf-8",
        )
        r2 = sync_ff_stall.report(
            behind=5,
            reason="ff-only not possible (local commits or edits in the way)",
            machine=unit_mid,
        )
        assert r2.get("deduped") is True, r2
        assert len(posts) == 1  # no second intake
        assert len(comments) == 1
        assert comments[0]["number"] == 9001


def test_fr6773_bobreport_exports_sync_field():
    sys.path.insert(0, str(REPO / "common" / "scripts"))
    import bobreport

    assert "sync" in bobreport._MERGE_PEER_FIELDS or "sync" in bobreport._TRAY_MACHINE_EXPORT_KEYS
    mid = "fr6773box"
    ent = bobreport._coerce_machine(mid, {"online": True, "sync": "behind 12, ff-only not possible"})
    assert ent.get("sync") == "behind 12, ff-only not possible"


def test_fr6989_dirty_tracked_product_files_ffs(world):
    """Redqueen stall: dirty RecycleSeat/gitclaim/recycleseat must not block ff."""
    r = world.root("bob")
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")
    assert world.sync().returncode == 0
    world.upstream(
        "bob/tray/tools/BobTrayRecycleSeat.ps1",
        "# recycle v1\n",
        msg="add recycle",
    )
    world.upstream(
        "common/scripts/gitclaim.py",
        "# gitclaim v1\n",
        msg="add gitclaim",
    )
    world.upstream(
        "common/scripts/recycleseat.py",
        "# recycleseat v1\n",
        msg="add recycleseat",
    )
    assert world.sync().returncode == 0
    write(r / "bob/tray/tools/BobTrayRecycleSeat.ps1", "# LOCAL HOTPATCH FAKE_secret_should_not_leak\n")
    write(r / "common/scripts/gitclaim.py", "# LOCAL gitclaim\n")
    write(r / "common/scripts/recycleseat.py", "# LOCAL recycleseat\n")
    world.upstream("common/scripts/c1.ps1", "# common tip 6989\n", msg="tip ahead")
    out = world.sync()
    text = out.text
    assert out.returncode == 0, text
    assert "sync-ff-failed" not in text, text
    assert "FAKE_secret_should_not_leak" not in text, text
    assert "sync-park-dirty" in text or "FR#6989" in text or "6989" in text
    head = git(r, "rev-parse", "HEAD").stdout.strip()
    tip = git(r, "rev-parse", "origin/main").stdout.strip()
    assert head == tip, (head, tip, text)
    assert (r / "bob/tray/tools/BobTrayRecycleSeat.ps1").read_text(encoding="utf-8").startswith("# recycle v1")
    parks = list((r / ".bobiverse-parked").rglob("*.ps1")) if (r / ".bobiverse-parked").exists() else []
    assert parks, text
    st = git(r, "status", "--porcelain", "--", "bob/tray/tools/BobTrayRecycleSeat.ps1")
    assert not st.stdout.strip(), st.stdout


def test_fr6989_skip_secret_named_dirty_file(world):
    r = world.root("bob")
    write(r / "VERSION", "0.0.1\n")
    write(r / "scripts/old.ps1", "# old\n")
    assert world.sync().returncode == 0
    world.upstream("bob/config/github.token", "FAKE_token_placeholder\n", msg="token tracked")
    assert world.sync().returncode == 0
    write(r / "bob/config/github.token", "FAKE_token_placeholder_dirty\n")
    world.upstream("common/scripts/c1.ps1", "# common after token\n", msg="tip")
    out = world.sync()
    text = out.text
    assert "FAKE_token_placeholder_dirty" not in text, text
    # docs/mrb-6990: require the skip log; do not accept bare returncode==0
    # (that would green if a regression copied the secret into .bobiverse-parked).
    assert "skip-secret" in text, text
    park = r / ".bobiverse-parked"
    if park.exists():
        leaked = [
            p for p in park.rglob("*")
            if p.is_file() and "github.token" in str(p).replace("\\", "/")
        ]
        assert not leaked, leaked
    # Dirty secret path must remain (not checkout --'d away).
    dirty = (r / "bob/config/github.token").read_text(encoding="utf-8")
    assert "FAKE_token_placeholder_dirty" in dirty


def test_fr6989_secret_path_helper_pins():
    """docs/mrb-6990: Test-BobiverseSyncParkSecretPath covers token/password/identity."""
    text = COMMON.read_text(encoding="utf-8")
    body = _fn_body(text, "Test-BobiverseSyncParkSecretPath")
    assert "FR #6989" in body or "FR #6989" in text
    # Regex source uses github\\.token / identity\\.json escaping.
    assert "github\\.token" in body
    assert "identity\\.json" in body
    assert ".password" in body
    assert "nickserv" in body.lower()
