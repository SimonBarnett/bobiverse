"""FR #8537: Free usage limit switches free OpenCode seats to paid; no false free=100."""
from __future__ import annotations

import json
import os
from pathlib import Path

import bob.scripts.bob_worker as bw
import opencode_fuel as of

FREE = "opencode/deepseek-v4.1-flash-free"
PAID = "opencode-go/deepseek-v4-pro"
EVIDENCE = "Free usage limit reached. Subscribe to OpenCode Go"


def test_should_switch_when_free_limit_and_go_remains():
    fuel = bw.Fuel(opencode_free=100, opencode_go=40)
    assert bw.should_switch_opencode_free_to_paid(EVIDENCE, FREE, fuel) is True
    assert bw.should_switch_opencode_free_to_paid(EVIDENCE, PAID, fuel) is False
    assert (
        bw.should_switch_opencode_free_to_paid(
            EVIDENCE, FREE, bw.Fuel(opencode_free=0, opencode_go=0)
        )
        is False
    )


def test_record_pause_accepts_cli_stderr_free_usage(tmp_path: Path):
    blob = json.dumps(
        {"text": EVIDENCE, "source": "cli-stderr", "model": FREE},
        separators=(",", ":"),
    )
    ts = of.record_opencode_pause(tmp_path, FREE, blob)
    assert ts is not None
    pauses = of.load_opencode_pauses(tmp_path)
    assert of.FUEL_ID_FREE in pauses
    folded = of.apply_runtime_pauses_to_fuel(
        {of.FUEL_ID_FREE: 100, of.FUEL_ID_GO: 40}, tmp_path
    )
    assert int(folded[of.FUEL_ID_FREE]) == 0


def test_record_pause_rejects_cli_stderr_free_usage_on_paid(tmp_path: Path):
    blob = json.dumps(
        {"text": EVIDENCE, "source": "cli-stderr", "model": PAID},
        separators=(",", ":"),
    )
    assert of.record_opencode_pause(tmp_path, PAID, blob) is None


def test_wrapper_live_free_phrase_without_provider_cue(tmp_path: Path):
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "prompt", "opencode.exe", tmp_path)
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "FR #8537" in script
    assert "-or (-not $isGoModel)" in script
    assert "-or (-not $scanIsGoModel)" in script
    assert "Try-OpencodeSwitchToPaid" in script


def test_on_hit_switches_without_giveup(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("BOB_OPENCODE_MODEL", FREE)
    state = tmp_path / "Bobiverse" / "worker" / "state"
    state.mkdir(parents=True)
    fuel = bw.Fuel(opencode_free=100, opencode_go=55)

    class Bored:
        def __init__(self):
            self.calls = []

        def note_out_of_fuel(self, text=""):
            self.calls.append(text)
            return "FR SimonBarnett/bobiverse#8537"

    class Sup:
        kind = "opencode"
        base_env = {"LOCALAPPDATA": str(tmp_path), "BOB_OPENCODE_MODEL": FREE}
        bored = Bored()
        _opencode_paid_switched = False

        def log(self, msg):
            self.last = msg

    env = {"LOCALAPPDATA": str(tmp_path), "BOB_OPENCODE_MODEL": FREE}
    bw.save_agent_list_fuel(fuel, env=env)
    sup = Sup()
    switched = bw.Supervisor._try_opencode_switch_free_to_paid(sup, EVIDENCE)
    assert switched is True
    assert sup._opencode_paid_switched is True
    assert "switch-to-paid" in getattr(sup, "last", "")
    assert sup.bored.calls == []
    # Free pool paused / zeroed
    pauses = of.load_opencode_pauses(state)
    assert of.FUEL_ID_FREE in pauses
    cached = bw.load_fresh_agent_list_fuel(max_age_s=3600, env=env)
    assert cached is not None
    assert cached.opencode_free == 0

def test_fr8537_paid_switch_model_reads_tray_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv(
        "BOB_WORKER_START_MODEL_JSON",
        '{"models":{"opencodeFree":"opencode/deepseek-v4.1-flash-free","opencodePaid":"opencode-go/kimi-k3"}}',
    )
    got = bw.resolve_opencode_paid_switch_model(
        env={
            "LOCALAPPDATA": str(tmp_path),
            "XDG_CONFIG_HOME": str(tmp_path),
            "BOB_WORKER_START_MODEL_JSON": '{"models":{"opencodeFree":"opencode/deepseek-v4.1-flash-free","opencodePaid":"opencode-go/kimi-k3"}}',
        }
    )
    assert got == "opencode-go/kimi-k3"
