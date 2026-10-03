"""FR #663: offer sets offered (not doing); ACK -> doing; GIVEUP clears; offered expires."""
from __future__ import annotations

import json
import time

import bobcallback
import bobreport
import chan_workers
import intake
import registered_machines as rm

ALLOW = {"127.0.0.1"}


def post(home, obj, *, rate=None, headers=None):
    return bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        headers or {"Content-Type": "application/json"},
        json.dumps(obj).encode(),
        "127.0.0.1",
        home,
        ALLOW,
        filer=intake.FakeGitHubFiler(),
        report_rate=rate,
    )


def workers(home, mid="marchhare"):
    return bobreport.build_digest_object(home, "Jeeves")["machines"][mid]["workers"]


def test_offer_ack_giveup_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    home = tmp_path
    nick = "marchhare-41928"
    assert post(home, {"op": "worker-upsert", "machine": "marchhare", "nick": nick})[0] == 204
    assert (
        post(
            home,
            {
                "op": "worker-work",
                "machine": "marchhare",
                "nick": nick,
                "state": "offered",
                "work": "bobiverse UAT #629",
            },
        )[0]
        == 204
    )
    w = workers(home)[0]
    assert w["state"] == "offered"
    assert "UAT #629" in w["work"]
    # tray-facing: not doing yet
    assert w["state"] != "doing"
    assert (
        post(
            home,
            {
                "op": "worker-work",
                "machine": "marchhare",
                "nick": nick,
                "state": "doing",
                "work": "bobiverse UAT #629",
            },
        )[0]
        == 204
    )
    assert workers(home)[0]["state"] == "doing"
    assert (
        post(
            home,
            {"op": "worker-work", "machine": "marchhare", "nick": nick, "state": "idle"},
        )[0]
        == 204
    )
    idle = workers(home)[0]
    assert idle["state"] == "idle" and idle["work"] == ""


def test_offered_expires_to_idle(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    home = tmp_path
    nick = "marchhare-101"
    post(home, {"op": "worker-upsert", "machine": "marchhare", "nick": nick})
    post(
        home,
        {
            "op": "worker-work",
            "machine": "marchhare",
            "nick": nick,
            "state": "offered",
            "work": "FR o/r#1",
        },
    )
    # Backdate updated stamp past timeout
    doc = bobreport.load_digest(home)
    ent = doc["machines"]["marchhare"]
    past = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() - bobreport.OFFERED_TIMEOUT_S - 5),
    )
    ent["worker_list"][0]["updated"] = past
    bobreport.save_digest(home, doc)
    w = workers(home)[0]
    assert w["state"] == "idle"
    assert w["work"] == ""


def test_tracker_on_offer_not_doing(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    home = tmp_path
    tr = chan_workers.WorkerTracker(home)
    nick = "marchhare-202"
    assert tr.on_bored(nick, "#marchhare") in (200, 204)
    assert tr.on_offer(nick, "#marchhare", "bobiverse FR #663") in (200, 204)
    w = workers(home)
    assert any(r["nick"] == nick and r["state"] == "offered" for r in w)
    assert tr.on_ack(nick, "#marchhare", "bobiverse FR #663") in (200, 204)
    assert any(r["nick"] == nick and r["state"] == "doing" for r in workers(home))
    assert tr.on_done(nick, "#marchhare") in (200, 204)
    assert any(r["nick"] == nick and r["state"] == "idle" for r in workers(home))


def test_idle_clears_machine_working_on_and_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    home = tmp_path
    nick = "marchhare-303"
    post(home, {"op": "worker-upsert", "machine": "marchhare", "nick": nick})
    post(
        home,
        {
            "op": "worker-work",
            "machine": "marchhare",
            "nick": nick,
            "state": "doing",
            "work": "bobiverse FR #168",
        },
    )
    doc = bobreport.load_digest(home)
    doc["machines"]["marchhare"]["working_on"] = "bobiverse FR #168"
    doc["machines"]["marchhare"]["jobs"] = [{"repo": "grok.exe", "state": "running"}]
    bobreport.save_digest(home, doc)
    post(
        home,
        {"op": "worker-work", "machine": "marchhare", "nick": nick, "state": "idle"},
    )
    ent = bobreport.load_digest(home)["machines"]["marchhare"]
    assert ent.get("working_on") in ("", None)
    assert ent.get("jobs") in ([], None)


def test_cursor_grok_chat_alias_maps_to_storage_id():
    # Preferred wire name normalizes to storage id grok-weekly (not xAI weekly).
    assert bobreport._normalize_cursor_pool_id("cursor-grok-chat") == "grok-weekly"
    assert bobreport._normalize_cursor_pool_id("grok-weekly") == "grok-weekly"
    assert bobreport._normalize_cursor_pool_id("sand") == "grok-weekly"
