"""Airc EXTENSION verb + isolated worker (FR #5290 / #5291 / #5293).

Auth matches UPDATE (ops/half-ops; ``update=off`` refuses). Worker faults must not stop Airc.
FR #5291: DC + GPO ``Priority-web-extension`` ForceInstall Chrome+Edge (service wires GPO worker).
FR #5293: structured operation log via DCCLISTEN or IRC CONT; never secrets.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

DEFAULT_EXTENSION_ID = "cgmpadejahkaggjpffnhaoiafbnicgpa"
DEFAULT_UPDATE_URL = "https://clients2.google.com/service/update2/crx"
DEFAULT_GPO_NAME = "Priority-web-extension"
FORCE_INSTALL_ENTRY = f"{DEFAULT_EXTENSION_ID};{DEFAULT_UPDATE_URL}"

_EXTENSION_CMD_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?EXTENSION\s+(install|status)(?P<rest>.*)$"
)


@dataclass
class ExtensionVerbResult:
    ok: bool
    reply: str
    job_id: str = ""
    payload: dict[str, Any] | None = None

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




def gpo_script_path() -> Path:
    return Path(__file__).resolve().parent / "Invoke-AircExtensionGpo.ps1"


def run_extension_gpo_work(
    action: str = "install",
    *,
    whatif: bool = False,
    extension_id: str = DEFAULT_EXTENSION_ID,
    update_url: str = DEFAULT_UPDATE_URL,
    gpo_name: str = DEFAULT_GPO_NAME,
    runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """FR #5291: DC discovery + GPO ForceInstall for Chrome and Edge."""
    eid = (extension_id or DEFAULT_EXTENSION_ID).strip() or DEFAULT_EXTENSION_ID
    url = (update_url or DEFAULT_UPDATE_URL).strip() or DEFAULT_UPDATE_URL
    name = (gpo_name or DEFAULT_GPO_NAME).strip() or DEFAULT_GPO_NAME
    if runner is not None:
        body = runner(
            action=action,
            whatif=whatif,
            extension_id=eid,
            update_url=url,
            gpo_name=name,
        )
        if not isinstance(body, dict):
            return {
                "ok": False,
                "gpo": "fail",
                "reason": "bad_runner",
                "wrote_gpo": False,
                "wrote_registry": False,
                "extension_id": eid,
                "browsers": [],
                "policy_names": [],
            }
        body.setdefault("extension_id", eid)
        body.setdefault("wrote_registry", False)
        body.setdefault(
            "browsers",
            ["chrome", "edge"] if body.get("ok") else [],
        )
        body.setdefault(
            "policy_names",
            [name] if body.get("gpo") in {"ok", "present"} else [],
        )
        return body
    script = gpo_script_path()
    if not script.is_file():
        return {
            "ok": False,
            "gpo": "fail",
            "reason": "gpo_script_missing",
            "wrote_gpo": False,
            "wrote_registry": False,
            "extension_id": eid,
            "browsers": [],
            "policy_names": [],
        }
    args = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Action",
        action,
        "-ExtensionId",
        eid,
        "-UpdateUrl",
        url,
        "-GpoName",
        name,
    ]
    if whatif:
        args.append("-WhatIf")
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "gpo": "fail",
            "reason": "gpo_invoke_failed",
            "error": type(exc).__name__,
            "wrote_gpo": False,
            "wrote_registry": False,
            "extension_id": eid,
            "browsers": [],
            "policy_names": [],
        }
    raw = (proc.stdout or "").strip().splitlines()
    blob = raw[-1] if raw else ""
    try:
        data = json.loads(blob) if blob else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict) or not data:
        return {
            "ok": False,
            "gpo": "fail",
            "reason": "gpo_bad_json" if blob else "gpo_empty_output",
            "exit_code": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-400:],
            "wrote_gpo": False,
            "wrote_registry": False,
            "extension_id": eid,
            "browsers": [],
            "policy_names": [],
        }
    data.setdefault("wrote_registry", False)
    data.setdefault("extension_id", eid)
    return data


def service_extension_runner(**kw: Any) -> ExtensionVerbResult:
    """Production runner: GPO in isolated thread/child (FR #5291 / parent S4).

    Do not wait=True here --- that blocks the IRC receive handler for nltest/GPO.
    Structured gpo=ok/fail belongs on the DCC/CONT log (FR #5293), not the accept line.
    """
    return run_extension_verb(worker=run_extension_gpo_work, wait=False, **kw)

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
    last: dict[str, Any] = {}

    def _safe() -> None:
        nonlocal last
        try:
            out = work(action=action, whatif=whatif, extension_id=DEFAULT_EXTENSION_ID)
            if isinstance(out, dict):
                last = out
        except Exception:
            last = {"ok": False, "gpo": "fail", "reason": "worker_exception"}
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
        f"gpo={DEFAULT_GPO_NAME}",
    ]
    if whatif:
        bits.append("whatif=1")
    if wait and last:
        gpo = str(last.get("gpo") or ("ok" if last.get("ok") else "fail"))
        bits.append(f"gpo_result={gpo}")
        if last.get("reason"):
            bits.append(f"reason={last.get('reason')}")
        browsers = last.get("browsers") or []
        if browsers:
            bits.append("browsers=" + ",".join(str(b) for b in browsers))
    return ExtensionVerbResult(True, " ".join(bits), job_id=qid, payload=last or None)


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
    if failures is not None:
        fails = list(failures)
    elif isinstance(gpo, dict) and gpo.get("ok"):
        fails = []
    elif isinstance(gpo, dict) and gpo.get("ok") is False:
        fails = [{"step": "gpo", "error": str(gpo.get("reason") or "gpo_fail")}]
    else:
        fails = [{"step": "gpo", "error": "not-implemented-fr-b"}]
    if extra:
        fails = fails  # extra is scrubbed, never merged as secrets
    gpo_block = gpo or {"attempted": False, "name": DEFAULT_GPO_NAME}
    if isinstance(gpo, dict):
        gpo_block = {
            "attempted": True,
            "name": gpo.get("gpo_name") or gpo.get("name") or DEFAULT_GPO_NAME,
            "ok": bool(gpo.get("ok")),
            "result": gpo.get("gpo"),
            "browsers": list(gpo.get("browsers") or []),
            "policy_names": list(gpo.get("policy_names") or []),
            "reason": gpo.get("reason"),
            "wrote_gpo": bool(gpo.get("wrote_gpo")),
        }
    log = {
        "action": action,
        "whatif": bool(whatif),
        "extension_id": extension_id,
        "gpo": gpo_block,
        "fallback": fallback or {"attempted": False},
        "hosts": list(hosts or []),
        "failures": fails,
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
