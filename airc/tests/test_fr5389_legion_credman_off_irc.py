"""FR #5389: CredRead must not run on the LEGION IRC accept path."""
from __future__ import annotations

import time

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


def test_fr5389_slow_credman_does_not_block_accept():
    def slow():
        time.sleep(0.3)
        return {}

    t0 = time.perf_counter()
    res = lg.run_legion_verb(
        target="box1", credman=slow, wait=False, job_id="aabbccdd"
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.15
    assert "LEGION accepted" in res.reply
    assert "126" not in res.reply


def test_fr5389_wait_still_fail_closed_126():
    res = lg.run_legion_verb(
        target="box1", credman=lambda: {}, wait=True, job_id="aabbccdd"
    )
    assert "126" in res.reply
    assert "credman-missing" in res.reply


def test_fr5389_console_accept_is_fast():
    def slow():
        time.sleep(0.3)
        return {}

    core = ac.AircConsoleCore(
        machine="tm",
        auth=ops_auth("op", channel="#tm"),
        nick="tm_console",
        legion_runner=lambda **kw: lg.run_legion_verb(credman=slow, wait=False, **kw),
    )
    t0 = time.perf_counter()
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION box1")
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.15
    assert hr and hr.action == "legion"
    assert "LEGION accepted" in (hr.reply or "")
