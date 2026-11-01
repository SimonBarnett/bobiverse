"""FR #5654: stalled DCC receiver must not stall the shell job or change exit.

DCC send has its own bounded timeout (separate from SHELL_TIMEOUT_S). A peer that
accepts but never reads must yield ``dcc failed: ...; falling back to IRC`` and
``DONE exit=<command exit>`` with the full CONT buffer available — never exit=124
from the shell run timeout.
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import airc_console as c
import airc_dcc_bulk as dcc


def _fat_cmd(job_id: str, lines: int = 80) -> str:
    # Enough lines/bytes to cross the DCC bulk threshold without a 120s shell.
    return (
        f"id={job_id} cmd: powershell -NoProfile -Command "
        f"\"1..{lines} | % {{ 'line ' + $_ + ' ' + ('x'*80) }}\""
    )


def test_fr5654_tls_never_read_falls_back_fast_preserves_exit():
    """TLS peer handshakes then never reads app data -> IRC fallback, exit=0."""
    ready = threading.Event()
    port_box: dict = {}

    def listen_tls_never_read() -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port_box["port"] = int(srv.getsockname()[1])
        srv.listen(1)
        ready.set()
        raw, _ = srv.accept()
        try:
            conn = dcc.load_tls_server_context().wrap_socket(raw, server_side=True)
            time.sleep(30)
            try:
                conn.close()
            except OSError:
                pass
        finally:
            srv.close()

    t = threading.Thread(target=listen_tls_never_read, daemon=True)
    t.start()
    assert ready.wait(5)

    jid = "d1000015"
    token = dcc.make_dcc_token()
    offer_line = (
        f"DCCLISTEN id={jid} host=127.0.0.1 port={port_box['port']} "
        f"token={token} tls=1"
    )
    lines: list[str] = []
    done_ev = threading.Event()

    def on_reply(_key: str, text: str) -> None:
        lines.append(text)
        if text.startswith("DONE"):
            done_ev.set()

    # Shell budget deliberately larger than DCC bound so a stall would hit 124
    # if DCC were incorrectly folded into the run timeout.
    runner = c.ShellJobRunner(on_reply=on_reply, timeout_s=60.0, wait=False)
    assert runner.note_dcclisten(offer_line)
    t0 = time.monotonic()
    runner.start("tester", _fat_cmd(jid, lines=120))
    assert done_ev.wait(45), "DONE must arrive without waiting for shell timeout"
    elapsed = time.monotonic() - t0
    assert elapsed < 25.0, f"DCC stall leaked into job wall clock: {elapsed:.1f}s"
    done = [ln for ln in lines if ln.startswith("DONE")][-1]
    assert "exit=0" in done
    assert any(
        "dcc failed" in ln.lower() and "falling back to IRC" in ln for ln in lines
    ), lines


def test_fr5654_hung_send_thread_still_falls_back(monkeypatch):
    """If the DCC send thread ignores socket timeouts, runner must still bound it."""
    jid = "d10000aa"
    lines: list[str] = []
    done_ev = threading.Event()

    def on_reply(_key: str, text: str) -> None:
        lines.append(text)
        if text.startswith("DONE"):
            done_ev.set()

    def hung_send(payload, offer, *, timeout_s=3.0):  # noqa: ARG001
        time.sleep(120)

    monkeypatch.setattr(dcc, "send_offer_payload", hung_send)
    # Offer a live-looking peer so prefer_dcc engages.
    offer_line = (
        f"DCCLISTEN id={jid} host=127.0.0.1 port=1 "
        f"token={dcc.make_dcc_token()} tls=0"
    )
    runner = c.ShellJobRunner(on_reply=on_reply, timeout_s=60.0, wait=False)
    assert runner.note_dcclisten(offer_line)
    t0 = time.monotonic()
    runner.start(
        "tester",
        f"id={jid} cmd: powershell -NoProfile -Command \"1..80 | % {{ 'x'*100 }}\"",
    )
    assert done_ev.wait(30), "bounded DCC must not block DONE"
    elapsed = time.monotonic() - t0
    assert elapsed < 20.0, f"hung DCC send was not bounded: {elapsed:.1f}s"
    assert any(ln.startswith("DONE") and "exit=0" in ln for ln in lines)
    assert any(
        "dcc failed" in ln.lower() and "falling back to IRC" in ln for ln in lines
    )


def test_fr5654_settimeout_before_tls_wrap():
    """Portable: raw socket timeout must be set before wrap_socket (FR #5654)."""
    src = Path(dcc.__file__).read_text(encoding="utf-8")
    assert "FR #5654" in src
    # reverse_dcc_send: settimeout on raw before wrap_socket
    send_fn = src.split("def reverse_dcc_send(", 1)[1].split("\ndef listen_and_receive", 1)[0]
    wrap_i = send_fn.find("wrap_socket")
    pre_i = send_fn.find("raw.settimeout")
    assert pre_i != -1 and wrap_i != -1 and pre_i < wrap_i


def test_fr5654_docs_mention_send_timeout():
    docs = Path(__file__).resolve().parents[1] / "docs" / "airc-remote-control.md"
    text = docs.read_text(encoding="utf-8")
    assert "FR #5654" in text
    assert "send timeout" in text.lower() or "bounded" in text.lower()
