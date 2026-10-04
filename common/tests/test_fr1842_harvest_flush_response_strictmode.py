"""FR #1842: Invoke-BobiverseHarvest Get-IntakeHttpStatus is StrictMode-safe for .Response."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / "common/scripts/Invoke-BobiverseHarvest.ps1"


def test_fr1842_harvest_response_strictmode_guard():
    # WinPS 5.1: .ps1 may carry UTF-8 BOM (required when non-ASCII); either is OK.
    raw = HARVEST.read_bytes()
    text = raw.decode("utf-8-sig")
    assert "Set-StrictMode" in text
    assert "Get-IntakeHttpStatus" in text
    assert "FR #1842" in text
    assert "Properties['Response']" in text
    assert "if ($ex.Response -and" not in text
    assert raw.endswith(b"\n")


def test_fr1842_live_strictmode_probe():
    inline = r"""
Set-StrictMode -Version Latest
function Get-IntakeHttpStatus {
    param($ErrorRecord)
    $ex = $ErrorRecord.Exception
    while ($null -ne $ex) {
        $resp = $null
        if ($null -ne $ex.PSObject -and $ex.PSObject.Properties['Response']) {
            try { $resp = $ex.Response } catch { $resp = $null }
        }
        if ($resp) {
            $code = $null
            if ($resp.PSObject.Properties['StatusCode']) {
                try { $code = $resp.StatusCode } catch { $code = $null }
            }
            if ($null -ne $code) {
                try { return [int]$code } catch { }
                try { return [int]$code.value__ } catch { }
            }
        }
        $ex = $ex.InnerException
    }
    if ($ErrorRecord.Exception.Message -match '\(502\)') { return 502 }
    return $null
}
try { throw (New-Object System.Exception 'boom (502)') } catch {
  $code = Get-IntakeHttpStatus -ErrorRecord $_
  if ($code -ne 502) { throw "expected 502 got $code" }
  Write-Output 'OK'
}
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", inline],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "OK" in r.stdout
