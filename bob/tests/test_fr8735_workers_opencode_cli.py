"""FR #8735 / BOB-26: Workers > Open Code starts the OpenCode CLI seat and logs it."""
from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_workers_opencode_logs_and_starts_opencode_agent():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert 'action", "opencode CLI start"' in cs
    assert 'StartWorker("agent", "opencode", env, slot)' in cs
    assert "Workers Open Code: opencode CLI start" in ps
    assert "-Agent 'opencode'" in ps and "-Trigger 'workers-opencode'" in ps
