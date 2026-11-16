"""FR #7899: capture read must not throw, and a hard-ceiling kill must GIVEUP once."""
from __future__ import annotations

import subprocess
from pathlib import Path

import bob_worker as bw
import opencode_turn_guard as g


def _launch_text(tmp_path: Path) -> str:
    spec = bw.build_launch("opencode", "agent", str(tmp_path), "hello", "opencode.exe", tmp_path)
    return next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))


def _ceiling_block(text: str) -> str:
    start = text.index("if ($stallMs -ge $hardCeilingMs)")
    end = text.index("if (($ocJobPoll % 50) -eq 0", start)
    return text[start:end]


def test_fr7899_wrapper_reads_with_share_and_ceiling_giveup(tmp_path: Path):
    text = _launch_text(tmp_path)
    assert "function Read-OpencodeCapture" in text
    assert "[System.IO.FileShare]::ReadWrite" in text
    assert "ReadAllText($outFile)" not in text
    assert "Read-OpencodeCapture $outFile" in text
    assert "capture-failed" in text
    block = _ceiling_block(text)
    assert block.count("Write-OpencodeJobGiveup") == 1
    assert "hard ceiling" in block


def test_fr7899_capture_read_degrades_when_file_is_locked(tmp_path: Path):
    text = _launch_text(tmp_path)
    start = text.index("function Read-OpencodeCapture")
    end = text.index("function Invoke-OpencodeRun", start)
    fn = text[start:end]
    held = tmp_path / "bob-oc-out-locked.txt"
    held.write_text("partial line\n", encoding="utf-8")
    script = tmp_path / "read.ps1"
    script.write_text(
        fn
        + "\n"
        + "$script:ocCaptureLogged = $false\n"
        + "$guardPy = 'missing-guard.py'\n"
        + f"$p = '{held}'\n"
        + "$fs = New-Object System.IO.FileStream($p, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)\n"
        + "try { $got = Read-OpencodeCapture $p; Write-Output ('RESULT=' + $got) } finally { $fs.Dispose() }\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "RESULT=" in proc.stdout
    assert "opencode-capture: read failed once" in proc.stdout or "RESULT=partial line" in proc.stdout


def test_fr7899_ceiling_giveup_once_and_done_while_file_open(tmp_path: Path):
    outbox = tmp_path / "outbox.txt"
    outbox.write_text("", encoding="utf-8")
    held = tmp_path / "bob-oc-out-open.txt"
    held.write_text("model said hello\n", encoding="utf-8")
    text = _launch_text(tmp_path)
    start = text.index("function Write-OpencodeJobGiveup")
    end = text.index("function Write-OpencodeJobNack", start)
    give = text[start:end]
    start_r = text.index("function Read-OpencodeCapture")
    end_r = text.index("function Invoke-OpencodeRun", start_r)
    reader = text[start_r:end_r]
    script = tmp_path / "finish.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        + f"$env:BOB_OUTBOX = '{outbox}'\n"
        + "$guardPy = 'missing-guard.py'\n"
        + give
        + "\n"
        + reader
        + "\n"
        + f"$p = '{held}'\n"
        + "$fs = New-Object System.IO.FileStream($p, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)\n"
        + "try {\n"
        + "  $stdout = Read-OpencodeCapture $p\n"
        + "  if (-not $stdout) { throw 'read returned empty while the file is shared' }\n"
        + "  Add-Content -LiteralPath $env:BOB_OUTBOX -Value 'DONE FR SimonBarnett/bobiverse#7899 https://example.invalid/pull/1'\n"
        + "  $jobKey = 'FR SimonBarnett/bobiverse#7899'\n"
        + "  $killReason = 'hard ceiling 1800000ms'\n"
        + "  Write-OpencodeJobGiveup $jobKey $killReason\n"
        + "} finally { $fs.Dispose() }\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    lines = [ln for ln in outbox.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines[0].startswith("DONE FR SimonBarnett/bobiverse#7899")
    giveups = [ln for ln in lines if ln.startswith("GIVEUP ")]
    assert giveups == ["GIVEUP FR SimonBarnett/bobiverse#7899 hard ceiling 1800000ms"]
    assert "password" not in proc.stdout.lower()
    assert held.exists()


def test_fr7899_capture_failed_reports_without_body():
    seen = {}

    def reporter(component, message, *, site=""):
        seen["component"] = component
        seen["message"] = message
        seen["site"] = site

    result = g.report_opencode_capture_read(
        "opencode-capture: read failed once\nsecret-looking body must not be a second field",
        reporter=reporter,
    )
    assert result["ok"] is True
    assert seen["site"] == "opencode-capture-read"
    assert seen["component"] == "bob-worker"
    assert "read failed once" in seen["message"]
    assert "\n" not in seen["message"]
