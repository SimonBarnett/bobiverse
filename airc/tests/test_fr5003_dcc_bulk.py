"""FR #5003: reverse DCC bulk path for oversized shell replies."""
from __future__ import annotations

import time

import airc_console as ac
import airc_dcc_bulk as dcc


def test_threshold_and_done_shape():
    assert dcc.should_use_dcc_bulk(piece_count=48, byte_count=10)
    assert dcc.should_use_dcc_bulk(piece_count=1, byte_count=12000)
    assert not dcc.should_use_dcc_bulk(piece_count=10, byte_count=100)
    data = dcc.build_bulk_bytes("hello\n", "e1\n")
    digest = dcc.sha256_hex(data)
    payload = dcc.BulkPayload("aabbccdd", 0, data, digest)
    lines = dcc.format_bulk_control_lines(payload)
    assert lines[0].startswith("out id=aabbccdd seq=1 bulk bytes=")
    assert lines[-1] == (
        f"DONE id=aabbccdd exit=0 bytes={payload.nbytes} sha256={digest} via=dcc"
    )
    parsed = dcc.parse_done_line(lines[-1])
    assert parsed["id"] == "aabbccdd"
    assert parsed["exit"] == 0
    assert parsed["via"] == "dcc"
    assert parsed["sha256"] == digest


def test_dcclisten_parse():
    offer = dcc.parse_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 token=0123456789abcdef0123456789abcdef"
    )
    assert offer is not None
    assert offer.job_id == "aabbccdd"
    assert offer.port == 9
    assert dcc.parse_dcclisten("CONT id=aabbccdd") is None


def test_reverse_dcc_localhost_roundtrip_faster_than_irc_line_count():
    # ~80 KB payload (would be many IRC pages).
    body = ("line-%05d-ABCDEFGHIJKLMNOPQRSTUVWXYZ\n" % i for i in range(2000))
    payload = "".join(body).encode("utf-8")
    t0 = time.perf_counter()
    got = dcc.reverse_dcc_roundtrip_localhost(payload, timeout_s=3.0)
    dcc_s = time.perf_counter() - t0
    assert got == payload
    # Simulated IRC: one PRIVMSG per 350-byte piece at FLOOD_S=1.5 would be minutes;
    # here we only assert DCC finished quickly and IRC piece count would be large.
    pieces = (len(payload) + 349) // 350
    assert pieces > 48
    assert dcc_s < 2.0


def test_format_shell_replies_ex_prefers_dcc_when_peer_ready():
    stdout = "\n".join(f"row-{i}" for i in range(80))
    outcome = ac.ShellOutcome(job_id="aabbccdd", exit_code=0, stdout=stdout, stderr="")
    irc = ac.format_shell_replies_ex(outcome)
    assert irc.via_dcc is False
    assert any("output truncated" in ln or ln.startswith("out ") for ln in irc.lines)
    bulk = ac.format_shell_replies_ex(
        outcome, prefer_dcc_bulk=True, dcc_peer_ready=True
    )
    assert bulk.via_dcc is True
    assert bulk.bulk_payload is not None
    assert bulk.lines[-1].endswith("via=dcc")
    assert len(bulk.lines) == 2


def test_format_shell_replies_ex_without_peer_stays_irc():
    stdout = "\n".join(f"row-{i}" for i in range(80))
    outcome = ac.ShellOutcome(job_id="aabbccdd", exit_code=0, stdout=stdout, stderr="")
    page = ac.format_shell_replies_ex(
        outcome, prefer_dcc_bulk=True, dcc_peer_ready=False
    )
    assert page.via_dcc is False
    assert page.lines[-1] == "DONE id=aabbccdd exit=0"


def test_shell_id_re_accepts_via_dcc():
    import airc_console_service as svc

    m = svc._SHELL_ID_RE.match(
        "DONE id=aabbccdd exit=0 bytes=12 sha256=ab via=dcc"
    )
    assert m is not None
    assert m.group(2) == "aabbccdd"


def test_runner_note_dcclisten():
    seen: list[str] = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line), wait=False)
    assert runner.note_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=1 token=0123456789abcdef0123456789abcdef"
    )
    assert "aabbccdd" in runner._dcc_listen
