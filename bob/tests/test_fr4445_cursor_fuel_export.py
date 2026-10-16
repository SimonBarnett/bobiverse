"""FR #4445: export Cursor group remain so Get-BobAgentFuel reports pools."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from repo_layout import ROOT

import bob_worker as bw

_FN = "Get-BobCursorGroupRemainFromLocalDoc"
_FIXTURE = {
    "period": {
        "planUsage": {"autoPercentUsed": 0, "apiPercentUsed": 25},
        "billingCycleEnd": "2026-11-16T17:23:01Z",
    }
}


def _exports(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_fr4445_function_is_exported_from_bobbridge():
    psd1 = _exports("tray/src/BobBridge.psd1")
    psm1 = _exports("tray/src/BobBridge.psm1")
    assert f"'{_FN}'" in psd1
    assert f"'{_FN}'" in psm1


def _run_fuel(tmp_path: Path, *, fault: str | None) -> dict:
    fix = tmp_path / "cursor-agent-fixture.json"
    fix.write_text(json.dumps(_FIXTURE), encoding="utf-8")
    env = os.environ.copy()
    env["BOB_CURSOR_AGENT_FIXTURE"] = str(fix)
    env.pop("BOB_CURSOR_USAGE_FILE", None)
    if fault:
        env["BOB_AGENT_FUEL_CURSOR_FAULT"] = fault
    else:
        env.pop("BOB_AGENT_FUEL_CURSOR_FAULT", None)
    script = ROOT / "tray" / "tools" / "Get-BobAgentFuel.ps1"
    install = ROOT / "tray"
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-InstallRoot",
            str(install),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    line = ""
    for raw in reversed((r.stdout or "").splitlines()):
        raw = raw.strip().lstrip("\ufeff")
        if raw.startswith("{"):
            line = raw
            break
    assert line, r.stdout
    return json.loads(line)


def test_fr4445_fixture_doc_returns_cursor_pools_and_selects_cursor(tmp_path: Path):
    doc = _run_fuel(tmp_path, fault=None)
    cur = doc["cursor"]
    assert cur["high"] == 75
    assert cur["low"] == 100
    assert "error" not in cur
    fuel = bw.Fuel(cur["high"], cur["low"], 0, "exhausted")
    decision = bw.select_agent(fuel, r"C:\cursor-agent\agent.cmd", r"C:\grok\agent.exe")
    assert decision.kind == "cursor"


def test_fr4445_reader_exception_sets_cursor_error(tmp_path: Path):
    doc = _run_fuel(tmp_path, fault="stage-missing-export")
    err = doc["cursor"].get("error") or ""
    assert "stage-missing-export" in err
    assert doc["cursor"]["high"] is None
    assert doc["cursor"]["low"] is None
