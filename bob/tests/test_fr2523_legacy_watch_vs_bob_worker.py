"""FR #2523: Watch-AgentHealth must not shop-start when bob-worker is the active product."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
START_WORKER = ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1"
WATCHER = ROOT / "bob" / "agentwatcher" / "Watch-AgentHealth.ps1"
INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"


def test_fr2523_tray_agent_click_uses_bob_worker_not_watch():
    text = TRAY.read_text(encoding="utf-8")
    # Top-level Agent menu must start bob-worker (t762u).
    assert "Start-BobTrayWorkerExe -Mode 'agent'" in text
    assert re.search(
        r"\$miAgents\s*=\s*\$menu\.Items\.Add\('Agent'\)\s*\n\$miAgents\.Add_Click\(\{\s*Start-BobTrayWorkerExe",
        text,
    )


def test_fr2523_start_watch_gated_when_bob_worker_active():
    text = TRAY.read_text(encoding="utf-8")
    assert "FR #2523" in text
    assert "Test-BobWorkerProductActive" in text
    start = text.index("function Start-BobTrayAgentWatch")
    block = text[start : start + 900]
    assert "Test-BobWorkerProductActive" in block
    assert "bob-worker" in block.lower()


def test_fr2523_invoke_agent_gated():
    text = TRAY.read_text(encoding="utf-8")
    start = text.index("function Invoke-BobTrayAgent")
    block = text[start : start + 500]
    assert "Test-BobWorkerProductActive" in block


def test_fr2523_cap_counts_only_bob_worker():
    text = START_WORKER.read_text(encoding="utf-8")
    assert "Measure-BobTrayWorkerSeats" in text
    assert r"^bob-worker(-[0-9a-f]+)?\.exe$" in text
    block = text[
        text.index("function Measure-BobTrayWorkerSeats") : text.index(
            "function Measure-BobTrayWorkerSeats"
        )
        + 400
    ]
    # Filter must only match bob-worker*.exe process names.
    assert "bob-worker" in block
    assert "Where-Object" in block


def test_fr2523_watch_agent_health_refuses_alongside_bob_worker():
    text = WATCHER.read_text(encoding="utf-8")
    assert "FR #2523" in text
    assert "Test-BobWorkerProductActive" in text or "bob-worker.exe" in text
    assert "AllowAlongsideBobWorker" in text


def test_fr2523_install_skips_desktop_watch_when_bob_worker_present():
    text = INSTALL.read_text(encoding="utf-8")
    assert "FR #2523" in text
    assert "skip Desktop Watch-AgentHealth install" in text
    assert "bob-worker.exe present" in text
    assert "worker\\bob-worker.exe" in text or "worker\\bob-worker.exe" in text.replace(
        "/", "\\"
    )
