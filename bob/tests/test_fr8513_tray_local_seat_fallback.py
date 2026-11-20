"""FR #8513: TipForm sync keeps local seat ledger when digest fetch fails / workers=[]."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray"
DIALOGS = TRAY / "tools" / "BobTrayDialogs.ps1"
if not DIALOGS.is_file():
    DIALOGS = ROOT / "third_party" / "bob-tray" / "tools" / "BobTrayDialogs.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_local_seat_helper_and_sync_wiring_static():
    d = _txt(DIALOGS)
    assert "function Get-BobTrayLocalSeatWorkerLines" in d
    assert "FR #8513" in d
    body = d[
        d.index("function Sync-BobTrayStatusWorkersFromDigest") : d.index(
            "function Sync-BobTrayStatusWorkersFromDigest"
        )
        + 6500
    ]
    assert "Get-BobTrayLocalSeatWorkerLines" in body
    assert "fetchFailed" in body or "MarkStale" in body
    assert "stale" in body.lower()


@needs_ps
def test_sync_empty_digest_uses_local_seat_ledger(tmp_path: Path):
    root = tmp_path / "bob"
    run = root / "run"
    run.mkdir(parents=True)
    seats = tmp_path / "seats"
    seats.mkdir()
    (seats / "redqueen-9192.irc.json").write_text(
        json.dumps(
            {
                "v": 1,
                "nick": "redqueen-9192",
                "pid": os.getpid(),
                "machine": "redqueen",
                "shop": "#redqueen",
                "mode": "agent",
            }
        ),
        encoding="utf-8",
    )
    status = {
        "v": 1,
        "ts": 1,
        "title": "bob redqueen",
        "machine": "redqueen",
        "short": "tip",
        "attention": False,
        "attention_seq": 0,
        "pulse": False,
        "overspend": "",
        "cursor": [],
        "grok": [
            {
                "known": True,
                "pct": 40,
                "r": 1,
                "g": 2,
                "b": 3,
                "heading": "REDQUEEN  -  ntsa (40%)",
                "red": False,
                "help": "",
                "workers": ["redqueen-9192: idle"],
            }
        ],
        "alert": "none",
        "alerts": [],
        "version": "bob 0.1.0",
    }
    (run / "tray-status.json").write_text(json.dumps(status), encoding="utf-8")
    digest_path = tmp_path / "digest.json"
    digest_path.write_text(
        json.dumps({"machines": {"redqueen": {"online": True, "workers": []}}}),
        encoding="utf-8",
    )
    script = tmp_path / "sync.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{DIALOGS}'
$digest = Get-Content -LiteralPath '{digest_path}' -Raw | ConvertFrom-Json
$p = Sync-BobTrayStatusWorkersFromDigest -Root '{root}' -Digest $digest -SeatsDir '{seats}'
if (-not $p) {{ throw 'sync returned null' }}
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$w = @($j.grok[0].workers)
($w -join '|')
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        timeout=60,
    )
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    err = (r.stderr or b"").decode("utf-8", errors="replace")
    assert r.returncode == 0, err + out
    joined = "\n".join(ln.strip() for ln in out.splitlines() if ln.strip())
    assert "redqueen-9192" in joined
    assert "stale" in joined.lower()


@needs_ps
def test_sync_digest_drop_clears_when_no_local_seats(tmp_path: Path):
    root = tmp_path / "bob"
    run = root / "run"
    run.mkdir(parents=True)
    seats = tmp_path / "seats-empty"
    seats.mkdir()
    status = {
        "v": 1,
        "ts": 1,
        "title": "bob redqueen",
        "machine": "redqueen",
        "short": "tip",
        "attention": False,
        "attention_seq": 0,
        "pulse": False,
        "overspend": "",
        "cursor": [],
        "grok": [
            {
                "known": True,
                "pct": 40,
                "r": 1,
                "g": 2,
                "b": 3,
                "heading": "REDQUEEN  -  ntsa (40%)",
                "red": False,
                "help": "",
                "workers": ["redqueen-1: idle", "redqueen-2: idle"],
            }
        ],
        "alert": "none",
        "alerts": [],
        "version": "bob 0.1.0",
    }
    (run / "tray-status.json").write_text(json.dumps(status), encoding="utf-8")
    digest_path = tmp_path / "digest.json"
    digest_path.write_text(
        json.dumps({"machines": {"redqueen": {"online": True, "workers": []}}}),
        encoding="utf-8",
    )
    script = tmp_path / "sync2.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{DIALOGS}'
$digest = Get-Content -LiteralPath '{digest_path}' -Raw | ConvertFrom-Json
$p = Sync-BobTrayStatusWorkersFromDigest -Root '{root}' -Digest $digest -SeatsDir '{seats}'
if (-not $p) {{ throw 'sync returned null' }}
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$w = @($j.grok[0].workers)
'count=' + $w.Count
($w -join '|')
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        timeout=60,
    )
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    err = (r.stderr or b"").decode("utf-8", errors="replace")
    assert r.returncode == 0, err + out
    assert "count=0" in out
    assert "redqueen-1" not in out
