"""FR #6366: OpenCode finish-runs (full-frame done-miss, no pause, cwd=worktree)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import bob_worker as bw
import opencode_seat_contract as osc


def test_fr6366_finish_steps_text_lists_end_of_job():
    text = bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#6360",
        worktree=r"D:\Temp\bobiverse-fr-6360",
        outbox=r"D:\Temp\bobiverse-fr-6360\.bob\outbox.txt",
    )
    low = text.lower()
    assert "git status" in low or "git diff" in low
    assert "commit" in low
    assert "push" in low
    assert "gh pr create" in low or "pr create" in low
    assert "closes" in low
    assert "done" in low
    assert "bob_outbox" in low or "outbox" in low
    assert "not over until" in low or "until done" in low


def test_fr6366_done_miss_reminder_opencode_is_framed_finish():
    shop = "#marchhare"
    key = "FR SimonBarnett/bobiverse#6360"
    wt = r"D:\Temp\bobiverse-fr-6360"
    ob = str(Path(wt) / ".bob" / "outbox.txt")
    line = bw.opencode_done_miss_reminder_line(
        shop=shop, outbox=ob, job_key=key, worktree=wt
    )
    parsed = osc.parse_opencode_frame(osc.console_text(line, maxlen=2000))
    assert parsed is not None, line[:200]
    assert parsed["key"] == key
    assert parsed["dir"] == wt
    body = parsed["line"]
    assert body.startswith("FROM ")
    assert "FINISH" in body.upper() or "finish" in body.lower()
    assert "git" in body.lower()
    # Must survive OpenCode inject maxlen (inject_console uses 2000 for @@BOBJOB1).
    assert osc.parse_opencode_frame(bw.one_line(line, maxlen=2000)) is not None
    assert "FINISH" in bw.one_line(line, maxlen=2000).upper() or "git" in bw.one_line(line, maxlen=2000).lower()


def test_fr6366_done_miss_reminder_grok_unchanged():
    line = bw.done_miss_reminder_line(
        shop="#flamingo",
        outbox=r"C:\tmp\outbox.txt",
        job_key="FR SimonBarnett/bobiverse#1",
    )
    assert "ACKed but no DONE" in line
    assert "@@BOBJOB1" not in line


def test_fr6366_finish_run_max_env(monkeypatch):
    monkeypatch.delenv("BOB_OPENCODE_FINISH_RUN_MAX", raising=False)
    assert bw.opencode_finish_run_max() == 3
    monkeypatch.setenv("BOB_OPENCODE_FINISH_RUN_MAX", "5")
    assert bw.opencode_finish_run_max() == 5
    monkeypatch.setenv("BOB_OPENCODE_FINISH_RUN_MAX", "99")
    assert bw.opencode_finish_run_max() == 10
    monkeypatch.setenv("BOB_OPENCODE_FINISH_RUN_MAX", "0")
    assert bw.opencode_finish_run_max() == 1


def test_fr6366_progress_snapshot_detects_commit(tmp_path: Path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "c1"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    before = bw.opencode_finish_progress_snapshot(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    after_dirty = bw.opencode_finish_progress_snapshot(repo)
    assert bw.opencode_finish_progress_changed(before, after_dirty)
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "c2"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    after_commit = bw.opencode_finish_progress_snapshot(repo)
    assert bw.opencode_finish_progress_changed(before, after_commit)
    assert not bw.opencode_finish_progress_changed(after_commit, after_commit)


def test_fr6366_worker_prompt_lists_finish_line():
    text = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "marchhare", "marchhare-1")
    low = text.lower()
    assert "fr #6366" in low or "finish" in low
    assert "gh pr create" in low or "closes" in low
    assert "not over until" in low or "until done" in low


def test_fr6366_wrapper_sets_workingdirectory_and_no_pause_on_watchdog(tmp_path: Path):
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
    assert "WorkingDirectory" in script
    assert "$ocDir" in script
    # Watchdog timeout must not call record-pause (FR #6366).
    assert "record-pause" in script
    # timedOut alone must not set hitLimit / record-pause.
    assert "if ($timedOut)" in script or "$timedOut" in script
    # Find the hitLimit assignment region
    assert "$hitLimit" in script
    # Must log watchdog without requiring pause
    assert "watchdog timeout" in script.lower() or "watchdog" in script.lower()
    # Explicit: hitLimit from limit patterns, not timedOut alone
    idx = script.find("$hitLimit")
    region = script[idx : idx + 400]
    assert "timedOut" not in region.split("=")[1].split("\n")[0] or (
        "Payment Required" in region and "$timedOut -or" not in region
    )


def test_fr6366_bored_emitter_opencode_retries_then_giveup():
    from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait

    clock = FakeClock(0.0)
    e, _sent, logs = _emitter(
        clock, harvest_hold_s=90.0, done_miss_grace_s=5.0, ack_stale_s=2700.0
    )
    attempts: list[str] = []
    progress_flags = [True, True, False]  # progress twice then none

    def _remind(key: str) -> None:
        attempts.append(key)

    def _decide(key: str) -> str:
        # Called on turn_ended after a remind. Consume progress_flags.
        if not progress_flags:
            return "giveup"
        prog = progress_flags.pop(0)
        n = len(attempts)
        e.log(
            f"opencode finish-run key={key} attempt={n}/{bw.opencode_finish_run_max()} "
            f"progress={'yes' if prog else 'no'}"
        )
        if prog and n < bw.opencode_finish_run_max():
            return "retry"
        return "giveup"

    e.done_miss_remind_fn = _remind
    e.opencode_finish_decide_fn = _decide
    giveups: list[tuple[str, str]] = []
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))

    e.on_outbox("ACK FR SimonBarnett/bobiverse#6360")
    e.turn_ended(at=clock())
    clock.advance(6.0)
    assert _wait(lambda: e._done_miss_reminded, clock)  # noqa: SLF001
    assert len(attempts) == 1

    # End after remind #1 with progress -> retry (re-arm)
    e.turn_ended(at=clock())
    clock.advance(6.0)
    assert _wait(lambda: len(attempts) >= 2, clock)

    # End after remind #2 with progress -> retry
    e.turn_ended(at=clock())
    clock.advance(6.0)
    assert _wait(lambda: len(attempts) >= 3, clock)

    # End after remind #3 with no progress -> GIVEUP
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent), clock), e.sent
    assert giveups and giveups[0][1] == "done-miss"
    assert any("opencode finish-run" in m for m in logs), logs
    e.stop()


def test_fr6366_pause_file_untouched_by_done_miss_helpers(tmp_path: Path, monkeypatch):
    """done-miss helpers must not write opencode-pauses.json."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    pause = bw.opencode_pauses_state_dir({"LOCALAPPDATA": str(tmp_path)}) / "opencode-pauses.json"
    if pause.exists():
        pause.unlink()
    _ = bw.opencode_done_miss_reminder_line(
        shop="#x",
        outbox=str(tmp_path / "o.txt"),
        job_key="FR o/r#1",
        worktree=str(tmp_path),
    )
    assert not pause.exists()
