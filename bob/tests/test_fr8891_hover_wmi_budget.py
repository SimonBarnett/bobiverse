"""FR #8891: update-hover-engine live grok WMI must use EnumerationOptions.Timeout."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOVER = ROOT / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def _fn(text: str, name: str) -> str:
    start = text.find(f"function {name}")
    assert start >= 0, name
    nxt = text.find("\nfunction ", start + 1)
    return text[start:] if nxt < 0 else text[start:nxt]


def test_fr8891_live_grok_uses_timed_wmi():
    text = HOVER.read_text(encoding="utf-8-sig")
    helper = _fn(text, "Get-BobWin32ProcessTimed")
    assert "EnumerationOptions" in helper
    assert "FromSeconds" in helper
    assert "ManagementObjectSearcher" in helper
    body = _fn(text, "Get-BobLiveGrokAgents")
    assert "Get-BobWin32ProcessTimed" in body
    assert "Name='grok.exe'" in body
    assert "BOB_LIVE_GROK_WMI_TIMEOUT_SEC" in body
    # No unbounded Get-CimInstance Win32_Process inside live grok.
    assert "Get-CimInstance Win32_Process" not in body


def test_fr8891_update_hover_engine_still_wired():
    watch = WATCH.read_text(encoding="utf-8-sig")
    assert "-Name 'update-hover-engine'" in watch
    assert "Get-BobTrayHover" in watch
