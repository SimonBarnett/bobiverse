"""MRB #5618 hostile: PUT/PUTEND write timeout must emit err+DONE (FR #5611)."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import airc_jobs as jobs


def test_mrb5618_dcc_write_timeout_emits_done(tmp_path, monkeypatch):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store, job_io_timeout_s=0.15, inline_jobs=False)
    seen: list[str] = []
    proto.on_reply = lambda _n, ln: seen.append(ln)
    body = b"ab"
    dig = hashlib.sha256(body).hexdigest()
    proto.dcc_receive = lambda _j: (body, dig)

    def hang_place(dest, blob, expect_sha=""):
        time.sleep(2.0)
        return dig

    monkeypatch.setattr(jobs, "atomic_place_file", hang_place)
    proto.handle_async(
        "op",
        "PUT",
        {
            "id": "aabbccdd",
            "path": "ok.bin",
            "bytes": str(len(body)),
            "sha256": dig,
            "via": "dcc",
        },
    )
    deadline = time.time() + 2.0
    while time.time() < deadline and not any("DONE" in ln for ln in seen):
        time.sleep(0.02)
    blob = "\n".join(seen)
    assert "code=timeout" in blob
    assert "DONE id=aabbccdd exit=1" in blob


def test_mrb5618_putend_write_timeout_emits_done(tmp_path, monkeypatch):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store, job_io_timeout_s=0.15, inline_jobs=True)
    body = b"hello"
    dig = hashlib.sha256(body).hexdigest()
    import base64

    lines = proto.handle(
        "op",
        "PUT",
        {"id": "aabbccdd", "path": "ok.bin", "bytes": str(len(body)), "sha256": dig},
    )
    assert any(ln.startswith("ok id=aabbccdd put") for ln in lines)
    chunk = base64.b64encode(body).decode("ascii")
    proto.handle("op", "CHUNK", {"id": "aabbccdd", "seq": "1", "data": chunk})

    def hang_place(dest, blob, expect_sha=""):
        time.sleep(2.0)
        return dig

    monkeypatch.setattr(jobs, "atomic_place_file", hang_place)
    out = proto.handle(
        "op",
        "PUTEND",
        {"id": "aabbccdd", "seqs": "1", "sha256": dig},
    )
    blob = "\n".join(out)
    assert "code=timeout" in blob
    assert "DONE id=aabbccdd exit=1" in blob


def test_mrb5618_service_sets_inline_jobs_false():
    src = Path(__file__).resolve().parents[1] / "scripts" / "airc_console_service.py"
    text = src.read_text(encoding="utf-8")
    assert "inline_jobs=False" in text
    jobs_src = Path(jobs.__file__).read_text(encoding="utf-8")
    assert "FR #5611" in jobs_src
    assert "run_job_io" in jobs_src
