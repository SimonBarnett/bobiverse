"""FR #3965: Fetch-Ergo/Wix/Nssm must not hang in hidden WinPS 5.1 hosts.

Pins: ProgressPreference, curl --max-time helpers, Wix TimeoutSec, Ergo sha256,
Nssm archive.org mirror + BOBIVERSE_NSSM_MIRROR, tar/ZipFile extract (no Expand-Archive).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from repo_layout import ROOT

S = ROOT / "common" / "scripts"
HELPERS = S / "Bobiverse-FetchHelpers.ps1"
ERGO = S / "Fetch-Ergo.ps1"
WIX = S / "Fetch-Wix.ps1"
NSSM = S / "Fetch-Nssm.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")

ERGO_SHA = "5397fac56f7110839aac2d8ab436279eb2a00dddfcc07032605b423e85ea40b6"
NSSM_SHA = "727d1e42275c605e0f04aba98095c38a8e1e46def453cdffce42869428aa6743"
NSSM_MIRROR = (
    "https://web.archive.org/web/20220301000000id_/"
    "https://nssm.cc/release/nssm-2.24.zip"
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr3965_helpers_exist_with_curl_and_no_expand_archive_stall():
    assert HELPERS.is_file(), HELPERS
    t = _read(HELPERS)
    assert "FR #3965" in t
    assert "ProgressPreference" in t
    assert "SilentlyContinue" in t
    assert "Invoke-BobiverseDownload" in t
    assert "Expand-BobiverseZip" in t
    assert "Assert-BobiverseSha256" in t
    assert "--max-time" in t
    assert "method=curl" in t
    assert "ZipFile" in t or "System.IO.Compression.ZipFile" in t
    assert "Get-BobiverseTarPath" in t
    # Helper must not invoke Expand-Archive (progress-bar stall class); mention in NOTES is ok.
    assert "Expand-Archive -" not in t
    assert "Expand-Archive -LiteralPath" not in t


def test_fr3965_fetch_scripts_dot_source_helpers_and_silence_progress():
    for path, needles in (
        (
            ERGO,
            (
                "Bobiverse-FetchHelpers.ps1",
                "ProgressPreference",
                "SilentlyContinue",
                "Invoke-BobiverseDownload",
                "Expand-BobiverseZip",
                "Assert-BobiverseSha256",
                ERGO_SHA,
                "FR #3965",
            ),
        ),
        (
            WIX,
            (
                "Bobiverse-FetchHelpers.ps1",
                "ProgressPreference",
                "SilentlyContinue",
                "Invoke-BobiverseDownload",
                "Expand-BobiverseZip",
                "TimeoutSec",
                "FR #3965",
            ),
        ),
        (
            NSSM,
            (
                "Bobiverse-FetchHelpers.ps1",
                "ProgressPreference",
                "SilentlyContinue",
                "Invoke-BobiverseDownload",
                "Expand-BobiverseZip",
                "MirrorUrls",
                "BOBIVERSE_NSSM_MIRROR",
                NSSM_MIRROR,
                NSSM_SHA,
                "FR #3965",
            ),
        ),
    ):
        assert path.is_file(), path
        t = _read(path)
        for n in needles:
            assert n in t, f"{path.name} missing {n!r}"
        # Direct Expand-Archive / bare IWR download paths removed from fetch bodies.
        assert "Expand-Archive" not in t, path.name
        assert "Invoke-WebRequest" not in t, path.name


def test_fr3965_wix_has_timeout_param():
    t = _read(WIX)
    assert "[int]$TimeoutSec" in t or "$TimeoutSec =" in t
    assert "TimeoutSec" in t


@win
def test_fr3965_helpers_curl_max_time_fails_closed(tmp_path):
    curl = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
    assert curl.is_file()
    dest = tmp_path / "stall.bin"
    t0 = time.time()
    r = subprocess.run(
        [
            str(curl),
            "-sSL",
            "--fail",
            "--connect-timeout",
            "2",
            "--max-time",
            "5",
            "-o",
            str(dest),
            "http://192.0.2.1:9/stall",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    elapsed = time.time() - t0
    assert r.returncode != 0
    assert elapsed < 20
    assert "--max-time" in _read(HELPERS)


@win
def test_fr3965_invoke_download_prefers_curl_and_times_out(tmp_path):
    """Dot-source helpers and call Invoke-BobiverseDownload against TEST-NET-1."""
    dest = tmp_path / "out.bin"
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HELPERS.as_posix()}'
try {{
  Invoke-BobiverseDownload -Url 'http://192.0.2.1:9/stall' -OutFile '{dest.as_posix()}' -TimeoutSec 5 -Retries 0
  exit 2
}} catch {{
  Write-Output $_.Exception.Message
  if ($_.Exception.Message -match 'download-failed') {{ exit 0 }}
  exit 1
}}
"""
    t0 = time.time()
    p = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    elapsed = time.time() - t0
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert elapsed < 45
    assert "download-failed" in (p.stdout + p.stderr)


@win
def test_fr3965_expand_zip_via_helper(tmp_path):
    """Expand-BobiverseZip extracts without Expand-Archive."""
    import zipfile

    zpath = tmp_path / "t.zip"
    out = tmp_path / "out"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("nested/hello.txt", "fr3965")
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HELPERS.as_posix()}'
Expand-BobiverseZip -ZipPath '{zpath.as_posix()}' -Destination '{out.as_posix()}'
if (-not (Test-Path -LiteralPath '{(out / "nested" / "hello.txt").as_posix()}')) {{ exit 1 }}
Get-Content -LiteralPath '{(out / "nested" / "hello.txt").as_posix()}' -Raw
"""
    p = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "fr3965" in p.stdout


@win
def test_fr3965_nssm_uses_mirror_when_primary_url_is_bad(tmp_path):
    """Primary bogus URL fails; archive.org mirror + sha256 succeeds (live network)."""
    out = tmp_path / "nssm-out"
    cache = tmp_path / "nssm-cache"
    # Skip if offline / archive unreachable.
    curl = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
    probe = subprocess.run(
        [
            str(curl),
            "-sSL",
            "--fail",
            "--max-time",
            "45",
            "-o",
            str(tmp_path / "probe.zip"),
            NSSM_MIRROR,
        ],
        capture_output=True,
        timeout=60,
    )
    if probe.returncode != 0:
        pytest.skip("archive.org nssm mirror unreachable")

    script = f"""
$ErrorActionPreference = 'Stop'
& '{NSSM.as_posix()}' -OutDir '{out.as_posix()}' -CacheDir '{cache.as_posix()}' `
  -Url 'https://nssm.cc/release/nssm-2.24-DOES-NOT-EXIST.zip' `
  -TimeoutSec 90
if (-not (Test-Path -LiteralPath '{(out / "nssm.exe").as_posix()}')) {{ exit 1 }}
"""
    p = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert (out / "nssm.exe").is_file()
    assert "download-ok" in p.stdout or "sha256-verified" in p.stdout or "nssm ready" in p.stdout
