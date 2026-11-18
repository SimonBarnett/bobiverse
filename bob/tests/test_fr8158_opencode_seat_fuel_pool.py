"""FR #8158: OpenCode mid-job fuel reading uses the seat's own pool."""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
import opencode_fuel as of


GO_MODEL = "opencode-go/deepseek-v4-pro"
FREE_MODEL = "opencode/beam-free"


def test_fr8158_seat_fuel_pool_from_start_model():
    assert bw.seat_fuel_pool("grok") == "grok"
    assert bw.seat_fuel_pool("cursor") == "cursor"
    assert bw.seat_fuel_pool("opencode", GO_MODEL) == "opencode_go"
    assert bw.seat_fuel_pool("opencode", FREE_MODEL) == "opencode_free"
    assert bw.seat_fuel_pool("opencode", "") == "opencode"


def test_fr8158_opencode_go_missing_known_false_not_grok_pct():
    """AC4: opencode-go seat with grok_pct=91 and opencode_go missing → known=False pool=opencode_go."""
    f = bw.Fuel(
        grok_pct=91,
        grok_state="available",
        opencode_free=100,
        opencode_go=None,
    )
    assert bw.seat_fuel_pool("opencode", GO_MODEL) == "opencode_go"
    assert bw.fuel_reading_known(f, "opencode", start_model=GO_MODEL) is False
    assert bw.fuel_explicitly_exhausted(f, "opencode", start_model=GO_MODEL) is False
    snap = bw.format_fuel_reading(f, "opencode", start_model=GO_MODEL)
    assert "pool=opencode_go" in snap
    assert "known=False" in snap
    assert "pct=None" in snap or "pct=None" in snap.replace(" ", "")
    # Must not present Grok 91 as this seat's pct.
    assert "pct=91" not in snap
    # Without start_model, selection still sees free/go either-pool known.
    assert bw.fuel_reading_known(f, "opencode") is True


def test_fr8158_opencode_go_zero_is_exhausted():
    f = bw.Fuel(grok_pct=91, grok_state="available", opencode_free=100, opencode_go=0)
    assert bw.fuel_reading_known(f, "opencode", start_model=GO_MODEL) is True
    assert bw.fuel_explicitly_exhausted(f, "opencode", start_model=GO_MODEL) is True
    snap = bw.format_fuel_reading(f, "opencode", start_model=GO_MODEL)
    assert "pct=0" in snap
    assert "pool=opencode_go" in snap
    assert "exhausted=True" in snap
    assert "pct=91" not in snap


def test_fr8158_free_refusal_zeros_pool(tmp_path: Path):
    """AC4: recorded free refusal → opencode_free=0 exhausted=True."""
    now = time.time()
    # FR #8207: free-usage pause needs app-log ERROR / AI_* provider cue.
    of.record_opencode_pause(
        tmp_path,
        FREE_MODEL,
        'timestamp=2026-11-18T12:00:00Z level=ERROR message="stream error" '
        "Free usage limit reached. Subscribe to OpenCode Go",
        now=now,
        default_pause_s=3600,
    )
    f = bw.Fuel(grok_pct=91, grok_state="available", opencode_free=100, opencode_go=40)
    folded = bw.fold_opencode_seat_pauses(
        f, FREE_MODEL, state_dir=tmp_path, now=now
    )
    assert folded.opencode_free == 0
    assert folded.opencode_go == 40
    assert bw.fuel_explicitly_exhausted(folded, "opencode", start_model=FREE_MODEL) is True
    snap = bw.format_fuel_reading(folded, "opencode", start_model=FREE_MODEL)
    assert "pool=opencode_free" in snap
    assert "exhausted=True" in snap
    assert "pct=0" in snap


def test_fr8158_go_model_pause_zeros_go_pool(tmp_path: Path):
    now = time.time()
    of.record_opencode_pause(
        tmp_path,
        GO_MODEL,
        "HTTP 429 rate limit exceeded; try again later",
        now=now,
        default_pause_s=1800,
    )
    f = bw.Fuel(opencode_free=100, opencode_go=55)
    folded = bw.fold_opencode_seat_pauses(f, GO_MODEL, state_dir=tmp_path, now=now)
    assert folded.opencode_go == 0
    assert folded.opencode_free == 100
    assert bw.fuel_explicitly_exhausted(folded, "opencode", start_model=GO_MODEL) is True


def test_fr8158_grok_and_cursor_still_own_pool():
    f = bw.Fuel(grok_pct=42, grok_state="available", cursor_high=10, cursor_low=5, opencode_free=100)
    g = bw.format_fuel_reading(f, "grok")
    assert "pool=grok" in g
    assert "pct=42" in g
    c = bw.format_fuel_reading(f, "cursor")
    assert "pool=cursor" in c
    assert "pct=10" in c
