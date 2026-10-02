from datetime import datetime, timezone

import pytest

import bobreport
import registered_machines as rm
from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
FUT = "2026-10-16T17:23:01Z"
WK = "2026-10-04T00:36:16Z"
GONE = "2026-09-29T00:36:16Z"


def bob_rows(grok=12, grok_pe=WK, auto=70, hi=40):
    # exactly what ConvertTo-BobDigestCursorPoolRows posts
    return [
        {"group_id": "grok-chat", "group_label": "grok chat", "remaining_pct": grok, "period_end": grok_pe},
        {"group_id": "high-cost-models", "group_label": "high cost models", "remaining_pct": hi, "period_end": FUT},
        {"group_id": "auto", "group_label": "Low cost models", "remaining_pct": auto, "period_end": FUT},
    ]


@pytest.fixture()
def home(tmp_path):
    rm.save_registered(tmp_path, {"win-mpre8vi4u6u", "flamingo", "marchhare"})
    return tmp_path


def merge(home, mid, **kw):
    kw.setdefault("online", True)       # bob posts online=true with every report (#80: only live machines set the min)
    out = bobreport.apply_callback(home, {"op": "merge", "machine": mid, **kw}, "Jeeves")
    assert out.ok, out.err
    return out


def test_coerce_accepts_bob_row_shape():
    got = {r["id"]: r for r in bobreport._coerce_cursor_pools(bob_rows())}
    assert set(got) == {"grok-weekly", "other-models", "cursor-models"}
    g = got["grok-weekly"]
    assert g["remaining"] == 12 and g["period_end"] == WK
    assert got["cursor-models"]["remaining"] == 70 and got["other-models"]["remaining"] == 40


def test_coerce_still_accepts_server_shape_and_rejects_garbage():
    r = bobreport._coerce_cursor_pool({"id": "cursor-models", "remaining": 33, "period_end": FUT})
    assert r["remaining"] == 33
    assert bobreport._coerce_cursor_pool({"group_id": "grok-chat", "remaining_pct": 150})["remaining"] is None
    assert bobreport._coerce_cursor_pool({"group_id": "grok-chat", "remaining_pct": "x"})["remaining"] is None
    assert bobreport._coerce_cursor_pool({"group_id": "flamingo", "remaining_pct": 5}) is None   # a machine, not a pool
    assert bobreport._coerce_cursor_pool({"group_id": "grok-chat", "remaining_pct": 5, "x": "password=abc"}) is not None
    assert bobreport._coerce_cursor_pool("nope") is None


def test_merge_stores_per_machine_rows_and_keeps_other_machines(home):
    merge(home, "win-mpre8vi4u6u", cursor_pools=bob_rows(grok=12), weekly=12, period_end=WK)
    merge(home, "flamingo", cursor_pools=bob_rows(grok=55, auto=20), weekly=55, period_end=WK)
    doc = bobreport.load_digest(home)
    a = {r["id"]: r for r in doc["machines"]["win-mpre8vi4u6u"]["cursor_pools"]}
    b = {r["id"]: r for r in doc["machines"]["flamingo"]["cursor_pools"]}
    assert a["grok-weekly"]["remaining"] == 12 and b["grok-weekly"]["remaining"] == 55
    assert b["cursor-models"]["remaining"] == 20
    assert "cursor_pools" not in doc            # no fleet-wide replace-with-None


def test_rows_never_cleared_by_empty_or_unparseable_post(home):
    merge(home, "flamingo", cursor_pools=bob_rows())
    merge(home, "flamingo", cursor_pools=[], working_on="x", pid=1)
    merge(home, "flamingo", cursor_pools=[{"junk": 1}], working_on="y", pid=1)
    rows = bobreport.load_digest(home)["machines"]["flamingo"]["cursor_pools"]
    assert len(rows) == 3


def test_grok_weekly_period_end_and_pcent_stored_per_machine(home):
    merge(home, "win-mpre8vi4u6u", cursor_pools=bob_rows(grok=12))
    ent = bobreport.load_digest(home)["machines"]["win-mpre8vi4u6u"]
    assert ent["pcent"]["grok-chat"] == 12 and ent["period_end"] == WK
    assert ent["pcent"]["cursor-models"] == 70 and ent["cursor_period_end"] == FUT


def test_posted_pcent_weekly_period_end_roundtrip(home):
    merge(home, "win-mpre8vi4u6u", pcent={"grok-chat": 9, "cursor-models": 60}, weekly=9,
          period_end=WK, cursor_period_end=FUT, cursor_pools=bob_rows(grok=9, auto=60))
    out = bobreport.build_digest_object(home, "Jeeves", now=NOW)
    m = out["machines"]["win-mpre8vi4u6u"]
    assert m["pcent"]["grok-chat"] == 9 and m["weekly"] == 9 and m["period_end"] == WK
    pools = {p["id"]: p for p in out["cursor_pools"]}
    assert pools["grok-weekly"]["remaining"] == 9 and pools["grok-weekly"]["state"] == "current"
    assert pools["cursor-models"]["remaining"] == 60


def test_fleet_pool_is_lesser_across_machines(home):
    merge(home, "win-mpre8vi4u6u", cursor_pools=bob_rows(grok=12, auto=90))
    merge(home, "flamingo", cursor_pools=bob_rows(grok=55, auto=20))
    pools = {p["id"]: p for p in bobreport.build_digest_object(home, "Jeeves", now=NOW)["cursor_pools"]}
    assert pools["grok-weekly"]["remaining"] == 12 and pools["cursor-models"]["remaining"] == 20


def test_expired_period_is_unknown_not_zero(home):
    merge(home, "marchhare", cursor_pools=bob_rows(grok=8, grok_pe=GONE), weekly=8, period_end=GONE)
    out = bobreport.build_digest_object(home, "Jeeves", now=NOW)
    m = out["machines"]["marchhare"]
    gw = {r["id"]: r for r in m["cursor_pools"]}["grok-weekly"]
    assert gw["remaining"] is None                       # unknown, not 8 and not 0
    assert m["weekly"] is None and m["pcent"]["grok-chat"] is None
    pool = {p["id"]: p for p in out["cursor_pools"]}["grok-weekly"]
    assert pool["remaining"] is None and pool["state"] == "unknown" and pool["reason"] == "period-expired"


def test_repeat_merge_is_idempotent_no_change(home):
    merge(home, "flamingo", cursor_pools=bob_rows(), pcent={"grok-chat": 12}, weekly=12, period_end=WK)
    again = bobreport.apply_callback(home, {"op": "merge", "machine": "flamingo", "cursor_pools": bob_rows(),
                                            "pcent": {"grok-chat": 12}, "weekly": 12, "period_end": WK}, "Jeeves")
    assert again.ok and again.changed is False


def test_pool_change_alone_is_a_change(home):
    merge(home, "flamingo", cursor_pools=bob_rows(auto=70))
    out = bobreport.apply_callback(home, {"op": "merge", "machine": "flamingo",
                                          "cursor_pools": bob_rows(auto=65)}, "Jeeves")
    assert out.ok and out.changed


def test_bob_derives_pcent_from_own_pool_rows_when_groups_missing():
    """marchhare posted pcent {} because cursor_spending_groups was absent; rows still carried data."""
    from pathlib import Path
    t = (ROOT / "third_party" / "bob-tray" / "src" / "Private" / "Get-BobIrc.ps1").read_text(encoding="utf-8-sig")
    assert "derive" in t and "$fromRows" in t and "'auto'" in t
    assert "$doc.pcent = [pscustomobject]$fromRows" in t


def test_marchhare_real_row_shape_end_to_end(home):
    # captured shape from marchhare's bob-peers (values only): grok-chat 94 but its window ended 2026-09-30
    rows = [{"group_id": "grok-chat", "group_label": "grok chat", "remaining_pct": 94, "period_end": "2026-09-30T17:23:58.025Z"},
            {"group_id": "high-cost-models", "group_label": "high cost models", "remaining_pct": None, "period_end": FUT},
            {"group_id": "auto", "group_label": "Low cost models", "remaining_pct": None, "period_end": FUT}]
    merge(home, "marchhare", cursor_pools=rows, weekly=8, period_end="2026-09-29T23:41:45.639212+00:00", pcent={})
    out = bobreport.build_digest_object(home, "Jeeves", now=NOW)
    m = out["machines"]["marchhare"]
    assert m["weekly"] is None                                  # expired => unknown, not 8
    by = {r["id"]: r for r in m["cursor_pools"]}
    assert by["grok-weekly"]["remaining"] is None and by["grok-weekly"]["period_end"].startswith("2026-09-30")
    assert by["other-models"]["remaining"] is None              # null stays unknown, never 0
