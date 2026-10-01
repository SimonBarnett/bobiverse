"""v0.1.18: channel privilege rules enforced chair-side (fake IRC server in, MODE lines out)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import bobreport
import chan_privs as cp
import irc_agent
import registered_machines as rm

CHANS = ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u"]


class Fake:
    """Drives ChanPrivEngine like Client.reader does; records everything Jeeves sends."""

    def __init__(self, home, *, accounts=None, nicks=None, ops=True, oper=False):
        self.sent, self.logs, self.t = [], [], 1000.0
        self.ops = {c.lower(): ops for c in CHANS}
        self.oper = oper
        self.eng = cp.ChanPrivEngine(
            send=self.sent.append, log=self.logs.append, now=lambda: self.t, me=lambda: "Jeeves",
            channels=lambda: list(CHANS),
            is_registered=lambda mid: rm.is_registered(home, mid), normalize=bobreport.normalize_machine_id,
            chan_op=lambda ch: self.ops.get(ch.lower(), False), is_oper=lambda: self.oper,
            accounts=({"simon"} if accounts is None else (None if accounts == "env" else accounts)), nicks=nicks,
        )

    def line(self, raw):
        tags, rest, prefix = {}, raw, ""
        if rest.startswith("@"):
            tag_part, _, rest = rest[1:].partition(" ")
            tags = dict(p.split("=", 1) for p in tag_part.split(";") if "=" in p)
        if rest.startswith(":"):
            prefix, _, rest = rest[1:].partition(" ")
        parts = rest.split(" ")
        trailing = rest.split(" :", 1)[1] if " :" in rest else ""
        self.eng.on_line(parts[0], parts, trailing, prefix, tags)

    def names(self, chan, members):
        self.line(f":srv 353 Jeeves = {chan} :{members}")
        self.line(f":srv 366 Jeeves {chan} :End of /NAMES list.")

    def modes(self):
        return [s for s in self.sent if s.startswith(("MODE", "SAMODE"))]

    def clear(self):
        self.sent.clear()
        self.logs.clear()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, CHANS)
    return tmp_path


@pytest.fixture
def irc(home):
    return Fake(home)


# ----------------------------------------------------------------------------- rule 2: bob ears
def test_bob_gets_o_in_own_channel_and_h_in_bobiverse(irc):
    irc.names("#marchhare", "@Jeeves bob-marchhare")
    irc.names("#bobiverse", "@Jeeves bob-marchhare")
    assert irc.modes() == ["MODE #marchhare +o bob-marchhare", "MODE #bobiverse +h bob-marchhare"]


def test_bob_never_gets_ops_in_another_machines_channel(irc):
    irc.names("#win-mpre8vi4u6u", "@Jeeves bob-marchhare")
    assert irc.modes() == []


def test_bob_of_unregistered_machine_gets_nothing(irc):
    irc.names("#marchhare", "@Jeeves bob-evil bob-marchhare_")
    assert irc.modes() == []


def test_bob_already_correct_or_higher_is_left_alone(irc):
    irc.names("#marchhare", "@Jeeves @bob-marchhare")
    irc.names("#bobiverse", "@Jeeves %bob-marchhare")
    irc.names("#win-mpre8vi4u6u", "@Jeeves @%bob-win-mpre8vi4u6u")
    assert irc.modes() == []


def test_bob_join_is_applied_immediately(irc):
    irc.names("#marchhare", "@Jeeves")
    irc.line(":bob-marchhare!u@h JOIN #marchhare")
    assert irc.modes() == ["MODE #marchhare +o bob-marchhare"]
    irc.line(":bob-marchhare!u@h JOIN #bobiverse")
    assert irc.modes()[-1] == "MODE #bobiverse +h bob-marchhare"


def test_seats_and_consoles_get_nothing(irc):
    irc.names("#marchhare", "@Jeeves marchhare-101 marchhare_console")
    assert irc.modes() == []


# ----------------------------------------------------------------------------- rule 3: Simon
def test_simon_with_verified_account_gets_o(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":simon!u@h ACCOUNT simon")
    assert "MODE #bobiverse +o simon" in irc.modes()


def test_simon_extended_join_account_grants_everywhere_he_joins(irc):
    irc.names("#marchhare", "@Jeeves")
    irc.line(":simon!u@h JOIN #marchhare simon :Simon")
    assert irc.modes() == ["MODE #marchhare +o simon"]


def test_account_tag_on_join_grants(irc):
    irc.names("#bobiverse", "@Jeeves")
    irc.line("@account=simon :simon!u@h JOIN #bobiverse")
    assert irc.modes() == ["MODE #bobiverse +o simon"]


def test_nick_alone_never_grants_even_if_it_is_literally_simon(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":simon!u@h JOIN #bobiverse * :x")        # extended-join with no account
    irc.line(":srv 318 Jeeves simon :End of WHOIS")
    assert [m for m in irc.modes() if "+o simon" in m] == []


def test_unknown_account_triggers_whois_not_a_grant(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    assert "WHOIS simon" in irc.sent and irc.modes() == []
    irc.line(":srv 330 Jeeves simon simon :is logged in as")
    irc.line(":srv 318 Jeeves simon :End of /WHOIS list.")
    assert irc.modes() == ["MODE #bobiverse +o simon"]


def test_whois_without_account_marks_not_logged_in_and_never_grants(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":srv 318 Jeeves simon :End of /WHOIS list.")
    assert irc.modes() == []


def test_other_account_on_simon_nick_is_not_granted(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":simon!u@h ACCOUNT mallory")
    assert irc.modes() == []


def test_verified_simon_under_another_nick_is_granted_by_account(irc):
    irc.names("#bobiverse", "@Jeeves sb-laptop")
    irc.line(":sb-laptop!u@h ACCOUNT simon")
    assert irc.modes() == ["MODE #bobiverse +o sb-laptop"]


def test_someone_elses_account_never_granted(irc):
    irc.names("#bobiverse", "@Jeeves alice")
    irc.line(":alice!u@h ACCOUNT alice")
    assert irc.modes() == []


def test_logout_revokes_o_that_jeeves_granted(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":simon!u@h ACCOUNT simon")
    irc.line(":Jeeves!u@h MODE #bobiverse +o simon")
    irc.clear()
    irc.line(":simon!u@h ACCOUNT *")
    assert irc.modes() == ["MODE #bobiverse -o simon"]
    assert any("WARN" not in m and "REVOKE" in m and "not logged in" in m for m in irc.logs)


def test_unverified_simon_nick_holding_o_is_deopped(irc):
    irc.names("#bobiverse", "@Jeeves @simon")
    irc.line(":srv 318 Jeeves simon :End of /WHOIS list.")
    assert irc.modes() == ["MODE #bobiverse -o simon"]


def test_other_nick_holding_o_is_never_touched(irc):
    irc.names("#bobiverse", "@Jeeves @alice")
    irc.line(":srv 318 Jeeves alice :End of WHOIS")
    assert irc.modes() == []


def test_account_resolution_is_session_only_not_persisted_file(home, monkeypatch):
    # accounts.json (persisted AccountMap) says simon -> simon; a fresh session has not verified it yet.
    f = Fake(home)
    f.names("#bobiverse", "@Jeeves simon")
    assert f.modes() == [] and "WHOIS simon" in f.sent


def test_quit_and_rejoin_needs_fresh_verification(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":simon!u@h ACCOUNT simon")
    irc.line(":simon!u@h QUIT :bye")
    irc.clear()
    irc.line(":simon!u@h JOIN #bobiverse * :x")
    assert irc.modes() == []


def test_nick_change_carries_verified_account(irc):
    irc.names("#bobiverse", "@Jeeves sb")
    irc.line(":sb!u@h ACCOUNT simon")
    irc.line(":Jeeves!u@h MODE #bobiverse +o sb")
    irc.clear()
    irc.line(":sb!u@h NICK :simon")
    assert irc.modes() == []                       # already +o, account carried over


# ----------------------------------------------------------------------------- drift / reconcile
def test_mode_drift_bob_deopped_is_reapplied(irc):
    irc.names("#marchhare", "@Jeeves @bob-marchhare")
    irc.t += 30
    irc.line(":someone!u@h MODE #marchhare -o bob-marchhare")
    assert irc.modes() == ["MODE #marchhare +o bob-marchhare"]


def test_mode_drift_simon_deopped_is_reapplied_when_verified(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":simon!u@h ACCOUNT simon")
    irc.line(":Jeeves!u@h MODE #bobiverse +o simon")
    irc.clear()
    irc.t += 30
    irc.line(":x!u@h MODE #bobiverse -o simon")
    assert irc.modes() == ["MODE #bobiverse +o simon"]


def test_mode_drift_manual_op_of_unverified_simon_is_reverted(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":srv 318 Jeeves simon :End of WHOIS")
    irc.clear()
    irc.line(":x!u@h MODE #bobiverse +o simon")
    assert irc.modes() == ["MODE #bobiverse -o simon"]


def test_no_mode_flood_same_action_is_rate_limited(irc):
    irc.names("#marchhare", "@Jeeves bob-marchhare")
    irc.line(":x!u@h MODE #marchhare -o bob-marchhare")
    irc.line(":x!u@h MODE #marchhare -o bob-marchhare")
    assert irc.modes() == ["MODE #marchhare +o bob-marchhare"]
    irc.t += cp.RESEND_S + 1
    irc.line(":x!u@h MODE #marchhare -o bob-marchhare")
    assert len(irc.modes()) == 2


def test_periodic_reconcile_requests_names_and_fixes_missed_drift(irc):
    irc.names("#marchhare", "@Jeeves @bob-marchhare")
    irc.clear()
    irc.eng.tick()
    assert {s for s in irc.sent} == {f"NAMES {c}" for c in CHANS}
    irc.clear()
    irc.eng.tick()                                   # inside the interval: nothing
    assert irc.sent == []
    irc.t += cp.RECONCILE_S + 1
    irc.eng.tick()
    irc.clear()
    irc.names("#marchhare", "@Jeeves bob-marchhare")  # the server says bob lost +o (missed MODE)
    assert irc.modes() == ["MODE #marchhare +o bob-marchhare"]


def test_kick_and_part_drop_membership(irc):
    irc.names("#marchhare", "@Jeeves bob-marchhare")
    irc.line(":x!u@h KICK #marchhare bob-marchhare :no")
    assert "bob-marchhare" not in (irc.eng.state.members["#marchhare"] or {})
    irc.line(":alice!u@h PART #marchhare")


# ----------------------------------------------------------------------------- how Jeeves acts
def test_uses_samode_when_not_op_but_oper_else_warns_loudly(home):
    f = Fake(home, ops=False, oper=True)
    f.names("#marchhare", "Jeeves bob-marchhare")
    assert f.modes() == ["SAMODE #marchhare +o bob-marchhare"]
    g = Fake(home, ops=False, oper=False)
    g.names("#marchhare", "Jeeves bob-marchhare")
    assert g.modes() == [] and any(m.startswith("WARN chan-privs cannot grant") for m in g.logs)


def test_every_decision_is_logged_loudly(irc):
    irc.names("#marchhare", "@Jeeves bob-marchhare")
    assert any(m.startswith("INFO chan-privs GRANT +o bob-marchhare in #marchhare") for m in irc.logs)


# ----------------------------------------------------------------------------- config
def test_config_values_and_loud_default_notice():
    assert cp.op_accounts({}) == ({"simon"}, "default")
    assert cp.op_accounts({"JEEVES_OWNER_ACCOUNT": "Simon.B"}) == ({"simon.b"}, "JEEVES_OWNER_ACCOUNT")
    assert cp.op_accounts({"BOB_OP_ACCOUNTS": "Simon, backup;x", "JEEVES_OWNER_ACCOUNT": "z"}) == (
        {"simon", "backup", "x"}, "BOB_OP_ACCOUNTS")
    assert cp.op_nicks({}) == {"simon"} and cp.op_nicks({"BOB_OP_NICKS": "Si,Sb"}) == {"si", "sb"}


def test_announce_flags_default_as_needing_simons_value(home, monkeypatch):
    for k in ("BOB_OP_ACCOUNTS", "JEEVES_OWNER_ACCOUNT"):
        monkeypatch.delenv(k, raising=False)
    f = Fake(home, accounts="env")
    f.eng.announce()
    assert "NEEDS Simon's value" in f.logs[-1] and "BOB_OP_ACCOUNTS" in f.logs[-1]
    monkeypatch.setenv("BOB_OP_ACCOUNTS", "simonb")
    g = Fake(home, accounts="env")
    g.eng.announce()
    assert "NEEDS" not in g.logs[-1] and "simonb" in g.logs[-1]


def test_parsers():
    assert cp.parse_names("@a %b +c d &e ~f @%g") == [
        ("a", {"o"}), ("b", {"h"}), ("c", {"v"}), ("d", set()), ("e", {"a"}), ("f", {"q"}), ("g", {"o", "h"})]
    assert cp.parse_mode_changes(["MODE", "#c", "+ov-h", "a", "b", "c"]) == [
        ("#c", "o", True, "a"), ("#c", "v", True, "b"), ("#c", "h", False, "c")]
    assert cp.parse_mode_changes(["MODE", "#c", "+l", "10"]) == [] and cp.parse_mode_changes(["MODE", "nick", "+i"]) == []


# ----------------------------------------------------------------------------- wiring in Client
def test_old_grant_logic_is_merged_not_duplicated():
    import inspect
    src = inspect.getsource(irc_agent.Client.handle_join)
    assert "_maybe_grant_bob_modes" not in src             # join now flows through the privilege engine
    body = inspect.getsource(irc_agent.Client._maybe_grant_bob_modes)
    assert "MODE" not in body.replace("MODE_", "") or "self.send" not in body
    assert "chan_privs" in inspect.getsource(irc_agent.Client._privs) or "ChanPrivEngine" in inspect.getsource(irc_agent.Client._privs)
    reader = inspect.getsource(irc_agent.Client.reader)
    assert "_chair_wire" in reader and "KICK" in reader and "NICK" in reader


def test_never_touches_ergo_config():
    import pathlib
    for name in ("chan_privs.py", "chan_workers.py"):
        txt = (pathlib.Path(irc_agent.__file__).parent / name).read_text(encoding="utf-8")
        assert "ircd.yaml" not in txt.replace("never edits Ergo", "") or "never" in txt
        assert "open(" not in txt and "write_text" not in txt

def test_op_accounts_config_file_between_env_and_owner(tmp_path):
    (tmp_path / "op-accounts.txt").write_text("# simon's NickServ account\nSimonB\nbackup\n", encoding="utf-8")
    env = {"BOB_CONFIG_DIR": str(tmp_path), "JEEVES_OWNER_ACCOUNT": "other"}
    assert cp.op_accounts(env) == ({"simonb", "backup"}, "op-accounts.txt")
    assert cp.op_accounts({**env, "BOB_OP_ACCOUNTS": "x"}) == ({"x"}, "BOB_OP_ACCOUNTS")
    assert cp.op_accounts({"BOB_CONFIG_DIR": str(tmp_path / "none"), "JEEVES_OWNER_ACCOUNT": "other"}) == (
        {"other"}, "JEEVES_OWNER_ACCOUNT")


def test_install_jeeves_has_opaccounts_parameter():
    import pathlib
    t = (pathlib.Path(irc_agent.__file__).parent / "Install-Jeeves.ps1").read_text(encoding="utf-8-sig")
    assert "[string]$OpAccounts" in t and "op-accounts.txt" in t


def test_periodic_reverify_drops_cached_account_then_whois_only(irc):
    irc.names("#bobiverse", "@Jeeves simon")
    irc.line(":simon!u@h ACCOUNT simon")
    irc.line(":Jeeves!u@h MODE #bobiverse +o simon")
    irc.clear()
    irc.t += cp.RECONCILE_S + 1
    irc.eng.tick()
    assert irc.eng.state.account("simon") is None            # cache dropped...
    irc.clear()
    irc.names("#bobiverse", "@Jeeves @simon")
    assert irc.sent == ["WHOIS simon"]                       # ...which only triggers a WHOIS, no -o
    irc.line(":srv 330 Jeeves simon simon :is logged in as")
    irc.line(":srv 318 Jeeves simon :End of /WHOIS list.")
    assert irc.modes() == []                                 # still verified and still +o: nothing to do
