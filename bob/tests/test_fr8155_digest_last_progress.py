"""FR #8155: digest last_progress heartbeat separate from state-change updated."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import bob_worker as bw
import bobreport
import registered_machines as rm

from repo_layout import ROOT

TRAY = ROOT / "third_party" / "bob-tray"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")
HOVER = TRAY / "src" / "Public" / "Get-BobTrayHover.ps1"
DIALOGS = TRAY / "tools" / "BobTrayDialogs.ps1"


def _run(body: str, tmp_path: Path) -> list[str]:
    script = tmp_path / "t.ps1"
    script.write_bytes(
        (
            "\ufeff$ErrorActionPreference='Stop'\r\n"
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\r\n"
            f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\r\n"
            f". '{DIALOGS}'\r\n"
            "& (Get-Module BobBridge) {\r\n" + body + "\r\n}\r\n"
        ).encode("utf-8")
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace") + r.stdout.decode("utf-8", "replace")
    return r.stdout.decode("utf-8", "replace").splitlines()


def _seat(home: Path, mid: str = "flamingo", nick: str = "flamingo-8155") -> None:
    rm.sync_from_chanserv(home, ["#bobiverse", f"#{mid}"])
    assert bobreport.apply_callback(
        home,
        {"op": "worker-upsert", "machine": mid, "nick": nick, "kind": "opencode"},
    ).ok
    assert bobreport.apply_callback(
        home,
        {
            "op": "worker-work",
            "machine": mid,
            "nick": nick,
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8155",
            "kind": "opencode",
        },
    ).ok


def _worker_row(home: Path, mid: str, nick: str) -> dict:
    digest = bobreport.build_digest_object(home, "Jeeves")
    rows = digest["machines"][mid]["workers"]
    row = next(w for w in rows if w["nick"].lower() == nick.lower())
    return row


def test_sanitize_progress_phase_strips_paths_args_and_secrets():
    assert bobreport.sanitize_progress_phase("tool:bash") == "tool:bash"
    assert bobreport.sanitize_progress_phase("edit") == "edit"
    assert bobreport.sanitize_progress_phase("stream") == "stream"
    # Absolute path + flags must not survive.
    dirty = r"tool:bash C:\Users\EXAMPLE\secret\file.py --token FAKESECRET_a3b4c5d6e7f8g9h0i1j2"
    cleaned = bobreport.sanitize_progress_phase(dirty)
    assert "Users" not in cleaned
    assert "token" not in cleaned.lower() or cleaned == "redacted"
    assert "--" not in cleaned
    assert bobreport.sanitize_progress_phase("password=EXAMPLE_SECRET_VALUE") == "redacted"
    assert bobreport.sanitize_progress_phase("") == ""
    assert bobreport.sanitize_progress_phase(r"C:\only\path") == ""


def test_worker_work_progress_heartbeat_keeps_updated_frozen(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    mid, nick = "flamingo", "flamingo-8155"
    _seat(tmp_path, mid, nick)
    row1 = _worker_row(tmp_path, mid, nick)
    updated1 = row1["updated"]
    assert row1["state"] == "doing"
    # ACK/doing seeds last_progress; capture then heartbeat with a later ISO.
    time.sleep(1.1)
    later = "2026-01-02T03:04:05Z"
    out = bobreport.apply_callback(
        tmp_path,
        {
            "op": "worker-work",
            "machine": mid,
            "nick": nick,
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8155",
            "last_progress": later,
            "progress_phase": "tool:bash",
            "kind": "opencode",
        },
    )
    assert out.ok
    row2 = _worker_row(tmp_path, mid, nick)
    assert row2["updated"] == updated1, "state-change updated must stay frozen on progress heartbeat"
    assert row2["last_progress"] == later
    assert row2["progress_phase"] == "tool:bash"
    # Legacy pid workers also carry the activity fields.
    pid_workers = bobreport.load_digest(tmp_path)["machines"][mid].get("workers") or {}
    assert any(
        isinstance(v, dict) and v.get("last_progress") == later for v in pid_workers.values()
    )


def test_idle_clears_progress_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    mid, nick = "flamingo", "flamingo-8155"
    _seat(tmp_path, mid, nick)
    bobreport.apply_callback(
        tmp_path,
        {
            "op": "worker-work",
            "machine": mid,
            "nick": nick,
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8155",
            "last_progress": "2026-01-02T03:04:05Z",
            "progress_phase": "edit",
        },
    )
    # Force idle without accepted-work preserve (no gitclaim home hold).
    bobreport.apply_callback(
        tmp_path,
        {"op": "worker-work", "machine": mid, "nick": nick, "state": "idle", "work": ""},
    )
    row = _worker_row(tmp_path, mid, nick)
    assert row["state"] == "idle"
    assert "last_progress" not in row
    assert "progress_phase" not in row


def test_detect_seat_progress_growing_log_moves_frozen_does_not(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    log = run_dir / "session.log"
    log.write_text("start\n", encoding="utf-8")
    moved1, phase1, state1 = bw.detect_seat_progress(
        kind="opencode", run_dir=run_dir, job_worktree="", prev={}
    )
    # First poll establishes fingerprint; growth may or may not count as moved
    # depending on prev empty vs size 0. Force a second poll after growth.
    log.write_text("start\nmore output\ntool_call name=bash\n", encoding="utf-8")
    moved2, phase2, state2 = bw.detect_seat_progress(
        kind="opencode", run_dir=run_dir, job_worktree="", prev=state1
    )
    assert moved2 is True
    assert phase2
    assert "password" not in phase2.lower()
    assert "--" not in phase2
    # Frozen: same fingerprint -> no move.
    moved3, phase3, _state3 = bw.detect_seat_progress(
        kind="opencode", run_dir=run_dir, job_worktree="", prev=state2
    )
    assert moved3 is False


def test_detect_seat_progress_worktree_mtime(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    wt = tmp_path / "wt"
    git = wt / ".git"
    git.mkdir(parents=True)
    head = git / "HEAD"
    head.write_text("ref: refs/heads/fr-8155\n", encoding="utf-8")
    moved1, _p1, state1 = bw.detect_seat_progress(
        kind="grok", run_dir=run_dir, job_worktree=str(wt), prev={}
    )
    time.sleep(1.05)
    head.write_text("ref: refs/heads/fr-8155\n# bumped\n", encoding="utf-8")
    moved2, phase2, _ = bw.detect_seat_progress(
        kind="grok", run_dir=run_dir, job_worktree=str(wt), prev=state1
    )
    assert moved2 is True
    assert phase2 in ("edit", "stream") or phase2.startswith("tool:")


def test_post_digest_progress_heartbeat_payload_is_safe(monkeypatch, tmp_path):
    captured = {}

    def _fake_post(url, payload, log=None):
        captured["url"] = url
        captured["payload"] = dict(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    monkeypatch.setenv("BOB_REPORT_URL", "https://example.test/bob/v1/report")
    ok = bw.post_digest_progress_heartbeat(
        machine="flamingo",
        nick="flamingo-8155",
        pid=8155,
        kind="opencode",
        work="FR SimonBarnett/bobiverse#8155",
        last_progress="2026-01-02T03:04:05Z",
        progress_phase="tool:bash --secret=EXAMPLE",
    )
    assert ok is True
    p = captured["payload"]
    assert p["op"] == "worker-work"
    assert p["state"] == "doing"
    assert p["last_progress"] == "2026-01-02T03:04:05Z"
    assert "secret" not in str(p.get("progress_phase") or "").lower()
    assert "--" not in str(p.get("progress_phase") or "")
    assert p.get("progress_phase") == "tool:bash"
    blob = json.dumps(p)
    assert "EXAMPLE" not in blob or "bobiverse" in blob  # work string may cite repo
    assert "password" not in blob.lower()


def test_progress_heartbeat_interval_bounds():
    assert bw.progress_heartbeat_interval_s({}) == 120.0
    assert bw.progress_heartbeat_interval_s({"BOB_PROGRESS_HEARTBEAT_S": "30"}) == 30.0
    assert bw.progress_heartbeat_interval_s({"BOB_PROGRESS_HEARTBEAT_S": "5"}) == 30.0
    assert bw.progress_heartbeat_interval_s({"BOB_PROGRESS_HEARTBEAT_S": "9999"}) == 900.0
    assert bw.progress_heartbeat_interval_s({"BOB_PROGRESS_HEARTBEAT_S": "nope"}) == 120.0


def test_static_pins_mention_last_progress():
    h = HOVER.read_text(encoding="utf-8-sig")
    d = DIALOGS.read_text(encoding="utf-8-sig")
    fmt = h[h.index("function Format-BobTrayWorkerLine") : h.index("function Get-BobTrayDigestWorkers")]
    get = h[h.index("function Get-BobTrayDigestWorkers") : h.index("function Get-BobTrayTitle")]
    assert "last_progress" in fmt
    assert "progress_phase" in fmt
    assert "last_progress" in get
    assert "LastProgress" in d[d.index("function Format-BobTrayStatusWorkerLine") : d.index("function Get-BobTrayDigestWorkerLinesForMachine")]


@needs_ps
def test_tray_shows_last_progress_age(tmp_path):
    out = _run(
        """
$lp = ([datetime]::UtcNow.AddMinutes(-3)).ToString('yyyy-MM-ddTHH:mm:ssZ')
Format-BobTrayWorkerLine ([pscustomobject]@{nick='flamingo-1';state='doing';work='FR o/r#8155';last_progress=$lp;progress_phase='edit'})
Format-BobTrayWorkerLine ([pscustomobject]@{nick='flamingo-2';state='doing';work='FR o/r#8155'})
Format-BobTrayStatusWorkerLine -Nick 'flamingo-3' -State 'doing' -Work 'FR o/r#8155' -LastProgress $lp -ProgressPhase 'tool:bash'
""",
        tmp_path,
    )
    assert any("flamingo-1:" in ln and "progress" in ln and "edit" in ln for ln in out)
    # No last_progress -> no progress suffix (updated is not used as progress).
    assert out[1] == "flamingo-2: FR o/r#8155"
    assert any("flamingo-3:" in ln and "progress" in ln and "tool:bash" in ln for ln in out)


@needs_ps
def test_tray_digest_workers_carry_last_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    mid, nick = "flamingo", "flamingo-9001"
    _seat(tmp_path, mid, nick)
    # Past ISO so Get-BobJobAge returns a real age (future stamps parse as '?').
    later = "2026-01-02T12:00:00Z"
    assert bobreport.apply_callback(
        tmp_path,
        {
            "op": "worker-work",
            "machine": mid,
            "nick": nick,
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8155",
            "last_progress": later,
            "progress_phase": "stream",
        },
    ).ok
    d = tmp_path / "digest-out.json"
    digest = bobreport.build_digest_object(tmp_path, "Jeeves")
    row = next(w for w in digest["machines"][mid]["workers"] if w["nick"] == nick)
    assert row["last_progress"] == later
    assert row["progress_phase"] == "stream"
    d.write_text(json.dumps(digest, ensure_ascii=False), encoding="utf-8")
    out = _run(
        f"""
$doc = [System.IO.File]::ReadAllText('{d}', [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$w = @(Get-BobTrayDigestWorkers -Digest $doc -MachineId 'flamingo') | Where-Object {{ $_.nick -eq '{nick}' }}
'lp=' + $w.last_progress
'pp=' + $w.progress_phase
Format-BobTrayWorkerLine -Worker $w
""",
        tmp_path,
    )
    assert f"lp={later}" in out
    assert "pp=stream" in out
    assert any("progress" in ln and "stream" in ln for ln in out)
