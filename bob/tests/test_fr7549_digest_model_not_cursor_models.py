"""FR #7549: ear digest model must never be the literal fuel label 'Cursor Models'."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bobreport  # noqa: E402
import bobtalk  # noqa: E402

IRC = ROOT / "third_party" / "bob-tray" / "src" / "Private" / "Get-BobIrc.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")

POISON = "Cursor Models"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr7549_source_never_assigns_cursor_models_model():
    """Ear must not invent model from cursor_label or fuel pool id."""
    irc = _txt(IRC)
    # Hardcoded fallback from cursor_label must be gone.
    assert "$model = 'Cursor Models'" not in irc
    assert '$model = "Cursor Models"' not in irc
    # Get-BobIrcModelFromJob must not map fuel cursor-models to the poison label.
    fn = irc[irc.index("function Get-BobIrcModelFromJob") : irc.index("function Get-BobIrcKindFromJob")]
    assert "'cursor-models' { return 'Cursor Models' }" not in fn
    assert '"cursor-models" { return "Cursor Models" }' not in fn
    assert "FR #7549" in fn or "FR #7549" in irc


def test_fr7549_build_payload_rejects_cursor_models_and_clears():
    """Build-BobDigestWebhookMergePayload: poison model omitted/null; real model kept."""
    irc = _txt(IRC)
    build = irc[irc.index("function Build-BobDigestWebhookMergePayload") :]
    build = build[: build.index("function Send-BobDigestWebhookIfChanged")]
    assert "FR #7549" in build
    # Must always publish model (null clears sticky) and reject the poison label.
    assert "Cursor Models" in build
    assert "$payload.model" in build


def test_fr7549_bobtalk_infer_never_returns_cursor_models():
    """cursor_label is fuel display only; never invents digest model."""
    peer = {"cursor_label": "74%", "running": 0}
    assert bobtalk._infer_model(peer) is None
    peer2 = {"model": POISON, "cursor_label": "74%"}
    assert bobtalk._infer_model(peer2) is None
    peer3 = {"model": "EXAMPLE_GROK_MIN", "cursor_label": "74%"}
    assert bobtalk._infer_model(peer3) == "EXAMPLE_GROK_MIN"
    peer4 = {"model": "grok.exe", "running": 1}
    assert bobtalk._infer_model(peer4) == "grok.exe"


def test_fr7549_fuel_publish_strips_poison_model():
    """Peer fuel merge must not re-forward sticky model='Cursor Models'."""
    peer = {
        "ok": True,
        "id": "peer-a",
        "online": True,
        "status": "operational",
        "weekly": 40,
        "weekly_known": True,
        "model": POISON,
        "cursor_label": "40%",
        "pcent": {"grok-build": 40},
        "xai_weekly": {"remaining_pct": 40, "source": "cli"},
        "lastSeen": "2026-11-15T12:00:00Z",
    }
    body = bobreport.build_peer_fuel_merge_payload(peer, "peer-a")
    assert body is not None
    assert body.get("model") != POISON
    # Explicit clear so chair drops sticky poison.
    assert body.get("model") in (None, "")
    cleared = body.get("cleared") or []
    assert "model" in cleared


def test_fr7549_fuel_publish_keeps_live_seat_model():
    """Real seat/CLI model survives strip; poison only is rejected."""
    peer = {
        "ok": True,
        "id": "peer-b",
        "online": True,
        "status": "operational",
        "weekly": 55,
        "weekly_known": True,
        "model": "EXAMPLE_GROK_MIN",
        "pcent": {"grok-build": 55},
        "xai_weekly": {"remaining_pct": 55, "source": "cli"},
        "lastSeen": "2026-11-15T12:00:00Z",
    }
    body = bobreport.build_peer_fuel_merge_payload(peer, "peer-b")
    assert body is not None
    assert body.get("model") == "EXAMPLE_GROK_MIN"
    blob = json.dumps(body)
    assert POISON not in blob


def test_fr7549_merge_null_clears_sticky_cursor_models(tmp_path: Path):
    """Chair pops sticky model when ear publishes null (clearable)."""
    import registered_machines

    home = tmp_path / "home"
    home.mkdir()
    registered_machines.save_registered(home, {"peer-c"})
    mid = "peer-c"
    assert bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "model": "EXAMPLE_GROK_MIN",
        },
    ).ok
    assert bobreport.load_digest(home)["machines"][mid].get("model") == "EXAMPLE_GROK_MIN"
    assert bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "model": None,
            "cleared": ["model"],
        },
    ).ok
    ent2 = bobreport.load_digest(home)["machines"][mid]
    assert ent2.get("model") in (None, "")
    assert POISON not in json.dumps(ent2)


def test_fr7549_merge_rejects_poison_model_on_write(tmp_path: Path):
    """Incoming model='Cursor Models' is treated as clear, never stored."""
    import registered_machines

    home = tmp_path / "home"
    home.mkdir()
    registered_machines.save_registered(home, {"peer-d"})
    mid = "peer-d"
    assert bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "model": "EXAMPLE_GROK_MIN",
        },
    ).ok
    assert bobreport.load_digest(home)["machines"][mid].get("model") == "EXAMPLE_GROK_MIN"
    assert bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "model": POISON,
        },
    ).ok
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("model") in (None, "")
    assert POISON not in json.dumps(ent)


@needs_ps
def test_fr7549_get_bob_irc_model_from_job_no_poison():
    """Get-BobIrcModelFromJob: fuel cursor-models -> null; Job.model wins; grok fuel ok."""
    script = r"""
$ErrorActionPreference = 'Stop'
. '{irc}'
$j1 = [pscustomobject]@{{ fuel = 'cursor-models'; model = $null }}
$m1 = Get-BobIrcModelFromJob $j1
if ($m1 -eq 'Cursor Models') {{ throw 'poison from fuel cursor-models' }}
if ($null -ne $m1 -and [string]$m1 -ne '') {{ throw ("unexpected model={{0}}" -f $m1) }}
$j2 = [pscustomobject]@{{ fuel = 'cursor-models'; model = 'EXAMPLE_SEAT_MODEL' }}
$m2 = Get-BobIrcModelFromJob $j2
if ($m2 -ne 'EXAMPLE_SEAT_MODEL') {{ throw ("want EXAMPLE_SEAT_MODEL got={{0}}" -f $m2) }}
$j3 = [pscustomobject]@{{ fuel = 'grok-build' }}
$m3 = Get-BobIrcModelFromJob $j3
if ($m3 -ne 'grok.exe') {{ throw ("want grok.exe got={{0}}" -f $m3) }}
$j4 = [pscustomobject]@{{ fuel = 'cursor-models'; model = 'Cursor Models' }}
$m4 = Get-BobIrcModelFromJob $j4
if ($m4 -eq 'Cursor Models') {{ throw 'poison Job.model must be rejected' }}
Write-Output 'MODEL_OK'
""".format(
        irc=str(IRC).replace("'", "''")
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        timeout=60,
    )
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0, err or out
    assert "MODEL_OK" in out


@needs_ps
def test_fr7549_build_payload_omits_poison_model():
    """Digest webhook payload never carries literal Cursor Models."""
    script = r"""
$ErrorActionPreference = 'Stop'
. '{irc}'
$docPoison = [pscustomobject]@{{
  id = 'peer-e'
  lastSeen = '2026-11-15T12:00:00Z'
  weekly = 40
  weekly_known = $true
  cursor_known = $false
  model = 'Cursor Models'
  kind = $null
  repo = $null
  sha = $null
  started_at = $null
  running = 0
  queued = 0
}}
$p1 = Build-BobDigestWebhookMergePayload $docPoison
if ($null -eq $p1) {{ throw 'payload null' }}
if ($p1.model -eq 'Cursor Models') {{ throw 'poison still in payload' }}
# Unknown / poison -> explicit null so chair can clear sticky.
if ($null -ne $p1.model -and [string]$p1.model -ne '') {{
  throw ("want null model got={{0}}" -f $p1.model)
}}
$docLive = [pscustomobject]@{{
  id = 'peer-e'
  lastSeen = '2026-11-15T12:00:00Z'
  weekly = 40
  weekly_known = $true
  cursor_known = $false
  model = 'EXAMPLE_GROK_MIN'
  kind = 'worker'
  repo = $null
  sha = $null
  started_at = $null
  running = 1
  queued = 0
}}
$p2 = Build-BobDigestWebhookMergePayload $docLive
if ($p2.model -ne 'EXAMPLE_GROK_MIN') {{ throw ("want live model got={{0}}" -f $p2.model) }}
$blob = ($p1 | ConvertTo-Json -Compress -Depth 6) + ($p2 | ConvertTo-Json -Compress -Depth 6)
if ($blob -like '*Cursor Models*') {{ throw 'literal Cursor Models in JSON' }}
Write-Output 'PAYLOAD_OK'
""".format(
        irc=str(IRC).replace("'", "''")
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        timeout=60,
    )
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0, err or out
    assert "PAYLOAD_OK" in out
