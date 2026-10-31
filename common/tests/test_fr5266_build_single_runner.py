"""FR #5266: one BUILD v1 runner per machine; work lock; git stderr in result."""
from __future__ import annotations

import json
from pathlib import Path

import bobiverse_build as bb
import run_bobiverse_build as runner


def test_build_v1_single_runner_per_machine(tmp_path: Path):
    line = (
        "BUILD v1 repos=SimonBarnett/bobiverse version=1.0.9 ref=HEAD id=b-1793350068"
    )
    routes = tmp_path / "routes"
    chair_q = tmp_path / "chair-q"
    ear_q = tmp_path / "ear-q"
    ok_chair = bb.consume_build_v1(
        line, "win-mpre8vi4u6u", "ionos",
        queue_dir=chair_q, route_marker_dir=routes,
    )
    ok_ear = bb.consume_build_v1(
        line, "ionos", "ionos",
        queue_dir=ear_q, route_marker_dir=routes,
    )
    assert ok_chair is True
    assert ok_ear is False
    assert len(list(chair_q.glob("build-*.json"))) == 1
    assert list(ear_q.glob("build-*.json")) == []
    assert (routes / "b-1793350068.claimed").is_file()


def test_runner_refuses_when_work_lock_held(tmp_path: Path):
    work = tmp_path / "build-work" / "1.0.9"
    work.mkdir(parents=True)
    (work / ".runner.lock").write_text("held-by-peer", encoding="utf-8")
    log: list[str] = []
    try:
        runner.checkout("SimonBarnett/bobiverse", "HEAD", work, log)
        raise AssertionError("checkout must refuse when .runner.lock exists")
    except RuntimeError as exc:
        assert "work lock" in str(exc).lower()
    assert not (work / "src").exists()


def test_git_failure_stderr_in_result(tmp_path: Path):
    log: list[str] = []
    try:
        runner._git(
            ["clone", "--", "https://127.0.0.1:1/no-such.git", str(tmp_path / "src")],
            None,
            log,
            timeout=8,
        )
        raise AssertionError("clone of closed port must fail")
    except RuntimeError as exc:
        blob = str(exc)
        assert "failed rc=" in blob
        assert blob != "git clone failed rc=128"
        assert any(part in blob.lower() for part in ("fail", "refus", "unable", "error", "could not"))
    result = {"ok": False, "errors": []}
    result["errors"].append(str(log[-1] if log else "no-log"))
    assert "rc=" in result["errors"][0]
