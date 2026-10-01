"""Chair-side channel privilege rules (v0.1.18). Deterministic, token-less, never edits Ergo.

Enforced by Jeeves (the chair) on every JOIN, on MODE drift and on a periodic reconcile (NAMES):

1. Jeeves holds +o in #bobiverse and every machine channel (``Client._ensure_chan_ops``).
2. Each registered machine's ear ``bob-<machine>`` gets +o in its OWN ``#<machine>`` channel and
   +h in #bobiverse.
3. Simon gets +o ONLY while logged in to a NickServ account listed in ``BOB_OP_ACCOUNTS``
   (default: ``JEEVES_OWNER_ACCOUNT``, else ``simon`` - the account the focus/ignore owner rule
   already uses). The account must be learned THIS SESSION from the wire (extended-join, account-notify,
   account-tag or WHOIS 330); the persisted accounts.json is never trusted for ops. A nick alone
   NEVER earns ops: a nick in ``BOB_OP_NICKS`` (default ``simon``) that holds +o without a verified
   account is de-opped; an account not yet known is looked up (WHOIS) and nothing is granted meanwhile.

``PrivState``/``plan`` are pure; ``ChanPrivEngine`` turns wire events into the MODE/WHOIS/NAMES lines
to send (sockets and clock are injected, so it is testable with a fake IRC).
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

OP_ACCOUNTS_ENV = "BOB_OP_ACCOUNTS"
OP_NICKS_ENV = "BOB_OP_NICKS"
OWNER_ACCOUNT_ENV = "JEEVES_OWNER_ACCOUNT"
DEFAULT_OWNER_ACCOUNT = "simon"
FLEET_CHANNEL = "#bobiverse"

PREFIX_MODE = {"~": "q", "&": "a", "@": "o", "%": "h", "+": "v"}
MODE_RANK = {"q": 5, "a": 4, "o": 3, "h": 2, "v": 1}

RECONCILE_S = 60.0       # periodic NAMES per channel
WHOIS_BATCH = 5          # max WHOIS per decision pass (flood safety)
RESEND_S = 20.0          # never repeat the same MODE/WHOIS sooner than this
BACKOFF_MAX_S = 600.0    # per (kind,chan,nick,mode) the gap between repeated MODEs doubles up to this ...
BACKOFF_DECAY_S = 900.0  # ... and drops back to RESEND_S after this long without a send
UNCONFIRMED_WARN = 3     # WARN once when this many sends for one key were never reflected in NAMES/MODE


# Characters that must never be part of a nick or a config token: BOM, zero-width/format chars, NBSP.
_JUNK = "\ufeff\u200b\u200c\u200d\u2060\u00a0\x00"
_JUNK_TABLE = {ord(c): None for c in _JUNK}


def clean(raw) -> str:
    """Strip BOM / zero-width chars and surrounding whitespace (nicks, channels, config values)."""
    return str(raw if raw is not None else "").translate(_JUNK_TABLE).strip()


def clean_nick(raw) -> str:
    """A bare nick/token: ``clean`` plus a leading ``:`` (IRC trailing marker)."""
    return clean(clean(raw).lstrip(":"))


def _csv(raw: str) -> set[str]:
    return {t.strip().lower() for t in clean(raw).replace(";", ",").replace(" ", ",").split(",") if t.strip()}


OP_ACCOUNTS_FILE = "op-accounts.txt"     # <BOB_CONFIG_DIR>/op-accounts.txt, survives service re-installs


def _config_file_accounts(env) -> set[str]:
    base = (env.get("BOB_CONFIG_DIR") or "").strip()
    if not base:
        return set()
    try:
        from pathlib import Path

        raw = (Path(base) / OP_ACCOUNTS_FILE).read_text(encoding="utf-8-sig")
    except OSError:
        return set()
    return _csv("\n".join(ln.split("#", 1)[0] for ln in raw.splitlines()).replace("\n", ","))


def op_accounts(environ: dict | None = None) -> tuple[set[str], str]:
    """(accounts that may be opped, source label) - the label is logged loudly at startup.

    Order: env ``BOB_OP_ACCOUNTS`` > ``<config>/op-accounts.txt`` > ``JEEVES_OWNER_ACCOUNT`` > default ``simon``."""
    env = os.environ if environ is None else environ
    explicit = _csv(env.get(OP_ACCOUNTS_ENV, ""))
    if explicit:
        return explicit, OP_ACCOUNTS_ENV
    filed = _config_file_accounts(env)
    if filed:
        return filed, OP_ACCOUNTS_FILE
    owner = _csv(env.get(OWNER_ACCOUNT_ENV, ""))
    if owner:
        return owner, OWNER_ACCOUNT_ENV
    return {DEFAULT_OWNER_ACCOUNT}, "default"


def op_nicks(environ: dict | None = None) -> set[str]:
    env = os.environ if environ is None else environ
    return _csv(env.get(OP_NICKS_ENV, "")) or {DEFAULT_OWNER_ACCOUNT}


def rank_of(modes: set[str]) -> int:
    return max((MODE_RANK.get(m, 0) for m in modes), default=0)


def parse_names(trailing: str) -> list[tuple[str, set[str]]]:
    """``@a %b +c d`` -> [(a,{o}), (b,{h}), (c,{v}), (d,set())] (multi-prefix aware)."""
    out: list[tuple[str, set[str]]] = []
    for tok in clean(trailing).split():
        tok = clean(tok)
        modes: set[str] = set()
        while tok and tok[0] in PREFIX_MODE:
            modes.add(PREFIX_MODE[tok[0]])
            tok = tok[1:]
        if "!" in tok:  # userhost-in-names
            tok = tok.split("!", 1)[0]
        tok = clean_nick(tok)
        if tok:
            out.append((tok, modes))
    return out


def parse_mode_changes(parts: list[str]) -> list[tuple[str, str, bool, str]]:
    """``MODE #chan +ov a b`` -> [(chan,'o',True,'a'), (chan,'v',True,'b')] (member modes only)."""
    if len(parts) < 3 or not clean(parts[1]).startswith("#"):
        return []
    chan = clean(parts[1])
    modestr = clean_nick(parts[2])
    args = [clean_nick(a) for a in parts[3:]]
    out: list[tuple[str, str, bool, str]] = []
    add = True
    ai = 0
    for ch in modestr:
        if ch == "+":
            add = True
        elif ch == "-":
            add = False
        elif ch in "ovhaqbeIk" or (add and ch in "lf"):
            arg = args[ai] if ai < len(args) else ""
            ai += 1
            if ch in "ovhaq" and arg:
                out.append((chan, ch, add, arg))
    return out


@dataclass
class Action:
    kind: str       # grant | revoke
    chan: str
    nick: str
    mode: str
    reason: str


@dataclass
class PrivState:
    members: dict = field(default_factory=dict)    # chan_l -> nick_l -> {"nick", "modes"}
    pending: dict = field(default_factory=dict)    # NAMES being collected
    accts: dict = field(default_factory=dict)      # nick_l -> account verified THIS session
    acct_none: set = field(default_factory=set)    # nick_l known NOT logged in (this session)

    def names_chunk(self, chan: str, trailing: str) -> None:
        pend = self.pending.setdefault(clean(chan).lower(), {})
        for nick, modes in parse_names(trailing):
            pend[nick.lower()] = {"nick": nick, "modes": set(modes)}

    def names_end(self, chan: str) -> set | None:
        chan = clean(chan)
        pend = self.pending.pop(chan.lower(), None)
        if pend is None:
            return None
        self.members[chan.lower()] = pend
        return {v["nick"] for v in pend.values()}

    def join(self, chan: str, nick: str) -> None:
        chan, nick = clean(chan), clean_nick(nick)
        self.members.setdefault(chan.lower(), {}).setdefault(nick.lower(), {"nick": nick, "modes": set()})

    def part(self, chan: str, nick: str) -> None:
        chan, nick = clean(chan), clean_nick(nick)
        self.members.get(chan.lower(), {}).pop(nick.lower(), None)
        if not any(nick.lower() in m for m in self.members.values()):
            self.forget_account(nick)

    def quit(self, nick: str) -> list:
        nick = clean_nick(nick)
        gone = [ch for ch, m in self.members.items() if m.pop(nick.lower(), None) is not None]
        self.forget_account(nick)
        return gone

    def rename(self, old: str, new: str) -> list:
        old, new = clean_nick(old), clean_nick(new)
        moved = []
        for ch, m in self.members.items():
            ent = m.pop(old.lower(), None)
            if ent is not None:
                ent["nick"] = new
                m[new.lower()] = ent
                moved.append(ch)
        acct = self.accts.pop(old.lower(), None)
        if acct is not None:
            self.accts[new.lower()] = acct
        if old.lower() in self.acct_none:
            self.acct_none.discard(old.lower())
            self.acct_none.add(new.lower())
        return moved

    def mode(self, chan: str, mode: str, add: bool, nick: str) -> None:
        chan, nick = clean(chan), clean_nick(nick)
        ent = self.members.setdefault(chan.lower(), {}).setdefault(nick.lower(), {"nick": nick, "modes": set()})
        (ent["modes"].add if add else ent["modes"].discard)(mode)

    def set_account(self, nick: str, account: str | None) -> None:
        nick, account = clean_nick(nick), (clean(account) if account is not None else None)
        n = nick.lower()
        if account and account != "*":
            self.accts[n] = account
            self.acct_none.discard(n)
        else:
            self.accts.pop(n, None)
            self.acct_none.add(n)

    def forget_account(self, nick: str) -> None:
        self.accts.pop(nick.lower(), None)
        self.acct_none.discard(nick.lower())

    def account(self, nick: str) -> str | None:
        return self.accts.get(clean_nick(nick).lower())

    def reset(self) -> None:
        self.members.clear()
        self.pending.clear()
        self.accts.clear()
        self.acct_none.clear()


def bob_machine(nick: str, is_registered: Callable[[str], bool], normalize: Callable[[str], str | None]) -> str | None:
    """Machine id for the ear nick ``bob-<machine>`` of a registered machine, else None.
    ``bob-<machine>_`` style fallback nicks (reserved nick owned by another account) are NOT ears."""
    n = clean_nick(nick)
    if not n.lower().startswith("bob-"):
        return None
    mid = normalize(clean(n[4:]))
    if not mid or not is_registered(mid):
        return None
    return mid


def plan(
    state: PrivState,
    chan: str,
    *,
    me: str,
    accounts: set,
    nicks: set,
    is_registered: Callable[[str], bool],
    normalize: Callable[[str], str | None],
    skip_whois: Callable[[str], bool] = lambda n: False,
    owner_granted: set | None = None,
) -> tuple[list, list]:
    """(actions, whois_nicks) the chair needs in ``chan`` right now. Pure."""
    acts: list[Action] = []
    whois: list[str] = []
    chan, me = clean(chan), clean_nick(me)
    members = state.members.get(chan.lower())
    if not members:
        return acts, whois
    cl = chan.lower()
    for nl, ent in sorted(members.items()):
        nick = ent["nick"]
        if nl == me.lower():
            continue
        rank = rank_of(ent["modes"])
        mid = bob_machine(nick, is_registered, normalize)
        if mid:
            if cl == f"#{mid}" and rank < MODE_RANK["o"]:
                acts.append(Action("grant", chan, nick, "o", f"bob-{mid} ear is ops in its own channel"))
            elif cl == FLEET_CHANNEL and rank < MODE_RANK["h"]:
                acts.append(Action("grant", chan, nick, "h", f"bob-{mid} ear is half-op in {FLEET_CHANNEL}"))
            continue
        acct = state.account(nick)
        if acct and acct.lower() in accounts:
            if rank < MODE_RANK["o"]:
                acts.append(Action("grant", chan, nick, "o", f"verified NickServ account {acct}"))
            continue
        was_ours = nl in (owner_granted or ())
        if nl not in nicks and not was_ours:
            # any other human may be Simon on another nick: learn the account (never grants on nick)
            if acct is None and nl not in state.acct_none and not skip_whois(nick):
                whois.append(nick)
            continue
        # candidate nick for the owner but NOT verified: never grant; de-op if it holds +o.
        if acct is None and nl not in state.acct_none:
            whois.append(nick)
            continue
        if rank >= MODE_RANK["o"] and "o" in ent["modes"] and (nl in nicks or was_ours):
            why = "not logged in" if acct is None else f"logged in as {acct}, not an op account"
            acts.append(Action("revoke", chan, nick, "o", f"{nick} holds +o but is {why}"))
    return acts, whois


class ChanPrivEngine:
    """Wire events in, MODE/WHOIS/NAMES lines out. ``chan_op(chan)`` says whether Jeeves has +o there."""

    def __init__(
        self,
        *,
        send: Callable[[str], None],
        log: Callable[[str], None],
        now: Callable[[], float],
        me: Callable[[], str],
        channels: Callable[[], list],
        is_registered: Callable[[str], bool],
        normalize: Callable[[str], str | None],
        chan_op: Callable[[str], bool],
        is_oper: Callable[[], bool] = lambda: False,
        accounts: set | None = None,
        nicks: set | None = None,
        on_names: Callable[[str, set], None] | None = None,
        skip_whois: Callable[[str], bool] = lambda n: False,
    ) -> None:
        self.skip_whois = skip_whois
        self.send, self.log, self.now, self.me = send, log, now, me
        self.channels, self.is_registered, self.normalize = channels, is_registered, normalize
        self.chan_op, self.is_oper, self.on_names = chan_op, is_oper, on_names
        if accounts is None:
            accounts, self.accounts_source = op_accounts()
        else:
            self.accounts_source = "explicit"
        self.accounts = set(accounts)
        self.nicks = op_nicks() if nicks is None else set(nicks)
        self.lock = threading.RLock()      # reader thread (on_line) vs outbox thread (tick)
        self.state = PrivState()
        self.owner_granted: set = set()    # nicks THIS chair opped for a verified account (revoked on logout)
        self._sent: dict = {}
        self._bo: dict = {}         # (kind,chan_l,nick_l,mode) -> {"last","wait","n","warned"} backoff / unconfirmed count
        self._whois: dict = {}      # nick_l -> got 330?
        self._last_names = 0.0
        self.sent_lines: list[str] = []

    # -- logging --------------------------------------------------------------------
    def announce(self) -> None:
        src = self.accounts_source
        note = ""
        if src == "default":
            note = f" (NEEDS Simon's value: set {OP_ACCOUNTS_ENV}=<his NickServ account>; assuming the default)"
        self.log(
            f"INFO chan-privs rules: jeeves +o everywhere; bob-<machine> +o own #channel / +h {FLEET_CHANNEL}; "
            f"ops only for verified account(s) {','.join(sorted(self.accounts))} [source {src}]{note}; "
            f"candidate nick(s) {','.join(sorted(self.nicks))}; never granted on nick alone"
        )

    def reset(self) -> None:
        self.state.reset()
        self.owner_granted.clear()
        self._sent.clear()
        self._bo.clear()
        self._whois.clear()
        self._last_names = 0.0

    # -- wire -------------------------------------------------------------------------
    def on_line(self, cmd: str, parts: list, trailing: str, prefix: str = "", tags: dict | None = None) -> None:
        with self.lock:
            self._on_line(cmd, parts, trailing, prefix, tags)

    def _on_line(self, cmd: str, parts: list, trailing: str, prefix: str = "", tags: dict | None = None) -> None:
        who = clean_nick(prefix.split("!", 1)[0]) if prefix else ""
        parts = [clean(p) for p in parts]
        trailing = clean(trailing)
        tags = tags or {}
        st = self.state
        if cmd == "353":
            chan = next((p for p in parts[2:5] if p.startswith("#")), "")
            if chan:
                st.names_chunk(chan, trailing)
        elif cmd == "366":
            chan = next((p for p in parts[2:4] if p.startswith("#")), "")
            present = st.names_end(chan) if chan else None
            if present is not None:
                if self.on_names:
                    self.on_names(chan, present)
                self.apply(chan, "reconcile")
        elif cmd == "JOIN" and who:
            chan = (parts[1] if len(parts) > 1 else trailing).lstrip(":")
            if chan.startswith("#"):
                if who.lower() not in st.members.get(chan.lower(), {}):
                    self._fresh(chan, who)      # a genuinely new arrival is a new situation, not a retry
                st.join(chan, who)
                # extended-join: JOIN #chan <account|*> :realname
                if len(parts) >= 3 and not parts[2].startswith("#") and "account" not in tags:
                    st.set_account(who, parts[2].lstrip(":"))
                elif "account" in tags:
                    st.set_account(who, tags.get("account") or "*")
                self.apply(chan, "join")
        elif cmd == "PART" and who:
            chan = (parts[1] if len(parts) > 1 else trailing).lstrip(":")
            st.part(chan, who)
        elif cmd == "KICK" and len(parts) > 2:
            st.part(parts[1], parts[2].lstrip(":"))
        elif cmd == "QUIT" and who:
            st.quit(who)
        elif cmd == "NICK" and who:
            new = (parts[1] if len(parts) > 1 else trailing).lstrip(":")
            if new:
                for ch in st.rename(who, new):
                    self.apply(ch, "nick")
        elif cmd == "ACCOUNT" and who:
            acct = (parts[1] if len(parts) > 1 else trailing).lstrip(":")
            if st.account(who) != (acct if acct not in ("", "*") else None):
                for ch in list(st.members):
                    self._fresh(ch, who)         # a login/logout is a new situation: its grant/revoke is not a retry
            st.set_account(who, acct)
            if acct in ("", "*"):
                self.log(f"INFO chan-privs {who} logged out")
            for ch, m in list(st.members.items()):
                if who.lower() in m:
                    self.apply(ch, "account")
        elif cmd == "PRIVMSG" and who and "account" in tags:
            if st.account(who) != (tags.get("account") or None):
                st.set_account(who, tags.get("account") or "*")
        elif cmd == "MODE" and len(parts) > 2 and parts[1].startswith("#"):
            touched = set()
            for chan, mode, add, nick in parse_mode_changes(parts):
                st.mode(chan, mode, add, nick)
                touched.add(chan)
                self._confirm(chan, nick, mode, add)
            # Our own MODE (or a server-sourced SAMODE) is the echo of what we just asked for: record it
            # (above) but never re-plan on it - that was the grant/echo feedback loop.
            if not self._is_self(who):
                for chan in touched:
                    self.apply(chan, "mode-drift")
        elif cmd == "330" and len(parts) >= 4:
            nick, acct = parts[2], parts[3]
            if nick.lower() in self._whois:
                self._whois[nick.lower()] = True
            st.set_account(nick, acct)
            for ch, m in list(st.members.items()):
                if nick.lower() in m:
                    self.apply(ch, "whois")
        elif cmd == "318" and len(parts) >= 3:
            nick = parts[2]
            got = self._whois.pop(nick.lower(), None)
            if got is False:
                st.set_account(nick, None)
                for ch, m in list(st.members.items()):
                    if nick.lower() in m:
                        self.apply(ch, "whois")

    def _fresh(self, chan: str, nick: str) -> None:
        """(Re)joined / renamed: drop that nick's backoff so its first grant is not delayed by an old one."""
        c, n = clean(chan).lower(), clean_nick(nick).lower()
        for k in [k for k in self._bo if k[1] == c and k[2] == n]:
            self._bo.pop(k, None)
            self._sent.pop(k, None)

    def _is_self(self, who: str) -> bool:
        who = clean_nick(who)
        return bool(who) and (who.lower() == clean_nick(self.me()).lower() or ("." in who and "!" not in who))

    def _confirm(self, chan: str, nick: str, mode: str, add: bool) -> None:
        """A MODE line reflects a grant/revoke we sent: log the change once and reset its backoff."""
        key = ("grant" if add else "revoke", clean(chan).lower(), clean_nick(nick).lower(), mode)
        ent = self._bo.get(key)
        if ent is not None and ent.get("n", 0):
            # keep the (decaying) gap so something else flapping the mode cannot make us re-send every 20 s
            ent["n"], ent["warned"] = 0, False
            self.log(f"INFO chan-privs confirmed {'+' if add else '-'}{mode} {clean_nick(nick)} in {clean(chan)}")

    # -- decisions ----------------------------------------------------------------------
    def apply(self, chan: str, why: str) -> list:
        chan = clean(chan)
        if not chan.startswith("#"):
            return []
        acts, whois = plan(
            self.state, chan, me=self.me(), accounts=self.accounts, nicks=self.nicks,
            is_registered=self.is_registered, normalize=self.normalize, skip_whois=self.skip_whois,
            owner_granted=self.owner_granted,
        )
        now = self.now()
        whois = whois[:WHOIS_BATCH]
        done = []
        for nick in whois:
            key = ("whois", nick.lower())
            if now - self._sent.get(key, -1e9) < RESEND_S:
                continue
            self._sent[key] = now
            self._whois[nick.lower()] = False
            self.log(f"INFO chan-privs {nick} unverified in {chan}: WHOIS to learn account ({why})")
            self.send(f"WHOIS {nick}")
        # Anything we were waiting on that the live channel state no longer needs has taken effect:
        # drop its "unconfirmed" counter (the doubling gap itself decays, see below).
        needed = {(a.kind, a.chan.lower(), a.nick.lower(), a.mode) for a in acts}
        for k in [k for k in self._bo if k[1] == chan.lower() and k not in needed]:
            if self._bo[k].get("n", 0):
                self._bo[k]["n"] = 0
        for a in acts:
            key = (a.kind, a.chan.lower(), a.nick.lower(), a.mode)
            bo = self._bo.get(key)
            gap = max(RESEND_S, (bo or {}).get("wait", RESEND_S))
            if now - self._sent.get(key, -1e9) < gap:
                continue
            sign = "+" if a.kind == "grant" else "-"
            if self.chan_op(a.chan):
                line = f"MODE {a.chan} {sign}{a.mode} {a.nick}"
            elif self.is_oper():
                line = f"SAMODE {a.chan} {sign}{a.mode} {a.nick}"
            else:
                if now - self._sent.get(("warn",) + key[1:], -1e9) >= 60.0:
                    self._sent[("warn",) + key[1:]] = now
                    self.log(
                        f"WARN chan-privs cannot {a.kind} {sign}{a.mode} {a.nick} in {a.chan}: Jeeves is not +o "
                        f"there and not oper ({a.reason})"
                    )
                continue
            if bo is None or now - bo["last"] > BACKOFF_DECAY_S:
                bo = {"last": now, "wait": RESEND_S, "n": 0, "warned": False}
            else:
                bo["wait"] = min(BACKOFF_MAX_S, max(RESEND_S, bo["wait"]) * 2)
                bo["last"] = now
            bo["n"] = bo.get("n", 0) + 1
            self._bo[key] = bo
            self._sent[key] = now
            if bo["n"] >= UNCONFIRMED_WARN and not bo["warned"]:
                bo["warned"] = True
                self.log(
                    f"WARN chan-privs {a.kind} {sign}{a.mode} {a.nick} in {a.chan} sent {bo['n']}x without the "
                    f"channel state changing; backing off to every {int(bo['wait'])}s"
                )
            if a.mode == "o" and a.reason.startswith("verified"):
                (self.owner_granted.add if a.kind == "grant" else self.owner_granted.discard)(a.nick.lower())
            elif a.kind == "revoke":
                self.owner_granted.discard(a.nick.lower())
            self.log(
                f"INFO chan-privs {a.kind.upper()} {sign}{a.mode} {a.nick} in {a.chan} [{why}]: {a.reason}"
            )
            self.send(line)
            self.sent_lines.append(line)
            done.append(a)
        return done

    def tick(self) -> None:
        with self.lock:
            self._tick()

    def _tick(self) -> None:
        """Periodic reconcile: NAMES every channel; the 366 handler re-plans with fresh modes."""
        now = self.now()
        if now - self._last_names < RECONCILE_S:
            return
        self._last_names = now
        self._ticks = getattr(self, "_ticks", 0) + 1
        st = self.state
        if self._ticks % 5 == 0:
            st.acct_none.clear()                      # re-ask everyone every ~5 minutes
        else:
            st.acct_none -= self.nicks                # candidate nick(s) every minute
        # Re-verify (WHOIS) every nick we opped for an account and every candidate nick: without
        # account-notify a logout is otherwise never seen. Dropping the cached account only ever
        # leads to a WHOIS, never to a grant or a revoke on its own.
        for n in set(self.nicks) | set(self.owner_granted):
            st.accts.pop(n, None)
        for ch in list(self.channels()):
            self.send(f"NAMES {ch}")
