"""FR #5008: DCC bulk WP2 - TLS wrap, relay, DCCLISTEN helper, offer send."""
from __future__ import annotations

import threading
import time

import airc_console as ac
import airc_dcc_bulk as dcc


def test_dcclisten_parse_tls_and_relay():
    offer = dcc.parse_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 "
        "token=0123456789abcdef0123456789abcdef tls=1 relay=10.0.0.2:4400"
    )
    assert offer is not None
    assert offer.tls is True
    assert offer.relay == "10.0.0.2:4400"
    line = dcc.format_dcclisten(offer)
    assert "tls=1" in line
    assert "relay=10.0.0.2:4400" in line
    plain = dcc.parse_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 "
        "token=0123456789abcdef0123456789abcdef tls=0"
    )
    assert plain is not None and plain.tls is False
    # Missing tls= defaults to True (FR #5008).
    defaulted = dcc.parse_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 "
        "token=0123456789abcdef0123456789abcdef"
    )
    assert defaulted is not None and defaulted.tls is True


def test_dcclisten_helper_tls_roundtrip():
    payload = b"fr5008-tls-" + b"Z" * 4096
    line, body, dig = dcc.dcclisten_helper_roundtrip(payload, tls=True, timeout_s=5.0)
    assert body == payload
    assert dig == dcc.sha256_hex(payload)
    assert "tls=1" in line
    offer = dcc.parse_dcclisten(line)
    assert offer is not None and offer.tls is True


def test_dcclisten_helper_plain_roundtrip():
    payload = b"fr5008-plain"
    line, body, dig = dcc.dcclisten_helper_roundtrip(payload, tls=False, timeout_s=5.0)
    assert body == payload
    assert "tls=0" in line
    assert dig == dcc.sha256_hex(payload)


def test_pair_relay_roundtrip():
    payload = b"relay-bulk-" + b"q" * 1024
    token = dcc.make_dcc_token()
    ready = threading.Event()
    port_box: dict = {}
    holder: dict = {}
    err: list = []

    def _relay() -> None:
        try:
            import socket

            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            port_box["port"] = int(srv.getsockname()[1])
            srv.close()
            dcc.run_pair_relay(
                host="127.0.0.1",
                port=port_box["port"],
                expect_token=token,
                timeout_s=8.0,
                ready=ready,
            )
        except BaseException as exc:  # noqa: BLE001
            err.append(("relay", exc))

    def _caller() -> None:
        ready.wait(5)
        time.sleep(0.05)
        try:
            body, dig = dcc.listen_via_relay_receive(
                relay_host="127.0.0.1",
                relay_port=port_box["port"],
                expect_token=token,
                timeout_s=8.0,
            )
            holder["body"] = body
            holder["dig"] = dig
        except BaseException as exc:  # noqa: BLE001
            err.append(("caller", exc))

    def _console() -> None:
        ready.wait(5)
        time.sleep(0.12)
        try:
            dcc.reverse_dcc_send_via_relay(
                payload,
                relay_host="127.0.0.1",
                relay_port=port_box["port"],
                token=token,
                timeout_s=8.0,
            )
        except BaseException as exc:  # noqa: BLE001
            err.append(("console", exc))

    threads = [
        threading.Thread(target=f, daemon=True) for f in (_relay, _caller, _console)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12.0)
    assert not err, err
    assert holder.get("body") == payload
    assert holder.get("dig") == dcc.sha256_hex(payload)


def test_send_offer_payload_tls():
    payload = b"offer-tls"
    token = dcc.make_dcc_token()
    ready = threading.Event()
    port_box: dict = {}
    holder: dict = {}

    def _listen() -> None:
        data, dig, port = dcc.listen_and_receive(
            host="127.0.0.1",
            port=0,
            expect_token=token,
            timeout_s=5.0,
            tls=True,
            ready=ready,
        )
        port_box["port"] = port
        holder["data"] = data
        holder["dig"] = dig

    # listen_and_receive sets ready after bind but port only returned after accept.
    # Use explicit bind pattern via helper roundtrip path — send_offer after port known.
    def _listen2() -> None:
        import socket

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port_box["port"] = int(srv.getsockname()[1])
        srv.listen(1)
        srv.settimeout(5.0)
        ctx = dcc.load_tls_server_context()
        ready.set()
        try:
            conn, _ = srv.accept()
        finally:
            srv.close()
        try:
            conn = ctx.wrap_socket(conn, server_side=True)
            conn.settimeout(5.0)
            data, dig = dcc._read_framed_bulk(conn, token)
            holder["data"] = data
            holder["dig"] = dig
        finally:
            conn.close()

    t = threading.Thread(target=_listen2, daemon=True)
    t.start()
    assert ready.wait(5)
    offer = dcc.DccListenOffer(
        job_id="aabbccdd",
        host="127.0.0.1",
        port=port_box["port"],
        token=token,
        tls=True,
        relay=None,
    )
    dcc.send_offer_payload(payload, offer, timeout_s=5.0)
    t.join(6)
    assert holder.get("data") == payload


def test_runner_note_dcclisten_tls_relay_fields():
    runner = ac.ShellJobRunner(on_reply=lambda n, line: None, wait=False)
    assert runner.note_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=1 "
        "token=0123456789abcdef0123456789abcdef tls=1 relay=127.0.0.1:9"
    )
    offer = runner.peek_dcc_offer("aabbccdd")
    assert offer.tls is True
    assert offer.relay == "127.0.0.1:9"
