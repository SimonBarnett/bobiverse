"""FR #8026: Free usage limit reached must fail the turn (not hang)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_fuel as of  # noqa: E402


FREE_FIXTURES = (
    "Free usage limit reached. Subscribe to OpenCode Go",
    "Free usage limit reached … subscribe to OpenCode Go",
    "AI_APICallError: Free usage limit reached",
    "error: Free usage limit reached — subscribe to OpenCode Go for more",
)


def test_is_out_of_fuel_text_detects_free_usage_limit():
    for sample in FREE_FIXTURES:
        assert bw.is_out_of_fuel_text(sample), sample
    assert not bw.is_out_of_fuel_text("docs say `Free usage limit reached` in the skill")
    assert not bw.is_out_of_fuel_text("hard ceiling 1800000ms")


def test_looks_like_rate_limit_detects_free_usage_limit():
    for sample in FREE_FIXTURES:
        assert of.looks_like_rate_limit(sample), sample


def test_fuel_exhausted_opencode_free_reason_helper():
    assert bw.opencode_fuel_exhausted_reason(
        "Free usage limit reached. Subscribe to OpenCode Go"
    ) == "fuel-exhausted:opencode-free"
    assert bw.opencode_fuel_exhausted_reason("HTTP 429 Too Many Requests") == "out-of-fuel"
    assert bw.opencode_fuel_exhausted_reason("") == "out-of-fuel"


def test_launch_script_scans_live_output_and_giveups_free_usage(tmp_path: Path):
    spec = bw.build_launch(
        "opencode",
        "agent",
        r"C:\ai\bob\worker",
        "prompt",
        "opencode.exe",
        tmp_path,
    )
    script_key = next(k for k in spec.files if k.endswith("launch-opencode.ps1"))
    script = spec.files[script_key]
    assert "Free usage limit" in script
    assert "subscribe to OpenCode Go" in script or "OpenCode Go" in script
    assert "fuel-exhausted:opencode-free" in script
    assert "$fuelHitLive" in script
    # Live capture scan must happen while the process is still running.
    loop_idx = script.find("while (-not $proc.HasExited)")
    assert loop_idx > 0
    loop = script[loop_idx : loop_idx + 4500]
    assert "Free usage limit" in loop or "$limitPattern" in loop or "fuelHitLive" in loop
    # hitLimit must not require nonzero exit alone when free-usage text is present.
    hit_idx = script.find("$hitLimit")
    assign = script[hit_idx : hit_idx + 350].split("\n")[0]
    assert "-not $timedOut" in assign
    assert "$fuelHitLive" in assign or "Free usage" in script[hit_idx : hit_idx + 800]
    # GIVEUP path for free pool.
    assert "Write-OpencodeJobGiveup" in script
    assert "fuel-exhausted:opencode-free" in script
