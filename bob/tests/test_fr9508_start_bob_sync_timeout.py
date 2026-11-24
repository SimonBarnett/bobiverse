"""FR #9508: Start-Bob must not hang forever on Sync/Update before bob-ear."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

START = ROOT / "bob" / "scripts" / "Start-Bob.ps1"


def test_fr9508_start_bob_sync_out_of_process_with_timeout():
    raw = START.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "FR #9508" in text
    # Sync + Update must not be bare in-process & $sync / & $updater (hangs nssm).
    block_start = text.index("no-update-guard")
    block_end = text.index("Select-BobEarLaunch")
    block = text[block_start:block_end]
    assert "Start-Process" in block
    assert "WaitForExit" in block
    assert "taskkill" in block.lower() or "/T" in block
    assert "BOB_START_SYNC_TIMEOUT_SEC" in block or "SyncTimeoutSec" in block
    # BOBIVERSE_NO_UPDATE still suppresses both before either begins.
    assert "Get-BobiverseNoUpdateReason" in text
    assert "sync=suppressed" in text
    # Ear launch still after sync/update block.
    assert text.index("Select-BobEarLaunch") > text.index("FR #9508")


def test_fr9508_comments_say_never_block_ear():
    text = START.read_text(encoding="utf-8")
    assert "bob-ear" in text.lower()
    assert "timeout" in text.lower()
