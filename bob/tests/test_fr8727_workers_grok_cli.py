"""FR #8727 / BOB-16: Workers > Grok starts the Grok CLI seat and logs it."""
from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_workers_grok_logs_and_starts_grok_agent():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert 'action", "grok CLI start"' in cs
    assert 'StartWorker("agent", "grok"' in cs
    assert "Workers Grok: grok CLI start" in ps
    assert "-Agent 'grok'" in ps and "-Trigger 'workers-grok'" in ps
