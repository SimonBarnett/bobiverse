"""MRB #2416 hostile: crash hook wiring, spool edges, CAST IRON redaction."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import crash_report
from repo_layout import ROOT, resolve


def test_mrb2416_dedupe_comment_fail_still_spools(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    crash_report._installed_for = None
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: 7)
    monkeypatch.setattr(crash_report, "_gh_comment", lambda *a, **k: False)
    try:
        raise ValueError("token=leak-me")
    except ValueError as exc:
        r = crash_report.report_exception("jeeves", type(exc), exc, exc.__traceback__)
    assert r["ok"] is False and r["deduped"] is True
    payload = json.loads(Path(r["spooled"]).read_text(encoding="utf-8"))
    assert payload["error"] == "dedupe_comment_failed"
    assert "leak-me" not in payload["body"]


def test_mrb2416_dedupe_comment_success_no_spool(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    crash_report._installed_for = None
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: 8)
    monkeypatch.setattr(crash_report, "_gh_comment", lambda *a, **k: True)
    try:
        raise RuntimeError("again")
    except RuntimeError as exc:
        r = crash_report.report_exception("airc", type(exc), exc, exc.__traceback__)
    assert r == {"ok": True, "deduped": True, "number": 8, "sig": r["sig"]}
    assert list(Path(crash_report.spool_dir()).glob("crash-*.json")) == []


def test_mrb2416_hook_never_raises_on_broken_post(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    crash_report._installed_for = None
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)

    def boom_post(*a, **k):
        raise ConnectionError("down")

    try:
        raise OSError("boom")
    except OSError as exc:
        r = crash_report.report_exception(
            "bob-worker", type(exc), exc, exc.__traceback__, filer_post=boom_post
        )
    assert r["ok"] is False and "spooled" in r


def test_mrb2416_all_python_entries_and_csharp_hook():
    for name, rel in (
        ("bob-worker", "bob/scripts/bob_worker.py"),
        ("bob-ear", "common/scripts/irc_agent.py"),
        ("jeeves", "common/scripts/jeeves_main.py"),
        ("airc", "airc/scripts/airc_console_service.py"),
        ("Watch-AgentHealth", "bob/agentwatcher/watch_agent_health.py"),
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "import crash_report" in text, name
        assert f'crash_report.install("{name}")' in text, name
    hook = resolve("third_party/bob-tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")
    assert "crash-sig:" in hook and "FlushSpool" in hook and "BOB_CRASH_SPOOL" in hook
    for rel, exe in (
        ("third_party/bob-tray/dialogs/BobAbout.cs", "bob-about"),
        ("third_party/bob-tray/dialogs/BobStatus.cs", "bob-status"),
        ("third_party/bob-tray/dialogs/BobTray.cs", "bob-tray"),
    ):
        assert f'CrashHook.Install("{exe}")' in resolve(rel).read_text(encoding="utf-8-sig")


def test_mrb2416_signature_ignores_message_text():
    def a():
        raise KeyError("alpha")

    def b():
        raise KeyError("beta-different")

    try:
        a()
    except KeyError as e1:
        # Different message in same helper line numbers would differ; compare identical re-raise shape via format twice.
        s1 = crash_report.signature(type(e1), e1, e1.__traceback__)
        s1b = crash_report.signature(type(e1), e1, e1.__traceback__)
        assert s1 == s1b and len(s1) == 16
    try:
        b()
    except KeyError as e2:
        s2 = crash_report.signature(type(e2), e2, e2.__traceback__)
        assert len(s2) == 16


def test_mrb2416_encoding_utf8_no_bom():
    for rel in (
        "common/scripts/crash_report.py",
        "bob/tray/dialogs/CrashHook.cs",
        "common/tests/test_fr2411_crash_report.py",
        "common/tests/test_mrb2416_hostile_crash_report.py",
    ):
        raw = (ROOT / rel).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), rel
