"""FR #9270 / BOB-TRAY-UI-09: Jeeves butler from bob.ntsa.uk cache or fallback."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

ICO = REPO / "jeeves" / "assets" / "jeeves-butler.ico"
CS = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
HELPER = REPO / "bob" / "tray" / "tools" / "BobTrayJeevesButler.ps1"
EVIDENCE = REPO / "bob" / "docs" / "bob-tray-ui-09-jeeves-butler-evidence.md"
URL = "https://bob.ntsa.uk/jeeves/assets/jeeves-butler.ico"


def test_fallback_ico_present():
    raw = ICO.read_bytes()
    assert raw[:4] == b"\x00\x00\x01\x00"


def test_tipform_pins_url_cache_and_fallback():
    text = CS.read_text(encoding="utf-8-sig")
    assert URL in text
    assert "assets" in text and "jeeves-butler.ico" in text
    # FR #9587: fallback uses rootPath + bob/tray/assets then jeeves/assets.
    assert (
        'Path.Combine(installRoot ?? "", "jeeves", "assets", "jeeves-butler.ico")' in text
        or 'Path.Combine(rootPath, "jeeves", "assets", "jeeves-butler.ico")' in text
    )
    assert (
        'Path.Combine(installRoot ?? "", "assets", "jeeves-butler.ico")' in text
        or 'Path.Combine(rootPath, "assets", "jeeves-butler.ico")' in text
        or 'JeevesButlerCachePath' in text
    )
    assert 'Path.Combine(rootPath, "bob", "tray", "assets", "jeeves-butler.ico")' in text
    assert "ResolveJeevesButlerIcon" in text
    assert "miJeeves.Image" in text
    assert "menu-icon MISSING" in text


def test_watch_pins_url_cache_and_fallback():
    helper = HELPER.read_text(encoding="utf-8-sig")
    watch = WATCH.read_text(encoding="utf-8-sig")
    assert URL in helper
    assert "function Resolve-BobTrayJeevesButlerIcon" in helper
    assert "assets\\jeeves-butler.ico" in helper
    assert "jeeves\\assets\\jeeves-butler.ico" in helper
    assert "BobTrayJeevesButler.ps1" in watch
    assert "Resolve-BobTrayJeevesButlerIcon" in watch
    assert "$miJeeves.Image" in watch


def test_evidence_documents_s1():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-TRAY-UI-09" in text or "9270" in text
    assert URL in text
    assert "jeeves/assets/jeeves-butler.ico" in text
    assert "assets/jeeves-butler.ico" in text or "install assets" in text.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell resolve harness")
def test_resolve_prefers_cache_then_fallback(tmp_path: Path):
    """SkipFetch: cache wins; else repo fallback under install-shaped root."""
    root = tmp_path / "install"
    assets = root / "assets"
    assets.mkdir(parents=True)
    jeeves = root / "jeeves" / "assets"
    jeeves.mkdir(parents=True)
    fallback = jeeves / "jeeves-butler.ico"
    fallback.write_bytes(ICO.read_bytes())

    ps = r"""
param($Root, $Mode)
$ErrorActionPreference = 'Stop'
. '{helper}'
if ($Mode -eq 'fallback') {{
  $p = Resolve-BobTrayJeevesButlerIcon -RepoRoot $Root -SkipFetch
  if (-not $p) {{ throw 'expected fallback' }}
  if ($p -notmatch 'jeeves[/\\]assets[/\\]jeeves-butler\.ico$') {{ throw "unexpected $p" }}
  Write-Output $p
  exit 0
}}
$cache = Join-Path $Root 'assets\jeeves-butler.ico'
Copy-Item -LiteralPath (Join-Path $Root 'jeeves\assets\jeeves-butler.ico') -Destination $cache -Force
$p = Resolve-BobTrayJeevesButlerIcon -RepoRoot $Root -SkipFetch
if ($p -ne $cache) {{ throw "cache miss: $p" }}
Write-Output $p
exit 0
""".replace("{helper}", str(HELPER).replace("'", "''"))

    script = tmp_path / "resolve.ps1"
    script.write_text(ps, encoding="utf-8")

    def run(mode: str) -> str:
        r = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                str(root),
                mode,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "BOB_JEEVES_BUTLER_SKIP_FETCH": "1"},
        )
        assert r.returncode == 0, r.stdout + "\n" + r.stderr
        return r.stdout.strip()

    fb = run("fallback")
    assert "jeeves" in fb.lower() and "jeeves-butler.ico" in fb.lower()
    cached = run("cache")
    assert cached.lower().endswith(os.path.join("assets", "jeeves-butler.ico").lower()) or cached.replace(
        "\\", "/"
    ).endswith("assets/jeeves-butler.ico")
