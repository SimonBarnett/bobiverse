"""FR #2411: unhandled exception -> GitHub issue (dedupe + spool).

Install from every shipped Python exe entrypoint. Never raise from the hook.
Secrets redacted; traceback signature dedupes open issues; offline spool flush on next start.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

REPO_DEFAULT = "SimonBarnett/bobiverse"
SPOOL_SUBDIR = ("Bobiverse", "crash-spool")
SIG_LABEL = "crash-sig"
_INSTALLED = False
_LOCK = threading.Lock()

_SECRET_RX = re.compile(
    r"(?i)("
    r"(?:xai_api_key|cursor_api_key|password|passwd|secret|token|authenticate|"
    r"gh_token|github_token|bob_irc_password|bob_irc_sasl_password|api[_-]?key)"
    r")\s*[=:]\s*\S+"
)
_ENV_SECRET_NAMES = re.compile(
    r"(?i)^(GH_TOKEN|GITHUB_TOKEN|XAI_API_KEY|CURSOR_API_KEY|BOB_IRC_PASSWORD|"
    r"BOB_IRC_SASL_PASSWORD|.*(_TOKEN|_PASSWORD|_SECRET|_API_KEY))$"
)


def redact(text: str) -> str:
    s = _SECRET_RX.sub(lambda m: m.group(1) + "=<redacted>", str(text or ""))
    out_lines = []
    for line in s.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            if _ENV_SECRET_NAMES.match(k.strip()):
                out_lines.append(f"{k.strip()}=<redacted>")
                continue
        out_lines.append(line)
    return "\n".join(out_lines)


def traceback_signature(exc_type: type | str, exc_value: BaseException | str, tb_text: str) -> str:
    """Stable short signature for dedupe (type + frames + message head)."""
    name = getattr(exc_type, "__name__", None) or str(exc_type)
    msg = redact(str(exc_value))[:200]
    frames = []
    for line in (tb_text or "").splitlines():
        line = line.strip()
        if line.startswith("File ") or (line and not line.startswith("Traceback")):
            frames.append(re.sub(r"[A-Za-z]:\\[^'\"\n]+", "<path>", line)[:160])
    tail = "|".join(frames[-6:])
    raw = f"{name}|{msg}|{tail}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def spool_dir(env: Optional[dict] = None) -> Path:
    e = os.environ if env is None else env
    override = (e.get("BOB_CRASH_SPOOL") or "").strip()
    if override:
        return Path(override)
    local = (e.get("LOCALAPPDATA") or e.get("TEMP") or str(Path.home())).strip()
    return Path(local).joinpath(*SPOOL_SUBDIR)


def _version_bits() -> dict[str, str]:
    out = {
        "exe": Path(sys.argv[0]).name if sys.argv else "python",
        "python": sys.version.split()[0],
        "machine": (os.environ.get("BOB_MACHINE_ID") or os.environ.get("COMPUTERNAME") or "").strip(),
    }
    for key in ("BOB_VERSION", "BOBIVERSE_VERSION", "GIT_SHA", "BOB_GIT_SHA"):
        v = (os.environ.get(key) or "").strip()
        if v:
            out[key.lower()] = v[:64]
    try:
        import ai_root
        out["ai_root"] = ai_root.find_ai_root()
    except Exception:
        pass
    return out


def format_issue_body(
    *,
    sig: str,
    exc_type: str,
    exc_value: str,
    tb_text: str,
    log_tail: str = "",
    extra: Optional[dict] = None,
) -> str:
    bits = _version_bits()
    if extra:
        bits.update({str(k): str(v)[:200] for k, v in extra.items()})
    lines = [
        f"<!-- {SIG_LABEL}:{sig} -->",
        f"crash-sig: `{sig}`",
        "",
        "### Process",
        "```",
        *[f"{k}={v}" for k, v in sorted(bits.items())],
        "```",
        "",
        f"### Exception",
        f"`{exc_type}: {redact(exc_value)[:500]}`",
        "",
        "### Traceback",
        "```",
        redact(tb_text)[:8000],
        "```",
    ]
    if log_tail:
        lines.extend(["", "### Log tail", "```", redact(log_tail)[:4000], "```"])
    lines.extend(["", "_Auto-filed by crash_report (FR #2411). Secrets redacted._"])
    return "\n".join(lines)


def _write_spool(payload: dict, directory: Optional[Path] = None) -> Path:
    d = directory or spool_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"crash-{int(time.time())}-{payload.get('sig', 'x')[:8]}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _load_spool(directory: Optional[Path] = None) -> list[tuple[Path, dict]]:
    d = directory or spool_dir()
    if not d.is_dir():
        return []
    out: list[tuple[Path, dict]] = []
    for f in sorted(d.glob("crash-*.json")):
        try:
            out.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


def find_open_by_sig(
    filer: Any,
    repo: str,
    sig: str,
    *,
    search: Optional[Callable[..., Any]] = None,
) -> Optional[int]:
    """Return open issue number with matching crash-sig, or None."""
    marker = f"{SIG_LABEL}:{sig}"
    if search is not None:
        for item in search(repo, marker) or []:
            body = str(item.get("body") or "")
            title = str(item.get("title") or "")
            if marker in body or sig in title:
                return int(item["number"])
        return None
    try:
        import shutil
        import subprocess

        gh = shutil.which("gh") or "gh"
        proc = subprocess.run(
            [
                gh, "issue", "list", "-R", repo, "--state", "open", "--limit", "50",
                "--search", f"crash-sig {sig} in:body", "--json", "number,title,body",
            ],
            capture_output=True, text=True, timeout=60, check=False,
            env=os.environ.copy(),
        )
        if proc.returncode != 0:
            return None
        for item in json.loads(proc.stdout or "[]"):
            if marker in str(item.get("body") or ""):
                return int(item["number"])
    except Exception:
        return None
    return None


def _comment_issue(filer: Any, repo: str, number: int, body: str) -> None:
    if hasattr(filer, "comment_issue"):
        filer.comment_issue(repo, number, body)
        return
    try:
        import shutil
        import subprocess

        gh = shutil.which("gh") or "gh"
        subprocess.run(
            [gh, "issue", "comment", str(number), "-R", repo, "--body", body],
            capture_output=True, text=True, timeout=60, check=False,
            env=os.environ.copy(),
        )
    except Exception:
        pass


def report_exception(
    exc_type: Any,
    exc_value: Any,
    exc_tb: Any,
    *,
    filer: Any = None,
    repo: str = REPO_DEFAULT,
    log_tail: str = "",
    spool: Optional[Path] = None,
    search: Optional[Callable[..., Any]] = None,
    create: bool = True,
) -> dict[str, Any]:
    """Build report; file or comment or spool. Never raises."""
    result: dict[str, Any] = {"ok": False, "action": "none"}
    try:
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        tname = getattr(exc_type, "__name__", str(exc_type))
        msg = str(exc_value)
        sig = traceback_signature(exc_type, exc_value, tb_text)
        exe_name = Path(sys.argv[0]).name if sys.argv else "python"
        title = f"crash: {exe_name} {tname}: {redact(msg)[:80]} [{sig}]"
        body = format_issue_body(
            sig=sig, exc_type=tname, exc_value=msg, tb_text=tb_text, log_tail=log_tail
        )
        payload = {
            "sig": sig,
            "title": title,
            "body": body,
            "repo": repo,
            "ts": time.time(),
        }
        result["sig"] = sig
        if not create:
            result["ok"] = True
            result["action"] = "dry"
            result["payload"] = payload
            return result

        existing = find_open_by_sig(filer, repo, sig, search=search)
        if existing:
            _comment_issue(
                filer,
                repo,
                existing,
                f"Repeat crash (sig `{sig}`) at {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                + redact(tb_text)[:3000],
            )
            result.update(ok=True, action="comment", number=existing)
            return result

        if filer is None:
            try:
                import gh_filer
                filer = gh_filer.default_filer()
            except Exception as exc:
                path = _write_spool(payload, spool)
                result.update(ok=True, action="spool", path=str(path), err=type(exc).__name__)
                return result

        try:
            created = filer.create_issue(
                repo, title, body, labels=["bug", "crash-auto"]
            )
            result.update(
                ok=True,
                action="create",
                number=int(created.get("number") or 0),
                url=str(created.get("url") or ""),
            )
            return result
        except Exception as exc:
            path = _write_spool(payload, spool)
            result.update(ok=True, action="spool", path=str(path), err=type(exc).__name__)
            return result
    except Exception as exc:  # noqa: BLE001
        result["err"] = type(exc).__name__
        return result


def flush_spool(
    *,
    filer: Any = None,
    spool: Optional[Path] = None,
    search: Optional[Callable[..., Any]] = None,
) -> list[dict[str, Any]]:
    """File or comment every spooled crash; delete on success. Never raises."""
    done: list[dict[str, Any]] = []
    try:
        if filer is None:
            try:
                import gh_filer
                filer = gh_filer.default_filer()
            except Exception:
                return done
        for path, payload in _load_spool(spool):
            try:
                sig = str(payload.get("sig") or "")
                repo = str(payload.get("repo") or REPO_DEFAULT)
                existing = find_open_by_sig(filer, repo, sig, search=search) if sig else None
                if existing:
                    _comment_issue(
                        filer, repo, existing, payload.get("body") or f"spooled crash {sig}"
                    )
                    action = "comment"
                    number = existing
                else:
                    created = filer.create_issue(
                        repo,
                        str(payload.get("title") or f"crash [{sig}]"),
                        str(payload.get("body") or ""),
                        labels=["bug", "crash-auto"],
                    )
                    action = "create"
                    number = int(created.get("number") or 0)
                path.unlink(missing_ok=True)
                done.append({"ok": True, "action": action, "number": number, "path": str(path)})
            except Exception as exc:
                done.append({"ok": False, "path": str(path), "err": type(exc).__name__})
    except Exception:
        pass
    return done


def _hook(exc_type, exc_value, exc_tb):
    try:
        report_exception(exc_type, exc_value, exc_tb)
    except Exception:
        pass
    try:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    except Exception:
        pass


def _thread_hook(args):
    try:
        report_exception(args.exc_type, args.exc_value, args.exc_traceback)
    except Exception:
        pass


def _asyncio_handler(loop, context):
    try:
        exc = context.get("exception")
        if exc is not None:
            report_exception(type(exc), exc, exc.__traceback__)
        else:
            report_exception(RuntimeError, RuntimeError(str(context.get("message") or context)), None)
    except Exception:
        pass


def install(*, flush: bool = True, product: str = "") -> bool:
    """Install sys / threading / asyncio hooks once. Returns True if newly installed."""
    global _INSTALLED
    with _LOCK:
        if _INSTALLED:
            return False
        sys.excepthook = _hook
        try:
            threading.excepthook = _thread_hook  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            import asyncio

            try:
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None:
                    loop.set_exception_handler(_asyncio_handler)
            except Exception:
                pass
            _orig = getattr(asyncio, "new_event_loop", None)
            if _orig and not getattr(asyncio, "_bob_crash_patched", False):
                def _new():
                    loop = _orig()
                    try:
                        loop.set_exception_handler(_asyncio_handler)
                    except Exception:
                        pass
                    return loop
                asyncio.new_event_loop = _new  # type: ignore[assignment]
                asyncio._bob_crash_patched = True  # type: ignore[attr-defined]
        except Exception:
            pass
        _INSTALLED = True
    if flush:
        try:
            flush_spool()
        except Exception:
            pass
    if product:
        os.environ.setdefault("BOB_CRASH_PRODUCT", product)
    return True


def is_installed() -> bool:
    return bool(_INSTALLED)


def _reset_for_tests() -> None:
    global _INSTALLED
    _INSTALLED = False
