from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "bob" / "scripts" / "Start-BobTrayInteractive.ps1"
INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"


def test_tray_registers_interactive_logon_task_with_fallback():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "TaskName = 'BobiverseTray'" in text
    assert "New-ScheduledTaskTrigger -AtLogOn" in text
    assert "-LogonType Interactive" in text
    assert "/SC ONLOGON" in text and "/IT" in text
    # A failed ScheduledTasks API call must reach the schtasks fallback.
    assert "Register-ScheduledTask -TaskName $TaskName" in text
    assert "-ErrorAction Stop" in text
    assert "schtasks /Create" in text


def test_install_registers_task_in_interactive_and_session0_paths():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "Start-BobTrayInteractive" in text
    assert "-RunNow" in text
    assert "-RegisterOnly" in text
