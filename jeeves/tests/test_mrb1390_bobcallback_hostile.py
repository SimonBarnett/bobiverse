"""Hostile MRB #1390 / FR #1388: foreign lock break must not hit fresh holders."""
from __future__ import annotations

import os
import time
from pathlib import Path

import bobreport
import registered_machines as rm


def test_fresh_foreign_live_lock_is_kept(tmp_path, monkeypatch):
    """Under BOB_DIGEST_LOCK_FOREIGN_S, a live foreign holder younger than the threshold stays."""
    home = tmp_path
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare"])
    bobreport.save_digest(home, bobreport.empty_digest())
    monkeypatch.setenv("BOB_DIGEST_LOCK_STALE_S", "60")
    monkeypatch.setenv("BOB_DIGEST_LOCK_FOREIGN_S", "12")
    foreign_pid = os.getpid() + 424242
    monkeypatch.setattr(bobreport, "_pid_alive", lambda pid: int(pid) == foreign_pid)
    lock = bobreport.digest_lock_path(home)
    lock.write_text(f"{foreign_pid}\n{time.time():.3f}\n", encoding="utf-8")
    old = time.time() - 3  # younger than foreign threshold
    os.utime(lock, (old, old))
    info = bobreport.break_stale_digest_lock(home)
    assert info is None, f"must not break fresh foreign lock: {info}"
    assert lock.exists()
    assert bobreport.digest_lock_holder_pid(home) == foreign_pid


def test_serve_source_binds_before_drain_call():
    """Static order check: ThreadingHTTPServer constructed before drain thread start."""
    src = (Path(__file__).resolve().parents[2] / "common" / "scripts" / "bobcallback.py").read_text(
        encoding="utf-8"
    )
    i_http = src.find("ThreadingHTTPServer(")
    i_drain_thread = src.find('name="bobcallback-drain"')
    i_sync_drain = src.find("drain_pending(home, briefer_nick=briefer_nick, filer=use_filer)")
    assert i_http > 0
    assert i_drain_thread > i_http
    # The only remaining drain_pending call in serve() should be inside _bg_drain, after bind.
    # Ensure there is no pre-bind synchronous drain_pending left in serve().
    serve_start = src.find("def serve(")
    serve_body = src[serve_start : src.find("\ndef assert_home_usable", serve_start)]
    # Synchronous drain before httpd = ThreadingHTTPServer must be gone.
    pre = serve_body.split("ThreadingHTTPServer(")[0]
    assert "drain_pending(" not in pre
