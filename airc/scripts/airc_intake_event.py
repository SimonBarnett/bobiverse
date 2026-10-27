"""FR #5067: airc wedge/crash/restart reports to bobiverse intake (#4963 dedupe).

Never raises. Callers must not wait on a long POST before NSSM restart:
``report_airc_event(..., wait_s=1.0)`` joins a daemon thread at most wait_s.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

STAMP_NAME = "airc-run.stamp"
KINDS = ("auth-wedge", "names-reconnect", "abnormal-exit", "exception")


def stamp_path(home) -> Path:
    return Path(home) / STAMP_NAME


def write_stamp(home, state: str) -> None:
    try:
        p = stamp_path(home)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(state).strip() + "\n", encoding="utf-8")
    except Exception:
        return


def read_stamp(home) -> str:
    try:
        t = stamp_path(home).read_text(encoding="utf-8").strip().lower()
        return t.split()[0] if t else ""
    except Exception:
        return ""


def _log_tail(home, n: int = 20) -> str:
    try:
        import crash_report

        home_p = Path(home)
        env_log = (os.environ.get("AIRC_LOG_FILE") or "").strip()
        candidates = [
            home_p / "airc-console.log",
            home_p / "console.log",
            home_p / "logs" / "airc-console.log",
            # FR #5105: NSSM --log-file is usually <install>/logs/, not ConsoleHome.
            home_p.parent / "logs" / "airc-console.log",
        ]
        if env_log:
            candidates.insert(0, Path(env_log))
        path = next((c for c in candidates if c.is_file()), None)
        if path is None:
            logs = sorted(home_p.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            path = logs[0] if logs else None
        if path is None:
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        return crash_report.redact("\n".join(lines))
    except Exception:
        return ""


def report_airc_event(
    kind: str,
    reason: str,
    *,
    home=None,
    filer_post: Callable[..., dict[str, Any]] | None = None,
    wait_s: float = 1.0,
    version: str | None = None,
) -> dict[str, Any]:
    """Post one intake issue per (machine, kind). Never raises."""
    out: dict[str, Any] = {"ok": False}
    kind = (kind or "exception").strip() or "exception"

    def _work() -> None:
        try:
            import crash_report

            mid = crash_report.machine_id()
            key = f"airc|{mid}|{kind}"[:128]
            ver = version or crash_report.read_version()
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            tail = _log_tail(home) if home else ""
            title = f"fail: airc {kind} {mid}"[:200]
            body = (
                f"what: airc operational event `{kind}`\n"
                f"where: machine=`{mid}` version=`{ver}` product=airc\n"
                f"event: {kind}\n"
                f"reason: {crash_report.redact(str(reason)[:400])}\n"
                f"first_seen: {now}\n"
                f"last_seen: {now}\n"
                f"fail-sig:{key}\n"
                f"\n### last log (redacted)\n```\n{tail or '(none)'}\n```\n"
                f"\n---\n_via-airc-intake-event FR=#5067_\n"
            )
            post = filer_post or (
                lambda t, b, **kw: crash_report._post_intake(
                    t, b, repo=kw.get("repo", crash_report.DEFAULT_REPO), sig=key, exe="airc"
                )
            )
            result = post(title, body, repo=crash_report.DEFAULT_REPO, sig=key, exe="airc")
            out.update(result if isinstance(result, dict) else {"result": result})
            out["ok"] = True
            out["dedupe_key"] = key
            out["kind"] = kind
        except Exception as exc:
            try:
                import crash_report as cr

                safe = f"airc-{kind}".replace("|", "-")[:80]
                path = cr._write_spool(
                    {
                        "title": f"fail: airc {kind}",
                        "body": str(reason)[:400],
                        "repo": cr.DEFAULT_REPO,
                        "sig": safe,
                        "exe": "airc",
                        "error": f"{type(exc).__name__}: {exc}",
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                )
                out.update({"ok": False, "spooled": str(path), "kind": kind})
            except Exception as spool_exc:
                out.update(
                    {
                        "ok": False,
                        "kind": kind,
                        "error": type(exc).__name__,
                        "spool_error": type(spool_exc).__name__,
                    }
                )

    if filer_post is not None:
        _work()
        return out
    t = threading.Thread(target=_work, name="airc-intake-event", daemon=True)
    t.start()
    if wait_s and wait_s > 0:
        t.join(timeout=float(wait_s))
    return out


def note_previous_abnormal_exit(home, *, filer_post=None) -> dict[str, Any] | None:
    """If the last run left stamp=running, report abnormal-exit. Then stamp running."""
    prev = read_stamp(home)
    result = None
    if prev == "running":
        result = report_airc_event(
            "abnormal-exit",
            "previous airc run ended without a clean shutdown stamp",
            home=home,
            filer_post=filer_post,
            wait_s=1.0,
        )
    write_stamp(home, "running")
    return result


def mark_clean_exit(home) -> None:
    write_stamp(home, "clean")


def mark_restarting(home) -> None:
    write_stamp(home, "restarting")
