"""v0.1.19: #79 alias machine rows folded out of the digest/roster; #80 fleet pool minimum ignores dead/alias machines."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import bobreport
import registered_machines as rm

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
SEEN = "2026-10-01T11:55:00Z"
OLD = "2026-09-29T11:55:00Z"
SAND = "2026-10-07T17:23:58Z"
XAI = "2026-10-04T00:36:16Z"
FUT = "2026-10-16T17:23:01Z"
REAL = "win-mpre8vi4u6u"


@pytest.fixture()
def home(tmp_path):
    # exactly the production shape: BOTH the legacy #ionos and the real channel are ChanServ-registered
    rm.save_registered(tmp_path, {"ionos", REAL, "marchhare", "flamingo"})
    return tmp_path


def put(home, mid, **ent):
    doc = bobreport.load_digest(home)
    doc.setdefault("machines", {})[mid] = {"id": mid, "online": True, "lastSeen": SEEN, **ent}
    (home / "digest.json").write_text(json.dumps(doc), encoding="utf-8")


def pools_of(home):
    return {p["id"]: p for p in bobreport.build_digest_object(home, "Jeeves", now=NOW)["cursor_pools"]}


# ------------------------------------------------------------------ #79
def test_roster_folds_alias_and_has_no_duplicate(home):
    ids = bobreport.roster_machine_ids(home)
    assert ids == ("flamingo", "marchhare", REAL) and "ionos" not in ids
    assert len(set(ids)) == len(ids)


def test_digest_machines_and_roster_never_carry_the_alias(home):
    put(home, "ionos", online=False, pcent={"grok-chat": 22})
    put(home, REAL, pcent={"grok-chat": 90})
    out = bobreport.build_digest_object(home, "Jeeves", now=NOW)
    assert "ionos" not in out["machines"] and "ionos" not in out["roster_machine_ids"]
    assert sorted(out["machines"]) == sorted(out["roster_machine_ids"]) == ["flamingo", "marchhare", REAL]
    assert out["machines"][REAL]["pcent"]["grok-chat"] == 90          # canonical entry wins over the alias


def test_alias_only_entry_is_promoted_to_the_canonical_machine(home):
    put(home, "ionos", pcent={"grok-chat": 33})
    doc = bobreport.load_digest(home)
    assert "ionos" not in doc["machines"] and doc["machines"][REAL]["pcent"]["grok-chat"] == 33
    assert doc["machines"][REAL]["id"] == REAL


def test_report_from_legacy_alias_lands_on_the_real_machine(home):
    out = bobreport.apply_callback(home, {"op": "merge", "machine": "ionos", "online": True, "weekly": 40}, "Jeeves")
    assert out.ok, out.err
    doc = bobreport.load_digest(home)
    assert "ionos" not in doc["machines"] and doc["machines"][REAL]["weekly"] == 40


def test_channels_still_include_legacy_shop_so_the_chair_stays_in_it(home):
    chans = bobreport.chair_channels(home)
    assert "#ionos" in chans and f"#{REAL}" in chans


def test_unrelated_ids_unchanged(home):
    assert bobreport.fold_machine_id("MarchHare") == "marchhare"
    assert bobreport.fold_machine_id("#ionos") == REAL
    assert bobreport.fold_machine_id("dev1") == "ce-priority-dev1"
    assert not bobreport.is_alias_machine_id(REAL) and bobreport.is_alias_machine_id("ionos")


# ------------------------------------------------------------------ #80
def test_stale_offline_alias_no_longer_poisons_the_fleet_min(home):
    put(home, "ionos", online=False, lastSeen=OLD, pcent={"grok-chat": 22}, sand_period_end=SAND)
    put(home, REAL, pcent={"grok-chat": 90}, sand_period_end=SAND, period_end=XAI)
    assert pools_of(home)["grok-weekly"]["remaining"] == 90


@pytest.mark.parametrize("kw", [{"online": False}, {"lastSeen": OLD}])
def test_offline_or_stale_machine_is_excluded(home, kw):
    put(home, "flamingo", pcent={"grok-chat": 5}, sand_period_end=SAND, **kw)
    put(home, REAL, pcent={"grok-chat": 70}, sand_period_end=SAND)
    assert pools_of(home)["grok-weekly"]["remaining"] == 70


def test_live_machines_still_use_the_lesser(home):
    put(home, "flamingo", pcent={"grok-chat": 5}, sand_period_end=SAND)
    put(home, REAL, pcent={"grok-chat": 70}, sand_period_end=SAND)
    assert pools_of(home)["grok-weekly"]["remaining"] == 5


def test_unknown_lastseen_does_not_exclude_an_online_machine(home):
    put(home, REAL, pcent={"grok-chat": 61}, lastSeen=None, sand_period_end=SAND)
    assert pools_of(home)["grok-weekly"]["remaining"] == 61


def test_only_dead_machines_report_gives_unknown_not_a_stale_number(home):
    put(home, "flamingo", online=False, pcent={"grok-chat": 5}, sand_period_end=SAND)
    p = pools_of(home).get("grok-weekly")
    assert p is None or p["remaining"] is None


def test_pool_reset_is_cursor_sand_period_end_not_xai_weekly(home):
    put(home, REAL, pcent={"grok-chat": 90}, sand_period_end=SAND, period_end=XAI)
    p = pools_of(home)["grok-weekly"]
    assert p["period_end"] == SAND and p["reset"] == SAND


def test_pool_reset_falls_back_to_period_end_without_sand(home):
    put(home, REAL, pcent={"grok-chat": 90}, period_end=XAI)
    assert pools_of(home)["grok-weekly"]["period_end"] == XAI


def test_label_renamed_and_xai_weekly_stays_out_of_pools(home):
    put(home, REAL, pcent={"grok-chat": 90}, sand_period_end=SAND, period_end=XAI, weekly=55)
    out = bobreport.build_digest_object(home, "Jeeves", now=NOW)
    labels = {p["id"]: p["label"] for p in out["cursor_pools"]}
    assert labels["grok-weekly"] == "Grok chat (Cursor)"
    assert "Grok Weekly" not in json.dumps(out)
    assert not any(p["id"] in ("weekly", "xai-weekly", "grok-build") for p in out["cursor_pools"])
    assert out["machines"][REAL]["weekly"] == 55                       # the xAI weekly is still per machine


def test_expired_sand_period_masks_the_pool_even_if_xai_weekly_is_still_open(home):
    put(home, REAL, pcent={"grok-chat": 90}, sand_period_end="2026-09-30T00:00:00Z", period_end=XAI)
    m = bobreport.build_digest_object(home, "Jeeves", now=NOW)["machines"][REAL]
    assert m["pcent"]["grok-chat"] is None


def test_workers_in_legacy_ionos_channel_count_for_the_real_machine(home):
    import chan_workers
    assert chan_workers.machine_for_channel(home, "#ionos") == REAL
    assert chan_workers.machine_for_channel(home, "#" + REAL) == REAL
    assert chan_workers.speaker_machine(home, "ionos-1234", "#ionos") == REAL
