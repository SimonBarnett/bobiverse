"""FR #8151: tool-output 'rate limit' must not pause; provider errors still do."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_fuel as of  # noqa: E402


CODERABBIT_GH = (
    '{"comments":[{"id":"IC_kwDO","author":{"login":"coderabbitai"},'
    '"body":"<!-- coderabbit-ai-generated:v1 --> rate limited by coderabbit.ai"}]}'
)
CODERABBIT_BODY = (
    '{"author":"coderabbitai","body":"<!-- coderabbit-ai-generated:v1 --> '
    '… rate limited by coderabbit.ai …"}'
)
DOCSTRING = "    Rate limit + single instance stay in jeeves_maintenance ..."


def test_tool_output_rate_limit_is_not_out_of_fuel():
    assert not bw.is_out_of_fuel_text(CODERABBIT_GH)
    assert not bw.is_out_of_fuel_text(CODERABBIT_BODY)
    assert not bw.is_out_of_fuel_text(DOCSTRING)
    assert bw.provider_fuel_evidence_source(CODERABBIT_GH) is None
    assert bw.provider_fuel_evidence_source(DOCSTRING) is None
    assert not of.looks_like_rate_limit(CODERABBIT_GH)
    assert not of.looks_like_rate_limit(DOCSTRING)


def test_tool_output_does_not_record_pause(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    assert (
        of.record_opencode_pause(
            state, "opencode-go/deepseek-v4-pro", CODERABBIT_BODY, now=1_700_000_000.0
        )
        is None
    )
    assert not of.is_opencode_model_paused(
        "opencode-go/deepseek-v4-pro", state, now=1_700_000_000.0
    )
    assert (
        of.record_opencode_pause(
            state, "opencode-go/deepseek-v4-pro", DOCSTRING, now=1_700_000_000.0
        )
        is None
    )


def test_bare_rate_limit_without_provider_context_is_not_fuel():
    assert not bw.is_out_of_fuel_text("rate limit")
    assert not bw.is_out_of_fuel_text("see rate limiting in the docs")
    assert not of.looks_like_rate_limit("rate limit")
    assert of.looks_like_rate_limit("rate limited by provider")
    assert bw.is_out_of_fuel_text("rate limited by provider")


def test_genuine_provider_refusals_still_pause(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    samples = (
        ("Free usage limit reached. Subscribe to OpenCode Go", "cli-stderr"),
        ("HTTP 429 Too Many Requests", "cli-stderr"),
        ("AI_APICallError: Free usage limit reached", "provider-json"),
        (
            'timestamp=2026-11-17T20:00:12Z level=ERROR message="stream error" '
            "Free usage limit reached",
            "app-log",
        ),
        ("402 Payment Required: usage balance exhausted", "cli-stderr"),
    )
    for text, want_src in samples:
        src = bw.provider_fuel_evidence_source(text)
        assert src == want_src, (text, src)
        assert bw.is_out_of_fuel_text(text), text
        assert of.looks_like_rate_limit(text) or of.is_free_usage_limit_text(text), text
        mid = "opencode/deepseek-v4.1-flash-free"
        assert of.record_opencode_pause(state, mid, text, now=1_700_000_000.0) is not None
        assert of.is_opencode_model_paused(mid, state, now=1_700_000_000.0)


def test_fuel_log_envelope_requires_provider_source():
    noise = {
        "pid": 7636,
        "model": "opencode-go/deepseek-v4-pro",
        "text": CODERABBIT_BODY,
        "source": "cli-stderr",  # bad stamp on tool text must still refuse
    }
    assert bw.provider_fuel_evidence_source(json.dumps(noise)) is None
    good = {
        "pid": 7636,
        "model": "opencode-go/deepseek-v4-pro",
        "text": "HTTP 429 Too Many Requests",
        "source": "cli-stderr",
    }
    assert bw.provider_fuel_evidence_source(json.dumps(good)) == "cli-stderr"
    legacy = {
        "pid": 7636,
        "model": "opencode-go/deepseek-v4-pro",
        "text": "402 Payment Required",
    }
    assert bw.provider_fuel_evidence_source(json.dumps(legacy)) == "cli-stderr"


def test_watcher_ignores_coderabbit_fuel_log_line():
    hits: list[str] = []
    watcher = bw.GrokOutOfFuelWatcher(on_hit=hits.append, agent_pid=7636)
    line = json.dumps(
        {
            "pid": 7636,
            "model": "opencode-go/deepseek-v4-pro",
            "text": CODERABBIT_GH,
        },
        separators=(",", ":"),
    )
    watcher._emit_line(line)
    assert hits == []
    watcher._fired = False
    watcher._emit_line(
        json.dumps(
            {
                "pid": 7636,
                "model": "opencode-go/deepseek-v4-pro",
                "text": "HTTP 429 Too Many Requests",
                "source": "cli-stderr",
            },
            separators=(",", ":"),
        )
    )
    assert hits and bw.is_out_of_fuel_text(hits[0])


def test_launch_script_drops_bare_rate_limit_and_stamps_source(tmp_path: Path):
    spec = bw.build_launch(
        "opencode",
        "agent",
        r"C:\ai\bob\worker",
        "prompt",
        "opencode.exe",
        tmp_path,
    )
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "rate limited by coderabbit" in script or "coderabbit" in script
    assert "source = $fuelSource" in script or "source=$fuelSource" in script or "'source'" in script or "source =" in script
    # Bare 'rate limit' must not be the sole cue in live/limit patterns.
    live_idx = script.find("$liveFuelPattern")
    assert live_idx > 0
    live_line = script[live_idx : live_idx + 350].split("\n")[0]
    assert "|rate limit|" not in live_line
    assert "rate limited by provider" in live_line or "Too Many Requests" in live_line
