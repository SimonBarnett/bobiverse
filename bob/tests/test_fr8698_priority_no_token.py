"""FR #8698 / BOB-52: Priority no-token dialog + quit on fuel-empty fixture."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repo_layout import ROOT

PRIV = ROOT / "bob" / "tray" / "src" / "Private" / "Get-BobPriorityFuel.ps1"
PUB = ROOT / "bob" / "tray" / "src" / "Public" / "Invoke-BobPriorityNoTokenGate.ps1"
EVIDENCE = ROOT / "bob" / "docs" / "bob-52-priority-no-token-evidence.md"
EMPTY = ROOT / "bob" / "tests" / "fixtures" / "priority-fuel-empty.json"
OK = ROOT / "bob" / "tests" / "fixtures" / "priority-fuel-ok.json"


def _run_ps(script: Path):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_evidence_doc_exists():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-52" in text
    assert "no-token" in text
    assert "quit" in text.lower()


def test_fuel_empty_fixture_blocks_start(tmp_path: Path):
    assert json.loads(EMPTY.read_text(encoding="utf-8"))["remaining"] == 0
    log_path = tmp_path / "priority-no-token-gate.log"
    priv = PRIV.as_posix()
    pub = PUB.as_posix()
    empty = EMPTY.as_posix()
    logp = log_path.as_posix()
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        f". '{priv}'\n"
        f". '{pub}'\n"
        f"$g = Invoke-BobPriorityNoTokenGate -FixturePath '{empty}' -LogPath '{logp}' -NoUi -Quiet\n"
        "if ($g.AllowStart) { throw 'must refuse' }\n"
        "if (-not $g.Quit) { throw 'must quit' }\n"
        "if ($g.Dialog -ne 'no-tokens') { throw 'dialog' }\n"
        f"$s = Start-BobTrayPriorityAgent -FixturePath '{empty}' -LogPath '{logp}' -NoUi\n"
        "if ($s.Started) { throw 'must not start' }\n"
        "if (-not $s.Quit) { throw 'start must quit' }\n"
    )
    script = tmp_path / "run-empty.ps1"
    script.write_text(ps, encoding="utf-8")
    proc = _run_ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = log_path.read_text(encoding="utf-8")
    assert "dialog=no-tokens" in body
    assert "quit=true" in body
    assert "start=blocked" in body
    assert "gate=refuse" in body


def test_fuel_ok_allows_gate(tmp_path: Path):
    log_path = tmp_path / "ok.log"
    priv = PRIV.as_posix()
    pub = PUB.as_posix()
    ok = OK.as_posix()
    logp = log_path.as_posix()
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        f". '{priv}'\n"
        f". '{pub}'\n"
        f"$g = Invoke-BobPriorityNoTokenGate -FixturePath '{ok}' -LogPath '{logp}' -NoUi -Quiet\n"
        "if (-not $g.AllowStart) { throw 'must allow' }\n"
        "if ($g.Quit) { throw 'must not quit' }\n"
    )
    script = tmp_path / "run-ok.ps1"
    script.write_text(ps, encoding="utf-8")
    proc = _run_ps(script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = log_path.read_text(encoding="utf-8")
    assert "gate=allow" in body
    assert "start=allowed" in body
