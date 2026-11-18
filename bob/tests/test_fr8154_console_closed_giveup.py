# -*- coding: utf-8 -*-
"""FR #8154: console-close mid-ACK GIVEUPs the job and saves WIP when dirty."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import bob_worker as bw

from test_bob_worker_020 import Rig


def _git_init_dirty(tmp: Path) -> Path:
    root = tmp / "wt"
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "a.txt").write_text("two\n", encoding="utf-8")
    return root


def _arm_ack(rig, job_key: str) -> bw.BoredEmitter:
    bored = bw.BoredEmitter(lambda: True, rig.logs.append)
    bored.run_dir = Path(rig.sup.run_dir)
    bored._ack_open = True
    bored._ack_job_key = job_key
    bored._ack_at = time.time()
    rig.sup.bored = bored
    return bored


def test_console_closed_giveup_line_with_and_without_wip():
    assert bw.console_closed_giveup_line("FR owner/repo#1") == (
        "GIVEUP FR owner/repo#1 console-closed"
    )
    assert bw.console_closed_giveup_line("FR owner/repo#1", "fr-1:abc123") == (
        "GIVEUP FR owner/repo#1 console-closed wip=fr-1:abc123"
    )


def test_is_console_closed_shutdown_reason():
    assert bw.is_console_closed_shutdown_reason("console-closed") is True
    assert bw.is_console_closed_shutdown_reason("window-closed") is True
    assert bw.is_console_closed_shutdown_reason("agent-exited") is False
    assert bw.is_console_closed_shutdown_reason("") is False


def test_pending_giveup_append_and_drain(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_BRIDGE_HOME", str(tmp_path / "bridge"))
    line = "GIVEUP FR owner/repo#9 console-closed"
    assert bw.append_pending_console_closed_giveup("flamingo", line) is True
    got = bw.drain_pending_console_closed_giveups("flamingo")
    assert got == [line]
    assert bw.drain_pending_console_closed_giveups("flamingo") == []


def test_save_console_closed_wip_dirty_and_clean(tmp_path):
    dirty = _git_init_dirty(tmp_path / "dirty")
    ref = bw.save_console_closed_wip(
        dirty, "FR SimonBarnett/bobiverse#8154", push=False
    )
    assert ref.startswith("fr-8154:")
    assert bw.worktree_is_dirty(dirty) is True  # stash create leaves tree intact

    clean = tmp_path / "clean"
    clean.mkdir()
    subprocess.run(["git", "init"], cwd=clean, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=clean,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=clean,
        check=True,
        capture_output=True,
    )
    (clean / "b.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "b.txt"], cwd=clean, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=clean,
        check=True,
        capture_output=True,
    )
    assert bw.save_console_closed_wip(clean, "FR owner/repo#1", push=False) == ""


def test_shutdown_console_closed_with_ack_posts_giveup(tmp_path, monkeypatch):
    """CTRL_CLOSE mid-ACK → GIVEUP on IRC when alive."""
    said: list[tuple[str, str]] = []

    class FakeIrc:
        shop = "#flamingo"
        alive = True

        def say(self, target, text):
            said.append((target, text))

        def close(self, *_a, **_k):
            pass

    monkeypatch.setenv("BOB_BRIDGE_HOME", str(tmp_path / "bridge"))
    wt = _git_init_dirty(tmp_path)
    monkeypatch.setenv("BOB_JOB_WORKTREE", str(wt))

    rig = Rig(tmp_path / "run", irc=FakeIrc(), kind="opencode")
    bored = _arm_ack(rig, "FR SimonBarnett/bobiverse#8154")
    rig.sup.irc = FakeIrc()

    rig.sup.shutdown("console-closed", bw.EXIT_OK)

    giveups = [t for _, t in said if t.startswith("GIVEUP ")]
    assert giveups, said
    assert "console-closed" in giveups[0]
    assert "wip=fr-8154:" in giveups[0]
    assert bored._ack_open is False


def test_shutdown_console_closed_clean_tree_no_wip(tmp_path, monkeypatch):
    said: list[str] = []

    class FakeIrc:
        shop = "#flamingo"
        alive = True

        def say(self, target, text):
            said.append(text)

        def close(self, *_a, **_k):
            pass

    monkeypatch.setenv("BOB_BRIDGE_HOME", str(tmp_path / "bridge"))
    clean = tmp_path / "clean"
    clean.mkdir()
    subprocess.run(["git", "init"], cwd=clean, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=clean,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=clean,
        check=True,
        capture_output=True,
    )
    (clean / "c.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "c.txt"], cwd=clean, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=clean,
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("BOB_JOB_WORKTREE", str(clean))

    rig = Rig(tmp_path / "run", irc=FakeIrc(), kind="grok")
    _arm_ack(rig, "FR SimonBarnett/bobiverse#8154")
    rig.sup.irc = FakeIrc()
    rig.sup.shutdown("console-closed", bw.EXIT_OK)
    giveups = [t for t in said if t.startswith("GIVEUP ")]
    assert giveups == ["GIVEUP FR SimonBarnett/bobiverse#8154 console-closed"]


def test_shutdown_idle_console_closed_posts_nothing(tmp_path, monkeypatch):
    said: list[str] = []

    class FakeIrc:
        shop = "#flamingo"
        alive = True

        def say(self, target, text):
            said.append(text)

        def close(self, *_a, **_k):
            pass

    monkeypatch.setenv("BOB_BRIDGE_HOME", str(tmp_path / "bridge"))
    rig = Rig(tmp_path / "run", irc=FakeIrc())
    bored = bw.BoredEmitter(lambda: True, rig.logs.append)
    assert bored._ack_open is False
    rig.sup.bored = bored
    rig.sup.irc = FakeIrc()
    rig.sup.machine = "flamingo"
    rig.sup.shutdown("console-closed", bw.EXIT_OK)
    assert not any(t.startswith("GIVEUP ") for t in said)
    assert bw.drain_pending_console_closed_giveups("flamingo") == []


def test_shutdown_irc_down_writes_pending(tmp_path, monkeypatch):
    class DeadIrc:
        shop = "#flamingo"
        alive = False

        def say(self, *_a, **_k):
            raise RuntimeError("down")

        def close(self, *_a, **_k):
            pass

    monkeypatch.setenv("BOB_BRIDGE_HOME", str(tmp_path / "bridge"))
    monkeypatch.delenv("BOB_JOB_WORKTREE", raising=False)
    rig = Rig(tmp_path / "run", irc=DeadIrc())
    rig.sup.machine = "flamingo"
    _arm_ack(rig, "FR owner/repo#7")
    rig.sup.irc = DeadIrc()
    rig.sup.shutdown("console-closed", bw.EXIT_OK)
    pending = bw.drain_pending_console_closed_giveups("flamingo")
    assert pending == ["GIVEUP FR owner/repo#7 console-closed"]
