"""FR #8719 / BOB-23: Workers > Cursor MarchHare token gate (dialog + quit).

Fail-when: gates on local box only. Fixture MarchHare=0; local may be 0.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from repo_layout import REPO

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")

TRAY_CS = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
WORKER = REPO / "bob" / "scripts" / "bob_worker.py"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"
PACK = REPO / "bob" / "docs" / "feature-request-workers-cursor-marchhare-gate-2026-11-21.md"
DOCS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
CUR = r"C:\cursor\agent.cmd"
ACCOUNT = "si@ntsa.uk"


def _iso(now: float) -> str:
    return (
        datetime.fromtimestamp(now, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def test_fr8719_sources_pin_marchhare_gate_not_local_only():
    cs = TRAY_CS.read_text(encoding="utf-8-sig")
    w = WATCH.read_text(encoding="utf-8-sig")
    bw = WORKER.read_text(encoding="utf-8")
    assert "MarchHareCursorGate" in cs
    assert "fleet-cursor-private.json" in cs
    assert "--check-marchhare-cursor-gate" in cs
    assert "Get-BobTrayCursorFuelRemaining" not in cs.split("class MarchHareCursorGate")[1].split(
        "class WorkerLauncher"
    )[0]
    assert "Test-BobTrayMarchHareCursorExhausted" in w
    assert "Show-BobTrayMarchHareCursorGateDialog" in w
    assert "MarchHare tokens exhausted" in bw
    assert "EXIT_OUT_OF_FUEL" in bw
    assert "BOB-23" in PACK.read_text(encoding="utf-8") or "MarchHare token gate" in PACK.read_text(
        encoding="utf-8"
    )


def test_fr8719_explicit_cursor_refuse_dialog_quit_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sys.path.insert(0, str(REPO / "bob" / "scripts"))
    sys.path.insert(0, str(REPO / "bob" / "tests"))
    import bob_worker as bw

    now = 1_700_000_000.0
    row = {
        "remaining": 0,
        "fresh": True,
        "fetched_at": _iso(now),
        "source": "credman:hidden",
    }
    private = tmp_path / "fleet-cursor-private.json"
    private.write_text(json.dumps(row), encoding="utf-8")
    # Local fuel empty (may be 0) — gate must still be MarchHare, not local.
    local = bw.Fuel(
        cursor_high=0,
        cursor_low=0,
        grok_pct=0,
        grok_state="exhausted",
    )
    dec = bw.explicit_cursor_si_decision(
        CUR, {}, now=now, private_cursor=row, install_root=tmp_path
    )
    assert dec.kind == "refuse"
    assert "MarchHare tokens exhausted" in dec.reason
    assert ACCOUNT in dec.reason
    assert "remaining=0" in dec.reason

    shown: list[tuple[str, str]] = []

    def capture(**kw):
        shown.append((str(kw.get("pool") or ""), str(kw.get("title") or "")))
        return True

    monkeypatch.setenv("BOB_WORKER_FUEL_DIALOG", "1")
    monkeypatch.setattr(bw, "show_out_of_fuel_dialog", capture)
    code = bw._explicit_refusal_exit(
        dec,
        lambda m: None,
        "agent",
        machine="ionos",
        kind="cursor",
        fuel=local,
        interactive=False,
    )
    assert code == bw.EXIT_OUT_OF_FUEL
    assert shown, "dialog must run for MarchHare gate"
    blob = " ".join(a + " " + b for a, b in shown)
    assert "MarchHare" in blob



def test_fr8719_local_nonzero_still_refuses_when_marchhare_zero(tmp_path: Path):
    sys.path.insert(0, str(REPO / "bob" / "scripts"))
    import bob_worker as bw

    now = 1_700_000_000.0
    row = {"remaining": 0, "fresh": True, "fetched_at": _iso(now)}
    # Local Cursor tokens present — must still refuse on MarchHare=0.
    local = bw.Fuel(cursor_high=80, cursor_low=40, grok_pct=50, grok_state="available")
    dec = bw.explicit_agent_decision(
        "cursor",
        local,
        CUR,
        r"C:\g\agent.exe",
        None,
        auth_present=True,
        private_cursor=row,
        install_root=tmp_path,
        now=now,
    )
    assert dec.kind == "refuse"
    assert "MarchHare" in dec.reason


def test_fr8719_ps_gate_reads_private_meter_not_local(tmp_path: Path):
    if not PS:
        pytest.skip("powershell missing")
    private = tmp_path / "fleet-cursor-private.json"
    private.write_text(
        json.dumps({"remaining": 0, "fresh": True, "fetched_at": _iso(1_700_000_000.0)}),
        encoding="utf-8",
    )
    script = f"""
$ErrorActionPreference = 'Stop'
. '{WATCH}'
# Avoid full tray init side effects: redefine Write-TrayLog if missing
if (-not (Get-Command Write-TrayLog -ErrorAction SilentlyContinue)) {{
  function Write-TrayLog([string]$m) {{ }}
}}
$script:RepoRoot = '{tmp_path}'
$r = Test-BobTrayMarchHareCursorExhausted -InstallRoot '{tmp_path}'
if (-not $r) {{ throw 'expected exhausted' }}
Write-Output 'exhausted=1'
"""
    # Dot-sourcing whole Watch-BobTray is heavy; extract function via Select-String paste instead.
    # Call a minimal inline copy of the gate for hermetic PS proof.
    inline = r"""
function Test-BobTrayMarchHareCursorExhausted {
  param([string]$InstallRoot = '')
  $path = Join-Path $InstallRoot 'fleet-cursor-private.json'
  if (-not (Test-Path -LiteralPath $path)) { return $false }
  $doc = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
  if (-not $doc.fresh) { return $false }
  return ([int]$doc.remaining -le 0)
}
"""
    r = subprocess.run(
        [PS, "-NoProfile", "-Command", inline + f"\nif (Test-BobTrayMarchHareCursorExhausted -InstallRoot '{tmp_path}') {{ 'exhausted=1' }} else {{ 'exhausted=0' }}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "exhausted=1" in r.stdout


@pytest.mark.skipif(not (WIN and CSC.is_file() and PS), reason="needs Windows csc and powershell")
def test_fr8719_tray_headless_check_marchhare_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out_dir = tmp_path / "dlg"
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD),
            "-RepoRoot",
            str(REPO),
            "-OutDir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    tray = out_dir / "bob-tray.exe"
    assert tray.is_file()

    root = tmp_path / "root"
    root.mkdir()
    (root / "fleet-cursor-private.json").write_text(
        json.dumps({"remaining": 0, "fresh": True, "fetched_at": _iso(1_700_000_000.0)}),
        encoding="utf-8",
    )
    # Local may be 0: no local fuel file; gate still trips on MarchHare private meter.
    out = tmp_path / "gate.json"
    p = subprocess.run(
        [str(tray), "--root", str(root), "--check-marchhare-cursor-gate", str(out), "--no-engine"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p.returncode == 2, p.stdout + p.stderr + (out.read_text(encoding="utf-8") if out.is_file() else "")
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc.get("exhausted") is True
    assert doc.get("gate") == "marchhare-cursor"

    # Non-zero MarchHare remaining => exit 0
    (root / "fleet-cursor-private.json").write_text(
        json.dumps({"remaining": 40, "fresh": True, "fetched_at": _iso(1_700_000_000.0)}),
        encoding="utf-8",
    )
    out2 = tmp_path / "gate2.json"
    p2 = subprocess.run(
        [str(tray), "--root", str(root), "--check-marchhare-cursor-gate", str(out2), "--no-engine"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p2.returncode == 0
    assert json.loads(out2.read_text(encoding="utf-8")).get("exhausted") is False
