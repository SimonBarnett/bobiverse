"""FR #7326: restore xAI weekly channels; no fleet Cursor/Grok-chat/OpenCode-free meters."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import bobreport
import fleet_pool_fetch as fp

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"


def _ps(script: str) -> str:
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return (r.stdout or "").strip()


DIGEST_JSON = r"""
{
  "machines": {
    "marchhare": {
      "xai_weekly": { "remaining_pct": 81, "account": "mh-xai", "fresh": true, "fetched_at": "2026-11-14T17:50:00Z" },
      "workers": ["marchhare-111: idle"]
    },
    "flamingo": {
      "xai_weekly": { "remaining_pct": 55, "account": "fl-xai", "fresh": true, "fetched_at": "2026-11-14T17:50:00Z" },
      "workers": ["flamingo-222: FR 1"]
    },
    "redqueen": {
      "xai_weekly": { "remaining_pct": 40, "account": "rq-xai", "fresh": true, "fetched_at": "2026-11-14T17:50:00Z" },
      "workers": ["redqueen-333: idle"]
    }
  },
  "fleet_pools": {
    "cursor": { "remaining": 74, "fetched_at": "2026-11-14T17:50:00Z", "fresh": true },
    "copilot": { "remaining": 33, "state": "ok", "fetched_at": "2026-11-14T17:50:00Z" },
    "opencode-go": { "remaining": 55, "fetched_at": "2026-11-14T17:50:00Z" },
    "opencode-free": { "remaining": 100, "source": "fixed-free" }
  },
  "copilot": { "remaining": 33, "state": "ok" }
}
"""


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7326_catalog_no_cursor_grok_chat_or_free_meter():
    script = f"""
. '{HOVER}'
$d = ConvertFrom-Json @'
{DIGEST_JSON}
'@
$rows = @(Get-BobTrayDigestPoolCatalog -Digest $d)
$o = [ordered]@{{
  ids = @($rows | ForEach-Object {{ [string]$_.id }})
  headings = @($rows | ForEach-Object {{ [string]$_.heading }})
}}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    ids = [str(x).lower() for x in data["ids"]]
    assert "cursor" not in ids
    assert "grok-chat" not in ids
    assert "opencode-free" not in ids
    assert "opencode-go" in ids
    assert "copilot" in ids
    joined = "\n".join(data["headings"])
    assert "Cursor / Grok chat" not in joined
    assert "OpenCode free" not in joined
    assert "older than 2 min" not in joined


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7326_snapshot_xai_weekly_three_channels_and_workers():
    script = f"""
. '{HOVER}'
$d = ConvertFrom-Json @'
{DIGEST_JSON}
'@
Format-BobTrayPoolLayoutSnapshot -Digest $d
"""
    text = _ps(script)
    up = text.upper()
    assert "XAI WEEKLY" in up
    assert "MARCHHARE" in up
    assert "FLAMINGO" in up
    assert "REDQUEEN" in up
    assert "81%" in text
    assert "55%" in text
    assert "40%" in text
    assert "Grok / Cursor" not in text
    assert "marchhare-111" in text
    assert "flamingo-222" in text
    assert "redqueen-333" in text
    low = text.lower()
    assert "cursor / grok chat" not in low
    assert "opencode free" not in low
    assert "older than 2 min" not in low


def test_fr7326_watch_restores_xai_weekly_heading():
    w = WATCH.read_text(encoding="utf-8-sig")
    sec = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "$sharedTitle = 'xAI weekly'" in sec
    assert "FR #7326" in sec


def test_fr7326_digest_has_no_fleet_cursor(tmp_path: Path):
    home = tmp_path / "d"
    home.mkdir()
    doc = bobreport.empty_digest()
    doc["machines"] = {
        "flamingo": {
            "id": "flamingo",
            "xai_weekly": {"remaining_pct": 55, "account": "fl-xai", "fresh": True},
        }
    }
    doc["fleet_pools"] = {
        "cursor": {"remaining": 74, "id": "cursor", "fresh": True},
        "copilot": {"remaining": 1, "id": "copilot"},
        "opencode-go": {"remaining": 2, "id": "opencode-go"},
        "opencode-free": {"remaining": 100, "source": "fixed-free"},
    }
    bobreport.save_digest(home, doc)
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    pub = bobreport.build_digest_object(home, "jeeves")
    fleet = pub.get("fleet") or {}
    pools = pub.get("fleet_pools") or {}
    assert fleet.get("cursor") is None
    assert fleet.get("grok-chat") is None
    assert "cursor" not in pools
    assert fleet.get("opencode-free") is None
    assert "opencode-free" not in pools or pools.get("opencode-free") is None


def test_fr7326_tick_does_not_fetch_cursor_or_fixed_free(tmp_path: Path):
    home = tmp_path / "d"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    hits = {"cursor": 0, "oc": 0}

    def copilot(_h, now):
        iso = fp.iso_utc(now)
        return {
            "id": "copilot",
            "remaining": 9,
            "fetched_at": iso,
            "error": None,
            "source": "t",
            "fresh": True,
        }

    def opencode(_h, now):
        hits["oc"] += 1
        iso = fp.iso_utc(now)
        return {
            "opencode-free": {
                "id": "opencode-free",
                "remaining": 1,
                "fetched_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
            "opencode-go": {
                "id": "opencode-go",
                "remaining": 2,
                "fetched_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
        }

    def cursor(_h, now):
        hits["cursor"] += 1
        return {
            "id": "cursor",
            "remaining": 74,
            "fetched_at": fp.iso_utc(now),
            "error": None,
            "source": "credman:Bobiverse/CursorAccess",
            "fresh": True,
        }

    a = fp.tick_fleet_pools(
        home,
        now=1_700_000_000.0,
        force=True,
        fetch_copilot=copilot,
        fetch_opencode=opencode,
        fetch_cursor=cursor,
    )
    assert hits["cursor"] == 0
    assert "cursor" not in a
    assert "opencode-free" not in a
    assert a["opencode-go"]["remaining"] == 2
    assert a["copilot"]["remaining"] == 9
    assert "cursor" not in fp.public_fleet_section(a)
    assert "opencode-free" not in fp.public_fleet_section(a)
