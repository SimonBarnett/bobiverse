"""v0.1.18: chair-maintained worker list - schema, roster gate, no-secret, pruning, nick exclusions."""
from __future__ import annotations

import json

import pytest

import bobcallback
import bobreport
import intake
import registered_machines as rm

ALLOW = {"127.0.0.1"}


def post(home, obj, *, rate=None, headers=None):
    return bobcallback.handle_request(
        "POST", "/bob/v1/report", headers or {"Content-Type": "application/json"},
        json.dumps(obj).encode(), "127.0.0.1", home, ALLOW,
        filer=intake.FakeGitHubFiler(), report_rate=rate,
    )


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def workers(home, mid="marchhare"):
    return bobreport.build_digest_object(home, "Jeeves")["machines"][mid]["workers"]


def up(home, nick="marchhare-101", mid="marchhare"):
    return post(home, {"op": "worker-upsert", "machine": mid, "nick": nick})


@pytest.mark.parametrize("nick", ["marchhare_console", "MarchHare_Console", "bob-marchhare", "Bob-marchhare",
                                  "jeeves", "Jeeves", "ChanServ", "NickServ", "OperServ", "HostServ", "simon",
                                  "console-marchhare", "", "bad nick", "a" * 40, "#chan"])
def test_ear_monitor_service_nicks_are_not_workers(nick):
    assert not bobreport.is_worker_nick(nick)


@pytest.mark.parametrize("nick", ["marchhare-101", "win-mpre8vi4u6u-8412", "marchhare_5", "w-mh-41124"])
def test_seat_nicks_are_workers(nick):
    assert bobreport.is_worker_nick(nick)


def test_upsert_work_idle_cycle_and_digest_shape(home):
    assert up(home)[0] == 204
    w = workers(home)
    assert [(r["nick"], r["state"], r["work"]) for r in w] == [("marchhare-101", "idle", "")]
    assert set(w[0]) == {"nick", "state", "work", "updated"} and w[0]["updated"].endswith("Z")
    assert post(home, {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-101",
                       "state": "doing", "work": "FR o/r#5 fix the thing"})[0] == 204
    assert workers(home)[0]["state"] == "doing" and workers(home)[0]["work"] == "FR o/r#5 fix the thing"
    assert post(home, {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-101", "state": "idle"})[0] == 204
    assert workers(home)[0]["state"] == "idle" and workers(home)[0]["work"] == ""
    # upsert of an existing doing worker does not reset it
    post(home, {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-101", "state": "doing", "work": "x"})
    up(home)
    assert workers(home)[0]["state"] == "doing"


def test_repeat_is_unchanged_200_not_204(home):
    assert up(home)[0] == 204
    assert up(home)[0] == 200


def test_remove_and_unknown_remove(home):
    up(home)
    assert post(home, {"op": "worker-remove", "machine": "marchhare", "nick": "marchhare-101"})[0] == 204
    assert workers(home) == []
    assert post(home, {"op": "worker-remove", "machine": "marchhare", "nick": "marchhare-101"})[0] == 200


def test_roster_gate_rejects_unregistered_machine_and_bad_machine(home):
    assert post(home, {"op": "worker-upsert", "machine": "evil", "nick": "evil-1"})[0] == 403
    assert post(home, {"op": "worker-upsert", "machine": "", "nick": "x-1"})[0] == 400
    assert "evil" not in bobreport.load_digest(home).get("machines", {})


@pytest.mark.parametrize("payload", [
    {"op": "worker-upsert", "machine": "marchhare", "nick": "bob-marchhare"},
    {"op": "worker-upsert", "machine": "marchhare", "nick": "marchhare_console"},
    {"op": "worker-upsert", "machine": "marchhare", "nick": "jeeves"},
    {"op": "worker-upsert", "machine": "marchhare"},
    {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-1"},                       # state required
    {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-1", "state": "sleeping"},
    {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-1", "state": "doing", "work": 5},
    {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-1", "state": "doing", "work": "x" * 401},
])
def test_schema_rejections(home, payload):
    assert post(home, payload)[0] == 400
    assert workers(home) == []


def test_no_secret_in_work_or_keys(home):
    for p in ({"op": "worker-work", "machine": "marchhare", "nick": "marchhare-1", "state": "doing",
               "work": "use password=hunter2 now"},
              {"op": "worker-upsert", "machine": "marchhare", "nick": "marchhare-1", "secret": "x"},
              {"op": "worker-upsert", "machine": "marchhare", "nick": "marchhare-1", "password": "x"}):
        assert post(home, p)[0] == 400
    assert workers(home) == []


def test_work_is_clamped_and_cleaned(home):
    post(home, {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-1", "state": "doing",
                "work": "a\r\nb\tc " + "z" * 300})
    w = workers(home)[0]["work"]
    assert len(w) <= bobreport.WORKER_WORK_MAX and "\n" not in w and "\r" not in w and "\t" not in w


def test_rate_limit_applies_to_worker_ops(home):
    rl = intake.RateLimiter(2)
    codes = [post(home, {"op": "worker-upsert", "machine": "marchhare", "nick": f"marchhare-{i}"}, rate=rl)[0]
             for i in range(1, 5)]
    assert 429 in codes


def test_list_is_capped(home):
    for i in range(1, bobreport.WORKER_LIST_MAX + 6):
        post(home, {"op": "worker-upsert", "machine": "marchhare", "nick": f"marchhare-{i}"})
    assert len(workers(home)) == bobreport.WORKER_LIST_MAX


def test_machines_are_isolated(home):
    up(home, "marchhare-1")
    up(home, "win-mpre8vi4u6u-9", "win-mpre8vi4u6u")
    assert [r["nick"] for r in workers(home)] == ["marchhare-1"]
    assert [r["nick"] for r in workers(home, "win-mpre8vi4u6u")] == ["win-mpre8vi4u6u-9"]


def test_workers_pruned_when_machine_dropped_and_when_shop_down(home):
    up(home)
    rm.sync_from_chanserv(home, ["#bobiverse", "#win-mpre8vi4u6u"])           # marchhare no longer registered
    doc = bobreport.build_digest_object(home, "Jeeves")
    assert "marchhare" not in doc["machines"]
    up(home, "win-mpre8vi4u6u-9", "win-mpre8vi4u6u")                          # any digest write persists the prune
    assert "marchhare" not in bobreport.load_digest(home)["machines"]
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"])
    assert workers(home) == []                                                # re-registered: starts empty
    up(home)
    bobreport.shop_down(home, "marchhare")
    assert workers(home) == []


def test_legacy_pid_workers_dict_untouched_by_list(home):
    post(home, {"op": "merge", "machine": "marchhare", "pid": 7, "working_on": "legacy", "kind": "grok"})
    up(home)
    ent = bobreport.load_digest(home)["machines"]["marchhare"]
    assert "7" in ent["workers"] and ent["worker_list"][0]["nick"] == "marchhare-101"
    assert [r["nick"] for r in workers(home)] == ["marchhare-101"]


def test_roundtrip_through_json_is_utf8_safe(home):
    post(home, {"op": "worker-work", "machine": "marchhare", "nick": "marchhare-1", "state": "doing",
                "work": "FR o/r#1 caf\u00e9 \u00b7 fix"})
    raw = json.dumps(bobreport.build_digest_object(home, "J"), ensure_ascii=False).encode("utf-8")
    assert "caf\u00e9 \u00b7 fix" in json.loads(raw.decode("utf-8"))["machines"]["marchhare"]["workers"][0]["work"]
