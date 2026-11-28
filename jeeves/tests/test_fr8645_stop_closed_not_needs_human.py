"""FR #8645: process-exit:stop-closed does not black out auto-offer."""
from __future__ import annotations

import bob.scripts.bob_worker as bw
import gitclaim


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
    src = bw.__file__
    text = open(src, encoding="utf-8").read()
    assert "$script:ocStopClosed = $false" in text
    assert "function Try-OpencodeSwitchToPaid" in text
    switch_body = text.split("function Try-OpencodeSwitchToPaid", 1)[1].split("function ", 1)[0]
    assert "return $false" in switch_body
    assert "opencode switch-to-paid model=" not in switch_body
    assert "-not $script:ocStopClosed" in text
    assert "Write-OpencodeJobGiveup $jobKey 'process-exit:stop-closed'" in text
