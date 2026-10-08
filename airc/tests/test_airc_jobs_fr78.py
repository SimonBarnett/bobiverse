"""FR #78: PUT/CHUNK/PUTEND/RUN/JOB/STATUS/GET sandbox + durable jobs."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

import airc_console as ac
from airc_auth_helpers import ops_auth  # FR #3639: channel +o/+h auth
import airc_jobs as jobs


@pytest.fixture()
def home(tmp_path):
    return tmp_path / "console-home"


def _put_file(proto: jobs.JobProtocol, nick: str, rel: str, data: bytes, chunk: int = 50):
    import base64

    sha = hashlib.sha256(data).hexdigest()
    jid = jobs.new_job_id()
    lines = proto.handle(nick, "PUT", {"path": rel, "id": jid, "bytes": str(len(data)), "sha256": sha})
    assert lines[0].startswith("ok id="), lines
    seq = 0
    for i in range(0, len(data), chunk):
        seq += 1
        b64 = base64.b64encode(data[i : i + chunk]).decode("ascii")
        lines = proto.handle(nick, "CHUNK", {"id": jid, "seq": str(seq), "data": b64})
        assert "ok id=" in lines[0], lines
    lines = proto.handle(nick, "PUTEND", {"id": jid, "seqs": str(seq), "sha256": sha})
    assert "putend" in lines[0], lines
    return jid


def test_status_parseable(home, tmp_path):
    (tmp_path / "bob").mkdir()
    (tmp_path / "bob" / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    (tmp_path / "airc").mkdir()
    (tmp_path / "airc" / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    (tmp_path / "jeeves").mkdir()
    (tmp_path / "jeeves" / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    store = jobs.JobStore(home)
    proto = jobs.JobProtocol(store, ai_root=tmp_path, machine="tm", airc_running=True)
    lines = proto.handle("bob-tm", "STATUS", {})
    assert len(lines) >= 2
    assert lines[0].startswith("out id=") and " seq=1 STATUS machine=tm airc=Running" in lines[0]
    assert "bob=1.2.3" in lines[0]
    assert "airc_ver=9.9.9" in lines[0]
    assert "jeeves=0.1.0" in lines[0]
    # FR #2570: STATUS ends with DONE id=… exit=0 for ReplyFile Wait.
    assert lines[-1].startswith("DONE id=") and lines[-1].endswith("exit=0")


def test_put_chunk_checksum_run_job_flow(home):
    store = jobs.JobStore(home)
    ran = {}

    def run_file(path: Path, timeout: float):
        ran["path"] = path
        text = path.read_text(encoding="utf-8")
        assert "Write-Output" in text
        return 0, "ok-line\n", ""

    replies: list[str] = []
    proto = jobs.JobProtocol(
        store,
        on_reply=lambda n, line: replies.append(line),
        run_file=run_file,
        machine="tm",
    )
    script = "\n".join([f"Write-Output '{i}'" for i in range(50)]) + "\n"
    data = script.encode("utf-8")
    jid = _put_file(proto, "bob-tm", "scripts/demo.ps1", data, chunk=40)
    dest = store.drop_root / "scripts" / "demo.ps1"
    assert dest.is_file()
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == hashlib.sha256(data).hexdigest()

    start = proto.handle("bob-tm", "RUN", {"id": jid})
    assert "run started" in start[0]
    # wait for background DONE
    for _ in range(50):
        if any(r.startswith("DONE id=") for r in replies):
            break
        time.sleep(0.05)
    assert any(r == f"DONE id={jid} exit=0" for r in replies)
    job_lines = proto.handle("bob-tm", "JOB", {"id": jid})
    assert "state=completed" in job_lines[0]
    assert "exit=0" in job_lines[0]
    assert ran["path"] == dest


def test_duplicate_chunk_idempotent_and_out_of_order_fails(home):
    store = jobs.JobStore(home)
    proto = jobs.JobProtocol(store)
    data = b"abcdefghij" * 5
    sha = hashlib.sha256(data).hexdigest()
    jid = jobs.new_job_id()
    proto.handle("bob-tm", "PUT", {"path": "x.bin", "id": jid, "bytes": str(len(data)), "sha256": sha})
    import base64

    c1 = base64.b64encode(data[:10]).decode()
    c2 = base64.b64encode(data[10:20]).decode()
    assert "ok" in proto.handle("bob-tm", "CHUNK", {"id": jid, "seq": "1", "data": c1})[0]
    assert "dup=1" in proto.handle("bob-tm", "CHUNK", {"id": jid, "seq": "1", "data": c1})[0]
    # skip seq 2, send 3
    c3 = base64.b64encode(data[20:30]).decode()
    proto.handle("bob-tm", "CHUNK", {"id": jid, "seq": "3", "data": c3})
    err = proto.handle("bob-tm", "PUTEND", {"id": jid, "seqs": "3", "sha256": sha})[0]
    assert err.startswith("err ")
    assert "order" in err or "incomplete" in err


def test_checksum_mismatch(home):
    store = jobs.JobStore(home)
    proto = jobs.JobProtocol(store)
    data = b"hello-world-data"
    jid = jobs.new_job_id()
    proto.handle(
        "bob-tm",
        "PUT",
        {"path": "a.bin", "id": jid, "bytes": str(len(data)), "sha256": "0" * 64},
    )
    import base64

    b64 = base64.b64encode(data).decode()
    proto.handle("bob-tm", "CHUNK", {"id": jid, "seq": "1", "data": b64})
    err = proto.handle("bob-tm", "PUTEND", {"id": jid, "seqs": "1", "sha256": "0" * 64})[0]
    assert "checksum" in err


def test_size_limit_rejected(home):
    store = jobs.JobStore(home)
    proto = jobs.JobProtocol(store)
    err = proto.handle(
        "bob-tm",
        "PUT",
        {"path": "big.bin", "id": "aabbccdd", "bytes": str(jobs.MAX_PUT_BYTES + 1), "sha256": "a" * 64},
    )[0]
    assert "size" in err


def test_traversal_absolute_secret_fail_closed(home):
    store = jobs.JobStore(home)
    proto = jobs.JobProtocol(store)
    assert "traversal" in proto.handle("bob-tm", "PUT", {"path": "..\\evil.ps1", "id": "a1b2c3d4", "bytes": "1"})[0]
    assert "sandbox" in proto.handle(
        "bob-tm", "PUT", {"path": r"C:\Windows\System32\x.ps1", "id": "a1b2c3d5", "bytes": "1"}
    )[0]
    assert "secret" in proto.handle(
        "bob-tm", "PUT", {"path": "console.password", "id": "a1b2c3d6", "bytes": "1"}
    )[0]
    # secret via GET
    assert "secret" in proto.handle("bob-tm", "GET", {"path": "ergo.password"})[0]


def test_unauthorized_verb_matrix(home):
    store = jobs.JobStore(home)
    auth = jobs.VerbAuthPolicy(write_nicks={"bob-tm"}, exec_nicks={"bob-tm"})
    proto = jobs.JobProtocol(store, verb_auth=auth)
    # read ok for other nick
    lines = proto.handle("bob-other", "STATUS", {})
    assert lines[0].startswith("out id=") and "STATUS machine=" in lines[0]
    # write denied
    err = proto.handle("bob-other", "PUT", {"path": "a.bin", "id": "deadbeef", "bytes": "1"})[0]
    assert "denied" in err
    err2 = proto.handle("bob-other", "RUN", {"id": "deadbeef"})[0]
    assert "denied" in err2


def test_malformed_frame(home):
    store = jobs.JobStore(home)
    proto = jobs.JobProtocol(store)
    assert "bad_frame" in proto.handle("bob-tm", "CHUNK", {"id": "x", "seq": "1"})[0]
    assert "bad_frame" in proto.handle("bob-tm", "JOB", {})[0]


def test_cancel_and_timeout(home):
    store = jobs.JobStore(home)
    replies: list[str] = []

    def slow(path: Path, timeout: float):
        time.sleep(0.2)
        if True:
            raise TimeoutError("timeout")

    proto = jobs.JobProtocol(
        store, on_reply=lambda n, l: replies.append(l), run_file=slow, run_timeout_s=0.01
    )
    data = b"Write-Output 1\n"
    jid = _put_file(proto, "bob-tm", "t.ps1", data)
    proto.handle("bob-tm", "CANCEL", {"id": jid})
    # cancelled while ready
    rec = store.get(jid)
    assert rec is not None and rec.state == "cancelled"


def test_restart_recovery_marks_running_failed(home):
    store = jobs.JobStore(home)
    rec = jobs.JobRecord(
        id="recov001",
        state="running",
        created_ts=time.time(),
        updated_ts=time.time(),
        path=str(store.drop_root / "x.ps1"),
    )
    store._save(rec)
    # new store simulates restart
    store2 = jobs.JobStore(home)
    got = store2.get("recov001")
    assert got is not None
    assert got.state == "failed"
    assert "interrupted" in got.error


def test_bounded_cleanup(home, monkeypatch):
    store = jobs.JobStore(home)
    monkeypatch.setattr(jobs, "MAX_JOBS_RETAINED", 3)
    monkeypatch.setattr(jobs, "JOB_RETENTION_S", 10_000)
    for i in range(5):
        rec = jobs.JobRecord(
            id=f"old{i:04d}",
            state="completed",
            created_ts=time.time() - i,
            updated_ts=time.time() - i,
        )
        store._save(rec)
    store.cleanup()
    assert len(store._meta) <= 3


def test_core_routes_status_and_denies_unauth(home):
    auth = ops_auth("bob-tm")
    store = jobs.JobStore(home)
    replies: list[str] = []
    proto = jobs.JobProtocol(
        store,
        on_reply=lambda n, line: replies.append(line),
        machine="tm",
        ai_root=home,
    )
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=proto,
    )
    hr = core.handle_raw(":bob-tm!u@h PRIVMSG tm_console :STATUS")
    assert hr is not None and hr.action == "job"
    assert any(r.startswith("out id=") and "STATUS machine=" in r for r in replies)
    replies.clear()
    hr2 = core.handle_raw(":evil!u@h PRIVMSG tm_console :STATUS")
    assert hr2 is not None and hr2.action == "deny"
