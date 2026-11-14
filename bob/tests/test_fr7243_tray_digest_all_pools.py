"""FR #7243: tray shows every digest pool, not a fixed xAI / OpenCode-Go / Copilot trio."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"

CANON = (
    "opencode-go",
    "copilot",
)


def _ps(script: str) -> str:
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return (r.stdout or "").strip()


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7243_six_pool_digest_fixture_headings():
    """Acceptance: fleet catalog is OpenCode go + Copilot (FR #7326)."""
    script = f"""
. '{HOVER}'
$d = ConvertFrom-Json @'
{{
  "machines": {{
    "flamingo": {{
      "pcent": {{
        "grok-build": 80,
        "grok-chat": 74,
        "opencode-free": 91,
        "opencode-go": 55,
        "cursor-models": 42
      }},
      "xai_weekly": {{ "remaining_pct": 80 }}
    }}
  }},
  "copilot": {{ "remaining": 33, "state": "ok" }}
}}
'@
$rows = @(Get-BobTrayDigestPoolCatalog -Digest $d -MachineId flamingo)
$o = [ordered]@{{
  ids = @($rows | ForEach-Object {{ [string]$_.id }})
  headings = @($rows | ForEach-Object {{ [string]$_.heading }})
}}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    ids = list(data["ids"])
    for need in CANON:
        assert need in ids, (need, ids)
    joined = "\n".join(data["headings"])
    assert "Grok Build" not in joined
    assert "Cursor / Grok chat" not in joined
    assert "OpenCode free" not in joined
    assert "OpenCode go 55%" in joined
    assert "Copilot 33%" in joined
    assert "cursor" not in ids
    assert "opencode-free" not in ids


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7243_unknown_when_digest_empty():
    script = f"""
. '{HOVER}'
$rows = @(Get-BobTrayDigestPoolCatalog -Digest $null)
@($rows | ForEach-Object {{ [string]$_.heading }}) | ConvertTo-Json -Compress
"""
    headings = json.loads(_ps(script).splitlines()[-1])
    text = "\n".join(headings)
    assert "unknown" in text or "OpenCode go" in text
    assert "Cursor / Grok chat" not in text
    assert "OpenCode free" not in text


def test_fr7243_watch_paints_digest_extra_families():
    w = WATCH.read_text(encoding="utf-8-sig")
    sec = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "DigestPoolRows" in sec
    assert "FR #7243" in sec
    assert "Add-BobTrayFuelFamilyRow" in sec
    assert "foreach ($drow in @($DigestPoolRows))" in sec
    assert "Get-BobTrayCursorGroupHelpTooltip" not in sec
    assert "foreach ($pool in $pools)" not in sec


def test_fr7243_status_and_docs_name_digest_pools():
    cs = STATUS_CS.read_text(encoding="utf-8")
    assert "digest_pools" in cs
    assert "DigestPoolPaint" in cs
    assert 'foreach (DigestPoolPaint p in m.DigestPools)' in cs
    dlg = DIALOGS.read_text(encoding="utf-8-sig")
    assert "digest_pools" in dlg
    d = DOCS.read_text(encoding="utf-8")
    assert "FR #7243" in d
    hover = HOVER.read_text(encoding="utf-8-sig")
    assert "function Get-BobTrayDigestPoolCatalog" in hover
    assert "digest_pools" in hover
