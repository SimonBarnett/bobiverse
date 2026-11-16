"""FR #7888: a paid OpenCode start_model does not NACK MRB."""
from __future__ import annotations

import bob_worker as bw


def test_paid_start_model_accepts_mrb():
    line = "FROM jeeves #redqueen redqueen-8580: MRB SimonBarnett/bobiverse#7870 https://x"
    assert bw.opencode_skips_hostile_assign(
        "opencode", line, start_model="opencode-go/deepseek-v4-pro"
    ) is False
    assert bw.opencode_skips_hostile_assign(
        "opencode", line, start_model="opencode/deepseek-v4.1-flash-free"
    ) is True
    assert bw.opencode_skips_hostile_assign("opencode", line, start_model="$model") is True
    assert bw.opencode_skips_hostile_assign("opencode", line) is True
    fr = "FROM jeeves #redqueen redqueen-8580: FR SimonBarnett/bobiverse#7888 https://x"
    assert bw.opencode_skips_hostile_assign(
        "opencode", fr, start_model="opencode/deepseek-v4.1-flash-free"
    ) is False
