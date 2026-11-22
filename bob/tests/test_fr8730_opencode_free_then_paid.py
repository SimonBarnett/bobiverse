"""FR #8730 / BOB-27: Open Code prefers free, then paid when free is exhausted."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fr8730_paid_when_free_exhausted():
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    ps1 = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    gate = (ROOT / "bob" / "tray" / "dialogs" / "OpencodeFreeThenPaid.cs").read_text(encoding="utf-8")
    assert 'return "paid"' in gate
    assert 'return "free"' in gate
    assert "free-exhausted" in cs
    assert "workers-opencode slot=paid reason=free-exhausted" in ps1
    assert "workers-opencode slot=free" in ps1
    start = ps1.index("elseif ($picked -eq 'opencode')")
    slot = ps1.index("workers-opencode slot=paid reason=free-exhausted", start)
    launch = ps1.index("Start-BobTrayWorkerExe -Mode 'agent' -Agent 'opencode'", slot)
    assert slot < launch
