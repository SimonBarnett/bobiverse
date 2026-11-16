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


def test_nack_uses_launched_model_not_configured_hello(monkeypatch):
    line = "FROM jeeves #redqueen redqueen-8580: MRB SimonBarnett/bobiverse#7870 https://x"
    monkeypatch.setattr(
        bw, "resolve_seat_hello_model", lambda _kind, env=None: "opencode/deepseek-v4.1-flash-free"
    )
    import worker_start_model as wsm

    launched = bw.launched_hostile_start_model(
        "opencode", {wsm.ENV_ACTUAL_MODEL: "opencode-go/deepseek-v4-pro"}
    )
    assert launched == "opencode-go/deepseek-v4-pro"
    assert bw.opencode_skips_hostile_assign("opencode", line, start_model=launched) is False
    missing = bw.launched_hostile_start_model("opencode", {})
    assert bw.opencode_skips_hostile_assign("opencode", line, start_model=missing) is True
