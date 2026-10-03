"""v0.1.18: chair-side IRC events -> worker list (fake IRC, real Client methods, real digest)."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

import bobreport
import chan_workers
import gitclaim
import irc_agent
import registered_machines as rm

MH = "marchhare"
SEAT = "marchhare-101"


class FakeChair:
    def __init__(self, home):
        self.args = SimpleNamespace(chair=True)
        self.home = home
        self.live_nick = "Jeeves"
        self.original_nick = "Jeeves"
        self.channels = ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"]
        self.sent, self.said, self.logs = [], [], []
        self.joined = SimpleNamespace(is_set=lambda: True)
        self._chan_op = {c: True for c in self.channels}
        self._op_try_at = {}
        self._oper_state = "off"
        self.accounts = None

    def send(self, line):
        self.sent.append(line)

    def _digest_home(self):
        return self.home

    def _joined_channel(self, target):
        return target.lower() in {c.lower() for c in self.channels}

    def _git_say(self, target, text):
        self.said.append((target, text))

    def _fleet_moot_state(self):
        return {}

    def _mine_nicks(self):
        return {"jeeves"}

    def _note_call_channel(self, target):
        pass

    _workers = irc_agent.Client._workers
    _privs = irc_agent.Client._privs
    _privs_skip_whois = irc_agent.Client._privs_skip_whois
    _on_channel_names = irc_agent.Client._on_channel_names
    _chair_wire = irc_agent.Client._chair_wire
    _maybe_git_claim = irc_agent.Client._maybe_git_claim
    _maybe_shop_listen = irc_agent.Client._maybe_shop_listen
    def _refresh_ledger(self): pass          # no GitHub lookups in unit tests
    _git_bored = irc_agent.Client._git_bored
    _git_ack = irc_agent.Client._git_ack
    _git_accept = irc_agent.Client._git_accept
    _maybe_grant_bob_modes = irc_agent.Client._maybe_grant_bob_modes
    _chan_privs_tick = irc_agent.Client._chan_privs_tick


@pytest.fixture
def chair(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    c = FakeChair(tmp_path)
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    return c


def listed(chair, mid=MH):
    return bobreport.build_digest_object(chair.home, "J")["machines"][mid]["workers"]


def say(chair, nick, chan, body):
    chair.handle = irc_agent.Client.handle_privmsg  # noqa: F841 (documented entry point)
    chair._maybe_shop_listen(nick, chan, body) or chair._maybe_git_claim(nick, chan, body)


def wire(chair, line):
    """Parse a raw server line the way Client.reader does and feed the chair-side hooks."""
    tags, rest = {}, line
    prefix = ""
    if rest.startswith(":"):
        prefix, _, rest = rest[1:].partition(" ")
    parts = rest.split(" ")
    trailing = rest.split(" :", 1)[1] if " :" in rest else ""
    chair._chair_wire(parts[0], parts, trailing, prefix, tags)


def queue(home, *rows):
    gitclaim._write_queue(gitclaim.queue_path(home), {"v": 1, "unaccepted": list(rows), "accepted": []})


def row(n=5):
    return {"repo": "o/r", "task": "FR", "id": f"#{n}", "seq": n, "ts": "2026-10-01T10:00:01Z", "line": "x",
            "title": "fix the thing"}


def test_bored_adds_speaker_idle_in_own_machine_channel(chair):
    queue(chair.home)
    say(chair, SEAT, "#marchhare", "!bored")
    assert [(w["nick"], w["state"]) for w in listed(chair)] == [(SEAT, "idle")]
    assert listed(chair, "win-mpre8vi4u6u") == []


def test_bored_even_when_gate_says_ignore_or_empty(chair):
    queue(chair.home)                                   # empty queue -> "nothing queued"
    say(chair, SEAT, "#marchhare", "!bored")
    assert any("nothing queued" in t for _, t in chair.said)
    assert [w["nick"] for w in listed(chair)] == [SEAT]


def test_bored_in_wrong_channel_or_fleet_channel_is_not_a_worker(chair):
    queue(chair.home)
    say(chair, SEAT, "#win-mpre8vi4u6u", "!bored")
    say(chair, SEAT, "#bobiverse", "!bored")
    assert listed(chair) == [] and listed(chair, "win-mpre8vi4u6u") == []


@pytest.mark.parametrize("nick", ["marchhare_console", "bob-marchhare", "Jeeves", "ChanServ", "simon"])
def test_non_workers_never_listed_even_if_they_say_bored(chair, nick):
    queue(chair.home)
    say(chair, nick, "#marchhare", "!bored")
    assert listed(chair) == []


def test_ack_sets_doing_and_done_sets_idle(chair):
    queue(chair.home, row(5))
    say(chair, SEAT, "#marchhare", "!bored")
    say(chair, SEAT, "#marchhare", "ACK FR o/r#5 fix the thing")
    w = listed(chair)[0]
    assert w["state"] == "doing" and w["work"] == "r FR #5"
    say(chair, SEAT, "#marchhare", "DONE FR o/r#5 PASS merged")
    w = listed(chair)[0]
    assert w["state"] == "idle" and w["work"] == ""


def test_ack_from_unlisted_seat_adds_it(chair):
    queue(chair.home, row(6))
    say(chair, SEAT, "#marchhare", "ACK FR o/r#6 title")
    assert [(w["nick"], w["state"]) for w in listed(chair)] == [(SEAT, "doing")]


def test_nack_giveup_go_idle(chair):
    queue(chair.home, row(7))
    say(chair, SEAT, "#marchhare", "ACK FR o/r#7 t")
    say(chair, SEAT, "#marchhare", "GIVEUP FR o/r#7 cannot")
    assert listed(chair)[0]["state"] == "idle"


def _two(chair):
    queue(chair.home)
    for n in ("marchhare-101", "marchhare-102"):
        say(chair, n, "#marchhare", "!bored")
    assert len(listed(chair)) == 2


def test_part_removes_worker(chair):
    _two(chair)
    wire(chair, ":marchhare-101!u@h PART #marchhare :bye")
    assert [w["nick"] for w in listed(chair)] == ["marchhare-102"]


def test_part_of_other_channel_keeps_worker(chair):
    _two(chair)
    wire(chair, ":marchhare-101!u@h PART #bobiverse :bye")
    assert len(listed(chair)) == 2


def test_quit_removes_worker(chair):
    _two(chair)
    wire(chair, ":marchhare-102!u@h QUIT :Ping timeout")
    assert [w["nick"] for w in listed(chair)] == ["marchhare-101"]


def test_kick_removes_the_kicked_nick_not_the_kicker(chair):
    _two(chair)
    wire(chair, ":bob-marchhare!u@h KICK #marchhare marchhare-101 :invalid")
    assert [w["nick"] for w in listed(chair)] == ["marchhare-102"]


def test_kick_by_jeeves_itself_removes_the_kicked_worker(chair):
    _two(chair)
    wire(chair, ":Jeeves!u@h KICK #marchhare marchhare-102 :invalid seat")
    assert [w["nick"] for w in listed(chair)] == ["marchhare-101"]


def test_nick_change_drops_old_nick(chair):
    _two(chair)
    wire(chair, ":marchhare-101!u@h NICK :marchhare-999")
    assert [w["nick"] for w in listed(chair)] == ["marchhare-102"]
    say(chair, "marchhare-999", "#marchhare", "!bored")                       # re-added when it speaks
    assert sorted(w["nick"] for w in listed(chair)) == ["marchhare-102", "marchhare-999"]


def test_names_reconcile_drops_absentees_only(chair):
    _two(chair)
    wire(chair, ":srv 353 Jeeves = #marchhare :@Jeeves +bob-marchhare marchhare-102 simon")
    wire(chair, ":srv 366 Jeeves #marchhare :End of /NAMES list.")
    assert [w["nick"] for w in listed(chair)] == ["marchhare-102"]
    assert any("workers reconcile" in m and "marchhare-101" in m for m in chair.logs)


def test_names_reconcile_ignores_fleet_channel(chair):
    _two(chair)
    wire(chair, ":srv 353 Jeeves = #bobiverse :@Jeeves")
    wire(chair, ":srv 366 Jeeves #bobiverse :End")
    assert len(listed(chair)) == 2


def test_periodic_tick_requests_names_for_every_channel(chair):
    chair._chan_privs_tick()
    assert {s for s in chair.sent if s.startswith("NAMES")} == {f"NAMES {c}" for c in chair.channels}


def test_own_nick_events_are_ignored(chair):
    _two(chair)
    wire(chair, ":Jeeves!u@h PART #marchhare :x")
    assert len(listed(chair)) == 2


def test_post_fn_gets_payloads_and_roster_gate_still_applies(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    got = []
    t = chan_workers.WorkerTracker(tmp_path, post_fn=lambda p: got.append(p) or 204)
    assert t.on_bored(SEAT, "#marchhare") == 204
    assert got == [{"op": "worker-upsert", "machine": "marchhare", "nick": SEAT}]
    assert t.on_bored("ionos-5", "#ionos") is None                            # not a roster channel
    assert t.post({"op": "worker-upsert", "machine": "ionos", "nick": "ionos-5"}) == 403
    assert len(got) == 1


# ---- t816u: short worker status "<reponame> FR|MRB|UAT #<num>" on assign, ACK (even unmatched), cleared on DONE/NACK/GIVEUP
def test_assign_sets_doing_with_short_status_before_ack(chair):
    queue(chair.home, row(68))
    say(chair, SEAT, "#marchhare", "!bored")
    assert any("o/r#68" in t for _, t in chair.said)                  # wire line unchanged
    w = listed(chair)[0]
    assert (w["nick"], w["state"], w["work"]) == (SEAT, "offered", "r FR #68")   # FR #663: offered until the ACK
    say(chair, SEAT, "#marchhare", "ACK FR o/r#68 long title that must not be in the status")
    assert listed(chair)[0]["work"] == "r FR #68"
    say(chair, SEAT, "#marchhare", "DONE FR o/r#68 PASS merged")
    assert listed(chair)[0]["state"] == "idle"


@pytest.mark.parametrize("verb", ["NACK", "GIVEUP"])
def test_assign_then_nack_or_giveup_clears_to_idle(chair, verb):
    queue(chair.home, row(9))
    say(chair, SEAT, "#marchhare", "!bored")
    assert listed(chair)[0]["state"] == "offered"
    say(chair, SEAT, "#marchhare", f"{verb} FR o/r#9 cannot")
    assert listed(chair)[0]["state"] == "idle" and listed(chair)[0]["work"] == ""


def test_ack_for_row_no_longer_queued_still_shows_doing(chair):
    queue(chair.home)                                                 # row gone (re-sync / already accepted)
    say(chair, SEAT, "#marchhare", "ACK MRB SimonBarnett/bobiverse#12 whatever")
    w = listed(chair)[0]
    assert (w["state"], w["work"]) == ("doing", "bobiverse MRB #12")
    say(chair, SEAT, "#marchhare", "DONE MRB SimonBarnett/bobiverse#12 PASS")
    assert listed(chair)[0]["state"] == "idle"


def test_bored_with_nothing_queued_is_idle(chair):
    queue(chair.home, row(3))
    say(chair, SEAT, "#marchhare", "!bored")
    assert listed(chair)[0]["state"] == "offered"
    queue(chair.home)                                                 # the offer vanished
    chair._git_bored(SEAT, "#marchhare", time.time() + 3600, chair=True)
    assert listed(chair)[0]["state"] == "idle"


def test_short_work_format():
    import shop_listen
    assert shop_listen.short_work("fr", "SimonBarnett/bobiverse", "#68") == "bobiverse FR #68"
    assert shop_listen.short_work("UAT", "plain", "7") == "plain UAT #7"
    assert shop_listen.activity_description({"task": "MRB", "repo": "a/b", "id": "#1", "line": "GIT x"}) == "b MRB #1"

def test_self_uat_giveup_loop_ends_idle_not_stuck_doing(chair):
    """t852u: a seat that GIVEUPs a self-UAT is never offered it again (ledger survives a row rebuild)
    and the digest goes to idle (not stuck on 'doing UAT #269')."""
    uat = {"repo": "o/r", "task": "UAT", "id": "#269", "seq": 1, "ts": "2026-10-03T09:21:37Z", "line": "x", "refs": ["#623"],
           "url": "https://github.com/o/r/issues/269"}
    queue(chair.home, dict(uat))
    say(chair, SEAT, "#marchhare", "!bored")
    assert listed(chair)[0]["state"] == "offered"
    say(chair, SEAT, "#marchhare", "ACK UAT o/r#269 x")
    say(chair, SEAT, "#marchhare", "GIVEUP UAT o/r#269 self-UAT forbidden")
    assert listed(chair)[0]["state"] == "idle" and listed(chair)[0]["work"] == ""
    queue(chair.home, dict(uat))                       # resync rebuilt the row without any stamp
    chair.said.clear()
    say(chair, SEAT, "#marchhare", "!bored")
    assert not any("UAT" in t for _, t in chair.said) and any("nothing queued" in t for _, t in chair.said)
    assert listed(chair)[0]["state"] == "idle"
