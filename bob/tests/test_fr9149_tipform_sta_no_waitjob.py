# -*- coding: utf-8 -*-
"""FR #9149: TipForm poll must not Wait-Job / double Get-BobTrayHover on the STA."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
if not WATCH.is_file():
    WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"


def _watch() -> str:
    assert WATCH.is_file(), WATCH
    return WATCH.read_text(encoding="utf-8-sig")


def _tipform_poll_branch(text: str) -> str:
    """Slice the TipForm (-not $engine) worker-sync / update-hover / irc-status area."""
    start = text.index("$poll.Add_Tick")
    end = text.index("$script:trayWorkerSyncTimer", start)
    return text[start:end]


def test_fr9149_tipform_skips_waitjob_update_hover():
    t = _watch()
    poll = _tipform_poll_branch(t)
    assert "tipform-ui-no-waitjob" in poll
    marker = "step-skip name=update-hover reason=tipform-ui-no-waitjob"
    assert marker in poll
    # Paint from tray-status.json within ~400 chars of the skip (same TipForm arm).
    paint_at = poll.index("Update-BobTrayTipFromStatusSnapshot", poll.index(marker))
    assert paint_at - poll.index(marker) < 400
    # TipForm must not Wait-Job update-hover via EngineStep.
    assert "Invoke-BobTrayEngineStep -Name 'update-hover'" not in poll


def test_fr9149_tipform_skips_worker_sync_when_armed():
    t = _watch()
    assert "trayWorkerSyncArmed" in t
    poll = _tipform_poll_branch(t)
    assert "tipform-ui-threadpool" in poll
    assert "step-skip name=worker-sync" in poll


def test_fr9149_tipform_skips_irc_status_when_digest_armed():
    t = _watch()
    assert "trayDigestArmed" in t
    poll = _tipform_poll_branch(t)
    assert "step-skip name=irc-status" in poll


def test_fr9149_update_hover_accepts_hover_param():
    t = _watch()
    fn = t[t.index("function Update-Hover") : t.index("function Update-Hover") + 900]
    assert "$Hover" in fn or "Hover =" in fn
    assert "Get-BobTrayHover" in fn
    # When Hover supplied, must not always fetch first
    assert "if ($null -eq $h)" in fn or "if ($null -eq $Hover)" in fn or "$Hover = $null" in fn


def test_fr9149_digest_timer_runs_for_tipform():
    t = _watch()
    # Early return that skipped TipForm must be gone
    dig = t[t.index("$script:trayDigestSub = Register-ObjectEvent") : t.index("$script:trayDigestSub = Register-ObjectEvent") + 2200]
    assert "if (-not (Test-BobTrayEngineMode)) { return }" not in dig
    assert "FR #9149" in dig or "TipForm" in dig


def test_fr9149_invoke_status_no_inline_hover_fetch():
    t = _watch()
    fn = t[t.index("function Invoke-BobTrayStatus") : t.index("function Invoke-BobTrayStatus") + 1200]
    # Must not call bare Update-Hover without -Hover on the click path
    assert "Update-BobTrayTipFromStatusSnapshot" in fn
    assert "Update-Hover -Hover" in fn or "lastHoverObject" in fn
