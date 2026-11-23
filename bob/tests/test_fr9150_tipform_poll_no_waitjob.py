"""FR #9150 / #9149: TipForm poll must not Wait-Job update-hover on the STA.

Deterministic exception Watch-BobTray.engine-step.update-hover timeoutSec=8
came from the TipForm (#9011 park) poll blocking on Invoke-BobTrayEngineStep
Wait-Job + a second Update-Hover Get-BobTrayHover. Productize RQ hotpatch:
skip worker-sync / update-hover Wait-Job / Write-BobIrcStatus on TipForm UI;
refresh snapshot off-thread; paint from tray-status.json only.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
DOCS = ROOT / "docs" / "bob-9150-tipform-poll-no-waitjob.md"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _poll_handler() -> str:
    w = _txt(WATCH)
    marker = "$poll.Add_Tick"
    open_idx = w.index("{", w.index(marker))
    depth = 0
    i = open_idx
    n = len(w)
    while i < n:
        c = w[i]
        if c == "'":
            i += 1
            while i < n and w[i] != "'":
                i += 1
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return w[open_idx : i + 1]
        i += 1
    raise AssertionError("poll Add_Tick unclosed")


def _tipform_branch(poll: str) -> str:
    """Body of the TipForm ``if (-not $engine)`` block that previously Wait-Job'd hover."""
    assert "FR #9150" in poll or "FR #9149" in poll
    # Prefer the TipForm skip markers.
    assert "tipform-ui-threadpool" in poll or "tipform-ui-snapshot" in poll
    return poll


def test_fr9150_tipform_skips_update_hover_engine_step():
    poll = _poll_handler()
    tip = _tipform_branch(poll)
    # Must not Wait-Job update-hover on TipForm STA (the #9150 timeout site).
    assert "step-skip name=update-hover" in tip
    # The blocking EngineStep name='update-hover' must not remain in TipForm branch.
    # Engine mode still has update-hover-engine.
    assert "update-hover-engine" in poll
    # TipForm branch: no Invoke-BobTrayEngineStep -Name 'update-hover'
    # Isolate TipForm arm: from first "if (-not $engine)" through its matching else for hover.
    idx = tip.index("if (-not $engine)")
    # Find update-hover-engine which lives in the else (engine) arm.
    eng = tip.index("update-hover-engine", idx)
    tip_arm = tip[idx:eng]
    assert "Invoke-BobTrayEngineStep -Name 'update-hover'" not in tip_arm
    assert "step-skip name=update-hover" in tip_arm


def test_fr9150_tipform_skips_worker_sync_and_digest_on_ui():
    poll = _poll_handler()
    assert "step-skip name=worker-sync" in poll
    assert "tipform-ui-threadpool" in poll
    assert "step-skip name=digest-status" in poll or "step-skip name=write-bob-irc-status" in poll
    # ThreadPool timers remain the owners
    w = _txt(WATCH)
    assert "trayWorkerSyncTimer" in w
    assert "trayDigestTimer" in w


def test_fr9150_tipform_paints_from_snapshot_not_second_hover():
    poll = _poll_handler()
    tip = poll[poll.index("if (-not $engine)") : poll.index("update-hover-engine")]
    assert "FromSnapshot" in tip or "Update-BobTrayTipFormFromSnapshot" in tip or "update-hover-ui" in tip
    # Must not call bare Update-Hover (second Get-BobTrayHover) after a TipForm skip.
    # Allow Update-Hover -FromSnapshot.
    bare = re.findall(r"Update-Hover(?!\s*-FromSnapshot)", tip)
    # Filter comments
    bare = [b for b in bare if True]
    assert not any(
        line.strip().startswith("Update-Hover") and "-FromSnapshot" not in line
        for line in tip.splitlines()
        if "Update-Hover" in line and not line.strip().startswith("#")
    ), tip


def test_fr9150_offthread_hover_refresh_exists():
    w = _txt(WATCH)
    assert "FR #9150" in w
    assert (
        "trayHoverTimer" in w
        or "Start-BobTrayTipFormHoverRefresh" in w
        or "tipFormHover" in w
    )


def test_fr9150_update_hover_from_snapshot_helper():
    w = _txt(WATCH)
    assert "FromSnapshot" in w
    assert "tray-status.json" in w
    # function Update-Hover still present for Status click / attention paths
    assert "function Update-Hover" in w


def test_fr9150_evidence_doc():
    assert DOCS.is_file()
    t = DOCS.read_text(encoding="utf-8")
    assert "FR #9150" in t
    assert "9149" in t
    assert "Wait-Job" in t or "update-hover" in t
    assert "tipform" in t.lower() or "TipForm" in t
