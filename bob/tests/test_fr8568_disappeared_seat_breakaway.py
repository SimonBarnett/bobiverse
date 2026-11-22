"""FR #8568: breakaway launch flags + synthetic last-exit / GIVEUP on seat disappearance."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
from repo_layout import ROOT

BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = ROOT / "bob" / "docs" / "bob-worker.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr8568_create_breakaway_constant_and_launch_flags():
    assert bw.CREATE_BREAKAWAY_FROM_JOB == 0x01000000
    t = _read(BOB_TRAY)
    assert "CreateBreakawayFromJob" in t or "CREATE_BREAKAWAY_FROM_JOB" in t
    assert "0x01000000" in t
    assert "CreateNewConsole | CreateBreakawayFromJob" in t.replace(" ", "") or (
        "CreateNewConsole | CreateBreakawayFromJob" in t
    )
    # FR #9097: compiled WorkerLauncher retries without breakaway on Access Denied.
    assert "ErrorAccessDenied" in t
    assert "FR #9097" in t
    assert t.count("CreateProcessW(run, cmd,") >= 2
    w = _read(WATCH)
    assert "CREATE_BREAKAWAY_FROM_JOB" in w
    assert "CREATE_NEW_CONSOLE | CREATE_UNICODE_ENVIRONMENT | CREATE_BREAKAWAY_FROM_JOB" in w


def test_fr8568_watchdog_handles_disappear_without_restart():
    t = _read(BOB_TRAY)
    assert "HandleDisappearedWorkerRuns" in t
    assert "external-kill" in t
    assert "not restarted" in t
    # FR #3180: still must not launch/heal from watchdog.
    i = t.find("void Watchdog()")
    assert i >= 0
    rest = t[i:]
    nxt = rest.find("\n        void ", 1)
    wd = rest if nxt < 0 else rest[:nxt]
    assert "WorkerLauncher.Launch" not in wd
    assert "HealWorkerSeats" not in wd


def test_fr8568_parse_worker_run_dir_name():
    assert bw.parse_worker_run_dir_name("worker-flamingo-14160-aabbccdd") == (
        "flamingo",
        14160,
    )
    assert bw.parse_worker_run_dir_name("worker-redqueen-11048-cce7cd9c") == (
        "redqueen",
        11048,
    )
    assert bw.parse_worker_run_dir_name("plan-plan-1-abc") is None


def test_fr8568_handle_disappeared_writes_last_exit_and_giveup(tmp_path):
    run = tmp_path / "worker-flamingo-99901-deadbeef"
    run.mkdir()
    (run / "last-from.txt").write_text(
        "FROM jeeves #flamingo flamingo-99901: FR SimonBarnett/bobiverse#8568 "
        "https://github.com/SimonBarnett/bobiverse/issues/8568\n",
        encoding="utf-8",
    )
    hit = bw.handle_disappeared_worker_run(
        run, shop="flamingo", pid_alive=lambda _pid: False
    )
    assert hit is not None
    assert hit["giveup"] is True
    assert hit["job_key"] == "FR SimonBarnett/bobiverse#8568"
    exit_doc = json.loads((run / "last-exit.json").read_text(encoding="utf-8"))
    assert exit_doc["reason"] == "external-kill"
    assert exit_doc["synthetic"] is True
    assert exit_doc["agent_pid"] == 99901
    out = (run / "outbox.txt").read_text(encoding="utf-8")
    assert "GIVEUP FR SimonBarnett/bobiverse#8568 external-kill" in out


def test_fr8568_alive_pid_skipped(tmp_path):
    run = tmp_path / "worker-flamingo-99902-aabbcc00"
    run.mkdir()
    (run / "last-from.txt").write_text(
        "FROM jeeves #flamingo x: FR SimonBarnett/bobiverse#1 https://x\n",
        encoding="utf-8",
    )
    assert (
        bw.handle_disappeared_worker_run(run, pid_alive=lambda _pid: True) is None
    )
    assert not (run / "last-exit.json").exists()


def test_fr8568_existing_last_exit_skipped(tmp_path):
    run = tmp_path / "worker-flamingo-99903-aabbcc01"
    run.mkdir()
    (run / "last-exit.json").write_text('{"reason":"already"}\n', encoding="utf-8")
    (run / "last-from.txt").write_text(
        "FROM jeeves #flamingo x: FR SimonBarnett/bobiverse#1 https://x\n",
        encoding="utf-8",
    )
    assert (
        bw.handle_disappeared_worker_run(run, pid_alive=lambda _pid: False) is None
    )


def test_fr8568_scan_multiple(tmp_path):
    a = tmp_path / "worker-flamingo-1-aaaaaaaa"
    b = tmp_path / "worker-flamingo-2-bbbbbbbb"
    for d, pid in ((a, 1), (b, 2)):
        d.mkdir()
        (d / "last-from.txt").write_text(
            f"FROM jeeves #flamingo x: MRB SimonBarnett/bobiverse#{pid} https://x\n",
            encoding="utf-8",
        )
    hits = bw.scan_disappeared_worker_runs(tmp_path, shop="flamingo", pid_alive=lambda _p: False)
    assert len(hits) == 2
    assert all(h["giveup"] for h in hits)


def test_fr8568_docs_breakaway_and_paste0():
    d = _read(DOCS)
    assert "FR #8568" in d
    assert "CREATE_BREAKAWAY_FROM_JOB" in d or "breakaway" in d.lower()
    assert "BOB_WORKER_INJECT_PASTE=0" in d
    assert "BOB_OPENCODE_FORCE_PAID=1" in d
