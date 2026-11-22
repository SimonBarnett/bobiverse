"""FR #9046: Watch refreshes tray-digest-pools when bob-tray.exe is parked."""
from pathlib import Path

WATCH = Path(__file__).resolve().parents[1] / "tray" / "tools" / "Watch-BobTray.ps1"


def test_watch_poll_refreshes_digest_pools_outside_engine_mode():
    text = WATCH.read_text(encoding="utf-8-sig")
    assert "function Update-BobTrayWatchDigestPools" in text
    assert "Update-BobTrayDigestPools.ps1" in text
    start = text.index("FR #9046: exe timer is absent")
    window = text[start : start + 250]
    assert "Update-BobTrayWatchDigestPools" in window
