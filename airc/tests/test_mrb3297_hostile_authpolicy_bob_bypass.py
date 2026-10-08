"""MRB #3297 hostile pins: AuthPolicy must not short-circuit True for arbitrary bob-*."""
from __future__ import annotations

import inspect
import re

import airc_console as ac
import airc_console_service as svc


def test_mrb3297_bob_evil_denied_default_ops_only():
    policy = ac.AuthPolicy(operators={"simon"}, machine="marchhare")
    assert policy.allow("bob-evil") is False
    assert policy.allow("bob-marchhare") is True


def test_mrb3297_allow_has_no_is_bob_fleet_nick_before_ops():
    src = inspect.getsource(ac.AuthPolicy.allow)
    before_ops = src.split("ops =", 1)[0]
    assert "is_bob_fleet_nick" not in before_ops
    assert not re.search(
        r"if\s+is_bob_fleet_nick\s*\([^)]*\)\s*:\s*\n\s*return\s+True",
        src,
    )


def test_mrb3297_selftest_source_pins_bob_evil_deny():
    src = inspect.getsource(svc.selftest)
    assert 'bob-evil' in src
    assert 'assert not auth.allow("bob-evil")' in src or "assert not auth.allow('bob-evil')" in src
