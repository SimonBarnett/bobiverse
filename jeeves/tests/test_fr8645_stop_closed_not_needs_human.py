"""FR #8645: process-exit:stop-closed does not black out auto-offer."""
from __future__ import annotations

import gitclaim
from repo_layout import REPO

WORKER = REPO / "bob" / "scripts" / "bob_worker.py"


def test_stop_closed_is_infra_soft_and_does_not_block():
    reason = "process-exit:stop-closed"
    assert gitclaim.is_stop_closed_giveup_reason(reason)
    assert gitclaim.is_infra_soft_giveup_reason(reason)
    row = {
        "needs_human": True,
        "giveup_reason": reason,
        "giveup_seats": "flamingo-9880",
    }
    assert gitclaim.row_needs_human(row, "redqueen-5764") is False
    assert gitclaim.row_has_false_needs_human(row) is True
    product = dict(row, giveup_reason="cannot review")
    assert gitclaim.row_needs_human(product, "redqueen-5764") is True


def test_stop_closed_script_does_not_switch_or_epipe_retry():
    """The launcher clears stop-closed before each run and will not switch to paid."""
    assert WORKER.is_file(), f"missing canonical worker source: {WORKER}"
    text = WORKER.read_text(encoding="utf-8")
    assert len(text) > 50_000, "bob_worker.py source too short; not the OpenCode launcher tree"
    assert "$script:ocStopClosed = $false" in text
    assert "if ($script:ocStopClosed) { return $false }" in text
    assert "-not $script:ocStopClosed" in text
    assert "Write-OpencodeJobGiveup $jobKey 'process-exit:stop-closed'" in text
