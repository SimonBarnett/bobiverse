"""FR #7505: tray engine dead / failed watchdog relaunch -> one bobiverse exception report per machine.

Dedupe: stable crash-sig per machine. First event opens (or intakes) one issue; repeats and
recovery comment on the open issue. Never includes secrets (crash_report.redact). Never raises.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import crash_report

DEFAULT_REPO = crash_report.DEFAULT_REPO
STATUS_STALE_SECONDS = 120
LIFECYCLE_TAIL_LINES = 50
COMMENT_RATE_S = 30 * 60  # repeats: comment at most every 30 min (recovery always allowed)


def stable_sig(machine: str | None = None) -> str:
    mid = (machine or crash_report.machine_id() or "unknown").strip().lower() or "unknown"
    raw = f"tray-engine-dead|{mid}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def lifecycle_log_path() -> Path:
    override = (os.environ.get("BOB_TRAY_LIFECYCLE_LOG") or "").strip()
    if override:
        return Path(override)
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".")
    return base / "Bobiverse" / "tray-lifecycle.log"


def state_dir() -> Path:
    override = (os.environ.get("BOB_TRAY_ENGINE_REPORT_DIR") or "").strip()
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".")
    p = base / "Bobiverse" / "tray-engine-report"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_path(sig: str) -> Path:
    return state_dir() / f"{sig}.json"


def _load_state(sig: str) -> dict[str, Any]:
    path = _state_path(sig)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(sig: str, doc: dict[str, Any]) -> None:
    _state_path(sig).write_text(json.dumps(doc, indent=2), encoding="utf-8")


def lifecycle_tail(path: Path | None = None, *, n: int = LIFECYCLE_TAIL_LINES) -> str:
    p = path or lifecycle_log_path()
    try:
        if not p.is_file():
            return "(no tray-lifecycle.log)"
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        chunk = "\n".join(lines[-max(1, int(n)) :])
        return crash_report.redact(chunk)
    except OSError as exc:
        return f"(lifecycle unread: {type(exc).__name__})"


def snap_age_seconds(snap_path: str | Path | None) -> float | None:
    if not snap_path:
        return None
    try:
        p = Path(snap_path)
        if not p.is_file():
            return None
        return max(0.0, time.time() - p.stat().st_mtime)
    except OSError:
        return None


def build_body(
    *,
    kind: str,
    machine: str,
    version: str,
    last_status_write: str,
    exit_code: str,
    relaunch_error: str,
    lifecycle: str,
    sig: str,
) -> str:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return (
        f"what: tray engine {kind} on `{machine}`\n"
        f"where: machine=`{machine}` tray_version=`{version}`\n"
        f"crash-sig:{sig}\n"
        f"fail-sig:{sig}\n"
        f"kind: {kind}\n"
        f"last_status_write: {last_status_write or '(unknown)'}\n"
        f"exit_code: {exit_code or '(none)'}\n"
        f"relaunch_error: {crash_report.redact(relaunch_error or '(none)')}\n"
        f"reported_at: {now}\n\n"
        f"### last {LIFECYCLE_TAIL_LINES} tray-lifecycle.log lines\n"
        f"```\n{lifecycle[-12000:]}\n```\n"
        f"\n---\n_via-tray-engine-report FR=#7505_\n"
    )


def report(
    kind: str,
    *,
    machine: str | None = None,
    version: str | None = None,
    snap_path: str | Path | None = None,
    last_status_write: str | None = None,
    exit_code: str | None = None,
    relaunch_error: str | None = None,
    lifecycle_path: str | Path | None = None,
    repo: str = DEFAULT_REPO,
    find_open: Callable[[str, str], int | None] | None = None,
    filer_new: Callable[..., dict[str, Any]] | None = None,
    filer_comment: Callable[[str, int, str], bool] | None = None,
    now_epoch: float | None = None,
    force_comment: bool = False,
) -> dict[str, Any]:
    """File or comment one tray-engine failure/recovery. Never raises."""
    try:
        kind = (kind or "dead").strip().lower()
        if kind not in ("dead", "relaunch-fail", "recovery", "status-stale"):
            kind = "dead"
        mid = (machine or crash_report.machine_id() or "unknown").strip().lower() or "unknown"
        ver = version or crash_report.read_version()
        sig = stable_sig(mid)
        age = snap_age_seconds(snap_path)
        if last_status_write is None:
            if age is None:
                last_status_write = "(missing)"
            else:
                last_status_write = f"{age:.0f}s ago"
        life = lifecycle_tail(Path(lifecycle_path) if lifecycle_path else None)
        title = f"fail: tray-engine {kind} {mid}"[:200]
        body = build_body(
            kind=kind,
            machine=mid,
            version=ver,
            last_status_write=last_status_write,
            exit_code=exit_code or "",
            relaunch_error=relaunch_error or "",
            lifecycle=life,
            sig=sig,
        )
        state = _load_state(sig)
        epoch = time.time() if now_epoch is None else float(now_epoch)
        find = find_open or crash_report._gh_search_open_sig
        comment = filer_comment or crash_report._gh_comment
        post = filer_new or (
            lambda t, b, **kw: crash_report._post_intake(
                t, b, repo=kw.get("repo", repo), sig=sig, exe="tray-engine"
            )
        )

        # Recovery always comments when an open issue exists; never opens a new recovery issue.
        if kind == "recovery":
            existing = find(repo, sig)
            if existing:
                ok = comment(repo, int(existing), body)
                state["last_recovery_epoch"] = epoch
                state["open_number"] = int(existing)
                _save_state(sig, state)
                return {
                    "ok": bool(ok),
                    "deduped": True,
                    "recovery": True,
                    "number": int(existing),
                    "sig": sig,
                    "kind": kind,
                }
            return {"ok": True, "skipped": True, "reason": "no-open-issue", "sig": sig, "kind": kind}

        existing = find(repo, sig)
        if existing is None and state.get("open_number"):
            try:
                existing = int(state["open_number"])
            except (TypeError, ValueError):
                existing = None

        if existing:
            last_c = float(state.get("last_comment_epoch") or 0)
            if (not force_comment) and last_c and (epoch - last_c) < COMMENT_RATE_S:
                state["count"] = int(state.get("count") or 1) + 1
                state["last_seen_epoch"] = epoch
                _save_state(sig, state)
                return {
                    "ok": True,
                    "deduped": True,
                    "rate_limited": True,
                    "number": int(existing),
                    "sig": sig,
                    "kind": kind,
                    "count": state["count"],
                }
            ok = comment(repo, int(existing), body)
            state["last_comment_epoch"] = epoch
            state["last_seen_epoch"] = epoch
            state["count"] = int(state.get("count") or 1) + 1
            state["open_number"] = int(existing)
            _save_state(sig, state)
            return {
                "ok": bool(ok),
                "deduped": True,
                "number": int(existing),
                "sig": sig,
                "kind": kind,
                "count": state["count"],
            }

        try:
            result = post(title, body, repo=repo, sig=sig, exe="tray-engine")
            state = {
                "first_seen_epoch": epoch,
                "last_seen_epoch": epoch,
                "last_comment_epoch": epoch,
                "count": 1,
                "machine": mid,
                "kind": kind,
            }
            if isinstance(result, dict):
                num = result.get("number") or result.get("issue")
                if num is not None:
                    try:
                        state["open_number"] = int(num)
                    except (TypeError, ValueError):
                        pass
            _save_state(sig, state)
            out = dict(result) if isinstance(result, dict) else {"ok": True, "result": result}
            out.update({"ok": True, "deduped": False, "sig": sig, "kind": kind})
            return out
        except Exception as send_exc:  # noqa: BLE001
            path = crash_report._write_spool(
                {
                    "title": title,
                    "body": body,
                    "repo": repo,
                    "sig": sig,
                    "exe": "tray-engine",
                    "error": f"{type(send_exc).__name__}: {send_exc}",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            return {"ok": False, "spooled": str(path), "sig": sig, "kind": kind}
    except Exception as outer:  # noqa: BLE001
        return {"ok": False, "error": type(outer).__name__}


def maybe_status_stale(snap_path: str | Path, *, stale_s: float = STATUS_STALE_SECONDS) -> bool:
    age = snap_age_seconds(snap_path)
    if age is None:
        return True
    return age >= float(stale_s)


def main(argv: list[str] | None = None) -> int:
    """CLI: dead|relaunch-fail|recovery|status-stale [--machine M] [--snap PATH] [--exit CODE] [--error TEXT]."""
    import argparse

    ap = argparse.ArgumentParser(prog="tray_engine_report")
    ap.add_argument("kind", choices=["dead", "relaunch-fail", "recovery", "status-stale"])
    ap.add_argument("--machine", default="")
    ap.add_argument("--version", default="")
    ap.add_argument("--snap", default="")
    ap.add_argument("--exit-code", default="")
    ap.add_argument("--error", default="")
    ap.add_argument("--lifecycle", default="")
    args = ap.parse_args(argv)
    r = report(
        args.kind,
        machine=args.machine or None,
        version=args.version or None,
        snap_path=args.snap or None,
        exit_code=args.exit_code or None,
        relaunch_error=args.error or None,
        lifecycle_path=args.lifecycle or None,
    )
    print(json.dumps(r, sort_keys=True))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
