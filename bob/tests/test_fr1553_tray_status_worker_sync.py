"""FR #1553: TipForm workers refresh from digest when Get-BobTrayHover hangs."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY = ROOT / "third_party" / "bob-tray"
DIALOGS = TRAY / "tools" / "BobTrayDialogs.ps1"
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_sync_function_and_watch_wiring_static():
    d = _txt(DIALOGS)
    w = _txt(WATCH)
    assert "function Sync-BobTrayStatusWorkersFromDigest" in d
    assert "TimeoutSec = 8" in d or "TimeoutSec=8" in d.replace(" ", "")
    body = d[d.index("function Sync-BobTrayStatusWorkersFromDigest") : d.index("function Sync-BobTrayStatusWorkersFromDigest") + 3500]
    # Must not *call* hover (comment may mention the name).
    assert "Get-BobTrayHover" not in body.replace("WITHOUT Get-BobTrayHover", "")
    assert "Sync-BobTrayStatusWorkersFromDigest" in w
    assert "System.Timers.Timer" in w
    assert "SynchronizingObject = $null" in w
    poll = w[w.index("$poll.Add_Tick") : w.index("$poll.Add_Tick") + 1200]
    assert poll.index("Sync-BobTrayStatusWorkersFromDigest") < poll.index("Update-Hover")


@needs_ps
def test_sync_rewrites_stale_worker_lines_from_digest(tmp_path: Path):
    root = tmp_path / "bob"
    run = root / "run"
    run.mkdir(parents=True)
    status = {
        "v": 1,
        "ts": 1,
        "title": "bob marchhare",
        "machine": "marchhare",
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
                "heading": "MARCHHARE  -  ntsa (40%)",
                "red": False,
                "help": "",
                "workers": ["marchhare-1: MRB #1529 stale"],
            }
        ],
        "alert": "none",
        "alerts": [],
        "version": "bob 0.1.0",
    }
    (run / "tray-status.json").write_text(json.dumps(status), encoding="utf-8")
    digest_path = tmp_path / "digest.json"
    digest_path.write_text(
        json.dumps(
            {
                "machines": {
                    "marchhare": {
                        "workers": [
                            {"nick": "marchhare-41928", "state": "doing", "work": "bobiverse FR #1553"},
                            {"nick": "marchhare-2", "state": "idle", "work": ""},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    script = tmp_path / "sync.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{DIALOGS}'
$digest = Get-Content -LiteralPath '{digest_path}' -Raw | ConvertFrom-Json
$p = Sync-BobTrayStatusWorkersFromDigest -Root '{root}' -Digest $digest
if (-not $p) {{ throw 'sync returned null' }}
$j = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
$w = @($j.grok[0].workers)
($w -join '|')
'ts=' + $j.ts
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    joined = next(ln for ln in lines if "|" in ln or "marchhare-41928" in ln)
    assert "marchhare-41928: bobiverse FR #1553" in joined
    assert "marchhare-2: idle" in joined
    assert "MRB #1529" not in joined
    assert any(ln.startswith("ts=") and ln != "ts=1" for ln in lines)


@needs_ps
def test_format_status_worker_line(tmp_path: Path):
    script = tmp_path / "fmt.ps1"
    script.write_text(
        f"""
. '{DIALOGS}'
Format-BobTrayStatusWorkerLine -Nick 'a-1' -State 'doing' -Work 'FR x'
Format-BobTrayStatusWorkerLine -Nick 'a-2' -State 'idle' -Work 'stale'
Format-BobTrayStatusWorkerLine -Nick 'a-3' -State 'offered' -Work 'UAT #1'
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert out == ["a-1: FR x", "a-2: idle", "a-3: offered: UAT #1"]
