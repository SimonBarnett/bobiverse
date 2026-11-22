"""FR #8988: fresh tray-digest-pools.json is the last-good digest when GET fails."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tray" / "src" / "Private" / "Invoke-BobDigestHttpGet.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def test_source_pins_retry_and_pools_fallback():
    text = HELPER.read_text(encoding="utf-8-sig")
    assert "function Invoke-BobDigestHttpGetWithRetry" in text
    assert "function Read-BobTrayDigestPoolsFallback" in text
    assert "GetResponse" in text
    hover = (ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1").read_text(encoding="utf-8-sig")
    assert "Invoke-BobDigestHttpGetWithRetry" in hover
    assert "TimeoutSec 12" in hover
    irc = (ROOT / "tray" / "src" / "Private" / "Get-BobIrc.ps1").read_text(encoding="utf-8-sig")
    assert "Read-BobTrayDigestPoolsFallback" in irc


@needs_ps
def test_fresh_pools_file_returns_last_good_meters(tmp_path):
    now = 1_763_800_000
    # Use a ts close to now so age stays inside 900s. The script overwrites ts.
    pools = {
        "digest_ok": True,
        "ts": now,
        "grok": [{"heading": "MARCHHARE 54%", "remaining_pct": 54}],
        "opencode_go": 80,
    }
    run = tmp_path / "run"
    run.mkdir()
    (run / "tray-digest-pools.json").write_text(json.dumps(pools), encoding="utf-8")
    script = """
$env:BOB_INSTALL_ROOT = '%s'
. '%s'
$doc = Get-Content -LiteralPath (Join-Path $env:BOB_INSTALL_ROOT 'run\\tray-digest-pools.json') -Raw | ConvertFrom-Json
$doc.ts = [int64][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText((Join-Path $env:BOB_INSTALL_ROOT 'run\\tray-digest-pools.json'), ($doc | ConvertTo-Json -Depth 6), $utf8)
$fb = Read-BobTrayDigestPoolsFallback
if (-not $fb) { 'NONE'; exit 0 }
$m = $fb.machines.MARCHHARE.xai_weekly
'{0}|{1}|{2}|{3}' -f $m.remaining_pct, $m.fresh, $m.age_s, $fb.note
""" % (str(tmp_path).replace("'", "''"), str(HELPER).replace("'", "''"))
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    line = [x for x in r.stdout.splitlines() if "|" in x][-1]
    pct, fresh, age, note = line.split("|", 3)
    assert pct == "54"
    assert fresh == "False"
    assert int(age) >= 0
    assert "last-good digest age" in note


@needs_ps
def test_stale_or_failed_pools_are_ignored(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "tray-digest-pools.json").write_text(
        json.dumps({"digest_ok": False, "ts": 1, "grok": []}), encoding="utf-8"
    )
    script = """
$env:BOB_INSTALL_ROOT = '%s'
. '%s'
$fb = Read-BobTrayDigestPoolsFallback
if ($fb) { 'HIT' } else { 'NONE' }
""" % (str(tmp_path).replace("'", "''"), str(HELPER).replace("'", "''"))
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "NONE" in r.stdout
