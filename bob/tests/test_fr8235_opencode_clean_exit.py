"""FR #8235: OpenCode exit 0 with no DONE continues once, then GIVEUP clean-exit-no-done."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr8235_launcher_continues_once_then_giveup_clean_exit():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "$script:ocCleanExitTries = 0" in src
    assert "opencode-clean-exit: continuation 1/1 (exit 0, no DONE)" in src
    assert "opencode-clean-exit: GIVEUP clean-exit-no-done" in src
    assert "Write-OpencodeJobGiveup $jobKey 'clean-exit-no-done'" in src
    # A null exit code must not become process-exit exit 0 ($null -ne 0).
    assert "Only a known nonzero code is an error." in src
    assert "if (-not $teClass -and $exitKnown -and $codeNum -ne 0)" in src
