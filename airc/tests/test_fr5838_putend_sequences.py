"""FR #5838: explicit PUTEND errors and recoverable missing IRC chunks."""
import base64
import hashlib
import threading

import pytest

import airc_jobs as jobs
from repo_layout import ROOT


@pytest.fixture
def upload(tmp_path):
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store)
    dest = store.drop_root / "file.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"old file")
    data = b"abcdef"
    proto.handle("operator", "PUT", {
        "id": "aabbccdd", "path": "file.bin", "bytes": str(len(data)),
        "sha256": hashlib.sha256(data).hexdigest(),
    })
    return proto, store, dest, data


def send_chunk(proto, seq, data):
    return proto.handle("operator", "CHUNK", {
        "id": "aabbccdd", "seq": str(seq),
        "data": base64.b64encode(data).decode("ascii"),
    })


@pytest.mark.parametrize("seqs", [None, "", " "])
def test_missing_count_is_one_named_error_and_retry_succeeds(upload, seqs):
    proto, store, dest, data = upload
    send_chunk(proto, 1, data)
    kv = {"id": "aabbccdd"}
    if seqs is not None:
        kv["seqs"] = seqs
    lines = proto.handle("operator", "PUTEND", kv)
    assert len(lines) == 1
    assert lines[0].startswith("err id=aabbccdd code=put-seqs-required ")
    assert dest.read_bytes() == b"old file"
    assert store.get("aabbccdd").state == "receiving"
    assert "putend bytes=6" in proto.handle("operator", "PUTEND", {
        "id": "aabbccdd", "seqs": "1",
    })[0]
    assert dest.read_bytes() == data


@pytest.mark.parametrize("seqs", ["-1", "nope", str(jobs.MAX_PUT_BYTES + 1)])
def test_invalid_count_does_not_replace_file(upload, seqs):
    proto, store, dest, _ = upload
    lines = proto.handle("operator", "PUTEND", {"id": "aabbccdd", "seqs": seqs})
    assert len(lines) == 1 and "code=bad_frame" in lines[0]
    assert dest.read_bytes() == b"old file"
    assert store.get("aabbccdd").state == "receiving"


def test_missing_middle_and_last_chunks_can_be_resent(upload):
    proto, store, dest, data = upload
    send_chunk(proto, 3, data[4:])
    for want, resend in [("1,2", 1), ("2", 2)]:
        lines = proto.handle("operator", "PUTEND", {"id": "aabbccdd", "seqs": "3"})
        assert len(lines) == 1 and "code=order" in lines[0]
        assert f"missing={want} missing_more=0 unexpected=0" in lines[0]
        assert dest.read_bytes() == b"old file"
        send_chunk(proto, resend, data[(resend - 1) * 2:resend * 2])
    assert "putend bytes=6" in proto.handle("operator", "PUTEND", {
        "id": "aabbccdd", "seqs": "3",
    })[0]
    assert dest.read_bytes() == data
    assert store.get("aabbccdd").state == "ready"


def test_missing_list_is_bounded_and_reports_unexpected(upload):
    proto, _, dest, _ = upload
    send_chunk(proto, 100, b"a")
    lines = proto.handle("operator", "PUTEND", {"id": "aabbccdd", "seqs": "99"})
    assert "missing=" + ",".join(map(str, range(1, 33))) + " missing_more=67" in lines[0]
    assert "unexpected=1" in lines[0]
    assert len(lines[0]) < 350
    assert dest.read_bytes() == b"old file"


def test_unexpected_chunks_require_new_upload_or_corrected_count(upload):
    proto, _, dest, data = upload
    send_chunk(proto, 2, data[3:])
    first = proto.handle("operator", "PUTEND", {"id": "aabbccdd", "seqs": "1"})[0]
    assert "missing=1 missing_more=0 unexpected=1" in first
    send_chunk(proto, 1, data[:3])
    retry = proto.handle("operator", "PUTEND", {"id": "aabbccdd", "seqs": "1"})[0]
    assert "missing=- missing_more=0 unexpected=1" in retry
    assert dest.read_bytes() == b"old file"


def test_zero_count_places_empty_file(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store)
    proto.handle("operator", "PUT", {"id": "aabbccdd", "path": "empty.bin", "bytes": "0"})
    lines = proto.handle("operator", "PUTEND", {"id": "aabbccdd", "seqs": "0"})
    assert "putend bytes=0" in lines[0]
    assert (store.drop_root / "empty.bin").read_bytes() == b""


def test_nonempty_upload_declared_as_zero_is_rejected(tmp_path):
    data = b"not empty"
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store)
    dest = store.drop_root / "file.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"old file")
    proto.handle("operator", "PUT", {
        "id": "aabbccdd", "path": "file.bin", "bytes": "0",
        "sha256": hashlib.sha256(data).hexdigest(),
    })
    send_chunk(proto, 1, data)
    lines = proto.handle("operator", "PUTEND", {
        "id": "aabbccdd", "seqs": "1",
    })
    assert len(lines) == 1 and "code=size" in lines[0]
    assert dest.read_bytes() == b"old file"
    assert store.get("aabbccdd").state == "receiving"


def test_async_putend_emits_error_once(upload):
    proto, _, dest, data = upload
    send_chunk(proto, 1, data)
    replies = []
    done = threading.Event()

    def reply(nick, line):
        replies.append((nick, line))
        done.set()

    proto.on_reply = reply
    proto.inline_jobs = False
    proto.handle_async("operator", "PUTEND", {"id": "aabbccdd"})
    assert done.wait(2)
    assert len(replies) == 1
    assert "code=put-seqs-required" in replies[0][1]
    assert dest.read_bytes() == b"old file"


def test_put_reply_timeout_starts_after_paced_frames():
    script = (ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1").read_text(encoding="utf-8")
    send = script.index("Write-AircOutbox -Outbox $Outbox")
    reset = script.index("if ($Action -eq 'Put')", send)
    wait = script.index("if (-not $wantWait)", reset)
    comment = script.rfind("# FR #5838: the reply allowance", 0, reset)
    assert send < comment < reset < wait
    assert "$deadline = [datetime]::UtcNow.AddSeconds([Math]::Max(1, $TimeoutSec))" in script[reset:wait]
    assert "FR #5838: the reply allowance starts once all paced PUT frames were sent." in script[comment:wait]
