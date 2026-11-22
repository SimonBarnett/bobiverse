"""FR #8884: startup hover must not scan Win32_Process or peer-peek."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"


def test_fr8884_startup_calls_local_only():
    watch = WATCH.read_text(encoding="utf-8-sig")
    start = watch.index("-Name 'startup-update-hover' -Root $RepoRoot")
    window = watch[start:start + 1800]
    assert "Get-BobTrayHover -LocalOnly" in window


def test_fr8884_local_only_skips_cim_and_peeks():
    text = HOVER.read_text(encoding="utf-8-sig")
    fn = text.index("function Get-BobTrayHover {")
    nxt = text.find("\nfunction ", fn + 10)
    body = text[fn:nxt if nxt != -1 else None]
    assert "param([switch]$LocalOnly)" in body
    assert body.count("if (-not $LocalOnly)") >= 2
    live = body.index("Get-BobLiveGrokAgents")
    assert body.rfind("if (-not $LocalOnly)", 0, live) != -1
    peek = body.index("Read-BobPeerPeek")
    assert body.rfind("if (-not $LocalOnly)", 0, peek) != -1
