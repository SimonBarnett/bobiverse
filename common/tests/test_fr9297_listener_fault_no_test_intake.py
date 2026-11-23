"""FR #9297: listener-fault intake must not file from pytest or unit-test port=9.

#9297 / #9298 were filed with host=127.0.0.1 port=9 free_mb fingerprints from the
FR #9236 / #7618 self-probe unit suite. Guard crash_report._post_intake under
PYTEST_CURRENT_TEST and skip report_http_listener_fault for the reserved test port.
"""
from __future__ import annotations

import os
from pathlib import Path

import bobcallback
import crash_report


def test_fr9297_post_intake_skips_under_pytest(monkeypatch):
    assert os.environ.get("PYTEST_CURRENT_TEST"), "must run under pytest"
    calls: list[object] = []

    def boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("urlopen must not run under pytest")

    monkeypatch.setattr(crash_report.urllib.request, "urlopen", boom)
    out = crash_report._post_intake(
        "bug: should not file",
        "body",
        repo="SimonBarnett/bobiverse",
        sig="fr9297-pytest-skip",
        exe="jeeves",
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "pytest"
    assert calls == []


def test_fr9297_listener_fault_skips_test_port_without_report_fn(monkeypatch):
    posts: list[object] = []

    def capture_post(title, body, *, repo, sig, exe):
        posts.append({"title": title, "body": body, "sig": sig})
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_post_intake", capture_post)
    # Simulate non-pytest caller (clear flag) with the reserved unit-test port.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("BOB_CALLBACK_ALLOW_TEST_INTAKE", raising=False)

    out = bobcallback.report_http_listener_fault(
        why="self-probe",
        detail="refused",
        host="127.0.0.1",
        port=9,
        exc=None,
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "unit-test-port"
    assert posts == []


def test_fr9297_listener_fault_still_reports_real_port(monkeypatch):
    posts: list[dict] = []

    def capture_post(title, body, *, repo, sig, exe):
        posts.append({"title": title, "body": body})
        return {"ok": True, "number": 1}

    monkeypatch.setattr(crash_report, "_post_intake", capture_post)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("BOB_CALLBACK_ALLOW_TEST_INTAKE", raising=False)

    # exc=None takes the _post_intake path (not report_exception).
    out = bobcallback.report_http_listener_fault(
        why="self-probe",
        detail="connection refused",
        host="127.0.0.1",
        port=7700,
        exc=None,
    )
    assert out.get("ok") is True
    assert len(posts) == 1
    assert "7700" in posts[0]["body"]


def test_fr9297_source_has_no_machine_names():
    root = Path(__file__).resolve().parents[2]
    src = (root / "common" / "scripts" / "bobcallback.py").read_text(encoding="utf-8")
    assert "UNIT_TEST_LISTENER_PORTS" in src or "unit-test-port" in src
    assert "FR #9297" in src
    banned = ("wal" + "rus", "flam" + "ingo")
    start = src.index("def report_http_listener_fault")
    chunk = src[start : start + 2500].lower()
    for name in banned:
        assert name not in chunk
