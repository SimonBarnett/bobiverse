"""v0.1.19+: +h/+o grant hard cap (3 per (channel,nick,mode) per 10 min), idempotence, SAMODE vs MODE,
ChanServ-strips-the-mode fight, % / multi-prefix NAMES, and the quiet 'unverified WHOIS' log (fake IRC)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import chan_privs as cp  # noqa: E402
from test_chan_privs_loop import BOM, CHANS, EAR, Server, _boot, home  # noqa: E402,F401

W, BF = "#win-mpre8vi4u6u", "#bobiverse"


class TimedServer(Server):
    """Server that timestamps every MODE and can act like ChanServ / Ergo SAMODE."""

    def __init__(self, home, *, strip=None, echo_from="Jeeves!u@h", whois_answer=True, **kw):
        super().__init__(home, **kw)
        self.strip, self.echo_from, self.whois_answer = strip, echo_from, whois_answer
        self.stamped: list = []

    def _send(self, line):
        self.sent.append(line)
        cmd, _, rest = line.partition(" ")
        if cmd == "NAMES":
            self.names(rest.strip())
        elif cmd == "WHOIS":
            if self.whois_answer:
                self.feed(f":srv 318 Jeeves {rest.strip()} :End of /WHOIS list.")
        elif cmd in ("MODE", "SAMODE"):
            self.stamped.append((self.t, line))
            chan, ms, nick = rest.split(" ")
            self.members[chan][nick].add(ms[1]) if ms[0] == "+" else self.members[chan][nick].discard(ms[1])
            self.feed(f":{self.echo_from} MODE {chan} {ms} {nick}")
            if self.strip and ms == f"+{self.strip[0]}" and chan == self.strip[1]:
                self.members[chan][nick].discard(ms[1])          # ChanServ AMODE / founder rule undoes it
                self.feed(f":ChanServ!ChanServ@services. MODE {chan} -{ms[1]} {nick}")


def _flap(srv, chan, nick, times, every):
    for _ in range(times):
        srv.feed(f":{nick}!u@h QUIT :Client Quit")
        srv.members[chan].pop(nick, None)
        srv.t += every
        srv.join(chan, nick)


def test_flapping_ear_gets_at_most_three_h_grants_per_ten_minutes_then_one_warn(home):
    srv = TimedServer(home)
    srv.join(BF, EAR)
    for _ in range(12):                                   # the 06:32-06:51 loop: re-join every ~30-60 s
        _flap(srv, BF, EAR, 1, 45)
    h = [m for _, m in srv.stamped if m == f"MODE {BF} +h {EAR}"]
    assert len(h) == 3, srv.stamped
    capw = [m for m in srv.logs if "hard cap" in m and f"+h {EAR}" in m]
    assert len(capw) == 1, capw                           # warned once, not on every re-join
    # the window slides: after 10 quiet minutes the next real arrival is granted again
    srv.t += 700
    _flap(srv, BF, EAR, 1, 5)
    assert len([m for _, m in srv.stamped if m == f"MODE {BF} +h {EAR}"]) == 4


def test_o_in_own_channel_is_capped_the_same_way(home):
    srv = TimedServer(home)
    srv.join(W, EAR)
    _flap(srv, W, EAR, 10, 20)
    assert len([1 for _, m in srv.stamped if m == f"MODE {W} +o {EAR}"]) == 3


def test_steady_joined_nick_never_repeats(home):
    srv = TimedServer(home)
    srv.members[BF][EAR] = set()
    srv.members[W][EAR] = set()
    _boot(srv)
    srv.run(3 * 3600)
    assert sorted(m for _, m in srv.stamped) == sorted([f"MODE {BF} +h {EAR}", f"MODE {W} +o {EAR}"])


def test_chanserv_strips_h_is_a_capped_fight_not_a_loop(home):
    srv = TimedServer(home, strip=("h", BF))
    srv.members[BF][EAR] = set()
    _boot(srv)
    srv.run(3600)
    stamps = [t for t, m in srv.stamped if m == f"MODE {BF} +h {EAR}"]
    assert 1 <= len(stamps) <= 18
    for t0 in stamps:                                     # never more than 3 inside any 10-minute window
        assert len([t for t in stamps if t0 <= t < t0 + cp.CAP_WINDOW_S]) <= cp.CAP_MAX
    removed = [m for m in srv.logs if "was removed by ChanServ" in m]
    assert removed and "undoing our grant" in removed[0]
    assert len(removed) <= 7                              # once per 10 min per key


def test_percent_prefix_and_multi_prefix_mean_half_op_already(home):
    srv = TimedServer(home, multi_prefix=True, userhost=True)
    srv.members[BF][EAR] = {"h", "v"}                     # NAMES shows %+bob-...
    _boot(srv)
    srv.run(900)
    assert srv.stamped == []
    assert cp.parse_names("%+bob-x @%y ~&@%+z") == [("bob-x", {"h", "v"}), ("y", {"o", "h"}),
                                                     ("z", {"q", "a", "o", "h", "v"})]


def test_ear_that_is_already_op_in_bobiverse_needs_no_h(home):
    srv = TimedServer(home)
    srv.members[BF][EAR] = {"o"}
    _boot(srv)
    srv.run(600)
    assert srv.stamped == []


def test_samode_grant_server_echo_is_not_a_retrigger(home):
    srv = TimedServer(home, echo_from="irc.ntsa.uk")       # SAMODE: the echo is server sourced
    srv.eng.chan_op = lambda ch: False                     # Jeeves has no +o here ...
    srv.eng.is_oper = lambda: True                         # ... but is an IRC operator
    srv.members[BF][EAR] = set()
    _boot(srv)
    srv.run(1800)
    assert [m for _, m in srv.stamped] == [f"SAMODE {BF} +h {EAR}"]
    assert any(f"confirmed +h {EAR}" in m for m in srv.logs)


def test_mode_via_plain_mode_and_via_samode_are_both_confirmed_and_idempotent(home):
    for chan_op, oper, verb in ((True, False, "MODE"), (False, True, "SAMODE")):
        srv = TimedServer(home)
        srv.eng.chan_op = lambda ch, v=chan_op: v
        srv.eng.is_oper = lambda v=oper: v
        srv.members[BF][EAR] = set()
        _boot(srv)
        srv.run(900)
        assert [m for _, m in srv.stamped] == [f"{verb} {BF} +h {EAR}"]


def test_unverified_whois_is_logged_once_not_every_minute(home):
    srv = TimedServer(home)
    srv.members[BF]["simon"] = set()
    _boot(srv)
    srv.run(1500)                                          # 25 minutes of the 60 s reconcile
    lines = [m for m in srv.logs if "simon unverified" in m]
    whois = [s for s in srv.sent if s == "WHOIS simon"]
    assert len(whois) >= 10                                # still re-verifies (a logout would otherwise go unseen)
    assert len(lines) == 1, lines
    srv.run(600)
    lines = [m for m in srv.logs if "simon unverified" in m]
    assert len(lines) == 2 and "identical lookups" in lines[1]


def test_sweep_clears_backoff_but_not_the_hard_cap(home):
    srv = TimedServer(home, strip=("h", BF))
    srv.members[BF][EAR] = set()
    _boot(srv)
    for _ in range(8):
        srv.t += 5
        srv.eng.sweep(BF)
    assert len([1 for _, m in srv.stamped if m == f"MODE {BF} +h {EAR}"]) == cp.CAP_MAX
