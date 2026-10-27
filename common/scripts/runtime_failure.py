"""FR #5050: caught operational failures report to bobiverse intake (deduped).

Tray / ear / Jeeves call ``report`` (or PowerShell ``Report-BobRuntimeFailure``)
instead of empty catch. Same signature (component + machine + error type + site)
is one issue; repeats update last-seen locally and do not POST again inside the
rate window. Intake down -> spool via crash_report, flush later.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
from pathlib import Path
from typing import Any, Callable

import crash_report

DEFAULT_RATE_S = 12 * 3600
_SEEN: dict[str, dict[str, Any]] = {}


def state_dir() -> Path:
    override = (os.environ.get("BOB_RUNTIME_FAILURE_DIR") or "").strip()
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".")
    p = base / "Bobiverse" / "runtime-failure"
    p.mkdir(parents=True, exist_ok=True)
    return p


def failure_signature(*, component: str, site: str, exc: BaseException | None) -> str:
    et = type(exc).__name__ if exc is not None else "Error"
    tb = getattr(exc, "__traceback__", None) if exc is not None else None
    base = crash_report.signature(type(exc) if exc is not None else None, exc, tb)
    mid = crash_report.machine_id()
    raw = f"{component}|{site}|{mid}|{et}|{base}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def _load_seen(sig: str) -> dict[str, Any] | None:
    if sig in _SEEN:
        return _SEEN[sig]
    path = state_dir() / f"{sig}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _SEEN[sig] = data
            return data
    except Exception:
        return None
    return None


def _save_seen(sig: str, doc: dict[str, Any]) -> None:
    _SEEN[sig] = doc
    path = state_dir() / f"{sig}.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def report(
    component: str,
    exc: BaseException,
    *,
    site: str = "",
    version: str | None = None,
    rate_s: int | None = None,
    filer_post: Callable[..., dict[str, Any]] | None = None,
    repo: str = crash_report.DEFAULT_REPO,
) -> dict[str, Any]:
    """Log + intake one distinct failure. Never raises."""
    try:
        site = (site or "caught").strip() or "caught"
        component = (component or "unknown").strip() or "unknown"
        sig = failure_signature(component=component, site=site, exc=exc)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        window = DEFAULT_RATE_S if rate_s is None else int(rate_s)
        prev = _load_seen(sig)
        if prev:
            first = str(prev.get("first_seen") or now)
            prev["last_seen"] = now
            prev["count"] = int(prev.get("count") or 1) + 1
            _save_seen(sig, prev)
            try:
                first_ts = float(prev.get("first_seen_epoch") or 0)
            except (TypeError, ValueError):
                first_ts = 0.0
            if first_ts and (time.time() - first_ts) < window:
                return {
                    "ok": True,
                    "deduped": True,
                    "sig": sig,
                    "component": component,
                    "first_seen": first,
                    "last_seen": now,
                    "count": prev["count"],
                }
        else:
            first = now
        ver = version or crash_report.read_version()
        tb = exc.__traceback__
        title = f"fail: {component} {type(exc).__name__} {site}"[:200]
        body = (
            f"what: caught operational failure in `{component}`\n"
            f"where: machine=`{crash_report.machine_id()}` version=`{ver}` site=`{site}`\n"
            f"fail-sig:{sig}\n"
            f"crash-sig:{sig}\n"
            f"exception: {type(exc).__name__}: {crash_report.redact(str(exc)[:180])}\n"
            f"first_seen: {first}\n"
            f"last_seen: {now}\n\n"
            f"```\n{crash_report.redact(''.join(traceback.format_exception(type(exc), exc, tb))[-8000:])}\n```\n"
            f"\n---\n_via-runtime-failure component=`{component}` FR=#5050_\n"
        )
        post = filer_post or (
            lambda t, b, **kw: crash_report._post_intake(
                t, b, repo=kw.get("repo", repo), sig=sig, exe=component
            )
        )
        try:
            result = post(title, body, repo=repo, sig=sig, exe=component)
            epoch = time.time() if not prev else float(prev.get("first_seen_epoch") or time.time())
            _save_seen(
                sig,
                {
                    "first_seen": first,
                    "first_seen_epoch": epoch,
                    "last_seen": now,
                    "count": 1 if not prev else int(prev.get("count") or 1),
                    "component": component,
                    "site": site,
                },
            )
            out = dict(result) if isinstance(result, dict) else {"ok": True, "result": result}
            out.update(
                {
                    "ok": True,
                    "deduped": False,
                    "component": component,
                    "site": site,
                    "first_seen": first,
                    "last_seen": now,
                    "fail_sig": sig,
                    "sig": sig,
                }
            )
            return out
        except Exception as send_exc:  # noqa: BLE001
            path = crash_report._write_spool(
                {
                    "title": title,
                    "body": body,
                    "repo": repo,
                    "sig": sig,
                    "exe": component,
                    "error": f"{type(send_exc).__name__}: {send_exc}",
                    "ts": now,
                }
            )
            return {
                "ok": False,
                "spooled": str(path),
                "sig": sig,
                "component": component,
                "first_seen": first,
                "last_seen": now,
            }
    except Exception as outer:  # noqa: BLE001
        return {"ok": False, "error": type(outer).__name__}


def report_message(component: str, message: str, *, site: str = "") -> dict[str, Any]:
    return report(component, RuntimeError(message), site=site)
