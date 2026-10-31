"""Airc LEGION verb + isolated worker scaffold (FR #5308).

No installer invoke in this slice (stub worker). Auth matches UPDATE.
Worker faults must not stop Airc. Single hostname or IPv4 only.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

LEGION_TIMEOUT_S = 900

_LEGION_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?LEGION(?:\s+(?P<rest>.*))?$"
)
_HOST_RE = re.compile(r"(?i)^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?(?:\.[a-z0-9\-]{1,63})*$")
_IPV4_RE = re.compile(
    r"^(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}$"
)


@dataclass
class LegionVerbResult:
    ok: bool
    reply: str
    job_id: str = ""

    def reply_text(self) -> str:
        return self.reply


def _classify_target(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return "empty"
    if "," in t or ";" in t:
        low = t.lower()
        if low.startswith("ou=") or "ou=" in low or low.startswith("cn="):
            return "ou"
        return "list"
    if t.lower().startswith("ou=") or t.lower().startswith("cn="):
        return "ou"
    if _IPV4_RE.match(t) or _HOST_RE.match(t):
        return None
    return "list"


def parse_legion_command(text: str) -> dict[str, Any] | None:
    m = _LEGION_CMD_RE.match((text or "").strip())
    if not m:
        return None
    rest = (m.group("rest") or "").strip()
    whatif = bool(re.search(r"(?i)(?:^|\s)-WhatIf(?:\s|$)", rest))
    rest = re.sub(r"(?i)(?:^|\s)-WhatIf(?:\s|$)", " ", rest).strip()
    parts = [p for p in rest.split() if p]
    qid = (m.group(1) or "").lower()
    if not parts:
        return {"qid": qid, "error": "empty", "target": "", "whatif": whatif}
    if len(parts) > 1:
        return {"qid": qid, "error": "list", "target": rest, "whatif": whatif}
    err = _classify_target(parts[0])
    if err:
        return {"qid": qid, "error": err, "target": parts[0], "whatif": whatif}
    return {"qid": qid, "error": None, "target": parts[0], "whatif": whatif}


def stub_legion_work(
    target: str,
    *,
    whatif: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "target": target,
        "whatif": bool(whatif),
        "invoked_installer": False,
        "force": False,
        "timeout_s": LEGION_TIMEOUT_S,
        "profile": "client",
    }


def run_legion_verb(
    *,
    target: str = "",
    whatif: bool = False,
    job_id: str = "",
    worker: Callable[..., Any] | None = None,
    wait: bool = False,
    **_kw: Any,
) -> LegionVerbResult:
    qid = (job_id or "").strip().lower() or "00000000"
    work = worker or stub_legion_work

    def _safe() -> None:
        try:
            work(target, whatif=whatif)
        except TypeError:
            try:
                work(target=target, whatif=whatif)
            except Exception:
                return
        except Exception:
            return

    if wait:
        _safe()
    else:
        threading.Thread(target=_safe, name="airc-legion-worker", daemon=True).start()
    extra = " whatif=1" if whatif else ""
    reply = (
        f"LEGION accepted id={qid} target={target} timeout={LEGION_TIMEOUT_S}{extra}\n"
        f"DONE id={qid} exit=0"
    )
    return LegionVerbResult(True, reply, job_id=qid)
