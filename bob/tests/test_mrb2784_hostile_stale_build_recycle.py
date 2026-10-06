"""MRB #2784 hostile: idle stale-build recycle (FR #2782)."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import bob_worker as bw

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
PRODUCT = ROOT / "bob" / "tests" / "test_fr2782_stale_build_recycle.py"


def test_mrb2784_skill_bullet_and_product_suite():
    text = SKILL.read_text(encoding="utf-8")
    assert "Stale build recycle (FR #2782)" in text
    assert "EXIT" in text or "exits `8`" in text or "exits 8" in text or "!bored" in text
    assert "BOB_WORKER_STALE_BUILD_RECYCLE=0" in text
    assert PRODUCT.is_file()
    assert "test_idle_stale_seat_recycles_instead_of_bored" in PRODUCT.read_text(encoding="utf-8")


def test_mrb2784_exit_code_and_helper_exist():
    assert bw.EXIT_STALE_BUILD == 8
    assert callable(bw.stale_build_reason)


def test_mrb2784_stale_differs_same_and_opt_out(tmp_path):
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    exe = root / "worker" / "bob-worker.exe"
    payload = b"hostile-new-build"
    exe.write_bytes(payload)
    old = time.time() - 3600
    os.utime(exe, (old, old))
    digest = hashlib.sha256(payload).hexdigest()[:12]
    why = bw.stale_build_reason(r"C:\x\bob-worker-d409556250b4.exe", root, env={})
    assert why == f"run=d409556250b4 install={digest}"
    assert bw.stale_build_reason(rf"C:\x\bob-worker-{digest}.exe", root, env={}) is None
    assert bw.stale_build_reason(r"C:\x\bob-worker-d409556250b4.exe", root, env={"BOB_WORKER_STALE_BUILD_RECYCLE": "0"}) is None
    assert bw.stale_build_reason(r"C:\x\bob-worker-d409556250b4.exe", root, env={"BOBIVERSE_WORKER_SEAT_HEAL": "0"}) is None


def test_mrb2784_post_bored_recycles_not_bored(tmp_path):
    class _Irc:
        def __init__(self):
            self.alive = True
            self.shop = "#marchhare"
            self.said = []

        def say(self, target, text):
            self.said.append((target, text))
            return True

        def close(self, why=""):
            self.alive = False

    logs = []
    relay = bw.Relay(logs.append, persist_dir=tmp_path)
    irc = _Irc()
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-4242",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=logs.append,
        bored=None,
    )
    sup.stale_build_check = lambda: "run=old install=new"
    assert sup.post_bored() is False
    assert ("#marchhare", "!bored") not in irc.said
    assert sup.done.wait(5.0)
    assert sup.exit_code == bw.EXIT_STALE_BUILD
