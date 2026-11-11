"""FR #6586: !build streams suite + runner logs incrementally (kill leaves partial output)."""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

import bobiverse_build as bb
from repo_layout import ROOT


SRC = ROOT / "common" / "scripts" / "bobiverse_build.py"
CLI = ROOT / "common" / "scripts" / "run_bobiverse_build.py"


def test_fr6586_run_command_streams_and_flushes_log(tmp_path: Path):
    """Lines appear in the log file while the child is still running."""
    log_path = tmp_path / "suite-ref.log"
    script = tmp_path / "slow_print.py"
    script.write_text(
        "import sys, time\n"
        "print('LINE_ONE', flush=True)\n"
        "time.sleep(2.5)\n"
        "print('LINE_TWO', flush=True)\n",
        encoding="utf-8",
    )
    cmd = [sys.executable, "-u", str(script)]
    seen = threading.Event()

    def _watch():
        deadline = time.time() + 8
        while time.time() < deadline:
            if log_path.is_file():
                text = log_path.read_text(encoding="utf-8", errors="replace")
                if "LINE_ONE" in text:
                    seen.set()
                    return
            time.sleep(0.05)

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()
    res = bb.run_command(cmd, cwd=tmp_path, timeout=10, name="slow", log_path=log_path)
    watcher.join(timeout=1)
    assert seen.is_set(), "log must contain LINE_ONE before the child finished"
    assert res.exit_code == 0
    assert "LINE_ONE" in res.stdout and "LINE_TWO" in res.stdout
    final = log_path.read_text(encoding="utf-8")
    assert "LINE_ONE" in final and "LINE_TWO" in final


def test_fr6586_kill_mid_suite_keeps_partial_log(tmp_path: Path):
    """Hard kill mid-suite leaves every flushed line (acceptance)."""
    log_path = tmp_path / "killed.log"
    script = tmp_path / "never_ends.py"
    script.write_text(
        "import sys, time\n"
        "print('BEFORE_KILL nodeid=tests/test_x.py::test_a FAILED', flush=True)\n"
        "sys.stdout.flush()\n"
        "time.sleep(60)\n"
        "print('AFTER_KILL', flush=True)\n",
        encoding="utf-8",
    )
    cmd = [sys.executable, "-u", str(script)]
    # Short timeout forces kill after first line.
    res = bb.run_command(cmd, cwd=tmp_path, timeout=0.8, name="killed", log_path=log_path)
    assert res.timed_out is True
    text = log_path.read_text(encoding="utf-8")
    assert "BEFORE_KILL" in text
    assert "AFTER_KILL" not in text
    assert "nodeid=tests/test_x.py::test_a" in text or "FAILED" in text
    assert "timed_out" in res.stdout


def test_fr6586_failed_tests_summary_updates_per_suite(tmp_path: Path):
    """failed-tests.txt is rewritten after each suite/rerun, not only at the end."""
    filer = bb.FakeGitHubFiler()
    calls = {"n": 0}

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", log_path=None, **_):
        calls["n"] += 1
        out = (
            "FAILED common/tests/test_a.py::test_one\n"
            if "baseline" not in str(ref_or_baseline)
            else "1 passed\n"
        )
        if log_path:
            Path(log_path).write_text(out, encoding="utf-8")
        return bb.SuiteRunResult(name, ref_or_baseline, 1 if "baseline" not in str(ref_or_baseline) else 0, out, False, 0.1)

    recipe = bb.BuildRecipe(
        machine="ionos",
        baseline="last_release_tag",
        suites=[bb.SuiteSpec(name="unit", cmd="python -m pytest -q", cwd=".", timeout=30)],
        pack={"cmd": "pack {{version}} {{out_dir}}", "artifacts": []},
        release={"target": "github-prerelease", "tag": "v{{version}}", "never_latest": True},
        cache_dirs=[],
    )
    log_dir = tmp_path / "logs"
    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "2.0.0",
        "HEAD",
        recipe,
        filer,
        work_dir=tmp_path / "work",
        log_dir=log_dir,
        local_machine="ionos",
        run_command_fn=run_fn,
        pack_fn=lambda **k: None,
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    runner.run()
    summary = log_dir / "failed-tests.txt"
    assert summary.is_file()
    body = summary.read_text(encoding="utf-8")
    assert "test_a.py::test_one" in body or "FAILED" in body
    assert "unit" in body


def test_fr6586_source_pins_stream_flush_and_summary():
    text = SRC.read_text(encoding="utf-8")
    assert "log_path" in text
    assert "failed-tests.txt" in text
    assert "flush" in text
    cli = CLI.read_text(encoding="utf-8")
    assert "flush=True" in cli or "flush=True" in text
    # No secret literals in the new streaming helpers.
    assert "password=" not in text.lower().split("def run_command", 1)[-1][:2000]


def test_fr6586_timeout_fake_still_kills_without_stdout(tmp_path: Path):
    """Injectable FakeSp without stdout keeps communicate timeout path."""

    class FakeProc:
        def __init__(self):
            self.killed = False
            self.returncode = None
            self.stdout = None

        def communicate(self, timeout=None):
            raise TimeoutError("slow")

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            self.returncode = -1
            return -1

    class FakeSp:
        PIPE = -1
        STDOUT = -2
        TimeoutExpired = TimeoutError

        def __init__(self):
            self.proc = FakeProc()

        def Popen(self, *a, **k):
            return self.proc

    sp = FakeSp()
    log_path = tmp_path / "fake.log"
    res = bb.run_command("sleep 999", cwd=tmp_path, timeout=0.1, runner=sp, name="slow", log_path=log_path)
    assert res.timed_out is True
    assert sp.proc.killed is True
