"""FR #5536: PUT via=dcc allows up to DCC_BULK_SIZE_CAP (2 MiB)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import airc_dcc_bulk as dcc
import airc_jobs as jobs


def test_fr5536_irc_put_still_256kib(tmp_path):
    proto = jobs.JobProtocol(jobs.JobStore(tmp_path))
    err = proto.handle(
        "bob-tm",
        "PUT",
        {
            "path": "big.bin",
            "id": "aabbccdd",
            "bytes": str(jobs.MAX_PUT_BYTES + 1),
            "sha256": "a" * 64,
        },
    )[0]
    assert "size" in err
    assert "262144" in err or str(jobs.MAX_PUT_BYTES) in err


def test_fr5536_dcc_put_300k_accepted(tmp_path):
    proto = jobs.JobProtocol(jobs.JobStore(tmp_path))
    payload = b"Z" * 300000
    digest = hashlib.sha256(payload).hexdigest()
    proto.dcc_receive = lambda _jid: (payload, digest)
    lines = proto.handle(
        "bob-tm",
        "PUT",
        {
            "path": "mid.bin",
            "id": "11223344",
            "bytes": str(len(payload)),
            "sha256": digest,
            "via": "dcc",
        },
    )
    assert any("via=dcc" in ln for ln in lines)
    assert any("putend" in ln for ln in lines)
    dest = Path(tmp_path) / "drop" / "mid.bin"
    assert dest.read_bytes() == payload


def test_fr5536_dcc_put_over_dcc_cap_rejected(tmp_path):
    proto = jobs.JobProtocol(jobs.JobStore(tmp_path))
    too = dcc.DCC_BULK_SIZE_CAP + 1
    err = proto.handle(
        "bob-tm",
        "PUT",
        {
            "path": "huge.bin",
            "id": "55667788",
            "bytes": str(too),
            "sha256": "b" * 64,
            "via": "dcc",
        },
    )[0]
    assert "size" in err
    assert str(dcc.DCC_BULK_SIZE_CAP) in err
