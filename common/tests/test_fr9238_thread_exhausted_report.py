# -*- coding: utf-8 -*-
"""FR #9238: report must soft-degrade when Thread.start fails (can't start new thread)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest import mock

import bobcallback
import bobreport


def test_fr9238_digest_lock_skips_heartbeat_on_thread_exhausted(tmp_path: Path, capsys):
    """Holding digest.lock must succeed even when heartbeat Thread.start fails."""
    real_thread = threading.Thread

    def boom(*args, **kwargs):
        raise RuntimeError("can't start new thread")

    with mock.patch("bobreport.threading.Thread", side_effect=boom):
        with bobreport.digest_lock(tmp_path):
            (tmp_path / "under-lock.txt").write_text("ok\n", encoding="utf-8")
    assert (tmp_path / "under-lock.txt").read_text(encoding="utf-8") == "ok\n"
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "digest-lock-heartbeat skipped" in out or "thread exhausted" in out.lower()
    # Real Thread still usable after patch ends.
    assert real_thread is threading.Thread


def test_fr9238_handle_report_runtimeerror_thread_exhausted_is_503(tmp_path: Path):
    """Escaped RuntimeError from apply_callback maps to 503 without 500 intake."""
    home = tmp_path
    payload = {
        "op": "merge",
        "machine": "flamingo",
        "online": True,
    }
    body = json.dumps(payload).encode("utf-8")

    def raise_thread(_home, _payload, _briefer=""):
        raise RuntimeError("can't start new thread")

    with mock.patch.object(bobreport, "is_roster_machine", return_value=True):
        with mock.patch.object(bobreport, "apply_callback", side_effect=raise_thread):
            code, out = bobcallback.handle_report_post(
                {"content-type": "application/json"},
                body,
                home,
                rate=None,
                filer=None,
            )
    assert code == 503
    assert b"thread_exhausted" in out


def test_fr9238_http_server_process_request_swallows_thread_exhausted():
    from http.server import BaseHTTPRequestHandler

    class _H(BaseHTTPRequestHandler):
        def log_message(self, *a, **k):
            return

    # Build the subclass the same way serve() does.
    from http.server import ThreadingHTTPServer

    class _BobCallbackHTTPServer(ThreadingHTTPServer):
        def process_request(self, request, client_address):
            try:
                return super().process_request(request, client_address)
            except RuntimeError as exc:
                msg = str(exc).lower()
                if "can't start new thread" in msg or "start new thread" in msg:
                    with __import__("contextlib").suppress(Exception):
                        request.close()
                    return
                raise

    srv = _BobCallbackHTTPServer.__new__(_BobCallbackHTTPServer)
    closed = {"n": 0}

    class _Req:
        def close(self):
            closed["n"] += 1

    def boom_super(self, request, client_address):
        raise RuntimeError("can't start new thread")

    with mock.patch.object(ThreadingHTTPServer, "process_request", boom_super):
        _BobCallbackHTTPServer.process_request(srv, _Req(), ("127.0.0.1", 9))
    assert closed["n"] == 1


def test_fr9238_source_pins():
    text = Path(bobreport.__file__).read_text(encoding="utf-8")
    assert "digest-lock-heartbeat skipped" in text
    assert "FR #9238" in text
    cb = Path(bobcallback.__file__).read_text(encoding="utf-8")
    assert "thread_exhausted" in cb
    assert "_BobCallbackHTTPServer" in cb
    assert "FR #9238" in cb
