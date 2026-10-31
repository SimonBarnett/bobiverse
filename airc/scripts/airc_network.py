"""Airc NETWORK verb + isolated worker scaffold (FR #5298).

No LDAP/DNS inventory in this slice (stub worker). Auth matches UPDATE.
Worker faults must not stop Airc.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

_NETWORK_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?NETWORK(?:\s+diag)?(?:\s+(-WhatIf))?\s*$"
)


@dataclass
class NetworkVerbResult:
    ok: bool
    reply: str
    job_id: str = ""

    def reply_text(self) -> str:
        return self.reply


def parse_network_command(text: str) -> dict[str, Any] | None:
    m = _NETWORK_CMD_RE.match((text or "").strip())
    if not m:
        return None
    return {
        "qid": (m.group(1) or "").lower(),
        "action": "diag",
        "whatif": bool(m.group(2)),
    }


def stub_network_work(
    action: str = "diag",
    *,
    whatif: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "action": action,
        "whatif": bool(whatif),
        "hosts": [],
        "ldap": False,
    }


def run_network_verb(
    *,
    action: str = "diag",
    whatif: bool = False,
    job_id: str = "",
    worker: Callable[..., Any] | None = None,
    wait: bool = False,
    **_kw: Any,
) -> NetworkVerbResult:
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or stub_network_work

    def _safe() -> None:
        try:
            work(action=action, whatif=whatif)
        except Exception:
            return

    if wait:
        _safe()
    else:
        threading.Thread(target=_safe, name="airc-network-worker", daemon=True).start()
    extra = " whatif=1" if whatif else ""
    reply = f"NETWORK accepted id={qid} action={action}{extra}\nDONE id={qid} exit=0"
    return NetworkVerbResult(True, reply, job_id=qid)
