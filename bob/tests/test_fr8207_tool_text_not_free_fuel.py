# -*- coding: utf-8 -*-
"""FR #8207: Free usage text in tool/PR output must not fuel-kill; paid never opencode-free."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_fuel as of  # noqa: E402

GO = "opencode-go/deepseek-v4-pro"
FREE = "opencode/deepseek-v4.1-flash-free"

# Fixture shaped like #8162 / gh pr view quoting Free usage limit.
PR_BODY_TOOL = (
    "## Summary\n"
    "Detect OpenCode Free usage limit reached from the seat app log.\n"
    "GIVEUP fuel-exhausted:opencode-free when hit.\n"
    "Closes SimonBarnett/bobiverse#8150\n"
)
GH_ISSUE_JSON = json.dumps(
    {
        "title": "FR: detect Free usage limit",
        "body": "Free usage limit reached. Subscribe to OpenCode Go\n",
        "number": 8162,
    }
)
GH_PR_VIEW_MARKDOWN = (
    "title:\tFR #8150: detect OpenCode Free usage limit\n"
    "body:\tFree usage limit reached. Subscribe to OpenCode Go\n"
    "fuel-exhausted:opencode-free\n"
)


def test_fr8207_pr_and_gh_tool_text_not_fuel():
    for sample in (PR_BODY_TOOL, GH_ISSUE_JSON, GH_PR_VIEW_MARKDOWN):
        assert bw.provider_fuel_evidence_source(sample) is None, sample[:80]
        assert not bw.is_out_of_fuel_text(sample), sample[:80]


def test_fr8207_bare_free_usage_without_provider_channel_not_fuel():
    """Bare phrase alone is tool-echoable; only ERROR / AI_* channels count (FR #8207)."""
    bare = "Free usage limit reached. Subscribe to OpenCode Go"
    assert bw.provider_fuel_evidence_source(bare) is None
    assert not bw.is_out_of_fuel_text(bare)


def test_fr8207_app_log_and_provider_json_still_fuel():
    app = (
        'timestamp=2026-11-18T14:58:00Z level=ERROR message="stream error" '
        "Free usage limit reached"
    )
    prov = "AI_APICallError: Free usage limit reached"
    assert bw.provider_fuel_evidence_source(app) == "app-log"
    assert bw.provider_fuel_evidence_source(prov) == "provider-json"
    assert bw.is_out_of_fuel_text(app)
    assert bw.is_out_of_fuel_text(prov)


def test_fr8207_paid_seat_never_opencode_free_reason():
    text = (
        'timestamp=2026-11-18T14:58:00Z level=ERROR message="stream error" '
        "Free usage limit reached"
    )
    assert bw.opencode_fuel_exhausted_reason(text) == "fuel-exhausted:opencode-free"
    assert (
        bw.opencode_fuel_exhausted_reason(text, start_model=GO) == "out-of-fuel"
    )
    assert (
        bw.opencode_fuel_exhausted_reason(text, start_model=FREE)
        == "fuel-exhausted:opencode-free"
    )


def test_fr8207_paid_seat_ignores_free_usage_pause(tmp_path: Path):
    """Genuine free-usage text must not pause a paid/go start model (FR #8207)."""
    text = (
        'timestamp=2026-11-18T14:58:00Z level=ERROR message="stream error" '
        "Free usage limit reached"
    )
    assert of.record_opencode_pause(tmp_path, GO, text, now=1_700_000_000.0) is None
    assert not of.is_opencode_model_paused(GO, tmp_path, now=1_700_000_000.0)
    # Free leaf may still pause on real ERROR free-usage.
    assert of.record_opencode_pause(tmp_path, FREE, text, now=1_700_000_000.0) is not None
    assert of.is_opencode_model_paused(FREE, tmp_path, now=1_700_000_000.0)


def test_fr8207_go_pool_fuel_ignores_stale_free_pause(tmp_path: Path):
    """False free pause must not exhaust a go seat when go pool has fuel."""
    pauses = {of.FUEL_ID_FREE: 1_700_000_000.0 + 3600}
    of.save_opencode_pauses(tmp_path, pauses)
    f = bw.Fuel(opencode_free=0, opencode_go=81)
    folded = bw.fold_opencode_seat_pauses(f, GO, state_dir=tmp_path, now=1_700_000_000.0)
    assert folded.opencode_go == 81
    assert bw.fuel_explicitly_exhausted(folded, "opencode", start_model=GO) is False
    assert bw.fuel_reading_known(folded, "opencode", start_model=GO) is True


def test_fr8207_launch_script_requires_provider_cue_for_free_usage(tmp_path: Path):
    spec = bw.build_launch(
        "opencode",
        "agent",
        r"C:\ai\bob\worker",
        "prompt",
        "opencode.exe",
        tmp_path,
    )
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "$providerFuelCue" in script
    assert "isGoModel" in script
    assert "scanFreeOk" in script
    assert "## Summary" in script  # tool-noise pattern

def test_mrb8212_retry_after_still_pauses_go_model(tmp_path: Path):
    """MRB #8212: Retry-After alone must still pause (rate limit), not be blocked by free-usage gate."""
    reset = of.record_opencode_pause(
        tmp_path, GO, "Retry-After: 600", now=1_000_000.0
    )
    assert reset == 1_000_000.0 + 600
    assert of.is_opencode_model_paused(GO, tmp_path, now=1_000_000.0)

