"""FR #8150: OpenCode app-log ERROR Free usage -> GIVEUP + pause (stdout silent)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_fuel as of  # noqa: E402
import provider_error_source as pes  # noqa: E402


ERROR_FREE = (
    'timestamp=2026-11-17T20:00:12.000Z level=ERROR run=abc123 '
    'message="stream error" AI_APICallError: Free usage limit reached. '
    "Free models work in OpenCode; subscribe to OpenCode Go"
)
ERROR_FREE_SPACE = (
    "2026-11-17T20:01:38Z level=ERROR message=\"stream error\" "
    "AI_RetryError: Failed after 3 attempts. Last error: Free usage limit reached."
)
INFO_FREE = (
    'timestamp=2026-11-17T20:00:12.000Z level=INFO run=abc123 '
    'message="docs mention Free usage limit reached for operators"'
)
ERROR_OTHER = (
    'timestamp=2026-11-17T20:00:12.000Z level=ERROR run=abc123 '
    'message="stream error" something else went wrong'
)


def test_classify_error_free_usage_hits():
    hit = pes.classify_opencode_app_log_line(ERROR_FREE)
    assert hit is not None
    assert hit.reason == "fuel-exhausted:opencode-free"
    hit2 = pes.classify_opencode_app_log_line(ERROR_FREE_SPACE)
    assert hit2 is not None
    assert hit2.reason == "fuel-exhausted:opencode-free"


def test_classify_ignores_info_and_non_fuel_error():
    assert pes.classify_opencode_app_log_line(INFO_FREE) is None
    assert pes.classify_opencode_app_log_line(ERROR_OTHER) is None
    # Tool / stdout-shaped text without level=ERROR must not fire.
    assert (
        pes.classify_opencode_app_log_line(
            "Free usage limit reached. Subscribe to OpenCode Go"
        )
        is None
    )


def test_scan_skips_stale_prefix_and_old_ts(tmp_path: Path):
    log = tmp_path / "opencode.log"
    stale = (
        'timestamp=2026-11-17T19:00:00.000Z level=ERROR run=old '
        'message="stream error" Free usage limit reached'
    )
    fresh = (
        'timestamp=2026-11-17T20:05:00.000Z level=ERROR run=new '
        'message="stream error" Free usage limit reached. subscribe to OpenCode Go'
    )
    body = stale + "\n" + fresh + "\n"
    log.write_text(body, encoding="utf-8")
    # Stale offset: start after the first line (new run baseline at EOF of prior content).
    stale_off = len((stale + "\n").encode("utf-8"))
    new_off, hits = pes.scan_opencode_app_log(log, since_offset=stale_off)
    assert len(hits) == 1
    assert hits[0].run_id == "new"
    assert new_off == log.stat().st_size

    # since_ts drops the old ERROR even on a full-file scan.
    # 19:00Z is before cutoff; 20:05Z is after.
    cutoff = time.mktime(time.strptime("2026-11-17T19:30:00Z", "%Y-%m-%dT%H:%M:%SZ"))
    # mktime is local; use explicit UTC epoch via datetime instead.
    from datetime import datetime, timezone

    cutoff = datetime(2026, 11, 17, 19, 30, tzinfo=timezone.utc).timestamp()
    _off, hits2 = pes.scan_opencode_app_log(log, since_offset=0, since_ts=cutoff)
    assert len(hits2) == 1
    assert hits2[0].run_id == "new"


def test_seat_start_records_pause_from_app_log(tmp_path: Path, monkeypatch):
    data = tmp_path / "seat" / "opencode"
    log_dir = data / "log"
    log_dir.mkdir(parents=True)
    log = log_dir / "opencode.log"
    now = time.time()
    from datetime import datetime, timezone

    ts = (
        datetime.fromtimestamp(now - 30, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    log.write_text(
        f'timestamp={ts} level=ERROR run=r1 message="stream error" '
        "Free usage limit reached. Subscribe to OpenCode Go\n",
        encoding="utf-8",
    )
    state = tmp_path / "state"
    state.mkdir()
    env = {"BOB_OPENCODE_DATA_DIR": str(data)}
    hit = pes.apply_seat_start_opencode_app_log_pause(
        env=env,
        state_dir=state,
        model_id="opencode/deepseek-v4.1-flash-free",
        lookback_s=120,
        now=now,
    )
    assert hit is not None
    assert hit.reason == "fuel-exhausted:opencode-free"
    assert of.is_opencode_model_paused(
        "opencode/deepseek-v4.1-flash-free", state, now=now
    )
    assert of.is_opencode_model_paused("opencode-free", state, now=now)


def test_seat_start_ignores_stale_error(tmp_path: Path):
    data = tmp_path / "seat" / "opencode"
    log_dir = data / "log"
    log_dir.mkdir(parents=True)
    log = log_dir / "opencode.log"
    from datetime import datetime, timezone

    old = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    log.write_text(
        f'timestamp={old} level=ERROR run=old message="stream error" '
        "Free usage limit reached\n",
        encoding="utf-8",
    )
    state = tmp_path / "state"
    state.mkdir()
    hit = pes.apply_seat_start_opencode_app_log_pause(
        env={"BOB_OPENCODE_DATA_DIR": str(data)},
        state_dir=state,
        model_id="opencode/deepseek-v4.1-flash-free",
        lookback_s=300,
        now=time.time(),
    )
    assert hit is None
    assert not of.is_opencode_model_paused(
        "opencode/deepseek-v4.1-flash-free", state, now=time.time()
    )


def test_provider_error_sources_registry():
    assert "opencode" in pes.PROVIDER_ERROR_SOURCES
    assert callable(pes.PROVIDER_ERROR_SOURCES["opencode"][0])
    assert "grok" in pes.PROVIDER_ERROR_SOURCES
    # Cursor may register later; empty tuple is fine.
    assert "cursor" in pes.PROVIDER_ERROR_SOURCES


def test_launch_script_polls_app_log_independent_of_stdout(tmp_path: Path):
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
    assert "provider_error_source.py" in script or "providerErrPy" in script
    assert "appLog" in script or "opencode.log" in script
    assert "fuel-exhausted:opencode-free" in script
    # Poll must not sit only inside the stdout-grew branch.
    loop_idx = script.find("while (-not $proc.HasExited)")
    assert loop_idx > 0
    loop = script[loop_idx : loop_idx + 8000]
    assert "providerErrPy peek" in loop or "$providerErrPy peek" in loop
    # app-log poll appears before / outside the $len -gt $lastLen growth gate.
    app_idx = loop.find("providerErrPy peek")
    if app_idx < 0:
        app_idx = loop.find("$providerErrPy")
    grow_idx = loop.find("$len -gt $lastLen")
    assert app_idx >= 0
    assert grow_idx >= 0
    assert app_idx < grow_idx


def test_resolve_skips_free_when_app_log_paused_pool(tmp_path: Path, monkeypatch):
    data = tmp_path / "seat" / "opencode"
    (data / "log").mkdir(parents=True)
    from datetime import datetime, timezone

    now = time.time()
    ts = (
        datetime.fromtimestamp(now - 20, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    (data / "log" / "opencode.log").write_text(
        f'timestamp={ts} level=ERROR run=r1 message="stream error" '
        "Free usage limit reached. Subscribe to OpenCode Go\n",
        encoding="utf-8",
    )
    state = tmp_path / "state"
    state.mkdir()
    env = {"BOB_OPENCODE_DATA_DIR": str(data)}
    # Clear operator/tray overrides so start_free is the first free candidate.
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    bw._OPENCODE_MODEL_ENV_AT_START = ""
    logs: list[str] = []
    chosen = bw.resolve_opencode_model(
        bw.Fuel(), state_dir=state, now=now, env=env, log_fn=logs.append
    )
    assert any("app-log fuel at seat start" in x for x in logs)
    assert of.is_opencode_model_paused("opencode-free", state, now=now)
    # Free leaf must be skipped; may fall through to a Go model or None.
    if chosen:
        leaf = chosen.rsplit("/", 1)[-1].lower()
        assert not leaf.endswith("-free"), chosen


def test_peek_cli_hit_and_ok(tmp_path: Path):
    log = tmp_path / "opencode.log"
    log.write_text(ERROR_FREE + "\n", encoding="utf-8")
    # offset 0 sees the ERROR
    import subprocess

    py = sys.executable
    helper = REPO / "bob" / "scripts" / "provider_error_source.py"
    out = subprocess.check_output(
        [py, str(helper), "peek", str(log), "0"], text=True
    ).strip()
    assert out.startswith("HIT fuel-exhausted:opencode-free")
    # EOF baseline: no new lines
    size = str(log.stat().st_size)
    out2 = subprocess.check_output(
        [py, str(helper), "peek", str(log), size], text=True
    ).strip()
    assert out2.startswith("OK ")
