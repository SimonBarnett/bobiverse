"""FR #2411: unhandled exception in any shipped exe -> GitHub issue (dedupe + spool).

Install via ``crash_report.install(exe_name)`` early in each Python entrypoint.
The hook never raises and never blocks shutdown longer than a short network timeout.
FR #2431: exe `probe` / messages with `do-not-file` or `probe-shape-only` are skipped (no intake, no spool keep).
FR #2535: WinError 448 (untrusted mount) on pytest-of-*/pytest-current is skipped; shipped
exe install is a no-op under PYTEST_CURRENT_TEST so product mains do not steal pytest's
excepthook (sessionfinish cleanup noise was filing as crash: jeeves).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_REPO = "SimonBarnett/bobiverse"
DEFAULT_INTAKE = "https://irc.ntsa.uk/bob/v1/intake"
_SIG_RE = re.compile(r"crash-sig:([0-9a-f]{8,64})", re.I)
_SECRET_RE = re.compile(
    r"(?i)("
    r"password|passwd|secret|token|api[_-]?key|xai_api_key|cursor_api_key|"
    r"BOB_IRC_PASSWORD|GH_TOKEN|GITHUB_TOKEN|Authorization|Bearer|"
    r"NickServ|SASL"
    r")\s*[=:]\s*\S+"
)
_TOKEN_BLOB_RE = re.compile(
    r"(?i)\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]+)\b"
)

_installed_for: str | None = None
_prev_sys_hook: Callable | None = None
_prev_thread_hook: Callable | None = None


def spool_dir() -> Path:
    override = (os.environ.get("BOB_CRASH_SPOOL") or "").strip()
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or str(Path.home())
    return Path(local) / "Bobiverse" / "crash-spool"


def redact(text: str) -> str:
    s = _SECRET_RE.sub(lambda m: m.group(1) + "=<redacted>", text or "")
    return _TOKEN_BLOB_RE.sub("<redacted-token>", s)


_PROBE_EXE = frozenset({"probe", "crash-probe", "crash_probe"})
_DO_NOT_FILE_RE = re.compile(r"(?i)do-not-file|probe-shape-only")
# FR #2535: pytest tmpdir symlink cleanup on Windows (WinError 448 / untrusted mount).
_PYTEST_EPHEMERAL_RE = re.compile(r"(?i)pytest-of-|pytest-current")
_UNTRUSTED_MOUNT_RE = re.compile(r"(?i)untrusted mount point|WinError\s*448")
_SHIPPED_EXE_INSTALL = frozenset(
    {
        "jeeves",
        "bob-ear",
        "bob-worker",
        "airc",
        "watch-agenthealth",
        "watch_agent_health",
    }
)


def _blob_for_skip(exc_value: BaseException | None, body: str = "", title: str = "") -> str:
    msg = ""
    if exc_value is not None:
        try:
            msg = str(exc_value)
        except Exception:
            msg = ""
    return "\n".join((msg, body or "", title or ""))


def _is_pytest_untrusted_mount(exc_value: BaseException | None, blob: str) -> bool:
    """True for OSError WinError 448 (or message twin) on pytest-of-*/pytest-current paths."""
    if not _PYTEST_EPHEMERAL_RE.search(blob):
        return False
    if exc_value is not None and isinstance(exc_value, OSError):
        if getattr(exc_value, "winerror", None) == 448:
            return True
    return bool(_UNTRUSTED_MOUNT_RE.search(blob))


def should_skip_report(exe: str, exc_value: BaseException | None, *, body: str = "", title: str = "") -> bool:
    """FR #2431 / #2535: skip probe markers and pytest WinError 448 ephemeral noise.

    Markers: exe name `probe` / `crash-probe`, or message/body/title containing
    `do-not-file` or `probe-shape-only`.
    FR #2535: OSError WinError 448 (untrusted mount point) whose path mentions
    pytest-of- or pytest-current — pytest sessionfinish symlink cleanup, not a product crash.
    """
    name = (exe or "").strip().lower()
    if name in _PROBE_EXE:
        return True
    blob = _blob_for_skip(exc_value, body, title)
    if _DO_NOT_FILE_RE.search(blob):
        return True
    return _is_pytest_untrusted_mount(exc_value, blob)


def read_version() -> str:
    env = (os.environ.get("BOBIVERSE_VERSION") or os.environ.get("BOB_VERSION") or "").strip()
    if env:
        return env
    here = Path(__file__).resolve().parent
    for cand in (
        here.parent / "VERSION",  # common/VERSION in repo
        here / "VERSION",
        Path(os.environ.get("BOB_INSTALL_ROOT") or "") / "VERSION",
        Path(os.environ.get("JEEVES_INSTALL_ROOT") or "") / "VERSION",
    ):
        try:
            if cand.is_file():
                return cand.read_text(encoding="utf-8").strip()[:64]
        except OSError:
            continue
    return "unknown"


def machine_id() -> str:
    return (
        (os.environ.get("BOB_MACHINE_ID") or os.environ.get("COMPUTERNAME") or platform.node() or "unknown")
        .strip()
        .lower()
    )


def signature(exc_type: type | None, exc_value: BaseException | None, tb) -> str:
    """Stable hash of exception type + top frames (file/line/func), not message values."""
    parts: list[str] = [getattr(exc_type, "__name__", "?") if exc_type else "?"]
    try:
        frames = traceback.extract_tb(tb) if tb is not None else []
    except Exception:
        frames = []
    for fr in frames[-8:]:
        parts.append(f"{Path(fr.filename).name}:{fr.lineno}:{fr.name}")
    if exc_value is not None:
        parts.append(type(exc_value).__name__)
    digest = hashlib.sha256("|".join(parts).encode("utf-8", errors="replace")).hexdigest()
    return digest[:16]


def format_report(
    *,
    exe: str,
    exc_type: type | None,
    exc_value: BaseException | None,
    tb,
    version: str | None = None,
    log_tail: str = "",
) -> tuple[str, str, str]:
    sig = signature(exc_type, exc_value, tb)
    et = getattr(exc_type, "__name__", "?") if exc_type else "?"
    msg = redact(str(exc_value)[:180] if exc_value is not None else "")
    ver = version or read_version()
    mach = machine_id()
    title = f"crash: {exe} {et} {sig}"[:200]
    try:
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, tb))
    except Exception:
        tb_text = f"{et}: {msg}"
    tb_text = redact(tb_text)[-12000:]
    body = (
        f"what: unhandled exception in `{exe}`\n"
        f"where: machine=`{mach}` version=`{ver}` platform=`{platform.platform()}`\n"
        f"crash-sig:{sig}\n"
        f"exception: {et}: {msg}\n\n"
        f"```\n{tb_text}\n```\n"
    )
    if log_tail:
        body += f"\n### log tail\n```\n{redact(log_tail)[-4000:]}\n```\n"
    body += (
        f"\n---\n_via-crash-hook exe=`{exe}` sig=`{sig}` "
        f"ts=`{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}`_\n"
    )
    return title, body, sig


def _read_log_tail(path: Path | None, *, max_bytes: int = 4000) -> str:
    if path is None:
        return ""
    try:
        data = path.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _write_spool(payload: dict[str, Any]) -> Path:
    d = spool_dir()
    d.mkdir(parents=True, exist_ok=True)
    sig = str(payload.get("sig") or "unknown")
    path = d / f"crash-{sig}-{int(time.time())}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _post_intake(title: str, body: str, *, repo: str, sig: str, exe: str) -> dict[str, Any]:
    url = (os.environ.get("BOB_INTAKE_URL") or DEFAULT_INTAKE).strip()
    payload = {
        "kind": "issue",
        "repo": repo,
        "title": title,
        "body": body,
        "idempotency_key": f"crash-{sig}",
        "machine": machine_id(),
        "agent": f"crash_report:{exe}",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "bobiverse-crash-report"},
    )
    key = (os.environ.get("BOB_INTAKE_KEY") or "").strip()
    if key:
        req.add_header("X-Bob-Intake-Key", key)
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw) if raw else {"ok": True}
    except json.JSONDecodeError:
        return {"ok": True, "raw": raw[:200]}


def _gh_search_open_sig(repo: str, sig: str) -> int | None:
    """Return open issue number with crash-sig in body, or None. Best-effort."""
    try:
        import shutil
        import subprocess

        if not shutil.which("gh"):
            return None
        q = f"repo:{repo} is:issue is:open crash-sig:{sig}"
        proc = subprocess.run(
            ["gh", "issue", "list", "--repo", repo, "--state", "open", "--search", f"crash-sig:{sig}", "--json", "number,body,title", "--limit", "20"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        if proc.returncode != 0:
            return None
        rows = json.loads(proc.stdout or "[]")
        for row in rows:
            blob = f"{row.get('title') or ''}\n{row.get('body') or ''}"
            if sig.lower() in blob.lower() or _SIG_RE.search(blob):
                return int(row["number"])
        # also match title crash: ... sig
        for row in rows:
            if sig in str(row.get("title") or ""):
                return int(row["number"])
        return None
    except Exception:
        return None


def _gh_comment(repo: str, number: int, body: str) -> bool:
    try:
        import shutil
        import subprocess

        if not shutil.which("gh"):
            return False
        proc = subprocess.run(
            ["gh", "issue", "comment", str(number), "--repo", repo, "--body", body[:6000]],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def report_exception(
    exe: str,
    exc_type: type | None,
    exc_value: BaseException | None,
    tb,
    *,
    repo: str = DEFAULT_REPO,
    version: str | None = None,
    log_path: Path | None = None,
    filer_post: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """File or spool a crash. Never raises."""
    try:
        if should_skip_report(exe, exc_value):
            return {"ok": True, "skipped": True, "reason": "probe-or-do-not-file"}
        title, body, sig = format_report(
            exe=exe,
            exc_type=exc_type,
            exc_value=exc_value,
            tb=tb,
            version=version,
            log_tail=_read_log_tail(log_path),
        )
        existing = _gh_search_open_sig(repo, sig)
        if existing:
            ok = _gh_comment(repo, existing, body)
            if ok:
                return {"ok": True, "deduped": True, "number": existing, "sig": sig}
            # FR #2411 / MRB #2416: gh comment fail must spool (never drop the crash).
            path = _write_spool(
                {
                    "title": title,
                    "body": body,
                    "repo": repo,
                    "sig": sig,
                    "exe": exe,
                    "error": "dedupe_comment_failed",
                    "dedupe_number": int(existing),
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            return {
                "ok": False,
                "deduped": True,
                "number": existing,
                "spooled": str(path),
                "sig": sig,
            }

        post = filer_post or _post_intake
        try:
            result = post(title, body, repo=repo, sig=sig, exe=exe)
            return {"ok": True, "deduped": False, "sig": sig, "result": result}
        except Exception as exc:  # noqa: BLE001
            path = _write_spool(
                {
                    "title": title,
                    "body": body,
                    "repo": repo,
                    "sig": sig,
                    "exe": exe,
                    "error": f"{type(exc).__name__}: {exc}",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            return {"ok": False, "spooled": str(path), "sig": sig}
    except Exception as outer:  # noqa: BLE001
        try:
            path = _write_spool(
                {
                    "title": f"crash: {exe} hook-failure",
                    "body": redact(f"crash hook failed: {type(outer).__name__}: {outer}"),
                    "repo": repo,
                    "sig": "hookfail",
                    "exe": exe,
                }
            )
            return {"ok": False, "spooled": str(path), "error": type(outer).__name__}
        except Exception:
            return {"ok": False, "error": "spool_failed"}


def flush_spool(
    *,
    repo: str = DEFAULT_REPO,
    filer_post: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Retry spooled crashes. Never raises."""
    sent = kept = dropped = 0
    try:
        d = spool_dir()
        if not d.is_dir():
            return {"sent": 0, "kept": 0, "dropped": 0}
        post = filer_post or _post_intake
        for path in sorted(d.glob("crash-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                dropped += 1
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            title = str(payload.get("title") or "crash: spool")
            body = str(payload.get("body") or "")
            sig = str(payload.get("sig") or path.stem)
            exe = str(payload.get("exe") or "unknown")
            r = str(payload.get("repo") or repo)
            if should_skip_report(exe, None, body=body, title=title):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                dropped += 1
                continue
            try:
                existing = _gh_search_open_sig(r, sig)
                if existing:
                    _gh_comment(r, existing, body)
                else:
                    post(title, body, repo=r, sig=sig, exe=exe)
                path.unlink(missing_ok=True)
                sent += 1
            except Exception:
                kept += 1
    except Exception:
        pass
    return {"sent": sent, "kept": kept, "dropped": dropped}


def install(
    exe: str,
    *,
    repo: str = DEFAULT_REPO,
    version: str | None = None,
    log_path: str | Path | None = None,
    flush: bool = True,
) -> None:
    """Install process-wide crash hooks. Idempotent per process; never raises.

    FR #2535: when ``PYTEST_CURRENT_TEST`` is set, skip installing for shipped product
    exe names so ``jeeves_main.main()`` (and siblings) under pytest do not replace
    pytest's excepthook. Unit tests may install non-shipped names (e.g. ``unit-test-exe``)
    or set ``BOB_CRASH_ALLOW_UNDER_PYTEST=1``.
    """
    global _installed_for, _prev_sys_hook, _prev_thread_hook
    try:
        name = (exe or "").strip()
        under_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        allow = (os.environ.get("BOB_CRASH_ALLOW_UNDER_PYTEST") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if under_pytest and not allow and name.lower() in _SHIPPED_EXE_INSTALL:
            return
        if _installed_for == exe:
            return
        log_p = Path(log_path) if log_path else None
        ver = version

        def _handle(exc_type, exc_value, tb) -> None:
            report_exception(
                exe,
                exc_type,
                exc_value,
                tb,
                repo=repo,
                version=ver,
                log_path=log_p,
            )

        prev_sys = sys.excepthook
        _prev_sys_hook = prev_sys

        def sys_hook(exc_type, exc_value, tb):
            try:
                _handle(exc_type, exc_value, tb)
            except Exception:
                pass
            try:
                if prev_sys is not sys.__excepthook__:
                    prev_sys(exc_type, exc_value, tb)
                else:
                    sys.__excepthook__(exc_type, exc_value, tb)
            except Exception:
                pass

        sys.excepthook = sys_hook

        prev_thread = getattr(threading, "excepthook", None)
        _prev_thread_hook = prev_thread

        def thread_hook(args):
            try:
                _handle(args.exc_type, args.exc_value, args.exc_traceback)
            except Exception:
                pass
            try:
                if prev_thread is not None:
                    prev_thread(args)
            except Exception:
                pass

        threading.excepthook = thread_hook  # type: ignore[attr-defined]

        try:
            import asyncio

            def async_handler(loop, context):  # noqa: ANN001
                exc = context.get("exception")
                if isinstance(exc, BaseException):
                    _handle(type(exc), exc, exc.__traceback__)
                else:
                    msg = redact(str(context.get("message") or context))
                    _handle(RuntimeError, RuntimeError(f"asyncio: {msg}"), None)

            try:
                loop = asyncio.get_event_loop()
                if loop is not None and not loop.is_closed():
                    loop.set_exception_handler(async_handler)
            except Exception:
                pass

            # Prefer wrapping the current policy's new_event_loop without replacing the policy class hierarchy.
            policy = asyncio.get_event_loop_policy()
            if not getattr(policy, "_bobiverse_crash_wrapped", False):
                orig_new = policy.new_event_loop

                def new_event_loop():  # noqa: ANN001
                    loop = orig_new()
                    try:
                        loop.set_exception_handler(async_handler)
                    except Exception:
                        pass
                    return loop

                policy.new_event_loop = new_event_loop  # type: ignore[method-assign]
                policy._bobiverse_crash_wrapped = True  # type: ignore[attr-defined]
        except Exception:
            pass

        if flush:
            flush_spool(repo=repo)
        _installed_for = exe
    except Exception:
        pass
