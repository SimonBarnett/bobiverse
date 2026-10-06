"""Chair command surface = gh-Jeeves @8d76d9a parity (inventory, !help, authorization matrix, replies) via the real
Client methods on a fake chair. The ear (bob-<machine>) and the verified owner must both work."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import bob_recycle
import bobreport
import chair_commands as cc
import focus_ignore as fi
import gitclaim
import irc_agent
import registered_machines as rm

EAR = "Bob-win-mpre8vi4u6u"          # exactly as the live ear connects (capital B)
MH_EAR = "bob-marchhare"
CHANS = ["#bobiverse", "#marchhare", "#win-mpre8vi4u6u", "#flamingo"]

GH_JEEVES_COMMANDS = {"help", "list", "status", "resync", "sweep", "ignore", "ignored", "unignore",
                      "focus", "unfocus", "recycle"}          # gh-Jeeves/src/jeeves/commands.py @ 8d76d9a
OPS_ONLY = {"ignore", "unignore", "focus", "unfocus", "recycle", "resync", "sweep", "assign"}


class FakeChair:
    def __init__(self, home):
        self.args = SimpleNamespace(chair=True)
        self.home = home
        self.live_nick = self.original_nick = "Jeeves"
        self.channels = list(CHANS)
        self.sent, self.pms, self.said, self.logs = [], [], [], []
        self.joined = SimpleNamespace(is_set=lambda: True)
        self._chan_op = {c: True for c in CHANS}
        self._op_try_at = {}
        self._oper_state = "off"
        self._cs_force = False
        self.acct: dict = {}
        self.accounts = SimpleNamespace(get=lambda n: self.acct.get((n or "").lower()))
        self._digest_asm = SimpleNamespace(feed=lambda s, b: None)

    # --- plumbing the real methods call
    def send(self, line): self.sent.append(line)
    def whisper(self, nick, msg): self.pms.append((nick, msg))
    def say(self, msg): self.said.append(msg)
    def _digest_home(self): return self.home
    def _joined_channel(self, t): return t.lower() in {c.lower() for c in self.channels}
    def _mine_nicks(self): return {"jeeves"}
    def _note_call_channel(self, t): pass
    def _maybe_channel_pong(self, *a): return False
    def _maybe_shop_listen(self, *a): return False
    def _maybe_git_claim(self, *a): return False
    def _handle_register_command(self, *a): return False
    def _mark_pm_open(self, n): pass
    def _is_briefer(self): return False
    def _refresh_ledger(self): pass          # no GitHub lookups in unit tests

    for _n in ("handle_privmsg", "_maybe_chair_commands", "_maybe_git_list", "_maybe_git_help", "_maybe_focus_ignore", "_maybe_assign", "_git_say",
               "_handle_recycle_command", "_handle_bob_local_recycle_command", "_maybe_startworker", "_cc", "_ear_machine", "_account_of",
               "_principal", "_jobs", "_jobs_status_lines", "_whois_hint", "_cmd_trace", "_cmd_reply", "_privs", "_privs_skip_whois",
               "_on_channel_names", "_workers"):
        locals()[_n] = getattr(irc_agent.Client, _n)
    del _n

    def to(self, nick):
        return [m for n, m in self.pms if n.lower() == nick.lower()]


@pytest.fixture
def chair(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "win-mpre8vi4u6u")
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS", "BOB_OP_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    rm.sync_from_chanserv(tmp_path, CHANS)
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    c = FakeChair(tmp_path)
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    monkeypatch.setattr(irc_agent.time, "sleep", lambda s: None)
    c.recycled = []
    monkeypatch.setattr(bob_recycle, "execute_local_recycle", lambda mid, home, **k: c.recycled.append(mid))
    import agent_control
    monkeypatch.setattr(agent_control, "request_agent_quit", lambda *a, **k: c.recycled.append("quit"))
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), {"v": 1, "accepted": [], "unaccepted": [
        # FR #2730: stamp open + issues URL so offline structural FR #2340 checks stay green.
        {"repo": "o/a", "task": "FR", "id": "#1", "seq": 1, "ts": "2026-10-01T10:00:01Z", "line": "x",
         "title": "fr one", "state": "open", "event": "issues",
         "url": "https://github.com/o/a/issues/1"},
        {"repo": "o/b", "task": "MRB", "id": "#2", "seq": 2, "ts": "2026-10-01T10:00:02Z", "line": "x",
         "title": "mrb two", "url": "https://github.com/o/b/pull/2"},
    ]})
    return c


def pm(c, nick, body, to="Jeeves"):
    c.pms.clear(), c.sent.clear(), c.said.clear()
    c.handle_privmsg(f":{nick}!u@h", to, body)
    return c.to(nick)


def chan(c, nick, body, ch="#bobiverse"):
    c.pms.clear(), c.sent.clear(), c.said.clear()
    c.handle_privmsg(f":{nick}!u@h", ch, body)
    return c.to(nick)


# ------------------------------------------------------------------ inventory
def test_registry_is_valid_and_has_every_gh_jeeves_command():
    assert cc.validate_registry() == []
    names = {c.name for c in cc.COMMANDS}
    assert GH_JEEVES_COMMANDS <= names
    assert {"filter", "ping"} <= names


def test_help_lists_every_command_for_owner_and_ear(chair):
    chair.acct["simon"] = "simon"
    for nick in ("simon", EAR):
        lines = pm(chair, nick, "!help")
        text = "\n".join(lines)
        for name in cc.COMMAND_BY_NAME:
            assert (f"!{name}" in text) or (name == "ping" and "ping [nick-glob]" in text), (nick, name)
        assert lines[-1].startswith("note: !bored")
        assert all(len(l.encode()) <= 400 for l in lines)


def test_help_for_strangers_hides_ops_commands(chair):
    lines = pm(chair, "mallory", "!help")
    heads = {l.split(" ")[0] for l in lines}
    for name in OPS_ONLY:
        assert f"!{name}" not in heads, name
    assert {"!list", "!status", "!ignored", "!help"} <= heads
    assert pm(chair, "mallory2", "!help recycle") == ["unknown command; try !help"]


def test_help_detail_and_rate_limit_and_channel_reply_is_pm_only(chair):
    d = pm(chair, EAR, "!help recycle")
    assert d[0].startswith("syntax: !recycle") and len(d) <= 5
    assert pm(chair, EAR, "!help recycle")[0].startswith("rate limit: wait")
    chair.pms.clear()
    out = chan(chair, MH_EAR, "!help")
    assert out and not chair.said and not any(s.startswith("PRIVMSG #") for s in chair.sent)


# ------------------------------------------------------------------ authorization matrix
@pytest.mark.parametrize("nick,acct,kind", [
    ("simon", "simon", "owner"), ("Simon", "simon", "owner"), ("laptop", "simon", "owner"),
    ("simon", None, "none"), ("simon-pc", "mallory", "none"),
    (EAR, None, "ear"), (EAR, "bob-win-mpre8vi4u6u", "ear"), (MH_EAR, None, "ear"),
    ("bob-nosuchbox", None, "none"), ("bob-marchhare_", None, "none"), (EAR, "mallory", "none"),
    ("mallory", None, "none"),
])
def test_classify(chair, nick, acct, kind):
    chair.acct[nick.lower()] = acct or ""
    assert chair._principal(nick).kind == kind


def test_allowlist_env_is_focus_only(chair, monkeypatch):
    monkeypatch.setenv("JEEVES_FOCUS_MUTATORS", "ops-ear")
    assert pm(chair, "ops-ear", "!focus high o/a")[0].startswith("focus: o/a")
    assert pm(chair, "ops-ear", "!ignore o/a")[0].startswith("ignore: denied")
    assert pm(chair, "ops-ear", "!recycle dry-run")[0].startswith("recycle: denied")


@pytest.mark.parametrize("body,deny", [
    ("!ignore o/x", "ignore: denied (simon or bob-* ops only)"),
    ("!unignore o/x", "unignore: denied (simon or bob-* ops only)"),
    ("!focus high o/x", "focus: denied (owner account required)"),
    ("!unfocus all", "unfocus: denied (owner account required)"),
    ("!recycle marchhare", "recycle: denied (authorised operator + services account required)"),
    ("!recycle", "recycle: denied (authorised operator + services account required)"),
    ("!resync", "resync: denied (simon or bob-* ops only)"),
    ("!sweep #bobiverse", "sweep: denied (simon or bob-* ops only)"),
])
def test_strangers_and_unverified_simon_are_denied_and_nothing_is_sent(chair, body, deny):
    for nick in ("mallory", "simon", "bob-nosuchbox"):
        assert pm(chair, nick, body)[0] == deny
        assert not [s for s in chair.sent if s.startswith(("PRIVMSG", "MODE", "SAMODE", "NAMES"))]
    assert fi.load_focus(chair.home)["repos"] == {} and fi.ignored_list(chair.home) == []


def test_denied_owner_nick_triggers_a_whois_to_learn_the_account(chair):
    pm(chair, "simon", "!focus high o/x")
    assert "WHOIS simon" in chair.sent


# ------------------------------------------------------------------ every command, as the ear AND as Simon
@pytest.fixture(params=[EAR, "simon"])
def op(request, chair):
    chair.acct["simon"] = "simon"
    return request.param


def test_list_and_filter_reply_by_pm_only(chair, op):
    allrows = pm(chair, op, "!list")
    assert any("o/a" in l for l in allrows) and any("o/b" in l for l in allrows)
    gitclaim.reset_list_rate()
    fr = chan(chair, op, "!filter fr")
    assert any("o/a" in l for l in fr) and not any("o/b" in l for l in fr)
    assert not chair.said
    assert chair.to(op)


def test_status(chair, op):
    lines = pm(chair, op, "!status")
    assert lines[0].startswith("Jeeves status: version=") and "uptime_s=" in lines[0]
    assert lines[1] == "queue: unaccepted=2 accepted=0"
    assert any(l.startswith("roster: machines=") for l in lines)


def test_ping_pm(chair, op):
    assert pm(chair, op, "ping") == ["pong"]
    assert pm(chair, op, "ping jeev*") == ["pong"]
    assert pm(chair, op, "ping marchhare") == []


def test_resync(chair, op):
    out = pm(chair, op, "!resync")
    assert out[0].startswith("resync: roster refresh requested; GitHub FR/MRB re-sync queued")
    assert "queue unaccepted=2 accepted=0" in out[0]
    assert chair._jobs().next_resync == 0.0      # picked up on the next tick
    assert chair._cs_force is True


def test_sweep_replans_and_asks_for_names(chair, op):
    out = pm(chair, op, "!sweep #bobiverse")
    assert out[0].startswith("sweep: #bobiverse re-planned")
    assert "NAMES #bobiverse" in chair.sent
    assert pm(chair, op, "!sweep #nowhere")[0] == "sweep: not in #nowhere"
    assert pm(chair, op, "!sweep")[0].startswith("sweep: #bobiverse")


def test_ignore_family(chair, op):
    assert pm(chair, op, "!ignore o/a")[0] == "ignore: now ignoring o/a (purged 1 queued)"
    assert pm(chair, op, "!ignored") == ["ignored (1):", "  o/a"]
    assert pm(chair, op, "!ignore") == ["ignore: usage !ignore {repo}"]
    assert pm(chair, "mallory", "!ignored") == ["ignored (1):", "  o/a"]            # reads are open
    assert pm(chair, op, "!unignore o/a")[0] == "unignore: resumed o/a (new events only)"
    assert pm(chair, op, "!ignored") == ["ignored: (none)"]


def test_focus_family(chair, op):
    assert pm(chair, op, "!focus high o/b")[0] == "focus: o/b priority=1 (high)"
    assert pm(chair, op, "!focus strict on") == ["focus strict: on"]
    assert pm(chair, "mallory", "!focus")[0] == "focus strict: on"                  # read is open
    assert pm(chair, op, "!focus o/a#1")[0].startswith("focus: item o/a#1")
    assert pm(chair, op, "!unfocus o/b")[0] == "unfocus: removed o/b"
    assert pm(chair, op, "!unfocus all")[0].startswith("unfocus: cleared")
    assert pm(chair, op, "!unfocus") == ["unfocus: usage !unfocus {repo|repo#N}|all"]


def test_recycle_dry_run_authorises_and_sends_nothing(chair, op):
    out = pm(chair, op, "!recycle dry-run")
    assert out[0].startswith("recycle dry-run: would recycle fleet (fleet)")
    out = pm(chair, op, "!recycle dry-run marchhare")
    assert out[0].startswith("recycle dry-run: would recycle marchhare (local)")
    assert not [s for s in chair.sent if s.startswith("PRIVMSG")] and chair.recycled == []


def test_recycle_unknown_machine_is_refused(chair, op):
    out = pm(chair, op, "!recycle nosuchbox")
    assert out == ["recycle: unknown machine nosuchbox (want: " + ", ".join(
        bobreport.roster_machine_ids(chair.home)) + ", all)"]
    assert chair.sent == []


def test_recycle_one_machine_routes_a_wire_to_the_fleet_channel_with_cooldown(chair, op):
    out = pm(chair, op, "!recycle marchhare")
    assert out[0] == "Recycling marchhare." and "routed to bob seat(s) (local marchhare)" in out[1]
    assert chair.sent == ["PRIVMSG #bobiverse :RECYCLE v1 marchhare"]
    assert pm(chair, op, "!recycle marchhare")[0].startswith("recycle: cooldown ")
    assert chair.sent == []


def test_recycle_bare_and_all_route_fleet(chair, op):
    out = pm(chair, op, "!recycle")
    assert out[0].startswith("Recycling all seats (") and "routed to bob seat(s) (fleet fleet)" in out[1]
    assert len(chair.sent) == 1 and chair.sent[0].startswith("PRIVMSG #bobiverse :RECYCLE machine=fleet by=")
    assert chair.sent[0].endswith("scope=fleet exec=local-bob-seat")
    assert bob_recycle.parse_jeeves_recycle_route(chair.sent[0].split(" :", 1)[1]) == ("fleet", "fleet")
    assert pm(chair, op, "!recycle all")[0].startswith("recycle: cooldown")


def test_recycle_chair_machine_runs_local_and_jeeves_departs(chair, op):
    pm(chair, op, "!recycle win-mpre8vi4u6u")
    assert chair.recycled == ["win-mpre8vi4u6u", "quit"] and chair.sent == []
    chair.recycled.clear()
    pm(chair, op, "!recycle jeeves")
    assert chair.recycled == ["quit"] and chair.said == ["Jeeves departing (recycle)"]


def test_commands_work_from_a_channel_too_and_reply_in_pm(chair, op):
    for body in ("!status", "!ignored", "!focus", "!recycle dry-run", "!resync"):
        out = chan(chair, op, body, "#win-mpre8vi4u6u")
        assert out, body
        assert not chair.said and not any(s.startswith("PRIVMSG #") for s in chair.sent), body


def test_replies_are_traced_for_audit(chair):
    pm(chair, EAR, "!status")
    t = (chair.home / "cmd-trace.log").read_text("utf-8")
    assert "\t" + EAR + "\tstatus\tJeeves status: version=" in t


def test_ear_bare_recycle_is_left_to_the_chair_route():
    t = (irc_agent.Path(irc_agent.__file__).read_text("utf-8-sig"))
    assert 'if kind == "refuse" and machine_id is None:' not in t

# ------------------------------------------------------------------ !assign (t849u)
def test_assign_owner_and_ear_post_normal_line_as_jeeves(chair, monkeypatch):
    # FR #2730: with a live GH token, issue_open(o/a#1) 404s and refuses; stub checkers.
    monkeypatch.setattr(gitclaim, "github_is_pull_checker", lambda **k: (lambda r, n: False))
    monkeypatch.setattr(gitclaim, "github_issue_open_checker", lambda **k: (lambda r, n: True))
    monkeypatch.setattr(gitclaim, "github_pr_exists_checker", lambda **k: (lambda r, n: True))
    chair.acct["simon"] = "simon"
    out = pm(chair, "simon", "!assign marchhare-41928 o/a FR 1")
    assert out == ["assign: sent marchhare-41928: FR o/a#1 https://github.com/o/a/issues/1"], out
    assert chair.sent[-1] == "PRIVMSG #marchhare :marchhare-41928: FR o/a#1 https://github.com/o/a/issues/1"
    # ACK in the shop accepts it (same path as !bored)
    st, job = gitclaim.accept_offered(chair.home, "marchhare-41928", "#marchhare")
    assert st == "ok" and job["id"] == "#1"
    # the Bob-* ear can do it too, from the channel; reply stays a PM
    out = chan(chair, EAR, "!assign marchhare-5 o/b MRB 2")
    assert chair.said == [] and out and out[0].startswith("assign: ")


def test_assign_denied_for_strangers_and_bad_usage(chair):
    out = pm(chair, "mallory", "!assign marchhare-41928 o/a FR 1")
    assert out[0].startswith("assign: denied")
    assert not any(s.startswith("PRIVMSG #marchhare") for s in chair.sent)
    chair.acct["simon"] = "simon"
    assert pm(chair, "simon", "!assign marchhare-41928 o/a")[0].startswith("assign: usage")
    assert pm(chair, "simon", "!assign Jeeves o/a FR 1")[0].startswith("assign: refused")
    assert not any(s.startswith("PRIVMSG #") for s in chair.sent)


def test_assign_refuses_busy_and_unknown_rows(chair, monkeypatch):
    chair.acct["simon"] = "simon"
    assert pm(chair, "simon", "!assign marchhare-9 o/a FR 77")[0].startswith("assign: refused")
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "doing FR o/zzz#1")
    assert "busy" in pm(chair, "simon", "!assign marchhare-9 o/a FR 1")[0]
    assert not any(s.startswith("PRIVMSG #marchhare") for s in chair.sent)

def test_help_lists_assign_with_usage_and_rules(chair):
    chair.acct["simon"] = "simon"
    for nick in ("simon", EAR):
        text = "\n".join(pm(chair, nick, "!help"))
        assert "!assign {worker-nick} {repo} {FR|MRB|UAT} {num}" in text, nick
    detail = pm(chair, MH_EAR, "!help assign")
    blob = "\n".join(detail)
    assert detail[0].startswith("syntax: !assign")
    assert "self-MRB/UAT" in blob and "idle" in blob and "simon" in blob
    # strangers do not see it
    assert not any(l.startswith("!assign") for l in pm(chair, "mallory", "!help"))

def test_fr2730_assign_refuses_when_issue_open_says_closed(chair, monkeypatch):
    # FR #2730: chair !assign path must refuse CLOSED FRs via live issue_open (FR #2340).
    monkeypatch.setattr(gitclaim, "github_is_pull_checker", lambda **k: (lambda r, n: False))
    monkeypatch.setattr(gitclaim, "github_issue_open_checker", lambda **k: (lambda r, n: False))
    monkeypatch.setattr(gitclaim, "github_pr_exists_checker", lambda **k: (lambda r, n: True))
    chair.acct["simon"] = "simon"
    out = pm(chair, "simon", "!assign marchhare-41928 o/a FR 1")
    assert out and out[0].startswith("assign: refused"), out
    assert "CLOSED" in out[0] or "pull" in out[0].lower(), out
    assert not any(s.startswith("PRIVMSG #marchhare") for s in chair.sent)


def test_fr2730_assign_refuses_when_is_pull_true(chair, monkeypatch):
    # FR #2730: chair !assign path must refuse FR rows that are actually pulls.
    monkeypatch.setattr(gitclaim, "github_is_pull_checker", lambda **k: (lambda r, n: True))
    monkeypatch.setattr(gitclaim, "github_issue_open_checker", lambda **k: (lambda r, n: True))
    monkeypatch.setattr(gitclaim, "github_pr_exists_checker", lambda **k: (lambda r, n: True))
    chair.acct["simon"] = "simon"
    out = pm(chair, "simon", "!assign marchhare-41928 o/a FR 1")
    assert out and out[0].startswith("assign: refused"), out
    assert "pull" in out[0].lower() or "CLOSED" in out[0], out
    assert not any(s.startswith("PRIVMSG #marchhare") for s in chair.sent)
