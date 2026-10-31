"""MRB #5623 hostile pins for FR #5613 DCCLISTEN TTL/cap/clear."""
from __future__ import annotations

import airc_console as ac
from airc_auth_helpers import ops_auth
from airc_jobs import JobProtocol, JobStore

LISTEN = (
    "DCCLISTEN id={jid} host=127.0.0.1 port=47121 "
    "token=0123456789abcdef0123456789abcdef tls=1"
)


def test_mrb5623_status_clears_unused_offer(tmp_path):
    runner = ac.ShellJobRunner(on_reply=lambda *_a, **_k: None)
    proto = JobProtocol(JobStore(tmp_path / "home"), machine="tm", airc_running=True)
    core = ac.AircConsoleCore(
        machine="tm",
        auth=ops_auth("op", channel="#tm"),
        nick="tm_console",
        shell_runner=runner,
        job_protocol=proto,
    )
    assert core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=deadbeef " + LISTEN.format(jid="deadbeef")
    )
    assert "deadbeef" in runner._dcc_listen
    assert core.handle_raw(":op!u@h PRIVMSG tm_console :id=deadbeef STATUS")
    assert "deadbeef" not in runner._dcc_listen
    assert any("cleared id=deadbeef" in e for e in runner.dcc_listen_events)


def test_mrb5623_peek_does_not_consume_and_prunes_expired():
    r = ac.ShellJobRunner(on_reply=lambda *_a, **_k: None)
    r._now = lambda: 100.0
    assert r.note_dcclisten(LISTEN.format(jid="aabbccdd"))
    assert r.peek_dcc_offer("aabbccdd") is not None
    assert "aabbccdd" in r._dcc_listen
    r._now = lambda: 100.0 + ac.DCCLISTEN_TTL_S + 5
    assert r.peek_dcc_offer("aabbccdd") is None
    assert "aabbccdd" not in r._dcc_listen
    assert any(e.startswith("expired id=aabbccdd") for e in r.dcc_listen_events)


def test_mrb5623_docs_and_constants():
    from pathlib import Path
    assert ac.DCCLISTEN_TTL_S == 60.0
    assert ac.DCCLISTEN_MAX == 32
    root = Path(ac.__file__).resolve().parents[1]
    skill = (root / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md").read_text(encoding="utf-8")
    assert "5613" in skill and "60 s" in skill and "capped at 32" in skill
