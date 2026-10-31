"""FR #4008: pure helpers for Jeeves !unregister / !register ops(+o/+h) gate."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

import registered_machines as rm

FLEET = "#bobiverse"
UNREGISTERED_WIRE = "UNREGISTERED v1 {mid}"
REGISTERED_WIRE = "REGISTERED v1 {mid}"
REGISTER_WAIT_S = 20.0

# Ergo / Atheme ChanServ REGISTER outcomes (FR #5274).
_CS_REG_OK = re.compile(
    r"(?i)(?:successfully registered channel\s+(#\S+)|"
    r"channel\s+(#\S+)\s+is now registered|"
    r"(#\S+)\s+is now registered|"
    r"channel\s+(#\S+)\s+is already registered|"
    r"(#\S+)\s+is already registered)"
)
_CS_REG_FAIL = re.compile(
    r"(?i)(?:could not register|registration (?:is )?disabled|"
    r"must be (?:in|an operator)|insufficient|permission|"
    r"command restricted|not authorised|not authorized)"
)
_CS_REG_SHOP = re.compile(r"(#\S+)")

# Ergo ChanServ confirmation: "... UNREGISTER #chan CODE" or "type: /cs UNREGISTER #chan CODE"
_CS_CONFIRM = re.compile(
    r"(?i)unregister\s+(#\S+)\s+([A-Za-z0-9_-]{4,})"
)


@dataclass
class GateResult:
    ok: bool
    reason: str = ""  # allowed | denied | unknown


def nick_has_op_or_halfop(
    *,
    nick: str,
    channel: str = FLEET,
    members: dict | None = None,
    member_lookup: Callable[[str, str], set[str]] | None = None,
) -> bool:
    """True when nick holds +o or +h (or higher aq) in channel.

    ``members`` is PrivState.members shape: chan_l -> nick_l -> {nick, modes}.
    Or pass ``member_lookup(chan, nick) -> modes set``.
    """
    nl = (nick or "").strip().lower()
    cl = (channel or FLEET).strip().lower()
    if not nl:
        return False
    modes: set[str] = set()
    if member_lookup is not None:
        modes = set(member_lookup(cl, nl) or ())
    elif members is not None:
        ent = (members.get(cl) or {}).get(nl) or {}
        modes = set(ent.get("modes") or ())
    return bool(modes & {"o", "h", "a", "q"})


def gate_register_unregister(
    *,
    nick: str,
    channel: str = FLEET,
    members: dict | None = None,
    member_lookup: Callable[[str, str], set[str]] | None = None,
) -> GateResult:
    if nick_has_op_or_halfop(
        nick=nick, channel=channel, members=members, member_lookup=member_lookup
    ):
        return GateResult(True, "allowed")
    return GateResult(False, "denied")


@dataclass
class UnregisterPlan:
    mid: str
    shop: str
    dry_run: bool
    confirm: bool
    in_registry: bool
    core_refused: bool = False
    chanserv_line: str = ""
    part_line: str = ""
    wire_line: str = ""
    notes: list[str] = field(default_factory=list)


def list_shop_console_nicks(mid: str, members: dict | None) -> list[str]:
    """FR #4040: nicks in #<mid> matching *_console (airc console clients).

    `members` is PrivState.members: chan_l -> nick_l -> {nick, modes}.
    """
    mid_l = (mid or "").strip().lower().lstrip("#")
    if not mid_l or not members:
        return []
    chan = members.get(f"#{mid_l}") or members.get(mid_l) or {}
    out = []
    for nick_l, ent in chan.items():
        nick = str((ent or {}).get("nick") or nick_l or "").strip()
        if nick.lower().endswith("_console"):
            out.append(nick)
    return sorted(out, key=lambda s: s.lower())


def console_nicks_note(mid: str, members: dict | None) -> str:
    """Plan/dry-run note listing mid_console nicks (or none seen)."""
    nicks = list_shop_console_nicks(mid, members)
    if not nicks:
        return f"note: #{mid} console clients: none seen"
    return f"note: #{mid} console clients: {', '.join(nicks)}"


def build_unregister_plan(
    home,
    parsed: dict,
    *,
    asker: str = "",
    members: dict | None = None,
) -> UnregisterPlan | None:
    if not parsed:
        return None
    mid = parsed.get("mid")
    dry = bool(parsed.get("dry_run"))
    confirm = bool(parsed.get("confirm"))
    if not mid:
        return None
    if rm.is_core_unregister_refused(mid):
        return UnregisterPlan(
            mid=mid,
            shop=f"#{mid}",
            dry_run=dry,
            confirm=confirm,
            in_registry=False,
            core_refused=True,
            notes=[f"!unregister: refused - #{mid} is a core channel"],
        )
    shop = f"#{mid}"
    in_reg = rm.is_registered(home, mid)
    plan = UnregisterPlan(
        mid=mid,
        shop=shop,
        dry_run=dry,
        confirm=confirm,
        in_registry=in_reg,
        chanserv_line=f"PRIVMSG ChanServ :UNREGISTER {shop}",
        part_line=f"PART {shop} :unregistered by {asker or '?'}",
        wire_line=UNREGISTERED_WIRE.format(mid=mid),
    )
    if not in_reg:
        plan.notes.append(f"!unregister: {shop} is not registered (nothing to do)")
        plan.notes.append(console_nicks_note(mid, members))  # FR #4040
    else:
        plan.notes.append(f"plan: ChanServ UNREGISTER {shop}")
        plan.notes.append(f"plan: remove_registered {mid}")
        plan.notes.append(f"plan: PART {shop}")
        plan.notes.append(f"plan: announce {plan.wire_line} on {FLEET}")
        plan.notes.append("note: airc clients on this shop fall back to #wonderland on next connect (FR #3834)")
        plan.notes.append(console_nicks_note(mid, members))  # FR #4040
    return plan


def parse_chanserv_register_result(notice: str) -> tuple[str, str | None]:
    """Return (ok|fail|unknown, shop_or_none) for a ChanServ REGISTER notice.

    ``already registered`` is ok: the channel exists on ChanServ (FR #5274).
    """
    t = (notice or "").strip()
    if not t:
        return "unknown", None
    m = _CS_REG_OK.search(t)
    if m:
        shop = next((g for g in m.groups() if g), None)
        return "ok", shop
    if _CS_REG_FAIL.search(t):
        sm = _CS_REG_SHOP.search(t)
        return "fail", sm.group(1) if sm else None
    return "unknown", None


def parse_chanserv_unregister_confirm(notice: str) -> tuple[str, str] | None:
    """Return (shop, code) if ChanServ asks to confirm UNREGISTER."""
    t = (notice or "").strip()
    m = _CS_CONFIRM.search(t)
    if not m:
        return None
    shop = m.group(1)
    code = m.group(2)
    if shop.lower() in ("#bobiverse", "#wonderland"):
        return None
    return shop, code


@dataclass
class PendingUnregister:
    mid: str
    asker: str
    deadline: float
    plan_shown: bool = False


class PendingUnregisterStore:
    """In-memory confirm window (60s) for !unregister."""

    def __init__(self, ttl_s: float = 60.0, now: Callable[[], float] = time.time) -> None:
        self.ttl_s = ttl_s
        self.now = now
        self._items: dict[str, PendingUnregister] = {}

    def put(self, mid: str, asker: str) -> PendingUnregister:
        mid = (mid or "").lower()
        item = PendingUnregister(mid=mid, asker=asker, deadline=self.now() + self.ttl_s, plan_shown=True)
        self._items[mid] = item
        return item

    def get(self, mid: str) -> PendingUnregister | None:
        mid = (mid or "").lower()
        item = self._items.get(mid)
        if not item:
            return None
        if self.now() > item.deadline:
            self._items.pop(mid, None)
            return None
        return item

    def pop(self, mid: str) -> PendingUnregister | None:
        return self._items.pop((mid or "").lower(), None)
