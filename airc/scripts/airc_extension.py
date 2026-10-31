"""Airc EXTENSION verb + isolated worker scaffold (FR #5290 / FR #5293).

No GPO/AD/registry mutation in this slice (stub worker). Auth matches UPDATE
(ops/half-ops; ``update=off`` refuses). Worker faults must not stop Airc.
FR #5293: structured operation log via DCCLISTEN or IRC CONT; never secrets.
"""
from __future__ import annotations

import hashlib
import json
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


_SECRET_KEY_RE = re.compile(r"(?i)pass|secret|token|pwd|cred")


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _scrub(v)
            for k, v in obj.items()
            if not _SECRET_KEY_RE.search(str(k))
        }
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    if isinstance(obj, str) and _SECRET_KEY_RE.search(obj) and "=" in obj:
        return "[redacted]"
    return obj


def build_extension_log(
    action: str,
    *,
    whatif: bool = False,
    hosts: list[dict] | None = None,
    failures: list[dict] | None = None,
    gpo: dict | None = None,
    fallback: dict | None = None,
    extra: dict | None = None,
    extension_id: str = DEFAULT_EXTENSION_ID,
) -> dict[str, Any]:
    fails = list(failures or [])
    if extra:
        fails = fails  # extra is scrubbed, never merged as secrets
    log = {
        "action": action,
        "whatif": bool(whatif),
        "extension_id": extension_id,
        "gpo": gpo or {"attempted": False, "name": "Priority-web-extension"},
        "fallback": fallback or {"attempted": False},
        "hosts": list(hosts or []),
        "failures": fails
        or [{"step": "gpo", "error": "not-implemented-fr-b"}],
    }
    if extra:
        for k, v in extra.items():
            if not _SECRET_KEY_RE.search(str(k)):
                log[k] = v
    log = _scrub(log)
    log["failure_count"] = len(log.get("failures") or [])
    return log


def extension_log_bytes(log: dict[str, Any]) -> bytes:
    return (json.dumps(log, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def deliver_extension_log(
    *,
    job_id: str,
    log: dict[str, Any],
    offer: Any | None = None,
    send_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    import airc_dcc_bulk as _dcc

    jid = (job_id or "").strip().lower() or "00000000"
    raw = extension_log_bytes(log)
    digest = hashlib.sha256(raw).hexdigest()
    nfail = int(log.get("failure_count") or 0)
    summary = f"EXTENSION log failures={nfail} action={log.get('action')} bytes={len(raw)}"
    lines: list[str] = [f"out id={jid} seq=1 {summary}"]
    for i, fail in enumerate(log.get("failures") or [], start=2):
        lines.append(f"out id={jid} seq={i} failure {json.dumps(fail, separators=(',', ':'))}")
    if offer is not None:
        sender = send_fn or _dcc.send_offer_payload
        try:
            sender(raw, offer)
            done = _dcc.format_done_via_dcc(jid, 0, nbytes=len(raw), sha256=digest, via="dcc")
            return {
                "via": "dcc",
                "sha256": digest,
                "nbytes": len(raw),
                "summary": summary,
                "lines": [lines[0], done],
                "done": done,
            }
        except Exception as exc:
            lines.append(f"err id={jid} seq={len(lines)+1} dcc failed: {exc}; falling back to IRC")
            done = f"DONE id={jid} exit=0 via=irc reason=dcc-fail"
            lines.append(done)
            return {
                "via": "irc",
                "sha256": digest,
                "nbytes": len(raw),
                "summary": summary,
                "lines": lines,
                "done": done,
            }
    lines.append("CONT id=" + jid + " offset=1")
    done = f"DONE id={jid} exit=0 via=irc"
    lines.append(done)
    return {
        "via": "irc",
        "sha256": digest,
        "nbytes": len(raw),
        "summary": summary,
        "lines": lines,
        "done": done,
    }
