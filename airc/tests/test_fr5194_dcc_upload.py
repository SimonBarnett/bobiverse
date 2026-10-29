"""FR #5194: authenticated caller-to-console DCC uploads."""
from __future__ import annotations

import hashlib
import json
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import airc_dcc_bulk as dcc
import airc_jobs as jobs


def _dccput(offer: dcc.DccListenOffer, path: str, payload: bytes) -> dict[str, str]:
    return {
        "id": offer.job_id,
        "path": path,
        "bytes": str(len(payload)),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "host": offer.host,
        "port": str(offer.port),
        "token": offer.token,
        "tls": "1" if offer.tls else "0",
        **({"relay": offer.relay} if offer.relay else {}),
    }


def test_dcc_upload_tls_roundtrip_and_atomic_commit(tmp_path):
    payload = b"caller-upload-" + b"x" * 4096
    token = dcc.make_dcc_token()
    ready = threading.Event()
    offer_box: dict[str, dcc.DccListenOffer] = {}
    errors: list[BaseException] = []

    def sender() -> None:
        try:
            def publish(port: int) -> None:
                offer_box["offer"] = dcc.DccListenOffer(
                    job_id="aabbccdd",
                    host="127.0.0.1",
                    port=port,
                    token=token,
                )
                ready.set()

            dcc.listen_and_send(
                payload, token=token, on_listening=publish, host="127.0.0.1",
                timeout_s=5.0,
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=sender, daemon=True)
    thread.start()
    assert ready.wait(5)

    store = jobs.JobStore(tmp_path / "console")
    proto = jobs.JobProtocol(store)
    offer = offer_box["offer"]
    lines = proto.handle("bob-tm", "DCCPUT", _dccput(offer, "incoming.bin", payload))
    thread.join(6)

    digest = hashlib.sha256(payload).hexdigest()
    assert not errors, errors
    assert lines == [f"DONE id=aabbccdd exit=0 bytes={len(payload)} sha256={digest} via=dcc"]
    dest = store.drop_root / "incoming.bin"
    assert dest.read_bytes() == payload
    assert store._payload_path("aabbccdd").read_bytes() == payload
    assert store.get("aabbccdd").state == "ready"
    assert not list(store.drop_root.glob("*.tmp"))


def test_caller_helper_uploads_to_console(tmp_path):
    root = Path(__file__).resolve().parents[2]
    script_dir = root / "airc" / "scripts"
    local_file = tmp_path / "source.bin"
    payload = b"helper-upload-" + b"y" * 2048
    local_file.write_bytes(payload)
    offer_path = tmp_path / "offer.json"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(script_dir / "airc_dcc_upload.py"),
            "--file",
            str(local_file),
            "--offer-file",
            str(offer_path),
            "--advertise-host",
            "127.0.0.1",
            "--timeout",
            "5",
        ],
        cwd=script_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not offer_path.is_file():
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        assert offer_path.is_file(), proc.stderr.read() if proc.poll() is not None else "no offer"
        data = json.loads(offer_path.read_text(encoding="utf-8"))
        offer = dcc.DccListenOffer(
            job_id="eef00112",
            host=data["host"],
            port=int(data["port"]),
            token=data["token"],
            tls=bool(data["tls"]),
        )
        lines = jobs.JobProtocol(jobs.JobStore(tmp_path / "console")).handle(
            "bob-tm", "DCCPUT", _dccput(offer, "helper.bin", payload)
        )
        _stdout, stderr = proc.communicate(timeout=6)
        assert proc.returncode == 0, stderr
        assert lines[-1].endswith("via=dcc")
        assert (tmp_path / "console" / "drop" / "helper.bin").read_bytes() == payload
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)


def test_dcc_upload_relay_roundtrip(tmp_path):
    payload = b"relay-upload-" + b"z" * 2048
    token = dcc.make_dcc_token()
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    relay_port = int(probe.getsockname()[1])
    probe.close()
    ready = threading.Event()
    errors: list[BaseException] = []

    def relay() -> None:
        try:
            dcc.run_pair_relay(
                host="127.0.0.1",
                port=relay_port,
                expect_token=token,
                timeout_s=6,
                ready=ready,
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=relay, daemon=True)
    thread.start()
    assert ready.wait(3)

    def send() -> None:
        try:
            dcc.reverse_dcc_send_via_relay(
                payload,
                relay_host="127.0.0.1",
                relay_port=relay_port,
                token=token,
                timeout_s=6,
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    sender = threading.Thread(target=send, daemon=True)
    sender.start()
    offer = dcc.DccListenOffer(
        job_id="f0011223",
        host="127.0.0.1",
        port=1,
        token=token,
        relay=f"127.0.0.1:{relay_port}",
    )
    lines = jobs.JobProtocol(jobs.JobStore(tmp_path / "console")).handle(
        "bob-tm", "DCCPUT", _dccput(offer, "relay.bin", payload)
    )
    sender.join(6)
    thread.join(6)

    assert not errors, errors
    assert lines[-1].endswith("via=dcc")
    assert (tmp_path / "console" / "drop" / "relay.bin").read_bytes() == payload


def test_corrupt_or_partial_dcc_upload_leaves_no_file(tmp_path):
    for mode in ("corrupt", "partial"):
        store = jobs.JobStore(tmp_path / mode)
        payload = b"received body"
        token = dcc.make_dcc_token()
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(4)
        port = int(srv.getsockname()[1])
        errors: list[BaseException] = []

        def sender() -> None:
            try:
                conn, _ = srv.accept()
                with conn:
                    body = payload[:3] if mode == "partial" else payload
                    declared = len(payload)
                    conn.sendall(token.encode("ascii") + b"\n" + struct.pack(">I", declared))
                    conn.sendall(body)
                    if mode == "corrupt":
                        conn.sendall(b"0" * 64 + b"\n")
                    conn.shutdown(socket.SHUT_WR)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                srv.close()

        thread = threading.Thread(target=sender, daemon=True)
        thread.start()
        offer = dcc.DccListenOffer(
            job_id="bbccddee", host="127.0.0.1", port=port, token=token, tls=False
        )
        lines = jobs.JobProtocol(store).handle(
            "bob-tm", "DCCPUT", _dccput(offer, "incoming.bin", payload)
        )
        thread.join(5)

        dest = store.drop_root / "incoming.bin"
        assert not dest.exists(), (mode, lines)
        assert not list(store.drop_root.rglob("*.tmp"))
        record = store.get("bbccddee")
        assert record is not None and record.state == "failed"
        assert lines[-1] == "DONE id=bbccddee exit=1 via=dcc reason=dcc"


def test_blocked_dcc_falls_back_to_existing_irc_put(tmp_path):
    store = jobs.JobStore(tmp_path / "console")
    proto = jobs.JobProtocol(store)
    payload = b"fallback-over-irc"
    token = dcc.make_dcc_token()
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    closed_port = int(probe.getsockname()[1])
    probe.close()
    offer = dcc.DccListenOffer(
        job_id="ccddeeff",
        host="127.0.0.1",
        port=closed_port,
        token=token,
        tls=False,
    )

    failed = proto.handle("bob-tm", "DCCPUT", _dccput(offer, "fallback.bin", payload))
    assert failed[-1] == "DONE id=ccddeeff exit=1 via=dcc reason=dcc"

    import base64

    digest = hashlib.sha256(payload).hexdigest()
    proto.handle(
        "bob-tm",
        "PUT",
        {"id": offer.job_id, "path": "fallback.bin", "bytes": str(len(payload)), "sha256": digest},
    )
    proto.handle(
        "bob-tm",
        "CHUNK",
        {
            "id": offer.job_id,
            "seq": "1",
            "data": base64.b64encode(payload).decode("ascii"),
        },
    )
    completed = proto.handle(
        "bob-tm", "PUTEND", {"id": offer.job_id, "seqs": "1", "sha256": digest}
    )
    assert completed[-1] == (
        f"DONE id={offer.job_id} exit=0 bytes={len(payload)} sha256={digest} via=irc"
    )
    assert (store.drop_root / "fallback.bin").read_bytes() == payload


def test_dccput_uses_put_write_auth_and_sandbox(tmp_path):
    store = jobs.JobStore(tmp_path / "console")
    proto = jobs.JobProtocol(
        store, verb_auth=jobs.VerbAuthPolicy(write_nicks={"bob-tm"})
    )
    offer = dcc.DccListenOffer(
        job_id="ddeeff00", host="127.0.0.1", port=1, token="a" * 32, tls=False
    )
    payload = b"x"

    denied = proto.handle("bob-other", "DCCPUT", _dccput(offer, "file.bin", payload))
    assert "denied" in denied[0]
    assert denied[-1] == "DONE id=ddeeff00 exit=1 via=dcc reason=denied"

    traversal = proto.handle(
        "bob-tm", "DCCPUT", _dccput(offer, "../outside.bin", payload)
    )
    assert "traversal" in traversal[0]
    assert not (tmp_path / "outside.bin").exists()

    secret = proto.handle(
        "bob-tm", "DCCPUT", _dccput(offer, "console.password", payload)
    )
    assert "secret" in secret[0]


def test_dccput_frame_and_invoke_default_with_irc_override():
    parsed = jobs.parse_job_verb(
        "id=ddeeff00 DCCPUT path=upload.bin bytes=1 sha256="
        + hashlib.sha256(b"x").hexdigest()
        + " host=127.0.0.1 port=9 token="
        + "a" * 32
        + " tls=1"
    )
    assert parsed is not None and parsed[0] == "DCCPUT"
    assert parsed[1]["id"] == "ddeeff00"

    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    script = (root / "airc" / "scripts" / "Invoke-AircRemote.ps1").read_text(
        encoding="utf-8"
    )
    assert "[switch]$ForceIrc" in script
    assert "DCCPUT id=" in script
    assert "-not $ForceIrc" in script
    assert "$built.Put.Lines" in script
    assert "upload path=dcc" in script and "upload path=irc" in script


def test_upload_docs_cover_dcc_output_and_upload():
    root = Path(__file__).resolve().parents[2]
    docs = (root / "airc" / "docs" / "airc-remote-control.md").read_text(
        encoding="utf-8"
    ).lower()
    skill = (
        root / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
    ).read_text(encoding="utf-8").lower()
    for content in (docs, skill):
        assert "dcc" in content and "upload" in content and "output" in content
        assert "fallback" in content
