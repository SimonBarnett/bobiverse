# -*- coding: utf-8 -*-
"""FR #7863: a pytest outbox UnicodeEncodeError must not open an intake issue."""
from __future__ import annotations

import runtime_failure


def test_fr7863_default_report_skips_intake_under_pytest(monkeypatch):
    called = {"n": 0}

    def fake_post(*_a, **_k):
        called["n"] += 1
        return {"ok": True}

    monkeypatch.delenv("BOB_RUNTIME_FAILURE_UNDER_PYTEST", raising=False)
    # Patch the intake poster the default path would use.
    monkeypatch.setattr(runtime_failure.crash_report, "_post_intake", fake_post)
    exc = UnicodeEncodeError("cp1252", "\u2192", 0, 1, "ordinal not in range")
    out = runtime_failure.report("bob-ear", exc, site="outbox-loop")
    assert out.get("skipped") is True
    assert out.get("reason") == "pytest"
    assert called["n"] == 0


def test_fr7863_explicit_filer_still_runs_under_pytest(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_RUNTIME_FAILURE_DIR", str(tmp_path))
    runtime_failure._SEEN.clear()
    posts = []

    def fake_post(title, body, **_kw):
        posts.append(title)
        return {"ok": True}

    exc = UnicodeEncodeError("cp1252", "\u2192", 0, 1, "ordinal not in range")
    out = runtime_failure.report(
        "bob-ear", exc, site="outbox-loop-filer", filer_post=fake_post, rate_s=3600
    )
    assert out.get("ok") is True
    assert posts
