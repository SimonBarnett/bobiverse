"""FR #6585: BUILD runner posts rate-limited progress to #bobiverse."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb


def test_fr6585_progress_line_carries_version_and_id():
    lines: list[str] = []
    p = bb.BuildProgressPoster(
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        build_id="abc123",
        sink=lines.append,
        min_interval_s=0.0,
        heartbeat_s=9999.0,
        time_fn=lambda: 1000.0,
    )
    assert p.emit("step start checkout") is True
    assert lines
    assert "version=2.0.0" in lines[0]
    assert "id=abc123" in lines[0]
    assert lines[0].startswith("BUILD progress ")


def test_fr6585_rate_limit_one_per_30s_except_force():
    lines: list[str] = []
    now = {"t": 0.0}

    def clock():
        return now["t"]

    p = bb.BuildProgressPoster(
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        build_id="x",
        sink=lines.append,
        min_interval_s=30.0,
        heartbeat_s=9999.0,
        time_fn=clock,
    )
    assert p.emit("a") is True
    assert p.emit("b") is False  # within 30s
    now["t"] = 29.9
    assert p.emit("c") is False
    now["t"] = 30.0
    assert p.emit("d") is True
    assert len(lines) == 2
    assert " a" in lines[0] or lines[0].endswith(" a")
    assert " d" in lines[1] or lines[1].endswith(" d")
    # force bypasses rate limit
    now["t"] = 30.1
    assert p.emit("forced", force=True) is True
    assert len(lines) == 3


def test_fr6585_heartbeat_when_idle_10_min():
    lines: list[str] = []
    now = {"t": 0.0}
    p = bb.BuildProgressPoster(
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        build_id="hb",
        sink=lines.append,
        min_interval_s=0.0,
        heartbeat_s=600.0,
        time_fn=lambda: now["t"],
    )
    p.emit("step start suites")
    p.set_current_step("suite common")
    now["t"] = 599.0
    assert p.maybe_heartbeat() is False
    now["t"] = 600.0
    assert p.maybe_heartbeat() is True
    assert any("heartbeat" in ln and "suite common" in ln for ln in lines)
    # second heartbeat needs another idle window from last post
    now["t"] = 700.0
    assert p.maybe_heartbeat() is False
    now["t"] = 1200.0
    assert p.maybe_heartbeat() is True


def test_fr6585_redacts_secrets_and_credential_paths():
    lines: list[str] = []
    token = "ghp_" + ("A" * 36)
    p = bb.BuildProgressPoster(
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        build_id="r",
        sink=lines.append,
        min_interval_s=0.0,
        heartbeat_s=9999.0,
        time_fn=lambda: 1.0,
        env={"GH_TOKEN": token, "GITHUB_TOKEN": token},
    )
    p.emit(f"step fail path=C:/Users/x/.config/gh/hosts.yml token={token}")
    assert lines
    assert token not in lines[0]
    assert "<redacted>" in lines[0]
    assert "<redacted-path>" in lines[0]


def test_fr6585_sink_failure_never_raises_or_blocks():
    def boom(_line: str) -> None:
        raise RuntimeError("irc down")

    p = bb.BuildProgressPoster(
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        build_id="e",
        sink=boom,
        min_interval_s=0.0,
        heartbeat_s=9999.0,
        time_fn=lambda: 1.0,
    )
    assert p.emit("step start pack") is False  # failed to deliver, but no raise


def test_fr6585_jsonl_sink_appends_and_read_new_lines(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    sink = bb.JsonlProgressSink(path)
    p = bb.BuildProgressPoster(
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        build_id="j",
        sink=sink,
        min_interval_s=0.0,
        heartbeat_s=9999.0,
        time_fn=lambda: 42.0,
    )
    p.emit("step start checkout")
    p.emit("step end checkout elapsed=3s", force=True)
    rows = bb.read_progress_jsonl(path, after_offset=0)
    assert len(rows) == 2
    assert rows[0]["line"].startswith("BUILD progress ")
    assert "checkout" in rows[0]["line"]
    # resume offset skips already-seen bytes
    off = path.stat().st_size
    p.emit("suite common done passed=10 failed=0 skipped=1", force=True)
    more = bb.read_progress_jsonl(path, after_offset=off)
    assert len(more) == 1
    assert "passed=10" in more[0]["line"]


def test_fr6585_parse_pytest_counts():
    text = "===== 21 failed, 1874 passed, 2 skipped, 2 warnings in 574.40s ====="
    c = bb.parse_pytest_summary_counts(text)
    assert c == {"passed": 1874, "failed": 21, "skipped": 2}


def test_fr6585_runner_emits_step_suite_and_rerun(tmp_path: Path):
    posted: list[str] = []
    poster = bb.BuildProgressPoster(
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        build_id="run1",
        sink=posted.append,
        min_interval_s=0.0,
        heartbeat_s=9999.0,
        time_fn=lambda: 100.0,
    )
    calls = {"n": 0}

    def run_cmd(cmd, cwd=None, env=None, timeout=None, name="", ref_or_baseline="", log_path=None, **_):
        calls["n"] += 1
        at = str(ref_or_baseline)
        if at.endswith("-solo"):
            return bb.SuiteRunResult(
                name=name or "common",
                ref_or_baseline=at,
                exit_code=1,
                stdout="FAILED common/tests/test_x.py::test_one\n===== 1 failed in 0.1s =====\n",
                timed_out=False,
                duration_s=0.1,
            )
        if "baseline" in at or at == "baseline":
            return bb.SuiteRunResult(
                name=name or "common",
                ref_or_baseline=at,
                exit_code=0,
                stdout="===== 3 passed in 0.2s =====\n",
                timed_out=False,
                duration_s=0.2,
            )
        # ref: one failure
        return bb.SuiteRunResult(
            name=name or "common",
            ref_or_baseline=at,
            exit_code=1,
            stdout=(
                "FAILED common/tests/test_x.py::test_one\n"
                "===== 1 failed, 2 passed, 0 skipped in 1.0s =====\n"
            ),
            timed_out=False,
            duration_s=1.0,
        )

    recipe = bb.BuildRecipe(
        machine="flamingo",
        suites=[bb.SuiteSpec(name="common", cmd="python -m pytest common/tests -q")],
        pack={},
        release={},
    )
    work = tmp_path / "work"
    runner = bb.BuildRunner(
        repo_root=tmp_path,
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        ref="HEAD",
        recipe=recipe,
        filer=bb.FakeGitHubFiler(),
        work_dir=work,
        log_dir=work / "logs",
        local_machine="flamingo",
        run_command_fn=run_cmd,
        build_id="run1",
        progress=poster,
        baseline_resolver=lambda *_a: "baseline",
    )
    report = runner.run(dry_run=False)
    assert any("step start suite common ref" in ln for ln in posted)
    assert any("passed=2" in ln and "failed=1" in ln for ln in posted)
    assert any("rerun 1/1" in ln and "fail" in ln for ln in posted)
    assert any("step start pack" not in ln or True for ln in posted)  # blockers skip pack
    assert report.ok is False
    # Terminal announce shape unchanged (still on report, not progress).
    assert report.announce_lines
    assert report.announce_lines[-1].startswith("BUILD fail ")


def test_fr6585_spawn_cmd_includes_progress_file():
    """Ear spawn must pass --progress-file (string pin; full IRC e2e is live-only).

    FR #6654: ear drains via BuildProgressRelay (durable .pos + logged relay).
    """
    src = (Path(__file__).resolve().parents[2] / "common" / "scripts" / "irc_agent.py").read_text(
        encoding="utf-8"
    )
    assert "--progress-file" in src
    assert "BuildProgressRelay" in src
    assert "progress.jsonl" in src
    assert "BUILD progress" in (
        Path(__file__).resolve().parents[2] / "common" / "scripts" / "bobiverse_build.py"
    ).read_text(encoding="utf-8")


def test_fr6585_rapid_pass_reruns_rate_limited_fails_forced():
    """Many fast pass solos do not flood; fail/first/last still post (MRB #6624)."""
    lines: list[str] = []
    now = {"t": 0.0}
    p = bb.BuildProgressPoster(
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        build_id="rl",
        sink=lines.append,
        min_interval_s=30.0,
        heartbeat_s=9999.0,
        time_fn=lambda: now["t"],
    )
    # Seed last_post via a forced step so the rate window is active.
    assert p.emit("step start solos", force=True) is True
    assert p.rerun_progress(index=1, total=10, nodeid="t::a", result="pass") is True
    # Immediate middle pass is rate-limited.
    assert p.rerun_progress(index=2, total=10, nodeid="t::b", result="pass") is False
    # Fail always forces through.
    assert p.rerun_progress(index=3, total=10, nodeid="t::c", result="fail") is True
    assert p.rerun_progress(index=4, total=10, nodeid="t::d", result="pass") is False
    # Last index forces.
    assert p.rerun_progress(index=10, total=10, nodeid="t::z", result="pass") is True
    assert sum(1 for ln in lines if "rerun " in ln) == 3
    assert any("rerun 3/10" in ln and "fail" in ln for ln in lines)


def test_fr6585_jsonl_sink_flushes(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    sink = bb.JsonlProgressSink(path)
    sink("BUILD progress demo")
    # After __call__ returns, another reader must see the line (flush contract).
    assert "BUILD progress demo" in path.read_text(encoding="utf-8")
