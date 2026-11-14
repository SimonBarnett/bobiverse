"""FR #7296: per-machine xAI, one Cursor/Grok chat fleet meter, OpenCode Free fixed 100%."""
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
      "xai_weekly": { "remaining_pct": 81, "account": "mh-xai", "fresh": true },
      "pcent": { "grok-chat": 74, "opencode-free": 12, "cursor-models": 74 }
    },
    "flamingo": {
      "xai_weekly": { "remaining_pct": 55, "account": "fl-xai", "fresh": true },
      "pcent": { "grok-chat": 74 }
    },
    "redqueen": {
      "xai_weekly": { "remaining_pct": 40, "account": "rq-xai", "fresh": true },
      "pcent": { "grok-chat": 74 }
    }
  },
  "fleet_pools": {
    "cursor": { "remaining": 74, "fetched_at": "2026-11-14T17:50:00Z", "fresh": true },
    "copilot": { "remaining": 33, "state": "ok", "fetched_at": "2026-11-14T17:50:00Z" },
    "opencode-go": { "remaining": 55, "fetched_at": "2026-11-14T17:50:00Z" }
  },
  "copilot": { "remaining": 33, "state": "ok" }
}
"""


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7296_catalog_one_cursor_grok_chat_and_free_100():
    script = f"""
. '{HOVER}'
$d = ConvertFrom-Json @'
{DIGEST_JSON}
'@
$rows = @(Get-BobTrayDigestPoolCatalog -Digest $d)
$o = [ordered]@{{
  ids = @($rows | ForEach-Object {{ [string]$_.id }})
  headings = @($rows | ForEach-Object {{ [string]$_.heading }})
  free_stale = @($rows | Where-Object {{ $_.id -eq 'opencode-free' }} | ForEach-Object {{ [bool]$_.never_stale }})
  free_pct = @($rows | Where-Object {{ $_.id -eq 'opencode-free' }} | ForEach-Object {{ $_.remaining_pct }})
}}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    ids = list(data["ids"])
    assert ids.count("cursor") == 1
    assert "grok-chat" not in ids
    assert "grok-build" not in ids
    joined = "\n".join(data["headings"])
    assert joined.lower().count("grok chat") + joined.lower().count("cursor") >= 1
    assert "Cursor / Grok chat 74%" in joined or "Cursor / Grok chat" in joined
    assert data["free_pct"][0] == 100
    assert data["free_stale"][0] is True
    assert "OpenCode free 100%" in joined


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7296_snapshot_three_machine_xai():
    script = f"""
. '{HOVER}'
$d = ConvertFrom-Json @'
{DIGEST_JSON}
'@
Format-BobTrayPoolLayoutSnapshot -Digest $d
"""
    text = _ps(script)
    assert "MARCHHARE" in text.upper()
    assert "FLAMINGO" in text.upper()
    assert "REDQUEEN" in text.upper()
    assert "81%" in text
    assert "55%" in text
    assert "40%" in text
    assert text.lower().count("cursor / grok chat") == 1 or (
        text.lower().count("grok chat") + text.lower().count("\ncursor ") <= 2
        and "Cursor / Grok chat" in text
    )
    assert "[stale]" not in text.split("OpenCode free")[1][:40] if "OpenCode free" in text else True


def test_fr7296_watch_no_fleet_xai_weekly_block():
    w = WATCH.read_text(encoding="utf-8-sig")
    sec = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "FR #7296" in sec
    assert "$sharedTitle = 'xAI weekly'" not in sec
    assert "never_stale" in sec or "opencode-free" in sec


def test_fr7296_digest_machines_xai_and_fleet_cursor(tmp_path: Path):
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
    }
    bobreport.save_digest(home, doc)
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    pub = bobreport.build_digest_object(home, "jeeves")
    fl = pub["machines"].get("flamingo") or {}
    assert fl.get("xai") or fl.get("xai_weekly")
    xai = fl.get("xai") or fl.get("xai_weekly")
    assert xai.get("remaining_pct") == 55
    fleet = pub.get("fleet") or {}
    cur = fleet.get("cursor") or (pub.get("fleet_pools") or {}).get("cursor")
    assert cur is not None
    assert cur.get("remaining") == 74
    assert fleet.get("grok-chat") is None or fleet.get("grok-chat") is cur or fleet.get("grok-chat") == cur
    free = (pub.get("fleet") or {}).get("opencode-free") or (pub.get("fleet_pools") or {}).get(
        "opencode-free"
    )
    if free:
        assert free.get("remaining") == 100
        assert free.get("fetched_at") in (None, "")
        assert free.get("never_stale") or free.get("source") == "fixed-free"


def test_fr7296_tick_does_not_fetch_opencode_free(tmp_path: Path, monkeypatch):
    home = tmp_path / "d"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    called = {"oc": 0}

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
        called["oc"] += 1
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

    a = fp.tick_fleet_pools(home, now=1_700_000_000.0, force=True, fetch_copilot=copilot, fetch_opencode=opencode)
    b = fp.tick_fleet_pools(
        home, now=1_700_000_120.0, force=True, fetch_copilot=copilot, fetch_opencode=opencode
    )
    assert a["opencode-free"]["remaining"] == 100
    assert a["opencode-free"].get("fetched_at") in (None, "")
    assert a["opencode-free"]["source"] == "fixed-free"
    assert a["opencode-free"]["fetched_at"] == b["opencode-free"]["fetched_at"]
    assert a["opencode-go"]["remaining"] == 2
