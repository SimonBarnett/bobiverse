"""FR #9034: TipForm Exit must not stop ircBob."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
LIFE = ROOT / "tray" / "tools" / "BobTrayLifecycle.ps1"
CS = ROOT / "tray" / "dialogs" / "BobTray.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_ps_exit_omits_stop_service():
    text = _txt(WATCH)
    assert "FR #9034" in text
    # Invoke-BobTrayExit must not pass -StopService
    start = text.find("function Invoke-BobTrayExit")
    end = text.find("function Get-BobTrayCursorHelpTooltip", start)
    block = text[start:end]
    assert "-StopService" not in block
    assert "Stop-BobTrayService" not in block
    assert "ircBob left running" in block or "left running" in block.lower()


def test_exit_sequence_stop_optional():
    text = _txt(LIFE)
    assert "FR #9034" in text
    assert "[scriptblock]$StopService = $null" in text
    assert "do not stop ircBob on TipForm Exit" in text


def test_csharp_exit_no_sc_stop():
    text = _txt(CS)
    start = text.find("void ExitTray()")
    end = text.find("void Restart()", start)
    block = text[start:end]
    assert "stop ircBob" not in block
    assert 'Command("exit")' in block
    assert "FR #9034" in text


def test_docs_exit_leaves_ear():
    text = _txt(DOCS)
    assert "FR #9034" in text
    assert "never** stops the ircBob" in text or "never stops the ircBob" in text.replace("*", "")
