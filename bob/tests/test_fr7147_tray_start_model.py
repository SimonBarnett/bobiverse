"""FR #7147: tray seat list shows digest CLI + start_model + mismatch (no secrets)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_fr7147_format_helpers_mention_start_model():
    """Static pin: both TipForm and Status formatters read start_model / mismatch."""
    h = HOVER.read_text(encoding="utf-8-sig")
    d = DIALOGS.read_text(encoding="utf-8-sig")
    assert "start_model" in h[h.index("function Format-BobTrayWorkerLine") : h.index("function Get-BobTrayDigestWorkers")]
    assert "model_mismatch" in h[h.index("function Format-BobTrayWorkerLine") : h.index("function Get-BobTrayDigestWorkers")]
    assert "start_model" in d[d.index("function Format-BobTrayStatusWorkerLine") : d.index("function Get-BobTrayDigestWorkerLinesForMachine")]
    assert "start_model" in d[d.index("function Get-BobTrayDigestWorkerLinesForMachine") : d.index("function Sync-BobTrayStatusWorkersFromDigest")]
    assert "start_model" in h[h.index("function Get-BobTrayDigestWorkers") : h.index("function Get-BobTrayTitle")]


@needs_ps
def test_fr7147_worker_line_includes_cli_start_model_and_mismatch(tmp_path):
    out = _run(
        """
Format-BobTrayWorkerLine ([pscustomobject]@{nick='redqueen-101';state='idle';work='';kind='grok';start_model='EXAMPLE_GROK_MIN';model_mismatch=$false})
Format-BobTrayWorkerLine ([pscustomobject]@{nick='redqueen-102';state='doing';work='FR o/r#7';kind='grok';start_model='EXAMPLE_GROK_MAX';model_mismatch=$true})
Format-BobTrayWorkerLine ([pscustomobject]@{nick='redqueen-103';state='idle';work=''})
Format-BobTrayStatusWorkerLine -Nick 'redqueen-201' -State 'idle' -Work '' -Kind 'cursor' -StartModel 'EXAMPLE_CUR_MIN' -ModelMismatch:$false
Format-BobTrayStatusWorkerLine -Nick 'redqueen-202' -State 'offered' -Work 'bobiverse FR #1' -Kind 'opencode' -StartModel 'EXAMPLE_OC_MIN' -ModelMismatch:$true
""",
        tmp_path,
    )
    assert out == [
        "redqueen-101: [grok/EXAMPLE_GROK_MIN] idle",
        "redqueen-102: [grok/EXAMPLE_GROK_MAX!] FR o/r#7",
        "redqueen-103: idle",
        "redqueen-201: [cursor/EXAMPLE_CUR_MIN] idle",
        "redqueen-202: [opencode/EXAMPLE_OC_MIN!] offered: bobiverse FR #1",
    ]


@needs_ps
def test_fr7147_digest_worker_lines_carry_start_model(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#redqueen"])
    assert bobreport.apply_callback(
        tmp_path,
        {
            "op": "worker-upsert",
            "machine": "redqueen",
            "nick": "redqueen-4242",
            "kind": "grok",
            "start_model": "EXAMPLE_GROK_MIN",
            "configured_model": "EXAMPLE_GROK_MIN",
            "model_mismatch": False,
        },
    ).ok
    assert bobreport.apply_callback(
        tmp_path,
        {
            "op": "worker-work",
            "machine": "redqueen",
            "nick": "redqueen-4242",
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#7147",
            "kind": "grok",
            "start_model": "EXAMPLE_GROK_MAX",
            "configured_model": "EXAMPLE_GROK_MIN",
            "model_mismatch": True,
        },
    ).ok
    d = tmp_path / "digest-out.json"
    digest = bobreport.build_digest_object(tmp_path, "Jeeves")
    workers = digest["machines"]["redqueen"]["workers"]
    assert any(w.get("start_model") == "EXAMPLE_GROK_MAX" for w in workers)
    assert any(w.get("model_mismatch") is True for w in workers)
    d.write_text(json.dumps(digest, ensure_ascii=False), encoding="utf-8")
    out = _run(
        f"""
$doc = [System.IO.File]::ReadAllText('{d}', [System.Text.Encoding]::UTF8) | ConvertFrom-Json
foreach ($w in @(Get-BobTrayDigestWorkers -Digest $doc -MachineId 'redqueen')) {{ Format-BobTrayWorkerLine -Worker $w }}
Get-BobTrayDigestWorkerLinesForMachine -Digest $doc -MachineId 'redqueen'
""",
        tmp_path,
    )
    assert any("EXAMPLE_GROK_MAX!" in line and "redqueen-4242" in line for line in out)
    assert any("[grok/EXAMPLE_GROK_MAX!]" in line for line in out)
