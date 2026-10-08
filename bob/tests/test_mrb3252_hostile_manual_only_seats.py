# -*- coding: utf-8 -*-
"""MRB #3252 hostile gates for FR #3180 manual-only worker seat starts.

Pins product acceptance after merge of PR #3252:
- Watchdog never launches seats (ObserveWorkerSeats only).
- SeatHealEnabled is always false.
- Ensure-BobWorkerSeats never queues req-*.json.
- Idle stale-build announces once, skips !bored, never EXIT_STALE_BUILD.
- Skill/docs say manual only and do not promise seat-heal relaunch.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import bob_worker as bw
from repo_layout import ROOT

BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobWorkerSeats.ps1"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
POST = ROOT / "common" / "docs" / "post-install.md"
WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _watchdog_body(src: str) -> str:
    i = src.find("void Watchdog()")
    assert i >= 0
    rest = src[i:]
    # Prefer public Watchdog used by --watchdog-ticks harness.
    if "public void Watchdog()" in src:
        i = src.find("public void Watchdog()")
        rest = src[i:]
    nxt = rest.find("\n        void ", 1)
    if nxt < 0:
        nxt = rest.find("\n        public void ", 1)
    return rest if nxt < 0 else rest[:nxt]


def test_mrb3252_watchdog_observe_never_launch():
    t = _read(BOB_TRAY)
    wd = _watchdog_body(t)
    assert "HealEngine()" in wd or "noEngine" in wd
    assert "ObserveWorkerSeats" in wd
    assert "HealWorkerSeats" not in wd
    assert "WorkerLauncher.Launch" not in wd
    assert "void HealWorkerSeats" not in t
    assert 'Launch(root, "agent"' not in t or "LaunchCalls" in t  # Launch exists for Agent click only


def test_mrb3252_seat_heal_enabled_always_false():
    t = _read(BOB_TRAY)
    i = t.find("SeatHealEnabled")
    assert i >= 0
    body = t[i : t.find("}", i) + 1]
    assert "return false" in body.replace(" ", "") or "returnfalse" in body.replace(" ", "").lower()
    assert "return true" not in body.replace(" ", "")


def test_mrb3252_ensure_never_writes_req():
    ens = _read(ENSURE)
    assert "FR #3180" in ens
    assert "report-only" in ens.lower() or "manual only" in ens.lower()
    assert "queued startworker" not in ens
    assert "kind" not in ens or "seat-heal" not in ens.split("report-only")[-1]
    # No write of req-*.json
    assert "req-{0}.json" not in ens and "req-$" not in ens
    assert "Move-Item" not in ens


def test_mrb3252_stale_announce_idempotent_no_exit(tmp_path):
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

    logs: list = []
    relay = bw.Relay(logs.append, persist_dir=tmp_path)
    irc = _Irc()
    sup = bw.Supervisor(
        kind="grok",
        exe=r"C:\x\agent.exe",
        cwd=str(tmp_path),
        machine="marchhare",
        nick="marchhare-9999",
        run_dir=tmp_path,
        irc=irc,
        relay=relay,
        log=logs.append,
        bored=None,
    )
    sup.stale_build_check = lambda: "run=deadbeefcafe install=cafebabedead"
    assert sup.post_bored() is False
    assert ("#marchhare", "!bored") not in irc.said
    notices = [s for s in irc.said if "stale build" in str(s).lower()]
    assert len(notices) == 1
    assert sup.post_bored() is False
    notices2 = [s for s in irc.said if "stale build" in str(s).lower()]
    assert len(notices2) == 1, "second idle tick must not re-spam the shop"
    assert getattr(sup, "exit_code", None) != bw.EXIT_STALE_BUILD
    assert not getattr(sup, "done", None) or not sup.done.is_set()


def test_mrb3252_heal_env_no_longer_gates_stale_detect(tmp_path):
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "worker" / "bob-worker.exe").write_bytes(b"install-new")
    run = tmp_path / "bob-worker-aaaaaaaaaaaa.exe"
    run.write_bytes(b"run-old")
    import time

    os.utime(root / "worker" / "bob-worker.exe", (time.time() - 120, time.time() - 120))
    why = bw.stale_build_reason(
        run,
        root,
        env={"BOBIVERSE_WORKER_SEAT_HEAL": "0", "BOB_WORKER_STALE_BUILD_RECYCLE": "1"},
    )
    assert why and "run=" in why and "install=" in why


def test_mrb3252_docs_manual_only_no_heal_promise():
    skill = _read(SKILL)
    post = _read(POST)
    blob = skill + "\n" + post
    assert "FR #3180" in blob
    assert re.search(r"manual only|manual-only", blob, re.I)
    assert "HealWorkerSeats" not in skill
    assert "tops agent seats back up" not in post.lower()
    assert "seat-heal relaunch" not in skill.lower()
    # Watchdog may observe, never auto-launch
    assert "not restarted" in blob or "ObserveWorkerSeats" in _read(BOB_TRAY)
