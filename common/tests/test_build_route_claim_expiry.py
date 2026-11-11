"""FR #6558: log BUILD v1 duplicate route drops; expire id-less route claims."""
from __future__ import annotations

import multiprocessing as mp
import os
import time
from pathlib import Path
from types import SimpleNamespace

import bobiverse_build as bb
import irc_agent as ia
import pytest


IDLESS_LINE = "BUILD v1 repos=SimonBarnett/bobiverse version=2.0.0 ref=HEAD"
EXPLICIT_LINE = (
    "BUILD v1 repos=SimonBarnett/bobiverse version=2.0.0 ref=HEAD id=b-1794400390"
)


def _idless_rid() -> str:
    route = bb.parse_build_v1_route(IDLESS_LINE)
    assert route is not None
    return bb.build_route_id(route)


def _write_aged_marker(path: Path, age_s: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() - float(age_s))
    path.write_text(f"{ts}\n", encoding="ascii")
    os.utime(path, (ts, ts))


def test_idless_duplicate_within_window_logs_once(tmp_path: Path):
    routes = tmp_path / "routes"
    q = tmp_path / "q"
    logs: list[str] = []
    rid = _idless_rid()
    assert (
        bb.consume_build_v1(
            IDLESS_LINE,
            "flamingo",
            "flamingo",
            queue_dir=q,
            route_marker_dir=routes,
            stale_claim_s=3600,
            log=logs.append,
        )
        is True
    )
    assert len(list(q.glob("build-*.json"))) == 1
    assert (
        bb.consume_build_v1(
            IDLESS_LINE,
            "flamingo",
            "flamingo",
            queue_dir=q,
            route_marker_dir=routes,
            stale_claim_s=3600,
            log=logs.append,
        )
        is False
    )
    assert len(list(q.glob("build-*.json"))) == 1
    dup = [ln for ln in logs if "dropped as duplicate" in ln]
    assert len(dup) == 1
    assert rid in dup[0]
    assert "duplicate" in dup[0]
    assert str(routes / f"{rid}.claimed") in dup[0]
    assert "age=" in dup[0]
    assert "stale_after=3600" in dup[0]


def test_idless_reclaim_after_window(tmp_path: Path):
    routes = tmp_path / "routes"
    q = tmp_path / "q"
    logs: list[str] = []
    rid = _idless_rid()
    marker = routes / f"{rid}.claimed"
    ttl = 100.0
    _write_aged_marker(marker, ttl + 10)
    assert (
        bb.consume_build_v1(
            IDLESS_LINE,
            "flamingo",
            "flamingo",
            queue_dir=q,
            route_marker_dir=routes,
            stale_claim_s=ttl,
            log=logs.append,
        )
        is True
    )
    assert len(list(q.glob("build-*.json"))) == 1
    text = marker.read_text(encoding="ascii").strip()
    assert int(text) >= int(time.time()) - 5
    reclaim = [ln for ln in logs if "reclaimed" in ln]
    assert len(reclaim) == 1
    assert rid in reclaim[0]
    assert str(marker) in reclaim[0]
    assert "previous_age=" in reclaim[0]


def test_idless_exact_ttl_boundary_stays_duplicate(tmp_path: Path, monkeypatch):
    routes = tmp_path / "routes"
    q = tmp_path / "q"
    logs: list[str] = []
    rid = _idless_rid()
    ttl = 200.0
    now = 1_700_000_000.0
    monkeypatch.setattr(bb.time, "time", lambda: now)
    marker = routes / f"{rid}.claimed"
    marker.parent.mkdir(parents=True)
    # Content timestamp exactly ttl seconds ago -> age == ttl (not strictly greater).
    marker.write_text(f"{int(now - ttl)}\n", encoding="ascii")
    os.utime(marker, (now - ttl, now - ttl))
    assert (
        bb.consume_build_v1(
            IDLESS_LINE,
            "flamingo",
            "flamingo",
            queue_dir=q,
            route_marker_dir=routes,
            stale_claim_s=ttl,
            log=logs.append,
        )
        is False
    )
    assert list(q.glob("build-*.json")) == []
    assert any("dropped as duplicate" in ln for ln in logs)


def test_explicit_id_old_marker_still_refuses(tmp_path: Path):
    routes = tmp_path / "routes"
    q = tmp_path / "q"
    logs: list[str] = []
    marker = routes / "b-1794400390.claimed"
    _write_aged_marker(marker, 999999)
    assert (
        bb.consume_build_v1(
            EXPLICIT_LINE,
            "flamingo",
            "flamingo",
            queue_dir=q,
            route_marker_dir=routes,
            stale_claim_s=60,
            log=logs.append,
        )
        is False
    )
    assert list(q.glob("build-*.json")) == []
    assert any(
        "dropped as duplicate" in ln and "stale_after=never" in ln for ln in logs
    )


def test_claim_open_permission_error_logs_error_not_duplicate(
    tmp_path: Path, monkeypatch
):
    routes = tmp_path / "routes"
    routes.mkdir()
    logs: list[str] = []
    real_open = os.open

    def boom(path, flags, *a, **k):
        if str(path).endswith(".claimed"):
            raise PermissionError("denied")
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", boom)
    assert (
        bb.consume_build_v1(
            IDLESS_LINE,
            "flamingo",
            "flamingo",
            queue_dir=tmp_path / "q",
            route_marker_dir=routes,
            stale_claim_s=60,
            log=logs.append,
        )
        is False
    )
    assert any("claim error" in ln for ln in logs)
    assert not any("dropped as duplicate" in ln for ln in logs)


def test_empty_marker_fresh_mtime_duplicate(tmp_path: Path):
    routes = tmp_path / "routes"
    rid = _idless_rid()
    marker = routes / f"{rid}.claimed"
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="ascii")
    now = time.time()
    os.utime(marker, (now, now))
    logs: list[str] = []
    assert (
        bb.consume_build_v1(
            IDLESS_LINE,
            "flamingo",
            "flamingo",
            queue_dir=tmp_path / "q",
            route_marker_dir=routes,
            stale_claim_s=60,
            log=logs.append,
        )
        is False
    )
    assert any("dropped as duplicate" in ln for ln in logs)


def test_empty_marker_old_mtime_reclaims(tmp_path: Path):
    routes = tmp_path / "routes"
    q = tmp_path / "q"
    rid = _idless_rid()
    marker = routes / f"{rid}.claimed"
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="ascii")
    old = time.time() - 500
    os.utime(marker, (old, old))
    logs: list[str] = []
    assert (
        bb.consume_build_v1(
            IDLESS_LINE,
            "flamingo",
            "flamingo",
            queue_dir=q,
            route_marker_dir=routes,
            stale_claim_s=100,
            log=logs.append,
        )
        is True
    )
    assert len(list(q.glob("build-*.json"))) == 1
    assert any("reclaimed" in ln for ln in logs)


def _race_worker(routes: str, queue: str, ttl: float, out_q: mp.Queue) -> None:
    logs: list[str] = []
    ok = bb.consume_build_v1(
        IDLESS_LINE,
        "flamingo",
        "flamingo",
        queue_dir=queue,
        route_marker_dir=routes,
        stale_claim_s=ttl,
        log=logs.append,
    )
    out_q.put((ok, list(logs)))


def test_concurrent_stale_reclaim_admits_one(tmp_path: Path):
    routes = tmp_path / "routes"
    q = tmp_path / "q"
    rid = _idless_rid()
    ttl = 50.0
    _write_aged_marker(routes / f"{rid}.claimed", ttl + 20)
    out_q: mp.Queue = mp.Queue()
    procs = [
        mp.Process(target=_race_worker, args=(str(routes), str(q), ttl, out_q))
        for _ in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0
    results = [out_q.get(timeout=5) for _ in procs]
    truths = [ok for ok, _ in results]
    assert truths.count(True) == 1
    assert len(list(q.glob("build-*.json"))) == 1
    dup_logs = sum(
        1 for _ok, logs in results for ln in logs if "dropped as duplicate" in ln
    )
    assert dup_logs >= 1


def test_agent_path_logs_duplicate_and_reclaim(tmp_path: Path, monkeypatch):
    """Client._maybe_start_build_runner wires recipe_max_run_s + log=info."""
    install = tmp_path / "install"
    (install / ".bobiverse").mkdir(parents=True)
    # Tiny recipe so recipe_max_run_s is small enough to age in-test.
    (install / ".bobiverse" / "build.yml").write_text(
        "machine: flamingo\n"
        "baseline: last_release_tag\n"
        "channel: \"#bobiverse\"\n"
        "max_parallel_builds: 1\n"
        "suites:\n"
        "  - name: tiny\n"
        "    cmd: python -c pass\n"
        "    cwd: .\n"
        "    timeout: 30\n",
        encoding="utf-8",
    )
    prog = tmp_path / "ProgramData"
    monkeypatch.setenv("ProgramData", str(prog))
    captured: list[str] = []
    spawns: list[Path] = []
    monkeypatch.setattr(ia, "info", lambda msg: captured.append(msg))

    agent = ia.Client.__new__(ia.Client)
    agent.args = SimpleNamespace(chair=False, home=str(tmp_path / "home"), nick="Bob-x")
    agent._local_machine_id = lambda: "flamingo"  # type: ignore[method-assign]
    agent._install_root = lambda: str(install)  # type: ignore[method-assign]
    agent._build_queue_dir = lambda: tmp_path / "build-queue"  # type: ignore[method-assign]
    agent._spawn_build_runner = lambda job, mid: spawns.append(job)  # type: ignore[method-assign]

    assert agent._maybe_start_build_runner(IDLESS_LINE, src_hint="walrus") is True
    assert len(spawns) == 1
    assert any("BUILD v1 accepted" in m for m in captured)

    captured.clear()
    assert agent._maybe_start_build_runner(IDLESS_LINE, src_hint="walrus") is False
    assert len(spawns) == 1
    assert any("dropped as duplicate" in m for m in captured)
    assert not any("BUILD v1 accepted" in m for m in captured)

    # Age marker beyond recipe_max_run_s and accept again.
    recipe = bb.load_recipe_from_candidates([install], repo="SimonBarnett/bobiverse")
    ttl = bb.recipe_max_run_s(recipe)
    rid = _idless_rid()
    marker = prog / "Bobiverse" / "build-routes" / f"{rid}.claimed"
    _write_aged_marker(marker, ttl + 10)
    captured.clear()
    assert agent._maybe_start_build_runner(IDLESS_LINE, src_hint="walrus") is True
    assert len(spawns) == 2
    assert any("reclaimed" in m for m in captured)
