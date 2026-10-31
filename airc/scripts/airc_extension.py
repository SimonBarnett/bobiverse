"""Airc EXTENSION verb + isolated worker scaffold (FR #5290).

No GPO/AD/registry mutation in this slice (stub worker). Auth matches UPDATE
(ops/half-ops; ``update=off`` refuses). Worker faults must not stop Airc.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_EXTENSION_ID = "cgmpadejahkaggjpffnhaoiafbnicgpa"

_EXTENSION_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?EXTENSION\s+(install|status)(?P<rest>.*)$"
)


@dataclass
class ExtensionVerbResult:
    ok: bool
    reply: str
    job_id: str = ""

    def reply_text(self) -> str:
        return self.reply


def parse_extension_command(text: str) -> dict[str, Any] | None:
    m = _EXTENSION_CMD_RE.match((text or "").strip())
    if not m:
        return None
    rest = m.group("rest") or ""
    return {
        "qid": (m.group(1) or "").lower(),
        "action": m.group(2).lower(),
        "whatif": bool(re.search(r"(?i)-WhatIf", rest)),
    }


def stub_extension_work(
    action: str,
    *,
    whatif: bool = False,
    extension_id: str = DEFAULT_EXTENSION_ID,
) -> dict[str, Any]:
    """FR-A stub: never writes GPO/registry (FR-B/C)."""
    return {
        "ok": True,
        "action": action,
        "whatif": bool(whatif),
        "wrote_gpo": False,
        "wrote_registry": False,
        "extension_id": extension_id,
    }


def run_extension_verb(
    *,
    action: str = "install",
    whatif: bool = False,
    job_id: str = "",
    worker: Callable[..., Any] | None = None,
    wait: bool = False,
    **_kw: Any,
) -> ExtensionVerbResult:
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or stub_extension_work

    def _safe() -> None:
        try:
            work(action=action, whatif=whatif, extension_id=DEFAULT_EXTENSION_ID)
        except Exception:
            return

    if wait:
        _safe()
    else:
        threading.Thread(target=_safe, name="airc-extension-worker", daemon=True).start()
    bits = [
        "EXTENSION accepted",
        f"id={qid}",
        f"action={action}",
        f"extension={DEFAULT_EXTENSION_ID}",
    ]
    if whatif:
        bits.append("whatif=1")
    return ExtensionVerbResult(True, " ".join(bits), job_id=qid)
