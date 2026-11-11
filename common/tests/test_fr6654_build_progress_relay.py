"""FR #6654: ear relays progress.jsonl to #bobiverse once each, with offset + throttle."""
from __future__ import annotations

import json
from pathlib import Path

import bobiverse_build as bb


def _append_events(path: Path, lines: list[str], *, t0: float = 100.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for i, ln in enumerate(lines):
            fh.write(json.dumps({"ts": t0 + i, "line": ln}, ensure_ascii=True) + "\n")


def test_fr6654_relay_posts_n_events_in_order_once(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    events = [
        "BUILD progress SimonBarnett/bobiverse version=2.0.0 step start checkout",
        "BUILD progress SimonBarnett/bobiverse version=2.0.0 step end checkout elapsed=6s ok",
        "BUILD progress SimonBarnett/bobiverse version=2.0.0 step start suites",
    ]
    _append_events(path, events)
    posted: list[str] = []
    logs: list[str] = []
    clock = {"t": 0.0}

    relay = bb.BuildProgressRelay(
        path,
        post_fn=posted.append,
        log_fn=logs.append,
        min_interval_s=0.0,
        time_fn=lambda: clock["t"],
    )
    n = relay.drain()
    assert n == 3
    assert posted == events
    assert sum(1 for x in logs if "build-progress relay:" in x) == 3
    # Exactly once: second drain adds nothing
    assert relay.drain() == 0
    assert posted == events


def test_fr6654_relay_survives_restart_no_dup_no_miss(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    first = [
        "BUILD progress r version=1 step start a",
        "BUILD progress r version=1 step end a ok",
    ]
    _append_events(path, first)
    posted: list[str] = []
    clock = {"t": 1.0}
    r1 = bb.BuildProgressRelay(
        path,
        post_fn=posted.append,
        min_interval_s=0.0,
        time_fn=lambda: clock["t"],
    )
    assert r1.drain() == 2
    assert posted == first
    # Mid-run: more events, then "ear restart" = new relay instance sharing .pos
    more = [
        "BUILD progress r version=1 step start b",
        "BUILD progress r version=1 heartbeat step=b",
    ]
    _append_events(path, more, t0=200.0)
    r2 = bb.BuildProgressRelay(
        path,
        post_fn=posted.append,
        min_interval_s=0.0,
        time_fn=lambda: clock["t"],
    )
    assert r2.drain() == 2
    assert posted == first + more
    assert r2.drain() == 0


def test_fr6654_throttle_delays_but_loses_none(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    events = [f"BUILD progress r version=1 evt={i}" for i in range(5)]
    _append_events(path, events)
    posted: list[str] = []
    logs: list[str] = []
    clock = {"t": 0.0}

    relay = bb.BuildProgressRelay(
        path,
        post_fn=posted.append,
        log_fn=logs.append,
        min_interval_s=30.0,
        time_fn=lambda: clock["t"],
    )
    # First drain: only first event posts; rest stay queued
    assert relay.drain() == 1
    assert posted == [events[0]]
    assert any("throttle" in x.lower() or "queued" in x.lower() for x in logs) or relay.pending_count > 0
    # Advance clock and drain remaining one-by-one
    for i in range(1, 5):
        clock["t"] += 30.0
        assert relay.drain() >= 1
    assert posted == events
    assert relay.pending_count == 0


def test_fr6654_read_advance_skips_incomplete_trailing_line(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    complete = json.dumps({"ts": 1, "line": "BUILD progress r version=1 a"}, ensure_ascii=True) + "\n"
    path.write_bytes(complete.encode("utf-8") + b'{"ts": 2, "line": "BUILD progress partial')
    rows, new_off = bb.read_progress_jsonl_advance(path, after_offset=0)
    assert len(rows) == 1
    assert rows[0][0]["line"].endswith(" a")
    assert new_off == len(complete.encode("utf-8"))
    # Complete the trailing line
    with path.open("a", encoding="utf-8") as fh:
        fh.write('"}\n')
    rows2, new_off2 = bb.read_progress_jsonl_advance(path, after_offset=new_off)
    assert len(rows2) == 1
    assert "partial" in rows2[0][0]["line"]
    assert new_off2 == path.stat().st_size


def test_fr6654_redacts_full_paths_and_secrets_on_relay(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    raw = (
        "BUILD progress r version=1 see C:\\ProgramData\\Bobiverse\\build-work\\x "
        "and Bearer FAKESECRET_e2f3g4h5i6j7k8l9m0n1"
    )
    _append_events(path, [raw])
    posted: list[str] = []
    relay = bb.BuildProgressRelay(
        path,
        post_fn=posted.append,
        min_interval_s=0.0,
        time_fn=lambda: 0.0,
    )
    assert relay.drain() == 1
    assert "ProgramData" not in posted[0]
    assert "ghp_" not in posted[0]
    assert "Bearer <redacted>" in posted[0] or "<redacted>" in posted[0]


def test_fr6654_irc_agent_watch_uses_build_progress_relay():
    """String pin: ear watch loop must use BuildProgressRelay (not silent bare drain)."""
    from pathlib import Path as P

    src = (P(__file__).resolve().parents[1] / "scripts" / "irc_agent.py").read_text(
        encoding="utf-8"
    )
    assert "BuildProgressRelay" in src
    assert "progress.jsonl" in src
    assert "build-progress" in src.lower() or "build_progress" in src.lower()
