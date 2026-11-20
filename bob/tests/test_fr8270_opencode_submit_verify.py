"""FR #8270: OpenCode submit-verify uses a turn receipt, not a TUI prompt."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw


def test_fr8270_turn_started_passes_without_prompt(tmp_path: Path):
    turns = tmp_path / "opencode-turns.jsonl"
    logs: list[str] = []
    now = {"t": 1000.0}
    wrote = {"n": 0}

    def probe() -> bool:
        return bw.probe_opencode_headless_receipt(turns, since_wall=10.0, baseline_size=0)

    def clock() -> float:
        now["t"] += 0.2
        wrote["n"] += 1
        if wrote["n"] == 3:
            turns.write_text(
                json.dumps({"type": "turn_started", "ts": "2026-11-18T20:00:00Z"}) + "\n",
                encoding="utf-8",
            )
        return now["t"]

    res = bw.run_submit_verify_loop(
        enter_fn=lambda: False,
        probe_fn=probe,
        clock=clock,
        sleep=lambda _s: None,
        log=logs.append,
        verify_s=1.0,
        max_retries=1,
        backoffs=(1.0,),
        kind="opencode",
        miss_label="no turn receipt",
        alive_fn=lambda: True,
    )
    assert res == "ok"
    assert not any("no prompt seen" in line for line in logs)


def test_fr8270_dead_spawn_giveup_names_probe_and_kind():
    logs: list[str] = []
    res = bw.run_submit_verify_loop(
        enter_fn=lambda: False,
        probe_fn=lambda: False,
        clock=lambda: 1.0,
        sleep=lambda _s: None,
        log=logs.append,
        verify_s=5.0,
        max_retries=3,
        kind="opencode",
        miss_label="no turn receipt",
        alive_fn=lambda: False,
    )
    assert res == "failed"
    assert any("probe=spawn" in line and "kind=opencode" in line for line in logs)
    assert not any("no prompt seen" in line for line in logs)
    wire = bw.submit_verify_giveup_line(
        "redqueen: MRB SimonBarnett/bobiverse#8266 https://x",
        probe="no turn receipt",
        kind="opencode",
    )
    assert wire == (
        "GIVEUP MRB SimonBarnett/bobiverse#8266 submit-verify failed "
        "probe=no turn receipt kind=opencode"
    )
