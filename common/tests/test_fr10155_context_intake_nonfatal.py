# -*- coding: utf-8 -*-
"""FR #10155: grok context unsupported-by-cli must never abort the seat start.

The real ``_file_grok_context_unsupported_intake`` path is exercised; only the
runtime_failure transport is stubbed. The intake is a deduped report, not a
raised exception that reaches the caller.
"""
from __future__ import annotations

import runtime_failure
import worker_start_model as wsm


def test_unsupported_context_is_nonfatal_and_deduped(monkeypatch):
    recorded: list[tuple[str, str, str]] = []

    def fake_report(component, exc, *, site=""):
        recorded.append((component, str(exc), site))
        return {}

    monkeypatch.setattr(runtime_failure, "report", fake_report)
    monkeypatch.setattr(wsm, "GROK_CONTEXT_CLI_FLAG", None)
    monkeypatch.setattr(wsm, "_context_intake_last", 0.0)

    # Two starts in the same hour: both must return argv, neither may raise.
    for _ in range(2):
        args, status = wsm.cli_settings_args(
            "grok", model="grok-4.7", effort="low", context="256"
        )
        assert status["context"] == "not-passed: unsupported-by-cli"
        assert "--reasoning-effort" in args
        assert "256" not in args

    assert len(recorded) == 1, recorded
    component, message, site = recorded[0]
    assert component == "bob-worker"
    assert site == "grok-context-unsupported-by-cli"
    assert "FR #9258" in message
    assert "GROK_CONTEXT_CLI_FLAG=None" in message
