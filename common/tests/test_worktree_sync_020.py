"""t781u/t782u: the install dir is a sparse git work tree (<product>/ + common/ only), fast-forwarded on service start.

The "remote" is a local bare repo with the split layout; Sync-BobiverseFromRepo.ps1 runs for real against it with BOB_AI_ROOT /
BOBIVERSE_REMOTE pointed at temp dirs (nothing touches the machine's real C:\\ai or GitHub).
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from repo_layout import REPO

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("git"), reason="windows + git harness")

SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def git(cwd, *a, check=True):
    r = subprocess.run(["git", *IDENT, "-c", "core.autocrlf=false", "-C", str(cwd), *a], capture_output=True, text=True)
    if check:
        assert r.returncode == 0, (a, r.stdout, r.stderr)
    return r


def write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture()
def world(tmp_path):
    """seed clone -> bare 'remote' with the split layout; ai root + install dirs under tmp."""
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    write(seed / "common/VERSION", "9.9.9\n")
    write(seed / "common/scripts/c1.ps1", "# common 1\n")
    write(seed / "bob/scripts/b1.ps1", "# bob 1\n")
    write(seed / "bob/scripts/b2.ps1", "# bob 2\n")
    write(seed / "bob/third_party/bob-tray/tools/Watch-BobTray.ps1", "# tray v1\n")
    write(seed / "bob/third_party/bob-tray/src/BobBridge.psm1", "# bridge v1\n")
    write(seed / "bob/third_party/bob-tray/src/VERSION", "0.0.0-tray\n")
    write(seed / "bob/third_party/bob-tray/assets/icon.txt", "icon\n")
    write(seed / "jeeves/scripts/j1.ps1", "# jeeves 1\n")
    write(seed / "airc/scripts/a1.ps1", "# airc 1\n")
    write(seed / "README.md", "root readme\n")
    write(seed / "conftest.py", "# root conftest\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "init")
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(bare)], check=True, capture_output=True)
    git(seed, "remote", "add", "origin", str(bare))
    git(seed, "branch", "-u", "origin/main", check=False)

    class W:
        pass

    w = W()
    w.tmp, w.seed, w.bare = tmp_path, seed, bare
    w.ai = tmp_path / "ai"
    w.ai.mkdir()

    def root(product):
        r = w.ai / product
        r.mkdir(exist_ok=True)
        return r

    def upstream(path, text, msg="up", version=None):
        write(seed / path, text)
        if version:
            write(seed / "common/VERSION", version + "\n")
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", msg)
        git(seed, "push", "-q", "origin", "main")

    def sync(product, extra_env=None, remote=None, root_dir=None):
        env = {k: v for k, v in os.environ.items() if k not in ("BOBIVERSE_REPO", "BOBIVERSE_NO_UPDATE", "BOB_AI_ROOT", "BOBIVERSE_REMOTE")}
        env["BOB_AI_ROOT"] = str(w.ai)
        env["BOBIVERSE_REMOTE"] = str(remote or bare)
        env.update(extra_env or {})
        t0 = time.time()
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SYNC), "-Product", product,
                            "-InstallRoot", str(root_dir or root(product))], capture_output=True, text=True, timeout=240, env=env)
        r.elapsed = time.time() - t0
        r.text = r.stdout + r.stderr
        return r

    w.root, w.upstream, w.sync = root, upstream, sync
    return w


def seed_install(r: Path):
    write(r / "scripts/old.ps1", "# pre-existing installed script\n")
    write(r / "VERSION", "0.0.1\n")
    write(r / "config/secret.txt", "keep me\n")
    write(r / "home/state.json", "{}\n")


@pytest.mark.parametrize("product,other", [("bob", ("jeeves", "airc")), ("jeeves", ("bob", "airc")), ("airc", ("bob", "jeeves"))])
def test_bootstrap_sparse_only_own_subtree_plus_common(world, product, other):
    r = world.root(product)
    seed_install(r)
    out = world.sync(product)
    assert out.returncode == 0, out.text
    assert (r / ".git").is_dir()
    # tracked tree = <product>/ + common/ and NOTHING else (no sibling products, no repo-root files)
    assert (r / product / "scripts" / f"{product[0]}1.ps1").is_file()
    assert (r / "common/scripts/c1.ps1").is_file() and (r / "common/VERSION").is_file()
    for o in other:
        assert not (r / o).exists(), o
    assert not (r / "README.md").exists() and not (r / "conftest.py").exists()
    # flat runtime composed from it, VERSION from common/VERSION, pre-existing files + config + home untouched
    assert (r / "scripts" / f"{product[0]}1.ps1").is_file() and (r / "scripts/c1.ps1").is_file()
    assert not (r / "scripts" / f"{other[0][0]}1.ps1").exists()
    assert (r / "VERSION").read_text().strip() == "9.9.9"
    assert (r / "scripts/old.ps1").read_text().startswith("# pre-existing")
    assert (r / "config/secret.txt").read_text() == "keep me\n" and (r / "home/state.json").is_file()
    # git view: on main tracking origin/main, clean (flat files hidden by info/exclude)
    assert git(r, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"
    assert git(r, "rev-parse", "--abbrev-ref", "main@{upstream}").stdout.strip() == "origin/main"
    assert git(r, "status", "--porcelain").stdout.strip() == ""
    assert "bootstrap" in out.text.lower()


def test_next_start_fast_forwards_and_recomposes(world):
    r = world.root("bob")
    seed_install(r)
    assert world.sync("bob").returncode == 0
    world.upstream("bob/scripts/b1.ps1", "# bob 1 v2\n", version="9.9.10")
    out = world.sync("bob")
    assert out.returncode == 0, out.text
    assert (r / "bob/scripts/b1.ps1").read_text() == "# bob 1 v2\n"
    assert (r / "scripts/b1.ps1").read_text() == "# bob 1 v2\n"
    assert (r / "VERSION").read_text().strip() == "9.9.10"
    assert git(r, "rev-parse", "HEAD").stdout == git(world.bare, "rev-parse", "main").stdout
    assert "fast-forwarded" in out.text


def test_local_uncommitted_edit_survives_non_overlapping_ff(world):
    r = world.root("bob")
    assert world.sync("bob").returncode == 0
    write(r / "bob/scripts/b2.ps1", "# MY LOCAL EDIT\n")
    world.upstream("bob/scripts/b1.ps1", "# bob 1 v2\n")
    out = world.sync("bob")
    assert out.returncode == 0, out.text
    assert (r / "bob/scripts/b2.ps1").read_text() == "# MY LOCAL EDIT\n"
    assert (r / "bob/scripts/b1.ps1").read_text() == "# bob 1 v2\n"


def test_overlapping_local_edit_blocks_ff_but_never_start_or_work(world):
    r = world.root("bob")
    assert world.sync("bob").returncode == 0
    head = git(r, "rev-parse", "HEAD").stdout
    write(r / "bob/scripts/b1.ps1", "# MY LOCAL EDIT\n")
    world.upstream("bob/scripts/b1.ps1", "# upstream change\n")
    out = world.sync("bob")
    assert out.returncode == 0, out.text
    assert (r / "bob/scripts/b1.ps1").read_text() == "# MY LOCAL EDIT\n"
    assert git(r, "rev-parse", "HEAD").stdout == head
    assert "ff-only not possible" in out.text


def test_diverged_local_commit_is_kept(world):
    r = world.root("bob")
    assert world.sync("bob").returncode == 0
    write(r / "bob/scripts/b2.ps1", "# local commit\n")
    git(r, "add", "bob/scripts/b2.ps1")
    git(r, "commit", "-q", "-m", "local work")
    mine = git(r, "rev-parse", "HEAD").stdout
    world.upstream("bob/scripts/b1.ps1", "# upstream change\n")
    out = world.sync("bob")
    assert out.returncode == 0, out.text
    assert git(r, "rev-parse", "HEAD").stdout == mine           # no merge, no reset
    assert (r / "bob/scripts/b2.ps1").read_text() == "# local commit\n"
    assert git(r, "log", "-1", "--format=%s").stdout.strip() == "local work"


def test_agent_branch_is_left_alone_but_origin_is_fetched(world):
    r = world.root("jeeves")
    assert world.sync("jeeves").returncode == 0
    git(r, "switch", "-q", "-c", "fix/my-work")
    write(r / "jeeves/scripts/j1.ps1", "# agent change\n")
    git(r, "commit", "-q", "-am", "agent commit")
    mine = git(r, "rev-parse", "HEAD").stdout
    world.upstream("jeeves/scripts/j1.ps1", "# upstream jeeves\n")
    out = world.sync("jeeves")
    assert out.returncode == 0, out.text
    assert git(r, "symbolic-ref", "--short", "HEAD").stdout.strip() == "fix/my-work"
    assert git(r, "rev-parse", "HEAD").stdout == mine
    assert git(r, "rev-parse", "origin/main").stdout == git(world.bare, "rev-parse", "main").stdout   # fetched
    # the running (flat) copy is built from the agent's branch work
    assert (r / "scripts/j1.ps1").read_text() == "# agent change\n"
    assert "fix/my-work" in out.text


def test_agent_can_branch_commit_and_push_from_the_install_dir(world):
    r = world.root("bob")
    assert world.sync("bob").returncode == 0
    git(r, "switch", "-q", "-c", "fix/from-install-dir")
    write(r / "bob/scripts/new_tool.ps1", "# new\n")
    git(r, "add", "bob/scripts/new_tool.ps1")
    git(r, "commit", "-q", "-m", "add tool")
    git(r, "push", "-q", "-u", "origin", "fix/from-install-dir")
    assert "fix/from-install-dir" in git(world.bare, "branch", "--list").stdout
    assert git(world.bare, "show", "fix/from-install-dir:bob/scripts/new_tool.ps1").stdout == "# new\n"


def test_offline_first_start_creates_nothing_and_never_fails(world):
    r = world.root("bob")
    seed_install(r)
    out = world.sync("bob", remote=world.tmp / "does-not-exist.git")
    assert out.returncode in (0, 2), out.text
    assert not (r / ".git").exists()                              # half-made repo cleaned up
    assert (r / "scripts/old.ps1").is_file() and (r / "VERSION").read_text().strip() == "0.0.1"
    assert out.elapsed < 90


def test_offline_later_start_keeps_the_tree(world):
    r = world.root("bob")
    assert world.sync("bob").returncode == 0
    head = git(r, "rev-parse", "HEAD").stdout
    gone = world.tmp / "gone.git"
    world.bare.rename(gone)
    out = world.sync("bob")
    assert out.returncode == 0, out.text
    assert git(r, "rev-parse", "HEAD").stdout == head and (r / "scripts/b1.ps1").is_file()
    assert "fetch failed" in out.text


def test_opt_out_bobiverse_no_update(world):
    r = world.root("bob")
    seed_install(r)
    out = world.sync("bob", {"BOBIVERSE_NO_UPDATE": "1"})
    assert out.returncode == 0 and "BOBIVERSE_NO_UPDATE=1" in out.text
    assert not (r / ".git").exists() and (r / "VERSION").read_text().strip() == "0.0.1"


def test_in_progress_merge_is_not_touched(world):
    r = world.root("bob")
    assert world.sync("bob").returncode == 0
    (r / ".git" / "MERGE_HEAD").write_text(git(r, "rev-parse", "HEAD").stdout)
    world.upstream("bob/scripts/b1.ps1", "# upstream\n")
    out = world.sync("bob")
    assert out.returncode == 0 and "operation in progress" in out.text
    assert (r / "bob/scripts/b1.ps1").read_text() == "# bob 1\n"


# ---------------------------------------------------------------- wiring / docs
def _t(rel):
    return (REPO / rel).read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("rel,prod", [("bob/scripts/Start-Bob.ps1", "bob"), ("jeeves/scripts/Start-Jeeves.ps1", "jeeves"), ("airc/scripts/Start-AircConsole.ps1", "airc")])
def test_start_scripts_ff_first_then_release_check_and_honour_opt_out(rel, prod):
    t = _t(rel)
    assert f"& $sync -Product {prod}" in t
    assert "BOBIVERSE_REPO -and" not in t                      # no longer an opt-in: every start tries the work tree
    assert "BOBIVERSE_NO_UPDATE" in t
    assert t.index("& $sync") < t.index("& $updater")   # dev path first, release path second


def test_sync_script_precedence_and_safety_contract():
    t = _t("common/scripts/Sync-BobiverseFromRepo.ps1")
    assert "Sync-BobiverseWorkTree" in t and "BOBIVERSE_REPO" in t
    c = _t("common/scripts/Bobiverse-Common.ps1")
    assert "--ff-only" in c and "sparse-checkout" in c and "'--no-cone'" in c
    for forbidden in ("reset --hard", "'reset'", "'stash'", "'clean'", "checkout', '-f'", "'--force'"):
        assert forbidden not in c.split("function Sync-BobiverseWorkTree")[1].split("function Test-BobiverseSplitRepo")[0], forbidden


def test_docs_describe_the_work_tree_and_opt_out():
    for rel in ("README.md", "bob/AGENTS.md", "jeeves/AGENTS.md", "airc/AGENTS.md", "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"):
        t = _t(rel)
        assert "work tree" in t.lower() or "worktree" in t.lower(), rel
        assert "BOBIVERSE_NO_UPDATE" in t, rel

def test_tray_runtime_dirs_follow_the_work_tree(world):
    """The tray runs from tools\\ src\\ assets\\ (not third_party\\bob-tray): a work-tree ff must refresh those too, but never VERSION."""
    r = world.root("bob")
    write(r / "src/VERSION", "0.1.19\n")
    assert world.sync("bob").returncode == 0
    assert (r / "tools/Watch-BobTray.ps1").read_text() == "# tray v1\n"
    assert (r / "src/BobBridge.psm1").read_text() == "# bridge v1\n"
    assert (r / "assets/icon.txt").is_file()
    assert (r / "src/VERSION").read_text().strip() == "0.1.19"           # the product VERSION is never replaced by the tray's
    world.upstream("bob/third_party/bob-tray/tools/Watch-BobTray.ps1", "# tray v2\n")
    assert world.sync("bob").returncode == 0
    assert (r / "tools/Watch-BobTray.ps1").read_text() == "# tray v2\n"
