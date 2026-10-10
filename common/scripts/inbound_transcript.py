#!/usr/bin/env python3
"""Always-on scrubbed inbound IRC transcript for Bob ears (FR #2174).

Every ircBob ear writes ``<home>/inbound-transcript.log`` with channel, nick, and
text for each PRIVMSG it handles. Secrets are redacted. The file rotates by size.
Raw wire dump remains opt-in via ``BOB_IRC_DEBUG=1`` → ``irc.log``.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path

TRANSCRIPT_NAME = "inbound-transcript.log"
MAX_BYTES = 2 * 1024 * 1024  # 2 MiB
BACKUP_COUNT = 3

# Same shape as intake / jira webhook redactors — never log credentials.
_SECRETISH = re.compile(
    r"(?i)(password\s*=\s*\S+|api[_-]?key\s*=\s*\S+|ghp_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]+|bearer\s+\S{8,})"
)

_lock = threading.Lock()

# Canonical fleet machine ids covered by FR #2174 acceptance (path + recovery).
# Ionos host shop is win-mpre8vi4u6u (DIGEST_ID_FOLD); keep alias "ionos" for docs/tests.
FLEET_EAR_MACHINES = ("win-mpre8vi4u6u", "marchhare", "flamingo")
FLEET_EAR_ALIASES = ("ionos", "dev1")


def scrub_text(text: str) -> str:
    """Replace secret-shaped tokens; collapse newlines for one log line."""
    s = (text or "").replace("\r", " ").replace("\n", " ").strip()
    return _SECRETISH.sub("[redacted]", s)


def sanitize_machine_id(machine_id: str) -> str:
    mid = re.sub(r"[^A-Za-z0-9_-]+", "-", (machine_id or "").strip()).strip("-_").lower()
    return mid


def canonical_machine_id(machine_id: str) -> str:
    """Fold digest aliases (ionos->win-mpre8vi4u6u, dev1->ce-priority-dev1) for shop channels."""
    mid = sanitize_machine_id(machine_id)
    if not mid:
        return mid
    try:
        import bobreport

        folded = bobreport.fold_machine_id(mid)
        return folded or mid
    except Exception:  # noqa: BLE001
        if mid == "ionos":
            return "win-mpre8vi4u6u"
        if mid == "dev1":
            return "ce-priority-dev1"
        return mid


def channel_list_for_machine(machine_id: str) -> str:
    """Identical Start-Bob --channel value on every fleet box (aliases folded).

    FR #3834: includes #wonderland between fleet and shop.
    """
    mid = canonical_machine_id(machine_id)
    if not mid:
        raise ValueError("machine_id required")
    return f"#bobiverse,#wonderland,#{mid}"


def ear_recovery_plan(
    machine_id: str,
    *,
    service_running: bool,
    home_has_outbox: bool,
    transcript_present: bool,
    stale_irc_listen: bool = False,
) -> list[str]:
    """Deterministic recovery steps for absent / stale / healthy ears.

    Covers Ionos / MarchHare / Flamingo path differences called out in FR #2174:
    missing ircBob, leftover ``irc_listen.py``, missing outbox, missing transcript.
    """
    mid = canonical_machine_id(machine_id)
    if mid not in FLEET_EAR_MACHINES and mid:
        # Still return a plan — unknown boxes follow the same recovery.
        pass
    actions: list[str] = []
    if stale_irc_listen:
        actions.append("retire_stale_irc_listen_use_ircBob")
    if not service_running:
        actions.append("install_or_start_ircBob")
    if not home_has_outbox:
        actions.append("ensure_home_outbox_txt")
    if service_running and not transcript_present:
        actions.append("restart_ircBob_for_inbound_transcript")
    if not actions:
        actions.append("ok")
    return actions


def format_transcript_line(
    channel: str,
    nick: str,
    text: str,
    when: datetime | None = None,
) -> str:
    ts = (when or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ch = (channel or "").strip() or "?"
    nk = (nick or "").strip() or "?"
    body = scrub_text(text)
    return f"{ts} {ch} {nk} {body}"


def transcript_path(home: Path) -> Path:
    return Path(home) / TRANSCRIPT_NAME


def rotate_if_needed(
    path: Path,
    *,
    max_bytes: int = MAX_BYTES,
    backup_count: int = BACKUP_COUNT,
) -> None:
    """Simple size rotation: ``.1`` newest backup … ``.N`` oldest."""
    if backup_count < 1 or max_bytes < 1:
        return
    try:
        if not path.is_file() or path.stat().st_size < max_bytes:
            return
    except OSError:
        return
    for i in range(backup_count, 0, -1):
        src = path if i == 1 else path.with_name(path.name + f".{i - 1}")
        dst = path.with_name(path.name + f".{i}")
        try:
            if dst.exists():
                dst.unlink()
            if src.exists():
                src.rename(dst)
        except OSError:
            pass


def append_inbound(
    home: Path,
    channel: str,
    nick: str,
    text: str,
    *,
    when: datetime | None = None,
    max_bytes: int = MAX_BYTES,
    backup_count: int = BACKUP_COUNT,
) -> Path:
    """Append one scrubbed PRIVMSG line; create home if needed. Always on."""
    home_p = Path(home)
    home_p.mkdir(parents=True, exist_ok=True)
    path = transcript_path(home_p)
    line = format_transcript_line(channel, nick, text, when=when)
    with _lock:
        rotate_if_needed(path, max_bytes=max_bytes, backup_count=backup_count)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
    return path


def worker_filter_verdict(
    src: str,
    target: str,
    text: str,
    own_nick: str,
    *,
    accept_fn=None,
) -> str:
    """Record whether bob_worker would accept (Jeeves→this seat) or drop the line.

    Returns ``accept`` or ``drop``. ``accept_fn`` defaults to bob_worker.accept_for_agent
    when importable; tests may inject a stub.
    """
    fn = accept_fn
    if fn is None:
        try:
            from bob_worker import accept_for_agent as fn  # type: ignore
        except Exception:
            # Lightweight local mirror of t812u when bob_worker is not on path.
            def fn(s, t, x, own, jeeves="Jeeves"):  # type: ignore
                if (s or "").strip().lower() != jeeves.lower():
                    return False
                if (t or "").strip().lower() == (own or "").strip().lower():
                    return True
                n = (own or "").strip()
                if not n:
                    return False
                return (
                    re.match(
                        r"(?i)^\s*@?" + re.escape(n) + r"(?:\s*[:,]|\s|$)",
                        x or "",
                    )
                    is not None
                )

    return "accept" if fn(src, target, text, own_nick) else "drop"


def record_ear_to_worker(
    home: Path,
    *,
    channel: str,
    nick: str,
    text: str,
    own_nick: str,
    filter_target: str | None = None,
    accept_fn=None,
) -> dict[str, str]:
    """Ear transcript + worker-filter verdict for one PRIVMSG (FR #2174 acceptance).

    ``channel`` is what the transcript stores (shop channel or PM target).
    ``filter_target`` is the IRC PRIVMSG target passed to ``accept_for_agent``
    (defaults to ``channel``; use the seat nick for PMs).
    """
    path = append_inbound(home, channel, nick, text)
    target = channel if filter_target is None else filter_target
    verdict = worker_filter_verdict(nick, target, text, own_nick, accept_fn=accept_fn)
    return {
        "transcript": str(path),
        "verdict": verdict,
        "line": format_transcript_line(channel, nick, text),
    }
