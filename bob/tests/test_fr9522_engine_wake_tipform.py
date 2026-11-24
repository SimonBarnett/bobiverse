"""FR #9522: TipForm consumes engine.wake -> ReloadEngine; NACK distinguishes wake pending vs tip lag."""
from __future__ import annotations

import os
import time
from pathlib import Path

import startworker as sw

from repo_layout import ROOT

CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
DOCS = ROOT / "bob" / "docs" / "bob-tray-dialogs.md"
MON = ROOT / "jeeves" / "docs" / "monitoring.md"
PS = ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1"


def _fresh_tray(q: Path) -> None:
    q.mkdir(parents=True, exist_ok=True)
    (q / sw.ALIVE_FILE).write_text("tray", encoding="ascii")
    now = time.time()
    os.utime(q / sw.ALIVE_FILE, (now, now))


def test_fr9522_cs_takewake_beside_takereload():
    t = CS.read_text(encoding="utf-8-sig")
    assert "TakeWake" in t
    assert "engine.wake" in t or "ENGINE_WAKE" in t or 'engine.wake"' in t
    assert "--consume-wake" in t
    # Reload() must OR TakeWake with TakeReload before one ReloadEngine call.
    i = t.index("void Reload()")
    window = t[i : i + 900]
    assert "TakeWake" in window
    assert "TakeReload" in window
    assert "ReloadEngine()" in window
    take = t[t.index("public static bool TakeWake") : t.index("public static bool TakeWake") + 700]
    assert "File.Delete" in take or "Delete(" in take


def test_fr9522_decide_wake_requested_vs_pending(tmp_path):
    run = tmp_path / "run"
    q = run / "startworker"
    q.mkdir(parents=True, exist_ok=True)
    now = 1_800_000_000.0
    (q / sw.ALIVE_FILE).write_text("tray", encoding="ascii")
    os.utime(q / sw.ALIVE_FILE, (now, now))  # tray fresh vs synthetic now; no engine.alive
    d1 = sw.decide(
        body="!startworker agent marchhare",
        nick="Bob-redqueen",
        account="bob-redqueen",
        channel="#bobiverse",
        local_machine="marchhare",
        gate=sw.StartGate(2, 0),
        qdir=q,
        machine_of_nick=lambda n: "redqueen" if "redqueen" in (n or "").lower() else None,
        write=True,
        now=now,
    )
    assert d1 is not None and d1.reason == "engine_stale"
    assert "wake requested" in d1.line.lower()
    # Second call within rate limit: wake pending (host tip lag hint).
    d2 = sw.decide(
        body="!startworker agent marchhare",
        nick="Bob-redqueen",
        account="bob-redqueen",
        channel="#bobiverse",
        local_machine="marchhare",
        gate=sw.StartGate(2, 0),
        qdir=q,
        machine_of_nick=lambda n: "redqueen" if "redqueen" in (n or "").lower() else None,
        write=True,
        now=now + 10.0,
    )
    assert d2 is not None and d2.reason == "engine_stale"
    assert "wake pending" in d2.line.lower()
    assert "tip" in d2.line.lower() or "recycle" in d2.line.lower() or "host" in d2.line.lower()


def test_fr9522_docs_merge_ne_host_heal():
    d = DOCS.read_text(encoding="utf-8")
    assert "9522" in d or "engine.wake" in d
    assert "Reload" in d or "reload" in d
    # Merge closing an FR does not heal the live host.
    blob = (d + "\n" + MON.read_text(encoding="utf-8")).lower()
    assert "merge" in blob and ("host" in blob or "tip" in blob)
    assert "engine.wake" in blob or "takewake" in blob.lower()
    ps = PS.read_text(encoding="utf-8-sig")
    assert "9522" in ps or "TakeWake" in ps or "consumes" in ps.lower()
