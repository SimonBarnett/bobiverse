"""FR #8159: env/tray pin is configured; false model_mismatch must stop."""
from __future__ import annotations

import bob_worker as bw
import worker_start_model as wsm

GO = "opencode-go/deepseek-v4-pro"
FREE = "opencode/deepseek-v4.1-flash-free"

CFG = {
    "workerStartModels": {
        "grok": "EXAMPLE_GROK_MIN",
        "cursor": "",
        "aider": "",
        "opencode": FREE,
    },
    "workerStartEffort": {},
    "models": {"opencodeFree": FREE},
    "workerModelCostTiers": {},
    "jobRequiredModelTier": {},
}


def test_fr8159_env_pin_go_with_tray_free_no_mismatch():
    """AC4: env pin to opencode-go with tray flash-free gives no mismatch."""
    env = {"BOB_OPENCODE_MODEL": GO}
    selected = wsm.launch_selected_model("opencode", CFG, env=env)
    assert selected == GO
    assert wsm.model_mismatch_reason(GO, selected, env=env) == ""
    fields = wsm.digest_seat_model_fields(
        cli="opencode", actual=GO, cfg=CFG, env=env
    )
    assert fields["configured_model"] == GO
    assert fields["start_model"] == GO
    assert fields["model_mismatch"] is False
    assert "mismatch_reason" not in fields


def test_fr8159_pause_fallback_mismatch_reason_paused():
    """AC4: pause fallback from go to free gives mismatch with reason paused."""
    env = {
        "BOB_OPENCODE_MODEL": GO,
        "BOB_OPENCODE_PAUSE_FALLBACK": "1",
    }
    selected = wsm.launch_selected_model("opencode", CFG, env=env)
    assert selected == GO
    reason = wsm.model_mismatch_reason("opencode/beam-free", selected, env=env)
    assert reason == "paused"
    fields = wsm.digest_seat_model_fields(
        cli="opencode", actual="opencode/beam-free", cfg=CFG, env=env
    )
    assert fields["configured_model"] == GO
    assert fields["model_mismatch"] is True
    assert fields["mismatch_reason"] == "paused"


def test_fr8159_paused_does_not_file_unavailable_intake(monkeypatch):
    """AC3: pause fallback is not the 'start model unavailable' line."""
    calls = []
    monkeypatch.setattr(
        bw,
        "report_configured_start_model_unavailable",
        lambda **kwargs: calls.append(kwargs) or {"ok": True},
    )
    out = bw.notify_start_model_after_launch(
        kind="opencode",
        configured=GO,
        actual=FREE,
        machine="redqueen",
        nick="redqueen-1",
        reason="paused",
        env={"BOB_OPENCODE_PAUSE_FALLBACK": "1"},
        shop_say=lambda *a, **k: True,
        log=lambda m: None,
    )
    assert out.get("skipped") is True
    assert calls == []


def test_fr8159_env_pin_match_skips_unavailable_log(monkeypatch):
    logs = []
    calls = []
    monkeypatch.setattr(
        bw,
        "report_configured_start_model_unavailable",
        lambda **kwargs: calls.append(kwargs) or {"ok": True},
    )
    out = bw.notify_start_model_after_launch(
        kind="opencode",
        configured=GO,
        actual=GO,
        machine="redqueen",
        nick="redqueen-1400",
        env={"BOB_OPENCODE_MODEL": GO},
        shop_say=lambda *a, **k: True,
        log=lambda m: logs.append(m),
    )
    assert out.get("skipped") is True
    assert calls == []
    assert not any("unavailable" in m for m in logs)


def test_fr8159_hello_prefers_env_pin_over_tray():
    env = {"BOB_OPENCODE_MODEL": GO}
    # Simulate tray free via BOB_WORKER_START_MODEL_JSON
    env["BOB_WORKER_START_MODEL_JSON"] = (
        '{"workerStartModels":{"opencode":"%s"}}' % FREE
    )
    got = bw.resolve_seat_hello_model("opencode", env=env)
    assert got == GO


def test_fr8159_grok_env_pin_is_configured():
    env = {"BOB_GROK_MODEL": "EXAMPLE_GROK_MAX"}
    selected = wsm.launch_selected_model("grok", CFG, env=env)
    assert selected == "EXAMPLE_GROK_MAX"
    fields = wsm.digest_seat_model_fields(
        cli="grok", actual="EXAMPLE_GROK_MAX", cfg=CFG, env=env
    )
    assert fields["configured_model"] == "EXAMPLE_GROK_MAX"
    assert fields["model_mismatch"] is False


def test_fr8159_post_digest_includes_mismatch_reason(monkeypatch):
    captured = {}

    def _fake_post(url, payload, log=None):
        captured["payload"] = dict(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    ok = bw.post_digest_seat_kind(
        machine="redqueen",
        pid=13916,
        nick="redqueen-13916",
        kind="opencode",
        model=FREE,
        configured_model=GO,
        model_mismatch=True,
        mismatch_reason="paused",
        url="https://example.test/bob/v1/report",
    )
    assert ok is True
    assert captured["payload"]["model_mismatch"] is True
    assert captured["payload"]["mismatch_reason"] == "paused"
    assert captured["payload"]["configured_model"] == GO
