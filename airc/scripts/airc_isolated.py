"""FR #5537: in-service isolated process for NETWORK / EXTENSION / LEGION work.

Spawns the same Python / frozen airc.exe with ``--isolated-job`` (stdin JSON,
stdout JSON). Not a peer product binary. Secrets never on argv.

FR #5665: child kill / empty / bad JSON returns ``error=worker_died`` (fail closed).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

try:
    import airc_fail_intake as _fail_intake
except Exception:  # pragma: no cover
    _fail_intake = None

_SECRET_KEY_RE = re.compile(r"(?i)pass|secret|token|pwd|cred")
_PACKAGED_MODULES = frozenset({"airc_legion", "airc_network", "airc_extension"})


def is_packaged_work(fn: Any) -> bool:
    """True when ``fn`` is a shipped airc_* default worker (safe to subprocess)."""
    if not callable(fn):
        return False
    name = getattr(fn, "__name__", "")
    if not name or name.startswith("<"):
        return False
    return getattr(fn, "__module__", "") in _PACKAGED_MODULES


def isolated_argv() -> list[str]:
    helper = Path(__file__).resolve()
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return [exe, "--isolated-job"]
    return [exe, str(helper)]


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("AIRC_LEGION_PASSWORD", None)
    # FR #5778: tell console info() to use stderr so stdout stays JSON-only.
    env["AIRC_ISOLATED_JOB"] = "1"
    return env


def _scrub_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (kwargs or {}).items():
        if _SECRET_KEY_RE.search(str(k)):
            continue
        if callable(v):
            continue
        out[k] = v
    return out


_DECODER = json.JSONDecoder()


def _last_json_dict(chunk: str) -> dict[str, Any] | None:
    """Return the last top-level JSON object in ``chunk`` (nested braces ignored).

    Walk with ``raw_decode`` end indexes so a later sibling object wins over an
    earlier one, while a nested object inside the result does not replace it.
    """
    last: dict[str, Any] | None = None
    idx = 0
    while True:
        start = chunk.find("{", idx)
        if start == -1:
            return last
        try:
            data, end = _DECODER.raw_decode(chunk, start)
        except (json.JSONDecodeError, ValueError):
            idx = start + 1
            continue
        if isinstance(data, dict):
            last = data
        idx = end


def extract_isolated_json_payload(stdout: str) -> dict[str, Any] | None:
    """FR #5778 / #7987: take the last JSON object from child stdout.

    Isolated workers must print one JSON object on stdout, but older builds and
    accidental ``print``/``info()`` calls can prefix or suffix log text on the
    same line (and BOM / UTF-16-as-cp1252 NUL bytes survive a pipe). Accept a
    JSON object anywhere in the blob, prefer the last top-level one, so a real
    result is not remapped to ``worker_died`` / ``bad-json`` (FR #7987).

    Whole-text JSON that is not a dict (array / string / number) returns
    ``None`` so the parent can report ``bad-payload``. Walk the full blob with
    ``_last_json_dict`` rather than a reverse line scan: a pretty-printed
    middle line like ``"hosts": [{"ok": true}]`` must not beat the outer object.
    """
    text = (stdout or "").replace("\x00", "").strip().lstrip("\ufeff")
    if not text:
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    else:
        return data if isinstance(data, dict) else None
    return _last_json_dict(text)


def is_worker_fault(payload: Any) -> bool:
    """FR #5665: True when child died / returned no usable verb result."""
    if not isinstance(payload, dict):
        return True
    err = str(payload.get("error") or "").strip().lower()
    if err == "worker_died" or err.startswith("isolated-fault:"):
        return True
    return False


def _worker_died(detail: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "worker_died",
        "detail": (detail or "no-result")[:200],
    }




def _parent_report_worker_died(module: str, func: str, detail: str) -> None:
    """FR #5775: parent reports when isolated child dies without a verb report.

    FR #5783: no-op under PYTEST_CURRENT_TEST / crash_report policy deny so
    test_fr5665 fake runners do not flood live intake twins.
    """
    if _fail_intake is None:
        return
    try:
        if hasattr(_fail_intake, "intake_allowed") and not _fail_intake.intake_allowed():
            return
        verb = func or module or 'isolated'
        _fail_intake.report_verb_failure(
            verb,
            'worker_died',
            args={'module': module, 'func': func, 'detail': (detail or '')[:200]},
            wait_s=1.0,
        )
    except Exception:
        pass


def call_isolated_module(
    module: str,
    func: str,
    kwargs: dict[str, Any] | None = None,
    *,
    timeout_s: float = 900,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Run ``module.func(**kwargs)`` in a child process. Returns a JSON object.

    FR #5665: non-zero exit, empty stdout, timeout, or bad JSON =>
    ``error=worker_died`` (fail closed). Never invent an empty success payload.
    FR #5778: tolerate leading log lines on stdout by extracting the JSON object.
    """
    spec = {
        "module": module,
        "func": func,
        "kwargs": _scrub_kwargs(kwargs or {}),
    }
    run = runner or subprocess.run
    try:
        p = run(
            isolated_argv(),
            input=json.dumps(spec, separators=(",", ":")),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=_child_env(),
        )
    except subprocess.TimeoutExpired as exc:
        _parent_report_worker_died(module, func, f"timeout:{type(exc).__name__}")
        return _worker_died(f"timeout:{type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        _parent_report_worker_died(module, func, f"spawn:{type(exc).__name__}")
        return _worker_died(f"spawn:{type(exc).__name__}")
    stdout = (p.stdout or "").strip()
    stderr = (p.stderr or "").strip()
    if p.returncode != 0:
        err_lines = (stderr or stdout).splitlines()
        reason = err_lines[-1] if err_lines else f"exit-{p.returncode}"
        detail = reason[:80]
        _parent_report_worker_died(module, func, detail)
        return _worker_died(detail)
    if not stdout:
        _parent_report_worker_died(module, func, "empty-stdout")
        return _worker_died("empty-stdout")
    data = extract_isolated_json_payload(stdout)
    if data is None:
        try:
            json.loads(stdout)
        except json.JSONDecodeError:
            reason = "bad-json"
        else:
            reason = "bad-payload"
        _parent_report_worker_died(module, func, reason)
        return _worker_died(reason)
    return data


def start_isolated(
    *,
    wait: bool,
    run: Callable[[], Any],
    packaged: tuple[str, str, dict[str, Any]] | None = None,
    name: str = "airc-isolated",
    on_done: Callable[[Any], Any] | None = None,
) -> Any:
    """``wait``: run now. Else packaged default -> child process; injected fn -> thread."""

    def _finish(result: Any) -> Any:
        if on_done is not None:
            on_done(result)
        return result

    if wait:
        return _finish(run())

    def _bg() -> None:
        try:
            if packaged is not None:
                module, func, kwargs = packaged
                _finish(call_isolated_module(module, func, kwargs))
            else:
                _finish(run())
        except Exception as exc:  # noqa: BLE001
            _finish({"ok": False, "error": type(exc).__name__})

    threading.Thread(target=_bg, name=name, daemon=True).start()
    return None


def _write_isolated_result(payload: dict[str, Any], stream: Any) -> None:
    """Write the one JSON result to the IPC stream (never raises)."""
    text = json.dumps(payload, separators=(",", ":"))
    try:
        if stream is not None:
            print(text, file=stream, flush=True)
        else:
            os.write(1, (text + "\n").encode("utf-8", "replace"))
    except (BrokenPipeError, OSError):
        pass


def isolated_job_main(argv: list[str] | None = None) -> int:
    """Child entry: read spec on stdin, call packaged func, print JSON."""
    # FR #5778: even when launched without parent _child_env, keep stdout JSON-only.
    os.environ.setdefault("AIRC_ISOLATED_JOB", "1")
    real_stdout = sys.stdout
    raw = sys.stdin.read()
    try:
        spec = json.loads(raw or "{}")
    except json.JSONDecodeError:
        _write_isolated_result(
            {"ok": False, "error": "isolated-fault:bad-spec"}, real_stdout
        )
        return 2
    module = str(spec.get("module") or "")
    func = str(spec.get("func") or "")
    if module not in _PACKAGED_MODULES or not func.isidentifier():
        _write_isolated_result(
            {"ok": False, "error": "isolated-fault:refused-target"}, real_stdout
        )
        return 2
    kwargs = spec.get("kwargs") if isinstance(spec.get("kwargs"), dict) else {}
    kwargs = _scrub_kwargs(kwargs)
    try:
        mod = __import__(module, fromlist=[func])
        fn = getattr(mod, func)
        # FR #7987: keep the IPC channel JSON-only even when an older build or a
        # dependency prints to stdout during the work.
        prev_stdout = sys.stdout
        if sys.stderr is not None:
            sys.stdout = sys.stderr
        try:
            data = fn(**kwargs)
        finally:
            sys.stdout = prev_stdout
    except Exception as exc:  # noqa: BLE001
        if _fail_intake is not None:
            try:
                _fail_intake.report_verb_failure(
                    func or module or 'isolated',
                    exc,
                    args={'module': module, 'func': func},
                    wait_s=0,
                )
            except Exception:
                pass
        _write_isolated_result(
            {"ok": False, "error": type(exc).__name__}, real_stdout
        )
        return 1
    if not isinstance(data, dict):
        data = {"ok": True, "result": str(type(data).__name__)}
    _write_isolated_result(data, real_stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(isolated_job_main())
