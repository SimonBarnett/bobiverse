"""FR #5531: optional leading job id= before DCCLISTEN (docs + Invoke-AircRemote)."""
from __future__ import annotations

import airc_console as ac
import airc_dcc_bulk as dcc
from airc_auth_helpers import ops_auth

_TOKEN = "0123456789abcdef0123456789abcdef"
_BARE = f"DCCLISTEN id=aabbccdd host=127.0.0.1 port=7700 token={_TOKEN} tls=1"
_PREFIXED = f"id=aabbccdd {_BARE}"


def test_fr5531_parse_accepts_leading_job_id():
    bare = dcc.parse_dcclisten(_BARE)
    pref = dcc.parse_dcclisten(_PREFIXED)
    assert bare is not None and pref is not None
    assert pref.job_id == bare.job_id == "aabbccdd"
    assert pref.host == "127.0.0.1"
    assert pref.port == 7700
    assert pref.token == _TOKEN


def test_fr5531_parse_rejects_non_hex_prefix():
    assert dcc.parse_dcclisten(f"id=notajob {_BARE}") is None


def test_fr5531_handle_prefixed_records_offer_not_shell():
    seen: list[str] = []
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line), wait=False),
    )
    hr = core.handle_raw(f":op!u@h PRIVMSG tm_console :{_PREFIXED}")
    assert hr is not None
    assert hr.action == "dcc_listen"
    assert "aabbccdd" in core.shell_runner._dcc_listen
    assert not any("CommandNotFoundException" in x for x in seen)


def test_fr5531_handle_bare_still_records():
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda *_a, **_k: None, wait=False),
    )
    hr = core.handle_raw(f":op!u@h PRIVMSG tm_console :{_BARE}")
    assert hr is not None
    assert hr.action == "dcc_listen"
    assert "aabbccdd" in core.shell_runner._dcc_listen
