"""#40 / #41 / #42: pool rollover, unknown-vs-zero, stale overspend, roster-driven rows."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bobreport
import registered_machines
from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service

T = ROOT / "third_party" / "bob-tray"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
ROSTER = {"ce-priority-dev1", "flamingo", "marchhare", "win-mpre8vi4u6u"}


def _digest(tmp_path: Path, machines: dict[str, dict]):
    registered_machines.save_registered(tmp_path, set(machines) | ROSTER)
    doc = bobreport._ensure_seats(bobreport.empty_digest(), tmp_path)
    for mid, fields in machines.items():
        doc["machines"].setdefault(mid, bobreport._empty_machine(mid)).update({"online": True, **fields})   # #80: only live machines set pools
    bobreport.save_digest(tmp_path, doc)
    return bobreport.build_digest_object(tmp_path, "Jeeves", now=NOW)


def _pool(out, pid):
    return {p["id"]: p for p in out["cursor_pools"]}.get(pid)


def test_period_expired_helper():
    assert bobreport._period_expired("2026-10-01T00:00:00Z", NOW) is True
    assert bobreport._period_expired("2026-10-04T00:36:16Z", NOW) is False
    assert bobreport._period_expired(None, NOW) is False
    assert bobreport._period_expired("garbage", NOW) is False


def test_current_period_values_are_kept(tmp_path):
    out = _digest(tmp_path, {"flamingo": {
        "pcent": {"cursor-models": 40, "grok-chat": 5},
        "cursor_period_end": "2026-10-16T17:23:01Z", "period_end": "2026-10-04T00:36:16Z",
        "weekly": 5}})
    assert out["machines"]["flamingo"]["pcent"]["grok-chat"] == 5
    assert out["machines"]["flamingo"]["weekly"] == 5
    assert _pool(out, "cursor-models")["remaining"] == 40
    assert _pool(out, "cursor-models")["state"] == "current"
    assert _pool(out, "grok-weekly")["remaining"] == 5


def test_expired_grok_weekly_is_unknown_not_zero_or_stale(tmp_path):
    # agentic_build#356 / bobiverse#40: old "95% used" (=5 remaining) after the weekly reset.
    out = _digest(tmp_path, {"flamingo": {
        "pcent": {"grok-chat": 5}, "weekly": 0,
        "period_end": "2026-09-30T00:36:16Z",
        "cursor_period_end": "2026-10-16T17:23:01Z"}})
    ex = out["machines"]["flamingo"]
    assert ex["pcent"]["grok-chat"] is None
    assert ex["weekly"] is None
    p = _pool(out, "grok-weekly")
    assert p["remaining"] is None and p["state"] == "unknown" and p["reason"] == "period-expired"


def test_expired_cursor_period_clears_stale_overspend_and_value(tmp_path):
    out = _digest(tmp_path, {"marchhare": {
        "pcent": {"cursor-models": 0, "on-demand": 0}, "overage_gbp": 150.84,
        "cursor_period_end": "2026-09-30T17:23:01Z"}})
    assert out["machines"]["marchhare"]["overage_gbp"] is None
    assert out["machines"]["marchhare"]["pcent"]["cursor-models"] is None
    for pid in ("cursor-models", "on-demand"):
        p = _pool(out, pid)
        assert p["remaining"] is None and p["state"] == "unknown"
        assert p["overage"] is None


def test_overspend_kept_inside_current_billing_period(tmp_path):
    out = _digest(tmp_path, {"marchhare": {
        "pcent": {"on-demand": 0}, "overage_gbp": 150.84,
        "cursor_period_end": "2026-10-16T17:23:01Z"}})
    assert out["machines"]["marchhare"]["overage_gbp"] == 150.84
    p = _pool(out, "on-demand")
    assert p["remaining"] == 0 and p["state"] == "current"   # real zero stays zero
    assert p["overage"] == "\u00a3150.84"


def test_unknown_is_distinct_from_zero(tmp_path):
    out = _digest(tmp_path, {"flamingo": {"pcent": {"cursor-models": 0}, "cursor_period_end": "2026-10-16T00:00:00Z"}})
    zero = _pool(out, "cursor-models")
    assert zero["remaining"] == 0 and zero["state"] == "current"
    out2 = _digest(tmp_path, {"flamingo": {"pcent": {"cursor-models": None}, "cursor_period_end": "2026-10-16T00:00:00Z"}})
    unk = _pool(out2, "cursor-models")
    assert unk["remaining"] is None and unk["state"] == "unknown"


def test_missing_period_end_does_not_mask_values(tmp_path):
    out = _digest(tmp_path, {"flamingo": {"pcent": {"cursor-models": 33}}})
    assert out["machines"]["flamingo"]["pcent"]["cursor-models"] == 33


def test_rollover_to_new_period_replaces_value(tmp_path):
    registered_machines.save_registered(tmp_path, ROSTER)
    doc = bobreport._ensure_seats(bobreport.empty_digest(), tmp_path)
    doc["machines"]["flamingo"]["pcent"] = {"cursor-models": 3}
    doc["machines"]["flamingo"]["cursor_period_end"] = "2026-09-16T00:00:00Z"
    bobreport.save_digest(tmp_path, doc)
    assert bobreport.apply_callback(tmp_path, {"op": "merge", "id": "flamingo", "online": True,
        "pcent": {"cursor-models": 100}, "cursor_period_end": "2026-10-16T00:00:00Z"}).ok
    out = bobreport.build_digest_object(tmp_path, "Jeeves", now=NOW)
    assert out["machines"]["flamingo"]["pcent"]["cursor-models"] == 100
    assert _pool(out, "cursor-models")["remaining"] == 100


def test_overage_gbp_roundtrips_through_merge(tmp_path):
    registered_machines.save_registered(tmp_path, ROSTER)
    assert bobreport.apply_callback(tmp_path, {"op": "merge", "id": "marchhare",
        "overage_gbp": 12.5, "pcent": {"on-demand": 0},
        "cursor_period_end": "2026-10-16T00:00:00Z"}).ok
    out = bobreport.build_digest_object(tmp_path, "Jeeves", now=NOW)
    assert out["machines"]["marchhare"]["overage_gbp"] == 12.5


def test_all_current_fleet_machines_exported_with_pool_payloads(tmp_path):
    fields = {m: {"pcent": {"cursor-models": 50, "grok-chat": 60},
                  "cursor_period_end": "2026-10-16T00:00:00Z", "period_end": "2026-10-04T00:00:00Z"}
              for m in sorted(ROSTER)}
    out = _digest(tmp_path, fields)
    assert out["roster_machine_ids"] == sorted(ROSTER)
    assert set(out["machines"]) == ROSTER
    for m in ROSTER:
        assert out["machines"][m]["pcent"] == {"cursor-models": 50, "grok-chat": 60}
    assert "ionos" not in out["machines"]   # legacy alias is not a roster machine id


def test_idempotent_merge_is_noop(tmp_path):
    registered_machines.save_registered(tmp_path, ROSTER)
    payload = {"op": "merge", "id": "flamingo", "online": True, "pcent": {"cursor-models": 50},
               "cursor_period_end": "2026-10-16T00:00:00Z"}
    first = bobreport.apply_callback(tmp_path, payload)
    again = bobreport.apply_callback(tmp_path, payload)
    assert first.ok and again.ok and again.changed is False


# ---- tray (static; PowerShell is not executed) ----
def _t(rel):
    return (T / rel).read_text(encoding="utf-8-sig")


def test_tray_has_no_separate_chanserv_section():
    t = _t("tools/Watch-BobTray.ps1")
    assert "-Title 'ChanServ'" not in t
    assert "-Title 'Grok accounts'" in t


def test_tray_grok_rows_come_from_digest_roster_not_hardcoded():
    h = _t("src/Public/Get-BobTrayHover.ps1")
    assert "roster_machine_ids" in h
    assert "$seatIds = @(Select-BobUniqueCanonicalIds @($script:BobRosterIds))" in h      # v0.1.19: canonical + de-duped
    c = _t("src/Private/Get-BobIrc.ps1")
    assert "BobRosterIds" in c   # Resolve-BobiverseMachineId accepts roster ids (e.g. win-mpre8vi4u6u)


def test_bob_reports_pools_every_30s_by_default():
    c = _t("src/Private/Get-BobIrc.ps1")
    i = c.index("function Get-BobDigestWebhookHeartbeatSec")
    body = c[i:i + 700]
    assert "return 30" in body and "return 300" not in body
    w = _t("tools/Watch-BobTray.ps1")
    assert "[int]$PollSec = 30" in w
