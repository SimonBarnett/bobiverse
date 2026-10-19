"""FR #4795: outbound file fetch is pull-chunked, not a PRIVMSG base64 dump."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import airc_jobs as jobs


def test_plain_get_stays_a_single_head_line(tmp_path: Path):
    home = tmp_path / "home"
    store = jobs.JobStore(home)
    blob = b"A" * 900
    dest = store.drop_root / "report.bin"
    dest.write_bytes(blob)
    proto = jobs.JobProtocol(store)
    lines = proto.handle("bob-tm", "GET", {"path": "report.bin"})
    assert len(lines) == 1
    assert "head=" in lines[0]
    assert "data=" not in lines[0]
    assert blob.decode() not in lines[0]


def test_fetch_chunk_metadata_then_one_chunk_per_pull(tmp_path: Path):
    home = tmp_path / "home"
    store = jobs.JobStore(home)
    blob = bytes(range(256)) * 4  # 1024 bytes, several IRC chunks
    (store.drop_root / "sheet.bin").write_bytes(blob)
    proto = jobs.JobProtocol(store)
    start = proto.handle("bob-tm", "GET", {"path": "sheet.bin", "fetch": "chunk"})
    assert len(start) == 1, start
    line = start[0]
    assert line.startswith("ok id=")
    assert "data=" not in line
    assert f"bytes={len(blob)}" in line
    assert f"sha256={hashlib.sha256(blob).hexdigest()}" in line
    assert "seqs=" in line
    jid = line.split()[1].split("=", 1)[1]
    seqs = int(line.split("seqs=", 1)[1].split()[0])
    assert seqs > 1
    parts = []
    for seq in range(1, seqs + 1):
        got = proto.handle("bob-tm", "GETCHUNK", {"id": jid, "seq": str(seq)})
        assert len(got) == 1, got
        assert f"seq={seq}" in got[0]
        b64 = got[0].split("data=", 1)[1]
        raw = base64.b64decode(b64, validate=True)
        assert 1 <= len(raw) <= jobs.MAX_CHUNK_RAW
        parts.append(raw)
        # duplicate pull is the same chunk, still one line
        again = proto.handle("bob-tm", "GETCHUNK", {"id": jid, "seq": str(seq)})
        assert again == got
    assert b"".join(parts) == blob


def test_getchunk_does_not_send_the_next_seq(tmp_path: Path):
    home = tmp_path / "home"
    store = jobs.JobStore(home)
    (store.drop_root / "a.bin").write_bytes(b"xyz" * 200)
    proto = jobs.JobProtocol(store)
    start = proto.handle("op", "GET", {"path": "a.bin", "fetch": "chunk"})
    jid = start[0].split()[1].split("=", 1)[1]
    one = proto.handle("op", "GETCHUNK", {"id": jid, "seq": "1"})
    assert len(one) == 1
    assert "seq=2" not in one[0]


def test_fetch_rejects_secret_and_missing(tmp_path: Path):
    home = tmp_path / "home"
    store = jobs.JobStore(home)
    (store.drop_root / "console.password").write_text("not-a-real-secret\n", encoding="ascii")
    proto = jobs.JobProtocol(store)
    secret = proto.handle("op", "GET", {"path": "console.password", "fetch": "chunk"})
    assert secret[0].startswith("err ")
    assert "secret_path" in secret[0]
    missing = proto.handle("op", "GET", {"path": "nope.bin", "fetch": "chunk"})
    assert "missing" in missing[0]


def test_parse_getchunk_verb():
    parsed = jobs.parse_job_verb("GETCHUNK id=abcd1234 seq=2")
    assert parsed is not None
    verb, kv = parsed
    assert verb == "GETCHUNK"
    assert kv["id"] == "abcd1234"
    assert kv["seq"] == "2"
