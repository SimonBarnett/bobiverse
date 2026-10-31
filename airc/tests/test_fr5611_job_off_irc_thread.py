"""FR #5611: job I/O (PUT/DCC) must not block the IRC read loop."""
from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import airc_jobs as jobs


def test_fr5611_handle_async_returns_while_dcc_blocks(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store, job_io_timeout_s=2.0, inline_jobs=False)
    started = threading.Event()
    release = threading.Event()
    seen: list[str] = []
    proto.on_reply = lambda _n, ln: seen.append(ln)

    def hang(_jid: str):
        started.set()
        release.wait(3.0)
        return b"x", hashlib.sha256(b"x").hexdigest()

    proto.dcc_receive = hang
    t0 = time.perf_counter()
    proto.handle_async(
        "op",
        "PUT",
        {
            "id": "aabbccdd",
            "path": "ok.bin",
            "bytes": "1",
            "sha256": hashlib.sha256(b"x").hexdigest(),
            "via": "dcc",
        },
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.25
    assert started.wait(1.0)
    release.set()
    deadline = time.time() + 2.0
    while time.time() < deadline and not any("putend" in ln or "falling back" in ln for ln in seen):
        time.sleep(0.02)
    assert any("via=dcc" in ln or "falling back" in ln or "putend" in ln for ln in seen)


def test_fr5611_dcc_timeout_emits_err_and_done(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store, job_io_timeout_s=0.15, inline_jobs=False)
    seen: list[str] = []
    proto.on_reply = lambda _n, ln: seen.append(ln)

    def hang(_jid: str):
        time.sleep(3.0)
        return b"x", "0" * 64

    proto.dcc_receive = hang
    proto.handle_async(
        "op",
        "PUT",
        {
            "id": "aabbccdd",
            "path": "ok.bin",
            "bytes": "1",
            "sha256": "0" * 64,
            "via": "dcc",
        },
    )
    deadline = time.time() + 1.5
    while time.time() < deadline and not any("DONE" in ln for ln in seen):
        time.sleep(0.02)
    blob = "\n".join(seen)
    assert "code=timeout" in blob
    assert "DONE id=aabbccdd exit=" in blob
    assert "exit=0" not in blob


def test_fr5611_inline_handle_still_works(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store)
    proto.dcc_receive = lambda _j: (b"ab", hashlib.sha256(b"ab").hexdigest())
    lines = proto.handle(
        "op",
        "PUT",
        {
            "id": "aabbccdd",
            "path": "ok.bin",
            "bytes": "2",
            "sha256": hashlib.sha256(b"ab").hexdigest(),
            "via": "dcc",
        },
    )
    assert any("via=dcc" in ln for ln in lines)
    assert (tmp_path / "drop" / "ok.bin").read_bytes() == b"ab"


def test_fr5611_pins():
    src = Path(jobs.__file__).read_text(encoding="utf-8")
    assert "FR #5611" in src
    assert "inline_jobs" in src
    assert "job_io_timeout_s" in src
    assert "code=timeout" in src
    assert not Path(jobs.__file__).read_bytes().startswith(b"\xef\xbb\xbf")
