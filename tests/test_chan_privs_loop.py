"""v0.1.19: Jeeves must not re-assign privileges in a loop (fake IRC server that echoes MODE / NAMES)."""
from __future__ import annotations

import pytest

import bobreport
import chan_privs as cp
import registered_machines as rm
import shop_ops

BOM = "\ufeff"
CHANS = ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"]
EAR = "bob-win-mpre8vi4u6u"


class Server:
    """Tiny IRC channel model: applies Jeeves' MODE lines and answers NAMES like Ergo.

    nick_decor: prefix glued onto the nick in server output (the production bug had a BOM there).
    echo: whether the server sends the MODE line back (False = a server/proxy that swallows it).
    apply: whether the mode actually lands (False = e.g. 482 / ChanServ refuses).
    """

    def __init__(self, home, *, nick_decor="", echo=True, apply=True, multi_prefix=False, userhost=False, accounts=None):
        self.sent, self.logs, self.t = [], [], 1000.0
        self.decor, self.echo, self.apply, self.multi, self.userhost = nick_decor, echo, apply, multi_prefix, userhost
        self.members = {c: {"Jeeves": {"o"}} for c in CHANS}
        self.eng = cp.ChanPrivEngine(
            send=self._send, log=self.logs.append, now=lambda: self.t, me=lambda: "Jeeves",
            channels=lambda: list(CHANS),
            is_registered=lambda mid: rm.is_registered(home, mid), normalize=bobreport.normalize_machine_id,
            chan_op=lambda ch: True, accounts=({"simon"} if accounts is None else accounts), nicks=None,
        )

    # --- wire
    def feed(self, raw):
        tags, rest, prefix = {}, raw, ""
        if rest.startswith("@"):
            tag_part, _, rest = rest[1:].partition(" ")
            tags = dict(p.split("=", 1) for p in tag_part.split(";") if "=" in p)
        if rest.startswith(":"):
            prefix, _, rest = rest[1:].partition(" ")
        parts = rest.split(" ")
        trailing = rest.split(" :", 1)[1] if " :" in rest else ""
        self.eng.on_line(parts[0], parts, trailing, prefix, tags)

    def join(self, chan, nick, modes=()):
        self.members[chan][nick] = set(modes)
        self.feed(f":{self.decor}{nick}!u@h JOIN {chan}")

    def _send(self, line):
        self.sent.append(line)
        cmd, _, rest = line.partition(" ")
        if cmd == "NAMES":
            self.names(rest.strip())
        elif cmd in ("MODE", "SAMODE"):
            chan, ms, nick = rest.split(" ")
            if self.apply:
                (self.members[chan][nick].add if ms[0] == "+" else self.members[chan][nick].discard)(ms[1])
            if self.echo:
                self.feed(f":Jeeves!u@h MODE {chan} {ms} {self.decor}{nick}")

    def names(self, chan):
        pref = {"q": "~", "a": "&", "o": "@", "h": "%", "v": "+"}
        toks = []
        for n, modes in self.members[chan].items():
            p = "".join(pref[m] for m in "qaohv" if m in modes)
            p = p if self.multi else p[:1]
            toks.append(f"{p}{self.decor}{n}" + ("!u@h" if self.userhost else ""))
        self.feed(f":srv 353 Jeeves = {chan} :{' '.join(toks)}")
        self.feed(f":srv 366 Jeeves {chan} :End of /NAMES list.")

    # --- time
    def run(self, seconds, step=5.0):
        end = self.t + seconds
        while self.t < end:
            self.t += step
            self.eng.tick()

    def modes(self):
        return [s for s in self.sent if s.startswith(("MODE", "SAMODE"))]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, CHANS)
    return tmp_path


def _boot(srv):
    for c in CHANS:
        srv.names(c)


# ------------------------------------------------------------------ the production loop
@pytest.mark.parametrize("opts", [
    {}, {"nick_decor": BOM}, {"multi_prefix": True}, {"userhost": True},
    {"nick_decor": BOM, "multi_prefix": True, "userhost": True},
])
def test_grant_is_sent_once_then_idempotent_over_half_an_hour(home, opts):
    srv = Server(home, **opts)
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    srv.members["#bobiverse"][EAR] = set()
    _boot(srv)
    srv.run(1800)
    assert sorted(srv.modes()) == sorted(["MODE #win-mpre8vi4u6u +o " + EAR, "MODE #bobiverse +h " + EAR])
    assert srv.members["#win-mpre8vi4u6u"][EAR] == {"o"}


def test_bom_in_names_is_stripped_so_the_state_matches_the_real_nick(home):
    srv = Server(home, nick_decor=BOM)
    srv.members["#win-mpre8vi4u6u"][EAR] = {"o"}
    _boot(srv)
    srv.run(600)
    assert srv.modes() == []                       # already +o: nothing to send, ever
    ent = srv.eng.state.members["#win-mpre8vi4u6u"][EAR]
    assert ent["nick"] == EAR and BOM not in ent["nick"]


def test_mode_echo_with_bom_nick_is_recorded_against_the_real_nick(home):
    srv = Server(home, nick_decor=BOM, echo=True)
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    srv.names("#win-mpre8vi4u6u")                  # grant goes out, echo lands with a BOM nick
    assert srv.eng.state.members["#win-mpre8vi4u6u"][EAR]["modes"] == {"o"}
    assert len(srv.modes()) == 1


def test_never_reacts_to_its_own_mode_echo(home):
    srv = Server(home)
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    srv.apply = False                              # server keeps refusing, but echoes: must not recurse
    srv.names("#win-mpre8vi4u6u")
    assert len(srv.modes()) == 1                   # not re-sent by the echo of the first one
    srv.feed(":Jeeves!u@h MODE #win-mpre8vi4u6u +o " + EAR)
    srv.feed(":Jeeves!u@h MODE #win-mpre8vi4u6u +o " + EAR)
    assert len(srv.modes()) == 1


def test_server_sourced_mode_is_also_not_a_trigger(home):
    srv = Server(home)
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    srv.apply = False
    srv.names("#win-mpre8vi4u6u")
    srv.feed(":irc.ntsa.uk MODE #win-mpre8vi4u6u +v somebody")
    assert len(srv.modes()) == 1


def test_swallowed_echo_and_refused_mode_back_off_instead_of_looping(home):
    srv = Server(home, echo=False, apply=False)    # worst case: nothing ever confirms
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    _boot(srv)
    srv.run(3600)
    n = len(srv.modes())
    # RESEND_S=20 would be ~60 sends/hour at the 60 s reconcile; backoff doubles up to 10 min.
    assert 2 <= n <= 12, srv.modes()      # 20,40,80,160,320,600,600,... not one per reconcile (60/h)
    assert any("WARN" in m and "without the channel state changing" in m for m in srv.logs)
    assert sum("WARN" in m for m in srv.logs) == 1             # warned once, not on every attempt


def test_log_only_on_actual_change(home):
    srv = Server(home)
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    _boot(srv)
    srv.run(1800)
    grants = [m for m in srv.logs if "GRANT" in m]
    assert len(grants) == 1
    assert sum("confirmed +o" in m for m in srv.logs) == 1


def test_real_deop_is_regranted_after_the_gap(home):
    srv = Server(home)
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    _boot(srv)
    srv.run(120)
    assert len(srv.modes()) == 1
    srv.members["#win-mpre8vi4u6u"][EAR].discard("o")
    srv.feed(f":Jeeves!u@h MODE #win-mpre8vi4u6u -o {EAR}")      # not Jeeves in reality; still our own echo
    srv.run(300)
    assert len(srv.modes()) == 2


def test_other_actor_deopping_triggers_a_regrant_but_rate_limited(home):
    srv = Server(home)
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    _boot(srv)
    for _ in range(30):                            # someone de-ops every few seconds
        srv.members["#win-mpre8vi4u6u"][EAR].discard("o")
        srv.feed(f":rogue!u@h MODE #win-mpre8vi4u6u -o {EAR}")
        srv.t += 5
    assert len(srv.modes()) <= 4


# ------------------------------------------------------------------ +h in #bobiverse, Simon's +o
def test_h_in_bobiverse_once(home):
    srv = Server(home, nick_decor=BOM)
    srv.members["#bobiverse"][EAR] = set()
    _boot(srv)
    srv.run(1800)
    assert srv.modes() == ["MODE #bobiverse +h " + EAR]


def test_simon_o_granted_once_and_revoked_once(home):
    srv = Server(home, nick_decor=BOM)
    srv.members["#bobiverse"]["simon"] = set()
    _boot(srv)
    srv.feed(":simon!u@h ACCOUNT simon")
    srv.run(1800)
    assert [m for m in srv.modes() if "simon" in m] == ["MODE #bobiverse +o simon"]
    srv.feed(":simon!u@h ACCOUNT *")
    srv.run(1800)
    assert [m for m in srv.modes() if "simon" in m] == ["MODE #bobiverse +o simon", "MODE #bobiverse -o simon"]


def test_simon_already_op_is_left_alone(home):
    srv = Server(home, multi_prefix=True, userhost=True)
    srv.members["#bobiverse"]["simon"] = {"o"}
    _boot(srv)
    srv.feed(":simon!u@h ACCOUNT simon")
    srv.run(900)
    assert srv.modes() == []


# ------------------------------------------------------------------ BOM / whitespace hygiene
def test_clean_helpers():
    assert cp.clean(f"{BOM} bob-x \u200b") == "bob-x"
    assert cp.clean_nick(f":{BOM}bob-x\r") == "bob-x"
    assert cp.parse_names(f"@{BOM}bob-x %{BOM}y!u@h {BOM}") == [("bob-x", {"o"}), ("y", {"h"})]
    assert cp.parse_mode_changes(["MODE", "#c", "+o", f":{BOM}bob-x"]) == [("#c", "o", True, "bob-x")]
    assert cp.parse_mode_changes(["MODE", f"{BOM}#c", f"{BOM}+ov", f"{BOM}a", "b "]) == [
        ("#c", "o", True, "a"), ("#c", "v", True, "b")]


def test_bob_machine_with_bom_and_case(home):
    reg = lambda mid: rm.is_registered(home, mid)
    assert cp.bob_machine(f"{BOM}Bob-WIN-MPRE8VI4U6U ", reg, bobreport.normalize_machine_id) == "win-mpre8vi4u6u"


def test_op_accounts_file_with_bom_and_env_with_bom(tmp_path):
    (tmp_path / "op-accounts.txt").write_bytes(b"\xef\xbb\xbf\xef\xbb\xbfSimon # me\r\n")
    accts, src = cp.op_accounts({"BOB_CONFIG_DIR": str(tmp_path)})
    assert accts == {"simon"} and src == cp.OP_ACCOUNTS_FILE
    accts, src = cp.op_accounts({"BOB_OP_ACCOUNTS": f"{BOM}Simon, {BOM}bob2"})
    assert accts == {"simon", "bob2"} and src == cp.OP_ACCOUNTS_ENV
    assert cp.op_nicks({"BOB_OP_NICKS": f"{BOM}Simon"}) == {"simon"}


def test_shop_ops_raw_mode_line_strips_bom_from_nick():
    line = f"MODE #marchhare +o {BOM}bob-marchhare"
    assert shop_ops.raw_op_line(f"{BOM}{line}", "bob-marchhare") == "MODE #marchhare +o bob-marchhare"


def test_rejoin_after_quit_gets_a_fresh_prompt_grant_even_after_earlier_grants(home):
    srv = Server(home, nick_decor=BOM)
    srv.members["#win-mpre8vi4u6u"][EAR] = set()
    _boot(srv)
    assert len(srv.modes()) == 1
    for _ in range(3):                                   # bob restarts: QUIT then JOIN, a few seconds apart
        srv.feed(f":{BOM}{EAR}!u@h QUIT :bye")
        srv.members["#win-mpre8vi4u6u"].pop(EAR, None)
        srv.t += 7
        srv.join("#win-mpre8vi4u6u", EAR)
    assert len(srv.modes()) == 4                         # one grant per real arrival, none from the echoes


def test_chair_own_op_state_survives_bom_and_userhost_names():
    import chair_oper
    r = chair_oper.names_has_op(["", "353", "Jeeves", "=", "#bobiverse"], f"{BOM}@{BOM}Jeeves!u@h bob-x", f"{BOM}Jeeves")
    assert r == ("#bobiverse", True)
    assert chair_oper.mode_changes_for(["MODE", "#c", "+o", f":{BOM}Jeeves"], "Jeeves") == [("#c", "o", True)]
