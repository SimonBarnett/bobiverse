"""FR #9027: out-of-fuel MessageBox must be plain text (no HTML/CSS dump)."""
from __future__ import annotations

import bob_worker as bw


def test_fr9027_dialog_strips_token_progress_html():
    html = (
        '</div><style>.token-progress-bar{width:100%}.token-progress-fill{background:#0f0}'
        '</style><div class="token-progress-bar">low cost models</div> Reset soon'
    )
    text = bw.format_out_of_fuel_dialog_text(
        pool="grok",
        remaining=html,
        reset_hint=html,
        evidence=html,
        nick="redqueen-1",
    )
    assert "<style>" not in text
    assert "</div>" not in text
    assert ".token-progress-bar" not in text
    assert ".token-progress-fill" not in text
    assert "low cost models" not in text.lower()
    assert "This seat will close now so it leaves the digest." in text
    assert "Seat: redqueen-1" in text
    assert "Pool: grok" in text


def test_fr9027_dialog_caps_fields_and_prefers_summary():
    blob = ("x" * 200) + " fuel-exhausted:opencode-free Free usage limit"
    text = bw.format_out_of_fuel_dialog_text(
        pool="opencode_free",
        remaining="free=0 go=0",
        evidence=blob,
        nick="m-1",
    )
    # evidence line capped; no huge blob
    for line in text.splitlines():
        assert len(line) <= 200
    assert "This seat will close now so it leaves the digest." in text


def test_fr9027_sanitize_plain_helper_rejects_css_json():
    assert bw.sanitize_out_of_fuel_dialog_field("<b>hi</b>", 80) == "hi"
    out = bw.sanitize_out_of_fuel_dialog_field(
        '{"error":"reset","html":"<style>.token-progress-bar{}</style>"}',
        80,
    )
    assert "<style>" not in out
    assert ".token-progress" not in out
    assert "{" not in out or out == ""


def test_fr9027_pool_bits_reset_not_raw_html_evidence():
    """Evidence containing 'reset' must not dump HTML into Reset: line."""
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "grok"
    sup.base_env = {}
    html = '<style>.token-progress-bar{}</style> reset at Monday'
    # Avoid live fuel load
    import types

    def _no_fuel(*_a, **_k):
        return None

    import bob_worker as mod

    orig = getattr(mod, "load_fresh_agent_list_fuel", None)
    try:
        mod.load_fresh_agent_list_fuel = _no_fuel
        pool, remaining, reset_hint = bw.Supervisor._out_of_fuel_dialog_pool_bits(
            sup, html
        )
    finally:
        if orig is not None:
            mod.load_fresh_agent_list_fuel = orig
    assert ".token-progress" not in reset_hint
    assert "<style>" not in reset_hint
    text = bw.format_out_of_fuel_dialog_text(
        pool=pool, remaining=remaining, reset_hint=reset_hint, evidence=html, nick="n"
    )
    assert ".token-progress-bar" not in text
    assert "<style>" not in text
