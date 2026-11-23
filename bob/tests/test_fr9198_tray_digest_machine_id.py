# -*- coding: utf-8 -*-
"""FR #9198: trayDigestTimer Action must load Get-ThisMachineId (BobBridge) for Write-BobIrcStatus."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
IRC = ROOT / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"


def _txt(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_fr9198_digest_msg_includes_psd1():
    w = _txt(WATCH)
    start = w.index("$script:trayDigestTimer = New-Object System.Timers.Timer")
    block = w[start : start + 5500]
    assert "FR #9198" in block
    assert "BobBridge.psd1" in block or "Psd1" in block
    assert "Import-Module" in block
    assert "Get-ThisMachineId" in block
    # Prefer module import over bare Get-BobIrc dot when Public helpers missing.
    assert "Get-Command Get-ThisMachineId" in block or "Get-ThisMachineId -ErrorAction" in block


def test_fr9198_write_status_soft_fails_missing_machine_id():
    irc = _txt(IRC)
    fn = irc[irc.index("function Write-BobIrcStatus") : irc.index("function Write-BobIrcStatus") + 900]
    assert "FR #9198" in fn
    # Must not bare-call Get-ThisMachineId without try/catch (CommandNotFound -> RuntimeError intake).
    assert "try { $id = Get-ThisMachineId }" in fn
    assert "catch { $id = $null }" in fn


def test_fr9198_bob_skill_pins_digest_import():
    assert SKILL.is_file(), SKILL
    s = _txt(SKILL)
    assert "FR #9198" in s
    assert "Get-ThisMachineId" in s
    assert "Import-Module" in s or "BobBridge" in s
