"""FR #5775: shared airc verb/entry fail intake (Python).

One wrapper for every verb/entry. Deterministic dedupe key (same shape as
``Report-AircVerbFailure.ps1``):

    airc-<verb>-fail|<machine>|<verb>|<version>|<exception-class>

Posts via native ``crash_report._post_intake`` (works inside packaged airc.exe).
On unreachable intake, spools to disk for ``flush_spool`` on next start.
Never raises into the caller; reporting is best-effort with a short join timeout.
"""
from __future__ import annotations

import functools
import os
import re
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

# Every registered console verb / isolated worker / service entry that must be wrapped.
VERB_ENTRYPOINTS: frozenset[str] = frozenset(
    {
        "update",
        "version",
        "status",
        "legion",
        "extension",
        "network",
        "priority",
        "shell",
        "cred",
        "job",
        "put",
        "get",
        "dcclisten",
        "help",
        "on_line",
        "handle",
        "installer_legion_work",
        "extension_gpo_then_fill_holes",
        "inventory_work",
        "main",
        "service_run",
    }
)

_WRAPPED: set[str] = set()
_SAFE_TOKEN = re.compile(r"[^a-z0-9._-]+")


def wrapped_verbs() -> frozenset[str]:
    return frozenset(_WRAPPED)


def _sanitize(tok: str, *, default: str = "-") -> str:
    t = _SAFE_TOKEN.sub("-", (tok or "").strip().lower()).strip("-")
    return t or default


def dedupe_key(
    *,
    verb: str,
    machine: str,
    version: str,
    exc_class: str,
) -> str:
    """Deterministic key shared with Report-AircVerbFailure.ps1."""
    v = _sanitize(verb, default="unknown")
    mid = _sanitize(machine, default="unknown")
    ver = _sanitize(version, default="-")
    exc = _sanitize(exc_class, default="Exception")
    return f"airc-{v}-fail|{mid}|{v}|{ver}|{exc}"[:128]


def _meipass_dir() -> Path | None:
    import sys

    mp = getattr(sys, "_MEIPASS", None)
    return Path(mp) if mp else None


def spool_dir() -> Path:
    try:
        import crash_report

        return crash_report.spool_dir()
    except Exception:
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or str(Path.home())
        return Path(local) / "Bobiverse" / "crash-spool"


def _redact(text: str) -> str:
    try:
        import crash_report

        return crash_report.redact(text or "")
    except Exception:
        return re.sub(
            r"(?i)(password|passwd|pwd|pass|secret|token|authorization)\s*[=:]\s*\S+",
            r"\1=<redacted>",
            text or "",
        )


def _machine_id() -> str:
    try:
        import crash_report

        return crash_report.machine_id()
    except Exception:
        raw = (
            os.environ.get("BOB_MACHINE_ID")
            or os.environ.get("COMPUTERNAME")
            or "unknown"
        )
        return _sanitize(raw, default="unknown")


def _version() -> str:
    try:
        import crash_report

        return crash_report.read_version() or "-"
    except Exception:
        return "-"


def _native_post(title: str, body: str, *, repo: str, sig: str, exe: str) -> dict[str, Any]:
    import crash_report

    return crash_report._post_intake(title, body, repo=repo, sig=sig, exe=exe)


def intake_allowed(*, env: dict[str, str] | None = None) -> bool:
    """FR #5783: no live fail-intake under pytest or when crash_report denies send.

    Same spirit as Update CheckFailIntake DryRun (FR #5641): unit tests must not
    flood twin issues when isolated worker_died paths exercise report_verb_failure.
    Injected ``filer_post`` bypasses this gate for intentional unit proofs.
    """
    e = env if env is not None else os.environ
    if str(e.get("PYTEST_CURRENT_TEST") or "").strip():
        return False
    try:
        import crash_report

        return bool(crash_report.load_crash_report_policy(env=dict(e)).send)
    except Exception:
        return True


def _write_fail_spool(payload: dict[str, Any]) -> Path:
    """Spool a fail-intake row; prefer crash_report helper, else local spool_dir."""
    try:
        import crash_report as cr

        return Path(cr._write_spool(payload))
    except Exception:
        import json

        d = spool_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"airc-fail-{int(time.time())}-{os.getpid()}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        return path


def report_verb_failure(
    verb: str,
    exc: BaseException | str,
    *,
    args: dict[str, Any] | None = None,
    version: str | None = None,
    machine: str | None = None,
    wait_s: float = 1.0,
    filer_post: Callable[..., dict[str, Any]] | None = None,
    traceback_text: str | None = None,
) -> dict[str, Any]:
    """Best-effort intake for one verb failure. Never raises."""
    out: dict[str, Any] = {"ok": False}
    v = _sanitize(verb, default="unknown")
    mid = _sanitize(machine or _machine_id(), default="unknown")
    ver = _sanitize(version or _version(), default="-")
    if isinstance(exc, BaseException):
        exc_class = type(exc).__name__
        detail = str(exc)
        tb = traceback_text or "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
    else:
        exc_class = _sanitize(str(exc), default="Error")
        detail = str(exc)
        tb = traceback_text or ""
    key = dedupe_key(verb=v, machine=mid, version=ver, exc_class=exc_class)
    # FR #5783: skip live post/spool under pytest / policy-deny unless filer_post injected.
    if filer_post is None and not intake_allowed():
        out.update(
            {
                "ok": False,
                "skipped": "pytest-or-policy",
                "dedupe_key": key,
                "verb": v,
            }
        )
        return out

    def _work() -> None:
        try:
            safe_args = _redact(repr({k: args[k] for k in (args or {}) if "pass" not in str(k).lower() and "secret" not in str(k).lower() and "token" not in str(k).lower()}))
            title = _redact(f"airc {v} fail {exc_class} machine={mid}")[:200]
            body = _redact(
                "FR #5775 airc verb failure (deterministic intake).\n"
                f"verb={v}\nmachine={mid}\nversion={ver}\n"
                f"exception_class={exc_class}\n"
                f"dedupe_key={key}\n"
                f"args={safe_args}\n"
                f"detail={detail[:800]}\n"
                f"\n### traceback (redacted)\n```\n{_redact(tb)[:4000] or '(none)'}\n```\n"
                f"\n---\n_via-airc-fail-intake FR=#5775_\n"
            )
            post = filer_post or _native_post
            result = post(
                title,
                body,
                repo="SimonBarnett/bobiverse",
                sig=key,
                exe="airc",
            )
            out.update(result if isinstance(result, dict) else {"result": result})
            out["ok"] = True
            out["dedupe_key"] = key
            out["verb"] = v
        except Exception as post_exc:
            try:
                path = _write_fail_spool(
                    {
                        "title": f"airc {v} fail {exc_class}",
                        "body": _redact(detail)[:800],
                        "repo": "SimonBarnett/bobiverse",
                        "sig": key,
                        "exe": "airc",
                        "error": f"{type(post_exc).__name__}: {post_exc}",
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                )
                out.update({"ok": False, "spooled": str(path), "dedupe_key": key, "verb": v})
            except Exception as spool_exc:
                out.update(
                    {
                        "ok": False,
                        "verb": v,
                        "dedupe_key": key,
                        "error": type(post_exc).__name__,
                        "spool_error": type(spool_exc).__name__,
                    }
                )

    # Sync when caller injects filer_post or asks wait_s=0 (tests / packaged prove).
    if filer_post is not None or float(wait_s or 0) <= 0:
        _work()
        return out
    t = threading.Thread(target=_work, name=f"airc-fail-{v}", daemon=True)
    t.start()
    t.join(timeout=float(wait_s))
    return out


def report_update_status_failure(
    *,
    product: str,
    result: str,
    tag: str = "",
    detail: str = "",
    version: str | None = None,
    machine: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """FR #5279 / #5766 / #5775: UPDATE status failure via shared key + native post."""
    mid = _sanitize(machine or _machine_id(), default="unknown")
    ver = _sanitize(version or tag or _version(), default="-")
    res = _sanitize(result, default="failed")
    key = dedupe_key(verb="update", machine=mid, version=ver, exc_class=res)
    title = _redact(f"airc UPDATE fail {res} product={_sanitize(product)}")
    body = _redact(
        "FR #5279 / #5775 UPDATE / Apply failure (deterministic intake).\n"
        f"product={_sanitize(product)}\ntag={_sanitize(tag, default='-')}\n"
        f"result={res}\ndedupe_key={key}\ndetail={detail[:400]}"
    )
    payload: dict[str, Any] = {
        "ok": True,
        "idempotency_key": key,
        "dedupe_key": key,
        "kind": "issue",
        "repo": "SimonBarnett/bobiverse",
        "title": title,
        "body": body,
        "product": _sanitize(product),
        "result": res,
        "dry_run": dry_run,
    }
    if dry_run:
        return payload
    # FR #5783: pytest / crash_report local-only must not post UPDATE fail intake.
    if not intake_allowed():
        payload.update({"ok": False, "skipped": "pytest-or-policy", "dry_run": True})
        return payload
    try:
        _native_post(title, body, repo="SimonBarnett/bobiverse", sig=key, exe="airc")
        payload["ok"] = True
    except Exception as exc:
        try:
            path = _write_fail_spool(
                {
                    "title": title,
                    "body": body,
                    "repo": "SimonBarnett/bobiverse",
                    "sig": key,
                    "exe": "airc",
                    "error": f"{type(exc).__name__}: {exc}",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            payload.update({"ok": False, "spooled": str(path)})
        except Exception as spool_exc:
            payload.update(
                {
                    "ok": False,
                    "error": type(exc).__name__,
                    "spool_error": type(spool_exc).__name__,
                }
            )
    return payload


def wrap_verb(verb: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: register verb and catch any exception -> intake + failure dict/reply."""
    v = _sanitize(verb, default="unknown")
    _WRAPPED.add(v)

    def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def _inner(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - CAST IRON catch-all for intake
                report_verb_failure(
                    v,
                    exc,
                    args={"kwargs_keys": sorted(str(k) for k in kwargs.keys())},
                    wait_s=1.0,
                )
                return {
                    "ok": False,
                    "error": type(exc).__name__,
                    "detail": _redact(str(exc))[:300],
                    "verb": v,
                    "status": "failed",
                }

        _inner.__airc_fail_wrapped__ = True  # type: ignore[attr-defined]
        return _inner

    return _decorator


def mark_wrapped(verb: str) -> None:
    """Record a centrally-wrapped entry (e.g. on_line / handle) without a decorator."""
    _WRAPPED.add(_sanitize(verb, default="unknown"))


def failure_reply(qid: str, verb: str, exc: BaseException | str) -> str:
    """IRC failure reply + DONE exit=1 for a wrapped verb fault."""
    q = (qid or "").strip().lower() or "00000000"
    name = type(exc).__name__ if isinstance(exc, BaseException) else _sanitize(str(exc))
    detail = _redact(str(exc))[:120]
    return (
        f"err id={q} seq=1 code=verb-fault verb={_sanitize(verb)} "
        f"exc={name} {detail}\nDONE id={q} exit=1"
    )
