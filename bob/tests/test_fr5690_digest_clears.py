"""FR #5690: explicit null is a clear, not an omitted partial update."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import bobreport
import bobstat
import registered_machines


FIELDS = {
    "repo": "SimonBarnett/hrsmith",
    "sha": "abc123",
    "started_at": "2026-10-01T12:00:00Z",
    "overage_usd": 200.11,
    "overage_gbp": 150.89,
    "on_demand_used_cents": 20011,
    "on_demand_limit_cents": 20000,
    "on_demand_remaining_pct": 0,
    "overage_fetched_at": "2026-11-01T11:42:30Z",
    "usd_gbp_rate": 0.754,
    "usd_gbp_rate_fetched_at": "2026-11-01T11:42:30Z",
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    return tmp_path


def merge(home, **fields):
    result = bobreport.apply_callback(
        home, {"op": "merge", "machine": "marchhare", **fields}
    )
    assert result.ok


def test_values_then_null_survive_save_reload_and_stale_peer(home):
    merge(home, **FIELDS, cursor_period_end="2099-12-01T00:00:00Z")
    bobstat.write_peer(home, {"id": "marchhare", "ok": True, **FIELDS})
    merge(home, **dict.fromkeys(FIELDS), overspend_state="unknown")
    stored = bobreport.load_digest(home)["machines"]["marchhare"]
    exported = bobreport.build_digest_object(home, "Jeeves")["machines"]["marchhare"]
    for key in FIELDS:
        assert key in stored and stored[key] is None
        assert key in exported and exported[key] is None
    assert exported["overspend_state"] == "unknown"


def test_omission_preserves_values_and_zero_is_known(home):
    merge(home, **FIELDS)
    merge(home, online=True)
    stored = bobreport.load_digest(home)["machines"]["marchhare"]
    for key, value in FIELDS.items():
        assert stored[key] == value
    merge(home, overage_gbp=0, overage_usd=0, on_demand_used_cents=0)
    stored = bobreport.load_digest(home)["machines"]["marchhare"]
    assert stored["overage_gbp"] == stored["overage_usd"] == stored["on_demand_used_cents"] == 0


def test_peer_delta_distinguishes_null_from_absent_and_roundtrips_pull(home):
    chair = {**FIELDS, "working_on": "old job", "jobs": [{"repo": "old"}]}
    peer = {"id": "marchhare", "ok": True, **dict.fromkeys(FIELDS), "working_on": "", "jobs": []}
    bobstat.write_peer(home, peer)
    payload = bobreport.merge_payload_local_peer_ahead_of_chair(home, "marchhare", chair)
    assert payload is not None
    for key in FIELDS:
        assert key in payload and payload[key] is None
    assert payload["working_on"] is None
    assert payload["jobs"] == []
    bobreport.ingest_fleet_digest_pull(home, {"machines": {"marchhare": peer}})
    assert bobstat.read_peer(home, "marchhare")["overage_usd"] is None
    bobstat.write_peer(home, {"id": "marchhare", "ok": True, "online": True})
    assert bobreport.merge_payload_local_peer_ahead_of_chair(home, "marchhare", {**chair, "online": True}) is None


def test_empty_machine_activity_does_not_wipe_doing_worker(home):
    doc = {"machines": {"marchhare": {
        "working_on": "stale",
        "worker_list": [{"nick": "marchhare-123", "state": "doing",
                         "work": "bobiverse FR #5690", "updated": "2099-01-01T00:00:00Z"}],
    }}}
    bobreport._apply_merge_payload(doc, "marchhare", {"working_on": None})
    assert doc["machines"]["marchhare"]["working_on"] == "bobiverse FR #5690"
    doc["machines"]["marchhare"]["worker_list"] = []
    bobreport._apply_merge_payload(doc, "marchhare", {"working_on": None, "jobs": []})
    assert doc["machines"]["marchhare"]["working_on"] == ""
    assert doc["machines"]["marchhare"]["jobs"] == []


def test_same_usd_uses_newest_shared_fx_without_changing_amount_fetch_time(home):
    merge(home, **FIELDS)
    result = bobreport.apply_callback(home, {
        "op": "merge", "machine": "flamingo", "overage_usd": 200.11,
        "overage_gbp": 159.52, "usd_gbp_rate": 0.746948,
        "overage_fetched_at": "2026-11-01T11:43:30Z",
    })
    assert result.ok
    rows = bobreport.build_digest_object(home, "Jeeves")["machines"]
    assert rows["marchhare"]["overage_gbp"] == rows["flamingo"]["overage_gbp"] == 149.47
    assert rows["marchhare"]["usd_gbp_rate"] == rows["flamingo"]["usd_gbp_rate"] == 0.746948
    assert rows["marchhare"]["overage_fetched_at"] == FIELDS["overage_fetched_at"]
    merge(home, overage_gbp=None)
    assert bobreport.build_digest_object(home, "Jeeves")["machines"]["marchhare"]["overage_gbp"] is None


@pytest.mark.parametrize("rate", [None, 0, -1, "NaN", "Infinity", "invalid"])
def test_invalid_fx_cannot_replace_known_conversion(rate):
    rows = {
        "marchhare": dict(FIELDS),
        "flamingo": {**FIELDS, "usd_gbp_rate": rate, "usd_gbp_rate_fetched_at": "2026-11-01T11:43:30Z"},
    }
    bobreport._normalize_shared_overage_gbp(rows)
    assert rows["flamingo"]["usd_gbp_rate"] == FIELDS["usd_gbp_rate"]
    assert rows["marchhare"]["overage_gbp"] == rows["flamingo"]["overage_gbp"]


def test_expired_billing_masks_all_on_demand_figures():
    row = {**FIELDS, "cursor_period_end": "2020-01-01T00:00:00Z"}
    bobreport._mask_expired_pools(row)
    for key in ("overage_usd", "overage_gbp", "usd_gbp_rate", "on_demand_used_cents",
                "on_demand_limit_cents", "on_demand_remaining_pct"):
        assert row[key] is None
    assert row["overage_fetched_at"] == FIELDS["overage_fetched_at"]


def test_peer_pull_does_not_promote_shared_rate_to_newer_amount_timestamp(home):
    merge(home, **{**FIELDS, "overage_fetched_at": "2026-11-01T12:00:00Z",
                   "usd_gbp_rate_fetched_at": "2026-11-01T12:00:00Z"})
    assert bobreport.apply_callback(home, {
        "op": "merge", "machine": "flamingo", "overage_usd": 200.11,
        "overage_gbp": 159.52, "usd_gbp_rate": None,
        "overage_fetched_at": "2026-11-01T13:00:00Z",
    }).ok
    pulled = bobreport.build_digest_object(home, "Jeeves")
    assert pulled["machines"]["flamingo"]["usd_gbp_rate_fetched_at"].startswith("2026-11-01T12:00:00")
    bobreport.ingest_fleet_digest_pull(home, pulled)
    peer = bobstat.read_peer(home, "flamingo")
    assert peer["overage_fetched_at"] == "2026-11-01T13:00:00Z"
    # A delayed actual FX measurement must beat the inherited noon conversion.
    merge(home, usd_gbp_rate=0.746948, overage_fetched_at="2026-11-01T12:30:00Z")
    rows = bobreport.build_digest_object(home, "Jeeves")["machines"]
    assert rows["marchhare"]["usd_gbp_rate"] == rows["flamingo"]["usd_gbp_rate"] == 0.746948
    assert rows["marchhare"]["overage_gbp"] == rows["flamingo"]["overage_gbp"] == 149.47


def test_usage_metadata_is_wired_into_peer_and_webhook_fingerprint():
    tray = Path(__file__).resolve().parents[1] / "tray"
    hover = (tray / "src/Public/Get-BobTrayHover.ps1").read_text(encoding="utf-8-sig")
    irc = (tray / "src/Private/Get-BobIrc.ps1").read_text(encoding="utf-8-sig")
    assert "usd_gbp_rate  = $(if ($null -ne $j.usd_gbp_rate" in hover
    assert "if (-not $j.ok -and $null -eq $remain" in hover
    assert "overage_fetched_at     = $(if ($cw) { $cw.fetched_at }" in irc
    assert "usd_gbp_rate           = $(if ($cw) { $cw.usd_gbp_rate }" in irc
    fingerprint = irc[irc.index("function Get-BobDigestWebhookFingerprint"):irc.index("function Build-BobDigestWebhookMergePayload")]
    for key in ("overage_fetched_at", "usd_gbp_rate", "on_demand_used_cents",
                "on_demand_remaining_pct", "started_at"):
        assert f"[string]$Doc.{key}" in fingerprint


@pytest.mark.skipif(os.name != "nt" or not (shutil.which("pwsh") or shutil.which("powershell")),
                    reason="needs Windows PowerShell")
def test_powershell_merge_sends_present_clears_and_empty_jobs(tmp_path):
    source = Path(__file__).resolve().parents[1] / "tray/src/Private/Get-BobIrc.ps1"
    script = tmp_path / "merge.ps1"
    script.write_text(
        f". '{source}'\n"
        "$doc = [pscustomobject]@{id='marchhare'; repo=$null; sha=''; started_at=$null; "
        "working_on=$null; jobs=@(); overage_gbp=$null; overage_usd=$null; "
        "overage_fetched_at=$null; usd_gbp_rate=$null; on_demand_used_cents=$null; "
        "on_demand_limit_cents=0; on_demand_remaining_pct=$null}\n"
        "Build-BobDigestWebhookMergePayload $doc | ConvertTo-Json -Compress\n",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [shutil.which("pwsh") or shutil.which("powershell"), "-NoProfile", "-File", str(script)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    payload = json.loads(result.stdout)
    for key in ("repo", "sha", "started_at", "working_on", "overage_gbp", "overage_usd",
                "overage_fetched_at", "usd_gbp_rate", "on_demand_used_cents", "on_demand_remaining_pct"):
        assert key in payload and payload[key] is None
    assert payload["jobs"] == []
    assert payload["on_demand_limit_cents"] == 0
    assert "model" not in payload


@pytest.mark.skipif(os.name != "nt" or not (shutil.which("pwsh") or shutil.which("powershell")),
                    reason="needs Windows PowerShell")
def test_powershell_unknown_usage_keeps_fetch_provenance(tmp_path):
    source = Path(__file__).resolve().parents[1] / "tray/src/Public/Get-BobTrayHover.ps1"
    script = tmp_path / "usage.ps1"
    script.write_text(
        f". '{source}'\n"
        "$known = ConvertTo-BobCursorUsageDoc ([pscustomobject]@{ok=$true; "
        "overage_gbp=149.47; overage_usd=200.11; usd_gbp_rate=0.746948; "
        "ts='2026-11-01T11:42:30Z'})\n"
        "$unknown = ConvertTo-BobCursorUsageDoc ([pscustomobject]@{ok=$true; "
        "overspend_state='unknown'; ts='2026-11-01T11:43:30Z'})\n"
        "@{known=$known; unknown=$unknown} | ConvertTo-Json -Compress -Depth 5\n",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [shutil.which("pwsh") or shutil.which("powershell"), "-NoProfile", "-File", str(script)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    docs = json.loads(result.stdout)
    assert docs["known"]["usd_gbp_rate"] == 0.746948
    assert docs["unknown"]["overage_usd"] is None
    assert docs["unknown"]["usd_gbp_rate"] is None
    assert docs["unknown"]["fetched_at"] == "2026-11-01T11:43:30Z"
