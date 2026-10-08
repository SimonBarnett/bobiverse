"""FR #3452: local_only / opt-out spool payloads must never POST on later flush.

Root cause of crash intake twins #3452/#3453 (sig 2039079cdce4f5c7):
report_exception under BOB_CRASH_REPORT=0 wrote local_only spool; a later
flush_spool with policy.send true posted it to intake as a real crash.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from repo_layout import REPO, resolve

SCRIPTS = REPO / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import crash_report  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    spool = tmp_path / "crash-spool"
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(spool))
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    monkeypatch.delenv("BOB_CRASH_REPORT_CONFIG", raising=False)
    monkeypatch.delenv("BOB_INTAKE_URL", raising=False)
    crash_report._installed_for = None
    crash_report._policy_cache = None
    yield spool


def test_fr3452_flush_drops_local_only_flag_when_send_true(tmp_path, monkeypatch):
    """Payload stamped local_only=True must be deleted, never POSTed, when send is on."""
    spool = Path(os.environ["BOB_CRASH_SPOOL"])
    spool.mkdir(parents=True, exist_ok=True)
    path = spool / "crash-2039079cdce4f5c7-1.json"
    path.write_text(
        json.dumps(
            {
                "title": "crash: bob-tray RuntimeError 2039079cdce4f5c7",
                "body": "crash-sig:2039079cdce4f5c7\nexception: RuntimeError: fr3328-parity\n",
                "repo": "SimonBarnett/bobiverse",
                "sig": "2039079cdce4f5c7",
                "exe": "bob-tray",
                "local_only": True,
                "ts": "2026-10-08T11:44:46Z",
            }
        ),
        encoding="utf-8",
    )
    posts = []

    def ok_post(title, body, *, repo, sig, exe):
        posts.append((title, sig, exe))
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: None)
    # policy.send true (default after delenv)
    stats = crash_report.flush_spool(filer_post=ok_post)
    assert stats["sent"] == 0
    assert stats["dropped"] >= 1
    assert posts == []
    assert not path.exists()


def test_fr3452_flush_drops_csharp_error_local_only_when_send_true(tmp_path, monkeypatch):
    """C# WriteSpool stamps error=local_only (no local_only bool) — same never-POST rule."""
    spool = Path(os.environ["BOB_CRASH_SPOOL"])
    spool.mkdir(parents=True, exist_ok=True)
    path = spool / "crash-csharp-optout-1.json"
    path.write_text(
        json.dumps(
            {
                "title": "crash: bob-tray RuntimeError abcd",
                "body": "crash-sig:abcd\n",
                "repo": "SimonBarnett/bobiverse",
                "sig": "abcd",
                "exe": "bob-tray",
                "error": "local_only",
                "ts": "2026-10-08T11:44:46Z",
            }
        ),
        encoding="utf-8",
    )
    posts = []

    def ok_post(title, body, *, repo, sig, exe):
        posts.append((title, sig, exe))
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: None)
    stats = crash_report.flush_spool(filer_post=ok_post)
    assert stats["sent"] == 0
    assert stats["dropped"] >= 1
    assert posts == []
    assert not path.exists()


def test_fr3452_opt_out_then_reenable_never_posts_local_only(tmp_path, monkeypatch):
    """End-to-end: report under opt-out, then flush after re-enable — no intake."""
    monkeypatch.setenv("BOB_CRASH_REPORT", "0")
    crash_report._policy_cache = None
    try:
        raise RuntimeError("fr3452-parity")
    except RuntimeError as exc:
        with mock.patch("crash_report.urllib.request.urlopen") as urlopen:
            result = crash_report.report_exception(
                "bob-tray", type(exc), exc, exc.__traceback__
            )
    assert result.get("local_only") is True
    spooled = Path(result["spooled"])
    assert spooled.is_file()
    payload = json.loads(spooled.read_text(encoding="utf-8"))
    assert payload.get("local_only") is True

    # Re-enable send (same process / next start without opt-out).
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    crash_report._policy_cache = None
    posts = []

    def ok_post(title, body, *, repo, sig, exe):
        posts.append(sig)
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: None)
    stats = crash_report.flush_spool(filer_post=ok_post)
    assert stats["sent"] == 0
    assert posts == []
    assert not spooled.exists()


def test_fr3452_flush_still_sends_real_offline_spool(tmp_path, monkeypatch):
    """post_failed / network spool (no local_only) still flushes when send is on."""
    spool = Path(os.environ["BOB_CRASH_SPOOL"])
    spool.mkdir(parents=True, exist_ok=True)
    path = spool / "crash-real-offline-1.json"
    path.write_text(
        json.dumps(
            {
                "title": "crash: airc RuntimeError real",
                "body": "crash-sig:realoffline1\n",
                "repo": "SimonBarnett/bobiverse",
                "sig": "realoffline1",
                "exe": "airc",
                "error": "post_failed",
            }
        ),
        encoding="utf-8",
    )
    posts = []

    def ok_post(title, body, *, repo, sig, exe):
        posts.append(sig)
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: None)
    stats = crash_report.flush_spool(filer_post=ok_post)
    assert stats["sent"] == 1
    assert posts == ["realoffline1"]
    assert not path.exists()


def test_fr3452_csharp_flush_drops_local_only_source_gate():
    """CrashHook.FlushSpool must drop local_only / error=local_only payloads (never TryPostIntake)."""
    text = resolve("third_party/bob-tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")
    assert "FR #3452" in text
    flush = text.split("public static void FlushSpool", 1)[1]
    # Must inspect payload for local_only before posting.
    assert "local_only" in flush.lower() or 'error")' in flush
    assert "local_only" in flush
    # Drop path deletes without TryPostIntake for opt-out stamps.
    assert "TryPostIntake" in flush
    # WriteSpool for opt-out should stamp local_only bool (parity with Python).
    write = text.split("static void WriteSpool", 1)[1]
    assert 'local_only' in write
