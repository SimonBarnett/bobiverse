"""Chair-side worker list maintenance (v0.1.18): Jeeves -> /bob/v1/report ``worker-*`` ops.

Deterministic and token-less. Jeeves (the chair) hears the machine channel ``#<machine>`` and keeps
``machines.<id>.workers = [{nick, state: doing|idle, work, updated}]`` current:

* JOIN / NAMES (FR #7186) from a seat nick in ``#<machine>`` -> worker-upsert (present; idle unless already doing)
* ``!bored`` from a nick in ``#<machine>``  -> worker-upsert (idle; wanting work)
* assign / offer (FR #663)                   -> worker-work  (offered + description)
* ACK                                        -> worker-work  (doing + description)
* DONE / NACK / GIVEUP                       -> worker-work  (idle)
* PART / KICK / QUIT / NICK / NAMES reconcile -> worker-remove for nicks no longer in the channel
* Un-ACKed ``offered`` expires to idle after ``OFFERED_TIMEOUT_S`` (bobreport)

Every op passes the SAME schema + roster gate as an HTTP POST (``bobcallback.validate_report_payload``)
and is applied with ``bobreport.apply_callback``; no secret or header is involved. ``post_fn`` lets a
caller (or a test) send the payload elsewhere, e.g. over HTTP to a remote receiver.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import bobreport


def machine_for_channel(home: Path, channel: str) -> str | None:
    """Machine id for a roster machine channel (``#win-mpre8vi4u6u`` -> ``win-mpre8vi4u6u``), else None."""
    ch = bobreport.normalize_channel(channel or "")
    if not ch.startswith("#") or ch.lower() == bobreport.FLEET_CHANNEL:
        return None
    mid = bobreport.normalize_machine_id(ch[1:])
    if not mid or not bobreport.is_roster_machine(home, mid):
        return None
    if ch.lower() != bobreport.shop_channel(mid).lower():
        return None
    return bobreport.fold_machine_id(mid)      # #79: workers in the legacy #ionos count for the real machine


def speaker_machine(home: Path, nick: str, channel: str) -> str | None:
    """Machine for a speaking worker, or None. A seat nick of ANOTHER machine never counts here."""
    mid = machine_for_channel(home, channel)
    if not mid or not bobreport.is_worker_nick(nick):
        return None
    seat = bobreport.parse_seat_nick(nick)
    if seat and bobreport.fold_machine_id(seat[0]) != mid:
        return None
    return mid


def payload_for(op: str, machine: str, nick: str, state: str | None = None, work: str | None = None) -> dict:
    p: dict = {"op": op, "machine": machine, "nick": nick}
    if state:
        p["state"] = state
    if work is not None:
        p["work"] = work
    return p


class WorkerTracker:
    def __init__(
        self,
        home: Path,
        *,
        post_fn: Callable[[dict], int] | None = None,
        log: Callable[[str], None] = lambda m: None,
        briefer: str = "Jeeves",
    ) -> None:
        self.home = Path(home)
        self.post_fn = post_fn
        self.log = log
        self.briefer = briefer

    # -- transport ------------------------------------------------------------------
    def post(self, payload: dict) -> int:
        """Gate (schema + roster) then deliver. Returns an HTTP-like code (204/200 ok, 4xx rejected)."""
        import bobcallback  # lazy: keeps import order flexible for the chair

        code, _mid, why = bobcallback.validate_report_payload(self.home, payload)
        if code:
            self.log(f"WARN workers {payload.get('op')} rejected {code} {why} nick={payload.get('nick')}")
            return code
        if self.post_fn is not None:
            return int(self.post_fn(payload))
        out = bobreport.apply_callback(self.home, payload, self.briefer)
        if not out.ok:
            self.log(f"WARN workers {payload.get('op')} failed err={out.err} nick={payload.get('nick')}")
            return 400
        if out.changed:
            self.log(
                f"INFO workers {payload.get('op')} machine={payload.get('machine')} nick={payload.get('nick')} "
                f"state={payload.get('state') or '-'}"
            )
        return 204 if out.changed else 200

    # -- current list -----------------------------------------------------------------
    def listed(self, machine: str) -> list[str]:
        doc = bobreport.load_digest(self.home)
        ent = (doc.get("machines") or {}).get(machine) or {}
        return [r["nick"] for r in bobreport._coerce_worker_list(ent.get("worker_list"))]

    def _machines_with(self, nick: str) -> list[str]:
        doc = bobreport.load_digest(self.home)
        out = []
        for mid, ent in (doc.get("machines") or {}).items():
            rows = bobreport._coerce_worker_list((ent or {}).get("worker_list"))
            if any(r["nick"].lower() == nick.lower() for r in rows):
                out.append(mid)
        return out

    # -- events -----------------------------------------------------------------------
    def on_join(self, nick: str, channel: str) -> int | None:
        """FR #7186: shop presence from JOIN, not !bored."""
        mid = speaker_machine(self.home, nick, channel)
        if not mid:
            return None
        code = self.post(payload_for("worker-upsert", mid, nick))
        self._stamp_shop_members(mid)
        return code

    def on_bored(self, nick: str, channel: str) -> int | None:
        mid = speaker_machine(self.home, nick, channel)
        if not mid:
            return None
        return self.post(payload_for("worker-upsert", mid, nick))

    def on_offer(self, nick: str, channel: str, work: str) -> int | None:
        """FR #663: assign line sets offered (not doing); ACK promotes to doing."""
        mid = speaker_machine(self.home, nick, channel)
        if not mid:
            return None
        return self.post(payload_for("worker-work", mid, nick, "offered", work or "offered"))

    def on_ack(self, nick: str, channel: str, work: str) -> int | None:
        mid = speaker_machine(self.home, nick, channel)
        if not mid:
            return None
        return self.post(payload_for("worker-work", mid, nick, "doing", work or "working"))

    def on_done(self, nick: str, channel: str) -> int | None:
        mid = speaker_machine(self.home, nick, channel)
        if not mid:
            return None
        return self.post(payload_for("worker-work", mid, nick, "idle"))

    def on_leave(self, nick: str, channel: str) -> int | None:
        """PART / KICK from a machine channel (and any chair channel for *_console)."""
        mid = machine_for_channel(self.home, channel)
        if str(nick or "").lower().endswith("_console"):
            # FR #5947: clear customer-channel presence even when channel is not a shop.
            bobreport.remove_channel_console_nick(self.home, nick, channel)
            if mid:
                bobreport.remove_machine_console_nick(self.home, mid, nick)
        if not mid or nick.lower() not in {n.lower() for n in self.listed(mid)}:
            return None
        return self.post(payload_for("worker-remove", mid, nick))

    def on_quit(self, nick: str) -> list[int]:
        codes = [
            self.post(payload_for("worker-remove", mid, nick))
            for mid in self._machines_with(nick)
        ]
        if str(nick or "").lower().endswith("_console"):
            # FR #5947: drop presence on every channel for this console nick.
            bobreport.remove_channel_console_nick(self.home, nick, None)
            doc = bobreport.load_digest(self.home)
            for mid, ent in (doc.get("machines") or {}).items():
                nicks = bobreport.coerce_console_nicks((ent or {}).get("console_nicks"))
                if any(n.lower() == nick.lower() for n in nicks):
                    bobreport.remove_machine_console_nick(self.home, mid, nick)
        return codes

    def on_nick(self, old: str, new: str) -> list[int]:
        """FR #7186: follow the seat nick on the shops it was listed in."""
        mids = list(self._machines_with(old))
        codes = self.on_quit(old)
        new_n = str(new or "").strip()
        seat = bobreport.parse_seat_nick(new_n)
        if not seat or not new_n:
            return codes
        new_mid = bobreport.fold_machine_id(seat[0])
        for mid in mids:
            if mid == new_mid:
                codes.append(self.post(payload_for("worker-upsert", mid, new_n)))
        return codes

    def reconcile(self, channel: str, present: set[str]) -> list[str]:
        """NAMES: drop absentees and upsert seats that are in the channel (FR #7186)."""
        mid = machine_for_channel(self.home, channel)
        consoles = bobreport.console_nicks_from_present(present)
        # FR #5947: record *_console nicks from every chair channel (shops + customer).
        bobreport.set_channel_console_presence(
            self.home, channel, consoles, machine=mid
        )
        if not mid:
            return []
        here = {n.lower() for n in present}
        gone = [n for n in self.listed(mid) if n.lower() not in here]
        for n in gone:
            self.post(payload_for("worker-remove", mid, n))
        if gone:
            self.log(f"INFO workers reconcile {channel}: removed {','.join(gone)} (not in channel)")
        added = []
        for raw in present:
            nick = str(raw or "").lstrip("@+%&~").strip()
            if not nick or not bobreport.is_worker_nick(nick):
                continue
            if speaker_machine(self.home, nick, channel) != mid:
                continue
            if nick.lower() not in {n.lower() for n in self.listed(mid)}:
                self.post(payload_for("worker-upsert", mid, nick))
                added.append(nick)
        if added:
            self.log(f"INFO workers reconcile {channel}: added {','.join(added)} (in channel)")
        self._stamp_shop_members(mid)
        # FR #5204: persist live *_console nicks for the public digest roster.
        bobreport.set_machine_console_nicks(self.home, mid, consoles)
        return gone

    def _stamp_shop_members(self, machine: str) -> None:
        try:
            doc = bobreport.load_digest(self.home)
            ent = (doc.get("machines") or {}).get(machine)
            if not isinstance(ent, dict):
                return
            ent["shop_members_ts"] = bobreport._utc_now_iso()
            bobreport.save_digest(self.home, doc)
        except Exception:
            pass
