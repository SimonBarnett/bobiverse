"""FR #5194: caller-to-console DCC upload, sha256, atomic write, IRC fallback."""
from __future__ import annotations

import hashlib
from pathlib import Path

import airc_dcc_bulk as dcc
import airc_jobs as jobs


def test_dcc_upload_roundtrip_sha256():
    payload = b"fr5194-upload-body\n" * 20
    got = dcc.upload_roundtrip_localhost(payload, timeout_s=3.0)
    assert got == payload
    assert dcc.sha256_hex(got) == hashlib.sha256(payload).hexdigest()


def test_corrupt_transfer_leaves_no_file(tmp_path):
    dest = tmp_path / "drop" / "out.bin"
    blob = b"good-bytes"
    bad_sha = "0" * 64
    try:
        jobs.atomic_place_file(dest, blob, bad_sha)
        raise AssertionError("corrupt sha should reject")
    except jobs.JobProtocolError as exc:
        assert exc.code == "checksum"
    assert not dest.exists()
    tmp = dest.with_name(dest.name + ".airc-put.tmp")
    assert not tmp.exists()


def test_dcc_blocked_falls_back_to_irc_put(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store)

    def boom(_jid: str):
        raise OSError("timed out")

    proto.dcc_receive = boom
    payload = b"fallback-payload"
    digest = hashlib.sha256(payload).hexdigest()
    put = proto.handle(
        "bob-tm",
        "PUT",
        {
            "id": "aabbccdd",
            "path": "file.bin",
            "bytes": str(len(payload)),
            "sha256": digest,
            "via": "dcc",
        },
    )
    assert any("falling back to IRC" in ln for ln in put)
    assert any(ln.startswith("ok id=aabbccdd put ") for ln in put)
    proto.handle(
        "bob-tm",
        "CHUNK",
        {"id": "aabbccdd", "seq": "1", "data": __import__("base64").b64encode(payload).decode("ascii")},
    )
    end = proto.handle(
        "bob-tm", "PUTEND", {"id": "aabbccdd", "seqs": "1", "sha256": digest}
    )
    assert any("putend" in ln and digest in ln for ln in end)
    dest = tmp_path / "drop" / "file.bin"
    assert dest.read_bytes() == payload


def test_put_path_checks_match_dcc_and_irc(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store)
    trav = proto.handle("bob-tm", "PUT", {"path": "..\\secret.bin", "via": "dcc"})
    assert any("code=traversal" in ln for ln in trav)
    secret = proto.handle("bob-tm", "PUT", {"path": "console.password", "via": "dcc"})
    assert any("code=secret_path" in ln for ln in secret)
    ok = proto.handle("bob-tm", "PUT", {"path": "ok.bin", "bytes": "0", "sha256": hashlib.sha256(b"").hexdigest()})
    assert any(ln.startswith("ok id=") for ln in ok)


def test_dcc_put_installs_via_receive(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store)
    payload = b"via-dcc-ok"
    digest = hashlib.sha256(payload).hexdigest()

    def recv(_jid: str):
        return payload, digest

    proto.dcc_receive = recv
    lines = proto.handle(
        "bob-tm",
        "PUT",
        {
            "id": "11223344",
            "path": "ok.bin",
            "bytes": str(len(payload)),
            "sha256": digest,
            "via": "dcc",
        },
    )
    assert any("via=dcc" in ln and digest in ln for ln in lines)
    dest = tmp_path / "drop" / "ok.bin"
    assert dest.read_bytes() == payload
    extra = proto.handle("bob-tm", "CHUNK", {"id": "11223344", "seq": "1", "data": "YQ=="})
    assert any("already=1" in ln for ln in extra)


def test_skill_documents_dcc_output_and_upload():
    skill = (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-airc-commands"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "DCCLISTEN" in skill
    assert "via=dcc" in skill
    assert "FR #5194" in skill
    assert "falling back to IRC" in skill
    assert "PUT path=" in skill
