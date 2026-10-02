"""FR #113: BOB_DIGEST_CAPTURE / WEBHOOK_CAPTURE must always write ndjson (Assert hermetic path)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY = ROOT / "third_party" / "bob-tray"
IRC = TRAY / "src" / "Private" / "Get-BobIrc.ps1"
ASSERT = ROOT / "scripts" / "Assert-BobDigestWebhookLocal.ps1"
if not ASSERT.is_file():
    ASSERT = ROOT.parents[0] / "jeeves" / "scripts" / "Assert-BobDigestWebhookLocal.ps1"

PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_capture_helper_and_force_path_exist_in_source():
    irc = _txt(IRC)
    assert "function Get-BobDigestWebhookCapturePath" in irc
    assert "BOB_DIGEST_CAPTURE" in irc
    assert "BOB_DIGEST_WEBHOOK_CAPTURE" in irc
    assert "forceCapture" in irc
    send = irc[irc.index("function Send-BobDigestWebhookIfChanged") : irc.index("function Write-BobIrcStatus")]
    assert "$forceCapture" in send
    assert "Get-BobDigestWebhookCapturePath" in send


def test_assert_script_sets_both_capture_env_names():
    assert ASSERT.is_file(), ASSERT
    t = _txt(ASSERT)
    assert "BOB_DIGEST_WEBHOOK_CAPTURE" in t
    assert "BOB_DIGEST_CAPTURE" in t
    assert "Get-BobDigestWebhookCapturePath" in t or "FR #113" in t


@needs_ps
def test_capture_env_writes_even_when_fingerprint_unchanged(tmp_path: Path):
    """Regression: second Write-BobIrcStatus with capture set must still create the ndjson file."""
    cap = tmp_path / "cap.ndjson"
    script = tmp_path / "t.ps1"
    body = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{TRAY / "src" / "BobBridge.psd1"}' -Force -DisableNameChecking
$env:BOB_DIGEST_CAPTURE = '{cap}'
Remove-Item Env:BOB_DIGEST_WEBHOOK_CAPTURE -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $env:BOB_DIGEST_CAPTURE) {{ Remove-Item -LiteralPath $env:BOB_DIGEST_CAPTURE -Force }}
& (Get-Module BobBridge) {{
  $doc = Write-BobIrcStatus -PassThru -SkipDigestWebhook
  if (-not $doc) {{ throw 'Write-BobIrcStatus returned nothing (config/home?)' }}
  # Seed posted state so a normal Send would skip on fingerprint.
  $fp = Get-BobDigestWebhookFingerprint $doc
  $mid = [string]$doc.id
  $state = Get-BobDigestWebhookPostStatePath
  New-Item -ItemType Directory -Force -Path (Split-Path $state -Parent) | Out-Null
  Write-JsonFile $state ([pscustomobject]@{{ $mid = $fp; ($mid + '@posted_at') = [string]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) }})
  $code = Send-BobDigestWebhookIfChanged -Doc $doc -Before $doc
  if (-not (Test-Path -LiteralPath $env:BOB_DIGEST_CAPTURE)) {{
    throw "capture missing after forced Send code=$code"
  }}
  # Delete and send again immediately (heartbeat not due) — must rewrite.
  Remove-Item -LiteralPath $env:BOB_DIGEST_CAPTURE -Force
  $code2 = Send-BobDigestWebhookIfChanged -Doc $doc -Before $doc
  if (-not (Test-Path -LiteralPath $env:BOB_DIGEST_CAPTURE)) {{
    throw "capture missing on second Send code=$code2 (fingerprint skip bug)"
  }}
  Write-Output 'CAPTURE_OK'
}}
"""
    script.write_bytes(("\ufeff" + body).encode("utf-8"))
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        timeout=180,
    )
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0, err or out
    assert "CAPTURE_OK" in out
