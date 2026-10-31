"""FR #5613: DCCLISTEN offers expire, size-cap, and clear on VERSION."""
from __future__ import annotations

import airc_console as ac
from airc_auth_helpers import ops_auth
from airc_jobs import JobProtocol, JobStore


LISTEN = (
    "DCCLISTEN id={jid} host=127.0.0.1 port=47121 "
    "token=0123456789abcdef0123456789abcdef tls=1"
)


def _runner() -> ac.ShellJobRunner:
    return ac.ShellJobRunner(on_reply=lambda *_a, **_k: None)


def test_fr5613_expired_offer_is_discarded():
    r = _runner()
    r._now = lambda: 1000.0
    assert r.note_dcclisten(LISTEN.format(jid="aabbccdd"))
    assert r.take_dcclisten("aabbccdd") is not None
    r.note_dcclisten(LISTEN.format(jid="aabbccdd"))
    r._now = lambda: 1000.0 + ac.DCCLISTEN_TTL_S + 1
    assert r.take_dcclisten("aabbccdd") is None
    assert "aabbccdd" not in r._dcc_listen


def test_fr5613_fresh_offer_still_taken():
    r = _runner()
    r._now = lambda: 50.0
    assert r.note_dcclisten(LISTEN.format(jid="11223344"))
    r._now = lambda: 50.0 + ac.DCCLISTEN_TTL_S - 1
    offer = r.take_dcclisten("11223344")
    assert offer is not None
    assert offer.job_id == "11223344"


def test_fr5613_cap_evicts_oldest():
    r = _runner()
    t = 10.0
    r._now = lambda: t
    for i in range(ac.DCCLISTEN_MAX + 2):
        jid = f"{i:08x}"
        r._now = lambda now=10.0 + i: now
        r.note_dcclisten(LISTEN.format(jid=jid))
    assert len(r._dcc_listen) <= ac.DCCLISTEN_MAX
    assert "00000000" not in r._dcc_listen
    last = f"{(ac.DCCLISTEN_MAX + 1):08x}"
    assert last in r._dcc_listen


def test_fr5613_version_clears_unused_offer(tmp_path):
    runner = _runner()
    proto = JobProtocol(JobStore(tmp_path / "home"), machine="tm", airc_running=True)
    core = ac.AircConsoleCore(
        machine="tm",
        auth=ops_auth("op", channel="#tm"),
        nick="tm_console",
        shell_runner=runner,
        job_protocol=proto,
    )
    hr = core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=11372a80 " + LISTEN.format(jid="11372a80")
    )
    assert hr is not None and hr.action == "dcc_listen"
    assert "11372a80" in runner._dcc_listen
    hr2 = core.handle_raw(":op!u@h PRIVMSG tm_console :id=11372a80 VERSION")
    assert hr2 is not None
    assert "11372a80" not in runner._dcc_listen
