"""FR #8454: OpenCode free-first start + end-of-turn free↔paid switch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import worker_start_model as wsm


def test_prefer_runtime_free_when_unknown_or_positive():
    m, a = wsm.prefer_opencode_runtime_model(
        "opencode-go/deepseek-v4-pro",
        free_remaining=None,
        go_remaining=50,
    )
    assert a == "switch-to-free"
    assert m == wsm.DEFAULT_OPENCODE_FREE

    m2, a2 = wsm.prefer_opencode_runtime_model(
        wsm.DEFAULT_OPENCODE_FREE,
        free_remaining=10,
        go_remaining=0,
    )
    assert (m2, a2) == (wsm.DEFAULT_OPENCODE_FREE, "keep")


def test_prefer_runtime_paid_when_free_empty():
    m, a = wsm.prefer_opencode_runtime_model(
        wsm.DEFAULT_OPENCODE_FREE,
        free_remaining=0,
        go_remaining=40,
    )
    assert a == "switch-to-paid"
    assert m == wsm.DEFAULT_OPENCODE_PAID


def test_prefer_runtime_exhausted_when_both_empty():
    m, a = wsm.prefer_opencode_runtime_model(
        wsm.DEFAULT_OPENCODE_PAID,
        free_remaining=0,
        go_remaining=0,
    )
    assert a == "exhausted"
    assert m == wsm.DEFAULT_OPENCODE_PAID


def test_prefer_runtime_switch_back_to_free_from_paid():
    m, a = wsm.prefer_opencode_runtime_model(
        "opencode-go/deepseek-v4-pro",
        free_remaining=5,
        go_remaining=90,
        free_id="opencode/deepseek-v4.1-flash-free",
        paid_id="opencode-go/deepseek-v4-pro",
    )
    assert (m, a) == ("opencode/deepseek-v4.1-flash-free", "switch-to-free")


def test_default_paid_helper_reads_tray():
    cfg = {"models": {"opencodePaid": "opencode-go/custom-pro"}}
    assert wsm.default_opencode_paid_model(cfg) == "opencode-go/custom-pro"
    assert wsm.default_opencode_paid_model({}) == wsm.DEFAULT_OPENCODE_PAID


def test_prefer_runtime_cli_json(tmp_path, monkeypatch):
    import opencode_fuel as of

    helper = Path(of.__file__)
    state = tmp_path / "state"
    state.mkdir()
    # Free paused → free=0; paid available → switch-to-paid
    of.save_opencode_pauses(state, {"opencode-free": 9_999_999_999.0})
    proc = __import__("subprocess").run(
        [
            sys.executable,
            str(helper),
            "prefer-runtime",
            "--dir",
            str(state),
            "--current",
            wsm.DEFAULT_OPENCODE_FREE,
            "--free-id",
            wsm.DEFAULT_OPENCODE_FREE,
            "--paid-id",
            wsm.DEFAULT_OPENCODE_PAID,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout.strip().splitlines()[-1])
    assert doc["action"] == "switch-to-paid"
    assert doc["model"] == wsm.DEFAULT_OPENCODE_PAID
    assert doc["free"] == 0
