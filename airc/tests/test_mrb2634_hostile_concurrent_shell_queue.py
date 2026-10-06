"""MRB #2634 hostile gates for FR #2632 concurrent shell queue + busy retry."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import airc_console as ac
from repo_layout import ROOT


def test_mrb2634_shell_pending_max_default_eight():
    assert ac.SHELL_PENDING_MAX == 8
    runner = ac.ShellJobRunner(on_reply=lambda *_: None, wait=False)
    assert runner.pending_max == 8


def test_mrb2634_three_queued_commands_all_done():
    """One in flight + two pending must all emit their own DONE (no busy)."""
    seen: list[str] = []
    lock = threading.Lock()

    def capture(_nick: str, line: str) -> None:
        with lock:
            seen.append(line)

    runner = ac.ShellJobRunner(on_reply=capture, wait=False, timeout_s=30, pending_max=4)
    ids = ("aaaaaaaa", "bbbbbbbb", "cccccccc")
    for jid in ids:
        runner.start(
            "bob-tm",
            f'id={jid} Write-Output "{jid}-ok"; Start-Sleep -Milliseconds 150',
        )

    deadline = time.time() + 20
    while time.time() < deadline:
        with lock:
            if all(any(x == f"DONE id={jid} exit=0" for x in seen) for jid in ids):
                break
        time.sleep(0.05)

    with lock:
        for jid in ids:
            assert any(x == f"DONE id={jid} exit=0" for x in seen), (jid, seen)
        assert not any("busy" in x.lower() for x in seen), seen


def test_mrb2634_docs_utf8_no_bom_and_queue_cues():
    doc = ROOT / "airc/docs/airc-remote-control.md"
    raw = doc.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM on airc-remote-control.md"
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    assert "FR #2632" in text
    assert "queued" in text.lower()
    assert "busy: prior shell still emitting" in text
    ps1 = (ROOT / "airc/scripts/Invoke-AircRemote.ps1").read_text(encoding="utf-8-sig")
    assert "MaxRetries" in ps1


def test_mrb2634_invoke_busy_retry_helper_present():
    ps1 = (ROOT / "airc/scripts/Invoke-AircRemote.ps1").read_text(encoding="utf-8-sig")
    assert "function Test-AircRemoteBusyReply" in ps1
    assert "busy:\\s*prior shell" in ps1
    assert "busyRetryActions" in ps1
    assert "pinnedJobId" in ps1
    skill = (ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md").read_text(encoding="utf-8")
    assert "FR #2632" in skill
    assert "SHELL_PENDING_MAX" in skill
