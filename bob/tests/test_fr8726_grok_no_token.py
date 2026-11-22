"""FR #8726 / BOB-18: Workers > Grok quits on an empty local fuel file."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fr8726_sources_quit_before_grok_start():
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    ps1 = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    gate = (ROOT / "bob" / "tray" / "dialogs" / "GrokNoTokenGate.cs").read_text(encoding="utf-8")
    assert "No tokens on this box. Grok will quit." in gate
    assert "grok-fuel.json" in gate
    assert "dialog-quit" in cs and "no-tokens" in cs
    grok = cs.split('id, "grok"', 1)[1].split("else if", 1)[0]
    assert grok.index("ShouldQuit") < grok.index("StartWorker")
    assert "workers-grok dialog-quit reason=no-tokens" in ps1
    block = ps1.split("elseif ($picked -eq 'grok')", 1)[1].split("elseif ($picked -eq 'opencode')", 1)[0]
    assert block.index("return") < block.index("Start-BobTrayWorkerExe")
