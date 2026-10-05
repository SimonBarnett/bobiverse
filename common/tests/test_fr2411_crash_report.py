"""FR #2411: crash_report.py + C# CrashHook coverage."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from repo_layout import REPO, resolve

SCRIPTS = REPO / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import crash_report  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_spool(tmp_path, monkeypatch):
    spool = tmp_path / "crash-spool"
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(spool))
    # reset install idempotency between tests
    crash_report._installed_for = None
    yield spool


def test_redact_secrets_and_token_blobs():
    raw = (
        "password=hunter2 token: abc GH_TOKEN=gho_xxx BOB_IRC_PASSWORD=secret "
        "Authorization: Bearer xyz ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    )
    out = crash_report.redact(raw)
    assert "hunter2" not in out
    assert "gho_xxx" not in out
    assert "secret" not in out or "BOB_IRC_PASSWORD=<redacted>" in out
    assert "ghp_" not in out or "<redacted-token>" in out
    assert "<redacted>" in out or "<redacted-token>" in out


def test_signature_stable_for_same_frames():
    def boom():
        raise ValueError("first")

    try:
        boom()
    except ValueError as e1:
        tb1 = e1.__traceback__
        sig1 = crash_report.signature(type(e1), e1, tb1)

    def boom2():
        raise ValueError("second-different-message")

    try:
        boom2()
    except ValueError as e2:
        # Same function names/lines pattern may differ; compare same exception twice.
        sig_a = crash_report.signature(type(e2), e2, e2.__traceback__)
        sig_b = crash_report.signature(type(e2), e2, e2.__traceback__)
        assert sig_a == sig_b
        assert len(sig_a) == 16
        assert all(c in "0123456789abcdef" for c in sig_a)

    assert sig1 != "hookfail"
    assert len(sig1) == 16


def test_spool_on_post_fail(tmp_path, monkeypatch):
    def boom():
        raise RuntimeError("password=should-redact boom")

    try:
        boom()
    except RuntimeError as exc:
        def fail_post(title, body, *, repo, sig, exe):
            raise OSError("offline")

        result = crash_report.report_exception(
            "test-exe",
            type(exc),
            exc,
            exc.__traceback__,
            filer_post=fail_post,
        )
    assert result.get("ok") is False
    assert "spooled" in result
    path = Path(result["spooled"])
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "crash-sig:" in payload["body"]
    assert "password=<redacted>" in payload["body"] or "should-redact" not in payload["body"]
    assert payload["sig"] == result["sig"]


def test_post_success_no_spool(tmp_path, monkeypatch):
    seen = {}

    def ok_post(title, body, *, repo, sig, exe):
        seen["title"] = title
        seen["body"] = body
        seen["sig"] = sig
        seen["exe"] = exe
        return {"ok": True, "number": 1}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: None)

    try:
        raise KeyError("missing")
    except KeyError as exc:
        result = crash_report.report_exception(
            "bob-worker",
            type(exc),
            exc,
            exc.__traceback__,
            filer_post=ok_post,
        )
    assert result.get("ok") is True
    assert result.get("deduped") is False
    assert "crash-sig:" in seen["body"]
    assert seen["exe"] == "bob-worker"
    assert not list(Path(crash_report.spool_dir()).glob("crash-*.json"))


def test_flush_spool_sends_and_deletes(tmp_path, monkeypatch):
    spool = crash_report.spool_dir()
    spool.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": "crash: x RuntimeError abcd",
        "body": "crash-sig:abcd1234abcd1234\nwhat: test",
        "repo": "SimonBarnett/bobiverse",
        "sig": "abcd1234abcd1234",
        "exe": "x",
    }
    path = spool / "crash-abcd1234abcd1234-1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    posts = []

    def ok_post(title, body, *, repo, sig, exe):
        posts.append((title, sig, exe))
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: None)
    stats = crash_report.flush_spool(filer_post=ok_post)
    assert stats["sent"] == 1
    assert not path.exists()
    assert posts and posts[0][1] == "abcd1234abcd1234"


def test_install_hooks_idempotent(monkeypatch):
    monkeypatch.setattr(crash_report, "flush_spool", lambda **kw: {"sent": 0, "kept": 0, "dropped": 0})
    prev = sys.excepthook
    crash_report.install("unit-test-exe", flush=True)
    assert sys.excepthook is not prev
    hook1 = sys.excepthook
    crash_report.install("unit-test-exe", flush=True)
    assert sys.excepthook is hook1
    assert getattr(threading, "excepthook", None) is not None


def test_python_entries_call_install():
    entries = {
        "bob-worker": resolve("bob/scripts/bob_worker.py"),
        "bob-ear": resolve("scripts/irc_agent.py"),
        "jeeves": resolve("scripts/jeeves_main.py"),
        "airc": resolve("airc/scripts/airc_console_service.py"),
        "Watch-AgentHealth": resolve("bob/agentwatcher/watch_agent_health.py"),
    }
    for name, path in entries.items():
        text = path.read_text(encoding="utf-8")
        assert "import crash_report" in text, name
        assert f'crash_report.install("{name}")' in text or f"crash_report.install('{name}')" in text, name


def test_csharp_references_crashhook():
    hook = resolve("third_party/bob-tray/dialogs/CrashHook.cs")
    assert hook.is_file()
    hook_text = hook.read_text(encoding="utf-8-sig")
    assert "internal static class CrashHook" in hook_text
    assert "namespace BobDialogs" in hook_text
    assert "UnhandledException" in hook_text
    assert "ThreadException" in hook_text
    assert "crash-sig:" in hook_text
    assert "BOB_CRASH_SPOOL" in hook_text
    assert "Report-BobiverseIntakeIssue.ps1" in hook_text
    assert "FlushSpool" in hook_text
    assert "GH_TOKEN" in hook_text and "BOB_IRC_PASSWORD" in hook_text

    for rel, exe in (
        ("third_party/bob-tray/dialogs/BobAbout.cs", "bob-about"),
        ("third_party/bob-tray/dialogs/BobStatus.cs", "bob-status"),
        ("third_party/bob-tray/dialogs/BobTray.cs", "bob-tray"),
    ):
        text = resolve(rel).read_text(encoding="utf-8-sig")
        assert f'CrashHook.Install("{exe}")' in text, rel

    build = resolve("bob/scripts/Build-BobDialogs.ps1").read_text(encoding="utf-8-sig")
    assert "CrashHook.cs" in build


def test_format_report_includes_crash_sig():
    try:
        raise AssertionError("token=leak")
    except AssertionError as exc:
        title, body, sig = crash_report.format_report(
            exe="bob-tray",
            exc_type=type(exc),
            exc_value=exc,
            tb=exc.__traceback__,
            version="0.0-test",
        )
    assert f"crash-sig:{sig}" in body
    assert "token=<redacted>" in body or "leak" not in body
    assert title.startswith("crash: bob-tray")
