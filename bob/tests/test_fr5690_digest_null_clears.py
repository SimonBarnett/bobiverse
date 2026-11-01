"""FR #5690: digest merge clears sticky null fields; same USD -> same GBP server-side."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import bobreport
import bobstat
import registered_machines


def _home(tmp_path: Path, mids=None) -> Path:
    registered_machines.save_registered(tmp_path, set(mids or {"marchhare", "flamingo"}))
    return tmp_path


def test_overage_then_null_clears_digest(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    assert bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "overage_usd": 200.11,
            "overage_gbp": 150.89,
            "on_demand_used_cents": 20011,
            "on_demand_limit_cents": 20000,
            "overspend_state": "at-limit",
            "usd_gbp_rate": 0.7540,
            "overage_fetched_at": "2026-10-01T10:00:00Z",
            "repo": "SimonBarnett/hrsmith",
            "sha": "abc1234",
            "started_at": "2026-10-01T09:00:00Z",
        },
    ).ok
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("overage_usd") == 200.11
    assert ent.get("repo") == "SimonBarnett/hrsmith"

    assert bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "overage_usd": None,
            "overage_gbp": None,
            "on_demand_used_cents": None,
            "on_demand_limit_cents": None,
            "on_demand_remaining_pct": None,
            "overspend_state": None,
            "usd_gbp_rate": None,
            "overage_fetched_at": None,
            "repo": None,
            "sha": None,
            "started_at": None,
        },
    ).ok
    ent2 = bobreport.load_digest(home)["machines"][mid]
    for k in (
        "overage_usd",
        "overage_gbp",
        "on_demand_used_cents",
        "on_demand_limit_cents",
        "on_demand_remaining_pct",
        "overspend_state",
        "usd_gbp_rate",
        "overage_fetched_at",
        "repo",
        "sha",
        "started_at",
    ):
        assert ent2.get(k) in (None, ""), k


def test_cleared_list_also_pops_sticky_fields(tmp_path: Path):
    home = _home(tmp_path)
    mid = "flamingo"
    assert bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "overage_gbp": 159.52,
            "overage_usd": 200.11,
            "repo": "SimonBarnett/oldjob",
        },
    ).ok
    assert bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "cleared": ["overage_gbp", "overage_usd", "repo"],
        },
    ).ok
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("overage_gbp") in (None, "")
    assert ent.get("overage_usd") in (None, "")
    assert ent.get("repo") in (None, "")


def test_same_overage_usd_same_gbp_server_side(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("BOB_CURSOR_USD_GBP_RATE", "0.7469")
    for mid in ("marchhare", "flamingo"):
        assert bobreport.apply_callback(
            home,
            {
                "op": "merge",
                "machine": mid,
                "overage_usd": 200.11,
                # Peers may disagree on GBP from stale FX; server must unify.
                "overage_gbp": 150.89 if mid == "marchhare" else 159.52,
            },
        ).ok
    d = bobreport.load_digest(home)["machines"]
    gbp_m = d["marchhare"]["overage_gbp"]
    gbp_f = d["flamingo"]["overage_gbp"]
    assert gbp_m == gbp_f
    assert gbp_m == round(200.11 * 0.7469, 2)
    assert d["marchhare"].get("usd_gbp_rate") == 0.7469
    assert d["flamingo"].get("usd_gbp_rate") == 0.7469
    assert d["marchhare"].get("overage_fetched_at")
    assert d["flamingo"].get("overage_fetched_at")


def test_peer_delta_sends_null_clear_when_chair_has_stale(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    # Chair still shows stale overage; local peer has cleared (nulls omitted / None).
    bobstat.write_peer(
        home,
        {
            "id": mid,
            "ok": True,
            "online": True,
            "weekly": 10,
            # overage_* intentionally absent (= null / unknown)
            "repo": "",
        },
    )
    chair = {
        "overage_usd": 200.11,
        "overage_gbp": 150.89,
        "on_demand_used_cents": 20011,
        "repo": "SimonBarnett/hrsmith",
        "weekly": 10,
    }
    payload = bobreport.merge_payload_local_peer_ahead_of_chair(home, mid, chair)
    assert payload is not None
    assert payload.get("op") == "merge"
    assert "overage_usd" in payload and payload["overage_usd"] is None
    assert "overage_gbp" in payload and payload["overage_gbp"] is None
    assert "repo" in payload and payload["repo"] in (None, "")
    # Unchanged weekly must not be re-sent as a clear
    assert "weekly" not in payload or payload.get("weekly") == 10


# --- PowerShell: merge payload always carries clearable nulls (FR #5690) ---
TRAY = Path(__file__).resolve().parents[1] / "tray"
PS = os.environ.get("BOB_POWERSHELL") or "powershell"
needs_ps = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell tray payload")


@needs_ps
def test_ps_merge_payload_emits_explicit_nulls_for_clears(tmp_path: Path):
    """Build-BobDigestWebhookMergePayload must include overage/repo keys as JSON null when empty."""
    mod = TRAY / "src" / "BobBridge.psd1"
    lines = [
        "$ErrorActionPreference='Stop'",
        "Import-Module '{0}' -Force -DisableNameChecking".format(mod),
        (
            "$doc = [pscustomobject]@{ id='flamingo'; online=$true; status='operational'; "
            "weekly=$null; weekly_known=$false; repo=$null; sha=$null; started_at=$null; "
            "working_on=$null; overage_gbp=$null; overage_usd=$null; overspend_state=$null; "
            "on_demand_used_cents=$null; on_demand_limit_cents=$null; on_demand_remaining_pct=$null; "
            "usd_gbp_rate=$null; overage_fetched_at=$null }"
        ),
        "$payload = & (Get-Module BobBridge) { param($d) Build-BobDigestWebhookMergePayload $d } $doc",
        "$payload | ConvertTo-Json -Depth 6 -Compress",
    ]
    script = tmp_path / "payload.ps1"
    script.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-File", str(script)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, (r.stderr or r.stdout)[-800:]
    out_line = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")][-1]
    data = json.loads(out_line)
    for k in (
        "overage_gbp",
        "overage_usd",
        "on_demand_used_cents",
        "repo",
        "sha",
        "started_at",
        "working_on",
        "usd_gbp_rate",
        "overage_fetched_at",
    ):
        assert k in data, k
        assert data[k] is None, k
