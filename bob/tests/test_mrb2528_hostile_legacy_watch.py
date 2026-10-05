"""MRB #2528 hostile: legacy Watch-AgentHealth gated when bob-worker is active (FR #2523)."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
START_WORKER = ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1"
WATCHER = ROOT / "bob" / "agentwatcher" / "Watch-AgentHealth.ps1"
INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"
TIP_TEST = ROOT / "bob" / "tests" / "test_fr2523_legacy_watch_vs_bob_worker.py"


def test_mrb2528_tray_sources_start_worker_before_agent_gates():
    text = TRAY.read_text(encoding="utf-8")
    helper_idx = text.index("BobTrayStartWorker.ps1")
    start_idx = text.index("function Start-BobTrayAgentWatch")
    invoke_idx = text.index("function Invoke-BobTrayAgent")
    assert helper_idx < start_idx < invoke_idx


def test_mrb2528_start_and_invoke_both_refuse_when_active():
    text = TRAY.read_text(encoding="utf-8")
    for fn in ("function Start-BobTrayAgentWatch", "function Invoke-BobTrayAgent"):
        start = text.index(fn)
        block = text[start : start + 700]
        assert "Test-BobWorkerProductActive" in block
        assert "FR #2523" in block


def test_mrb2528_watcher_escape_hatch_and_default_throw():
    text = WATCHER.read_text(encoding="utf-8")
    assert "[switch]$AllowAlongsideBobWorker" in text
    assert "if (-not $AllowAlongsideBobWorker -and (Test-BobWorkerProductActive" in text
    assert "refuse Watch-AgentHealth shop start" in text


def test_mrb2528_measure_seats_excludes_watch_process_names():
    text = START_WORKER.read_text(encoding="utf-8")
    start = text.index("function Measure-BobTrayWorkerSeats")
    block = text[start : start + 450]
    assert "bob-worker(-[0-9a-f]+)?\\.exe" in block or r"^bob-worker(-[0-9a-f]+)?\.exe$" in block
    # Comment may mention legacy watch; process filter must still be bob-worker only.
    assert "Where-Object" in block
    assert re.search(r"Name\s+-match\s+'?\^bob-worker", block)


def test_mrb2528_install_skip_message_stable():
    text = INSTALL.read_text(encoding="utf-8")
    assert "INFO FR #2523 skip Desktop Watch-AgentHealth install" in text
    assert "worker\\bob-worker.exe" in text.replace("/", "\\")


def test_mrb2528_tip_test_utf8_no_bom_trailing_newline():
    raw = TIP_TEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    assert b"\x08" not in raw
