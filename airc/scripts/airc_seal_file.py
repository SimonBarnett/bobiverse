"""FR #7131: console SEAL identity + FILE v1 tier S receive (no python.exe CLI)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import filexfer
import protect
import seal
import wire


def identity_path(home: Path) -> Path:
    return Path(home) / "identity.json"


def peers_path(home: Path) -> Path:
    return Path(home) / "peers.json"


def ensure_identity(home: Path) -> dict:
    """Mint ConsoleHome/identity.json once; load thereafter. Frozen airc.exe has cryptography."""
    path = identity_path(home)
    if path.is_file():
        return seal.load_ident(path)
    return seal.genkey(path)


def agpk_line(ident: dict) -> str:
    return f"AGPK v1 {ident['pk']}"


def agpk_privmsg_body(core: Any) -> str | None:
    inbox = getattr(core, "seal_inbox", None)
    if inbox is None:
        return None
    return inbox.announce_agpk()


class SealFileInbox:
    """TOFU AGPK + SEAL v2 AIRC-FILE into home/files/complete/."""

    def __init__(self, home: Path, *, nick: str, channel: str) -> None:
        self.home = Path(home)
        self.nick = nick
        self.channel = channel
        self.ident = ensure_identity(self.home)
        self.peers = seal.load_peers(peers_path(self.home))
        self.fragments = seal.FragmentStore()
        self.file_bags = filexfer.FileBag()
        protect.protect_path(self.home)

    def announce_agpk(self) -> str:
        return agpk_line(self.ident)

    def consume(self, src: str, body: str, *, channel: str) -> tuple[bool, str | None]:
        """Return (handled, optional FILE v1 ACCEPT/REFUSE). Never raises to the IRC loop."""
        text = (body or "").strip()
        pk = seal.parse_agpk_line(text)
        if pk is not None:
            result = seal.tofu_pin(self.peers, src, pk)
            if result == "pinned":
                seal.save_peers(self.peers, peers_path(self.home))
            return True, None
        fl = wire.parse_file_line(text)
        if fl is not None:
            return self._file_line(src, fl)
        parsed = seal.parse_seal_line(text)
        if parsed is None:
            return False, None
        self._seal_line(src, parsed, channel=channel)
        return True, None

    def _mine(self, name: str) -> bool:
        return name.lower() in {self.nick.lower(), "*"}

    def _file_line(self, src: str, fl: Any) -> tuple[bool, str | None]:
        if fl.verb == "OFFER":
            to_n = fl.fields[0] if fl.fields else ""
            if to_n != "*" and to_n.lower() != self.nick.lower():
                return True, None
            name = fl.fields[-1] if fl.fields else ""
            nbytes = fl.fields[3] if len(fl.fields) > 3 else ""
            sha = fl.fields[4] if len(fl.fields) > 4 else ""
            tier = fl.fields[5] if len(fl.fields) > 5 else ""
            if not fl.file_id:
                return True, None
            self.file_bags.note_offer(src, fl.file_id, name, sha, nbytes, tier)
            extra = 0
            try:
                extra = int(nbytes or 0)
            except (TypeError, ValueError):
                extra = 0
            if str(tier).upper() != "S":
                return True, f"FILE v1 REFUSE {fl.file_id} :tier"
            if filexfer.would_exceed_cap(self.home, extra=extra):
                return True, f"FILE v1 REFUSE {fl.file_id} :disk"
            return True, f"FILE v1 ACCEPT {fl.file_id}"
        if fl.verb == "ABORT" and fl.file_id:
            self.file_bags.abort(fl.file_id)
            return True, None
        # Tier S payload is SEAL, not FILE CHUNK. Ignore leftover M chunks.
        return True, None

    def _seal_line(self, src: str, parsed: Any, *, channel: str) -> None:
        if parsed.version == 2 and parsed.from_nick and parsed.from_nick.lower() != src.lower():
            return
        if parsed.to_nick.lower() != self.nick.lower():
            return
        if parsed.version != 2:
            return
        payload = self.fragments.add(parsed)
        if payload is None:
            return
        pin = self.peers.get((parsed.from_nick or src).lower(), {}).get("pk")
        if not pin:
            return
        try:
            blob = seal.b64d(payload)
            pt = seal.open_bytes_v2(
                blob,
                self.ident,
                channel,
                parsed.to_nick,
                parsed.from_nick or src,
                parsed.msg_id,
                pin,
            )
        except Exception:
            return
        self._take_airc_file(parsed.msg_id, pt)

    def _take_airc_file(self, msg_id: str, pt: bytes) -> None:
        if not pt.startswith(b"AIRC-FILE v1"):
            dest = self.home / "inbox" / f"{msg_id}.bin"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(pt)
                protect.protect_path(dest)
            return
        env = filexfer.decode_airc_file(pt)
        if env is None:
            return
        offer = self.file_bags._offers.get(msg_id.lower(), {})
        if offer:
            if offer.get("sha") and str(offer["sha"]).lower() != env["sha256"]:
                return
            try:
                offered_n = int(offer["bytes"]) if offer.get("bytes") is not None else None
            except (TypeError, ValueError):
                offered_n = None
            if offered_n is not None and offered_n != env["bytes"]:
                return
            if offer.get("name") and offer["name"] != env["name"]:
                return
        filexfer.complete_write(
            self.home, msg_id, env["name"], env["data"], env["sha256"], expect_len=env["bytes"]
        )
