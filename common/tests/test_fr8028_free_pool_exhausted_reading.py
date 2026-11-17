"""FR #8028: Free usage limit must not leave opencode_free painted at 100."""
from __future__ import annotations

import json
import time
from pathlib import Path

import gitclaim
import bobreport
import opencode_fuel as of
import registered_machines


NOW = 1_763_300_000.0
RESET_TS = NOW + 3600
NICK = "redqueen-8688"
REPO = "SimonBarnett/bobiverse"


def test_free_usage_limit_records_free_pool_pause(tmp_path: Path):
    text = "Free usage limit reached. Subscribe to OpenCode Go"
    assert of.is_free_usage_limit_text(text)
    reset = of.record_opencode_pause(
        tmp_path,
        "opencode/deepseek-v4.1-flash-free",
        text,
        now=NOW,
        default_pause_s=3600,
    )
    assert reset == RESET_TS
    pauses = of.load_opencode_pauses(tmp_path, now=NOW)
    assert pauses.get(of.FUEL_ID_FREE) == RESET_TS
    assert pauses.get("opencode/deepseek-v4.1-flash-free") == RESET_TS


def test_apply_runtime_pauses_zeros_free_pool(tmp_path: Path):
    of.record_opencode_pause(
        tmp_path,
        "opencode/beam-free",
        "Free usage limit reached … subscribe to OpenCode Go",
        now=NOW,
        default_pause_s=7200,
    )
    fuel = {
        of.FUEL_ID_FREE: 100,
        of.FUEL_ID_GO: 40,
        "free_model_ids": ["opencode/beam-free"],
        "models": {},
    }
    out = of.apply_runtime_pauses_to_fuel(fuel, tmp_path, now=NOW)
    assert out[of.FUEL_ID_FREE] == 0
    assert out[of.FUEL_ID_GO] == 40
    assert out.get("free_reset_at")
    assert out.get("free_status") == "exhausted"


def test_fuel_from_stats_respects_pause_state_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_PAUSE_STATE_DIR", str(tmp_path))
    of.record_opencode_pause(
        tmp_path,
        "opencode/beam-free",
        "Free usage limit reached",
        now=NOW,
        default_pause_s=1800,
    )
    stats = {
        "costs": {},
        "free_models": ["beam-free"],
        "free_model_ids": ["opencode/beam-free"],
    }
    fuel = of.fuel_from_stats(stats, state_dir=tmp_path, now=NOW)
    assert fuel[of.FUEL_ID_FREE] == 0
    assert fuel[of.FUEL_ID_FREE] != 100


def test_free_seat_offer_paused_when_opencode_free_is_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"redqueen"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    reset = "2026-11-22T19:28:00Z"
    doc = {
        "v": 1,
        "machines": {
            "redqueen": {
                "id": "redqueen",
                "pcent": {"opencode-free": 0, "opencode-go": 55},
                "opencode_free_reset_at": reset,
                "fetched_at": "2026-11-16T00:00:00Z",
                "workers": {
                    "8688": {
                        "pid": "8688",
                        "nick": NICK,
                        "kind": "opencode",
                        "state": "running",
                        "start_model": "opencode/deepseek-v4.1-flash-free",
                        "cost_tier": "opencode-free",
                    }
                },
            }
        },
    }
    bobreport.save_digest(tmp_path, doc)
    # Coerce must keep the free-pool reset (stamp path uses load_digest).
    loaded = bobreport.load_digest(tmp_path)
    assert loaded["machines"]["redqueen"].get("opencode_free_reset_at") == reset
    bobreport.save_digest(tmp_path, loaded)
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#8008",
        "seq": 1,
        "url": f"https://github.com/{REPO}/issues/8008",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    reason = gitclaim.seat_fuel_pause_reason(tmp_path, NICK, NOW)
    assert reason == "pool-0-until-reset"
    # Second check must not self-clear (offer_focus_top calls this again).
    assert gitclaim.seat_fuel_pause_reason(tmp_path, NICK, NOW) == "pool-0-until-reset"
    status, job = gitclaim.offer_focus_top(tmp_path, NICK, "#redqueen", now=NOW)
    assert status == "empty" and job is None


def test_enrich_peer_copies_free_reset_when_exhausted():
    peer = {"id": "redqueen", "pcent": {"opencode-go": 40}}
    oc = {
        "opencode-free": 0,
        "opencode-go": 40,
        "free_reset_at": "2026-11-22T19:28:00Z",
        "free_status": "exhausted",
    }
    enriched = bobreport.enrich_peer_with_opencode_pcent(peer, oc)
    assert enriched["pcent"]["opencode-free"] == 0
    assert enriched["opencode_free_reset_at"] == "2026-11-22T19:28:00Z"
    assert enriched["free_status"] == "exhausted"
