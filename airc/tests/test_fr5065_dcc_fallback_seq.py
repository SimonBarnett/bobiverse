"""FR #5065: DCC->IRC fallback must not reuse seq=1 (Invoke-AircRemote parse)."""
from __future__ import annotations

import re

import airc_console as ac


_SEQ = re.compile(r"^(?:out|err) id=[0-9a-f]{8} seq=(\d+) ", re.I)


def _seqs(lines: list[str]) -> list[int]:
    return [int(m.group(1)) for ln in lines if (m := _SEQ.match(ln))]


def test_fr5065_insert_notice_after_page_unique_seq():
    jid = "006dfca0"
    page = [
        f"out id={jid} seq=1 L0001 xxxx",
        f"out id={jid} seq=2 L0002 xxxx",
        f"err id={jid} seq=3 output truncated, 1 lines omitted; CONT id={jid}",
        f"DONE id={jid} exit=0",
    ]
    # Pre-fix shape (notice first at seq=1) would collide.
    broken = [f"err id={jid} seq=1 dcc failed: refused; falling back to IRC"] + page
    assert len(_seqs(broken)) != len(set(_seqs(broken)))

    fixed = ac.insert_dcc_fallback_notice(
        page, jid, "dcc failed: refused; falling back to IRC"
    )
    seqs = _seqs(fixed)
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))
    assert any("dcc failed" in ln and "falling back to IRC" in ln for ln in fixed)
    assert fixed[-1] == f"DONE id={jid} exit=0"
    assert "dcc failed" in fixed[-2]


def test_fr5065_runner_dcc_raise_unique_seq_and_done(monkeypatch):
    emitted: list[str] = []
    stdout = "\n".join(f"row-{i}" for i in range(80))

    def _fake_run(req, timeout_s=None, cwd=None):
        return ac.ShellOutcome(job_id=req.job_id, exit_code=0, stdout=stdout, stderr="")

    def _boom(*_a, **_k):
        raise OSError(10061, "No connection could be made because the target machine actively refused it")

    monkeypatch.setattr(ac, "run_shell_request", _fake_run)
    monkeypatch.setattr("airc_dcc_bulk.send_offer_payload", _boom)

    runner = ac.ShellJobRunner(
        on_reply=lambda nick, line: emitted.append(line),
        wait=True,
        timeout_s=5,
    )
    jid = "006dfca0"
    token = "0123456789abcdef0123456789abcdef"
    assert runner.note_dcclisten(
        f"DCCLISTEN id={jid} host=127.0.0.1 port=1 token={token}"
    )
    runner.start("op", f"id={jid} Write-Output x")
    seqs = _seqs(emitted)
    assert seqs, emitted
    assert len(seqs) == len(set(seqs)), emitted
    assert any("dcc failed" in ln and "falling back to IRC" in ln for ln in emitted)
    assert emitted[-1] == f"DONE id={jid} exit=0"
    assert not any(ln.endswith("via=dcc") for ln in emitted)
