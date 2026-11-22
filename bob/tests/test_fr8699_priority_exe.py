"""FR #8699 / BOB-50: Agents > Priority starts PriorityAgent.exe."""
from repo_layout import REPO

TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_priority_click_starts_priority_agent_exe():
    cs = TRAY.read_text(encoding="utf-8-sig")
    ps = WATCH.read_text(encoding="utf-8-sig")
    assert "StartPriorityExe()" in cs
    assert "vendor\\priority\\PriorityAgent.exe" in cs
    assert "action\", \"start exe\"" in cs
    assert "$miPriority.Add_Click({ Start-BobTrayPriorityExe })" in ps
    assert "vendor\\priority\\PriorityAgent.exe" in ps
    assert "Priority: start exe" in ps
