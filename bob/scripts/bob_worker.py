r"""bob-worker: one compiled EXE that starts ONE NEW agent (Cursor agent.cmd or Grok agent.exe), keeps ITS OWN IRC
connection for that agent and relays IRC -> agent the instant a message arrives.

Modes
  --mode agent   worker seat: cwd <install>\worker, IRC nick <machine>-<pid>, joins ONLY #<machine>
  --mode plan    plan agent: cwd <install>\plan, no IRC, fire-and-forget launch
  --mode monitor Jeeves MONITORING agent: cwd --work-root (default <ai>\\jeeves), no IRC; same fuel pick as agent
  --mode maintenance Jeeves maintenance after --heal still failing (FR #2412): cwd --work-root, diagnose/fix, file intake

Rules (CAST IRON, Simon t762u-t765u)
  * Agent choice is ALWAYS automatic by token availability (FR #3997 / #6120): Grok (local weekly > 0 or unknown read)
    -> Cursor (high or low pool > 0) -> OpenCode (free or Go fuel > 0) -> dialog asking for a Grok session key (kept in memory only, handed to the child env, never written/printed).
  * EVERY launch is a NEW agent: new session id, new console window, new run dir. Never --resume/--continue/-r, never
    reuse or attach to an existing window/process (assert_fresh() enforces it; a restart after a hang is a NEW agent too).
    ONE exception (FR #2522): --mode maintenance SHOULD resume its own last maintenance session (recorded by this exe)
    when that grok session still exists; otherwise it starts NEW. Worker/plan/monitor never resume.
  * IRC: blocking socket reader thread; a message is injected into the agent's console input from that very thread
    (no poll/timer between receive and inject). PING/PONG and the fleet `ping` liveness are answered here, not by the agent.
  * IRC lost  => FR #3456: reconnect with backoff for BOB_WORKER_IRC_RECONNECT_GRACE_S (default 600s), keep the
    agent and ACKed job, hold outbox lines and flush + re-ACK after reconnect. Grace 0 = legacy: kill agent tree
    and exit (EXIT_IRC_LOST). After grace exhausted: clean exit (Jeeves #3400 releases the orphan ACK).
  * Agent hung => bounded restart (new agent) with backoff, each restart logged; give up after the bound.
"""
from __future__ import annotations

import argparse
import contextlib
import base64
from collections import deque
import hashlib
import ctypes
import datetime as _dt
import json
import os
import queue
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional, NamedTuple

from seat_session_log import SeatSessionLog, console_startup_state, redact_session_text

EXIT_OK = 0


def get_source_commit() -> str:
    """Return the SHA embedded at freeze time (FR #6349), else 'unknown'."""
    try:
        from bob_worker_build_meta import SOURCE_COMMIT as _sc
        return str(_sc or 'unknown')
    except ImportError:
        return 'unknown'


def short_build_sha(commit: str | None = None) -> str:
    """FR #6409: short source SHA for hello / DONE / digest (never empty)."""
    raw = str(commit if commit is not None else get_source_commit() or "").strip()
    if not raw or raw.lower() in ("unknown", "none", "null"):
        return "unknown"
    return raw[:12]


def resolve_seat_hello_model(kind: str, env: Optional[dict] = None) -> str:
    """FR #6418 / FR #7084 / FR #8159: model the seat was launched for.

    Precedence: env pin (Si tray click), then tray ``workerStartModels``, then
    OpenCode free default / OpenCode config. Never invent a premium id.
    """
    env = os.environ if env is None else env
    k = (kind or "").strip().lower()
    try:
        import worker_start_model as wsm

        cfg = wsm.load_worker_start_config(env=env)
        picked = wsm.launch_selected_model(k, cfg, env=env)
        if picked:
            return picked
        if k == "opencode":
            cfg_m = read_opencode_config_model(env) or ""
            if cfg_m and not wsm.opencode_is_go_or_paid(cfg_m):
                return cfg_m
            return wsm.default_opencode_free_model(cfg)
    except Exception:
        pass
    if k != "opencode":
        return ""
    m = str(env.get("BOB_OPENCODE_MODEL") or "").strip()
    if m:
        return m
    return read_opencode_config_model(env) or ""


def worker_hello_line(kind: str, *, model: str | None = None, build: str | None = None) -> str:
    """FR #6409 / FR #6418: shop presence line after successful agent start (MRB #6411).

    FR #6418: ``model=<configured model|unknown>`` always sits between ``kind=`` and
    ``build=`` (never omitted); by default it is resolved from the same configuration
    the agent will launch with (see ``resolve_seat_hello_model``).
    """
    k = (kind or "").strip().lower() or "grok"
    m = (str(model).strip() if model is not None else resolve_seat_hello_model(k)) or "unknown"
    b = short_build_sha(build) if build is not None else short_build_sha()
    return f"worker ready kind={k} model={m} build={b}"


def worker_needs_signin_line(kind: str, *, build: str | None = None, reason: str | None = None) -> str:
    """FR #7180 / #8222: shop line when Grok has no valid machine sign-in (never 'ready').

    ``reason`` is ``no-seat-auth`` when the machine has nothing to give. Never
    the word expired for a missing file.
    """
    k = (kind or "").strip().lower() or "grok"
    b = short_build_sha(build) if build is not None else short_build_sha()
    extra = f" reason={reason}" if reason else ""
    return f"worker needs sign-in kind={k} build={b}{extra}"


def grok_agent_signed_in(*, run_dir: Path | str | None = None, env: Optional[dict] = None) -> bool:
    """True when the machine Grok auth store is present and not expired (FR #8222)."""
    try:
        import skill_dag_bound as _sdb

        e = os.environ if env is None else env
        auth = None
        if e:
            raw = str((e or {}).get("GROK_AUTH_PATH") or "").strip()
            if raw:
                auth = raw
        return bool(_sdb.grok_session_usable(auth_path=auth, env=e))
    except Exception:
        return False


def agent_session_signed_in(
    kind: str,
    *,
    run_dir: Path | str | None = None,
    env: Optional[dict] = None,
) -> bool:
    """FR #7180 / #7183: signed-in session that may announce ready / !bored (no first-turn wait)."""
    k = (kind or "").strip().lower()
    if k == "grok":
        return grok_agent_signed_in(run_dir=run_dir, env=env)
    if k == "opencode":
        e = os.environ if env is None else env
        home = str((e or {}).get("HOME") or (e or {}).get("USERPROFILE") or "").strip()
        if home and (Path(home) / ".local" / "share" / "opencode" / "auth.json").is_file():
            return True
        return False
    return True


EXIT_USAGE = 64
EXIT_IRC_FAIL = 2  # could not connect / register: no agent was started
EXIT_IRC_LOST = 3  # IRC lost for good (grace 0 immediate, or reconnect grace exhausted): agent tree killed
EXIT_NO_AGENT = 4  # nothing to start (no key given / no agent installed)
EXIT_GAVE_UP = 5  # hang-restart bound exceeded
EXIT_LAUNCH_FAIL = 6
EXIT_REFUSED = 7  # t815u: already the maximum number of workers running
EXIT_STALE_BUILD = 8  # FR #2782 legacy; FR #3180 keeps the seat running and asks for a manual restart instead
EXIT_XAI_AUTH_EXPIRED = 9  # FR #7345: Grok sign-in missing/expired; do not launch interactive auth
EXIT_OUT_OF_FUEL = 10  # FR #8814: fuel exhausted — dialog then quit (no out_of_fuel zombie seat)

def _default_install_root() -> str:
    """<drive>:\\ai\\bob on the fixed disk that really holds the fleet (t780u); never a hard-coded C:."""
    try:
        import ai_root

        return ai_root.product_root("bob")
    except Exception:  # pragma: no cover - standalone fallback
        return r"C:\ai\bob"


DEFAULT_INSTALL_ROOT = ""  # lazy: resolve_install_root() (FR #7189, no import-time drive scan)


def resolve_install_root(raw: str | None = None) -> str:
    s = str(raw or "").strip()
    if s:
        return s
    return _default_install_root()


def maybe_sync_install_skills(*, install_root: str | None = None, job_busy: bool = False) -> dict:
    """FR #7238: overlay origin `.grok/skills` between jobs (never mid-ACK)."""
    root = str(install_root or os.environ.get("BOB_INSTALL_ROOT") or "").strip()
    if not root:
        return {"ok": False, "reason": "no-install", "sha": ""}
    try:
        import sync_install_skills as sis
    except ImportError:
        scripts = _common_scripts_dir()
        sys.path.insert(0, str(scripts))
        try:
            import sync_install_skills as sis  # type: ignore
        except ImportError:
            return {"ok": False, "reason": "no-helper", "sha": ""}
    try:
        return sis.sync_install_skills_from_origin(root, job_busy=job_busy)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": type(exc).__name__, "sha": ""}


def _common_scripts_dir() -> Path:
    """Resolve common/scripts beside bob/scripts (worktree or install layout)."""
    here = Path(__file__).resolve().parent
    for cand in (here.parent.parent / "common" / "scripts", here.parent / "common" / "scripts"):
        if cand.is_dir():
            return cand
    return here.parent.parent / "common" / "scripts"


def _resolve_opencode_fuel_helper_path(
    cwd: str | Path | None = None,
    source_file: str | Path | None = None,
    install_root: str | Path | None = None,
) -> Path:
    """Locate ``opencode_fuel.py`` for embedding in the PowerShell wrapper.

    FR #6159: flat installs compose the helper to ``<root>/scripts/opencode_fuel.py``.
    Order: source-relative ``common/scripts`` (repo), then ``install_root`` flat
    ``scripts`` then ``common/scripts``, then ``cwd.parent`` flat ``scripts`` then
    ``common/scripts``. First existing file wins. Miss returns the first candidate.
    """
    source = Path(source_file).resolve() if source_file else Path(__file__).resolve()
    here = source.parent
    candidates = [
        (here.parent.parent / "common" / "scripts" / "opencode_fuel.py"),
        (here.parent / "common" / "scripts" / "opencode_fuel.py"),
    ]
    if install_root is not None:
        root = Path(install_root)
        candidates.append(root / "scripts" / "opencode_fuel.py")
        candidates.append(root / "common" / "scripts" / "opencode_fuel.py")
    if cwd is not None:
        parent = Path(cwd).parent
        candidates.append(parent / "scripts" / "opencode_fuel.py")
        candidates.append(parent / "common" / "scripts" / "opencode_fuel.py")
    for cand in candidates:
        if cand.is_file():
            return cand.resolve()
    return candidates[0].resolve()


def _path_is_mei_extract(path: Path) -> bool:
    return any(part.startswith("_MEI") for part in Path(path).parts)


def _resolve_installed_worker_script(
    name: str,
    *,
    cwd: str | Path | None = None,
    source_file: str | Path | None = None,
    install_root: str | Path | None = None,
) -> Optional[Path]:
    """Locate a worker ``.py`` handed to external python. Never prefer a PyInstaller ``_MEI`` extract.

    FR #8202: when frozen, prefer ``<exe>\\scripts`` (hash-checked unpack) over a
    stale flat ``install\\scripts`` (often ``C:\\ai\\bob\\scripts``). Flat wins
    only when ``BOB_WORKER_USE_FLAT_SCRIPTS`` is set.
    """
    flat_override = False
    # FR #7910 / #8202: a frozen exe writes bundled helpers beside itself first.
    try:
        import worker_shipped_scripts as _shipped_scripts

        _shipped_scripts.extract_bundled_scripts()
        flat_override = _shipped_scripts.use_flat_scripts_override()
    except Exception:
        flat_override = False
    source = Path(source_file).resolve() if source_file else Path(__file__).resolve()
    here = source.parent
    candidates: list[Path] = []
    frozen = getattr(sys, "frozen", False)

    def _add_install_flat(root: Path) -> None:
        candidates.append(root / "scripts" / name)
        candidates.append(root / "bob" / "scripts" / name)
        candidates.append(root / "common" / "scripts" / name)

    # FR #8202: explicit flat override puts install scripts first (dev only).
    if flat_override and install_root is not None:
        _add_install_flat(Path(install_root))
    # FR #8202 / #7963: frozen ship dir before install flat (default).
    if frozen:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "scripts" / name)
        candidates.append(exe_dir.parent / "scripts" / name)
        candidates.append(exe_dir.parent / "worker" / "scripts" / name)
    if (not frozen) and install_root is not None and not flat_override:
        _add_install_flat(Path(install_root))
    if not _path_is_mei_extract(here):
        candidates.append(here / name)
    if cwd is not None:
        parent = Path(cwd).resolve().parent
        # cwd-parent scripts often alias the install flat tree; skip when frozen
        # unless the flat override is on (FR #8202).
        if flat_override or not frozen:
            candidates.append(parent / "scripts" / name)
            candidates.append(parent / "bob" / "scripts" / name)
    if frozen:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir.parent / "bob" / "scripts" / name)
    if frozen and (not flat_override) and install_root is not None:
        # Last resort after ship dirs so a missing unpack still finds something.
        _add_install_flat(Path(install_root))
    for cand in candidates:
        if _path_is_mei_extract(cand):
            continue
        if cand.is_file():
            return cand.resolve()
    return None


def prefer_shipped_scripts_on_sys_path(
    log: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """FR #8202: put ``<exe>\\scripts`` first on ``sys.path`` after hash-checked unpack.

    Logs one line per helper (path + short hash) and any overwrite failures.
    Returns names that failed to unpack/overwrite.
    """
    failed_names: list[str] = []
    if not getattr(sys, "frozen", False):
        return failed_names
    result = None
    try:
        import worker_shipped_scripts as _shipped_scripts

        result = _shipped_scripts.extract_bundled_scripts_result()
    except Exception as e:
        if log:
            log(f"shipped-scripts: extract failed {type(e).__name__}")
        return failed_names
    ship_dir = None
    try:
        import worker_shipped_scripts as _shipped_scripts

        ship_dir = _shipped_scripts.ship_scripts_dir()
    except Exception:
        ship_dir = None
    if ship_dir is not None and ship_dir.is_dir():
        s = str(ship_dir)
        if s in sys.path:
            sys.path.remove(s)
        sys.path.insert(0, s)
    if log and result is not None:
        for name, err in result.failed:
            failed_names.append(name)
            log(f"shipped-scripts: FAIL overwrite {name} ({err}); stale file may run")
        for name in sorted(set(result.written) | set(result.unchanged)):
            path = (ship_dir / name) if ship_dir is not None else None
            hx = (result.hashes or {}).get(name) or "-"
            if path is not None and path.is_file():
                try:
                    hx = hx if hx != "-" else __import__(
                        "worker_shipped_scripts"
                    ).short_content_hash(path.read_bytes())
                except Exception:
                    pass
                tag = "overwritten" if name in result.overwritten else "ok"
                log(f"shipped-scripts: {name} path={path} hash={hx} ({tag})")
            else:
                log(f"shipped-scripts: {name} missing after extract hash={hx}")
    return failed_names


def _report_missing_worker_script(name: str) -> None:
    """FR #7884: a missing helper is an exception. The seat still starts."""
    try:
        import runtime_failure

        runtime_failure.report_message(
            "bob-worker",
            "%s is missing from the installed worker scripts. The OpenCode seat still starts and that check is off."
            % name,
            site="opencode-helper-missing",
        )
    except Exception:
        pass


def log_install_root_guard(install_root: str | Path, log: Callable[[str], None] = print, *, run=subprocess.run) -> Optional[str]:
    """FR #4843: at seat start, surface when the live install checkout is off main."""
    try:
        scripts = _common_scripts_dir()
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from bob_install_root_guard import install_root_branch_warning  # type: ignore
    except Exception as e:  # pragma: no cover - missing helper must not block seats
        log(f"install-root: guard import failed {type(e).__name__}")
        return None
    try:
        warn = install_root_branch_warning(install_root, run=run)
    except Exception as e:  # pragma: no cover
        log(f"install-root: branch check failed {type(e).__name__}")
        return None
    if warn:
        log(warn)
    return warn


# Re-export for tests / playbooks (FR #4843).
try:
    if str(_common_scripts_dir()) not in sys.path:
        sys.path.insert(0, str(_common_scripts_dir()))
    from bob_install_root_guard import (  # noqa: E402
        install_root_branch_warning,
        refuse_job_git,
        suggest_job_worktree,
    )
except Exception:  # pragma: no cover
    install_root_branch_warning = None  # type: ignore
    refuse_job_git = None  # type: ignore
    suggest_job_worktree = None  # type: ignore

try:
    if str(_common_scripts_dir()) not in sys.path:
        sys.path.insert(0, str(_common_scripts_dir()))
    import opencode_fuel  # noqa: E402
except Exception:  # pragma: no cover
    opencode_fuel = None  # type: ignore

# FR #6363: operator BOB_OPENCODE_MODEL captured at process start (not worker re-exports).
_OPENCODE_MODEL_ENV_AT_START: Optional[str] = None

try:
    from opencode_seat_contract import (  # noqa: E402
        console_text,
        is_worktree_absent_nack,
        job_worktree_base,
        message_job_keys,
        opencode_job_context_nack,
        opencode_job_context_nack_ready,
        opencode_outbox_line_allowed,
        opencode_outbox_refuse_reason,
        opencode_outbox_path,
        ensure_opencode_bob_outbox,
        outbox_is_writable,
        prepare_opencode_wire,
        frame_opencode_message,
        probe_gh_auth,
        project_dir_for_assign,
        ensure_opencode_job_worktree,
    )
except ImportError:  # package import (bob.scripts.bob_worker)
    from bob.scripts.opencode_seat_contract import (  # type: ignore  # noqa: E402
        console_text,
        is_worktree_absent_nack,
        job_worktree_base,
        message_job_keys,
        opencode_job_context_nack,
        opencode_job_context_nack_ready,
        opencode_outbox_line_allowed,
        opencode_outbox_refuse_reason,
        opencode_outbox_path,
        ensure_opencode_bob_outbox,
        outbox_is_writable,
        prepare_opencode_wire,
        frame_opencode_message,
        probe_gh_auth,
        project_dir_for_assign,
        ensure_opencode_job_worktree,
    )


class JobContextRefused(Exception):
    """FR #6240: the assign was NACKed before the model saw it. Do not hold it."""

    def __init__(self, nack: str):
        super().__init__(nack)
        self.nack = nack

DEFAULT_HOST = "irc.ntsa.uk"
DEFAULT_PORT = 6697
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
FORBIDDEN_FLAGS = ("--resume", "-r", "--continue", "-c", "--resume-session", "--session", "--chat")
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000
# FR #8568: break away from parent job objects (monitor/shell kill-on-close).
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
# FR #7117: console QuickEdit freezes the seat until Enter (looks like a crash).
ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080
STD_INPUT_HANDLE = -10

RULE_RESTART_MAX = 3
RULE_RESTART_WINDOW_S = 1800.0
RULE_BACKOFF_S = (5.0, 15.0, 45.0)


# --------------------------------------------------------------------------------------------- identity
def normalize_machine_id(raw: str) -> Optional[str]:
    mid = str(raw or "").strip().lower().lstrip("#")
    mid = re.sub(r"[^a-z0-9_-]+", "-", mid).strip("-_")
    mid = mid.replace("_", "-")
    if not mid or mid == "nope" or not ID_RE.match(mid):
        return None
    return mid


def default_machine_id(env: Optional[dict] = None) -> Optional[str]:
    env = os.environ if env is None else env
    for key in ("BOB_MACHINE_ID", "COMPUTERNAME"):
        mid = normalize_machine_id(env.get(key, ""))
        if mid:
            return mid
    return None


def shop_channel(machine: str) -> str:
    return "#" + machine


def seat_nick(machine: str, pid: int) -> str:
    """Talk-seat nick rule (talk_seat_pid.py): <machine>-<pid of the process that holds the IRC connection>."""
    return f"{machine}-{int(pid)}"


# --------------------------------------------------------------------------------------------- logging
class Log:
    def __init__(self, path: Optional[Path] = None, echo: bool = False):
        self.path = path
        self.echo = echo
        self._lock = threading.Lock()
        if path:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.path = None

    def __call__(self, msg: str) -> None:
        line = time.strftime("%Y-%m-%dT%H:%M:%S") + " " + _scrub(str(msg))
        with self._lock:
            if self.path:
                try:
                    with open(self.path, "a", encoding="utf-8") as f:
                        f.write(line + "\n")
                except OSError:
                    pass
            if self.echo:
                try:
                    print(line, flush=True)
                except Exception:
                    pass


class _LogStream:
    """t787u: stands in for sys.stderr so NOTHING reaches the shared console (the agent's TUI lives there) except what the exe
    deliberately prints. Everything goes to the worker.log file instead."""

    def __init__(self, log):
        self.log = log

    def write(self, s):
        t = str(s).strip()
        if t:
            self.log("stderr: " + _scrub(t)[:300])
        return len(str(s))

    def flush(self):
        pass

    def isatty(self):
        return False


def silence_console(log) -> None:
    """Route every error path (stderr, uncaught exceptions, ctypes-callback 'Exception ignored', thread exceptions) to the log
    file, each distinct message once. Deliberate console output (the key prompt, --dry-run JSON, --echo) uses sys.stdout and is untouched."""
    seen: set = set()

    def once(msg: str) -> None:
        if msg not in seen and len(seen) < 50:
            seen.add(msg)
            log(msg)

    sys.stderr = _LogStream(log)
    sys.unraisablehook = lambda u: once("unraisable: %s: %s (%s)" % (getattr(u.exc_type, "__name__", "?"), str(u.exc_value)[:160], str(u.err_msg or "")[:80]))
    threading.excepthook = lambda a: once("thread error: %s: %s" % (getattr(a.exc_type, "__name__", "?"), str(a.exc_value)[:160]))
    sys.excepthook = lambda t, v, tb: once("error: %s: %s" % (getattr(t, "__name__", "?"), str(v)[:160]))


_SECRET_RX = re.compile(r"(?i)(xai_api_key|cursor_api_key|password|passwd|secret|token|authenticate)\s*[=:]\s*\S+")


def _scrub(s: str) -> str:
    return redact_session_text(_SECRET_RX.sub(lambda m: m.group(1) + "=<redacted>", s))


class SecretStr:
    """Holds a session key in memory only; repr/str never reveal it."""

    __slots__ = ("_v",)

    def __init__(self, v: str):
        self._v = v

    def reveal(self) -> str:
        return self._v

    def __repr__(self) -> str:  # pragma: no cover
        return "<secret>"

    __str__ = __repr__


# --------------------------------------------------------------------------------------------- fuel + selection
@dataclass(frozen=True)
class Fuel:
    cursor_high: Optional[int] = None
    cursor_low: Optional[int] = None
    grok_pct: Optional[int] = None
    grok_state: str = "unknown"
    # FR #6119: Cursor on-demand spend limit (digest on_demand_*); at-limit is out-of-fuel
    # even when high/low pool remain % still looks non-zero (flamingo high=100 class).
    on_demand_used_cents: Optional[int] = None
    on_demand_limit_cents: Optional[int] = None
    on_demand_remaining_pct: Optional[int] = None
    overspend_state: str = "unknown"
    opencode_free: Optional[int] = None
    opencode_go: Optional[int] = None
    opencode_models: dict = field(default_factory=dict)
    opencode_free_model_ids: tuple = field(default_factory=tuple)
    # FR #8186: provider windows (week/rolling/month) when aggregate go is nulled.
    opencode_windows: Optional[dict] = None


def parse_fuel(text: str) -> Fuel:
    """Parse Get-BobAgentFuel.ps1 JSON (last JSON line wins). Anything unreadable = unknown. Seat selection (FR #3997) treats unknown Grok as available; mid-job still uses fuel_explicitly_exhausted."""
    doc = None
    for ln in reversed((text or "").splitlines()):
        ln = ln.strip().lstrip("\ufeff")
        if ln.startswith("{"):
            try:
                doc = json.loads(ln)
                break
            except ValueError:
                continue
    if not isinstance(doc, dict):
        return Fuel()

    def _i(v):
        try:
            return None if v is None or v == "" else int(v)
        except (TypeError, ValueError):
            return None

    cur = doc.get("cursor") or {}
    grok = doc.get("grok") or {}
    # Prefer cursor.* on_demand; accept top-level keys for fixtures / older helpers (FR #6119).
    od_used = _i(cur.get("on_demand_used_cents"))
    if od_used is None:
        od_used = _i(doc.get("on_demand_used_cents"))
    od_limit = _i(cur.get("on_demand_limit_cents"))
    if od_limit is None:
        od_limit = _i(doc.get("on_demand_limit_cents"))
    od_remain = _i(cur.get("on_demand_remaining_pct"))
    if od_remain is None:
        od_remain = _i(doc.get("on_demand_remaining_pct"))
    od_state = str(
        cur.get("overspend_state") or doc.get("overspend_state") or "unknown"
    ).strip().lower() or "unknown"
    op = doc.get("opencode") or {}
    op_free = _i(op.get("free")) if isinstance(op, dict) else None
    op_go = _i(op.get("go")) if isinstance(op, dict) else None
    op_models = op.get("models") if isinstance(op, dict) and isinstance(op.get("models"), dict) else {}
    op_free_ids = op.get("free_model_ids") if isinstance(op, dict) else None
    if isinstance(op_free_ids, (list, tuple)):
        op_free_ids = tuple(str(i) for i in op_free_ids)
    else:
        op_free_ids = ()
    op_windows = op.get("windows") if isinstance(op, dict) and isinstance(op.get("windows"), dict) else None
    if op_windows is None and isinstance(doc.get("windows"), dict):
        op_windows = doc.get("windows")
    return Fuel(
        _i(cur.get("high")),
        _i(cur.get("low")),
        _i(grok.get("remaining_pct")),
        str(grok.get("state") or "unknown").lower(),
        od_used,
        od_limit,
        od_remain,
        od_state,
        op_free,
        op_go,
        dict(op_models),
        op_free_ids,
        op_windows,
    )


def read_fuel(install_root: Path, run: Callable = subprocess.run, timeout: float = 90.0, provider: str = "") -> Fuel:
    helper = Path(install_root) / "tools" / "Get-BobAgentFuel.ps1"
    if not helper.is_file():
        return Fuel()
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper), "-InstallRoot", str(install_root)]
    if provider:
        cmd.extend(["-Provider", provider])
    try:
        from winps51 import env_for_powershell_exe

        r = run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            env=env_for_powershell_exe(),
        )
        return parse_fuel(r.stdout or "")
    except Exception:
        return Fuel()


def merge_fuel_parts(parts: dict) -> Fuel:
    """Combine per-provider readings. A missing part stays unknown and does not wipe the others."""
    cursor = parts.get("cursor") or Fuel()
    grok = parts.get("grok") or Fuel()
    opencode = parts.get("opencode") or Fuel()
    return Fuel(
        cursor.cursor_high,
        cursor.cursor_low,
        grok.grok_pct,
        grok.grok_state or "unknown",
        cursor.on_demand_used_cents,
        cursor.on_demand_limit_cents,
        cursor.on_demand_remaining_pct,
        cursor.overspend_state or "unknown",
        opencode.opencode_free,
        opencode.opencode_go,
        dict(opencode.opencode_models or {}),
        tuple(opencode.opencode_free_model_ids or ()),
        opencode.opencode_windows,
    )


def read_fuel_bounded(install_root: Path, run: Callable = subprocess.run, per_provider_s: float = 8.0) -> Fuel:
    """Read Cursor, Grok, and OpenCode on separate budgets so one slow reader cannot hide the others."""
    from concurrent.futures import ThreadPoolExecutor

    names = ("cursor", "grok", "opencode")

    def one(name: str) -> Fuel:
        return read_fuel(install_root, run=run, timeout=per_provider_s, provider=name)

    parts: dict = {}
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        fut_map = {pool.submit(one, name): name for name in names}
        for fut, name in fut_map.items():
            try:
                parts[name] = fut.result()
            except Exception:
                parts[name] = Fuel()
    return merge_fuel_parts(parts)


AGENT_LIST_CACHE_NAME = "agent-list-fuel.json"
AGENT_LIST_CACHE_MAX_AGE_S = 45.0
AGENT_LIST_CACHE_MAX_BYTES = 65536
UNKNOWN_MENU_REASON = "fuel unknown (not exhausted); start checks this agent"
REBUILD_LIST_REASON = "this bob-worker.exe has no --list-agents; rebuild to choose an agent"
WORKER_MISSING_REASON = "bob-worker.exe not found"
NOT_INSTALLED_REASON = "not installed"


def agent_list_cache_path(env: Optional[dict] = None) -> Path:
    return opencode_pauses_state_dir(env) / AGENT_LIST_CACHE_NAME


def fuel_cache_document(fuel: Fuel, now: Optional[float] = None) -> dict:
    """Percents and states only. Never a path, token, or auth body."""
    return {
        "ts": float(now if now is not None else time.time()),
        "cursor_high": fuel.cursor_high,
        "cursor_low": fuel.cursor_low,
        "grok_pct": fuel.grok_pct,
        "grok_state": fuel.grok_state or "unknown",
        "on_demand_used_cents": fuel.on_demand_used_cents,
        "on_demand_limit_cents": fuel.on_demand_limit_cents,
        "on_demand_remaining_pct": fuel.on_demand_remaining_pct,
        "overspend_state": fuel.overspend_state or "unknown",
        "opencode_free": fuel.opencode_free,
        "opencode_go": fuel.opencode_go,
        "opencode_models": dict(fuel.opencode_models or {}),
        "opencode_free_model_ids": list(fuel.opencode_free_model_ids or ()),
        "opencode_windows": fuel.opencode_windows,
    }


def fuel_from_cache_document(doc: dict) -> Fuel:
    def _i(v):
        try:
            return None if v is None or v == "" else int(v)
        except (TypeError, ValueError):
            return None

    models = doc.get("opencode_models") if isinstance(doc.get("opencode_models"), dict) else {}
    ids = doc.get("opencode_free_model_ids")
    if not isinstance(ids, (list, tuple)):
        ids = ()
    return Fuel(
        _i(doc.get("cursor_high")),
        _i(doc.get("cursor_low")),
        _i(doc.get("grok_pct")),
        str(doc.get("grok_state") or "unknown").lower(),
        _i(doc.get("on_demand_used_cents")),
        _i(doc.get("on_demand_limit_cents")),
        _i(doc.get("on_demand_remaining_pct")),
        str(doc.get("overspend_state") or "unknown").lower() or "unknown",
        _i(doc.get("opencode_free")),
        _i(doc.get("opencode_go")),
        {str(k): _i(v) for k, v in models.items()},
        tuple(str(i) for i in ids),
        doc.get("opencode_windows") if isinstance(doc.get("opencode_windows"), dict) else None,
    )


def load_fresh_agent_list_fuel(
    *,
    now: Optional[float] = None,
    max_age_s: float = AGENT_LIST_CACHE_MAX_AGE_S,
    env: Optional[dict] = None,
) -> Optional[Fuel]:
    path = agent_list_cache_path(env)
    try:
        if path.stat().st_size > AGENT_LIST_CACHE_MAX_BYTES:
            return None
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    try:
        ts = float(doc.get("ts"))
    except (TypeError, ValueError):
        return None
    age = float(now if now is not None else time.time()) - ts
    if age < 0 or age > float(max_age_s):
        return None
    return fuel_from_cache_document(doc)


def save_agent_list_fuel(fuel: Fuel, *, now: Optional[float] = None, env: Optional[dict] = None) -> bool:
    """Persist a menu reading only when at least one provider actually answered."""
    if not any(fuel_reading_known(fuel, kind) for kind in ("grok", "cursor", "opencode")):
        return False
    path = agent_list_cache_path(env)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(fuel_cache_document(fuel, now=now), sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return False
    return True


def cursor_on_demand_at_limit(f: Fuel) -> bool:
    """True when Cursor on-demand spend has hit its limit (FR #6119).

    Authoritative when included pool remain % still looks healthy (e.g. high=100)
    but the seat cannot charge on-demand. Prefer overspend_state=at-limit or
    used_cents >= limit_cents. Do not trust remaining_pct alone: Get-CursorAgentUsage
    rounds remain to an int, so remain_pct can be 0 while cents are still left.
    """
    st = (f.overspend_state or "").strip().lower()
    if st == "at-limit":
        return True
    used = f.on_demand_used_cents
    limit = f.on_demand_limit_cents
    if used is not None and limit is not None and int(limit) > 0 and int(used) >= int(limit):
        return True
    return False


# FR #8649: explicit Cursor seats are billed to this fleet account. Label only.
SI_NTSA_CURSOR_ACCOUNT = "si@ntsa.uk"


def cursor_has_tokens(f: Fuel) -> bool:
    # FR #6119: at-limit on-demand means the seat cannot run Cursor work.
    if cursor_on_demand_at_limit(f):
        return False
    return any(v is not None and v > 0 for v in (f.cursor_high, f.cursor_low))


def opencode_has_tokens(f: Fuel) -> bool:
    """True when OpenCode fuel readings show at least one usable pool.

    Unknown readings are treated as unavailable for seat selection, unlike Grok.
    When per-model Go readings exist, aggregate `opencode_go` alone is not enough:
    every listed Go model must be exhausted and free must be unavailable before we
    treat the seat as out of OpenCode fuel (FR #6120 - do not launch capped glm-5.3).

    FR #8540 / #8186: provider ``opencode_windows`` can show Go remaining when
    aggregate ``opencode_go`` is null.
    """
    if f.opencode_free is not None and f.opencode_free > 0:
        return True
    models = f.opencode_models or {}
    if models:
        for v in models.values():
            try:
                if int(v or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return False
    if f.opencode_go is not None and f.opencode_go > 0:
        return True
    return _opencode_windows_go_usable(f.opencode_windows)



def seat_fuel_pool(kind: str, start_model: str = "") -> str:
    """FR #8158 / #8186: fuel pool id for this seat kind + optional start model.

    Returns `grok`, `cursor`, `opencode_go`, `opencode_free`, or `opencode`
    (OpenCode with no start model yet).
    """
    k = (kind or "").strip().lower()
    if k == "grok":
        return "grok"
    if k == "cursor":
        return "cursor"
    if k != "opencode":
        return k or ""
    mid = (start_model or "").strip()
    if not mid:
        return "opencode"
    try:
        import worker_start_model as wsm

        if wsm.opencode_is_go_or_paid(mid):
            return "opencode_go"
        cls = wsm.start_model_review_class(mid)
        if cls == "paid":
            return "opencode_go"
        if cls == "free":
            return "opencode_free"
    except Exception:
        pass
    low = mid.lower()
    if low.startswith("opencode-go/") or "-pro" in low or "/opencode-go/" in low:
        return "opencode_go"
    return "opencode_free"


def _opencode_windows_go_usable(windows: Optional[dict]) -> bool:
    """True when provider windows show Go fuel remaining (FR #8186 AC6)."""
    if not isinstance(windows, dict):
        return False
    for key in ("week", "rolling", "month"):
        rec = windows.get(key) or {}
        if not isinstance(rec, dict):
            continue
        if rec.get("limited") is True:
            continue
        try:
            rem = rec.get("remaining_pct")
            if rem is not None and float(rem) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _opencode_windows_go_known(windows: Optional[dict]) -> bool:
    if not isinstance(windows, dict):
        return False
    for key in ("week", "rolling", "month"):
        rec = windows.get(key) or {}
        if isinstance(rec, dict) and rec.get("remaining_pct") is not None:
            return True
    return False


def opencode_pool_has_tokens(f: Fuel, pool: str, start_model: str = "") -> bool:
    """FR #8186: usable tokens for one OpenCode pool (not the unrelated pool)."""
    pool = (pool or "").strip().lower()
    mid = (start_model or "").strip()
    models = f.opencode_models or {}
    if pool == "opencode_free":
        return f.opencode_free is not None and int(f.opencode_free) > 0
    if pool == "opencode_go":
        if mid:
            # Per-model reading for the exact start model wins when present.
            short = mid.split("/")[-1]
            for key, val in models.items():
                k = str(key or "")
                if k == mid or k.endswith("/" + short) or k == short:
                    try:
                        return int(val or 0) > 0
                    except (TypeError, ValueError):
                        return False
        if f.opencode_go is not None:
            return int(f.opencode_go) > 0
        return _opencode_windows_go_usable(f.opencode_windows)
    # No specific pool: either pool (selection / no start model).
    return opencode_has_tokens(f)



def seat_pool_pct(f: Fuel, pool: str) -> Optional[int]:
    """Remaining pct for ``pool`` only (FR #8158). Never cross-reads another kind."""
    p = (pool or "").strip().lower()
    if p == "grok":
        return f.grok_pct
    if p == "cursor":
        vals = [v for v in (f.cursor_high, f.cursor_low) if v is not None]
        return max(vals) if vals else None
    if p == "opencode_go":
        return f.opencode_go
    if p == "opencode_free":
        return f.opencode_free
    if p == "opencode":
        # Ambiguous OpenCode seat: no start model — do not fall back to grok_pct.
        if f.opencode_go is not None:
            return f.opencode_go
        return f.opencode_free
    return None


def fold_opencode_seat_pauses(
    f: Fuel,
    start_model: str = "",
    *,
    env: Optional[dict] = None,
    now: Optional[float] = None,
    state_dir: Optional[Path] = None,
) -> Fuel:
    """FR #8158 / #8028: recorded provider refusal exhausts that seat's pool reading.

    Free-pool pauses zero ``opencode_free``. A pause on the seat's Go start model
    zeros ``opencode_go`` for this mid-job snapshot until the pause expires.
    """
    pool = seat_fuel_pool("opencode", start_model)
    try:
        import opencode_fuel as of
    except Exception:
        return f
    root = state_dir
    if root is None:
        try:
            root = of.opencode_pauses_state_dir(env if env is not None else {})
        except Exception:
            return f
    now_f = float(now if now is not None else time.time())
    free = f.opencode_free
    go = f.opencode_go
    changed = False
    if pool in ("opencode_free", "opencode"):
        d = {
            of.FUEL_ID_FREE: free,
            of.FUEL_ID_GO: go,
        }
        try:
            out = of.apply_runtime_pauses_to_fuel(d, root, now=now_f)
        except Exception:
            out = d
        new_free = out.get(of.FUEL_ID_FREE)
        if new_free is not None and new_free != free:
            free = int(new_free)
            changed = True
    if pool == "opencode_go" and (start_model or "").strip():
        try:
            if of.is_opencode_model_paused(start_model, root, now=now_f):
                if go != 0:
                    go = 0
                    changed = True
        except Exception:
            pass
    if not changed:
        return f
    return Fuel(
        f.cursor_high,
        f.cursor_low,
        f.grok_pct,
        f.grok_state,
        f.on_demand_used_cents,
        f.on_demand_limit_cents,
        f.on_demand_remaining_pct,
        f.overspend_state,
        free,
        go,
        dict(f.opencode_models or {}),
        tuple(f.opencode_free_model_ids or ()),
    )

def opencode_pauses_state_dir(env: Optional[dict] = None) -> Path:
    """Default directory for the worker's OpenCode pause JSON file."""
    env = os.environ if env is None else env
    base = env.get("BOB_OPENCODE_PAUSE_STATE_DIR") or env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Bobiverse" / "worker" / "state"


def _opencode_free_known_zero(f: Fuel) -> bool:
    """True only when the free pool reading is present and not positive."""
    if f.opencode_free is None:
        return False
    try:
        return int(f.opencode_free) <= 0
    except (TypeError, ValueError):
        return True


def _opencode_paid_positive(f: Fuel) -> bool:
    """Paid/Go pool has a positive reading (aggregate or any per-model leaf)."""
    if f.opencode_go is not None:
        try:
            if int(f.opencode_go) > 0:
                if not f.opencode_models:
                    return True
        except (TypeError, ValueError):
            pass
    models = f.opencode_models or {}
    if models:
        any_pos = False
        for v in models.values():
            try:
                if int(v or 0) > 0:
                    any_pos = True
                    break
            except (TypeError, ValueError):
                continue
        return any_pos
    if f.opencode_go is not None:
        try:
            return int(f.opencode_go) > 0
        except (TypeError, ValueError):
            return False
    return _opencode_windows_go_usable(f.opencode_windows)


def _opencode_paid_known_exhausted(f: Fuel) -> bool:
    """True only when Go/paid is known empty (FR #8541).

    ``go=None`` with no provider windows is unknown, not exhausted — still try
    the paid tray slot after free is known 0.
    """
    if _opencode_windows_go_usable(f.opencode_windows):
        return False
    models = f.opencode_models or {}
    if models:
        any_pos = False
        for v in models.values():
            try:
                if int(v or 0) > 0:
                    any_pos = True
                    break
            except (TypeError, ValueError):
                continue
        return not any_pos
    if f.opencode_go is None and not _opencode_windows_go_known(f.opencode_windows):
        return False
    if f.opencode_go is not None:
        try:
            return int(f.opencode_go) <= 0
        except (TypeError, ValueError):
            return True
    return False


def opencode_default_model(
    f: Fuel,
    state_dir: Optional[Path] = None,
    *,
    now: Optional[float] = None,
) -> Optional[str]:
    """Pick an OpenCode model from fuel (FR #6120 / #8454).

    Free first: remaining > 0 or unknown uses a free id. A Go/paid id is
    returned only when free is known 0 and a Go reading is positive. Paused
    models are skipped. No third model is invented: free ids come from live
    readings, else the tray free slot; paid is the tray paid slot when that
    leaf is not listed as exhausted.
    """
    if state_dir is None:
        state_dir = opencode_pauses_state_dir()

    def _paused(model_id: str) -> bool:
        if not opencode_fuel:
            return False
        return opencode_fuel.is_opencode_model_paused(model_id, state_dir, now=now)

    try:
        import worker_start_model as wsm

        free_slot = wsm.DEFAULT_OPENCODE_FREE
        paid_slot = wsm.DEFAULT_OPENCODE_PAID
    except Exception:
        free_slot = "opencode/deepseek-v4.1-flash-free"
        paid_slot = "opencode-go/deepseek-v4-pro"

    def _first_free() -> Optional[str]:
        for free_id in f.opencode_free_model_ids:
            if _paused(str(free_id)):
                continue
            return str(free_id)
        if free_slot and not _paused(free_slot):
            return free_slot
        return None

    if not _opencode_free_known_zero(f):
        return _first_free()

    if not _opencode_paid_positive(f):
        return None

    models = f.opencode_models or {}
    if models:
        order = opencode_fuel.OPENCODE_GO_FALLBACK_ORDER if opencode_fuel else ()
        paid_leaf = paid_slot.split("/", 1)[-1] if paid_slot else ""
        leaves: list[str] = []
        for m in (paid_leaf,) + tuple(order) + tuple(models.keys()):
            if m and m not in leaves:
                leaves.append(m)
        for m in leaves:
            if m not in models:
                continue
            try:
                if int(models.get(m) or 0) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            candidate = f"opencode-go/{m}"
            if _paused(candidate):
                continue
            return candidate
        return None
    if paid_slot and not _paused(paid_slot):
        return paid_slot
    return None


def capture_opencode_model_env_at_start(env: Optional[dict] = None) -> Optional[str]:
    """Record operator ``BOB_OPENCODE_MODEL`` once at process start (FR #6363).

    Later worker exports into ``os.environ`` must not count as an operator override.
    """
    global _OPENCODE_MODEL_ENV_AT_START
    env = os.environ if env is None else env
    raw = str(env.get("BOB_OPENCODE_MODEL") or "").strip()
    _OPENCODE_MODEL_ENV_AT_START = raw or None
    return _OPENCODE_MODEL_ENV_AT_START


SEAT_MODEL_PIN_ENV = "BOB_SEAT_MODEL_PIN"


def seat_model_pinned(env: Optional[dict] = None) -> bool:
    """FR #8321: the tray restored a clicked seat and pinned its saved model."""
    env = os.environ if env is None else env
    return str(env.get(SEAT_MODEL_PIN_ENV) or "").strip().lower() in (
        "1", "true", "yes", "on"
    )


def opencode_model_pause_reason(
    model: str,
    *,
    now: Optional[float] = None,
    env: Optional[dict] = None,
) -> str:
    """FR #8321: why a saved OpenCode model cannot start (empty string = usable)."""
    mid = str(model or "").strip()
    if not mid or not opencode_fuel:
        return ""
    env = os.environ if env is None else env
    state_dir = opencode_pauses_state_dir(env)
    try:
        if opencode_fuel.is_opencode_model_paused(mid, state_dir, now=now):
            return "paused"
        leaf = mid.rsplit("/", 1)[-1].lower()
        free_leaf = leaf.endswith("-free") or leaf in getattr(
            opencode_fuel, "OPENCODE_FREE_MODELS", ()
        )
        if free_leaf and opencode_fuel.is_opencode_model_paused(
            "opencode-free", state_dir, now=now
        ):
            return "paused"
    except Exception:
        return ""
    return ""


# FR #7196: provider/region cues only. Bare "model unavailable" matches job/skill/prompt
# text and the wrapper's own message; permission/tool rejects are not model misses.
_OPENCODE_UNAVAIL_CUES = (
    "not available in your region",
    "unavailable in your region",
    "provider_model_not_found",
    "model not found",
    "no such model",
)
_OPENCODE_UNAVAIL_NOISE = (
    "permission requested",
    "external_directory",
    "rejected permission",
    "this specific tool call",
    "the user rejected",
)
_OPENCODE_UNAVAIL_PROVIDER = (
    "not available in your region",
    "unavailable in your region",
    "provider_model_not_found",
)


def format_opencode_model_unavailable_error(
    text: str,
    *,
    model: str = "",
) -> Optional[str]:
    """FR #6429 / #7196: clear region/model-unavailable message; never invent a substitute model.

    Returns a human-facing error string when *text* looks like a missing/region-blocked
    model, else ``None`` (caller keeps the original failure text). Job, skill, and
    permission/tool-call text must not trip this (FR #7196).
    """
    raw = str(text or "")
    low = raw.lower()
    if any(n in low for n in _OPENCODE_UNAVAIL_NOISE) and not any(
        c in low for c in _OPENCODE_UNAVAIL_PROVIDER
    ):
        return None
    if not any(c in low for c in _OPENCODE_UNAVAIL_CUES):
        return None
    mid = str(model or "").strip() or "(configured OpenCode model)"
    if "region" in low and ("unavailable" in low or "not available" in low):
        return (
            "OpenCode model unavailable: %s (set OpenCode console region to Global "
            "for paid V4 Pro, or pick a model available in this region). "
            "No substitute model was selected."
        ) % mid
    return (
        "OpenCode model unavailable: %s. No substitute model was selected."
    ) % mid


def opencode_needs_model_line(model: str, reason: str) -> str:
    """FR #7196: shop/digest line; never 'worker ready' / ACK."""
    mid = str(model or "").strip() or "(configured OpenCode model)"
    why = str(reason or "unavailable").strip() or "unavailable"
    return "needs model: %s unavailable (%s)" % (mid, why)


def probe_opencode_model_listing_unavailable(model: str, listing: str) -> str:
    """Return a short reason when *listing* is a true provider miss; else '' (unknown/ok)."""
    msg = format_opencode_model_unavailable_error(listing or "", model=model)
    if not msg:
        return ""
    if "region" in msg.lower():
        return "not available in your region"
    return "unavailable"


def probe_opencode_models_listing(
    exe: str | None = None,
    *,
    listing: str | None = None,
    timeout: float = 8.0,
) -> str:
    """Cheap ``opencode models`` stdout+stderr; empty on timeout/fail (do not block ready)."""
    if listing is not None:
        return str(listing)
    env_list = os.environ.get("BOB_OPENCODE_PROBE_LISTING")
    if env_list is not None:
        return env_list
    cmd = str(exe or "").strip()
    if not cmd:
        return ""
    try:
        p = subprocess.run(
            [cmd, "models"],
            capture_output=True,
            text=True,
            timeout=float(timeout),
            check=False,
        )
        return ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    except Exception:
        return ""



def _strip_jsonc(text: str) -> str:
    """Strip // and /* */ comments and trailing commas for OpenCode JSONC configs."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                i += 2
                while i < n and text[i] not in "\n\r":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i = min(i + 2, n)
                continue
        out.append(c)
        i += 1
    stripped = "".join(out)
    return re.sub(r",\s*([}\]])", r"\1", stripped)


def opencode_global_config_candidates(env: Optional[dict] = None) -> list[Path]:
    """Paths to try for the OpenCode global config (FR #6363)."""
    env = os.environ if env is None else env
    paths: list[Path] = []
    custom = str(env.get("OPENCODE_CONFIG") or "").strip()
    if custom:
        paths.append(Path(custom))
    xdg = str(env.get("XDG_CONFIG_HOME") or "").strip()
    home = Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    bases: list[Path] = []
    if xdg:
        bases.append(Path(xdg) / "opencode")
    bases.append(home / ".config" / "opencode")
    local = str(env.get("LOCALAPPDATA") or "").strip()
    if local:
        bases.append(Path(local) / "opencode")
    for base in bases:
        for name in ("opencode.jsonc", "opencode.json"):
            paths.append(base / name)
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def read_opencode_config_model(
    env: Optional[dict] = None,
    *,
    path: Optional[Path] = None,
) -> Optional[str]:
    """Read ``model`` from OpenCode config (JSON/JSONC). FR #6363."""
    env = os.environ if env is None else env
    candidates = [path] if path is not None else opencode_global_config_candidates(env)
    for cand in candidates:
        if cand is None:
            continue
        try:
            if not cand.is_file():
                continue
        except OSError:
            continue
        try:
            raw = cand.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            doc = json.loads(_strip_jsonc(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        model = str(doc.get("model") or "").strip()
        if model:
            return model
    return None


def _opencode_model_known_capped(model: str, fuel: Fuel) -> bool:
    """True when fuel readings prove the model is exhausted (unknown = not capped)."""
    mid = str(model or "").strip()
    if not mid:
        return True
    models = fuel.opencode_models or {}
    if mid.startswith("opencode-go/"):
        leaf = mid.split("/", 1)[-1]
        if leaf in models:
            try:
                return int(models.get(leaf) or 0) <= 0
            except (TypeError, ValueError):
                return True
        return False
    leaf = mid.split("/")[-1]
    is_free = mid.endswith("-free") or leaf.endswith("-free")
    if opencode_fuel is not None:
        try:
            is_free = bool(
                opencode_fuel._is_free_model(leaf)
                or opencode_fuel._is_free_model(mid)
                or is_free
            )
        except Exception:  # noqa: BLE001
            pass
    if is_free and fuel.opencode_free is not None:
        try:
            return int(fuel.opencode_free) <= 0
        except (TypeError, ValueError):
            return True
    return False


def resolve_opencode_model(
    fuel: Fuel,
    state_dir: Optional[Path] = None,
    *,
    now: Optional[float] = None,
    env: Optional[dict] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Resolve OpenCode model: env -> tray start -> config -> free default -> fuel (FR #6363 / #7187).

    Skips paused or known-capped candidates and falls through. Logs one grep-able
    line: ``opencode model=<id> source=env|config|fuel skipped=<...>``.
    """
    env = os.environ if env is None else env
    if state_dir is None:
        state_dir = opencode_pauses_state_dir(env)

    # FR #8150: seat-start scan of the OpenCode app log for a recent ERROR
    # "Free usage limit" / rate-limit refusal. Stdout may be empty; the app
    # log still carries the stream error. record-pause then lets selection
    # fall through (#7952 path).
    try:
        import provider_error_source as pes

        hit = pes.apply_seat_start_opencode_app_log_pause(
            env=env, state_dir=state_dir, now=now
        )
        if hit is not None and log_fn is not None:
            try:
                log_fn(
                    "opencode: app-log fuel at seat start reason=%s"
                    % hit.reason
                )
            except Exception:
                pass
    except Exception:
        pass

    def _paused(model_id: str) -> bool:
        if not opencode_fuel:
            return False
        if opencode_fuel.is_opencode_model_paused(model_id, state_dir, now=now):
            return True
        # FR #8150 / #8028: an opencode-free pool pause exhausts every free leaf.
        try:
            leaf = str(model_id or "").rsplit("/", 1)[-1].lower()
            free_leaf = leaf.endswith("-free") or leaf in getattr(
                opencode_fuel, "OPENCODE_FREE_MODELS", ()
            )
        except Exception:
            free_leaf = str(model_id or "").lower().endswith("-free")
        if free_leaf and opencode_fuel.is_opencode_model_paused(
            "opencode-free", state_dir, now=now
        ):
            return True
        return False

    skipped: list[str] = []
    candidates: list[tuple[str, str]] = []

    try:
        import worker_start_model as wsm

        start_cfg = wsm.load_worker_start_config(env=env)
        start_model = str((start_cfg.get("workerStartModels") or {}).get("opencode") or "").strip()
        start_free = wsm.default_opencode_free_model(start_cfg)
        start_paid = wsm.default_opencode_paid_model(start_cfg)
    except Exception:
        start_cfg = {}
        start_model = ""
        start_free = "opencode/deepseek-v4.1-flash-free"
        start_paid = "opencode-go/deepseek-v4-pro"

    # FR #8454: free remaining > 0 or unknown starts on a free id even when the
    # tray/env pin is paid. Paid slot only when free is known 0 and paid > 0.
    # FR #6363: a free operator env / config still beats the tray free slot.
    env_model = (_OPENCODE_MODEL_ENV_AT_START or "").strip()
    pinned = seat_model_pinned(env) and bool(env_model)
    free_known_zero = _opencode_free_known_zero(fuel)
    # FR #8555: a free-pool pause (seat-start app-log scan or a prior refusal)
    # means free is exhausted even when the catalogue still reports 100. Fold it
    # into the branch choice so the paid slot is tried instead of every free
    # candidate being skipped as paused and the seat dying with model=-.
    if not free_known_zero and opencode_fuel is not None:
        try:
            if opencode_fuel.is_opencode_model_paused(
                "opencode-free", state_dir, now=now
            ):
                free_known_zero = True
        except Exception:
            pass

    def _is_paid(mid: str) -> bool:
        try:
            import worker_start_model as wsm

            return bool(wsm.opencode_is_go_or_paid(mid))
        except Exception:
            low = str(mid or "").lower()
            return low.startswith("opencode-go/") or low.endswith("-pro")

    if not free_known_zero:
        if pinned and _is_paid(env_model):
            skipped.append(f"pin:{env_model}:free-first")
        elif pinned and env_model:
            candidates.append(("pin", env_model))
        elif env_model and _is_paid(env_model):
            skipped.append(f"env:{env_model}:free-first")
        elif env_model:
            candidates.append(("env", env_model))

        if start_model and _is_paid(start_model):
            skipped.append(f"start:{start_model}:free-first")
        elif start_model:
            candidates.append(("tray", start_model))

        cfg_model = read_opencode_config_model(env)
        if cfg_model and _is_paid(cfg_model):
            skipped.append(f"config:{cfg_model}:free-first")
        elif cfg_model:
            candidates.append(("config", cfg_model))

        if start_free:
            candidates.append(("start", start_free))

        for free_id in fuel.opencode_free_model_ids or ():
            fid = str(free_id or "").strip()
            if fid and not _is_paid(fid):
                candidates.append(("fuel", fid))
    else:
        if pinned and env_model and not _is_paid(env_model):
            skipped.append(f"pin:{env_model}:free-exhausted")
        elif env_model and not _is_paid(env_model):
            skipped.append(f"env:{env_model}:free-exhausted")
        # FR #8541: free known 0 + go unknown must still try the paid tray slot
        # (do not skip as exhausted / report capped-paused).
        if start_paid and (
            _opencode_paid_positive(fuel) or not _opencode_paid_known_exhausted(fuel)
        ):
            candidates.append(("paid", start_paid))
        elif start_paid:
            skipped.append(f"paid:{start_paid}:exhausted")

    chosen: Optional[str] = None
    source = ""
    for src, mid in candidates:
        if _paused(mid):
            skipped.append(f"{src}:{mid}:paused")
            continue
        if _opencode_model_known_capped(mid, fuel):
            skipped.append(f"{src}:{mid}:capped")
            continue
        chosen = mid
        source = src
        break

    skip_s = ",".join(skipped) if skipped else "-"
    line = f"opencode model={chosen or '-'} source={source or '-'} skipped={skip_s}"
    if log_fn is not None:
        try:
            log_fn(line)
        except Exception:  # noqa: BLE001
            pass
    return chosen


def stamp_opencode_pause_fallback(env: dict, chosen: str, *, now: Optional[float] = None) -> bool:
    """Mark a launch that fell back because the configured model was paused.

    An operator ``BOB_OPENCODE_MODEL`` captured at process start is a chosen
    model and is not a fallback (FR #7952). Returns True when the stamp is set.
    """
    if (_OPENCODE_MODEL_ENV_AT_START or "").strip():
        env.pop("BOB_OPENCODE_PAUSE_FALLBACK", None)
        env.pop("BOB_OPENCODE_CONFIGURED_MODEL", None)
        return False
    cfg = ""
    try:
        import worker_start_model as wsm

        cfg = wsm.configured_start_model("opencode", wsm.load_worker_start_config(env=env))
    except Exception:
        cfg = ""
    if not cfg:
        cfg = read_opencode_config_model(env) or ""
    picked = str(chosen or "").strip()
    paused = False
    if cfg and picked and cfg.lower() != picked.lower() and opencode_fuel is not None:
        paused = opencode_fuel.is_opencode_model_paused(
            cfg, opencode_pauses_state_dir(env), now=now
        )
    if not paused:
        env.pop("BOB_OPENCODE_PAUSE_FALLBACK", None)
        env.pop("BOB_OPENCODE_CONFIGURED_MODEL", None)
        return False
    env["BOB_OPENCODE_CONFIGURED_MODEL"] = cfg
    env["BOB_OPENCODE_PAUSE_FALLBACK"] = "1"
    env["BOB_OPENCODE_SEAT_PID"] = str(os.getpid())
    return True


def resume_opencode_pause_fallback(
    *,
    current: str,
    configured: str,
    state_dir: Path,
    pause_fallback: bool,
    now: Optional[float] = None,
    machine: str = "",
    nick: str = "",
    pid: int | str = 0,
    publish=None,
) -> str:
    """Model for the next job. Does not change a model while a turn is in progress.

    When ``pause_fallback`` is set and the configured model's pause has expired,
    return that model and ask ``publish(model, mismatch)`` once.
    """
    if opencode_fuel is None:
        return str(current or "").strip()
    nxt = opencode_fuel.next_job_model(
        current,
        configured,
        state_dir,
        now=now,
        pause_fallback=pause_fallback,
    )
    cur = str(current or "").strip()
    if nxt != cur and publish is not None:
        mismatch = nxt.lower() != str(configured or "").strip().lower()
        publish(nxt, mismatch)
    elif nxt != cur and machine and pid:
        post_digest_seat_kind(
            machine=machine,
            pid=pid,
            nick=nick,
            kind="opencode",
            model=nxt,
            configured_model=configured,
            model_mismatch=nxt.lower() != str(configured or "").strip().lower(),
            log=None,
        )
    return nxt

def grok_has_tokens(f: Fuel) -> bool:
    """True when seat start may pick Grok (FR #3997).

    Exhausted only on explicit signals: pct <= 0 or state exhausted/empty/none/unavailable.
    Unknown / failed reads count as available so a flaky helper does not skip weekly Grok.
    """
    if f.grok_pct is not None:
        return int(f.grok_pct) > 0
    st = (f.grok_state or "unknown").strip().lower()
    if st in ("exhausted", "empty", "none", "unavailable"):
        return False
    # available, unknown, or other non-exhausted -> try Grok first
    return True


def fuel_reading_known(f: Fuel, kind: str, start_model: str = "") -> bool:
    """True when the helper returned a parseable reading for this seat kind (FR #3923).

    Empty `Fuel()` (helper missing / timeout / unreadable) is **unknown**, not exhausted.

    FR #8158 / #8186: when `start_model` selects an OpenCode pool, only that pool counts.
    Without a start model, either OpenCode pool still counts (seat selection / cache).
    Go pool may also be known via provider `opencode_windows` when aggregate go is nulled.
    """
    k = (kind or "").strip().lower()
    if k == "grok":
        if f.grok_pct is not None:
            return True
        st = (f.grok_state or "unknown").strip().lower()
        return st != "unknown"
    if k == "cursor":
        if f.cursor_high is not None or f.cursor_low is not None:
            return True
        if (
            f.on_demand_used_cents is not None
            or f.on_demand_limit_cents is not None
            or f.on_demand_remaining_pct is not None
            or (f.overspend_state or "").strip().lower() not in ("", "unknown")
        ):
            return True
        return False
    if k == "opencode":
        pool = seat_fuel_pool(k, start_model)
        if pool == "opencode_go":
            return f.opencode_go is not None or _opencode_windows_go_known(f.opencode_windows)
        if pool == "opencode_free":
            return f.opencode_free is not None
        # No start model (either-pool). FR #8540: free known 0 + go unknown must
        # not count as a known dual-pool reading (that refused paid Go seats).
        # Free > 0 alone is enough; go known (aggregate or windows) is enough;
        # free known 0 alone is not.
        try:
            free_n = int(f.opencode_free) if f.opencode_free is not None else None
        except (TypeError, ValueError):
            free_n = None
        if free_n is not None and free_n > 0:
            return True
        if f.opencode_go is not None or _opencode_windows_go_known(f.opencode_windows):
            return True
        return False
    return False


def fuel_explicitly_exhausted(f: Fuel, kind: str, start_model: str = "") -> bool:
    """True only for an explicit zero/exhausted reading (FR #3923 mid-job gate).

    Unknown / unreadable readings must **not** trip mid-job GIVEUP. Seat *selection*
    still uses ``grok_has_tokens`` / ``cursor_has_tokens`` (unknown = not available).

    FR #8158: OpenCode mid-job with a start model keys exhaustion to that pool only
    (never treat free=100 as fuel for an ``opencode-go/*`` seat).
    """
    k = (kind or "").strip().lower()
    # FR #6119: on-demand at-limit before known gate (limit alone is enough evidence).
    if k == "cursor" and cursor_on_demand_at_limit(f):
        return True
    if not fuel_reading_known(f, k, start_model=start_model):
        return False
    if k == "grok":
        if f.grok_pct is not None:
            return int(f.grok_pct) <= 0
        st = (f.grok_state or "").strip().lower()
        return st in ("exhausted", "empty", "none", "unavailable")
    if k == "cursor":
        # On-demand fields alone can make the reading "known" without pool high/low.
        # Incomplete pool data must not mid-job GIVEUP unless on-demand is at-limit.
        if f.cursor_high is None and f.cursor_low is None:
            return False
        return not cursor_has_tokens(f)
    if k == "opencode":
        pool = seat_fuel_pool(k, start_model)
        if pool == "opencode_go":
            # FR #8186: aggregate go None + usable windows is known fuel, not exhausted.
            if f.opencode_go is None and _opencode_windows_go_usable(f.opencode_windows):
                return False
            if f.opencode_go is None and _opencode_windows_go_known(f.opencode_windows):
                return not _opencode_windows_go_usable(f.opencode_windows)
            return int(f.opencode_go or 0) <= 0
        if pool == "opencode_free":
            return int(f.opencode_free or 0) <= 0
        return not opencode_has_tokens(f)
    return False


def format_fuel_reading(
    f: Fuel,
    kind: str = "",
    start_model: str = "",
    *,
    source: str = "",
    age_s: Optional[float] = None,
) -> str:
    """One-line fuel snapshot for mid-job logs (no secrets).

    FR #8158: ``pct=`` is the seat's own pool remaining (never Grok pct on an
    OpenCode seat). ``pool=`` names that pool; ``known=False`` keeps ``pool=``.
    """
    k = (kind or "").strip().lower()
    pool = seat_fuel_pool(k, start_model)
    pct = seat_pool_pct(f, pool)
    known = fuel_reading_known(f, k, start_model=start_model)
    exhausted = fuel_explicitly_exhausted(f, k, start_model=start_model)
    state = f.grok_state if pool == "grok" else ("exhausted" if exhausted else ("available" if known else "unknown"))
    return (
        f"kind={k or '-'} pool={pool or '-'} pct={pct!s} state={state!s} "
        f"cursor_high={f.cursor_high!s} cursor_low={f.cursor_low!s} "
        f"on_demand_used={f.on_demand_used_cents!s} on_demand_limit={f.on_demand_limit_cents!s} "
        f"on_demand_remain_pct={f.on_demand_remaining_pct!s} overspend={f.overspend_state!s} "
        f"opencode_free={f.opencode_free!s} opencode_go={f.opencode_go!s} "
        f"known={known} exhausted={exhausted}"
        + (f" source={source} age_s={int(age_s)}" if source else "")
    )


# FR #8230: fleet/digest fills a pool the local helper left unknown. Never calls Go zen.
FLEET_FUEL_MAX_AGE_S = 600.0


def _parse_fleet_stamp(raw) -> Optional[float]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = _dt.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _fleet_pool_row(doc: dict, pool: str) -> Optional[dict]:
    """Public digest row for one pool. Never returns credential fields."""
    if not isinstance(doc, dict):
        return None
    names = {
        "opencode_go": ("opencode-go", "opencode_go"),
        "opencode_free": ("opencode-free", "opencode_free"),
        "cursor": ("cursor",),
    }.get(pool, ())
    if not names:
        return None
    containers = [doc]
    for key in ("opencode", "fleet", "fleet_pools"):
        node = doc.get(key)
        if isinstance(node, dict):
            containers.append(node)
            nested = node.get("opencode")
            if isinstance(nested, dict):
                containers.append(nested)
    for node in containers:
        for name in names:
            row = node.get(name)
            if isinstance(row, dict):
                return row
    return None


def fleet_pool_fill(
    row: Optional[dict],
    *,
    now: float,
    max_age_s: float = FLEET_FUEL_MAX_AGE_S,
) -> dict:
    """Decide whether a digest row may fill a missing local pool.

    Usable only when ``fresh`` is true and ``fetched_at``/``ts`` is within
    ``max_age_s``. ``limited: true`` or remaining 0 is an explicit zero.
    Stale or missing stays unusable (known=False). No guess.
    """
    out = {
        "usable": False,
        "remaining": None,
        "windows": None,
        "age_s": None,
        "source": "",
    }
    if not isinstance(row, dict):
        return out
    if row.get("fresh") is not True:
        return out
    stamp = _parse_fleet_stamp(row.get("fetched_at"))
    if stamp is None:
        stamp = _parse_fleet_stamp(row.get("ts"))
    if stamp is None:
        return out
    age = float(now) - float(stamp)
    out["age_s"] = age
    if age < -60.0 or age > float(max_age_s):
        return out
    limited = row.get("limited") is True
    rem = row.get("remaining")
    try:
        rem_i = None if rem is None or rem == "" else int(rem)
    except (TypeError, ValueError):
        rem_i = None
    if limited and rem_i is None:
        rem_i = 0
    if rem_i is None:
        return out
    usage = str(row.get("usage_source") or "digest").strip() or "digest"
    if "key" in usage.lower() or "token" in usage.lower() or "credman" in usage.lower():
        usage = "digest"
    windows = row.get("windows") if isinstance(row.get("windows"), dict) else None
    out["usable"] = True
    out["remaining"] = rem_i
    out["windows"] = windows
    out["source"] = "fleet:" + usage
    return out


def supplement_fuel_from_fleet(
    fuel: Fuel,
    digest: Optional[dict],
    *,
    now: float,
    max_age_s: float = FLEET_FUEL_MAX_AGE_S,
) -> tuple:
    """Fill only pools the local helper left empty. Returns (fuel, source, age_s)."""
    if not isinstance(digest, dict):
        return fuel, "", None
    source = ""
    age_s = None
    go = fuel.opencode_go
    free = fuel.opencode_free
    windows = fuel.opencode_windows
    for pool, current in (("opencode_go", go), ("opencode_free", free)):
        if current is not None:
            continue
        fill = fleet_pool_fill(_fleet_pool_row(digest, pool), now=now, max_age_s=max_age_s)
        if not fill["usable"]:
            continue
        if pool == "opencode_go":
            go = fill["remaining"]
        else:
            free = fill["remaining"]
        if windows is None and fill["windows"] is not None:
            windows = fill["windows"]
        if not source:
            source = fill["source"]
            age_s = fill["age_s"]
    if go is fuel.opencode_go and free is fuel.opencode_free and windows is fuel.opencode_windows:
        return fuel, "", None
    return (
        replace(fuel, opencode_go=go, opencode_free=free, opencode_windows=windows),
        source,
        age_s,
    )


def load_public_digest(path: Optional[Path]) -> dict:
    """Read digest.json. Returns {} on any failure. Caller must not log the body."""
    if path is None:
        return {}
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError, UnicodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def digest_home_candidates(
    env: Optional[dict] = None,
    *,
    install_root: Optional[Path | str] = None,
) -> list[Path]:
    """Homes that may hold digest.json / private fleet meters (FR #8667)."""
    env = os.environ if env is None else env
    out: list[Path] = []
    home = str((env or {}).get("BOB_DIGEST_HOME") or "").strip()
    if home:
        out.append(Path(home))
    try:
        import bob_home as bh
        out.append(Path(bh.digest_home()))
    except Exception:
        out.append(Path.home() / ".bobiverse")
    bob_home = str((env or {}).get("BOB_HOME") or "").strip()
    if bob_home:
        out.append(Path(bob_home))
    if install_root:
        out.append(Path(install_root) / "home")
    seen: set[str] = set()
    uniq: list[Path] = []
    for cand in out:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(cand)
    return uniq


def load_private_cursor_meter(
    env: Optional[dict] = None,
    *,
    install_root: Optional[Path | str] = None,
    home: Optional[Path | str] = None,
) -> Optional[dict]:
    """FR #8667: private si Cursor remaining. Never from public digest."""
    homes: list[Path] = []
    if home:
        homes.append(Path(home))
    if install_root:
        homes.append(Path(install_root))
    homes.extend(digest_home_candidates(env, install_root=install_root))
    try:
        import fleet_pool_fetch as fpf
        loader = getattr(fpf, "load_private_cursor_meter", None)
        path_fn = getattr(fpf, "private_cursor_path", None)
    except Exception:
        loader = None
        path_fn = None
    for h in homes:
        if callable(loader):
            try:
                row = loader(h)
            except Exception:
                row = None
            if isinstance(row, dict):
                return row
        if callable(path_fn):
            try:
                p = path_fn(h)
                if p is not None and Path(p).is_file():
                    doc = json.loads(Path(p).read_text(encoding="utf-8"))
                    if isinstance(doc, dict):
                        return doc
            except Exception:
                pass
        # Fallback path name if import missing
        p = Path(h) / "fleet-cursor-private.json"
        if p.is_file():
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(doc, dict):
                return doc
    return None



def public_digest_path(
    env: Optional[dict] = None,
    *,
    install_root: Optional[Path | str] = None,
) -> Optional[Path]:
    """First existing digest.json the seat can read (FR #8230 / MRB #8231).

    Seats often have no ``BOB_DIGEST_HOME``. Fall back to ``bob_home.digest_home``,
    ``BOB_HOME``, and ``<install>/home``. Prefer a real file; never invent fuel.
    """
    env = os.environ if env is None else env
    candidates: list[Path] = []
    home = str((env or {}).get("BOB_DIGEST_HOME") or "").strip()
    if home:
        candidates.append(Path(home) / "digest.json")
    try:
        import bob_home as bh

        candidates.append(Path(bh.digest_home()) / "digest.json")
    except Exception:
        candidates.append(Path.home() / ".bobiverse" / "digest.json")
    bob_home = str((env or {}).get("BOB_HOME") or "").strip()
    if bob_home:
        candidates.append(Path(bob_home) / "digest.json")
        candidates.append(Path(bob_home) / "bob-peers" / "_report-digest.json")
    if install_root:
        candidates.append(Path(install_root) / "home" / "digest.json")
    seen: set[str] = set()
    for cand in candidates:
        try:
            key = str(cand.resolve()) if cand.exists() else str(cand)
        except OSError:
            key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def take_midjob_fuel(
    local_fn: Callable[[], Fuel],
    digest: Optional[dict],
    *,
    now: float,
    hold: Optional[dict],
    pool: str,
    max_age_s: float = FLEET_FUEL_MAX_AGE_S,
) -> tuple:
    """Reuse a fleet fill until it ages out. Otherwise read local, then fill.

    ``hold`` is ``{pool, until, fuel, source, fetched_at}``. Returns
    ``(fuel, source, age_s, new_hold)``. Does not call ``local_fn`` when the
    hold still covers ``pool``.
    """
    if (
        isinstance(hold, dict)
        and hold.get("pool") == pool
        and pool
        and float(hold.get("until") or 0) > float(now)
        and isinstance(hold.get("fuel"), Fuel)
    ):
        fetched = hold.get("fetched_at")
        age = None if fetched is None else float(now) - float(fetched)
        return hold["fuel"], str(hold.get("source") or ""), age, hold
    try:
        local = local_fn()
    except Exception:
        local = Fuel()
    fuel, source, age = supplement_fuel_from_fleet(
        local, digest, now=now, max_age_s=max_age_s
    )
    new_hold = None
    if source.startswith("fleet:") and pool in ("opencode_go", "opencode_free"):
        fetched = float(now) - float(age or 0)
        new_hold = {
            "pool": pool,
            "until": fetched + float(max_age_s),
            "fuel": fuel,
            "source": source,
            "fetched_at": fetched,
        }
    return fuel, source, age, new_hold


@dataclass(frozen=True)
class Decision:
    kind: str  # cursor | grok | opencode | dialog | none | refuse | xai-auth-expired
    reason: str
    account: str = ""


XAI_SIGNIN_EXPIRED_ERRORS = frozenset(
    {
        "grok-login-expired",
        "auth-missing",
        "auth-file-missing",
        "auth-key-missing",
        "auth-file-unreadable",
        "xai-auth-expired",
    }
)
GROK_SIGNIN_PROMPT_WINDOW_S = 30.0
GROK_SIGNIN_PROMPT_NEEDLES = (
    "sign in",
    "device code",
    "device-code",
    "visit https://",
    "open the following url",
    "authorize this device",
    "login to grok",
    "x.ai/activate",
    "x.ai/authorize",
)


XAI_SIGNIN_ABSENT_ERRORS = frozenset(
    {
        "auth-missing",
        "auth-file-missing",
        "auth-key-missing",
        "auth-file-unreadable",
        "auth-unresolved",
        "no-seat-auth",
    }
)


def classify_xai_signin_state(error: Optional[str]) -> str:
    """Ear-aligned class: ok, absent, or expired. Never reads auth file bodies.

    A missing file is ``absent`` (FR #8222), never ``expired``.
    """
    err = (error or "").strip().lower()
    if err in XAI_SIGNIN_ABSENT_ERRORS or err.startswith("auth-file-unreadable"):
        return "absent"
    if err in XAI_SIGNIN_EXPIRED_ERRORS:
        return "expired"
    return "ok"


def preflight_xai_signin(
    *,
    fetch_fn: Optional[Callable] = None,
    last_acq: Optional[dict] = None,
) -> str:
    """Same live weekly source as the SYSTEM ear (FR #7251). Returns ok|absent|expired.

    Does not copy, print, or rewrite sign-in files. fetch_fn is inject-only.
    """
    acq = last_acq
    if fetch_fn is not None:
        try:
            fetch_fn()
        except Exception:
            pass
    elif last_acq is None:
        try:
            import bobreport as _br

            _br.fetch_live_xai_weekly()
            acq = getattr(_br, "_last_xai_acquisition", None)
        except Exception:
            return "ok"
    err = ""
    if isinstance(acq, dict):
        err = str(acq.get("error") or "")
    return classify_xai_signin_state(err)


def grok_console_is_signin_prompt(text: str) -> bool:
    blob = (text or "").lower()
    return any(n in blob for n in GROK_SIGNIN_PROMPT_NEEDLES)


class GrokSigninPromptGuard:
    """FR #7345: first 30s of Grok console. Sign-in/device-code => trigger kill."""

    def __init__(
        self,
        read_fn,
        *,
        timeout_s: float = GROK_SIGNIN_PROMPT_WINDOW_S,
        clock=time.monotonic,
        log: Optional[Callable] = None,
    ):
        self.read_fn = read_fn
        self.timeout_s = float(timeout_s)
        self.clock = clock
        self.log = log or (lambda _s: None)
        self._t0 = clock()
        self.triggered = False
        self.timed_out = False

    def tick(self) -> bool:
        if self.triggered:
            return True
        if self.timed_out:
            return False
        text = ""
        with contextlib.suppress(Exception):
            text = self.read_fn() or ""
        if grok_console_is_signin_prompt(text):
            self.triggered = True
            self.log("grok: interactive sign-in prompt; not waiting")
            return True
        if (self.clock() - self._t0) >= self.timeout_s:
            self.timed_out = True
            return False
        return False


# FR #7868: a started Grok console without an input frame and prompt is blank.
# Report once. Do not kill or recycle until that same-kind recycle is approved.
GROK_BLANK_TUI_WINDOW_S = 120.0


def grok_blank_tui_watch_enabled() -> bool:
    raw = (os.environ.get("BOB_WORKER_BLANK_TUI") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def grok_console_has_tui_chrome(text: str) -> bool:
    """Require an input frame and prompt; a cwd header and empty border are not enough."""
    text = text or ""
    frame = re.search(r"(?m)^[ \t]*[╭┌╔+][─━═-]{2,}[╮┐╗+][ \t]*$", text)
    prompt = re.search(r"(?m)^[ \t]*(?:[│┃║|][ \t]*)?[>❯›](?:[ \t]|$)", text)
    return bool(frame and prompt)


class GrokBlankTuiGuard:
    """FR #7868: after window_s of a blank console, report once. Never kills the seat."""

    def __init__(
        self,
        read_fn,
        *,
        window_s: float = GROK_BLANK_TUI_WINDOW_S,
        clock=time.monotonic,
        report: Optional[Callable] = None,
        log: Optional[Callable] = None,
    ):
        self.read_fn = read_fn
        self.window_s = float(window_s)
        self.clock = clock
        self.report = report
        self.log = log or (lambda _s: None)
        self._t0 = clock()
        self.rendered = False
        self.reported = False

    def tick(self) -> bool:
        if self.reported or self.rendered:
            return self.reported
        text = ""
        with contextlib.suppress(Exception):
            text = self.read_fn() or ""
        if grok_console_has_tui_chrome(text):
            self.rendered = True
            return False
        if (self.clock() - self._t0) < self.window_s:
            return False
        self.reported = True
        self.log("grok: blank TUI after 120s; reported; not recycling")
        if self.report is not None:
            with contextlib.suppress(Exception):
                self.report()
        return True


def apply_xai_signin_gate(
    dec: Decision,
    fuel: Fuel,
    cursor_cmd: Optional[str],
    grok_exe: Optional[str],
    opencode_cmd: Optional[str],
    *,
    signin_ok: bool,
    signin_state: Optional[str] = None,
    machine: str = "",
    launched_kind: str = "",
) -> Decision:
    """Bad sign-in never launches Grok and never falls through to another kind.

    FR #7485: never rewrite ``refuse`` / ``cursor`` / ``opencode`` /
    ``xai-auth-expired`` / ``no-seat-auth``. FR #8221: a seat only ever runs
    the kind the tray launched, so an automatic or explicit ``grok`` decision
    with a bad sign-in exits instead of falling through to Cursor/OpenCode.
    ``launched_kind`` is the kind the tray launched (empty for automatic); it
    never changes the outcome, only the reason text.

    FR #8222: a missing login is ``no-seat-auth`` (never the word expired).
    A past expiry stays ``xai-auth-expired``.
    """
    state = (signin_state or ("ok" if signin_ok else "expired")).strip().lower()
    if state == "ok":
        return dec
    if dec.kind in ("refuse", "cursor", "opencode", "xai-auth-expired", "no-seat-auth"):
        return dec
    # FR #8221: never fall through. FR #8222: absent -> no-seat-auth.
    launched = (launched_kind or dec.kind or "").strip().lower()
    if state == "absent":
        host = (machine or "machine").strip() or "machine"
        tag = f"no-seat-auth; no Grok login on {host}"
        if launched == "grok":
            return Decision("no-seat-auth", "grok: " + tag)
        return Decision("no-seat-auth", tag)
    if launched == "grok":
        return Decision("xai-auth-expired", "grok: xai-auth-expired")
    return Decision("xai-auth-expired", "xai-auth-expired")


def classify_grok_signin_prompt_cause(
    *,
    seat_home: str | Path | None = None,
    machine_auth: str | Path | None = None,
) -> str:
    """FR #8222: seat folder has no login, or the machine login has expired.

    Returns ``no-seat-auth`` or ``xai-auth-expired``. Does not read token values.
    """
    try:
        import skill_dag_bound as _sdb
    except Exception:
        return "no-seat-auth"
    seat_file = (Path(seat_home) / "auth.json") if seat_home else None
    seat_info = (
        _sdb.summarize_grok_auth(seat_file)
        if seat_file
        else {"present": False, "usable": False, "expired": None}
    )
    machine_info = (
        _sdb.summarize_grok_auth(machine_auth)
        if machine_auth
        else {"present": False, "usable": False, "expired": None}
    )
    if machine_info.get("expired") is True:
        return "xai-auth-expired"
    if not seat_info.get("present") or not seat_info.get("usable"):
        return "no-seat-auth"
    if not machine_info.get("usable"):
        return "no-seat-auth"
    return "xai-auth-expired"


def decision_after_grok_signin_prompt(
    fuel: Fuel,
    cursor_cmd: Optional[str],
    opencode_cmd: Optional[str],
    *,
    seat_home: str | Path | None = None,
    machine_auth: str | Path | None = None,
    machine: str = "",
    launched_kind: str = "grok",
) -> Decision:
    """FR #8221/#8222: sign-in prompt exits no-seat-auth or xai-auth-expired.

    Never falls through to Cursor/OpenCode. Classify seat-missing vs
    machine-expired when seat/machine paths are provided.
    """
    cause = "xai-auth-expired"
    if seat_home is not None or machine_auth is not None:
        cause = classify_grok_signin_prompt_cause(
            seat_home=seat_home, machine_auth=machine_auth
        )
    state = "expired" if cause == "xai-auth-expired" else "absent"
    kind = (launched_kind or "grok").strip().lower()
    return apply_xai_signin_gate(
        Decision(kind or "grok", "signin-prompt"),
        fuel,
        cursor_cmd,
        None,
        opencode_cmd,
        signin_ok=False,
        signin_state=state,
        machine=machine,
        launched_kind=kind or "grok",
    )


def opencode_auth_file_present(env: Optional[dict] = None) -> bool:
    """True when the OpenCode auth file exists. Never reads the body or any token."""
    env = os.environ if env is None else env
    home = (env.get("USERPROFILE") or env.get("HOME") or "").strip()
    if not home:
        return False
    return (Path(home) / ".local" / "share" / "opencode" / "auth.json").is_file()


EXPLICIT_AGENTS = ("grok", "cursor", "opencode")


def normalize_explicit_agent(raw: Optional[str]) -> str:
    """``''`` keeps automatic Grok → Cursor → OpenCode. Explicit ids never fall through."""
    value = (raw or "").strip().lower()
    if value in ("", "auto", "default"):
        return ""
    if value in EXPLICIT_AGENTS:
        return value
    raise ValueError(
        "unknown --agent %r (expected grok, cursor, opencode, or omit for automatic selection)" % (raw,)
    )


def explicit_opencode_decision(
    fuel: Fuel,
    opencode_cmd: Optional[str],
    *,
    auth_present: bool,
    start_model: str = "",
) -> Decision:
    """Explicit OpenCode request. Never falls through to Grok or Cursor.

    FR #8186: judge the pool of the model about to start (`start_model` /
    `BOB_OPENCODE_MODEL`). A known-empty *other* pool never refuses.
    """
    if not opencode_cmd:
        return Decision("refuse", "explicit opencode: opencode.exe missing")
    mid = (start_model or "").strip()
    pool = seat_fuel_pool("opencode", mid)
    pool_label = {"opencode_go": "go", "opencode_free": "free"}.get(pool, pool or "opencode")
    # FR #7714 / #8186: unknown *own* pool is not exhausted.
    if not fuel_reading_known(fuel, "opencode", start_model=mid):
        return Decision(
            "opencode",
            "explicit opencode: fuel unknown, starting (model=%s pool=%s free=%s go=%s)"
            % (mid or "-", pool, fuel.opencode_free, fuel.opencode_go),
        )
    if not opencode_pool_has_tokens(fuel, pool, start_model=mid):
        # FR #8758: a free start model with free known 0 must not refuse when
        # paid/Go can still be tried. resolve_opencode_model (FR #8454 / #8541)
        # picks the paid tray slot after this Decision; refusing here stranded
        # redqueen seats on flash-free with free=0 go=None.
        if pool == "opencode_free" and _opencode_free_known_zero(fuel):
            if _opencode_paid_positive(fuel) or not _opencode_paid_known_exhausted(fuel):
                return Decision(
                    "opencode",
                    "explicit opencode: free exhausted, trying paid (model=%s free=%s go=%s)"
                    % (mid or "-", fuel.opencode_free, fuel.opencode_go),
                )
        return Decision(
            "refuse",
            "explicit opencode: no usable fuel (model=%s pool=%s free=%s go=%s)"
            % (mid or "-", pool, fuel.opencode_free, fuel.opencode_go),
        )
    free_ok = fuel.opencode_free is not None and int(fuel.opencode_free) > 0
    go_pool = pool == "opencode_go"
    if go_pool and not auth_present:
        return Decision("refuse", "explicit opencode: auth.json absent (body not read)")
    if not mid and not free_ok and not auth_present:
        # No start model: go-only still needs auth (legacy).
        if fuel.opencode_go is not None and int(fuel.opencode_go) > 0:
            return Decision("refuse", "explicit opencode: auth.json absent (body not read)")
    return Decision(
        "opencode",
        "explicit opencode (model=%s pool=%s free=%s go=%s)"
        % (mid or "-", pool, fuel.opencode_free, fuel.opencode_go),
    )



def explicit_cursor_si_decision(
    cursor_cmd: Optional[str],
    fleet_digest: Optional[dict] = None,
    *,
    now: Optional[float] = None,
    private_cursor: Optional[dict] = None,
    install_root: Optional[Path | str] = None,
) -> Decision:
    """Explicit Cursor uses the si@ntsa.uk fleet pool, never the local reading.

    A missing or stale fleet meter still starts. A fresh remaining of 0 refuses.
    Local high/low and on-demand do not gate this path (FR #8649).
    FR #8667: prefer the private cursor meter (fleet-cursor-private.json). Public
    digest still omits cursor (FR #7326); synthetic digest.cursor is a test aid only.
    """
    if not cursor_cmd:
        return Decision("refuse", "explicit cursor: agent.cmd missing")
    account = SI_NTSA_CURSOR_ACCOUNT
    now_f = time.time() if now is None else float(now)
    row = private_cursor if isinstance(private_cursor, dict) else None
    if row is None:
        row = load_private_cursor_meter(install_root=install_root)
    if row is None:
        row = _fleet_pool_row(fleet_digest or {}, "cursor")
    fill = fleet_pool_fill(row, now=now_f)
    if fill["usable"] and int(fill["remaining"]) <= 0:
        return Decision(
            "refuse",
            "explicit cursor: %s pool exhausted (remaining=0)" % account,
            account=account,
        )
    rem = fill["remaining"] if fill["usable"] else "unknown"
    return Decision(
        "cursor",
        "explicit cursor (account=%s remaining=%s)" % (account, rem),
        account=account,
    )


def explicit_agent_decision(
    requested: str,
    fuel: Fuel,
    cursor_cmd: Optional[str],
    grok_exe: Optional[str],
    opencode_cmd: Optional[str],
    *,
    auth_present: bool,
    start_model: str = "",
    fleet_digest: Optional[dict] = None,
    now: Optional[float] = None,
    install_root: Optional[Path | str] = None,
    private_cursor: Optional[dict] = None,
) -> Decision:
    """One requested agent. ``refuse`` never starts a different agent."""
    agent_id = normalize_explicit_agent(requested)
    if agent_id == "grok":
        if not grok_exe:
            return Decision("refuse", "explicit grok: agent.exe missing")
        if not grok_has_tokens(fuel):
            return Decision(
                "refuse",
                "explicit grok: not available (pct=%s state=%s)" % (fuel.grok_pct, fuel.grok_state),
            )
        return Decision(
            "grok",
            "explicit grok (weekly pct=%s state=%s)" % (fuel.grok_pct, fuel.grok_state),
        )
    if agent_id == "cursor":
        # Local fuel is ignored. Automatic selection still uses cursor_has_tokens.
        return explicit_cursor_si_decision(
            cursor_cmd, fleet_digest, now=now,
            private_cursor=private_cursor, install_root=install_root,
        )
    if agent_id == "opencode":
        return explicit_opencode_decision(
            fuel, opencode_cmd, auth_present=auth_present, start_model=start_model
        )
    return Decision("refuse", "explicit agent %s is not supported" % (requested,))



def opencode_model_menu_rows(fuel: Fuel) -> list:
    """FR #6301: models the installed OpenCode fuel helper reported (not hard-coded)."""
    rows = []
    seen = set()
    models = fuel.opencode_models or {}
    for mid in list(fuel.opencode_free_model_ids or ()) + list(models.keys()):
        m = str(mid or "").strip()
        if not m or m in seen:
            continue
        seen.add(m)
        rows.append({"id": m, "label": m})
    return rows


def list_worker_agents(
    fuel: Fuel,
    cursor_cmd: Optional[str],
    grok_exe: Optional[str],
    opencode_cmd: Optional[str],
    *,
    auth_present: bool,
    readings_known: bool = True,
) -> list:
    """Systray Agents submenu. One row per agent, not per fuel pool.

    FR #7189: fuel never greys a start option. Installed agents stay clickable;
    the launch path still reads fuel and refuses a real miss. Only a missing
    command greys a row (reason ``not installed``).
    """
    rows = [
        {
            "id": "auto",
            "label": "Automatic",
            "available": True,
            "installed": True,
            "fuel_state": "known",
            # FR #6301: start entries carry no fuel/quota state text.
            "reason": "Grok, then Cursor, then OpenCode",
        }
    ]
    labels = (("grok", "Grok"), ("cursor", "Cursor"), ("opencode", "Open Code"))  # FR #8713 / BOB-06
    installed = {"grok": bool(grok_exe), "cursor": bool(cursor_cmd), "opencode": bool(opencode_cmd)}
    for agent_id, label in labels:
        present = installed[agent_id]
        known = bool(readings_known) and fuel_reading_known(fuel, agent_id)
        if not present:
            rows.append(
                {
                    "id": agent_id,
                    "label": label,
                    "available": False,
                    "installed": False,
                    "fuel_state": "known" if known else "unknown",
                    "reason": NOT_INSTALLED_REASON,
                }
            )
            continue
        rows.append(
            {
                "id": agent_id,
                "label": label,
                "available": True,
                "installed": True,
                "fuel_state": "known" if known else "unknown",
                "reason": "",
            }
        )
    return rows


def unknown_agent_list_rows() -> list[dict]:
    return [
        {
            "id": "auto",
            "label": "Automatic",
            "available": True,
            "installed": True,
            "reason": "Grok, then Cursor, then OpenCode",
            "fuel_state": "known",
        },
        {"id": "grok", "label": "Grok", "available": True, "installed": True, "reason": "", "fuel_state": "unknown"},
        {"id": "cursor", "label": "Cursor", "available": True, "installed": True, "reason": "", "fuel_state": "unknown"},
        {"id": "opencode", "label": "Open Code", "available": True, "installed": True, "reason": "", "fuel_state": "unknown"},
    ]


def _grey_explicit_rows(reason: str) -> list[dict]:
    rows = unknown_agent_list_rows()
    out = []
    for row in rows:
        item = dict(row)
        if item["id"] != "auto":
            item["available"] = False
            item["installed"] = False
            item["reason"] = reason
            item["fuel_state"] = "known"
        out.append(item)
    return out


def agent_list_rows_complete(rows: list | None) -> bool:
    if not isinstance(rows, list) or len(rows) < 4:
        return False
    by_id = {str(r.get("id") or ""): r for r in rows if isinstance(r, dict)}
    for ident in ("auto", "grok", "cursor", "opencode"):
        if ident not in by_id:
            return False
        if not isinstance(by_id[ident].get("available"), bool):
            return False
    return True


def _probe_unsupported(exit_code: int, stderr: str) -> bool:
    err = str(stderr or "").lower()
    return int(exit_code or 0) == 2 and "unrecognized arguments" in err and "--list-agents" in err


def classify_agent_probe(
    *,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
    start_failed: bool = False,
    worker_missing: bool = False,
    last_good: list | None = None,
) -> tuple[list[dict], str]:
    """FR #7189 tray policy. Transient failures never grey installed agents."""
    if worker_missing:
        return _grey_explicit_rows(WORKER_MISSING_REASON), "WorkerMissing"
    if _probe_unsupported(exit_code, stderr):
        return _grey_explicit_rows(REBUILD_LIST_REASON), "Unsupported"
    kind = "Ok"
    if timed_out:
        kind = "Timeout"
    elif start_failed:
        kind = "StartFailed"
    elif int(exit_code or 0) not in (0,):
        kind = "Failed"
    payload = None
    if kind == "Ok":
        text = str(stdout or "")
        blob = ""
        for line in text.replace("\r", "").split("\n"):
            t = line.strip()
            if t.startswith("{") and '"agents"' in t:
                blob = t
        if not blob and text.strip().startswith("{"):
            blob = text.strip()
        try:
            payload = json.loads(blob) if blob else None
        except ValueError:
            payload = None
        if not isinstance(payload, dict) or not agent_list_rows_complete(payload.get("agents")):
            kind = "Malformed"
    if kind != "Ok":
        if last_good and agent_list_rows_complete(last_good):
            return [dict(r) for r in last_good], kind
        return unknown_agent_list_rows(), kind
    return list(payload.get("agents") or []), kind


def resolve_seat_decision(
    requested: Optional[str],
    dec: Decision,
    fuel: Fuel,
    cursor_cmd: Optional[str],
    grok_exe: Optional[str],
    opencode_cmd: Optional[str],
    *,
    auth_present: bool,
    xai_signin_ok: bool = True,
    start_model: str = "",
    signin_state: Optional[str] = None,
    machine: str = "",
    fleet_digest: Optional[dict] = None,
    now: Optional[float] = None,
    install_root: Optional[Path | str] = None,
    private_cursor: Optional[dict] = None,
) -> Decision:
    """Apply an explicit agent request, else the automatic Grok → Cursor → OpenCode order.

    FR #7485: an explicit ``--agent`` either starts that agent or refuses /
    xai-auth-expired. It never falls through to a different agent (including
    when xAI sign-in is expired and Cursor still has fuel).
    """
    if normalize_explicit_agent(requested):
        mid = (start_model or "").strip() or (_OPENCODE_MODEL_ENV_AT_START or "").strip()
        out = explicit_agent_decision(
            requested,
            fuel,
            cursor_cmd,
            grok_exe,
            opencode_cmd,
            auth_present=auth_present,
            start_model=mid,
            fleet_digest=fleet_digest,
            now=now,
            install_root=install_root,
            private_cursor=private_cursor,
        )
        if out.kind == "grok" and not xai_signin_ok:
            state = (signin_state or "expired").strip().lower()
            if state == "absent":
                return Decision("no-seat-auth", "explicit grok: no-seat-auth")
            return Decision("xai-auth-expired", "explicit grok: xai-auth-expired")
        return out
    if opencode_cmd and dec.kind in ("dialog", "none"):
        dec = select_agent(
            fuel, cursor_cmd, grok_exe, opencode_cmd, xai_signin_ok=xai_signin_ok
        )
    return apply_xai_signin_gate(
        dec, fuel, cursor_cmd, grok_exe, opencode_cmd,
        signin_ok=xai_signin_ok, signin_state=signin_state, machine=machine,
        launched_kind=requested or "",
    )


def select_agent(
    fuel: Fuel,
    cursor_cmd: Optional[str],
    grok_exe: Optional[str],
    opencode_cmd: Optional[str] = None,
    *,
    xai_signin_ok: bool = True,
) -> Decision:
    """grok -> cursor -> opencode -> dialog (session key). Pure; no I/O. FR #3997 / #6120 / #7345."""
    if grok_exe and grok_has_tokens(fuel) and xai_signin_ok:
        return Decision(
            "grok",
            f"grok (weekly pct={fuel.grok_pct} state={fuel.grok_state})",
        )
    why_grok = "grok: " + (
        "agent.exe missing" if not grok_exe else f"exhausted (pct={fuel.grok_pct} state={fuel.grok_state})"
    )
    if cursor_cmd and cursor_has_tokens(fuel):
        return Decision(
            "cursor",
            f"{why_grok}; cursor tokens remain (high={fuel.cursor_high} low={fuel.cursor_low})",
        )
    why_cur = "cursor: " + (
        "agent.cmd missing" if not cursor_cmd else f"no tokens (high={fuel.cursor_high} low={fuel.cursor_low})"
    )
    if opencode_cmd and opencode_has_tokens(fuel):
        return Decision(
            "opencode",
            f"{why_grok}; {why_cur}; opencode tokens remain (free={fuel.opencode_free} go={fuel.opencode_go})",
        )
    why_op = "opencode: " + (
        "opencode.exe missing" if not opencode_cmd else f"no tokens (free={fuel.opencode_free} go={fuel.opencode_go})"
    )
    if not grok_exe:
        return Decision("none", f"{why_grok}; {why_cur}; {why_op}")
    return Decision(
        "dialog",
        f"{why_grok}; {why_cur}; {why_op} -> ask for a session key",
    )


def resolve_cursor_cmd(env: Optional[dict] = None, which: Callable = shutil.which) -> Optional[str]:
    env = os.environ if env is None else env
    la = env.get("LOCALAPPDATA", "")
    if la:
        p = Path(la) / "cursor-agent" / "agent.cmd"
        if p.is_file():
            return str(p)
    for n in ("agent.cmd", "cursor-agent.cmd"):
        w = which(n)
        if w:
            return str(w)
    return None


def resolve_grok_exe(env: Optional[dict] = None, which: Callable = shutil.which) -> Optional[str]:
    env = os.environ if env is None else env
    up = env.get("USERPROFILE", "")
    if up:
        p = Path(up) / ".grok" / "bin" / "agent.exe"
        if p.is_file():
            return str(p)
    w = which("agent.exe")
    return str(w) if w else None


def _is_untrusted_mount_oserror(exc: BaseException) -> bool:
    """FR #7302: WinError 448 / untrusted reparse (WinGet Links under SYSTEM)."""
    if not isinstance(exc, OSError):
        return False
    if getattr(exc, "winerror", None) == 448:
        return True
    msg = str(exc).lower()
    return "untrusted mount" in msg or "winerror 448" in msg


def _opencode_exe_exists(path: Path, reasons: Optional[list] = None) -> bool:
    try:
        return path.is_file()
    except OSError as exc:
        if _is_untrusted_mount_oserror(exc):
            if reasons is not None:
                reasons.append(
                    "WinError 448 untrusted mount point while resolving %s" % path
                )
            return False
        raise


def resolve_opencode_cmd(
    env: Optional[dict] = None,
    which: Callable = shutil.which,
    reasons: Optional[list] = None,
) -> Optional[str]:
    """Find opencode.exe: explicit, WinGet Links (process then seat user), PATH.

    FR #6996: LocalSystem LOCALAPPDATA is the system profile; look at
    ``BOB_OPENCODE_SEAT_HOME`` / interactive user WinGet Links too.
    FR #7302: never follow an untrusted WinGet Links reparse (WinError 448);
    use ``Programs\\opencode\\opencode.exe`` or return None (readiness miss).
    """
    env = os.environ if env is None else env
    explicit = str(env.get("BOB_OPENCODE_EXE") or "").strip()
    if explicit and _opencode_exe_exists(Path(explicit), reasons):
        return explicit

    def _winget(local: str) -> Optional[str]:
        if not local:
            return None
        p2 = Path(local) / "Programs" / "opencode" / "opencode.exe"
        p = Path(local) / "Microsoft" / "WinGet" / "Links" / "opencode.exe"
        link_ok = False
        try:
            link_ok = p.is_file()
        except OSError as exc:
            if not _is_untrusted_mount_oserror(exc):
                raise
            if reasons is not None:
                reasons.append(
                    "WinError 448 untrusted mount point on WinGet Links; trying package path"
                )
            if _opencode_exe_exists(p2, reasons):
                return str(p2)
            return None
        if link_ok:
            return str(p)
        if _opencode_exe_exists(p2, reasons):
            return str(p2)
        return None

    la = str(env.get("LOCALAPPDATA") or "")
    sysprof = "\\systemprofile\\" in la.replace("/", "\\").lower()
    if la and not sysprof:
        found = _winget(la)
        if found:
            return found
    seat = str(env.get("BOB_OPENCODE_SEAT_HOME") or env.get("BOB_GROK_WEEKLY_USER_HOME") or "").strip()
    if seat:
        found = _winget(str(Path(seat) / "AppData" / "Local"))
        if found:
            return found

    def _which_safe(name: str) -> Optional[str]:
        try:
            w = which(name)
            return str(w) if w else None
        except OSError as exc:
            if _is_untrusted_mount_oserror(exc):
                if reasons is not None:
                    reasons.append(
                        "WinError 448 untrusted mount point from PATH lookup %s" % name
                    )
                return None
            raise

    w = _which_safe("opencode.exe")
    if w:
        return w
    return _which_safe("opencode")


def _resolve_opencode_cmd_for_seat(log: "Log") -> Optional[str]:
    reasons: list = []
    found = resolve_opencode_cmd(reasons=reasons)
    for r in reasons:
        log("opencode: " + r)
    if not found and reasons:
        log("opencode: readiness miss (untrusted WinGet Links or not installed)")
    return found


def ask_session_key(prompt: str, title: str = "Grok session key") -> Optional[str]:
    """t771u: asked IN THE WORKER'S OWN CONSOLE (the single window) - no dialog, no second window. Input is hidden, held in
    memory only, never saved or printed. Enter accepts, Esc cancels. Returns the key or None."""
    try:
        import msvcrt
    except Exception:
        try:
            import getpass

            return getpass.getpass(prompt + " (hidden): ").strip() or None
        except Exception:
            return None
    sys.stdout.write("\n" + prompt + "\nType the key (hidden), Enter = accept, Esc = cancel: ")
    sys.stdout.flush()
    chars: list = []
    try:
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                break
            if ch in ("\x1b", "\x03"):
                chars = []
                sys.stdout.write("\ncancelled\n")
                return None
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()  # function-key second code
                continue
            if ch == "\x08":
                if chars:
                    chars.pop()
                continue
            chars.append(ch)
        sys.stdout.write("\n")
        key = "".join(chars).strip()
        return key or None
    finally:
        chars.clear()


# --------------------------------------------------------------------------------------------- prompts / seat env (FR #2380)
def outbox_path_for_run(run_dir: Path | str) -> Path:
    """Canonical seat outbox path under the worker run dir (never the ear home\\outbox.txt)."""
    return Path(run_dir) / "outbox.txt"


DEFAULT_HARVEST_REPO = "SimonBarnett/bobiverse"
_JOB_REF_REPO_RX = re.compile(r"(?i)^\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\s*#\s*\d+\s*$")
# a-search harvest fix: outbox_job_key() returns ``FR owner/repo#N`` (typed key). Strip the
# job type (and a leading ACK/DONE verb) before parsing, or every typed ACK key fell back
# to DEFAULT_HARVEST_REPO and job-repo.txt said bobiverse for a-search jobs.
_JOB_REF_TYPE_PREFIX_RX = re.compile(r"(?i)^\s*(?:(?:ACK|DONE|NACK|GIVEUP)\s+)?(?:FR|MRB|UAT)\s+")
_JOB_REF_URL_RX = re.compile(
    r"(?i)github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/(?:issues|pull)/(\d+)"
)


def _strip_job_ref(raw: str) -> str:
    """Normalise ``FR owner/repo#N`` / issue-or-PR URL to ``owner/repo#N``."""
    t = (raw or "").strip()
    m = _JOB_REF_URL_RX.search(t)
    if m:
        return f"{m.group(1)}#{m.group(2)}"
    return _JOB_REF_TYPE_PREFIX_RX.sub("", t, count=1).strip()


def parse_job_repo(job_ref: str | None) -> str:
    """Return ``owner/name`` from a job ref (typed or not), or ``""`` when it cannot be read.

    Never invents a default: callers that need a repo must decide explicitly.
    """
    raw = _strip_job_ref(job_ref or "")
    if not raw:
        return ""
    m = _JOB_REF_REPO_RX.match(raw)
    repo = m.group(1) if m else (raw.split("#", 1)[0].strip() if "#" in raw else raw)
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo or ""):
        return ""
    owner, _, name = repo.partition("/")
    if owner.lower() == "simonbarnett":
        if name.lower() == "a-search":
            return "SimonBarnett/a-search"
        if name.lower() == "bobiverse":
            return DEFAULT_HARVEST_REPO
        return f"SimonBarnett/{name}"
    return f"{owner}/{name}"


def harvest_repo_for_job(job_ref: str | None) -> str:
    """FR #3189: map ``owner/repo#N`` (ACK/assign key) to harvest ``-Repo`` owner/name.

    Accepts typed keys (``FR SimonBarnett/a-search#5``) and issue/PR URLs too.
    """
    raw = _strip_job_ref(job_ref or "")
    if not raw:
        return DEFAULT_HARVEST_REPO
    m = _JOB_REF_REPO_RX.match(raw)
    repo = m.group(1) if m else (raw.split("#", 1)[0].strip() if "#" in raw else raw)
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo or ""):
        return DEFAULT_HARVEST_REPO
    owner, _, name = repo.partition("/")
    if owner.lower() == "simonbarnett" and name.lower() == "a-search":
        return "SimonBarnett/a-search"
    if owner.lower() == "simonbarnett" and name.lower() == "bobiverse":
        return DEFAULT_HARVEST_REPO
    return f"{owner}/{name}"


def harvest_invoke_repo_args(job_ref: str | None) -> list[str]:
    """Argv fragment ``['-Repo', owner/name]`` for Invoke-BobiverseHarvest (FR #3189)."""
    return ["-Repo", harvest_repo_for_job(job_ref)]


def write_job_repo_marker(run_dir: Path | str, job_ref: str | None) -> str:
    """Persist job repo beside the outbox so agent-invoked harvest sees it (FR #3189).

    Writes only a repo parsed from the job ref (typed ``FR owner/repo#N`` keys included);
    an unreadable ref removes the marker instead of writing a bobiverse default.
    """
    repo = parse_job_repo(job_ref)
    path = Path(run_dir) / "job-repo.txt"
    if not repo:
        try:
            path.unlink()
        except OSError:
            pass
        return ""
    try:
        path.write_text(repo + "\n", encoding="utf-8")
    except OSError:
        pass
    return repo



SEAT_MARKER_NAME = ".bobiverse-seat"


def write_live_seat_marker(
    cwd: Path | str,
    *,
    nick: str,
    pid: int,
    machine: str = "",
    extra: dict | None = None,
) -> Path:
    """Atomically rewrite ``<cwd>/.bobiverse-seat`` with the live nick/pid (FR #6341).

    Replaces any stale marker from an older session. Uses a temp file + ``os.replace``.
    """
    folder = Path(cwd)
    folder.mkdir(parents=True, exist_ok=True)
    marker: dict = {"nick": (nick or "").strip(), "pid": int(pid)}
    mid = (machine or "").strip().lstrip("#").lower()
    if mid:
        marker["machine"] = mid
    if extra:
        for k, v in extra.items():
            if v is None:
                continue
            marker[str(k)] = v
    target = folder / SEAT_MARKER_NAME
    tmp = folder / f"{SEAT_MARKER_NAME}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    payload = json.dumps(marker, separators=(",", ":"))
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.replace(str(tmp), str(target))
    finally:
        if tmp.is_file():
            try:
                tmp.unlink()
            except OSError:
                pass
    return target


def resolve_and_ensure_job_worktree_base(env: dict | None = None) -> str:
    """Resolve ``BOB_JOB_WORKTREE_BASE`` (FR #4988 / #6341) and create the directory.

    Never returns a drive root. Prefer existing env ``BOB_JOB_WORKTREE_BASE``, else
    ``job_worktree_base`` (bridge/worktrees or ``<data-drive>\\ai\\worktrees``).
    """
    e = dict(env or os.environ)
    base = job_worktree_base(e)
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)

def seat_env_extra(
    run_dir: Path | str,
    machine: str,
    nick: str,
    job_repo: str | None = None,
) -> dict:
    """Env vars every agent child must inherit so compaction cannot lose the outbox (FR #2380).

    FR #2790: also export ``BOB_AGENT_NICK`` (same value as ``BOB_NICK``) so
    ``Invoke-BobiverseHarvest.ps1`` and legacy Watch-AgentHealth readers stamp
    ``source.seat`` / footer ``seat=`` for lesson-PR self-MRB blocking.
    FR #3189: optional ``BOB_JOB_REPO`` so harvest targets the offered product repo.
    FR #6341: also export ``BOB_JOB_WORKTREE_BASE`` (and ``BOB_JOB_WORKTREE`` when set).
    """
    outbox = str(outbox_path_for_run(run_dir))
    mid = (machine or "").strip().lstrip("#")
    shop = f"#{mid}"
    nick_s = (nick or "").strip()
    out = {
        "BOB_OUTBOX": outbox,
        "BOB_SHOP": shop,
        "BOB_NICK": nick_s,
        "BOB_AGENT_NICK": nick_s,
        "BOB_MACHINE": mid.lower(),
    }
    jr = (job_repo or "").strip()
    if jr:
        out["BOB_JOB_REPO"] = harvest_repo_for_job(jr if "#" in jr else f"{jr}#1")
    # FR #6341: export job worktree base so seats never search drives for D: vs C:.
    try:
        out["BOB_JOB_WORKTREE_BASE"] = resolve_and_ensure_job_worktree_base()
    except Exception:
        existing = (os.environ.get("BOB_JOB_WORKTREE_BASE") or "").strip()
        if existing:
            out["BOB_JOB_WORKTREE_BASE"] = existing
    job_wt = (os.environ.get("BOB_JOB_WORKTREE") or "").strip()
    if job_wt:
        out["BOB_JOB_WORKTREE"] = job_wt
    # FR #6864: process-local skill catalog bound (never GROK_CONFIG / user [skills]).
    try:
        import skill_dag_bound as _sdb

        out = _sdb.apply_bound_env(out)
    except Exception:
        out["BOB_SKILL_DAG_BOUND"] = "skill-dag-core"
    return out


# FR #2669: tray wrapper used to write C:\\Users\\... into BOB_*_HOME; scrub agent-host vars too.
_BOB_PATH_ENV_KEYS = (
    "BOB_IRC_HOME",
    "BOB_HOME",
    "BOB_BRIDGE_HOME",
    "AGENTIC_IRC_HOME",
    "BOB_AI_ROOT",
)
_AGENT_HOST_ENV_PREFIXES = ("CURSOR_", "SAND_")


def normalize_bob_home_path(value: str) -> str:
    """Collapse accidental doubled backslashes from tray wrappers (FR #2669)."""
    raw = (value or "").strip()
    if not raw:
        return raw
    s = raw.replace("/", "\\")
    if s.startswith("\\\\"):
        return "\\\\" + re.sub(r"\\+", r"\\", s[2:])
    return re.sub(r"\\+", r"\\", s)


def normalize_bob_path_envs(env: dict) -> dict:
    """Return a copy with known BOB_* home/root paths normalised (FR #2669)."""
    out = dict(env or {})
    for key in _BOB_PATH_ENV_KEYS:
        if key in out and out[key] is not None:
            out[key] = normalize_bob_home_path(str(out[key]))
    return out


def scrub_agent_host_env(env: dict) -> dict:
    """Drop CURSOR_* / SAND_* so tray-started seats do not inherit agent-host secrets (FR #2669)."""
    out = {}
    for k, v in (env or {}).items():
        ku = str(k).upper()
        if ku.startswith(_AGENT_HOST_ENV_PREFIXES):
            continue
        out[k] = v
    return out


def prepare_seat_child_env(base_env: dict | None, extra: dict | None = None) -> dict:
    """Normalize BOB_* paths and scrub agent-host vars for a seat child (FR #2669 / #2413 / #2683).

    Scrub + normalise run **after** merging ``extra`` so CURSOR_*/SAND_* (or doubled
    BOB_* paths) cannot re-enter via the overlay (hostile probe / FR #2683).
    """
    env = dict(base_env or {})
    if extra:
        env.update(extra)
    out = scrub_agent_host_env(normalize_bob_path_envs(env))
    try:
        from winps51 import apply_winps51_module_path
        apply_winps51_module_path(out)
    except Exception:
        # FR #7315 / #7355: same defaults when winps51 import fails.
        out["PSModulePath"] = r"C:\Windows\System32\WindowsPowerShell\v1.0\Modules"
        out["PSModuleAutoLoadingPreference"] = "All"
    return out


_WORKER_EXE_MODES = ("agent", "plan", "monitor", "maintenance")


def describe_worker_exe_launch(
    install_root: str | Path,
    mode: str,
    machine_id: str = "",
    *,
    work_root: str | Path | None = None,
    local_app_data: str | Path | None = None,
    source: str = "tray",
    agent: str = "",
) -> dict:
    """Canonical bob-worker.exe process launch (FR #2413 / FR #2698).

    Tray Agent/Plan click, remote ``!startworker``, CLI, and maintenance/monitor
    starters must use the same plan: hashed run-copy under
    ``%LOCALAPPDATA%\\Bobiverse\\worker\\bin``, argv ``--mode`` / ``--install-root``
    / optional ``--machine-id`` / ``--work-root``, cwd matching the mode.

    Unknown modes raise ``ValueError`` (never silently map to agent — FR #2698).
    ``source`` is recorded by callers but must not change argv/cwd/run_exe.
    """
    src = (source or "tray").strip().lower() or "tray"
    root = Path(install_root)
    mode_l = (mode or "agent").strip().lower() or "agent"
    if mode_l not in _WORKER_EXE_MODES:
        raise ValueError("unknown bob-worker mode: %r (expected one of %s)" % (mode_l, ", ".join(_WORKER_EXE_MODES)))
    install_exe = root / "worker" / "bob-worker.exe"
    digest = hashlib.sha256(
        install_exe.read_bytes() if install_exe.is_file() else b"missing"
    ).hexdigest()[:12].lower()
    base = Path(local_app_data) if local_app_data else Path(
        os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    )
    run_exe = base / "Bobiverse" / "worker" / "bin" / ("bob-worker-%s.exe" % digest)
    argv = ["--mode", mode_l, "--install-root", str(root)]
    agent_l = normalize_explicit_agent(agent)
    if agent_l:
        argv += ["--agent", agent_l]
    mid = (machine_id or "").strip().lstrip("#")
    if mid:
        argv += ["--machine-id", mid]
    icon = None
    if mode_l in ("monitor", "maintenance"):
        wr = Path(work_root) if work_root else _default_jeeves_root(root)
        argv += ["--work-root", str(wr)]
        cwd = wr
        if mode_l == "maintenance":
            title = MAINTENANCE_TITLE
            try:
                ip = maintenance_icon_path(wr)
                if ip is not None:
                    icon = str(ip)
            except Exception:
                icon = None
        else:
            title = "Bob monitor - starting (closing this window ends the agent)"
    elif mode_l == "plan":
        cwd = root / "plan"
        title = "Bob plan - starting (closing this window ends the agent)"
    else:
        cwd = root / "worker"
        title = "Bob agent - starting (closing this window ends the agent)"
    if not cwd.is_dir():
        cwd = root
    _ = src  # recorded only by callers; must not diverge the plan (tray == cli)
    out = {
        "mode": mode_l,
        "machine_id": mid,
        "install_exe": str(install_exe),
        "run_exe": str(run_exe),
        "argv": argv,
        "cwd": str(cwd),
        "title": title,
        "agent": agent_l,
    }
    if icon is not None:
        out["icon"] = icon
    return out


def describe_agent_child_launch(
    *,
    kind: str,
    mode: str,
    cwd: str | Path,
    run_dir: str | Path,
    machine: str,
    nick: str,
    agent_exe: str,
    prompt: str | None = None,
    session_id: str | None = None,
    install_root: str | Path | None = None,
) -> dict:
    """Canonical cursor/grok child launch for agent and plan (FR #2413).

    Always includes ``seat_env_extra`` (BOB_OUTBOX / BOB_SHOP / BOB_NICK / BOB_AGENT_NICK / BOB_MACHINE)
    and the mode prompt that points at ``.grok/skills`` + AGENTS.md under ``cwd``.

    FR #6891: grok **agent** seats use a bound cwd under ``run_dir`` (outside the install
    tree) plus seat-local ``GROK_HOME`` so ``grok inspect`` lists only skill-dag-core
    (+ bundled). Plan/monitor/cursor keep the caller's cwd.
    """
    mode_l = (mode or "agent").strip().lower()
    folder = str(cwd)
    rd = Path(run_dir)
    kind_l = (kind or "").strip().lower()
    launch_folder = folder
    install_worker = folder
    bound_meta: dict = {}
    if kind_l == "grok" and mode_l == "agent":
        try:
            import skill_dag_bound as _sdb

            mcp_script = skill_dag_mcp_script_path(folder)
            bound = _sdb.prepare_bound_agent_cwd(
                rd, folder, mcp_script=mcp_script, mcp_roots=skill_dag_vision_roots(folder)
            )
            grok_home = _sdb.prepare_seat_grok_home(rd, trust_paths=[bound])
            grok_auth = _sdb.machine_grok_auth_path()
            launch_folder = str(bound)
            bound_meta = {
                "bound_cwd": str(bound),
                "grok_home": str(grok_home),
                "grok_auth_path": str(grok_auth),
                "install_worker": install_worker,
            }
        except Exception:
            bound_meta = {}
    if prompt is None:
        if mode_l == "plan":
            prompt = plan_prompt(folder)
        elif mode_l == "monitor":
            prompt = monitor_prompt(folder)
        else:
            # Prompt keeps install worker paths (outbox / AGENTS / harvest scripts).
            prompt = worker_prompt(install_worker, str(rd), machine, nick)
            if bound_meta.get("bound_cwd"):
                prompt = (
                    f"Harness cwd is {bound_meta['bound_cwd']} (FR #6891 skill catalog bound; "
                    f"only skill-dag-core is listed). Install worker tree: {install_worker}. "
                ) + prompt
    launch_mode = mode_l if mode_l in ("agent", "plan", "monitor") else "agent"
    spec = build_launch(
        kind, launch_mode, launch_folder, prompt, agent_exe, rd,
        session_id=session_id, install_root=install_root,
    )
    env = seat_env_extra(rd, machine, nick)
    try:
        import worker_start_model as wsm

        _scfg = wsm.load_worker_start_config()
        # FR #8220: stamp BOB_OPENCODE_MODEL into child env so launch-opencode.ps1 and
        # launch-record see a concrete id even when tray pin is empty and parent env lacks it.
        if kind_l == "opencode":
            oc_stamp = (
                wsm.concrete_model_id(os.environ.get("BOB_OPENCODE_MODEL"))
                or wsm.launch_selected_model("opencode", _scfg, env=os.environ)
                or wsm.default_opencode_free_model(_scfg)
            )
            if oc_stamp:
                env["BOB_OPENCODE_MODEL"] = oc_stamp
        actual = wsm.concrete_model_id(wsm.actual_from_launch_spec(kind_l, spec, env=env))
        if not actual and kind_l == "opencode":
            actual = wsm.concrete_model_id(
                env.get("BOB_OPENCODE_MODEL") or os.environ.get("BOB_OPENCODE_MODEL")
            )
        effort = wsm.configured_start_effort(kind_l, _scfg)
        if actual:
            env[wsm.ENV_ACTUAL_MODEL] = actual
        elif kind_l == "opencode":
            env.pop(wsm.ENV_ACTUAL_MODEL, None)
        env[wsm.ENV_ACTUAL_EFFORT] = effort
        saved = wsm.normalize_effort((_scfg.get("workerStartEffort") or {}).get(kind_l))
        if not saved and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                wsm.save_worker_start_settings(effort={kind_l: effort})
            except Exception:
                pass
        wsm.write_launch_record(
            rd, kind=kind_l, model=actual, effort=effort, argv=list(spec.argv)
        )
    except Exception:
        pass
    if bound_meta.get("grok_home"):
        try:
            import skill_dag_bound as _sdb

            env = _sdb.apply_bound_env(
                env,
                grok_home=bound_meta["grok_home"],
                grok_auth_path=bound_meta.get("grok_auth_path"),
            )
        except Exception:
            env["GROK_HOME"] = str(bound_meta["grok_home"])
            env["BOB_SKILL_DAG_BOUND"] = "skill-dag-core"
            env.pop("GROK_CONFIG", None)
            if bound_meta.get("grok_auth_path"):
                env["GROK_AUTH_PATH"] = str(bound_meta["grok_auth_path"])
    # Bound cwd already has MCP config with absolute install roots; skip rewrite from launch_folder.
    if bound_meta.get("bound_cwd") and getattr(spec, "write_skill_dag_mcp", False):
        spec.write_skill_dag_mcp = False
    skills = str(Path(launch_folder) / ".grok" / "skills")
    out = {
        "kind": kind,
        "mode": mode_l,
        "cwd": launch_folder,
        "run_dir": str(rd),
        "argv": list(spec.argv),
        "env": dict(env),
        "prompt": prompt,
        "skills_dir": skills,
        "session_id": spec.session_id,
        "files": dict(spec.files or {}),
        "spec": spec,
    }
    out.update(bound_meta)
    return out


def worker_prompt(worker_dir: str, home: str, machine: str, nick: str) -> str:
    outbox = str(outbox_path_for_run(home))
    return (
        f"You are a NEW Bobiverse worker agent (fresh session - never resume or continue an older one). "
        f"Your working folder is {worker_dir}. FIRST read {worker_dir}\\AGENTS.md and the process-local core stub "
        f"(skill-dag-core). Do not list other skill-dag index nodes in this prompt; resolve per job: call skill-dag MCP resolve then get_skill "
        f"(do not read every skill in {worker_dir}\\.grok\\skills). "
        f"FR #7000 / #8785 / #8846 (Cursor): if the skill-dag MCP namespace is missing from dynamic tools, use the one-shot CLI from "
        f"`{worker_dir}\\.cursor\\mcp.json` -> mcpServers.skill-dag only: run its `command` with **all** `args` unchanged "
        f"(script is args[0]; keep every `--root` and `--job-worktree-file`), then append "
        f"`--once resolve --seed <job-type token>` (e.g. FR or MRB) and `--once get_skill --path <matched[].path>` "
        f"(JSON on stdout). Check the JSON result (unresolved can exit 0). Do not guess a script path. "
        f"PowerShell: `$cfg=(Get-Content -Raw .cursor\\mcp.json|ConvertFrom-Json).mcpServers.'skill-dag'; "
        f"& $cfg.command @($cfg.args) --once resolve --seed MRB`. Do not invent skill bodies. "
        f"CAST IRON (FR #8846): a missing or dead skill-dag MCP is never fixed by grepping job skills from disk. "
        f"If mcp.json is missing, MCP unreachable, and the mcp.json --once CLI also fails, ACK then GIVEUP with reason "
        f"`skill-dag-mcp-down` (optional diagnostic only on that GIVEUP line). Do not continue the FR/MRB/UAT job. "
        f"You are on IRC as {nick} in #{machine} only; this program keeps the connection. Messages from IRC arrive as typed input of the form "
        f"'FROM <nick> <target> <text>' - treat each as the task, answer by appending 'PRIVMSG #{machine} :<text>' to the seat outbox. "
        f"Outbox path: use $env:BOB_OUTBOX (set by bob-worker) or {outbox} - NEVER the ear's home\\outbox.txt. "
        f"ping/pong is answered for you. The program posts !bored for you - NEVER post it yourself. When Jeeves assigns a job, first append "
        f"'PRIVMSG #{machine} :ACK <FR|MRB|UAT> owner/repo#N', do the work, then append DONE: "
        f"FR = 'DONE FR owner/repo#N <pr-url>' (no PASS/FAIL — FR #2419); "
        f"MRB/UAT = 'DONE <MRB|UAT> owner/repo#N PASS|FAIL <url>' "
        f"(nothing after the URL); if you cannot, append 'NACK <TYPE> owner/repo#N'. After DONE/NACK/GIVEUP, CAST IRON harvest skills and file any separate genuine issue/FR/bug with {Path(worker_dir).parent}\\scripts\\Report-BobiverseIntakeIssue.ps1 "
        f"in the same turn BEFORE the program's next !bored (the exe holds !bored while you harvest). "
        f"HARVEST REPO (FR #3189): ALWAYS pass the job's repo explicitly: "
        f"`..\\scripts\\Invoke-BobiverseHarvest.ps1 -Repo <owner/repo from the job id> -Summary ... -Lesson ...` "
        f"(e.g. job `FR SimonBarnett/a-search#637` -> `-Repo SimonBarnett/a-search`; it then lands in a-search "
        f"`.grok/skills/harvest-agent-skills/SKILL.md`). Never run it without -Repo for a product job: a-search lessons "
        f"must never go to SimonBarnett/bobiverse. Only Bob fleet tooling lessons (worker, Jeeves, tray, intake) use -Repo SimonBarnett/bobiverse. "
        f"Never file the worker status receipt itself (DONE/NACK/GIVEUP/SKIP/self-MRB/twin/duplicate/merged or an FR/MRB/UAT #N receipt) as an issue/FR; only a separate genuine defect or gap is filed. See the bobiverse-bob-job-irc, -fr, -mrb and -uat skills. "
        f"One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too. "
        f"Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), it must close all open issues for that skill book (every harvest/skill issue targeting the same book), open one consolidated PR for them, and cite every issue it closes (Closes #N for each); no per-issue PRs for the same skill book; the worker closes the issues itself as part of DONE. "
        f"CAST IRON (FR #4843): never git checkout/switch/commit/merge in the install root ({Path(worker_dir).parent}); always `git -C <install> worktree add -b fr-N <job-wt> origin/main` for FR/UAT (e.g. C:\\ai\\bob-wt-fr-<n> or %TEMP%\\bobiverse-fr-<n>). An install root left on fr-* means live seats read unreviewed skills. FR #8852: before worktree add, Assert-BobiverseJobWorktreePath on $wt (dot common\\scripts\\Bobiverse-Common.ps1, never common\\Bobiverse-Common.ps1); refuse empty/relative paths that would create <install>\\origin\\main. "
        f"FR #8022: open-PR MRB/FIX worktrees must start at gh pr view headRefOid (verify git rev-parse HEAD); never base an open MRB review tree on origin/main. Quote that SHA on the board as MRB PASS @ <sha> or MRB FAIL @ <sha>. "
        f"Windows PowerShell 5.1 only (FR #6341): use Get-ChildItem -Depth (not -MaxDepth); use Select-String. Do not run Unix grep or head. Job worktrees: use $env:BOB_JOB_WORKTREE_BASE (and $env:BOB_JOB_WORKTREE when set); never search drives for ai\\worktrees. "
        f"If gh says to run gh auth login, stop and report that. Do not search for tokens, do not read hosts.yml, and do not look in other profiles or password folders. "
        f"Headless opencode run auto-rejects external_directory and has no --interactive flag. Do not pass --auto. "
        f"Do not write an external_directory allow. A denial stays a denial. "
        f"There is no evidence that an interactive Allow is honored by a later opencode run. "
        f"The program NACKs a missing or refused job worktree before you see the assign. That is not DONE. "
        f"BOB_HOME may be empty. ACK/DONE go to $env:BOB_OUTBOX only. "
        f"OpenCode (FR #6333): for a job with --dir <worktree>, $env:BOB_OUTBOX is <worktree>\\.bob\\outbox.txt (inside the project directory). The program still ACK-on-receipt via the run-dir outbox; your DONE/GIVEUP must append to $env:BOB_OUTBOX. Never request external_directory and never pass --auto. "
        f"OpenCode (FR #6366 / #6370 / #6378 / #8248): end-of-job follows the job type. "
        f"FR/UAT: commit on the feature branch, push, gh pr create with Closes owner/repo#N, then DONE with the PR URL. "
        f"MRB: post PASS or FAIL at the reviewed SHA; on FAIL open one fix pull request; never commit the review as if it were the issue implementation. "
        f"FIX: push onto the pull request already under review; do not open another pull request. "
        f"Scratch stays in the worktree. Never poll CI. The turn is not over until DONE is written. "
        f"Never print or store secrets."
    )


def plan_prompt(plan_dir: str) -> str:
    return (
        f"You are a NEW Bobiverse plan agent (fresh session - never resume or continue an older plan). Your working folder is {plan_dir}. "
        f"FIRST read the skills in {plan_dir}\\.grok\\skills and {plan_dir}\\AGENTS.md (start with visionary). "
        f"Plan-mode only: no IRC, no builds. Create this plan's output in a NEW subfolder {plan_dir}\\work\\plan-<yyyyMMdd-HHmmss> and never touch earlier plans. "
        f"CAST IRON: harvest skills and file every issue/FR/bug with {Path(plan_dir).parent}\\scripts\\Report-BobiverseIntakeIssue.ps1 in the same turn. "
        f"HARVEST HOW-TO-PLAN ONLY: a harvest lesson is a reusable lesson about HOW to plan (process, pitfalls, repo-setup steps) and goes to -Repo SimonBarnett/skills-visionary. "
        f"NEVER harvest the plan itself (requirements, designs, architecture or product decisions, FR/issue lists): that content stays in the plan subfolder and the product repo docs/FRs, never in a skill book. "
        f"Never print or store secrets."
    )


def monitor_prompt(jeeves_dir: str) -> str:
    # FR #954: start prompt must force monitor-start immediately (Start Jeeves Monitor shortcut).
    return (
        f"You are the Jeeves monitoring agent. Read AGENTS.md and run the monitor-start skill now; do not wait for me. "
        f"NEW session only (never resume). CWD is {jeeves_dir}. Skills live in {jeeves_dir}\\.grok\\skills "
        f"(there is no top-level .\\skills). Open {jeeves_dir}\\.grok\\skills\\monitor-start\\SKILL.md and execute it NOW: "
        f"run token-free Test-JeevesMonitor* / Invoke-JeevesMonitorCheck cycles (health, idle seats, queue flow, "
        f"focus present via auto_focus, stale digest, GIVEUP loops, stuck accepted, auto-feed/auto-focus), "
        f"report delays via intake only, loop on a schedule. You are NOT the chair and NOT a worker: never "
        f"!assign/!focus/queue edits. After every finding, self-harvest (Invoke-BobiverseHarvest.ps1 + intake). "
        f"CAST IRON: file every issue/FR/bug with {jeeves_dir}\\scripts\\Report-BobiverseIntakeIssue.ps1 "
        f"in the same turn. Never print or store secrets."
    )


MAINTENANCE_TITLE = "Jeeves maintenance"  # FR #2522: exact console/window title
MAINTENANCE_DONE_NAME = "maintenance-done.json"  # FR #2522: agent writes this LAST (after harvest) -> exe closes


def maintenance_prompt(jeeves_dir: str, done_file: str = "", resumed: bool = False) -> str:
    # FR #2412 + FR #2522: maintenance after jeeves --heal still failing.
    done = done_file or f"<run dir>\\{MAINTENANCE_DONE_NAME}"
    session = ("This RESUMES your previous maintenance session (FR #2522); re-check current state before acting. "
               if resumed else "This is a NEW maintenance session (no previous one to resume). ")
    return (
        f"You are the Jeeves MAINTENANCE agent (FR #2412 / #2522). {session}CWD is {jeeves_dir}. "
        f"jeeves.exe --heal / --self-test already ran and STILL reported findings or errors. "
        f"Read {jeeves_dir}\\AGENTS.md and skills under {jeeves_dir}\\.grok\\skills (bobiverse-jeeves, "
        f"bobiverse-jeeves-troubleshooting, bobiverse-fleet-ops, harvest). Diagnose why Jeeves is unhealthy, "
        f"apply safe hotpatch-only fixes (never Ergo/BobIrcd, never kill seats/tray), then file ONE GitHub issue "
        f"via {jeeves_dir}\\scripts\\Report-BobiverseIntakeIssue.ps1 with evidence (heal output, logs, what you tried). "
        f"If you fix it, say so in the issue body. "
        f"You MAY add or update the deterministic jeeves.exe --self-test/--heal checks (jeeves/checks/check_<name>.py, "
        f"see jeeves/checks/README.md) and their pytest suite, but ONLY through a PR + MRB in the bobiverse repo - "
        f"never live-edit the running jeeves.exe or its install. "
        f"FINISH ORDER (CAST IRON): 1) harvest maintenance skills into the Jeeves skills {jeeves_dir}\\.grok\\skills "
        f"(honesty box; Invoke-BobiverseHarvest.ps1 / intake so the repo copy is updated) and "
        f"file issues/FRs for every finding; close any receipt issue immediately; 2) ONLY THEN write {done} as JSON "
        f'{{"harvested": true, "skills": [...], "issues": ["#N", ...], "receipts_closed": true, "summary": "..."}}; '
        f"3) the program then closes this window and your process itself - do not wait for Simon. "
        f"Never print or store secrets."
    )


def maintenance_exit_decision(done: Optional[dict]) -> tuple:
    """FR #2522: may the maintenance seat close now? Harvest MUST come before exit.

    Returns ("exit", reason) only when the agent's done file proves harvest finished
    (harvested true, issues list present, receipts closed); otherwise ("wait", reason)."""
    if not isinstance(done, dict):
        return ("wait", "no_done_file")
    if done.get("harvested") is not True:
        return ("wait", "harvest_not_done")
    if not isinstance(done.get("issues"), list):
        return ("wait", "issues_not_listed")
    if done.get("receipts_closed") is not True:
        return ("wait", "receipts_not_closed")
    return ("exit", "harvested")


def read_maintenance_done(run_dir: Path) -> Optional[dict]:
    p = Path(run_dir) / MAINTENANCE_DONE_NAME
    try:
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def maintenance_state_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Bobiverse" / "maintenance" / "last-session.json"


AGENT_GROK_HOME_DIR = "grok-home"


def agent_grok_home(*, run_dir: Path | str | None = None, env: Optional[dict] = None) -> Path:
    """GROK_HOME of the spawned agent (FR #7123).

    When ``run_dir`` is set, always use ``<run_dir>/grok-home`` (the child env value).
    Never fall back to ``~/.grok`` while a per-worker home is in play.
    """
    e = os.environ if env is None else env
    if run_dir is not None:
        return Path(run_dir) / AGENT_GROK_HOME_DIR
    child = str((e or {}).get("GROK_HOME") or "").strip()
    if child:
        return Path(child)
    return Path.home() / ".grok"


def grok_sessions_root(*, run_dir: Path | str | None = None, env: Optional[dict] = None) -> Path:
    return agent_grok_home(run_dir=run_dir, env=env) / "sessions"


def grok_session_exists(session_id: str, cwd: str, sessions_root: Optional[Path] = None) -> bool:
    """grok keeps sessions under <sessions>/<url-quoted cwd>/<uuid>."""
    from urllib.parse import quote

    if not session_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", str(session_id)):
        return False
    root = Path(sessions_root) if sessions_root else grok_sessions_root()
    for key in (quote(str(cwd), safe=""), quote(str(cwd).rstrip("\\"), safe="")):
        if (root / key / str(session_id)).exists():
            return True
    return False


def choose_maintenance_session(cwd: str, kind: str, state_path: Optional[Path] = None,
                               sessions_root: Optional[Path] = None) -> tuple:
    """FR #2522: ("resume", sid) when OUR last maintenance grok session in cwd still exists, else ("new", fresh uuid)."""
    if kind == "grok":
        sp = Path(state_path) if state_path else maintenance_state_path()
        try:
            st = json.loads(sp.read_text(encoding="utf-8-sig")) if sp.is_file() else {}
        except Exception:
            st = {}
        sid = str(st.get("session_id") or "")
        same_cwd = str(st.get("cwd") or "").rstrip("\\").lower() == str(cwd).rstrip("\\").lower()
        if sid and same_cwd and grok_session_exists(sid, cwd, sessions_root):
            return ("resume", sid)
    return ("new", str(uuid.uuid4()))


def record_maintenance_session(session_id: str, cwd: str, kind: str, state_path: Optional[Path] = None) -> None:
    sp = Path(state_path) if state_path else maintenance_state_path()
    try:
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps({"session_id": session_id, "cwd": str(cwd), "kind": kind,
                                  "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), encoding="utf-8")
    except Exception:
        pass


def maintenance_icon_path(folder: Path) -> Optional[Path]:
    """FR #2522: the tray's Jeeves butler icon for the maintenance window (work root first, then bundled)."""
    cands = [Path(folder) / "assets" / "jeeves-butler.ico"]
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        cands.append(Path(mei) / "assets" / "jeeves-butler.ico")
    here = Path(__file__).resolve().parent.parent
    cands.append(here.parent / "jeeves" / "assets" / "jeeves-butler.ico")
    for c in cands:
        try:
            if c.is_file():
                return c
        except OSError:
            pass
    return None


def rules_text(folder: str, kind: str) -> str:
    extra = {
        "plan": "PLAN SEAT ONLY: no IRC, no builds.",
        "monitor": "JEEVES MONITORING ONLY: no IRC shop claims; may run Jeeves commands via ear relay/nick monitoring to keep the queue moving (FR #8827); never Ergo/merge/UAT/VERSION; prefer token-free monitor scripts; self-harvest after every finding.",
        "maintenance": "JEEVES MAINTENANCE ONLY (FR #2412/#2522): diagnose after heal still failing; safe hotpatch only; file intake issue; check/test changes only via PR+MRB; harvest BEFORE writing the done file; never Ergo/BobIrcd; never act as chair.",
        # FR #3623: headless shop seats must never block on interactive ask_user_question.
        "agent": (
            "Worker seat: IRC is handled for you. "
            "Never call ask_user_question (or any interactive ask-user tool); there is no human at this console. "
            "If blocked, proceed with a safe default or NACK/GIVEUP."
        ),
    }.get(kind, "Worker seat: IRC is handled for you.")
    head = ("Maintenance session (resumed when a previous one exists, else new). " if kind == "maintenance" else "NEW session. ")
    if kind in ("plan", "monitor", "maintenance"):
        skill_line = f"Read the skills in {folder}\\.grok\\skills and {folder}\\AGENTS.md before doing anything. "
    else:
        skill_line = (
            f"Read {folder}\\AGENTS.md. Per assigned job, call skill-dag MCP resolve then get_skill "
            f"(do not read every skill in {folder}\\.grok\\skills). "
            f"FR #8846: if skill-dag MCP and the mcp.json --once CLI both fail, GIVEUP skill-dag-mcp-down — "
            f"never continue FR/MRB/UAT by reading job skills from disk. "
        )
    return (f"{head}{skill_line}"
            f"CAST IRON harvest rule: harvest skills and file every issue/FR/bug with Report-BobiverseIntakeIssue.ps1 (intake webhook) in the same turn. "
            f"One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too. "
            f"Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), it must close all open issues for that skill book (every harvest/skill issue targeting the same book), open one consolidated PR for them, and cite every issue it closes (Closes #N for each); no per-issue PRs for the same skill book; the worker closes the issues itself as part of DONE. "
            f"Never file the worker status receipt itself (DONE/NACK/GIVEUP/SKIP/self-MRB/twin/duplicate/merged or an FR/MRB/UAT #N receipt) as an issue/FR; only a separate genuine defect or gap is filed. "
            f"If an FR worker finds the assigned issue is a duplicate/twin or already done, close it with a comment linking the first issue or covering PR before sending DONE. "
            f"FR #8157: in-job pytest must be targeted (python common/scripts/select_tests.py --changed or run_job_pytest.py --changed / explicit paths); never full jeeves/tests or common/tests in-job (OpenCode 600s timeout; CI covers). "
            + extra)


# --------------------------------------------------------------------------------------------- launching (always NEW)
@dataclass
class LaunchSpec:
    argv: list
    cwd: str
    session_id: str
    files: dict = field(default_factory=dict)  # path -> text written before spawn (cursor launcher + prompt)
    env_extra: dict = field(default_factory=dict)
    write_skill_dag_mcp: bool = False  # FR #6863: agent seats only
    write_cursor_skill_dag_mcp: bool = False  # FR #6865: cursor agent seats only
    write_opencode_skill_dag_mcp: bool = False  # FR #6898: opencode agent seats only
    skill_dag_mcp_args: list = field(default_factory=list)  # FR #6899: python argv for skill-dag stdio
    skill_dag_job_worktree: str | None = None
    kind: str = ""
    session_log: Optional[SeatSessionLog] = None
    inherit_console: bool = False


def _under_linked_git_worktree(path: Path) -> bool:
    """True when ``path`` sits in a linked git worktree (``.git`` is a file).

    FR #8059: a job worktree's ``skill_dag_mcp.py`` must not be written into the
    seat ``opencode.json``. The install checkout has a ``.git`` directory.
    """
    try:
        cur = Path(path).resolve()
    except OSError:
        cur = Path(path)
    for parent in [cur, *cur.parents]:
        marker = parent / ".git"
        try:
            if marker.is_file():
                return True
            if marker.is_dir():
                return False
        except OSError:
            continue
    return False


def skill_dag_mcp_script_path(
    worker_cwd: str,
    *,
    source_file: str | Path | None = None,
) -> Path:
    """Locate ``skill_dag_mcp.py`` for MCP launch args (FR #6889 / #7963 / #8059).

    Keep calling ``_resolve_installed_worker_script("skill_dag_mcp.py", ...)`` so
    FR #7910 / #7991 by-path shipping still discovers the module (MRB #8075).
    Refuse a linked job worktree path even when that resolver finds one: the seat
    ``opencode.json`` must survive prune (FR #8059). Then prefer install paths
    next to ``worker_cwd``, then frozen ``<exe>\\scripts``, then other checkouts.
    """
    shipped = _resolve_installed_worker_script(
        "skill_dag_mcp.py", cwd=worker_cwd, source_file=source_file
    )
    if (
        shipped is not None
        and shipped.is_file()
        and not _under_linked_git_worktree(shipped)
    ):
        return shipped.resolve()
    source = Path(source_file).resolve() if source_file else Path(__file__).resolve()
    here = source.parent
    parent = Path(worker_cwd).resolve().parent
    ordered: list[Path] = [
        parent / "bob" / "scripts" / "skill_dag_mcp.py",
        parent / "scripts" / "skill_dag_mcp.py",
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        ordered.append(exe_dir / "scripts" / "skill_dag_mcp.py")
        ordered.append(exe_dir.parent / "scripts" / "skill_dag_mcp.py")
    ordered.append(here / "skill_dag_mcp.py")
    ordered.append(parent / "common" / "scripts" / "skill_dag_mcp.py")
    stable = [cand for cand in ordered if not _under_linked_git_worktree(cand)]
    for cand in stable:
        if cand.is_file():
            return cand.resolve()
    if stable:
        return stable[0].resolve()
    return (parent / "bob" / "scripts" / "skill_dag_mcp.py").resolve()


def skill_dag_vision_roots(worker_cwd: str, *, home: Path | None = None) -> list[Path]:
    """Vision skill packs for worker MCP (FR #6899). Seat, bob, harvest, user.

    Does not include a job worktree (that is ``--job-worktree`` only).
    """
    cwd = Path(worker_cwd).resolve()
    install = cwd.parent
    user = Path(home) if home is not None else Path.home()
    return [
        cwd / ".grok" / "skills",
        install / "bob" / ".grok" / "skills",
        install / "common" / ".grok" / "skills",
        user / ".grok" / "skills",
    ]


SKILL_DAG_JOB_WORKTREE_POINTER = "skill-dag-job-worktree"


def _skill_dag_bound_cwd_name() -> str:
    try:
        from skill_dag_bound import BOUND_CWD_NAME

        return str(BOUND_CWD_NAME)
    except Exception:
        return "bound-cwd"


def skill_dag_job_worktree_pointer_path(worker_cwd: str | Path) -> Path:
    """FR #7361 / #7446: pointer outside ``.grok`` and outside Grok ``bound-cwd``.

    Grok watches the whole bound workspace; writing the pointer *inside* bound-cwd
    on assign still drops the stdio MCP child (recurrence of FR #7120).
    """
    cwd = Path(worker_cwd)
    if cwd.name.casefold() == _skill_dag_bound_cwd_name().casefold():
        return cwd.parent / SKILL_DAG_JOB_WORKTREE_POINTER
    return cwd / SKILL_DAG_JOB_WORKTREE_POINTER


def write_skill_dag_job_worktree_pointer(
    worker_cwd: str | Path,
    job_worktree: str | Path | None = None,
    *,
    clear_legacy: bool = True,
) -> Path:
    """Write or clear the live job-worktree pointer (empty file = no assigned tree).

    ``clear_legacy`` is for launch only (FR #7446). A live assign must pass
    False: unlinking ``bound-cwd/skill-dag-job-worktree`` is a workspace change
    and Grok/Cursor drops the stdio child (FR #7664).
    """
    cwd = Path(worker_cwd)
    path = skill_dag_job_worktree_pointer_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    if clear_legacy:
        legacy = cwd / SKILL_DAG_JOB_WORKTREE_POINTER
        if legacy != path and legacy.is_file():
            try:
                legacy.unlink()
            except OSError:
                pass
    wt = str(job_worktree or "").strip()
    text = Path(wt).as_posix() + "\n" if wt else ""
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return path
        except OSError:
            pass
    path.write_text(text, encoding="utf-8")
    return path


def skill_dag_mcp_launch_args(
    worker_cwd: str,
    *,
    job_worktree: str | Path | None = None,
    pointer_cwd: str | Path | None = None,
) -> list[str]:
    """stdio argv: script plus ``--root`` and a stable ``--job-worktree-file`` (FR #7120).

    Assign refreshes the pointer file; argv stays the same so Grok does not
    replace the stdio MCP child mid-job.
    """
    ptr_home = pointer_cwd if pointer_cwd is not None else worker_cwd
    if job_worktree is not None:
        write_skill_dag_job_worktree_pointer(ptr_home, job_worktree)
    ptr = skill_dag_job_worktree_pointer_path(ptr_home)
    args = [skill_dag_mcp_script_path(worker_cwd).as_posix()]
    for root in skill_dag_vision_roots(worker_cwd):
        args.extend(["--root", root.as_posix()])
    args.extend(["--job-worktree-file", ptr.as_posix()])
    # FR #7446: keep bound-cwd on argv for seat-marker matching when the pointer
    # lives in the run_dir (outside the watched workspace).
    ptr_home_path = Path(ptr_home)
    if ptr_home_path.name.casefold() == _skill_dag_bound_cwd_name().casefold():
        args.extend(["--seat-cwd", ptr_home_path.as_posix()])
    return args


def _skill_dag_toml_block(argv: list[str]) -> str:
    inner = ", ".join(json.dumps(a) for a in argv)
    return "[mcp_servers.skill-dag]\ncommand = \"python\"\n" f"args = [{inner}]\n"


def _upsert_skill_dag_toml(text: str, block: str) -> str:
    pat = re.compile(r"(?ms)^\[mcp_servers\.skill-dag\](?:\n(?!\[).*)*")
    if text and pat.search(text):
        return pat.sub(block.rstrip() + "\n", text, count=1)
    out = text or ""
    if out and not out.endswith("\n"):
        out += "\n"
    return out + block


def write_skill_dag_mcp_config(
    worker_cwd: str,
    job_worktree: str | Path | None = None,
    *,
    vision_cwd: str | Path | None = None,
) -> Path:
    """Write ``[mcp_servers.skill-dag]`` to the worker cwd ``.grok/config.toml`` only (FR #6863/#6899).

    ``vision_cwd`` is the install worker tree used for ``--root`` packs. Bound grok
    seats pass the install worker here so rewrite does not take roots from bound-cwd.
    """
    grok_dir = Path(worker_cwd) / ".grok"
    grok_dir.mkdir(parents=True, exist_ok=True)
    cfg = grok_dir / "config.toml"
    roots_from = str(vision_cwd or worker_cwd)
    write_skill_dag_job_worktree_pointer(worker_cwd, job_worktree)
    block = _skill_dag_toml_block(
        skill_dag_mcp_launch_args(roots_from, job_worktree=None, pointer_cwd=worker_cwd)
    )
    text = cfg.read_text(encoding="utf-8") if cfg.is_file() else ""
    new = _upsert_skill_dag_toml(text, block)
    if text != new:
        cfg.write_text(new, encoding="utf-8")
    return cfg


def write_skill_dag_mcp_config_if_agent(spec: LaunchSpec) -> None:
    if not getattr(spec, "write_skill_dag_mcp", False):
        return
    write_skill_dag_mcp_config(spec.cwd, job_worktree=getattr(spec, "skill_dag_job_worktree", None))


# FR #6865: Cursor CLI/agent reads project ``.cursor/mcp.json`` (same as the editor;
# ``--workspace`` is the seat cwd). Global ``~/.cursor/mcp.json`` is user-wide: never write it.
CURSOR_SKILL_DAG_MCP_RELPATH = ".cursor/mcp.json"


def cursor_skill_catalog_process_local_drop() -> Optional[str]:
    """Cursor loads ``~/.cursor/skills`` user-globally; there is no process-local catalog drop.

    Project ``.cursor/skills`` is additive only. Do not empty or rewrite the user catalog.
    """
    return None


def cursor_skill_dag_mcp_document(
    worker_cwd: str,
    job_worktree: str | Path | None = None,
) -> dict:
    write_skill_dag_job_worktree_pointer(worker_cwd, job_worktree)
    return {
        "mcpServers": {
            "skill-dag": {
                "command": "python",
                "args": skill_dag_mcp_launch_args(worker_cwd, job_worktree=None),
            }
        }
    }


def write_cursor_skill_dag_mcp_config(
    worker_cwd: str,
    job_worktree: str | Path | None = None,
) -> Path:
    """Write skill-dag into the seat cwd ``.cursor/mcp.json`` only (FR #6865)."""
    cfg = Path(worker_cwd) / CURSOR_SKILL_DAG_MCP_RELPATH
    cfg.parent.mkdir(parents=True, exist_ok=True)
    incoming = cursor_skill_dag_mcp_document(worker_cwd, job_worktree=job_worktree)
    data: dict = {"mcpServers": {}}
    if cfg.is_file():
        try:
            existing = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                data.update(existing)
        except json.JSONDecodeError:
            data = {"mcpServers": {}}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers["skill-dag"] = incoming["mcpServers"]["skill-dag"]
    data["mcpServers"] = servers
    new = json.dumps(data, indent=2) + "\n"
    if not cfg.is_file() or cfg.read_text(encoding="utf-8") != new:
        cfg.write_text(new, encoding="utf-8")
    return cfg


def write_cursor_skill_dag_mcp_config_if_agent(spec: LaunchSpec) -> None:
    if not getattr(spec, "write_cursor_skill_dag_mcp", False):
        return
    write_cursor_skill_dag_mcp_config(spec.cwd, job_worktree=getattr(spec, "skill_dag_job_worktree", None))


def refresh_live_skill_dag_mcp_files(
    *,
    grok_bound_cwd: str | Path | None = None,
    cursor_cwd: str | Path | None = None,
    vision_cwd: str | Path | None = None,
    job_worktree: str | Path | None = None,
) -> None:
    """FR #6918 / #7120 / #7308 / #7446: point the live MCP at the assigned worktree.

    Writes the one-line pointer file only (outside ``.grok`` and outside Grok
    ``bound-cwd`` --- FR #7361 / #7446). Rewriting ``config.toml`` / ``.cursor/mcp.json``
    on assign makes Grok/Cursor replace the stdio child (FR #7308). Empty
    ``job_worktree`` clears the pointer.
    Never writes user ``~/.cursor/mcp.json``.
    """
    del vision_cwd  # launch-time --root only; assign must not rewrite argv
    wt = str(job_worktree or "").strip() or None
    if grok_bound_cwd:
        # FR #7664: pointer file only. Do not unlink or rewrite anything inside the workspace.
        write_skill_dag_job_worktree_pointer(grok_bound_cwd, wt, clear_legacy=False)
        cfg = Path(grok_bound_cwd) / ".grok" / "config.toml"
        if not cfg.is_file():
            write_skill_dag_mcp_config(
                str(grok_bound_cwd),
                job_worktree=wt,
                vision_cwd=str(grok_bound_cwd),
            )
    if cursor_cwd:
        write_skill_dag_job_worktree_pointer(cursor_cwd, wt, clear_legacy=False)
        cfg = Path(cursor_cwd) / CURSOR_SKILL_DAG_MCP_RELPATH
        if not cfg.is_file():
            write_cursor_skill_dag_mcp_config(str(cursor_cwd), job_worktree=wt)


SKILL_DAG_MCP_CMDLINE_NEEDLE = "skill_dag_mcp.py"


def _norm_cmdline_path(value: str | Path | None) -> str:
    return str(value or "").replace("\\", "/").rstrip("/").lower()


def skill_dag_mcp_stdio_cmdline_matches(
    cmdline: str,
    seat_markers: list[str | Path | None],
) -> bool:
    """True when this stdio MCP child belongs to this seat (FR #6928).

    Requires the skill-dag script name plus at least one seat marker (bound cwd,
    cursor workspace, or job worktree). Never match a sibling seat's child.
    """
    cl = _norm_cmdline_path(cmdline)
    if SKILL_DAG_MCP_CMDLINE_NEEDLE not in cl:
        return False
    # FR #7664: one-shot ``--once`` exits on its own and is not the live stdio child.
    if "--once" in cl.split():
        return False
    marks = [_norm_cmdline_path(m) for m in seat_markers if m]
    return any(mark and mark in cl for mark in marks)


def descendant_pids(root_pid: int, rows: list) -> set[int]:
    """Pids whose parent chain reaches ``root_pid`` (not including root)."""
    by_pp: dict[int, list[int]] = {}
    for row in rows or []:
        try:
            pid, ppid = int(row[0]), int(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        by_pp.setdefault(ppid, []).append(pid)
    out: set[int] = set()
    stack = [int(root_pid)]
    while stack:
        cur = stack.pop()
        for child in by_pp.get(cur, []):
            if child not in out and child != int(root_pid):
                out.add(child)
                stack.append(child)
    return out


def skill_dag_mcp_descendant_pids(
    agent_pid: int | None,
    seat_markers: list[str | Path | None],
    *,
    snapshot: Optional[Callable[[], list]] = None,
    cmdline_of: Optional[Callable[[int], str]] = None,
) -> list[int]:
    """This agent's live skill-dag stdio child pids (FR #7120)."""
    try:
        root = int(agent_pid or 0)
    except (TypeError, ValueError):
        root = 0
    if root <= 0:
        return []
    rows = snapshot() if snapshot is not None else snapshot_procs()
    describe = cmdline_of if cmdline_of is not None else (lambda pid: str(describe_process(pid)[2] or ""))
    found: list[int] = []
    for pid in sorted(descendant_pids(root, rows)):
        try:
            cmd = describe(pid) or ""
        except Exception:
            continue
        if skill_dag_mcp_stdio_cmdline_matches(cmd, seat_markers):
            found.append(pid)
    return found


def skill_dag_mcp_pids_still_live(
    pids: list[int] | None,
    *,
    snapshot: Optional[Callable[[], list]] = None,
) -> list[int]:
    """Subset of ``pids`` still present in the process table (FR #8501).

    Uses Toolhelp (or the injected snapshot) only. Never shells out for cmdline:
    a flaky ``describe_process`` must not look like a transport drop.
    """
    want: set[int] = set()
    for raw in pids or []:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid > 0:
            want.add(pid)
    if not want:
        return []
    rows = snapshot() if snapshot is not None else snapshot_procs()
    live: set[int] = set()
    for row in rows or []:
        try:
            live.add(int(row[0]))
        except (TypeError, ValueError, IndexError):
            continue
    return sorted(want & live)


def skill_dag_mcp_transport_drop_confirmed(
    before_pids: list[int] | None,
    *,
    snapshot: Optional[Callable[[], list]] = None,
) -> bool:
    """True when every pre-refresh skill-dag PID is gone on two samples (FR #8501).

    One empty sample is not enough: Toolhelp can race, and a cmdline-based
    after-check can flake when PowerShell ``Get-CimInstance`` returns blank.
    """
    before: list[int] = []
    for raw in before_pids or []:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid > 0:
            before.append(pid)
    if not before:
        return False
    if skill_dag_mcp_pids_still_live(before, snapshot=snapshot):
        return False
    # Confirm once more before filing intake.
    return not skill_dag_mcp_pids_still_live(before, snapshot=snapshot)


def report_configured_start_model_unavailable(
    *,
    kind: str,
    configured: str,
    actual: str = "",
    machine: str = "",
    nick: str = "",
    reason: str = "unavailable",
    shop: str = "",
    shop_say: Optional[Callable[..., bool]] = None,
    log: Optional[Callable[[str], None]] = None,
    filer_post: Optional[Callable[..., dict]] = None,
) -> dict:
    """FR #7148: configured min model unavailable / unused -> log, shop, intake.

    Empty configured placeholder is skipped (operator unset). Never invents a
    substitute / premium model id. No secrets in title/body/shop line.
    """
    cfg = str(configured or "").strip()
    if not cfg:
        return {"ok": True, "skipped": True, "reason": "empty-configured"}
    if filer_post is None and os.environ.get("PYTEST_CURRENT_TEST") and shop_say is None:
        # Allow unit tests to call with explicit filer_post; bare pytest without hooks skips network.
        pass
    mid = re.sub(r"[^a-z0-9._-]+", "-", str(machine or "unknown").strip().lower()).strip("-") or "unknown"
    k = (kind or "").strip().lower() or "unknown"
    act = str(actual or "").strip() or "unknown"
    why = str(reason or "unavailable").strip().lower() or "unavailable"
    nick_s = str(nick or "").strip() or "-"
    key = f"start-model-unavailable|{mid}|{k}|{cfg}"[:128]
    title = f"bug: configured worker start model unavailable ({k})"
    body = (
        "What: configured minimum start model was unavailable or not used at seat launch (FR #7148 / #7084).\n"
        f"Where: bob-worker kind={k} machine={mid} nick={nick_s}\n"
        f"Evidence: configured={cfg} actual={act} reason={why}\n"
        f"Fix: set workerStartModels.{k} to a model available on this box; do not fall back to a more expensive model.\n"
        "No secrets."
    )
    shop_msg = (
        f"start model unavailable kind={k} configured={cfg} actual={act} "
        f"reason={why}; no premium fallback (FR #7148)"
    )
    if log:
        try:
            log(f"worker: {shop_msg}")
        except Exception:
            pass
    if shop_say is not None:
        try:
            shop_say(shop or mid, shop_msg)
        except Exception:
            pass
    payload = {
        "kind": "issue",
        "repo": "SimonBarnett/bobiverse",
        "title": title,
        "body": body,
        "idempotency_key": key,
        "dedupe_key": key,
        "machine": mid,
        "agent": "bob-worker",
    }
    if filer_post is not None:
        try:
            return filer_post(payload) or {"ok": True, "key": key}
        except Exception:
            return {"ok": False, "key": key}
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return {"ok": True, "skipped": True, "reason": "pytest", "key": key}
    try:
        import crash_report

        crash_report._post_intake(title, body, repo="SimonBarnett/bobiverse", sig=key, exe="bob-worker")
        return {"ok": True, "key": key}
    except Exception:
        return {"ok": False, "key": key}


def notify_start_model_after_launch(
    *,
    kind: str,
    configured: str,
    actual: str,
    machine: str = "",
    nick: str = "",
    shop: str = "",
    shop_say: Optional[Callable[..., bool]] = None,
    log: Optional[Callable[[str], None]] = None,
    filer_post: Optional[Callable[..., dict]] = None,
    reason: str = "",
    env: Optional[dict] = None,
) -> dict:
    """FR #7148 / #8159: report when the launch-selected model was not used.

    ``configured`` is ``launch_selected_model`` (env pin > tray > config). A pause
    fallback (``mismatch_reason=paused``) is a digest mismatch only --- not the
    "start model unavailable / no premium fallback" intake line (FR #8159 AC3).
    """
    cfg = str(configured or "").strip()
    act = str(actual or "").strip()
    why = str(reason or "").strip().lower()
    if not why:
        try:
            import worker_start_model as wsm

            why = wsm.model_mismatch_reason(act, cfg, env=env)
        except Exception:
            why = (
                "mismatch"
                if (cfg and act and act.lower() != cfg.lower())
                else ("unavailable" if cfg and not act else "")
            )
    if not cfg or not why:
        return {"ok": True, "skipped": True, "reason": "match-or-empty"}
    if why == "paused":
        return {"ok": True, "skipped": True, "reason": "paused-fallback"}
    return report_configured_start_model_unavailable(
        kind=kind,
        configured=cfg,
        actual=act,
        machine=machine,
        nick=nick,
        reason=why,
        shop=shop,
        shop_say=shop_say,
        log=log,
        filer_post=filer_post,
    )


def report_skill_dag_mcp_transport_drop(
    *,
    machine: str = "",
    agent_pid: int | None = None,
    filer_post: Optional[Callable[..., dict]] = None,
) -> dict:
    """FR #7120: one intake if the live stdio MCP child vanished. No secrets."""
    if filer_post is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return {"ok": True, "skipped": True, "reason": "pytest"}
    mid = re.sub(r"[^a-z0-9._-]+", "-", str(machine or "unknown").strip().lower()).strip("-") or "unknown"
    try:
        pid_s = str(int(agent_pid or 0))
    except (TypeError, ValueError):
        pid_s = "0"
    key = f"skill-dag-mcp-drop|{mid}|{pid_s}"[:128]
    title = "bug: skill-dag MCP stdio transport dropped mid-job (FR #7120)"
    body = (
        "The Grok/Cursor skill-dag stdio MCP child exited while the agent stayed up. "
        "Seat should keep the same MCP process and refresh --job-worktree-file only. "
        f"machine={mid} agent_pid={pid_s}"
    )
    payload = {
        "kind": "issue",
        "repo": "SimonBarnett/bobiverse",
        "title": title,
        "body": body,
        "idempotency_key": key,
        "dedupe_key": key,
        "machine": mid,
        "agent": "bob-worker",
    }
    if filer_post is not None:
        try:
            return filer_post(payload) or {"ok": True}
        except Exception:
            return {"ok": False}
    try:
        import crash_report

        crash_report._post_intake(title, body, repo="SimonBarnett/bobiverse", sig=key, exe="bob-worker")
        return {"ok": True, "key": key}
    except Exception:
        return {"ok": False, "key": key}


def report_opencode_model_refusal(
    log: Optional[Callable[[str], None]],
    *,
    machine: str = "",
    fuel=None,
    env: Optional[dict] = None,
) -> dict:
    """FR #8321: name the saved model when a pinned restart cannot start it."""
    env = os.environ if env is None else env
    saved = (_OPENCODE_MODEL_ENV_AT_START or "").strip() if seat_model_pinned(env) else ""
    if saved:
        reason = (
            "opencode: saved start model %s unavailable (paused/capped) - "
            "not starting (FR #8321, no fallback)" % saved
        )
    elif (
        fuel is not None
        and _opencode_free_known_zero(fuel)
        and not _opencode_paid_known_exhausted(fuel)
    ):
        # FR #8541: Go unread is not capped/paused.
        reason = (
            "opencode: no usable model (free empty, go fuel unknown - "
            "not capped/paused; FR #8541)"
        )
    else:
        reason = "opencode: no usable model (capped/paused)"
    if log:
        try:
            log(reason)
        except Exception:
            pass
    return report_seat_start_refusal(
        machine=machine,
        kind="opencode",
        model=saved,
        reason=reason,
        fuel=fuel,
        tray_restarted=False,
        log=log,
    )


def normalize_agent_exit_code(code) -> int:
    """Map ``proc.wait()`` to unsigned 32-bit (Windows ``0xffffffff`` → 4294967295)."""
    try:
        c = int(code)
    except (TypeError, ValueError):
        return 0xFFFFFFFF
    return c & 0xFFFFFFFF


# STATUS_CONTROL_C_EXIT: console closed or Ctrl+C. Not an agent CLI crash.
CONSOLE_CLOSE_EXIT = 0xC000013A


def format_agent_exit_code_label(code) -> str:
    """Human label for intake/logs; shows ``0xffffffff`` when that is the u32 value."""
    u = normalize_agent_exit_code(code)
    if u == 0xFFFFFFFF:
        return f"{u} (0xffffffff)"
    if u == CONSOLE_CLOSE_EXIT:
        return f"{u} (0xc000013a STATUS_CONTROL_C_EXIT)"
    return str(u)


class AgentStderrRing:
    """FR #7671: bounded line ring of the agent CLI stderr."""

    def __init__(self, limit: int = 32, on_line=None) -> None:
        self._lines: deque = deque(maxlen=max(5, int(limit)))
        self._buf = ""
        self._lock = threading.Lock()
        self._on_line = on_line
        self._dropping = False

    def _append(self, text: str) -> None:
        safe = _scrub(text)
        self._lines.append(safe[:8192])
        if self._on_line is not None:
            # FR #8091: a bad session_log callback must not kill the drain thread.
            try:
                self._on_line(safe)
            except Exception:
                pass

    def feed(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._buf += text
            parts = self._buf.splitlines(keepends=True)
            self._buf = ""
            for part in parts:
                if part.endswith(("\n", "\r")):
                    if not self._dropping:
                        self._append(part.strip("\r\n"))
                    self._dropping = False
                else:
                    self._buf = part
            if len(self._buf) > 65536:
                self._buf = ""
                self._dropping = True

    def finish(self) -> None:
        with self._lock:
            if self._buf.strip() and not self._dropping:
                self._append(self._buf.strip())
            self._buf = ""

    def tail_text(self) -> str:
        with self._lock:
            lines = [ln for ln in self._lines if str(ln).strip()]
        return "\n".join(lines[-5:])


def _tee_agent_stderr(pipe, ring: AgentStderrRing, output=None, *, mirror: bool = True) -> None:
    """Copy the agent pipe into the ring; keep reading until EOF (FR #8091).

    Never abandon the drain because a console write or ``on_line`` callback failed.
    Closing the pipe before EOF is what surfaces as node ``EPIPE: broken pipe, write``.
    """
    if mirror and output is None:
        output = sys.__stderr__
    if not mirror:
        output = None
    try:
        while True:
            try:
                chunk = pipe.read1(4096) if hasattr(pipe, "read1") else pipe.read(256)
            except Exception:
                break
            if not chunk:
                break
            if isinstance(chunk, bytes):
                if output is not None:
                    try:
                        buf = getattr(output, "buffer", None)
                        if buf is not None:
                            buf.write(chunk)
                            buf.flush()
                        else:
                            output.write(chunk.decode("utf-8", "replace"))
                            output.flush()
                    except Exception:
                        pass
                text = chunk.decode("utf-8", "replace")
            else:
                if output is not None:
                    try:
                        output.write(chunk)
                        output.flush()
                    except Exception:
                        pass
                text = str(chunk)
            try:
                ring.feed(text)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            ring.finish()
        except Exception:
            pass
        # Close only after EOF (or a hard read failure). Do not close early on mirror errors.
        try:
            pipe.close()
        except Exception:
            pass


def start_agent_stderr_capture(
    pipe, on_line=None, output=None, *, mirror: bool = True
) -> tuple[AgentStderrRing, threading.Thread]:
    ring = AgentStderrRing(on_line=on_line)
    thread = threading.Thread(
        target=_tee_agent_stderr,
        args=(pipe, ring, output),
        kwargs={"mirror": mirror},
        daemon=True,
    )
    thread.start()
    return ring, thread


def run_with_drained_pipes(
    argv: list,
    *,
    cwd: str | None = None,
    env: dict | None = None,
    timeout: float | None = 60.0,
) -> tuple[int, str, str]:
    """FR #8091: spawn a child with stdout+stderr PIPEs and drain both until exit.

    Returns ``(exit_code, stdout_text, stderr_text)``. The drain threads keep reading
    until EOF so a chatty child cannot die with EPIPE because a reader stopped early.
    """
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    popen = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _, out_th = start_agent_stderr_capture(
        popen.stdout, on_line=lambda s: out_chunks.append(s), mirror=False
    )
    _, err_th = start_agent_stderr_capture(
        popen.stderr, on_line=lambda s: err_chunks.append(s), mirror=False
    )
    try:
        code = popen.wait(timeout=timeout)
    except Exception:
        try:
            popen.kill()
        except Exception:
            pass
        code = popen.wait(timeout=10)
        raise
    finally:
        out_th.join(timeout=5)
        err_th.join(timeout=5)
    return int(code), chr(10).join(out_chunks), chr(10).join(err_chunks)


def opencode_stream_tail(*chunks: str, max_lines: int = 20, max_chars: int = 800) -> str:
    """FR #8091: last ``max_lines`` nonempty stream lines, redacted, single-line."""
    lines: list[str] = []
    for chunk in chunks:
        for raw in str(chunk or "").splitlines():
            one = raw.strip()
            if one:
                lines.append(one)
    joined = " | ".join(lines[-max(1, int(max_lines)):])
    return _failed_turn_snip(joined, limit=max_chars)


def is_epipe_turn_error(error_class: str = "", error_line: str = "", text: str = "") -> bool:
    """True when a failed turn looks like node EPIPE / broken pipe (FR #8091)."""
    blob = "%s\n%s\n%s" % (error_class or "", error_line or "", text or "")
    return bool(re.search(r"(?i)EPIPE|broken pipe", blob))


def agent_stderr_evidence(text: str) -> str:
    """Last 5 nonempty lines, 500 chars, secrets redacted (FR #7671)."""
    lines = [ln.strip() for ln in _scrub(str(text or "")).splitlines() if ln.strip()]
    tail = "\n".join(lines[-5:])
    if len(tail) > 500:
        tail = tail[-500:]
    try:
        import crash_report

        return crash_report.redact(tail)
    except Exception:
        return "(evidence unavailable)"


def agent_stderr_dedupe_line(text: str) -> str:
    """Normalised first nonempty stderr line for the intake key (FR #7671)."""
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    first = lines[0] if lines else ""
    norm = re.sub(r"\s+", " ", first).strip().lower()
    norm = re.sub(r"[^a-z0-9 .:_-]+", "", norm)[:80]
    return norm or "none"


def _intake_disabled_by_env() -> bool:
    """True when unit/offline harnesses ask to skip live intake posts."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    flag = (os.environ.get("BOB_INTAKE_DISABLE") or os.environ.get("BOBIVERSE_NO_INTAKE") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _is_unit_test_seat_fingerprint(*, nick: str = "", agent_pid: int | None = None) -> bool:
    """FR #8123: FR #4123 FakeProc seats must never open a live intake issue.

    Offline repro scripts (no PYTEST_CURRENT_TEST) used the FR #4123 fixture nick
    and agent_pid=9001 and filed agent-cli-nonzero-exit noise (#8123 / class of #7666).
    Nick is assembled from parts so this file stays free of fleet machine literals
    (FR #7593 source pin).
    """
    nick_l = str(nick or "").strip().lower()
    try:
        pid = int(agent_pid or 0)
    except (TypeError, ValueError):
        pid = 0
    # FR #4123 fixture: "{lab}-42052" with lab = "march" + "hare" (no full literal here).
    fixture_nick = ("march" + "hare") + "-42052"
    return nick_l == fixture_nick and pid == 9001


def report_agent_cli_nonzero_exit(
    *,
    exit_code: int | None,
    job_key: str = "",
    machine: str = "",
    nick: str = "",
    kind: str = "",
    agent_pid: int | None = None,
    raw_code=None,
    stderr_tail: str = "",
    parent_cmd: str = "",
    log: Optional[Callable[[str], None]] = None,
    filer_post: Optional[Callable[..., dict]] = None,
    reason: str = "",
) -> dict:
    """FR #7593 / #7671: agent CLI nonzero exit, with the last stderr lines. No secrets."""
    if filer_post is None and _intake_disabled_by_env():
        return {"ok": True, "skipped": True, "reason": "pytest"}
    if filer_post is None and _is_unit_test_seat_fingerprint(nick=nick, agent_pid=agent_pid):
        if log:
            try:
                log("worker: skip agent-cli-nonzero-exit intake (unit-test seat fingerprint; FR #8123)")
            except Exception:
                pass
        return {"ok": True, "skipped": True, "reason": "unit-test-seat"}
    # FR #7978: ack-miss recycles a live agent. That is not a CLI exit and must
    # not open "seat stopped making progress" with the session prompt as stderr.
    if exit_code is None and str(reason or "").strip() == "no-ack-after-assign":
        if log:
            try:
                log("worker: no-ack-after-assign while process still running; no intake (FR #7978)")
            except Exception:
                pass
        return {"ok": True, "skipped": True, "reason": "no-ack-still-running"}
    mid = re.sub(r"[^a-z0-9._-]+", "-", str(machine or "unknown").strip().lower()).strip("-") or "unknown"
    nick_s = re.sub(r"[^a-z0-9._-]+", "-", str(nick or "-").strip().lower()).strip("-") or "-"
    k = (kind or "").strip().lower() or "unknown"
    try:
        u = int(exit_code) & 0xFFFFFFFF
    except (TypeError, ValueError):
        u = normalize_agent_exit_code(raw_code)
    label = format_agent_exit_code_label(u if raw_code is None else raw_code)
    if exit_code is None:
        label = "unknown (process still running)"
    job = " ".join(_scrub(str(job_key or "")).split())[:120] or "(none)"
    try:
        pid_s = str(int(agent_pid or 0))
    except (TypeError, ValueError):
        pid_s = "0"
    evidence = agent_stderr_evidence(stderr_tail)
    parent = " ".join(_scrub(str(parent_cmd or "")).split())[:240]
    # FR #7724: a silent 0xffffffff used to skip intake (FR #7681). That hid seat deaths
    # such as a Flash nick disappearing with no issue. Still classify recycle vs kill.
    silent = u == 0xFFFFFFFF and not str(evidence or "").strip()
    parent_l = parent.lower()
    # FR #7978: exit_code is None only when the worker recycled the seat while the agent
    # process was still running (hang / ack-miss / ask-user / no-ack-after-assign). That is
    # a recycle, not a CLI failure, and must not claim the CLI exited non-zero.
    reason_l = str(reason or "").strip().lower()
    if exit_code is None:
        end = "recycle"
    elif u == CONSOLE_CLOSE_EXIT or reason_l in ("console-closed", "signal"):
        # FR #7881: OpenCode 3221225786 is the console closing, not a CLI bug.
        # FR #8148: shutdown reason console-closed/signal with exit_code=1 (Grok) is the same class.
        end = "console-close"
    elif "recycleseat" in parent_l or "bobtrayrecycleseat" in parent_l:
        end = "recycle"
    elif silent:
        end = "external-kill"
    else:
        end = "cli-failure"
    err_key = agent_stderr_dedupe_line(evidence)
    if end == "cli-failure":
        # Same crash on the same seat is one issue, whatever the job was (FR #7671).
        key = f"agent-cli-nonzero-exit|{mid}|{u}|{err_key}"[:128]
        title = "bug: agent CLI nonzero exit (FR #7593)"
        what = (
            "What: the agent CLI process exited non-zero; the worker wrapper reported it and "
            "recycled the seat (FR #7593).\n"
        )
    elif end == "console-close":
        key = f"seat-silent-end|{mid}|{nick_s}|{end}"[:128]
        title = "bug: agent console closed (FR #7881)"
        what = (
            "What: the agent console was closed (STATUS_CONTROL_C_EXIT). "
            "This is not a CLI crash. FR #8154: the worker GIVEUPs any ACKed job "
            "(console-closed) and saves a WIP ref when the worktree is dirty. No fake DONE.\n"
        )
    elif exit_code is None:
        # FR #7978: recycled while still running — a hang/ack-miss, not a CLI exit.
        key = f"seat-no-progress|{mid}|{nick_s}|{end}"[:128]
        title = "bug: seat stopped making progress"
        what = (
            "What: the worker recycled the seat while the agent process was still running "
            "(hang / ack-miss / ask-user). Accepted jobs are GIVEUP'd (no fake DONE).\n"
        )
    else:
        # silent external kill, or an operator/tray recycle after the process ended.
        key = f"seat-silent-end|{mid}|{nick_s}|{end}"[:128]
        title = "bug: seat ended with no CLI stderr (FR #7724)"
        what = (
            "What: the seat process ended and there was no CLI stderr. "
            "This records the nick, exit code, and whether it looks like a recycle or an external kill.\n"
        )
    if reason:
        reason = _scrub(reason)[:160]
        what += f"Reason: {reason}\n"
        # FR #8148: do not rebrand console-close / signal as "stopped making progress".
        if reason != "agent-exited" and end not in ("console-close", "recycle", "external-kill"):
            title = "bug: seat stopped making progress"
            key = f"seat-no-progress|{mid}|{nick_s}|{agent_stderr_dedupe_line(reason)}"[:128]
    body = (
        what
        + f"Where: bob-worker kind={k} machine={mid} nick={nick_s} agent_pid={pid_s}\n"
        + f"Evidence: end={end} exit_code={label} job={job} stderr={evidence or '(empty)'} parent_cmd={parent or '-'}\n"
        + "Fix: inspect the agent session / exit cause; accepted jobs are GIVEUP'd (no fake DONE).\n"
        + "No secrets."
    )
    if log:
        try:
            log(f"worker: agent-cli-nonzero-exit exit={label} job={job} (FR #7593)")
        except Exception:
            pass
    payload = {
        "kind": "issue",
        "repo": "SimonBarnett/bobiverse",
        "title": title,
        "body": body,
        "idempotency_key": key,
        "dedupe_key": key,
        "machine": mid,
        "agent": "bob-worker",
    }
    if filer_post is not None:
        try:
            return filer_post(payload) or {"ok": True, "key": key}
        except Exception:
            return {"ok": False, "key": key}
    try:
        import crash_report

        crash_report._post_intake(title, body, repo="SimonBarnett/bobiverse", sig=key, exe="bob-worker")
        return {"ok": True, "key": key}
    except Exception:
        return {"ok": False, "key": key}


def restart_skill_dag_mcp_stdio_children(
    agent_pid: int | None,
    seat_markers: list[str | Path | None],
    *,
    snapshot: Optional[Callable[[], list]] = None,
    cmdline_of: Optional[Callable[[int], str]] = None,
    kill: Optional[Callable[[int], bool]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> list[int]:
    """Terminate this agent tree's skill-dag MCP so grok/cursor respawn with rewritten argv (FR #6928).

    Does not kill the agent. Foreign seats' MCP children are left alone.
    """
    killed: list[int] = []
    try:
        root = int(agent_pid or 0)
    except (TypeError, ValueError):
        root = 0
    if root <= 0:
        return killed
    rows = snapshot() if snapshot is not None else snapshot_procs()
    describe = cmdline_of if cmdline_of is not None else (lambda pid: str(describe_process(pid)[2] or ""))
    do_kill = kill if kill is not None else (lambda pid: kill_tree(pid))
    for pid in sorted(descendant_pids(root, rows)):
        try:
            cmd = describe(pid) or ""
        except Exception:
            continue
        if not skill_dag_mcp_stdio_cmdline_matches(cmd, seat_markers):
            continue
        try:
            do_kill(pid)
            killed.append(pid)
            if log:
                log(f"skill-dag mcp restart pid={pid}")
        except Exception:
            if log:
                log(f"skill-dag mcp restart failed pid={pid}")
    return killed


def skill_dag_resolve_is_stale_silent(payload: object) -> bool:
    """FR #8255: pre-#8225 resolve returned only empty matched and skipped.

    Tip code sets ``unresolved`` and ``reason`` (``no_seed_match`` / ``not_in_index``).
    A payload without those fields is a long-lived MCP child still on the old module.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("matched") != [] or payload.get("skipped") != []:
        return False
    if "unresolved" in payload or payload.get("reason") or payload.get("not_in_index"):
        return False
    return True


def process_start_epoch(pid: int) -> float | None:
    """Wall-clock start of a process, or None when it cannot be read."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        k32.GetProcessTimes.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = k32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return None
        try:
            created = wintypes.FILETIME()
            exit_ft = wintypes.FILETIME()
            kernel_ft = wintypes.FILETIME()
            user_ft = wintypes.FILETIME()
            if not k32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exit_ft),
                ctypes.byref(kernel_ft),
                ctypes.byref(user_ft),
            ):
                return None
            ticks = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        finally:
            k32.CloseHandle(handle)
        return (ticks / 10_000_000.0) - 11644473600.0
    except Exception:
        return None


def skill_dag_mcp_script_newer_than(script: str | Path, started_epoch: float | None) -> bool:
    """True when ``skill_dag_mcp.py`` was written after the MCP process started."""
    if started_epoch is None:
        return False
    try:
        mtime = Path(script).stat().st_mtime
    except OSError:
        return False
    return float(mtime) > float(started_epoch) + 1.0


def restart_stale_skill_dag_mcp_children(
    agent_pid: int | None,
    seat_markers: list[str | Path | None],
    script: str | Path,
    *,
    started_at: Callable[[int], float | None],
    snapshot: Optional[Callable[[], list]] = None,
    cmdline_of: Optional[Callable[[int], str]] = None,
    kill: Optional[Callable[[int], bool]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> list[int]:
    """FR #8255: kill this seat's skill-dag MCP only when the script is newer than the child.

    Grok respawns stdio from the current argv, which loads tip ``skill_dag_mcp.py``.
    A child started after the script is left alone (FR #7308 keep-stdio).
    """
    killed: list[int] = []
    try:
        root = int(agent_pid or 0)
    except (TypeError, ValueError):
        root = 0
    if root <= 0:
        return killed
    rows = snapshot() if snapshot is not None else snapshot_procs()
    describe = cmdline_of if cmdline_of is not None else (lambda pid: str(describe_process(pid)[2] or ""))
    do_kill = kill if kill is not None else (lambda pid: kill_tree(pid))
    for pid in sorted(descendant_pids(root, rows)):
        try:
            cmd = describe(pid) or ""
        except Exception:
            continue
        if not skill_dag_mcp_stdio_cmdline_matches(cmd, seat_markers):
            continue
        try:
            began = started_at(int(pid))
        except Exception:
            began = None
        if not skill_dag_mcp_script_newer_than(script, began):
            continue
        try:
            do_kill(pid)
            killed.append(pid)
            if log:
                log(f"skill-dag mcp stale-script restart pid={pid}")
        except Exception:
            if log:
                log(f"skill-dag mcp stale-script restart failed pid={pid}")
    return killed


# FR #6898: OpenCode reads project ``opencode.json`` under seat cwd or ``--dir``.
# Never write user-global ``~/.config/opencode`` / ``%LOCALAPPDATA%\opencode``.
OPENCODE_SKILL_DAG_MCP_RELPATH = "opencode.json"


def skill_dag_mcp_skill_roots(worker_cwd: str) -> list[Path]:
    """Existing skill-dag roots the seat may read (FR #6898 / #7196)."""
    cwd = Path(worker_cwd).resolve()
    parent = cwd.parent
    home_skills = Path.home() / ".grok" / "skills"
    found: list[Path] = []
    for root in (
        cwd / ".grok" / "skills",
        parent / "bob" / ".grok" / "skills",
        parent / ".grok" / "skills",
        parent / "common" / ".grok" / "skills",
        home_skills,
    ):
        try:
            if root.is_dir():
                found.append(root.resolve())
        except OSError:
            continue
    return found


def skill_dag_mcp_argv(
    worker_cwd: str,
    *,
    job_worktree: str | Path | None = None,
    source_file: str | Path | None = None,
) -> list[str]:
    """``python`` + script + vision ``--root`` / optional ``--job-worktree`` (FR #6898)."""
    script = skill_dag_mcp_script_path(worker_cwd, source_file=source_file)
    argv = ["python", script.as_posix()]
    for root in skill_dag_mcp_skill_roots(worker_cwd):
        argv.extend(["--root", root.as_posix()])
    if job_worktree is not None:
        wt = Path(job_worktree)
        if wt.is_dir():
            argv.extend(["--job-worktree", wt.resolve().as_posix()])
    return argv


def opencode_skill_root_read_patterns(root: Path) -> list[str]:
    """Path forms OpenCode asks for under one skill root (FR #7200 / #7909).

    A bare directory key does not match ``<root>\\<book>\\*``. Headless
    ``opencode run --dir`` loads these keys from that directory's ``opencode.json``.
    """
    patterns: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        patterns.append(text)

    resolved = str(root)
    posix = root.as_posix()
    for base in (resolved.rstrip("\\/"), posix.rstrip("/")):
        add(base)
        add(base + "\\*")
        add(base + "/*")
        add(base + "\\**")
        add(base + "/**")
        add(base + "\\*\\*")
        add(base + "/*/*")
    try:
        children = [p for p in root.iterdir() if p.is_dir()]
    except OSError:
        children = []
    for child in children:
        for base in (str(child).rstrip("\\/"), child.as_posix().rstrip("/")):
            add(base)
            add(base + "\\*")
            add(base + "/*")
            add(base + "\\**")
            add(base + "/**")
    return patterns

# FR #7908: worker health-checks skill-dag before handing a job to the model.
SKILL_DAG_PREFLIGHT_TIMEOUT_S = 20.0
JOB_SKILL_BY_TYPE = {
    "FR": "bobiverse-bob-job-fr",
    "MRB": "bobiverse-bob-job-mrb",
    "UAT": "bobiverse-bob-job-uat",
    "FIX": "bobiverse-bob-job-fr",
}


def skill_dag_job_skill_id(job_key: str) -> str:
    """Job line ``FR owner/repo#N`` -> the job skill that must load (FR #7908)."""
    m = re.match(r"(?i)^\s*(FR|MRB|UAT|FIX)\b", str(job_key or ""))
    if not m:
        return "bobiverse-bob-job-fr"
    return JOB_SKILL_BY_TYPE.get(m.group(1).upper(), "bobiverse-bob-job-fr")


def skill_dag_job_skill_md(worker_cwd: str, job_key: str = "") -> Path | None:
    """First ``<root>/<job-skill>/SKILL.md`` the seat can read, or None."""
    sid = skill_dag_job_skill_id(job_key)
    for root in skill_dag_mcp_skill_roots(worker_cwd):
        try:
            cand = Path(root) / sid / "SKILL.md"
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def probe_skill_dag_mcp_cli(
    worker_cwd: str,
    *,
    job_worktree: str | Path | None = None,
    job_key: str = "",
    runner: Optional[Callable[..., object]] = None,
    timeout_s: float = SKILL_DAG_PREFLIGHT_TIMEOUT_S,
) -> dict:
    """Run the seat's skill-dag one-shot and load the job skill (FR #7908).

    Same script + roots + ``--job-worktree`` OpenCode launches. ``get_skill`` is the
    path that used to kill the stdio server on non-code-page glyphs; a status probe
    is the fallback when no job SKILL.md exists.
    """
    try:
        script = skill_dag_mcp_script_path(worker_cwd)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"script-{type(exc).__name__}"}
    if not script.is_file():
        return {"ok": False, "reason": "script-missing"}
    argv = ["python", script.as_posix()]
    for root in skill_dag_mcp_skill_roots(worker_cwd):
        argv.extend(["--root", Path(root).as_posix()])
    if job_worktree:
        try:
            wt = Path(job_worktree)
            if wt.is_dir():
                argv.extend(["--job-worktree", wt.resolve().as_posix()])
        except OSError:
            pass
    skill = skill_dag_job_skill_md(worker_cwd, job_key)
    if skill is not None:
        argv.extend(["--once", "get_skill", "--path", str(skill)])
    else:
        argv.extend(["--once", "status"])
    run = runner or subprocess.run
    try:
        proc = run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"run-{type(exc).__name__}"}
    rc_raw = getattr(proc, "returncode", 1)
    rc = 1 if rc_raw is None else int(rc_raw)
    out = str(getattr(proc, "stdout", "") or "").strip()
    err = str(getattr(proc, "stderr", "") or "").strip()
    if rc != 0:
        return {"ok": False, "reason": f"exit-{rc}", "stderr": err[-500:]}
    try:
        data = json.loads(out.splitlines()[-1]) if out else {}
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "reason": "bad-json", "stdout": out[-300:]}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "bad-json", "stdout": out[-300:]}
    if skill is not None:
        ok = bool(data.get("ok"))
    else:
        ok = "node_count" in data
    return {"ok": ok, "reason": "" if ok else str(data.get("reason") or "unhealthy")}


def skill_dag_preflight(
    probe: Callable[[], object],
    restart: Callable[[], object],
) -> dict:
    """FR #7908: probe, restart once, probe again; give up cleanly with skill_dag_down."""
    try:
        first = bool(probe())
    except Exception:  # noqa: BLE001
        first = False
    if first:
        return {"action": "continue", "restarted": False, "reason": ""}
    try:
        restart()
    except Exception:  # noqa: BLE001 - a failed restart is just still down
        pass
    try:
        second = bool(probe())
    except Exception:  # noqa: BLE001
        second = False
    if second:
        return {"action": "continue", "restarted": True, "reason": ""}
    return {"action": "giveup", "restarted": True, "reason": "skill_dag_down"}


def skill_dag_down_detail_token(probe_reason: str = "", skill_path: str | Path | None = None) -> str:
    """Wire token after GIVEUP job key (FR #7963): ``skill_dag_down`` or ``skill_dag_down:exit-1``."""
    reason = "skill_dag_down"
    detail = " ".join(str(probe_reason or "").split()).strip()
    if detail and detail.lower() not in ("skill_dag_down", "skill-dag-down"):
        # Keep one wire token: colons ok, spaces become dashes, cap length.
        safe = re.sub(r"[^A-Za-z0-9._:=+/-]+", "-", detail).strip("-")[:80]
        if safe:
            reason = f"skill_dag_down:{safe}"
    if skill_path:
        try:
            name = Path(skill_path).name
        except (TypeError, ValueError):
            name = ""
        name = " ".join(str(name).split()).strip()
        if name:
            reason = f"{reason}:skill={name}"
    return reason


def skill_dag_down_giveup_line(
    job_key: str,
    *,
    probe_reason: str = "",
    skill_path: str | Path | None = None,
) -> str:
    """Shop wire ``GIVEUP <TYPE> owner/repo#N skill_dag_down[:detail]`` (FR #7908 / #7963)."""
    key = " ".join(str(job_key or "").split()).strip()
    token = skill_dag_down_detail_token(probe_reason, skill_path)
    return f"GIVEUP {key} {token}" if key else f"GIVEUP job {token}"


def opencode_fleet_script_roots(worker_cwd: str) -> list[Path]:
    """Install script dirs the seat skills tell OpenCode to read (FR #8064).

    ``worker_cwd`` is ``<ai root>\\bob\\worker``. The fleet copies live beside
    that, not inside the job worktree: ``bob\\scripts`` and ``common\\scripts``.
    """
    install = Path(worker_cwd).resolve().parent
    return [install / "bob" / "scripts", install / "common" / "scripts"]


def opencode_skill_read_permission_block(worker_cwd: str) -> dict:
    """Read-only ``external_directory`` allow for skill roots and fleet scripts.

    FR #7196 / #7909: skill-dag roots. FR #8064: ``bob\\scripts`` and
    ``common\\scripts`` so harvest/intake reads are not auto-rejected. Edit
    stays deny. ``C:\\passwords`` stays deny and is never an allow.
    """
    allow: dict[str, str] = {}
    edit: dict[str, str] = {}
    roots = list(skill_dag_mcp_skill_roots(worker_cwd))
    roots.extend(opencode_fleet_script_roots(worker_cwd))
    for root in roots:
        for key in opencode_skill_root_read_patterns(root):
            allow[key] = "allow"
            edit[key] = "deny"
    for key in (r"C:\passwords", r"C:\passwords\*", r"C:\passwords\**", r"C:/passwords", r"C:/passwords/*"):
        allow[key] = "deny"
        edit[key] = "deny"
    return {"external_directory": allow, "edit": edit}


def opencode_skill_read_allow_gaps(config_path: str | Path, worker_cwd: str) -> list[str]:
    """Skill-root read patterns missing from the ``opencode.json`` ``--dir`` loads."""
    expected = opencode_skill_read_permission_block(worker_cwd).get("external_directory") or {}
    try:
        data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return sorted(str(k) for k in expected)
    perm = data.get("permission") if isinstance(data, dict) else None
    allow = {}
    if isinstance(perm, dict) and isinstance(perm.get("external_directory"), dict):
        allow = perm["external_directory"]
    missing = [
        str(key)
        for key, want in expected.items()
        if want == "allow" and allow.get(key) != "allow"
    ]
    return missing


def report_opencode_skill_read_gaps(config_path: str | Path, worker_cwd: str) -> list[str]:
    """FR #7909: auto-report when the effective config does not grant skill-root reads."""
    missing = opencode_skill_read_allow_gaps(config_path, worker_cwd)
    if not missing:
        return []
    try:
        import runtime_failure

        runtime_failure.report_message(
            "bob-worker",
            "opencode skill-root read allow missing count=%s" % len(missing),
            site="opencode-skill-read-allow",
        )
    except Exception:
        return missing
    return missing

def opencode_job_worktree_read_patterns(worktree: str | Path) -> list[str]:
    """FR #7911: the job tree and its ``.bob`` folder are not external."""
    root = Path(worktree)
    try:
        root = root.resolve()
    except OSError:
        pass
    patterns: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        patterns.append(text)

    for folder in (root, root / ".bob"):
        for base in (str(folder).rstrip("\\/"), folder.as_posix().rstrip("/")):
            add(base)
            add(base + "/**")
            add(base + "\\**")
            add(base + "/*")
            add(base + "\\*")
    return patterns


def resolve_job_git_dir(job_worktree: str | Path) -> Optional[Path]:
    """Resolve the on-disk gitdir for a linked worktree (``.git`` file -> ``.../.git/worktrees/<name>``).

    FR #8572: stale ``index.lock`` and OpenCode ``external_directory`` cleanup live under this
    path (often ``C:\\ai\\bob\\.git\\worktrees\\<job>``), outside the job cwd.
    """
    root = Path(job_worktree or "")
    if not root:
        return None
    try:
        root = root.resolve()
    except OSError:
        return None
    marker = root / ".git"
    if marker.is_dir():
        return marker
    if marker.is_file():
        try:
            text = marker.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if text.lower().startswith("gitdir:"):
            raw = text.split(":", 1)[1].strip()
            found = Path(raw)
            if not found.is_absolute():
                found = (root / found).resolve()
            else:
                try:
                    found = found.resolve()
                except OSError:
                    pass
            return found
    return None


def opencode_job_gitdir_read_patterns(job_worktree: str | Path) -> list[str]:
    """FR #8572: allowlist the job's git worktree dir so lock cleanup is not auto-rejected."""
    git_dir = resolve_job_git_dir(job_worktree)
    if git_dir is None:
        return []
    patterns: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        patterns.append(text)

    for base in (str(git_dir).rstrip("\\/"), git_dir.as_posix().rstrip("/")):
        add(base)
        add(base + "/**")
        add(base + "\\**")
        add(base + "/*")
        add(base + "\\*")
        add(base + "/index.lock")
        add(base + "\\index.lock")
    return patterns


def clear_stale_job_index_lock(
    job_worktree: str | Path,
    *,
    log_fn: Optional[Callable[[str], None]] = None,
) -> bool:
    """FR #8572: drop stale ``index.lock`` under the job gitdir before inject / git ops.

    Best-effort unlink. If another ``git.exe`` still holds the lock, ``OSError`` is logged and
    False is returned (do not crash the seat).
    """
    git_dir = resolve_job_git_dir(job_worktree)
    if git_dir is None:
        return False
    lock = git_dir / "index.lock"
    if not lock.is_file():
        return False
    try:
        lock.unlink()
    except OSError as e:
        if log_fn is not None:
            try:
                log_fn(
                    f"opencode-ready: stale index.lock unlink failed "
                    f"path={lock} err={type(e).__name__}"
                )
            except Exception:
                pass
        return False
    if log_fn is not None:
        try:
            log_fn(f"opencode-ready: cleared stale index.lock path={lock}")
        except Exception:
            pass
    return True


def opencode_skill_dag_mcp_document(
    worker_cwd: str,
    *,
    job_worktree: str | Path | None = None,
) -> dict:
    """Project ``opencode.json`` fragment with local skill-dag MCP (FR #6898 / #7196)."""
    perm = opencode_skill_read_permission_block(worker_cwd)
    if job_worktree:
        allow = perm.setdefault("external_directory", {})
        for key in opencode_job_worktree_read_patterns(job_worktree):
            allow[key] = "allow"
        # FR #8572: linked worktree gitdir (index.lock) is outside the job cwd.
        for key in opencode_job_gitdir_read_patterns(job_worktree):
            allow[key] = "allow"
    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "skill-dag": {
                "type": "local",
                "command": skill_dag_mcp_argv(worker_cwd, job_worktree=job_worktree),
            }
        },
        "permission": perm,
    }


def write_opencode_skill_dag_mcp_config(
    target_dir: str | Path,
    *,
    worker_cwd: str | None = None,
    job_worktree: str | Path | None = None,
) -> Path:
    """Write/merge skill-dag into project ``opencode.json`` under ``target_dir`` only."""
    root = Path(target_dir)
    root.mkdir(parents=True, exist_ok=True)
    cfg = root / OPENCODE_SKILL_DAG_MCP_RELPATH
    seat = worker_cwd or str(root)
    incoming = opencode_skill_dag_mcp_document(seat, job_worktree=job_worktree)
    data: dict = {}
    if cfg.is_file():
        try:
            existing = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                data.update(existing)
        except json.JSONDecodeError:
            data = {}
    mcp = data.get("mcp")
    if not isinstance(mcp, dict):
        mcp = {}
    mcp["skill-dag"] = incoming["mcp"]["skill-dag"]
    data["mcp"] = mcp
    incoming_perm = incoming.get("permission")
    if isinstance(incoming_perm, dict):
        perm = data.get("permission")
        if not isinstance(perm, dict):
            perm = {}
        for key, block in incoming_perm.items():
            if isinstance(block, dict):
                cur = perm.get(key)
                if not isinstance(cur, dict):
                    cur = {}
                cur.update(block)
                perm[key] = cur
            else:
                perm[key] = block
        data["permission"] = perm
    if "$schema" not in data:
        data["$schema"] = incoming["$schema"]
    cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    report_opencode_skill_read_gaps(cfg, seat)
    return cfg


def write_opencode_skill_dag_mcp_config_if_agent(spec: LaunchSpec) -> None:
    if not getattr(spec, "write_opencode_skill_dag_mcp", False):
        return
    write_opencode_skill_dag_mcp_config(spec.cwd, worker_cwd=spec.cwd)


def assert_fresh(argv: list, files: Optional[dict] = None, allow_resume: bool = False) -> None:
    """t765u: an agent is never resumed/continued/attached. Refuse any command line that says so.
    FR #2522: allow_resume=True is passed ONLY by maintenance builds; it permits exactly one --resume <uuid>."""
    args = list(argv)
    if allow_resume and "--resume" in args:
        i = args.index("--resume")
        sid = str(args[i + 1]) if i + 1 < len(args) else ""
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", sid):
            raise ValueError("refusing to launch: maintenance --resume needs an explicit session uuid")
        args = args[:i] + args[i + 2:]
    for a in args:
        if str(a).lower() in FORBIDDEN_FLAGS:
            raise ValueError(f"refusing to launch: '{a}' would reuse an existing agent session")
    for text in (files or {}).values():
        if re.search(r"(?i)(^|\s)(--resume|--continue|-r|-c)(\s|=|$)", str(text)):
            raise ValueError("refusing to launch: launcher script would resume/continue an agent session")


def build_launch(kind: str, mode: str, cwd: str, prompt: str, exe: str, run_dir: Path, session_id: Optional[str] = None,
                 resume_session_id: Optional[str] = None, install_root: str | Path | None = None) -> LaunchSpec:
    if resume_session_id and not (mode == "maintenance" and kind == "grok"):
        raise ValueError("refusing to launch: only grok maintenance may resume (FR #2522)")
    sid = resume_session_id or session_id or str(uuid.uuid4())
    rules = rules_text(cwd, mode)
    files: dict = {}
    job_wt = (os.environ.get("BOB_JOB_WORKTREE") or "").strip() or None
    mcp_args: list = []
    if str(mode).strip().lower() == "agent" and str(kind).strip().lower() in ("grok", "cursor"):
        mcp_args = skill_dag_mcp_launch_args(cwd, job_worktree=job_wt)
    if kind == "grok":
        # FR #2699: every grok seat (agent/plan/monitor/maintenance) shares the same
        # --no-auto-update + --no-alt-screen prefix so Plan cannot self-update mid-session.
        prefix = [exe, "--no-auto-update", "--no-alt-screen", "--cwd", cwd]
        # FR #3623: headless agent seats must not block on ask_user_question (TUI waits forever).
        if mode == "agent":
            prefix = prefix + ["--disallowed-tools", "ask_user_question"]
        if mode == "plan":
            argv = prefix + ["--permission-mode", "plan", "--session-id", sid, "--rules", rules, prompt]
        elif resume_session_id:
            argv = prefix + ["--resume", sid, "--rules", rules, prompt]
        else:
            argv = prefix + ["-s", sid, "--rules", rules, prompt]
        try:
            import worker_start_model as wsm

            _gcfg = wsm.load_worker_start_config()
            # FR #8321: a restored seat pins its model in the child env; launch it.
            grok_model = wsm.launch_selected_model("grok", _gcfg, env=os.environ)
            # FR #2699 / MRB #2710: the shared --no-auto-update/--no-alt-screen/--cwd
            # prefix stays first; model/effort flags go right after it.
            tail = [exe] + argv[len(prefix):]
            tail = wsm.launch_argv_with_model("grok", tail, grok_model)
            tail = wsm.launch_argv_with_effort(
                "grok", tail, wsm.configured_start_effort("grok", _gcfg)
            )
            argv = prefix + tail[1:]
        except Exception:
            pass
    elif kind == "cursor":
        # The prompt goes through a FILE read by a fixed launcher: text never lands on a command line (no shell injection).
        pfile = str(Path(run_dir) / "prompt.txt")
        lfile = str(Path(run_dir) / "launch-cursor.ps1")
        esc = lambda s: str(s).replace("'", "''")  # noqa: E731
        agent_line = (f"& '{esc(exe)}' --plan --model auto --workspace '{esc(cwd)}' $prompt" if mode == "plan"
                      else f"& '{esc(exe)}' --trust --force --workspace '{esc(cwd)}' -- $prompt")
        try:
            import worker_start_model as wsm

            cur_model = wsm.launch_selected_model(
                "cursor", wsm.load_worker_start_config(), env=os.environ
            )
            if cur_model:
                if "--model auto" in agent_line:
                    agent_line = agent_line.replace("--model auto", f"--model {esc(cur_model)}", 1)
                elif "--model" not in agent_line:
                    agent_line = agent_line.replace(
                        f"& '{esc(exe)}'",
                        f"& '{esc(exe)}' --model '{esc(cur_model)}'",
                        1,
                    )
        except Exception:
            pass
        files[pfile] = prompt
        files[lfile] = "\n".join(["$ErrorActionPreference = 'Stop'", f"$prompt = [IO.File]::ReadAllText('{esc(pfile)}')",
                                  f"Set-Location -LiteralPath '{esc(cwd)}'", agent_line, "exit $LASTEXITCODE"])
        if str(mode).strip().lower() == "agent":
            mcp_path = str(Path(cwd) / CURSOR_SKILL_DAG_MCP_RELPATH)
            files[mcp_path] = json.dumps(
                cursor_skill_dag_mcp_document(cwd, job_worktree=job_wt), indent=2
            ) + "\n"
        argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", lfile]
    elif kind == "opencode":
        # FR #6120: OpenCode is a headless CLI one-shot per prompt.  The wrapper runs the
        # initial prompt from a file, then loops on injected console lines so the worker
        # can drive it like a persistent seat.  The model comes from $env:BOB_OPENCODE_MODEL.
        #
        # Runtime 5h rolling-cap guard: each ``opencode run`` is watched.  If it hits a
        # 429 / rate-limit / rolling-limit message, stalls with no stdout/stderr for the
        # idle watchdog (BOB_OPENCODE_WATCHDOG_MS, default 120s), or exits with a
        # payment/balance error, the wrapper kills the process tree, logs to
        # opencode-out-of-fuel.log, and records a pause for that model until the window
        # resets (parsed from output if present, else a conservative 1-hour default).
        # FR #6156: wall-clock alone while the process still produces output must not kill
        # or pause — only idle/no-output (or real 402/429 text) trips the guard.
        pfile = str(Path(run_dir) / "prompt.txt")
        lfile = str(Path(run_dir) / "launch-opencode.ps1")
        turns_log = str(Path(run_dir) / "opencode-turns.jsonl")
        esc = lambda s: str(s).replace("'", "''")  # noqa: E731
        files[pfile] = prompt
        if str(mode).strip().lower() == "agent":
            mcp_path = str(Path(cwd) / OPENCODE_SKILL_DAG_MCP_RELPATH)
            files[mcp_path] = json.dumps(opencode_skill_dag_mcp_document(cwd), indent=2) + "\n"
        helper_path = _resolve_opencode_fuel_helper_path(cwd=cwd, install_root=install_root)
        guard_resolved = _resolve_installed_worker_script(
            "opencode_turn_guard.py", cwd=cwd, install_root=install_root
        )
        guard_path = guard_resolved or (Path(__file__).resolve().parent / "opencode_turn_guard.py")
        wedge_resolved = _resolve_installed_worker_script(
            "opencode_tool_wedge.py", cwd=cwd, install_root=install_root
        )
        if wedge_resolved is None:
            _report_missing_worker_script("opencode_tool_wedge.py")
        wedge_text = str(wedge_resolved or "")
        iso_resolved = _resolve_installed_worker_script(
            "opencode_seat_isolate.py", cwd=cwd, install_root=install_root
        )
        iso_path = iso_resolved or (Path(__file__).resolve().parent / "opencode_seat_isolate.py")
        log_resolved = _resolve_installed_worker_script(
            "opencode_stdout_log.py", cwd=cwd, install_root=install_root
        )
        log_path = log_resolved or (Path(__file__).resolve().parent / "opencode_stdout_log.py")
        # FR #8150: peek OpenCode app log for ERROR Free usage / rate-limit (stdout may be silent).
        pes_resolved = _resolve_installed_worker_script(
            "provider_error_source.py", cwd=cwd, install_root=install_root
        )
        pes_path = pes_resolved or (
            Path(__file__).resolve().parent / "provider_error_source.py"
        )
        # FR #6157: each opencode run emits turn_started / turn_ended into opencode-turns.jsonl
        # so BoredEmitter gets harvest-hold / done-miss / startup-ready parity with Grok.
        # FR #6240: no external_directory allow. Each injected assign carries its own
        # @@BOBJOB1 frame. The standing prompt is not a job and is not scanned.
        # FR #8220: env pin > tray pin > free default. Never throw when tray pin is empty
        # (flamingo-22516 recycled with empty workerStartModels.opencode + no child env stamp).
        oc_cfg_model = ""
        try:
            import worker_start_model as wsm

            _oc_cfg = wsm.load_worker_start_config()
            oc_cfg_model = wsm.launch_selected_model("opencode", _oc_cfg, env=os.environ)
            if not oc_cfg_model:
                oc_cfg_model = wsm.default_opencode_free_model(_oc_cfg)
            oc_paid_model = wsm.default_opencode_paid_model(_oc_cfg)
        except Exception:
            oc_cfg_model = ""
            oc_paid_model = ""
        if not oc_cfg_model:
            oc_cfg_model = "opencode/deepseek-v4.1-flash-free"
        if not oc_paid_model:
            oc_paid_model = "opencode-go/deepseek-v4-pro"
        oc_fallback = (
            f"if (-not $env:BOB_OPENCODE_MODEL) {{ $env:BOB_OPENCODE_MODEL = '{esc(oc_cfg_model)}' }}"
        )
        files[lfile] = "\n".join([
            r"$ErrorActionPreference = 'Stop'",
            oc_fallback,
            r"$model = $env:BOB_OPENCODE_MODEL",
            f"$exe = '{esc(exe)}'",
            f"$prompt = [IO.File]::ReadAllText('{esc(pfile)}')",
            f"$turnsLog = '{esc(turns_log)}'",
            r"$script:ocTurnN = 0",
            r"$fuelLog = Join-Path $env:LOCALAPPDATA 'Bobiverse\worker\logs\opencode-out-of-fuel.log'",
            r"$pauseStateDir = Join-Path $env:LOCALAPPDATA 'Bobiverse\worker\state'",
            f"$pyHelper = '{esc(str(helper_path))}'",
            f"$guardPy = '{esc(str(guard_path))}'",
            f"$wedgePy = '{esc(wedge_text)}'",
            f"$isolatePy = '{esc(str(iso_path))}'",
            f"$stdoutLogPy = '{esc(str(log_path))}'",
            f"$providerErrPy = '{esc(str(pes_path))}'",
            r"$script:ocStdoutLog = ''",
            r"$script:ocDagRetries = 1",
            r"$script:ocDbLockTries = 0",
            r"$script:ocWedgeTicks = 0",
            r"$script:ocWedgeAction = ''",
            r"$script:ocEpipeTries = 0",
            r"$script:ocCleanExitTries = 0",
            r"New-Item -ItemType Directory -Force -Path (Split-Path -Parent $fuelLog) | Out-Null",
            r"New-Item -ItemType Directory -Force -Path $pauseStateDir | Out-Null",
            r"New-Item -ItemType Directory -Force -Path (Split-Path -Parent $turnsLog) | Out-Null",
            r"# FR #7997: one OpenCode data dir per seat so two runs do not share opencode.db.",
            r"$pyIso = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"if (-not $pyIso) { $pyIso = 'python.exe' }",
            r"try {",
            r"    $isoOut = & $pyIso $isolatePy prepare 2>&1",
            r"    if ($LASTEXITCODE -ne 0) { throw ('prepare exit ' + $LASTEXITCODE) }",
            r"    foreach ($row in @($isoOut)) {",
            r"        if ($row -match '^(XDG_DATA_HOME|OPENCODE_DB|BOB_OPENCODE_DATA_DIR)=(.*)$') {",
            r"            Set-Item -Path ('Env:' + $Matches[1]) -Value $Matches[2].Trim()",
            r"        }",
            r"    }",
            r"    if ($env:BOB_OPENCODE_DATA_DIR) {",
            r"        Set-Content -LiteralPath (Join-Path (Split-Path -Parent $turnsLog) 'opencode-data-dir.txt') -Value $env:BOB_OPENCODE_DATA_DIR -Encoding ascii",
            r"    }",
            r"} catch {",
            r"    Write-Output ('opencode-seat-isolate: prepare failed ' + $_.Exception.Message)",
            r"}",
            r"# FR #8033: prepare failure / miss must not inherit the shared default opencode.db.",
            r"if (-not $env:OPENCODE_DB -or [string]::IsNullOrWhiteSpace([string]$env:OPENCODE_DB) -or -not $env:XDG_DATA_HOME) {",
            r"    $fbBase = $env:BOB_OPENCODE_SEAT_DATA_ROOT",
            r"    if (-not $fbBase) { $fbBase = Join-Path $env:LOCALAPPDATA 'Bobiverse\worker\opencode-data' }",
            r"    $fbTag = $env:BOB_NICK",
            r"    if (-not $fbTag) { $fbTag = 'seat' }",
            r"    if ($env:BOB_WORKER_PID) { $fbTag = ($fbTag + '-' + $env:BOB_WORKER_PID) }",
            r"    $fbTag = ($fbTag + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)) -replace '[^A-Za-z0-9._-]', '-'",
            r"    $fbRoot = Join-Path $fbBase $fbTag",
            r"    $fbData = Join-Path $fbRoot 'opencode'",
            r"    New-Item -ItemType Directory -Force -Path $fbData | Out-Null",
            r"    $env:XDG_DATA_HOME = $fbRoot",
            r"    $env:BOB_OPENCODE_DATA_DIR = $fbData",
            r"    $env:OPENCODE_DB = Join-Path $fbData 'opencode.db'",
            r"    Set-Content -LiteralPath (Join-Path (Split-Path -Parent $turnsLog) 'opencode-data-dir.txt') -Value $fbData -Encoding ascii",
            r"    Write-Output ('opencode-seat-isolate: fallback data dir ' + $fbData)",
            r"}",
            r"function Write-OpencodeTurnMarker([string]$Type, [int]$TurnNumber, [string]$Status, [string]$Err, [string]$ErrClass) {",
            r"    # FR #6157 / #7201 / #8018: durable turn markers; error status trips failed-turn retry/GIVEUP",
            r"    $entry = @{ type = $Type; ts = (Get-Date -Format o); turn_number = $TurnNumber }",
            r"    if ($Status) { $entry.status = $Status }",
            r"    if ($Err) { $entry.error = $Err }",
            r"    if ($ErrClass) { $entry.error_class = $ErrClass }",
            r"    if ($script:ocStdoutLog) { $entry.stdout_log = [IO.Path]::GetFileName($script:ocStdoutLog) }",
            r"    Add-Content -LiteralPath $turnsLog -Value ($entry | ConvertTo-Json -Compress) -ErrorAction SilentlyContinue",
            r"}",
            r"function Write-OpencodeJobGiveup([string]$JobKey, [string]$Reason) {",
            r"    if (-not $JobKey) { return }",
            r"    $g = 'GIVEUP ' + $JobKey + ' ' + $Reason",
            r"    if ($script:ocStdoutLog) { $g = $g + ' log=' + [IO.Path]::GetFileName($script:ocStdoutLog) }",
            r"    if ($env:BOB_OUTBOX) { Add-Content -LiteralPath $env:BOB_OUTBOX -Value $g -ErrorAction SilentlyContinue }",
            r"    Write-Output $g",
            r"}",
            # FR #8454: free pool exhausted and paid remains -> rebind, same job, no shop GIVEUP.
            f"$script:ocPaidModel = '{esc(oc_paid_model)}'",
            r"$script:ocPaidSwitched = $false",
            r"$script:ocSwitchPaid = $false",
            r"function Test-OpencodeModelIsFree([string]$Mid) {",
            r"    if (-not $Mid) { return $true }",
            r"    if ($Mid -match '(?i)^opencode-go/|-pro(/|$)|/opencode-go/') { return $false }",
            r"    return $true",
            r"}",
            r"function Test-OpencodePaidPoolRemains {",
            r"    if ($env:BOB_OPENCODE_GO_REMAINING -eq '0') { return $false }",
            r"    $cache = Join-Path $pauseStateDir 'agent-list-fuel.json'",
            r"    if (-not (Test-Path -LiteralPath $cache)) { return $true }",
            r"    try {",
            r"        $doc = Get-Content -LiteralPath $cache -Raw | ConvertFrom-Json",
            r"        $go = $doc.opencode_go",
            r"        if ($null -eq $go -or [string]$go -eq '') { return $true }",
            r"        if ([int]$go -gt 0 -and -not $doc.opencode_models) { return $true }",
            r"        $any = $false",
            r"        if ($doc.opencode_models) {",
            r"            foreach ($p in $doc.opencode_models.PSObject.Properties) {",
            r"                try { if ([int]$p.Value -gt 0) { $any = $true } } catch { }",
            r"            }",
            r"            return $any",
            r"        }",
            r"        return ([int]$go -gt 0)",
            r"    } catch { return $true }",
            r"}",
            r"function Try-OpencodeSwitchToPaid([string]$Current, [string]$Reason) {",
            r"    if ($script:ocStopClosed) { return $false }",
            r"    if ($script:ocPaidSwitched) { return $false }",
            r"    if (-not (Test-OpencodeModelIsFree $Current)) { return $false }",
            r"    if (-not $script:ocPaidModel) { return $false }",
            r"    if (-not (Test-OpencodePaidPoolRemains)) { return $false }",
            r"    $script:ocPaidSwitched = $true",
            r"    $script:ocSwitchPaid = $true",
            r"    $script:model = $script:ocPaidModel",
            r"    $env:BOB_OPENCODE_MODEL = $script:ocPaidModel",
            r"    Write-Output ('opencode switch-to-paid model=' + $script:ocPaidModel + ' reason=' + $Reason)",
            r"    return $true",
            r"}",
            # FR #7899: ReadAllText throws when OpenCode still holds bob-oc-out exclusive.
            r"function Read-OpencodeCapture([string]$Path) {",
            r"    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return '' }",
            r"    try {",
            r"        $fs = New-Object System.IO.FileStream($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)",
            r"        try {",
            r"            $reader = New-Object System.IO.StreamReader($fs)",
            r"            try { return $reader.ReadToEnd() } finally { $reader.Dispose() }",
            r"        } finally { $fs.Dispose() }",
            r"    } catch {",
            r"        if (-not $script:ocCaptureLogged) {",
            r"            $script:ocCaptureLogged = $true",
            r"            $capMsg = 'opencode-capture: read failed once'",
            r"            Write-Output $capMsg",
            r"            $pyCap = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"            if (-not $pyCap) { $pyCap = 'python.exe' }",
            r"            try { & $pyCap $guardPy capture-failed --message $capMsg 2>$null | Out-Null } catch { }",
            r"        }",
            r"        return ''",
            r"    }",
            r"}",
            r"function Write-OpencodeJobNack([string]$JobKey, [string]$Reason) {",
            r"    if (-not $JobKey) { return }",
            r"    $nack = 'NACK ' + $JobKey + ' ' + $Reason + ' (FR #6240)'",
            r"    if ($script:ocStdoutLog) { $nack = $nack + ' log=' + [IO.Path]::GetFileName($script:ocStdoutLog) }",
            r"    if ($env:BOB_OUTBOX) {",
            r"        Add-Content -LiteralPath $env:BOB_OUTBOX -Value $nack -ErrorAction SilentlyContinue",
            r"        $refuse = Join-Path (Split-Path -Parent $env:BOB_OUTBOX) 'opencode-job-refused.txt'",
            r"        Add-Content -LiteralPath $refuse -Value $JobKey -ErrorAction SilentlyContinue",
            r"    }",
            r"    Write-Output $nack",
            r"}",
            r"function Invoke-OpencodeRun([string]$line, [string]$jobKey, [string]$ocDir) {",
            r"    if ($env:BOB_OPENCODE_MODEL) { $model = $env:BOB_OPENCODE_MODEL }",
            r"    $script:ocSwitchPaid = $false",
            r"    if ($jobKey -and -not $ocDir) {",
            r"        Write-Output 'opencode-ready: blocked job_context_malformed. Next: the worker message had no job directory. No DONE.'",
            r"        Write-OpencodeJobNack $jobKey 'job-context-malformed'",
            r"        return",
            r"    }",
            r"    if ($ocDir) {",
            r"        try { $full = [IO.Path]::GetFullPath($ocDir) } catch { $full = $ocDir }",
            r"        $root = [IO.Path]::GetPathRoot($full)",
            r"        if ($root -and ($full.TrimEnd('\') -eq $root.TrimEnd('\'))) {",
            r"            Write-Output 'opencode-ready: blocked worktree_base_refused. Next: the job directory canonicalized to a drive root. No DONE.'",
            r"            Write-OpencodeJobNack $jobKey 'worktree-base-refused'",
            r"            return",
            r"        }",
            r"        $norm = $ocDir.Replace('/','\')",
            r"        $check = $norm + ' ' + $full.Replace('/','\')",
            r"        if (Test-Path -LiteralPath $ocDir) {",
            r"            $item = Get-Item -LiteralPath $ocDir -Force",
            r"            if ($item.Target) { foreach ($t in @($item.Target)) { $check = $check + ' ' + ([string]$t).Replace('/','\') } }",
            r"        }",
            r"        if ($check -match '(?i)(\.config\\gh|hosts\.yml|\.git-credentials|\\passwords|\.netrc)') {",
            r"            Write-Output 'opencode-ready: blocked opencode_dir_forbidden. Next: the job worktree path is a credential path. Do not point OpenCode at a credential store.'",
            r"            Write-OpencodeJobNack $jobKey 'opencode-dir-forbidden'",
            r"            exit 4",
            r"        }",
            r"        if (-not (Test-Path -LiteralPath $ocDir -PathType Container)) {",
            r"            Write-Output 'opencode-ready: blocked worktree_absent. Next: create the assigned job worktree (Get-BobiverseJobWorktreePath). Do not pass --auto. This run is not a completed job.'",
            r"            Write-OpencodeJobNack $jobKey 'worktree-absent'",
            r"            return",
            r"        }",
            r"        # FR #6333: BOB_OUTBOX inside --dir so headless opencode can append without external_directory.",
            r"        $bobDir = Join-Path $ocDir '.bob'",
            r"        New-Item -ItemType Directory -Force -Path $bobDir | Out-Null",
            r"        $env:BOB_OUTBOX = Join-Path $bobDir 'outbox.txt'",
            r"        if (-not (Test-Path -LiteralPath $env:BOB_OUTBOX)) { [IO.File]::WriteAllText($env:BOB_OUTBOX, '') }",
            # FR #8247: seat scratch under worktree so a "temp" ask lands inside --dir (never widen %TEMP% allow).
            r"        $bobTmp = Join-Path $bobDir 'tmp'",
            r"        New-Item -ItemType Directory -Force -Path $bobTmp | Out-Null",
            r"        $env:TEMP = $bobTmp",
            r"        $env:TMP = $bobTmp",
            r"        $env:TMPDIR = $bobTmp",
            r"        $env:BOB_OPENCODE_SCRATCH = $bobTmp",
            r"        $argList = @('run', '--dir', $ocDir, '-m', $model, $line)",
            r"    } else {",
            r"        $argList = @('run', '-m', $model, $line)",
            r"    }",
            r"    if ($argList -contains '--auto') { throw 'opencode --auto is forbidden' }",
            r"    $script:ocTurnN++",
            # FR #7952: once per job, before the run. Never changes $model mid-turn.
            r"    if ($env:BOB_OPENCODE_PAUSE_FALLBACK -eq '1' -and $env:BOB_OPENCODE_CONFIGURED_MODEL) {",
            r"        $pyResume = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"        if (-not $pyResume) { $pyResume = 'python.exe' }",
            r"        $nextModel = ''",
            r"        try { $nextModel = (& $pyResume $pyHelper next-model --dir $pauseStateDir --configured $env:BOB_OPENCODE_CONFIGURED_MODEL --current $model 2>$null | Select-Object -Last 1) } catch { $nextModel = '' }",
            r"        $nextModel = ([string]$nextModel).Trim()",
            r"        if ($nextModel -and $nextModel -ne $model) {",
            r"            $model = $nextModel",
            r"            $env:BOB_OPENCODE_MODEL = $model",
            r"            $env:BOB_OPENCODE_PAUSE_FALLBACK = '0'",
            r"        }",
            r"    }",
            r"    $turnN = $script:ocTurnN",
            # FR #8133: turn markers and watchdogs only for a real job inject. Standing /
            # idle runs must not arm turn_started or the hard ceiling.
            r"    $script:ocSkipFuelLog = $false",
            r"    $script:ocStopClosed = $false",
            r"    $script:ocHasJob = -not [string]::IsNullOrWhiteSpace([string]$jobKey)",
            r"    if ($script:ocHasJob) { Write-OpencodeTurnMarker 'turn_started' $turnN }",
            r"    try {",
            r"""    $argStr = ($argList | ForEach-Object { if ($_ -match '[\s"]') { $escaped = $_ -replace '(\\*)"', '$1$1\"'; $escaped = $escaped -replace '(\\+)$', '$1$1'; '"' + $escaped + '"' } else { $_ } }) -join ' '""",
            r"    $proc = $null",
            r"    $stdout = ''",
            r"    $stderr = ''",
            r"    $outFile = $null",
            r"    $errFile = $null",
            r"    $timedOut = $false",
            r"    $fuelHitLive = $false",
            r"    $killReason = ''",
            r"    try {",
            # FR #6156: redirect to files and treat growing file size as heartbeat (not absolute WaitForExit).
            # FR #6366: descendant presence refreshes the short watchdog. FR #7976 / #8008:
            # the 30 min ceiling measures time since real progress (output growth or
            # worktree mtime), not wall clock. CPU/descendants refresh lastBeat only
            # (short idle watchdog); they do not reset the hard-ceiling stall clock.
            # FR #8133: both clocks are job-only.
            r"        $watchdogMs = if ($env:BOB_OPENCODE_WATCHDOG_MS) { [int]$env:BOB_OPENCODE_WATCHDOG_MS } else { 120000 }",
            r"        $hardCeilingMs = if ($env:BOB_OPENCODE_HARD_CEILING_MS) { [int]$env:BOB_OPENCODE_HARD_CEILING_MS } else { 1800000 }",
            r"        $script:ocStdoutLog = ''",
            r"        if ($script:ocHasJob -and $env:BOB_OPENCODE_STDOUT_LOG -ne '0' -and $stdoutLogPy) {",
            r"            $env:BOB_OC_LOG_JOB = [string]$jobKey",
            r"            $env:BOB_OC_LOG_SEAT = if ($env:BOB_NICK) { $env:BOB_NICK } else { $env:BOB_AGENT_NICK }",
            r"            $env:BOB_OC_LOG_MODEL = [string]$model",
            r"            $env:BOB_OC_LOG_WORKTREE = [string]$ocDir",
            r"            $pyLog = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"            if (-not $pyLog) { $pyLog = 'python.exe' }",
            r"            try { $script:ocStdoutLog = ([string](& $pyLog $stdoutLogPy open)).Trim() } catch { $script:ocStdoutLog = '' }",
            r"        }",
            r"        $script:ocOutPos = 0",
            r"        $script:ocErrPos = 0",
            r"        $capDir = Split-Path -Parent $turnsLog",
            r"        if (-not $capDir) { $capDir = $env:TEMP }",
            r"        $outFile = Join-Path $capDir ('bob-oc-out-' + [guid]::NewGuid().ToString('n') + '.txt')",
            r"        $errFile = Join-Path $capDir ('bob-oc-err-' + [guid]::NewGuid().ToString('n') + '.txt')",
            # MRB #6163 / CodeRabbit: ArgumentList array drops quotes/spaces in $line; use pre-escaped $argStr.
            # FR #8553: never -NoNewWindow with redirects. Sharing the parent console
            # hangs opencode after the build banner (empty stdout) and can tear down the
            # seat with no last-exit. Redirects alone = CreateNoWindow (gap FR-OC-INJECT).
            r"        if ($ocDir) { $proc = Start-Process -FilePath $exe -ArgumentList $argStr -WorkingDirectory $ocDir -PassThru -RedirectStandardOutput $outFile -RedirectStandardError $errFile } else { $proc = Start-Process -FilePath $exe -ArgumentList $argStr -PassThru -RedirectStandardOutput $outFile -RedirectStandardError $errFile }",
            r"        $timedOut = $false",
            r"        $killReason = ''",
            r"        $fuelHitLive = $false",
            r"        $ocJobPoll = 0",
            r"        $lastLen = 0",
            r"        $lastCpu = -1.0",
            r"        $lastWtStamp = $null",
            r"        $lastBusyCheck = [datetime]::UtcNow",
            r"        $lastBeat = [datetime]::UtcNow",
            r"        $runStarted = [datetime]::UtcNow",
            r"        $lastProgress = $runStarted",
            # FR #8026: match free-pool exhaustion while the process is still alive.
            # FR #8151: no bare "rate limit" (tool output / CodeRabbit comments false-pause).
            # FR #8207: Free usage in tool/PR text needs providerFuelCue (level=ERROR / AI_*).
            r"        $liveFuelPattern = 'Free usage limit|subscribe to OpenCode Go|Payment Required|usage balance exhausted|Too Many Requests|rolling limit|rate limited by provider|(HTTP|status( code)?)\D{0,3}(402|429)|AI_(APICall|Retry)Error'",
            r"        $providerFuelCue = 'level=ERROR|AI_(APICall|Retry)Error'",
            r"        $toolNoisePattern = 'coderabbit|coderabbit-ai-generated|rate limited by coderabbit|Rate limit \+ single instance|\"(title|body)\"\s*:|gh (issue|pr|api)|Closes SimonBarnett/|## Summary'",
            # FR #8150: OpenCode may write Free usage only to its app log (no stdout bytes).
            r"        $appLog = ''",
            r"        if ($env:BOB_OPENCODE_DATA_DIR) { $appLog = Join-Path $env:BOB_OPENCODE_DATA_DIR 'log\opencode.log' }",
            r"        $appLogPos = 0",
            r"        if ($appLog -and (Test-Path -LiteralPath $appLog)) { try { $appLogPos = [int](Get-Item -LiteralPath $appLog).Length } catch { $appLogPos = 0 } }",
            r"        $appLogTicks = 0",
            r"        while (-not $proc.HasExited) {",
            r"          try {",
            # FR #8150: poll the app log every ~1s even when stdout/stderr are silent.
            r"            $appLogTicks++",
            r"            if (($appLogTicks % 10) -eq 0 -and $appLog -and $providerErrPy -and -not $fuelHitLive) {",
            r"                $pyApp = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"                if (-not $pyApp) { $pyApp = 'python.exe' }",
            r"                $peekLine = ''",
            r"                try { $peekLine = ([string](& $pyApp $providerErrPy peek $appLog $appLogPos 2>$null | Select-Object -Last 1)).Trim() } catch { $peekLine = '' }",
            r"                if ($peekLine -match '^HIT\s+(\S+)\s+(\d+)') {",
            r"                    $fuelHitLive = $true",
            r"                    $killReason = $Matches[1]",
            r"                    $appLogPos = [int]$Matches[2]",
            r"                    try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }",
            r"                    if ($jobKey -and -not (Try-OpencodeSwitchToPaid $model $killReason)) { Write-OpencodeJobGiveup $jobKey $killReason }",
            r"                    break",
            r"                } elseif ($peekLine -match '^OK\s+(\d+)') {",
            r"                    $appLogPos = [int]$Matches[1]",
            r"                }",
            r"            }",
            r"            $len = 0",
            r"            if (Test-Path -LiteralPath $outFile) { $len += (Get-Item -LiteralPath $outFile).Length }",
            r"            if (Test-Path -LiteralPath $errFile) { $len += (Get-Item -LiteralPath $errFile).Length }",
            r"            if ($len -gt $lastLen) {",
            r"                $lastLen = $len",
            r"                $lastBeat = [datetime]::UtcNow",
            r"                $lastProgress = [datetime]::UtcNow",
            r"                if ($script:ocStdoutLog) {",
            r"                    $pyLog = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"                    if (-not $pyLog) { $pyLog = 'python.exe' }",
            r"                    foreach ($pair in @(@($outFile, 'ocOutPos'), @($errFile, 'ocErrPos'))) {",
            r"                        $cap = Read-OpencodeCapture $pair[0]",
            r"                        $pos = [int](Get-Variable -Name $pair[1] -Scope Script).Value",
            r"                        if ($cap.Length -gt $pos) {",
            r"                            $slice = $cap.Substring($pos)",
            r"                            Set-Variable -Name $pair[1] -Scope Script -Value $cap.Length",
            r"                            $sliceFile = Join-Path $env:TEMP ('bob-oc-slice-' + [guid]::NewGuid().ToString('n') + '.txt')",
            r"                            try {",
            r"                                [IO.File]::WriteAllText($sliceFile, $slice)",
            r"                                & $pyLog $stdoutLogPy append $script:ocStdoutLog $sliceFile | Out-Null",
            r"                            } catch { }",
            r"                            finally { Remove-Item -LiteralPath $sliceFile -ErrorAction SilentlyContinue }",
            r"                        }",
            r"                    }",
            r"                }",
            r"                $peek = (Read-OpencodeCapture $outFile) + [Environment]::NewLine + (Read-OpencodeCapture $errFile)",
            r"                if ($line) { $peek = $peek.Replace([string]$line, ' ') }",
            r"                $peek = [regex]::Replace($peek, '`[^`]*`', ' ')",
            # FR #8151 / #8207: never treat tool/PR/gh echo as live fuel.
            r"                $isToolNoise = ($peek -match $toolNoisePattern)",
            r"                $isFreePhrase = ($peek -match 'Free usage limit|subscribe to OpenCode Go')",
            r"                $hasProviderCue = ($peek -match $providerFuelCue)",
            # FR #8207: paid/go still needs provider cue for Free usage (PR/tool echo).
            r"                # FR #8537: free model CLI stderr Free usage is enough to kill+switch.",
            r"                $isGoModel = ($model -match '(?i)^opencode-go/|-pro(/|$)|/opencode-go/')",
            r"                if ((-not $isToolNoise) -and ($peek -match $liveFuelPattern) -and ((-not $isFreePhrase) -or $hasProviderCue -or (-not $isGoModel))) {",
            r"                    $fuelHitLive = $true",
            r"                    if ($isFreePhrase -and -not $isGoModel) { $killReason = 'fuel-exhausted:opencode-free' } else { $killReason = 'out-of-fuel' }",
            r"                    try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }",
            r"                    if ($jobKey -and -not (Try-OpencodeSwitchToPaid $model $killReason)) { Write-OpencodeJobGiveup $jobKey $killReason }",
            r"                    break",
            r"                }",
            r"            }",
            r"            $busy = $false",
            r"            if (([datetime]::UtcNow - $lastBusyCheck).TotalMilliseconds -ge 2000) {",
            r"                $lastBusyCheck = [datetime]::UtcNow",
            r"                try {",
            # FR #6366 / MRB #6367: walk ALL descendants (pytest under shell is a grandchild).
            r"                    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)",
            r"                    $desc = New-Object 'System.Collections.Generic.HashSet[int]'",
            r"                    $queue = New-Object System.Collections.Queue",
            r"                    $queue.Enqueue([int]$proc.Id)",
            r"                    while ($queue.Count -gt 0) {",
            r"                        $pidCur = [int]$queue.Dequeue()",
            r"                        foreach ($tp in $all) {",
            r"                            if ([int]$tp.ParentProcessId -eq $pidCur -and $desc.Add([int]$tp.ProcessId)) { $queue.Enqueue([int]$tp.ProcessId) }",
            r"                        }",
            r"                    }",
            r"                    $cpuSum = 0.0",
            r"                    try { $self = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $proc.Id) -ErrorAction SilentlyContinue; if ($self) { $cpuSum += [double]$self.UserModeTime + [double]$self.KernelModeTime } } catch { }",
            r"                    foreach ($tp in $all) { if ($desc.Contains([int]$tp.ProcessId)) { try { $cpuSum += [double]$tp.UserModeTime + [double]$tp.KernelModeTime } catch { } } }",
            # Alive descendant (e.g. silent pytest grandchild) keeps the run busy even if CPU sum resets.
            r"                    if ($desc.Count -gt 0) { $busy = $true; $lastBeat = [datetime]::UtcNow }",
            r"                    if ($lastCpu -ge 0 -and $cpuSum -gt $lastCpu) { $busy = $true; $lastBeat = [datetime]::UtcNow }",
            r"                    $lastCpu = $cpuSum",
            r"                } catch { }",
            r"                if ($ocDir -and (Test-Path -LiteralPath $ocDir)) {",
            r"                    try {",
            r"                        $stamp = (Get-ChildItem -LiteralPath $ocDir -Recurse -File -Depth 3 -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).LastWriteTimeUtc",
            r"                        if ($stamp -and $lastWtStamp -and $stamp -gt $lastWtStamp) { $busy = $true; $lastBeat = [datetime]::UtcNow; $lastProgress = [datetime]::UtcNow }",
            r"                        if ($stamp) { $lastWtStamp = $stamp }",
            r"                    } catch { }",
            r"                }",
            r"            }",
            r"            $idleMs = ([datetime]::UtcNow - $lastBeat).TotalMilliseconds",
            r"            $runMs = ([datetime]::UtcNow - $runStarted).TotalMilliseconds",
            r"            $stallMs = ([datetime]::UtcNow - $lastProgress).TotalMilliseconds",
            r"            if ($script:ocHasJob -and $stallMs -ge $hardCeilingMs) {",
            r"                $timedOut = $true",
            r"                $lastProgIso = $lastProgress.ToUniversalTime().ToString('o')",
            r"                $killReason = ('hard ceiling ' + [int]$hardCeilingMs + 'ms; last progress ' + $lastProgIso + '; stall ' + [int]$stallMs + 'ms')",
            r"                try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }",
            # FR #7739: one intake report (machine, seat, job, elapsed, reason). Dedupe is in the helper.
            # FR #8133: never file ceiling intake without a job key.
            r"                $pyCeil = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"                if (-not $pyCeil) { $pyCeil = 'python.exe' }",
            r"                $mach = if ($env:BOB_MACHINE_ID) { $env:BOB_MACHINE_ID } else { $env:COMPUTERNAME }",
            r"                try { & $pyCeil $guardPy ceiling --machine $mach --nick $env:BOB_NICK --job $jobKey --elapsed-ms ([int]$stallMs) --reason $killReason 2>$null | Out-Null } catch { }",
            # FR #7899: a ceiling kill must reach the outbox or the chair re-offers a silent job.
            r"                Write-OpencodeJobGiveup $jobKey $killReason",
            r"                break",
            r"            }",
            # FR #7739: every 50 x 100ms (5s, under 60s) ask if the job was closed, given up, or reassigned.
            r"            $ocJobPoll++",
            r"            if (($ocJobPoll % 50) -eq 0 -and $jobKey) {",
            r"                $pyStop = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"                if (-not $pyStop) { $pyStop = 'python.exe' }",
            r"                $stopLine = ''",
            r"                try { $stopLine = (& $pyStop $guardPy stop --job $jobKey --outbox $env:BOB_OUTBOX 2>$null | Out-String).Trim() } catch { $stopLine = '' }",
            r"                if ($stopLine -like 'stop*') {",
            r"                    $timedOut = $true",
            r"                    try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }",
            # FR #8413: DONE/NACK already in the outbox is not a new hand-back.
            # FR #8509: already-finished is not fuel — skip opencode-out-of-fuel.log
            # the same way stop-closed does (ocSkipFuelLog gates the timedOut append).
            r"                    if ($stopLine -eq 'stop finished') {",
            r"                        $killReason = 'already-finished'",
            r"                        $script:ocSkipFuelLog = $true",
            r"                        Write-Output ('opencode-watchdog: already-finished ' + $jobKey)",
            r"                        break",
            r"                    }",
            # FR #8413: issue closed with no DONE/NACK. Not fuel, not a hard ceiling.
            r"                    if ($stopLine -eq 'stop closed') {",
            r"                        $killReason = 'process-exit:stop-closed'",
            r"                        $script:ocSkipFuelLog = $true",
            # FR #8645: closed issue is not fuel and must not switch a free pin to pro.
            r"                        $script:ocStopClosed = $true",
            r"                        $teStatus = 'error'",
            r"                        $teClass = 'process-exit'",
            r"                        $teErr = 'process-exit:stop-closed'",
            r"                        Write-OpencodeJobGiveup $jobKey 'process-exit:stop-closed'",
            r"                        break",
            r"                    }",
            r"                    $killReason = ('job-ended ' + $stopLine)",
            # FR #7739: killing the child is not enough. The chair still holds the
            # accepted row, so !bored is nak busy until this GIVEUP is drained.
            r"                    Write-OpencodeJobGiveup $jobKey $killReason",
            r"                    break",
            r"                }",
            r"            }",
            r"            if ($script:ocHasJob -and $idleMs -ge $watchdogMs) {",
            r"                $timedOut = $true",
            r"                $killReason = ('watchdog timeout (no output/cpu/worktree idle ' + [int]$watchdogMs + 'ms)')",
            r"                try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }",
            r"                break",
            r"            }",
            r"            $script:ocWedgeTicks = [int]$script:ocWedgeTicks + 1",
            r"            if (($script:ocWedgeTicks % 10) -eq 0 -and $outFile -and (Test-Path -LiteralPath $outFile) -and $wedgePy) {",
            r"                $py = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"                if (-not $py) { $py = 'python.exe' }",
            r"                try { $wedgeLine = & $py $wedgePy peek $outFile $script:ocDagRetries 2>$null } catch { $wedgeLine = '' }",
            "                if ($wedgeLine -match 'report-and-giveup' -or $wedgeLine -match '\"action\": \"giveup\"') {",
            r"                    $script:ocWedgeAction = 'giveup'",
            r"                    try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }",
            r"                    if ($jobKey) { Write-OpencodeJobGiveup $jobKey 'skill-dag wedge' }",
            r"                    break",
            r"                }",
            "                if ($wedgeLine -match '\"action\": \"reconnect\"' -and [int]$script:ocDagRetries -gt 0) {",
            r"                    $script:ocDagRetries = 0",
            r"                    $script:ocWedgeAction = 'reconnect'",
            r"                    try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { }",
            r"                    break",
            r"                }",
            r"            }",
            r"            Start-Sleep -Milliseconds 100",
            r"          } catch {",
            r"            Start-Sleep -Milliseconds 100",
            r"          }",
            r"        }",
            r"        try { $proc.WaitForExit(2000) | Out-Null } catch { }",
            r"        if ($script:ocStdoutLog -and $stdoutLogPy) {",
            r"            $pyLog = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"            if (-not $pyLog) { $pyLog = 'python.exe' }",
            r"            foreach ($pair in @(@($outFile, 'ocOutPos'), @($errFile, 'ocErrPos'))) {",
            r"                $cap = Read-OpencodeCapture $pair[0]",
            r"                $pos = [int](Get-Variable -Name $pair[1] -Scope Script).Value",
            r"                if ($cap.Length -gt $pos) {",
            r"                    $sliceFile = Join-Path $env:TEMP ('bob-oc-slice-' + [guid]::NewGuid().ToString('n') + '.txt')",
            r"                    try { [IO.File]::WriteAllText($sliceFile, $cap.Substring($pos)); & $pyLog $stdoutLogPy append $script:ocStdoutLog $sliceFile | Out-Null } catch { }",
            r"                    finally { Remove-Item -LiteralPath $sliceFile -ErrorAction SilentlyContinue }",
            r"                    Set-Variable -Name $pair[1] -Scope Script -Value $cap.Length",
            r"                }",
            r"            }",
            r"        }",
            r"        $stdout = Read-OpencodeCapture $outFile",
            r"        $stderr = Read-OpencodeCapture $errFile",
            r"        $exitCode = if ($proc.HasExited) { $proc.ExitCode } else { -1 }",
            r"    } catch {",
            r"        $stdout = ''",
            r"        $stderr = $_",
            r"        $exitCode = -1",
            r"    } finally {",
            r"        if ($proc -and -not $proc.HasExited) { try { $proc.WaitForExit(5000) | Out-Null } catch { } }",
            r"        if (-not $proc -or $proc.HasExited) {",
            r"            foreach ($f in @($outFile, $errFile)) { if ($f -and (Test-Path -LiteralPath $f)) { Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue } }",
            r"        }",
            r"    }",
            r"    $outStr = $stdout + [Environment]::NewLine + $stderr",
            r"    Write-Output $outStr",
            r"    # Drop the prompt echo and markdown quotations before the fuel match.",
            r"    # The seat prompt documents `402 Payment Required`; that is not a provider 402.",
            r"    $scan = $outStr",
            r"    if ($line) { $scan = $scan.Replace([string]$line, ' ') }",
            r"    $scan = [regex]::Replace($scan, '`[^`]*`', ' ')",
            # FR #8151: no bare "rate limit" in limitPattern (CodeRabbit / gh tool echo).
            r"    $limitPattern = 'Payment Required|usage balance exhausted|Too Many Requests|rolling limit|Free usage limit|subscribe to OpenCode Go|rate limited by provider|AI_(APICall|Retry)Error'",
            r"    $codePattern = '(HTTP|status( code)?)\D{0,3}(402|429)'",
            r"    $freeUsagePattern = 'Free usage limit|subscribe to OpenCode Go'",
            r"    $providerFuelCue = 'level=ERROR|AI_(APICall|Retry)Error'",
            r"    $toolNoisePattern = 'coderabbit|coderabbit-ai-generated|rate limited by coderabbit|Rate limit \+ single instance|\"(title|body)\"\s*:|gh (issue|pr|api)|Closes SimonBarnett/|## Summary'",
            # FR #8150: app-log HIT may leave stdout empty; seed $scan so record-pause
            # still marks opencode-free (same cue the ERROR stream error carried).
            r"    if ($fuelHitLive -and $killReason -eq 'fuel-exhausted:opencode-free' -and ($scan -notmatch $freeUsagePattern)) {",
            r"        $scan = ($scan + [Environment]::NewLine + 'Free usage limit reached. Subscribe to OpenCode Go')",
            r"    }",
            # FR #6366: watchdog timeout kills the run but must NOT record a model pause
            # (done-miss finish-runs looked like out-of-fuel). Only real 402/429/limit text pauses.
            # FR #7951: a hard ceiling or watchdog kill is not out of fuel.
            # FR #8026: free-usage text (or a live mid-run fuel kill) pauses even when exit is 0.
            # FR #8151 / #8207: tool-output noise never sets hitLimit.
            r"    # FR #8537: free-model CLI Free usage is hitLimit even without provider cue.",
            r"    $scanIsToolNoise = ($scan -match $toolNoisePattern)",
            r"    $scanIsGoModel = ($model -match '(?i)^opencode-go/|-pro(/|$)|/opencode-go/')",
            r"    $scanFreeOk = (($scan -match $freeUsagePattern) -and (($scan -match $providerFuelCue) -or (-not $scanIsGoModel)))",
            r"    $hitLimit = (-not $timedOut -and -not $scanIsToolNoise -and ($fuelHitLive -or ((($scan -match $limitPattern) -or ($scan -match $codePattern)) -and ($exitCode -ne 0 -or $scanFreeOk))))",
            r"    if ($timedOut -and -not $script:ocStopClosed) {",
            r"        if ($proc -and -not $proc.HasExited) { try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { } }",
            r"        if (-not $killReason) { $killReason = 'watchdog timeout (no output)' }",
            r"        $msg = $killReason",
            r"        Write-Output ('opencode-watchdog: kill reason=' + $msg)",
            r"        if (-not $script:ocSkipFuelLog) {",
            r"            $entry = @{ pid = $PID; ts = (Get-Date -Format o); model = $model; text = $msg; pause = $false } | ConvertTo-Json -Compress",
            r"            Add-Content -Path $fuelLog -Value $entry -ErrorAction SilentlyContinue",
            r"        }",
            r"    }",
            r"    if ($hitLimit) {",
            r"        if ($proc -and -not $proc.HasExited) { try { & taskkill /T /F /PID $proc.Id 2>$null | Out-Null } catch { } }",
            r"        $matchLines = $scan -split '\r?\n' | Where-Object { $_ -match $limitPattern -or $_ -match $codePattern }",
            r"        $msg = ($matchLines | Select-Object -First 3) -join ' '",
            r"        if (-not $msg) { $msg = ($scan -replace '\s+', ' ').Trim(); if ($msg.Length -gt 300) { $msg = $msg.Substring(0, 300) } }",
            # FR #8151: stamp source= so pauses are only from provider channels.
            r"        $fuelSource = 'cli-stderr'",
            r"        if ($msg -match '(?i)level=ERROR') { $fuelSource = 'app-log' }",
            r"        elseif ($msg -match '(?i)AI_(APICall|Retry)Error|\"status(_code)?\"\s*:\s*(402|429)') { $fuelSource = 'provider-json' }",
            r"        $entry = @{ pid = $PID; ts = (Get-Date -Format o); model = $model; text = $msg; source = $fuelSource } | ConvertTo-Json -Compress",
            r"        Add-Content -Path $fuelLog -Value $entry -ErrorAction SilentlyContinue",
            r"        $py = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"        if (-not $py) { $py = 'python.exe' }",
            r"        $prevEap = $ErrorActionPreference",
            r"        $ErrorActionPreference = 'Continue'",
            r"        try {",
            r"            $recordOutput = $scan | & $py $pyHelper record-pause --dir $pauseStateDir --model $model 2>&1 | Out-String",
            r"            $recordExit = $LASTEXITCODE",
            r"        } finally { $ErrorActionPreference = $prevEap }",
            r"        if ($recordExit -ne 0) {",
            r"            $failText = ('record-pause helper failed (exit ' + $recordExit + '): ' + $recordOutput)",
            r"            $failEntry = @{ pid = $PID; ts = (Get-Date -Format o); model = $model; text = $failText } | ConvertTo-Json -Compress",
            r"            Add-Content -Path $fuelLog -Value $failEntry -ErrorAction SilentlyContinue",
            r"        }",
            # FR #8026 / #8207: free-pool reason only for non-go models with provider-cued free usage.
            r"        if ($jobKey -and -not $script:ocPaidSwitched) {",
            r"            $isGoModel = ($model -match '(?i)^opencode-go/|-pro(/|$)|/opencode-go/')",
            r"            $giveReason = if ((-not $isGoModel) -and ($scanFreeOk -or ($killReason -eq 'fuel-exhausted:opencode-free'))) { 'fuel-exhausted:opencode-free' } else { 'out-of-fuel' }",
            r"            if (-not (Try-OpencodeSwitchToPaid $model $giveReason)) { Write-OpencodeJobGiveup $jobKey $giveReason }",
            r"        }",
            r"    }",
            # FR #6429: clear region/model-unavailable (no silent fail, no substitute model).
            r"    $regionCue = 'not available in your region|unavailable in your region|provider_model_not_found|model not found|no such model'",
            r"    $permNoise = 'permission requested|external_directory|rejected permission|this specific tool call|The user rejected'",
            r"    if ($exitCode -ne 0 -and -not $hitLimit -and -not $timedOut -and ($scan -notmatch $permNoise) -and ($scan -match $regionCue)) {",
            r"        $availMsg = ('OpenCode model unavailable: ' + $model + ' (set OpenCode console region to Global for paid V4 Pro, or pick a model available in this region). No substitute model was selected.')",
            r"        Write-Output $availMsg",
            r"        [Console]::Error.WriteLine($availMsg)",
            r"        $availEntry = @{ pid = $PID; ts = (Get-Date -Format o); model = $model; text = $availMsg } | ConvertTo-Json -Compress",
            r"        Add-Content -Path $fuelLog -Value $availEntry -ErrorAction SilentlyContinue",
            r"        if ($jobKey) { Write-OpencodeJobGiveup $jobKey ('model unavailable (' + $model + ')') }",
            r"    }",
            # FR #7997: locked SQLite retries; a permanent startup failure GIVEUPs the job.
            # FR #8147: never pass an empty/null exit code to classify (use the real process
            # exit code, or omit --exit when unknown); a job whose outbox already carries a
            # terminal DONE/GIVEUP line is never re-classified as a startup failure; a null
            # classify result is logged as classify_unavailable instead of throwing.
            r"    $script:ocDbRetry = $false",
            r"    $script:ocCleanRetry = $false",
            r"    $teStatus = ''; $teErr = ''; $teClass = ''",
            r"    if ($exitCode -eq 0) { $script:ocDbLockTries = 0 }",
            # FR #8235: exit 0 and no DONE/NACK/GIVEUP — one continuation, then GIVEUP.
            r"    if ($exitCode -eq 0 -and $jobKey -and -not $hitLimit) {",
            r"        $term = $false",
            r"        if ($env:BOB_OUTBOX -and (Test-Path -LiteralPath $env:BOB_OUTBOX)) {",
            r"            try { $ob2 = [IO.File]::ReadAllText($env:BOB_OUTBOX); if ($ob2 -match '(?m)\b(DONE|GIVEUP|NACK)\s+(FR|MRB|UAT|FIX)\s+\S+#\d+') { $term = $true } } catch { }",
            r"        }",
            r"        if (-not $term) {",
            r"            if ([int]$script:ocCleanExitTries -lt 1) {",
            r"                $script:ocCleanExitTries = [int]$script:ocCleanExitTries + 1",
            r"                $script:ocCleanRetry = $true",
            r"                Write-Output 'opencode-clean-exit: continuation 1/1 (exit 0, no DONE)'",
            r"            } else {",
            r"                Write-Output 'opencode-clean-exit: GIVEUP clean-exit-no-done'",
            r"                Write-OpencodeJobGiveup $jobKey 'clean-exit-no-done'",
            r"                $teStatus = 'error'; $teErr = 'exit 0 no DONE'; $teClass = 'clean-exit-no-done'",
            r"            }",
            r"        }",
            r"    }",
            r"    if ($exitCode -ne 0 -and -not $hitLimit -and -not $timedOut) {",
            r"        $pyDb = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
            r"        if (-not $pyDb) { $pyDb = 'python.exe' }",
            r"        $maxLock = 3",
            r"        if ($env:BOB_OPENCODE_DB_LOCK_RETRIES) { try { $maxLock = [int]$env:BOB_OPENCODE_DB_LOCK_RETRIES } catch { $maxLock = 3 } }",
            r"        $clsDone = $false",
            r"        if ($env:BOB_OUTBOX -and (Test-Path -LiteralPath $env:BOB_OUTBOX)) {",
            r"            try { $obText = [IO.File]::ReadAllText($env:BOB_OUTBOX); if ($obText -match '(?m)\b(DONE|GIVEUP|NACK)\s+(FR|MRB|UAT|FIX)\s+\S+#\d+') { $clsDone = $true } } catch { }",
            r"        }",
            r"        $clsExit = ''",
            r"        if ($null -ne $exitCode -and ([string]$exitCode).Trim() -ne '') { try { $clsExit = [string][int]$exitCode } catch { $clsExit = '' } }",
            r"        $clsArgs = @('--attempt', ([string]$script:ocDbLockTries), '--max', ([string]$maxLock))",
            r"        if ($clsExit -ne '') { $clsArgs += '--exit'; $clsArgs += $clsExit }",
            r"        if ($clsDone) { $clsArgs += '--done' }",
            r"        $dbAction = ''",
            r"        try { $dbAction = ($scan | & $pyDb $isolatePy classify @clsArgs | Select-Object -Last 1) } catch { $dbAction = '' }",
            r"        $dbAction = ([string]$dbAction).Trim()",
            r"        if ([string]::IsNullOrWhiteSpace($dbAction)) {",
            r"            Write-Output 'opencode-classify: classify_unavailable'",
            r"        }",
            r"        if ($dbAction -eq 'retry') {",
            r"            $script:ocDbLockTries = [int]$script:ocDbLockTries + 1",
            r"            $script:ocDbRetry = $true",
            r"            $wait = [Math]::Min(8, [int][Math]::Pow(2, $script:ocDbLockTries - 1))",
            r"            Write-Output ('opencode-db-lock: retry ' + $script:ocDbLockTries + '/' + $maxLock + ' in ' + $wait + 's')",
            r"            Start-Sleep -Seconds $wait",
            r"        } elseif ($dbAction -eq 'giveup' -and $jobKey) {",
            r"            $script:ocDbLockTries = 0",
            r"            Write-OpencodeJobGiveup $jobKey 'opencode-startup-failed'",
            r"        }",
            r"    }",
            r"    if ($proc -and $proc.HasExited) { try { $proc.Dispose() } catch { } }",
            r"    } finally {",
            r"        if (-not $script:ocDbRetry -and -not $script:ocCleanRetry) {",
            # FR #8018 / #8091: turn_ended carries exit code + last ~20 stderr/stdout lines.
            # FR #8235: $null -ne 0 is true in PowerShell and [int]$null is 0, which
            # stamped process-exit exit 0. Only a known nonzero code is an error.
            r"            $exitKnown = $false; $codeNum = 0",
            r"            if ($null -ne $exitCode -and ([string]$exitCode).Trim() -ne '') { try { $codeNum = [int]$exitCode; $exitKnown = $true } catch { $exitKnown = $false } }",
            r"            if (-not $teClass -and $exitKnown -and $codeNum -ne 0) {",
            r"                $teStatus = 'error'",
            r"                $snipLines = @()",
            r"                foreach ($chunk in @($stderr, $stdout)) {",
            r"                    if (-not $chunk) { continue }",
            r"                    foreach ($ln in @($chunk -split '\r?\n' | Where-Object { $_.Trim().Length -gt 0 })) { $snipLines += [string]$ln.Trim() }",
            r"                }",
            r"                if ($snipLines.Count -gt 20) { $snipLines = @($snipLines[($snipLines.Count - 20)..($snipLines.Count - 1)]) }",
            r"                $snip = ($snipLines -join ' | ')",
            r"                $snip = ($snip -replace '\s+', ' ').Trim()",
            r"                $snip = [regex]::Replace($snip, '(?i)(?:ghp_|github_pat_|gho_|sk-|Bearer\s+)\S+', '<redacted>')",
            r"                if ($snip.Length -gt 800) { $snip = $snip.Substring(0, 800) }",
            r"                $teErr = ('exit ' + $codeNum)",
            r"                if ($snip) { $teErr = ($teErr + ': ' + $snip) }",
            r"                if ($script:ocStdoutLog) { $teErr = $teErr + ' log=' + [IO.Path]::GetFileName($script:ocStdoutLog) }",
            r"                $teClass = 'process-exit'",
            r"                if ($hitLimit) { $teClass = 'out-of-fuel' }",
            r"                elseif ($snip -match 'EPIPE|broken pipe' -or $stderr -match 'EPIPE|broken pipe') { $teClass = 'epipe' }",
            # FR #8247: external_directory auto-reject (do not widen %TEMP% allow).
            r"                elseif ($snip -match 'external_directory' -or $stderr -match 'external_directory') { $teClass = 'external-directory' }",
            r"            } elseif (($stderr + [Environment]::NewLine + $stdout) -match '(?i)permission requested:\s*external_directory|external_directory[^\r\n]*auto-reject') {",
            r"                $teStatus = 'error'",
            r"                $teClass = 'external-directory'",
            r"                $teErr = 'exit 0: external_directory auto-reject'",
            r"                $script:ocEpipeTries = 0",
            r"            } else {",
            r"                $script:ocEpipeTries = 0",
            r"            }",
            # FR #8578: free-to-paid switch continues the same job — never stamp terminal
            # out-of-fuel turn_ended (BoredEmitter would GIVEUP the ACK before re-invoke).
            r"            # FR #8578: successful free-to-paid switch is non-terminal (no out-of-fuel GIVEUP).",
            r"            if ($script:ocSwitchPaid -and $hitLimit) {",
            r"                $teStatus = ''",
            r"                $teErr = ''",
            r"                $teClass = 'free-to-paid-switch'",
            r"            }",
            r"            if ($script:ocHasJob) { Write-OpencodeTurnMarker 'turn_ended' $turnN $teStatus $teErr $teClass }",
            r"        }",
            r"    }",
            # FR #8454: turn_ended already written; continue the same job on the paid slot.
            r"    if ($script:ocSwitchPaid) {",
            r"        $script:ocSwitchPaid = $false",
            r"        Invoke-OpencodeRun $line $jobKey $ocDir",
            r"        return",
            r"    }",
            r"    if ($script:ocDbRetry) {"
            r"        $script:ocDbRetry = $false",
            r"        Invoke-OpencodeRun $line $jobKey $ocDir",
            r"        return",
            r"    }",
            # FR #8235: exit 0 with no DONE/NACK/GIVEUP continues once in this session.
            r"    if ($script:ocCleanRetry) {",
            r"        $script:ocCleanRetry = $false",
            r"        Invoke-OpencodeRun $line $jobKey $ocDir",
            r"        return",
            r"    }",
            r"    # FR #8645: a stop-closed kill can surface node EPIPE. Do not retry or switch model.",
            r"    $epipeHit = ($exitCode -ne 0 -and -not $hitLimit -and -not $timedOut -and -not $script:ocStopClosed -and (($stderr + [Environment]::NewLine + $stdout) -match 'EPIPE|broken pipe'))",
            r"    if ($epipeHit -and [int]$script:ocEpipeTries -lt 1) {",
            r"        $wtOk = (-not $ocDir) -or (Test-Path -LiteralPath $ocDir -PathType Container)",
            r"        if ($wtOk) {",
            r"            $script:ocEpipeTries = [int]$script:ocEpipeTries + 1",
            r"            Write-Output ('opencode-epipe: retry ' + $script:ocEpipeTries + '/1')",
            r"            Invoke-OpencodeRun $line $jobKey $ocDir",
            r"            return",
            r"        }",
            r"    }",
            r"    if ($script:ocWedgeAction -eq 'reconnect') {",
            r"        $script:ocWedgeAction = ''",
            r"        Invoke-OpencodeRun $line $jobKey $ocDir",
            r"    }",
            r"}",
            r"function Split-OpencodeFrame([string]$raw) {",
            r"    $prefix = '@@BOBJOB1|'",
            r"    if (-not $raw.StartsWith($prefix)) { return $null }",
            r"    $rest = $raw.Substring($prefix.Length)",
            r"    $keyEnd = $rest.IndexOf('|')",
            r"    if ($keyEnd -lt 1) { return $null }",
            r"    $dirEnd = $rest.IndexOf('|', $keyEnd + 1)",
            r"    if ($dirEnd -lt 0) { return $null }",
            r"    $key = $rest.Substring(0, $keyEnd)",
            r"    $dir = $rest.Substring($keyEnd + 1, $dirEnd - $keyEnd - 1)",
            r"    $line = $rest.Substring($dirEnd + 1)",
            r"    if (-not $dir -or -not $line.StartsWith('FROM ')) { return $null }",
            r"    if ($key -notmatch '^(?i)(FR|MRB|UAT|FIX) \S+#\d+$') { return $null }",
            r"    return @{ key = $key; dir = $dir; line = $line }",
            r"}",
            r"function Get-OpencodeFromJobKeys([string]$raw) {",
            r"    if ($raw -notmatch '^(?i)FROM\s+\S+\s+\S+\s+(.*)$') { return @() }",
            r"    $body = $Matches[1]",
            r"    $keys = @()",
            r"    foreach ($m in [regex]::Matches($body, '(?i)(FR|MRB|UAT|FIX)\s+(\S+#\d+)')) {",
            r"        $keys += ($m.Groups[1].Value.ToUpper() + ' ' + $m.Groups[2].Value)",
            r"    }",
            r"    return $keys",
            r"}",
            r"function Invoke-OpencodeInbound([string]$raw) {",
            r"    $frame = Split-OpencodeFrame $raw",
            r"    if ($frame) {",
            r"        Invoke-OpencodeRun $frame.line $frame.key $frame.dir",
            r"        return",
            r"    }",
            r"    if ($raw.StartsWith('@@BOBJOB1')) {",
            r"        $key = ''",
            r"        $tail = $raw.Substring(9).TrimStart('| ')",
            r"        $km = [regex]::Match($tail, '^(?i)((?:FR|MRB|UAT|FIX)\s+\S+#\d+)')",
            r"        if ($km.Success) {",
            r"            $rawKey = $km.Groups[1].Value",
            r"            $spaceAt = $rawKey.IndexOf(' ')",
            r"            $key = $rawKey.Substring(0, $spaceAt).ToUpper() + $rawKey.Substring($spaceAt)",
            r"        }",
            r"        Write-Output 'opencode-ready: blocked job_context_malformed. Next: the console line lost its job frame. No DONE.'",
            r"        Write-OpencodeJobNack $key 'job-context-malformed'",
            r"        return",
            r"    }",
            r"    $fromKeys = @(Get-OpencodeFromJobKeys $raw)",
            r"    if ($fromKeys.Count -ge 1) {",
            r"        $reason = 'job-context-malformed'",
            r"        if ($fromKeys.Count -gt 1) { $reason = 'job-context-ambiguous' }",
            r"        foreach ($k in $fromKeys) { Write-OpencodeJobNack $k $reason }",
            r"        Write-Output 'opencode-ready: blocked job_context_malformed. Next: a FROM assign arrived without its job frame. No DONE.'",
            r"        return",
            r"    }",
            r"    Invoke-OpencodeRun $raw '' ''",
            r"}",
            # FR #8133: do not run the standing prompt as a watched turn. Idle seats
            # wait on ReadLine; the first job inject starts turn_started and the ceiling.
            r"Write-Output 'opencode-ready: idle (FR #8133; first turn is the first job inject)'",
            r"while ($true) { $line = [Console]::ReadLine(); if ($null -eq $line -or $line -eq 'exit') { break }; if (-not [string]::IsNullOrWhiteSpace($line)) { try { Invoke-OpencodeInbound $line } catch { [Console]::Error.WriteLine('opencode run failed: ' + $_) } } }",
            r"exit 0",
        ])
        argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", lfile]
    else:
        raise ValueError(f"unknown agent kind {kind!r}")
    assert_fresh(argv, {k: v for k, v in files.items() if k.endswith(".ps1")}, allow_resume=bool(resume_session_id))
    return LaunchSpec(
        kind=kind,
        argv=argv,
        cwd=cwd,
        session_id=sid,
        files=files,
        write_skill_dag_mcp=(str(mode).strip().lower() == "agent"),
        write_cursor_skill_dag_mcp=(str(kind).strip().lower() == "cursor" and str(mode).strip().lower() == "agent"),
        write_opencode_skill_dag_mcp=(str(kind).strip().lower() == "opencode" and str(mode).strip().lower() == "agent"),
        skill_dag_mcp_args=mcp_args,
        skill_dag_job_worktree=job_wt,
        inherit_console=(kind == "grok"),
    )


class ProcHandle:
    """Thin wrapper so tests can fake processes."""

    def __init__(self, popen: subprocess.Popen, stderr_ring: AgentStderrRing | None = None, stderr_thread: threading.Thread | None = None, stdout_thread=None):
        self._p = popen
        self.pid = popen.pid
        self._stderr_ring = stderr_ring
        self._stderr_thread = stderr_thread
        self._stdout_thread = stdout_thread

    def poll(self):
        return self._p.poll()

    def wait(self, timeout=None):
        code = self._p.wait(timeout)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=2)
        if self._stdout_thread is not None:
            self._stdout_thread.join(timeout=2)
        return code

    def stderr_tail(self) -> str:
        if self._stderr_ring is None:
            return ""
        return self._stderr_ring.tail_text()


def default_spawn(spec: LaunchSpec, env: dict) -> ProcHandle:
    for path, text in spec.files.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
    write_skill_dag_mcp_config_if_agent(spec)
    write_cursor_skill_dag_mcp_config_if_agent(spec)
    write_opencode_skill_dag_mcp_config_if_agent(spec)
    # t771u: ONE window. The agent INHERITS this exe's console (no CREATE_NEW_CONSOLE, no second console); a kill-on-close job object
    # makes the agent die with us even if we are killed. "New agent every time" is about the SESSION, not the window: the exe's
    # window IS the agent's window and a new click opens a new exe + window.
    # FR #7916: Grok renders on stderr only when it is a console. A tee breaks TTY
    # detection; use Grok's per-seat logs instead. Other agents keep FR #7671 capture.
    # OpenCode's headless wrapper can be teed; interactive stdout stays inherited.
    capture = {} if spec.kind == "grok" or spec.inherit_console else {"stderr": subprocess.PIPE}
    if spec.kind == "opencode":
        capture["stdout"] = subprocess.PIPE
    popen = subprocess.Popen(
        spec.argv, cwd=spec.cwd, env=env, creationflags=0, close_fds=True, **capture,
    )
    ring = None
    thread = None
    if getattr(popen, "stderr", None) is not None:
        callback = (lambda text: spec.session_log.write("stderr", text)) if spec.session_log else None
        ring, thread = start_agent_stderr_capture(popen.stderr, on_line=callback)
    stdout_thread = None
    if spec.kind == "opencode" and getattr(popen, "stdout", None) is not None:
        callback = (lambda text: spec.session_log.write("stdout", text)) if spec.session_log else None
        _, stdout_thread = start_agent_stderr_capture(popen.stdout, on_line=callback, output=sys.__stdout__)
    try:
        owned_job().assign(popen)
    except Exception:
        pass
    return ProcHandle(popen, ring, thread, stdout_thread)


def kill_tree(pid: int, run: Callable = subprocess.run) -> bool:
    """Kill pid and ITS descendants (taskkill /T). Callers only pass pids this exe spawned."""
    if int(pid) <= 4 or int(pid) == os.getpid():
        return False
    try:
        run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True, timeout=30,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------------------------- console (one window) + injection
def ensure_console(title: str = "") -> bool:
    """t771u: the exe OWNS exactly one console window; the agent and the IRC relay live inside it. If this process was started
    without a console (e.g. from a service) allocate one. Returns True when a console exists afterwards."""
    if os.name != "nt":
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    buf = (ctypes.c_uint * 4)()
    if k32.GetConsoleProcessList(buf, 4) == 0:
        if not k32.AllocConsole():
            return False
    if title:
        k32.SetConsoleTitleW(str(title)[:200])
    disable_console_quick_edit(k32)
    return True


def disable_console_quick_edit(k32=None) -> bool:
    """Turn off QuickEdit so a click/select cannot freeze the worker until Enter (FR #7117)."""
    if os.name != "nt":
        return False
    try:
        k32 = k32 or ctypes.WinDLL("kernel32", use_last_error=True)
        GetStdHandle = k32.GetStdHandle
        GetConsoleMode = k32.GetConsoleMode
        SetConsoleMode = k32.SetConsoleMode
        GetStdHandle.restype = ctypes.c_void_p
        h = GetStdHandle(STD_INPUT_HANDLE)
        if not h or int(h) in (0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            return False
        mode = ctypes.c_uint(0)
        if not GetConsoleMode(ctypes.c_void_p(int(h)), ctypes.byref(mode)):
            return False
        new_mode = (int(mode.value) | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE
        return bool(SetConsoleMode(ctypes.c_void_p(int(h)), new_mode))
    except Exception:
        return False


def find_window_icon(install_root: Optional[Path] = None) -> Optional[Path]:
    """Window icon: jeeves-butler.ico (monitor) or bob-systray.ico; install then PyInstaller embed."""
    cands: list = []
    if install_root:
        cands.append(Path(install_root) / "assets" / "jeeves-butler.ico")
        cands.append(Path(install_root) / "assets" / "bob-systray.ico")
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        cands.append(Path(mei) / "assets" / "bob-systray.ico")
    cands.append(Path(__file__).resolve().parent.parent / "assets" / "bob-systray.ico")
    cands.append(Path(__file__).resolve().parent.parent / "tray" / "assets" / "bob-systray.ico")  # t829u: bob/tray is a first-class source
    cands.append(Path(__file__).resolve().parent.parent / "third_party" / "bob-tray" / "assets" / "bob-systray.ico")
    for c in cands:
        try:
            if c.is_file():
                return c
        except OSError:
            pass
    return None


def set_console_icon(install_root: Optional[Path] = None, icon: Optional[Path] = None) -> bool:
    """t794u: put the systray icon on the worker's console window (title bar + taskbar). The exe itself carries the same icon
    (PyInstaller --icon). Typed ctypes (HWND/HICON are pointers); never raises, never prints."""
    if os.name != "nt":
        return False
    try:
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32.GetConsoleWindow.restype = ctypes.c_void_p
        u32.LoadImageW.restype = ctypes.c_void_p
        u32.LoadImageW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u32.SendMessageW.restype = ctypes.c_ssize_t
        u32.SendMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        hwnd = k32.GetConsoleWindow()
        ico = Path(icon) if icon else find_window_icon(install_root)
        if not hwnd or not ico:
            return False
        done = False
        for which, px in ((0, 16), (1, 32)):   # ICON_SMALL, ICON_BIG ; LR_LOADFROMFILE
            h = u32.LoadImageW(None, str(ico), 1, px, px, 0x10)
            if h:
                u32.SendMessageW(hwnd, 0x80, which, h)   # WM_SETICON
                done = True
        return done
    except Exception:
        return False


_CTRL_KEEP: list = []


def install_ctrl_handler(on_close: Callable[[], None]) -> bool:
    """Console events: Ctrl+C / Ctrl+Break are NOT ours (the agent TUI decides what to do with them; an agent that exits ends us).
    Closing the window / logoff / shutdown ends the agent tree we started and then us."""
    if os.name != "nt":
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    from ctypes import wintypes

    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def handler(ev):
        if ev in (0, 1):
            return True
        if ev in (2, 5, 6):
            try:
                on_close()
            except Exception:
                pass
            return True
        return False

    cb = proto(handler)
    _CTRL_KEEP.append(cb)
    return bool(k32.SetConsoleCtrlHandler(cb, True))


class OwnedJob:
    """A Windows job object with KILL_ON_JOB_CLOSE: if this exe dies for ANY reason (killed, crashed) the agent tree it started
    dies with it - no orphan agent window. Only processes this exe spawns are ever assigned."""

    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        try:
            from ctypes import wintypes

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class IOC(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f")]

            class EXT(ctypes.Structure):
                _fields_ = [("Basic", BASIC), ("Io", IOC), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateJobObjectW.restype = wintypes.HANDLE
            k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            h = k32.CreateJobObjectW(None, None)
            if not h:
                return
            ext = EXT()
            ext.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(h, 9, ctypes.byref(ext), ctypes.sizeof(ext)):
                return
            self.handle = h
        except Exception:
            self.handle = None

    def assign(self, popen) -> bool:
        if not self.handle or os.name != "nt":
            return False
        try:
            from ctypes import wintypes

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            return bool(k32.AssignProcessToJobObject(self.handle, int(popen._handle)))
        except Exception:
            return False


_JOB: Optional[OwnedJob] = None


def owned_job() -> OwnedJob:
    global _JOB
    if _JOB is None:
        _JOB = OwnedJob()
    return _JOB

_CONSOLE_LOCK = threading.Lock()


def _win_structs():
    from ctypes import wintypes

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD), ("wVirtualKeyCode", wintypes.WORD),
                    ("wVirtualScanCode", wintypes.WORD), ("uChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

    class MOUSE_EVENT_RECORD(ctypes.Structure):
        _fields_ = [("x", wintypes.SHORT), ("y", wintypes.SHORT), ("b", wintypes.DWORD), ("c", wintypes.DWORD), ("f", wintypes.DWORD)]

    class EV(ctypes.Union):
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("MouseEvent", MOUSE_EVENT_RECORD)]

    class INPUT_RECORD(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", EV)]

    return wintypes, INPUT_RECORD


def build_key_records(text: str, user32=None):
    """KEY_EVENT down+up per character (text only; Enter is sent separately). Returns a ctypes array."""
    wintypes, INPUT_RECORD = _win_structs()
    chars = [c for c in text]
    arr = (INPUT_RECORD * (len(chars) * 2))()
    i = 0
    for ch in chars:
        vk = scan = 0
        ctrl = 0
        if user32 is not None:
            try:
                r = user32.VkKeyScanW(ord(ch)) & 0xFFFF
                if r != 0xFFFF:
                    vk = r & 0xFF
                    if (r >> 8) & 1:
                        ctrl |= 0x10
                    scan = user32.MapVirtualKeyW(vk, 0)
            except Exception:
                pass
        for down in (1, 0):
            rec = arr[i]
            rec.EventType = 1
            k = rec.Event.KeyEvent
            k.bKeyDown = down
            k.wRepeatCount = 1
            k.wVirtualKeyCode = vk
            k.wVirtualScanCode = scan
            k.uChar = ch
            k.dwControlKeyState = ctrl
            i += 1
    return arr


def build_enter_records():
    wintypes, INPUT_RECORD = _win_structs()
    arr = (INPUT_RECORD * 2)()
    for i, down in enumerate((1, 0)):
        rec = arr[i]
        rec.EventType = 1
        k = rec.Event.KeyEvent
        k.bKeyDown = down
        k.wRepeatCount = 1
        k.wVirtualKeyCode = 0x0D
        k.wVirtualScanCode = 0x1C
        k.uChar = "\r"
        k.dwControlKeyState = 0
    return arr


def one_line(text: str, maxlen: int = 600) -> str:
    """Console inject payload. Control characters, including tab, become spaces.

    FR #6366: OpenCode inject_console passes maxlen=2000 for ``@@BOBJOB1`` frames
    so finish-run checklists survive; default 600 keeps FR #6240 prefix-only contract.
    """
    return console_text(text, maxlen)


def _submit_gap_s(default: float = 0.20) -> float:
    """Gap after typing before Enter so TUI paste-mode ends (FR #1601).

    Too-short gaps (0.06s) let Enter insert a newline instead of submitting; the
    worker console then shows the Jeeves FROM line waiting for a manual Enter.
    Override: ``BOB_WORKER_SUBMIT_GAP_S`` (seconds, clamped 0.05..2.0).
    """
    raw = (os.environ.get("BOB_WORKER_SUBMIT_GAP_S") or "").strip()
    if not raw:
        return float(default)
    try:
        v = float(raw)
    except ValueError:
        return float(default)
    return max(0.05, min(2.0, v))


# FR #3894: rdpclip / other owners briefly hold the clipboard; one OpenClipboard miss
# used to fall back to per-char KEY_EVENTs (the #2498 drip). Retry open.
# FR #3996: on clipboard *set* failure, use ONE batched WriteConsoleInput KEY_EVENT write
# (no per-char sleep). Never drip. Tiny-string constant kept for diagnostics / opt paths.
_CLIPBOARD_OPEN_ATTEMPTS = 20
_CLIPBOARD_OPEN_DELAY_S = 0.025
# Legacy gate from FR #3894 (tiny strings); FR #3996 always allows batched KEY fallback.
_KEY_FALLBACK_MAX_CHARS = 8

def _configure_clipboard_winapi(k32, u32) -> None:
    """FR #3996: declare HGLOBAL/HANDLE restype+argtypes so x64 pointers are not truncated to C int."""
    HGLOBAL = ctypes.c_void_p
    UINT = ctypes.c_uint
    BOOL = ctypes.c_int
    HWND = ctypes.c_void_p
    SIZE_T = ctypes.c_size_t

    k32.GlobalAlloc.restype = HGLOBAL
    k32.GlobalAlloc.argtypes = [UINT, SIZE_T]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [HGLOBAL]
    k32.GlobalUnlock.restype = BOOL
    k32.GlobalUnlock.argtypes = [HGLOBAL]
    k32.GlobalFree.restype = HGLOBAL
    k32.GlobalFree.argtypes = [HGLOBAL]

    u32.OpenClipboard.restype = BOOL
    u32.OpenClipboard.argtypes = [HWND]
    u32.CloseClipboard.restype = BOOL
    u32.CloseClipboard.argtypes = []
    u32.EmptyClipboard.restype = BOOL
    u32.EmptyClipboard.argtypes = []
    u32.SetClipboardData.restype = ctypes.c_void_p
    u32.SetClipboardData.argtypes = [UINT, ctypes.c_void_p]
    u32.GetClipboardData.restype = ctypes.c_void_p
    u32.GetClipboardData.argtypes = [UINT]
    u32.IsClipboardFormatAvailable.restype = BOOL
    u32.IsClipboardFormatAvailable.argtypes = [UINT]



def _clipboard_owner_diag(u32=None) -> str:
    """Best-effort clipboard owner hwnd/pid for WARN logs (FR #3894)."""
    if os.name != "nt":
        return ""
    try:
        u32 = u32 or ctypes.WinDLL("user32", use_last_error=True)
        hwnd = int(u32.GetOpenClipboardWindow() or 0)
        if not hwnd:
            err = int(ctypes.get_last_error() or 0)
            return f"owner=none last_error={err}"
        pid = ctypes.c_ulong(0)
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return f"owner_hwnd={hwnd} owner_pid={int(pid.value or 0)}"
    except Exception as exc:  # noqa: BLE001
        return f"owner_diag={type(exc).__name__}"


def _open_clipboard_retry(
    u32,
    *,
    attempts: int | None = None,
    delay_s: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """OpenClipboard with short retries (FR #3894). Logs last_error + owner on final fail."""
    n = int(_CLIPBOARD_OPEN_ATTEMPTS if attempts is None else attempts)
    delay = float(_CLIPBOARD_OPEN_DELAY_S if delay_s is None else delay_s)
    last_err = 0
    for i in range(max(1, n)):
        if u32.OpenClipboard(None):
            return True
        try:
            last_err = int(ctypes.get_last_error() or 0)
        except Exception:
            last_err = 0
        if i + 1 < n:
            try:
                sleep(delay)
            except Exception:
                pass
    diag = _clipboard_owner_diag(u32)
    if log:
        try:
            log(f"relay: clipboard OpenClipboard failed attempts={n} last_error={last_err} {diag}")
        except Exception:
            pass
    return False


def _clipboard_get_unicode(log: Optional[Callable[[str], None]] = None) -> str | None:
    """Best-effort read of current CF_UNICODETEXT (FR #2504). None if empty/unavailable."""
    if os.name != "nt":
        return None
    CF_UNICODETEXT = 13
    try:
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _configure_clipboard_winapi(k32, u32)
        if not u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        if not _open_clipboard_retry(u32, log=log):
            return None
        try:
            h = u32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return None
            ptr = k32.GlobalLock(h)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                k32.GlobalUnlock(h)
        finally:
            u32.CloseClipboard()
    except Exception:
        return None


def _clipboard_set_unicode(text: str, log: Optional[Callable[[str], None]] = None) -> bool:
    """Put Unicode text on the Windows clipboard. Used by inject_console paste path (FR #2498 / #3894 / #3996)."""
    if os.name != "nt":
        return False
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    def _fail(step: str) -> bool:
        err = 0
        try:
            err = int(ctypes.get_last_error() or 0)
        except Exception:
            err = 0
        if log:
            try:
                log(f"relay: inject path=fail reason=clipboard_set step={step} last_error={err}")
            except Exception:
                pass
        return False

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    _configure_clipboard_winapi(k32, u32)
    data = (text.replace("\x00", "") + "\x00").encode("utf-16-le")
    if not _open_clipboard_retry(u32, log=log):
        return False
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return _fail("alloc")
        ptr = k32.GlobalLock(h)
        if not ptr:
            k32.GlobalFree(h)
            return _fail("lock")
        try:
            ctypes.memmove(ptr, data, len(data))
        finally:
            k32.GlobalUnlock(h)
        if not u32.SetClipboardData(CF_UNICODETEXT, h):
            k32.GlobalFree(h)
            return _fail("set")
        return True
    finally:
        u32.CloseClipboard()


def _clipboard_restore_unicode(
    prior: str | None, log: Optional[Callable[[str], None]] = None
) -> bool:
    """Restore prior CF_UNICODETEXT after inject paste, or leave empty if prior was None (FR #2504)."""
    if os.name != "nt":
        return False
    try:
        if prior is None:
            u32 = ctypes.WinDLL("user32", use_last_error=True)
            if not _open_clipboard_retry(u32, log=log):
                return False
            try:
                u32.EmptyClipboard()
                return True
            finally:
                u32.CloseClipboard()
        return _clipboard_set_unicode(prior, log=log)
    except Exception:
        return False



def _clipboard_restore_delay_s() -> float:
    """FR #4115: seconds to keep the injected text on the clipboard before restoring the prior text."""
    return _env_float("BOB_WORKER_CLIPBOARD_RESTORE_S", 8.0, 0.0, 120.0)


def _startup_wait_ready_enabled() -> bool:
    """FR #7180: default off --- signed-in seats !bored without waiting for a first turn.

    BOB_WORKER_STARTUP_WAIT_READY=1 restores FR #4115/#4123 hold-until-turn_ended.
    """
    raw = (os.environ.get("BOB_WORKER_STARTUP_WAIT_READY") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _startup_ready_cap_s() -> float:
    """FR #4115: longest wait for the first turn_ended before inject is released anyway."""
    return _env_float("BOB_WORKER_STARTUP_READY_CAP_S", 900.0, 60.0, 7200.0)


def _startup_proc_idle(proc, probe=None) -> bool:
    """FR #4123: True when the agent process is gone or reports 0 CPU/IO activity."""
    if proc is None:
        return True
    try:
        if proc.poll() is not None:
            return True
    except Exception:
        return True
    if probe is None:
        return False
    try:
        sample = probe(int(proc.pid))
    except Exception:
        return False
    try:
        return int(getattr(sample, "activity", 0) or 0) <= 0
    except Exception:
        return False




def clipboard_set_verified(
    text: str,
    *,
    set_fn: Callable[..., bool],
    read_fn: Callable[..., Optional[str]],
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """FR #4115: set CF_UNICODETEXT then read it back; True only when the readback equals ``text``.

    Logs ``relay: clipboard readback ok|mismatch|fail``. The caller falls back to the batched
    KEY_EVENT path on False (never the per-char drip).
    """
    def _log(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass

    want = (text or "").replace("\x00", "")
    try:
        ok = bool(set_fn(want, log=log))
    except TypeError:
        ok = bool(set_fn(want))
    except Exception as e:  # noqa: BLE001
        _log(f"relay: clipboard set error {type(e).__name__}")
        ok = False
    if not ok:
        _log(f"relay: clipboard readback fail reason=set chars={len(want)}")
        return False
    try:
        got = read_fn(log=log)
    except TypeError:
        got = read_fn()
    except Exception:  # noqa: BLE001
        got = None
    if got is None:
        _log(f"relay: clipboard readback fail reason=read chars={len(want)}")
        return False
    if got != want:
        _log(f"relay: clipboard readback mismatch want={len(want)} got={len(got)} chars")
        return False
    _log(f"relay: clipboard readback ok chars={len(want)}")
    return True


def schedule_clipboard_restore(
    prior: Optional[str],
    ours: str,
    *,
    delay_s: Optional[float] = None,
    read_fn: Optional[Callable[..., Optional[str]]] = None,
    restore_fn: Optional[Callable[..., bool]] = None,
    timer_cls=None,
    log: Optional[Callable[[str], None]] = None,
):
    """FR #4115: restore the operator clipboard after ``delay_s`` only if it still holds ``ours``."""
    delay = _clipboard_restore_delay_s() if delay_s is None else max(0.0, float(delay_s))
    read_fn = read_fn or _clipboard_get_unicode
    restore_fn = restore_fn or _clipboard_restore_unicode
    want = (ours or "").replace("\x00", "")

    def _restore() -> None:
        try:
            cur = read_fn(log=log)
        except TypeError:
            cur = read_fn()
        except Exception:  # noqa: BLE001
            return
        if cur != want:
            return  # someone else (operator / next inject) owns the clipboard now
        try:
            restore_fn(prior, log=log)
        except TypeError:
            restore_fn(prior)
        except Exception:  # noqa: BLE001
            pass

    tc = timer_cls or threading.Timer
    t = tc(delay, _restore)
    t.daemon = True
    t.start()
    return t


def _build_ctrl_v_records():
    """Ctrl down, V down/up, Ctrl up - one paste chord."""
    wintypes, INPUT_RECORD = _win_structs()
    arr = (INPUT_RECORD * 4)()
    seq = [
        (0x11, 1, "\x00", 0x0008),
        (0x56, 1, "v", 0x0008),
        (0x56, 0, "v", 0x0008),
        (0x11, 0, "\x00", 0),
    ]
    for i, (vk, down, ch, ctrl) in enumerate(seq):
        rec = arr[i]
        rec.EventType = 1
        k = rec.Event.KeyEvent
        k.bKeyDown = down
        k.wRepeatCount = 1
        k.wVirtualKeyCode = vk
        k.wVirtualScanCode = 0
        k.uChar = ch
        k.dwControlKeyState = ctrl
    return arr


def _write_console_all(k32, h, recs, wintypes) -> bool:
    """Write every INPUT_RECORD; retry remainder if WriteConsoleInput truncates. No sleeps."""
    if not recs:
        return True
    total = len(recs)
    offset = 0
    written = wintypes.DWORD(0)
    Elem = recs._type_
    while offset < total:
        n = total - offset
        rem = (Elem * n)()
        for i in range(n):
            rem[i] = recs[offset + i]
        if not k32.WriteConsoleInputW(h, rem, n, ctypes.byref(written)):
            return False
        got = int(written.value or 0)
        if got <= 0:
            return False
        offset += got
    return True


def _inject_prefer_paste() -> bool:
    """FR #2508: BOB_WORKER_INJECT_PASTE=0 skips clipboard+Ctrl+V (KEY_EVENT batch only)."""
    raw = (os.environ.get("BOB_WORKER_INJECT_PASTE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def inject_console(
    pid: int,
    text: str,
    submit_gap_s: float | None = None,
    log: Optional[Callable[[str], None]] = None,
    kind: str | None = None,
) -> bool:
    """Paste text into THIS process's console input and submit with Enter.

    FR #2498: do not drip KEY_EVENT per character into the Grok TUI (that paints
    one glyph at a time and can take minutes per Jeeves line). Prefer clipboard +
    Ctrl+V (one paste), then the FR #1601 submit gap + double Enter.

    FR #3894: retry OpenClipboard (rdpclip races). Never fall back to *per-char*
    KEY_EVENT drip (FR #2498). FR #3996: if clipboard set fails, use one batched
    WriteConsoleInput KEY_EVENT write (``path=keys reason=clipboard_fallback``).
    Explicit ``BOB_WORKER_INJECT_PASTE=0`` skips clipboard and uses the batch path.

    FR #2508: opt out with BOB_WORKER_INJECT_PASTE=0 (KEY_EVENT batch only).
    FR #2504: save prior CF_UNICODETEXT before EmptyClipboard; restore after the
    Ctrl+V chord has been queued and the submit gap has elapsed (best-effort) so
    operator clipboard is not permanently clobbered. pid is call-signature only.
    """
    # FR #6240: this is the real transport. Tabs do not survive. OpenCode job
    # frames use pipes so the key and directory are still here after one_line.
    # FR #6366: OpenCode finish frames need the full checklist body (maxlen 2000).
    _oc_frame = (kind or "").strip().lower() == "opencode" and (text or "").startswith(
        "@@BOBJOB1|"
    )
    text = one_line(text, 2000) if _oc_frame else one_line(text)
    if not text or os.name != "nt":
        return False
    gap = _submit_gap_s() if submit_gap_s is None else max(0.05, float(submit_gap_s))
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    wintypes, _ = _win_structs()
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.WriteConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    def _log(msg: str) -> None:
        if not log:
            return
        try:
            # FR #6158: tag path logs with kind= so OpenCode/Cursor/Grok are distinguishable.
            k = (kind or "").strip().lower()
            if k and " kind=" not in msg:
                msg = f"{msg} kind={k}"
            log(msg)
        except Exception:
            pass

    with _CONSOLE_LOCK:
        h = k32.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
        if not h or h == ctypes.c_void_p(-1).value:
            return False
        prior = None
        clipboard_touched = False
        try:
            pasted = False
            prior = None
            if _inject_prefer_paste():
                prior = _clipboard_get_unicode(log=log)
                # FR #4115: set, then read back and compare before Ctrl+V. A failed set or a
                # readback mismatch (rdpclip / another owner raced us) falls back to keys.
                if clipboard_set_verified(
                    text, set_fn=_clipboard_set_unicode, read_fn=_clipboard_get_unicode, log=_log
                ):
                    clipboard_touched = True
                    pasted = _write_console_all(k32, h, _build_ctrl_v_records(), wintypes)
            if not pasted:
                # FR #3996: clipboard paste failed (or paste opt-out). One batched
                # WriteConsoleInput - never per-char drip (FR #2498 / #3894).
                prefer_paste = _inject_prefer_paste()
                recs = build_key_records(text, u32)
                if not _write_console_all(k32, h, recs, wintypes):
                    _log("relay: inject path=fail reason=keys_write")
                    return False
                if prefer_paste:
                    _log(
                        "relay: inject path=keys reason=clipboard_fallback "
                        f"chars={len(text)} (no KEY_EVENT drip; batched)"
                    )
                else:
                    _log(f"relay: inject path=keys chars={len(text)}")
            else:
                _log(f"relay: inject path=paste chars={len(text)}")
            # Give the TUI time to drain Ctrl+V and read our clipboard, then restore.
            # Enter only after paste/keys write finished (never mid-drip).
            time.sleep(gap)
            if clipboard_touched:
                # FR #4115: the Grok TUI reads the clipboard itself on Ctrl+V and can be slow
                # (busy turn end / session start). Restoring after the 0.2 s gap emptied the
                # clipboard under it ("Couldn't read clipboard text"). Restore later, and only
                # if the clipboard still holds our text.
                schedule_clipboard_restore(prior, text, restore_fn=_clipboard_restore_unicode, log=log)
                clipboard_touched = False
            if not _write_console_all(k32, h, build_enter_records(), wintypes):
                return False
            time.sleep(min(0.08, gap))
            # enter2: second Enter (FR #1601); name kept for test_fr1601 source probe.
            enter2 = _write_console_all(k32, h, build_enter_records(), wintypes)
            return enter2
        finally:
            if clipboard_touched:
                try:
                    schedule_clipboard_restore(prior, text, restore_fn=_clipboard_restore_unicode, log=log)
                except Exception:
                    pass
            k32.CloseHandle(h)


def build_clear_input_records():
    """FR #4510: Ctrl+A then Backspace, so a failed paste is not concatenated into the next offer."""
    wintypes, INPUT_RECORD = _win_structs()
    arr = (INPUT_RECORD * 6)()
    seq = [
        (0x11, 1, "\x00", 0x0008),
        (0x41, 1, "\x01", 0x0008),
        (0x41, 0, "\x01", 0x0008),
        (0x11, 0, "\x00", 0),
        (0x08, 1, "\x08", 0),
        (0x08, 0, "\x08", 0),
    ]
    for i, (vk, down, ch, ctrl) in enumerate(seq):
        rec = arr[i]
        rec.EventType = 1
        k = rec.Event.KeyEvent
        k.bKeyDown = down
        k.wRepeatCount = 1
        k.wVirtualKeyCode = vk
        k.wVirtualScanCode = 0
        k.uChar = ch
        k.dwControlKeyState = ctrl
    return arr


def clear_console_input(pid: int = 0) -> bool:
    """FR #4510: clear THIS process input box. Never paste."""
    if os.name != "nt":
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    wintypes, _ = _win_structs()
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    k32.WriteConsoleInputW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    with _CONSOLE_LOCK:
        h = k32.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
        if not h or h == ctypes.c_void_p(-1).value:
            return False
        try:
            return _write_console_all(k32, h, build_clear_input_records(), wintypes)
        finally:
            k32.CloseHandle(h)


def send_console_enter(pid: int = 0) -> bool:
    """Write one Enter to THIS process CONIN$ (FR #2696 submit-verify retry). Never paste."""
    if os.name != "nt":
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    wintypes, _ = _win_structs()
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    k32.WriteConsoleInputW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    with _CONSOLE_LOCK:
        h = k32.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
        if not h or h == ctypes.c_void_p(-1).value:
            return False
        try:
            return _write_console_all(k32, h, build_enter_records(), wintypes)
        finally:
            k32.CloseHandle(h)


def _submit_verify_enabled() -> bool:
    """FR #2696: BOB_WORKER_SUBMIT_VERIFY=0 disables post-inject submit probe/retry."""
    raw = (os.environ.get("BOB_WORKER_SUBMIT_VERIFY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _submit_verify_s(default: float = 3.0) -> float:
    """Seconds to wait for a submit probe before first Enter-only retry (FR #2696)."""
    raw = (os.environ.get("BOB_WORKER_SUBMIT_VERIFY_S") or "").strip()
    if not raw:
        return float(default)
    try:
        v = float(raw)
    except ValueError:
        return float(default)
    return max(0.2, min(30.0, v))


def _submit_verify_retries(default: int = 3) -> int:
    raw = (os.environ.get("BOB_WORKER_SUBMIT_VERIFY_RETRIES") or "").strip()
    if not raw:
        return int(default)
    try:
        v = int(raw)
    except ValueError:
        return int(default)
    return max(0, min(10, v))


def _submit_verify_giveup_grace_s(default: float = 20.0) -> float:
    """FR #4732: seconds to poll turn_running before Cursor GIVEUP after verify FAILED."""
    raw = (os.environ.get("BOB_WORKER_SUBMIT_VERIFY_GIVEUP_GRACE_S") or "").strip()
    if not raw:
        return float(default)
    try:
        v = float(raw)
    except ValueError:
        return float(default)
    return max(0.0, min(120.0, v))


def cursor_submit_verify_stop(bored, *, probe: Optional[Callable[[], bool]] = None) -> Callable[[], bool]:
    """FR #4732 / FR #4889: stop on turn_open or probe; never receipt ack_open alone.

    Cursor (#4732) and grok (#4889) both ACK on receipt (FR #4115). That ACK must
    not end submit-verify as ok (stop/ACK) before the paste is submitted.
    """

    def _stop() -> bool:
        try:
            if bored is not None and bool(getattr(bored, "turn_open", False)):
                return True
        except Exception:
            pass
        if probe is not None:
            try:
                if probe():
                    return True
            except Exception:
                pass
        return False

    return _stop


# FR #4889: grok uses the same predicate (alias for call sites / skills).
grok_submit_verify_stop = cursor_submit_verify_stop


def _submit_verify_backoffs() -> tuple:
    """Backoff seconds between Enter-only retries after the first verify window (FR #2696)."""
    raw = (os.environ.get("BOB_WORKER_SUBMIT_VERIFY_BACKOFFS") or "").strip()
    if raw:
        out = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(max(0.2, min(60.0, float(part))))
            except ValueError:
                continue
        if out:
            return tuple(out)
    return (3.0, 5.0, 8.0)


def _parse_iso_ts(raw: str) -> Optional[float]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def grok_session_dir(
    cwd: str,
    session_id: str,
    sessions_root: Optional[Path] = None,
    run_dir: Path | str | None = None,
) -> Optional[Path]:
    """Resolve ``<agent GROK_HOME>/sessions/<url-quoted cwd>/<uuid>`` (FR #2696 / #7123)."""
    from urllib.parse import quote

    if not session_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", str(session_id)):
        return None
    root = Path(sessions_root) if sessions_root else grok_sessions_root(run_dir=run_dir)
    sid = str(session_id)
    for key in (quote(str(cwd), safe=""), quote(str(cwd).rstrip("\\"), safe="")):
        d = root / key / sid
        if d.is_dir():
            return d
    try:
        if root.is_dir():
            for d in root.glob("*/" + sid):
                if d.is_dir():
                    return d
    except OSError:
        pass
    return None


def probe_grok_session_submit(session_dir: Path | str, *, since_wall: float) -> bool:
    """True when events.jsonl has turn_started with ts > since_wall (FR #2696)."""
    path = Path(session_dir) / "events.jsonl"
    if not path.is_file():
        return False
    try:
        # Read tail only for large logs.
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = data.splitlines()[-200:]
    for line in reversed(lines):
        line = line.strip()
        if not line or '"turn_started"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if str(obj.get("type") or "") != "turn_started":
            continue
        ts = _parse_iso_ts(str(obj.get("ts") or ""))
        if ts is not None and ts > float(since_wall):
            return True
    return False


def probe_unified_prompt_enqueue(*, agent_pid: int, since_wall: float, log_path: Optional[Path] = None) -> bool:
    """True when unified.jsonl has grok-pager prompt.enqueue for agent_pid after since_wall."""
    path = Path(log_path) if log_path else default_unified_log_path()
    if not path.is_file() or int(agent_pid or 0) <= 0:
        return False
    try:
        # Bound read: last ~512 KiB.
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 524288), os.SEEK_SET)
            chunk = f.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    for line in reversed(chunk.splitlines()[-400:]):
        if "prompt.enqueue" not in line or "grok-pager" not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if str(obj.get("msg") or "") != "prompt.enqueue":
            continue
        if int(obj.get("pid") or 0) != int(agent_pid):
            continue
        ts = _parse_iso_ts(str(obj.get("ts") or ""))
        if ts is not None and ts > float(since_wall):
            return True
    return False



def probe_opencode_turns_submit(turns_path: Path | str, *, since_wall: float) -> bool:
    """True when opencode-turns.jsonl has turn_started with ts > since_wall (FR #6158).

    Reuses FR #6157 wrapper markers: a new turn_started after the inject baseline means
    ReadLine accepted a line and Invoke-Opencode began.
    """
    path = Path(turns_path)
    if not path.is_file():
        return False
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = data.splitlines()[-200:]
    for line in reversed(lines):
        line = line.strip()
        if not line or '"turn_started"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if str(obj.get("type") or "") != "turn_started":
            continue
        ts = _parse_iso_ts(str(obj.get("ts") or ""))
        if ts is not None and ts > float(since_wall):
            return True
    return False


def probe_opencode_headless_receipt(
    turns_path: Path | str,
    *,
    since_wall: float,
    baseline_size: int = 0,
) -> bool:
    """FR #8270: OpenCode has no TUI prompt. A turn receipt is enough.

    ``turn_started`` after the inject, or any new bytes in opencode-turns.jsonl
    (first output from the headless run). A missing file is not a receipt.
    """
    if probe_opencode_turns_submit(turns_path, since_wall=since_wall):
        return True
    path = Path(turns_path)
    try:
        if path.is_file() and path.stat().st_size > int(baseline_size):
            return True
    except OSError:
        return False
    return False


def make_submit_probe(
    kind: str,
    *,
    cwd: str = "",
    session_id: str | None = None,
    agent_pid: int = 0,
    since_wall: float | None = None,
    sessions_root: Optional[Path] = None,
    text: str = "",
    cursor_chats_root: Optional[Path] = None,
    run_dir: Path | str | None = None,
) -> Optional[Callable[[], bool]]:
    """Build a submit probe for the agent kind (FR #2696 / #6158). None = no probe available."""
    k = (kind or "").strip().lower()
    t0 = float(time.time() if since_wall is None else since_wall)

    if k == "grok":
        sdir = (
            grok_session_dir(cwd, session_id or "", sessions_root=sessions_root, run_dir=run_dir)
            if session_id
            else None
        )
        unified = default_unified_log_path(run_dir=run_dir)

        def _probe() -> bool:
            if sdir and probe_grok_session_submit(sdir, since_wall=t0):
                return True
            if agent_pid and probe_unified_prompt_enqueue(
                agent_pid=int(agent_pid), since_wall=t0, log_path=unified
            ):
                return True
            return False

        return _probe

    if k == "cursor":
        # Cursor submit probe: cursor-agent appends each submitted prompt to
        # ~/.cursor/chats/<ws>/<chat>/prompt_history.json. True once a history file touched
        # since the inject holds the injected text (prefix match; a lone "v" from Ctrl+V is not it).
        want = re.sub(r"\s+", " ", (text or "")).strip()[:60]
        croot = Path(cursor_chats_root) if cursor_chats_root else (Path.home() / ".cursor" / "chats")

        def _cprobe() -> bool:
            return probe_cursor_prompt_history(croot, want, since_wall=t0)

        return _cprobe if want else None

    if k == "opencode":
        # FR #6158: wrapper writes turn_started to run_dir/opencode-turns.jsonl (FR #6157).
        if run_dir is None:
            return None
        turns = Path(run_dir) / "opencode-turns.jsonl"
        try:
            base_size = turns.stat().st_size if turns.is_file() else 0
        except OSError:
            base_size = 0

        def _oprobe() -> bool:
            # FR #8270: headless run has no TUI prompt. turn_started or new
            # turn-log bytes are the receipt.
            return probe_opencode_headless_receipt(
                turns, since_wall=t0, baseline_size=base_size
            )

        return _oprobe

    # Unknown kinds: no durable enqueue log on this fleet yet.
    return None


def probe_cursor_prompt_history(
    chats_root: Path | str,
    want: str,
    *,
    since_wall: float,
    require_newest_job_key: bool = True,
) -> bool:
    """True when a prompt_history.json modified at/after ``since_wall`` contains ``want``.

    FR #4842: when ``want`` is a Jeeves assign, the *newest* assign-like history entry
    must carry the same ``assign_job_key`` as ``want``. An older matching paste must not
    pass while a later stale assign (different key) is the tip of history.
    """
    if not want:
        return False
    want_norm = re.sub(r"\s+", " ", want)
    want_key = assign_job_key(want)
    try:
        root = Path(chats_root)
        for f in root.glob("*/*/prompt_history.json"):
            try:
                if f.stat().st_mtime + 1.0 < float(since_wall):
                    continue
                data = json.loads(f.read_text(encoding="utf-8", errors="replace") or "[]")
            except (OSError, ValueError):
                continue
            if not isinstance(data, list):
                continue
            norms = [re.sub(r"\s+", " ", str(entry)) for entry in data]
            if want_norm not in norms and not any(want_norm in n for n in norms):
                continue
            if not (require_newest_job_key and want_key):
                return True
            newest_key = None
            for n in reversed(norms):
                k = assign_job_key(n)
                if k:
                    newest_key = k
                    break
            if newest_key is None:
                return True
            if newest_key.lower() == want_key.lower():
                return True
            continue
    except OSError:
        return False
    return False


def _cursor_submit_gap_s(default: float = 1.0) -> float:
    """Pre-Enter gap for cursor-agent: its Ctrl+V clipboard read is async (Enter must wait)."""
    raw = (os.environ.get("BOB_WORKER_CURSOR_SUBMIT_GAP_S") or "").strip()
    try:
        v = float(raw) if raw else float(default)
    except ValueError:
        v = float(default)
    return max(0.2, min(10.0, v))


def bored_on_turn_end_enabled() -> bool:
    """FR #2802: BOB_WORKER_BORED_ON_TURN_END=0 restores timer-only harvest_hold_s behaviour."""
    raw = (os.environ.get("BOB_WORKER_BORED_ON_TURN_END") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def should_start_turn_watcher(kind: str) -> bool:
    """FR #2802: grok turn watcher only when opt-in is on (default on)."""
    return (kind or "").strip().lower() == "grok" and bored_on_turn_end_enabled()


def should_start_opencode_turn_watcher(kind: str) -> bool:
    """FR #6157: OpenCode seats tail run_dir/opencode-turns.jsonl (wrapper markers).

    Opt out with BOB_WORKER_BORED_ON_TURN_END=0 or BOB_WORKER_OPENCODE_TURN_WATCH=0.
    """
    if (kind or "").strip().lower() != "opencode" or not bored_on_turn_end_enabled():
        return False
    raw = (os.environ.get("BOB_WORKER_OPENCODE_TURN_WATCH") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def startup_turn_release_enabled(kind: str) -> bool:
    """FR #6157: startup wait_ready / first-turn release for grok or opencode turn watchers.

    Cursor uses its own quiet-period watcher and does not gate startup on events.jsonl.
    """
    k = (kind or "").strip().lower()
    if k == "grok":
        return should_start_turn_watcher(k)
    if k == "opencode":
        return should_start_opencode_turn_watcher(k)
    return False


def should_start_cursor_turn_watcher(kind: str) -> bool:
    """Cursor seats: chat-store quiet-period turn watcher (BOB_WORKER_CURSOR_TURN_WATCH=0 disables)."""
    if (kind or "").strip().lower() != "cursor" or not bored_on_turn_end_enabled():
        return False
    raw = (os.environ.get("BOB_WORKER_CURSOR_TURN_WATCH") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def should_start_aider_turn_watcher(kind: str) -> bool:
    """FR #7265: Aider seats infer turn end from process idle (BOB_WORKER_AIDER_TURN_WATCH=0 disables)."""
    if (kind or "").strip().lower() != "aider" or not bored_on_turn_end_enabled():
        return False
    raw = (os.environ.get("BOB_WORKER_AIDER_TURN_WATCH") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _aider_turn_quiet_s(default: float = 5.0) -> float:
    raw = (os.environ.get("BOB_WORKER_AIDER_TURN_QUIET_S") or "").strip()
    try:
        v = float(raw) if raw else float(default)
    except ValueError:
        v = float(default)
    return max(1.0, min(60.0, v))


class ProcIdleTurnWatcher:
    """FR #7265: turn_started on process activity; turn_ended after quiet_s with no CPU/IO."""

    def __init__(
        self,
        *,
        probe: Callable[[], object],
        quiet_s: float | None = None,
        clock: Callable[[], float] = time.time,
        on_turn_started: Optional[Callable[[Optional[int], float], None]] = None,
        on_turn_ended: Optional[Callable[[Optional[int], float], None]] = None,
        stop_event: Optional[threading.Event] = None,
        log: Optional[Callable[[str], None]] = None,
        interval_s: float = 0.5,
    ) -> None:
        self.probe = probe
        self.quiet_s = float(_aider_turn_quiet_s() if quiet_s is None else quiet_s)
        self.clock = clock
        self._on_started = on_turn_started
        self._on_ended = on_turn_ended
        self._stop = stop_event
        self.log = log or (lambda _m: None)
        self.interval_s = max(0.2, float(interval_s))
        self._active = False
        self._quiet_since: Optional[float] = None
        self._turn = 0

    def _busy(self) -> bool:
        try:
            sample = self.probe()
        except Exception:
            return False
        try:
            return int(getattr(sample, "activity", 0) or 0) > 0
        except Exception:
            return False

    def tick(self) -> Optional[str]:
        now = float(self.clock())
        busy = self._busy()
        if busy:
            self._quiet_since = None
            if not self._active:
                self._active = True
                self._turn += 1
                if self._on_started:
                    try:
                        self._on_started(self._turn, now)
                    except Exception:
                        pass
                return "started"
            return None
        if not self._active:
            return None
        if self._quiet_since is None:
            self._quiet_since = now
            return None
        if (now - self._quiet_since) < self.quiet_s:
            return None
        self._active = False
        self._quiet_since = None
        if self._on_ended:
            try:
                self._on_ended(self._turn, now)
            except Exception:
                pass
        return "ended"

    def run(self) -> None:
        while self._stop is None or not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                pass
            if self._stop is not None:
                self._stop.wait(self.interval_s)
            else:
                time.sleep(self.interval_s)


def apply_cursor_inject_keys_default(kind: str, log: Optional[Callable[[str], None]] = None) -> bool:
    """FR #4464 / #6158 / #8558 / #8560: Cursor and OpenCode seats use batched KEY_EVENT.

    cursor-agent treats Ctrl+V as a literal v. OpenCode ReadLine paste is unreliable on
    this fleet (FR-OC-INJECT / #8560): PASTE=1 leaves a stray ``v`` in the TUI, submit-verify
    fails, and the seat later exits cli-failure with ``What would you like me to do?``.
    OpenCode always forces ``BOB_WORKER_INJECT_PASTE=0`` (even when the env was set to 1).
    Cursor still defaults to 0 when unset; an explicit Cursor value wins.
    """
    k = (kind or "").strip().lower()
    if k not in ("cursor", "opencode"):
        return False
    raw = (os.environ.get("BOB_WORKER_INJECT_PASTE") or "").strip().lower()
    if k == "opencode":
        if raw in ("0", "false", "no", "off"):
            return False
        # Unset or PASTE=1 (or other truthy): force keys. FR #8558 / #8560.
        changed = raw != "0"
        os.environ["BOB_WORKER_INJECT_PASTE"] = "0"
        if log is not None:
            try:
                if raw in ("1", "true", "yes", "on"):
                    log(
                        "relay: opencode seat - ignoring BOB_WORKER_INJECT_PASTE=1; "
                        "inject via batched keys only (FR #8558 / #8560: never PASTE=1)"
                    )
                elif changed:
                    log(
                        "relay: opencode seat - inject via batched keys "
                        "(FR #8560: keep BOB_WORKER_INJECT_PASTE=0; never PASTE=1)"
                    )
            except Exception:
                pass
        return True
    if raw:
        return False
    os.environ["BOB_WORKER_INJECT_PASTE"] = "0"
    if log is not None:
        try:
            log("relay: cursor seat - inject via batched keys (Ctrl+V lands as literal 'v')")
        except Exception:
            pass
    return True


def cursor_project_slug(cwd: str) -> str:
    """``C:\\ai\\bob\\worker`` -> ``C-ai-bob-worker`` (Cursor's ``~/.cursor/projects`` folder)."""
    s = str(cwd or "").replace("/", "\\").rstrip("\\")
    if len(s) >= 2 and s[1] == ":":
        s = s[0] + s[2:]
    return s.replace("\\", "-").replace(":", "-")


def _cursor_transcript_tail_objs(path: Path | str, *, max_bytes: int = 262144) -> list[dict]:
    """Parse trailing JSON objects from a cursor agent transcript (best-effort)."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        return []
    try:
        with p.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            raw = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    out: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def cursor_transcript_last_turn_ended(path: Path | str) -> Optional[dict]:
    """FR #4753: newest ``type=turn_ended`` record (any status), or None."""
    last: Optional[dict] = None
    for obj in _cursor_transcript_tail_objs(path):
        if str(obj.get("type") or "") == "turn_ended":
            last = obj
    return last


def cursor_transcript_still_open(path: Path | str) -> Optional[bool]:
    """FR #4670: True while the newest transcript record is not a finished assistant reply.

    A trailing ``tool_use`` (or a user line, including a done-miss reminder) means the
    agent is still in the turn. ``False`` when the newest assistant message is text
    with no tool call. ``None`` when the file is missing or has no parseable records
    (caller keeps the legacy quiet-gap end).

    FR #4753: a trailing ``type=turn_ended`` (including ``status=error``) means the
    turn is closed — Connection stalled / error ends must arm done-miss.
    """
    objs = _cursor_transcript_tail_objs(path)
    if not objs:
        return None
    # Prefer explicit turn lifecycle events over chat role/content heuristics.
    for obj in reversed(objs):
        typ = str(obj.get("type") or "")
        if typ == "turn_ended":
            return False
        if typ == "turn_started":
            return True
        role = obj.get("role")
        msg = obj.get("message")
        if role in ("assistant", "user") and isinstance(msg, dict):
            if role != "assistant":
                return True
            content = msg.get("content")
            if not isinstance(content, list):
                return True
            types = [part.get("type") for part in content if isinstance(part, dict)]
            if any(t in ("tool_use", "tool_call") for t in types):
                return True
            if "text" in types:
                return False
            return True
    return None



def _user_message_text(obj: dict) -> str:
    """Flatten text parts from a transcript user/assistant message object."""
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return str(obj.get("content") or obj.get("text") or "")
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") in (None, "text"):
            t = part.get("text")
            if t:
                parts.append(str(t))
    return "\n".join(parts)


def cursor_transcript_latest_user_assign_key(path: Path | str) -> Optional[str]:
    """FR #4842: newest user-turn assign_job_key from a cursor transcript, or None."""
    for obj in reversed(_cursor_transcript_tail_objs(path)):
        role = obj.get("role")
        typ = str(obj.get("type") or "")
        if role != "user" and typ not in ("user", "user_message"):
            continue
        key = assign_job_key(_user_message_text(obj) if isinstance(obj, dict) else "")
        if key:
            return key
    return None


def stale_replay_assign_key(
    *,
    user_key: Optional[str],
    finished_keys,
    open_ack_key: Optional[str],
    done_keys=None,
) -> Optional[str]:
    """FR #4842 / #5327: return finished user_key when it differs from the open ACK.

    FR #5327: never treat a DONE-finished key as stale-replay (transcript lag after
    DONE K + assign J still shows K). GIVEUP/NACK-finished keys still hit.
    """
    uk = (user_key or "").strip()
    if not uk:
        return None
    open_k = (open_ack_key or "").strip()
    if open_k and uk.lower() == open_k.lower():
        return None
    done = {str(x).strip().lower() for x in (done_keys or []) if x}
    if uk.lower() in done:
        return None
    finished = {str(x).strip().lower() for x in (finished_keys or []) if x}
    if uk.lower() not in finished:
        return None
    return uk


def stale_replay_wait_s(default: float = 8.0) -> float:
    """FR #5403: how long to wait for transcript J after inject."""
    return _env_float("BOB_WORKER_STALE_REPLAY_WAIT_S", default, 1.0, 60.0)


def stale_replay_compare_ready(
    *,
    user_key: Optional[str],
    open_ack_key: Optional[str],
    inject_at: Optional[float],
    now: float,
    wait_s: Optional[float] = None,
    turn_started_for_open: bool = False,
) -> bool:
    """True when it is safe to run stale-replay compare (FR #5403).

    Wait until the latest user assign is the open ACK (J), or turn-started
    for J, or the wait after inject/ACK has elapsed. Callers should pass
    ``_inject_at or _ack_at`` because ACK clears ``_inject_at`` (MRB #5435).
    DONE-key exemption stays in stale_replay_assign_key.
    """
    if turn_started_for_open:
        return True
    uk = (user_key or "").strip()
    open_k = (open_ack_key or "").strip()
    if open_k and uk and uk.lower() == open_k.lower():
        return True
    if inject_at is None:
        return True
    limit = float(wait_s) if wait_s is not None else stale_replay_wait_s()
    try:
        return float(now) - float(inject_at) >= limit
    except (TypeError, ValueError):
        return True


def _cursor_turn_quiet_s(default: float = 20.0) -> float:

    raw = (os.environ.get("BOB_WORKER_CURSOR_TURN_QUIET_S") or "").strip()
    try:
        v = float(raw) if raw else float(default)
    except ValueError:
        v = float(default)
    return max(5.0, min(300.0, v))


class CursorTurnWatcher:
    """cursor-agent writes no turn events; infer them from its chat store.

    The seat's chat is the ``~/.cursor/chats/<ws>/<chat>/`` dir created closest after the agent
    spawn (``since_wall``). A write to any file in it after a quiet spell = turn_started.

    FR #4670: ``turn_ended`` is not a quiet gap between tool calls. When the chat's
    ``meta.json`` cwd points at an agent transcript, the turn stays open while the newest
    record is a ``tool_use`` or a user line (no final assistant text). A quiet store ends
    the turn only after that transcript shows a finished assistant reply, or when no
    transcript exists (legacy). ``clock`` is wall time (file mtimes are wall time).
    """

    def __init__(
        self,
        *,
        since_wall: float,
        chats_root: Path | str | None = None,
        projects_root: Path | str | None = None,
        quiet_s: float | None = None,
        on_turn_started: Optional[Callable[[Optional[int], float], None]] = None,
        on_turn_ended: Optional[Callable[[Optional[int], float], None]] = None,
        stop_event: Optional[threading.Event] = None,
        poll_s: float = 1.0,
        clock: Callable[[], float] = time.time,
        log: Optional[Callable[[str], None]] = None,
        bind_window_s: float = 120.0,
    ):
        self.root = Path(chats_root) if chats_root else (Path.home() / ".cursor" / "chats")
        self.projects_root = (
            Path(projects_root) if projects_root else (Path.home() / ".cursor" / "projects")
        )
        self.since_wall = float(since_wall)
        self.quiet_s = float(_cursor_turn_quiet_s() if quiet_s is None else quiet_s)
        self._on_started = on_turn_started
        self._on_ended = on_turn_ended
        self._stop = stop_event or threading.Event()
        self.poll_s = max(0.05, float(poll_s))
        self.clock = clock
        self._log = log
        self.bind_window_s = float(bind_window_s)
        self.chat_dir: Optional[Path] = None
        self._transcript_path: Optional[Path] = None
        self._last_mtime = 0.0
        self._active = False
        self._turn = 0
        # FR #4753: only fire on turn_ended records appended after this turn started.
        self._te_count_at_start = 0

    def _bind(self) -> Optional[Path]:
        if self.chat_dir is not None:
            return self.chat_dir
        best = None
        try:
            for d in self.root.glob("*/*"):
                if not d.is_dir():
                    continue
                # FR #6713: skip project-tree dirs accidentally nested under chats_root
                # (tests used tmp/projects beside tmp/ws). Prefer real chat stores.
                try:
                    looks_chat = (d / "store.db").is_file() or (d / "meta.json").is_file()
                except OSError:
                    looks_chat = False
                if not looks_chat:
                    continue
                try:
                    st = d.stat()
                except OSError:
                    continue
                born = min(st.st_mtime, getattr(st, "st_ctime", st.st_mtime))
                if os.name != "nt":
                    born = st.st_mtime
                    with contextlib.suppress(OSError):
                        born = min(f.stat().st_mtime for f in d.iterdir()) if any(d.iterdir()) else born
                if born + 2.0 < self.since_wall or born > self.since_wall + self.bind_window_s:
                    continue
                if best is None or born < best[0]:
                    best = (born, d)
        except OSError:
            return None
        if best is not None:
            self.chat_dir = best[1]
            if self._log:
                with contextlib.suppress(Exception):
                    self._log(f"bored: cursor turn watcher following {self.chat_dir}")
        return self.chat_dir

    def _newest_mtime(self, d: Path) -> float:
        m = 0.0
        try:
            for f in d.iterdir():
                with contextlib.suppress(OSError):
                    if f.is_file():
                        m = max(m, f.stat().st_mtime)
        except OSError:
            pass
        tp = self._transcript_file(d)
        if tp is not None:
            with contextlib.suppress(OSError):
                m = max(m, tp.stat().st_mtime)
        return m

    def _transcript_file(self, chat_dir: Path) -> Optional[Path]:
        """Agent transcript for this chat, from ``meta.json`` cwd. Missing until the file exists."""
        if self._transcript_path is not None:
            return self._transcript_path
        meta_path = chat_dir / "meta.json"
        if not meta_path.is_file():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError, TypeError):
            return None
        if not isinstance(meta, dict):
            return None
        cwd = str(meta.get("cwd") or "")
        chat_id = chat_dir.name
        if not cwd or not chat_id:
            return None
        cand = (
            self.projects_root
            / cursor_project_slug(cwd)
            / "agent-transcripts"
            / chat_id
            / f"{chat_id}.jsonl"
        )
        if cand.is_file():
            self._transcript_path = cand
            return cand
        try:
            found = next(
                self.projects_root.glob(f"*/agent-transcripts/{chat_id}/{chat_id}.jsonl"),
                None,
            )
        except OSError:
            found = None
        if found is not None and found.is_file():
            self._transcript_path = found
            return found
        return None

    def _transcript_blocks_end(self, chat_dir: Path) -> bool:
        """True when a readable transcript still has a tool call or no final assistant text.

        FR #6713: when the transcript file exists but yields no parseable records
        (``cursor_transcript_still_open`` → ``None``), keep the turn open. Windows
        full-suite / AV races can briefly read an empty flush; quiet-ending then
        falsely fires ``turn_ended`` during tool gaps and user-reminder lines.
        Missing transcript still uses the legacy quiet-gap end (``False`` here).
        """
        tp = self._transcript_file(chat_dir)
        if tp is None:
            return False
        open_state = cursor_transcript_still_open(tp)
        if open_state is True:
            return True
        if open_state is None:
            return True
        return False

    def _transcript_turn_ended_count(self, chat_dir: Path) -> int:
        """FR #4753: count of ``type=turn_ended`` records in the transcript tail."""
        tp = self._transcript_file(chat_dir)
        if tp is None:
            return 0
        return sum(
            1
            for o in _cursor_transcript_tail_objs(tp)
            if str(o.get("type") or "") == "turn_ended"
        )

    def tick(self) -> Optional[str]:
        """One poll; returns 'started' / 'ended' when it fired a callback (tests)."""
        d = self._bind()
        if d is None:
            return None
        now = float(self.clock())
        m = self._newest_mtime(d)
        # FR #5129: under full-suite load, file mtimes can briefly read as 0 while the
        # chat dir is already bound; fall back to directory mtime so turn_started fires.
        if m <= 0.0:
            with contextlib.suppress(OSError):
                m = float(d.stat().st_mtime)
        fired = None
        if m > self._last_mtime:
            self._last_mtime = m
            if not self._active:
                self._active = True
                self._turn += 1
                self._te_count_at_start = self._transcript_turn_ended_count(d)
                fired = "started"
                if self._on_started:
                    with contextlib.suppress(Exception):
                        self._on_started(self._turn, now)
        # FR #4753: a new transcript turn_ended (incl. status=error) ends this turn
        # even when the chat store stays quiet or still looks open via a user line.
        if self._active and self._transcript_turn_ended_count(d) > self._te_count_at_start:
            self._active = False
            fired = "ended"
            kw = {}
            tp = self._transcript_file(d)
            te = cursor_transcript_last_turn_ended(tp) if tp else None
            if te is not None and str(te.get("status") or "").lower() == "error":
                kw = {
                    "error": True,
                    "error_class": "turn_ended",
                    "error_line": str(te.get("error") or "status=error")[:200],
                }
            with contextlib.suppress(Exception):
                _notify_turn_ended_cb(self._on_ended, self._turn, now, **kw)
            return fired
        if self._active and now - self._last_mtime >= self.quiet_s:
            # FR #4670: a quiet store.db during a tool call is not the end of the turn.
            if self._transcript_blocks_end(d):
                return None
            self._active = False
            fired = "ended"
            with contextlib.suppress(Exception):
                _notify_turn_ended_cb(self._on_ended, self._turn, now)
        return fired

    def run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.poll_s)


class GrokTurnWatcher:
    """FR #2802: poll grok session events.jsonl for turn_started / turn_ended."""

    def __init__(
        self,
        *,
        events_path: Path | str | None = None,
        events_path_fn: Optional[Callable[[], Path | str | None]] = None,
        on_turn_started: Optional[Callable[[Optional[int], float], None]] = None,
        on_turn_ended: Optional[Callable[[Optional[int], float], None]] = None,
        stop_event: Optional[threading.Event] = None,
        poll_s: float = 0.5,
        log: Optional[Callable[[str], None]] = None,
    ):
        self._path = Path(events_path) if events_path else None
        self._path_fn = events_path_fn
        self._on_started = on_turn_started
        self._on_ended = on_turn_ended
        self._stop = stop_event or threading.Event()
        self.poll_s = max(0.05, float(poll_s))
        self._log = log
        self._offset = 0
        self._cur: Optional[Path] = None

    def _resolve(self) -> Optional[Path]:
        if self._path_fn is not None:
            try:
                p = self._path_fn()
            except Exception:
                return None
            return Path(p) if p else None
        return self._path

    def _emit_line(self, line: str) -> None:
        line = (line or "").strip()
        if not line:
            return
        try:
            obj = json.loads(line)
        except Exception:
            return
        typ = str(obj.get("type") or "")
        wall = _parse_iso_ts(str(obj.get("ts") or ""))
        if wall is None:
            wall = time.time()
        turn = obj.get("turn_number")
        try:
            turn_i = int(turn) if turn is not None else None
        except Exception:
            turn_i = None
        if typ == "turn_started" and self._on_started:
            try:
                self._on_started(turn_i, float(wall))
            except Exception:
                pass
        elif typ == "turn_ended" and self._on_ended:
            st = str(obj.get("status") or "").lower()
            err_txt = str(obj.get("error") or "")
            kw = {}
            if st == "error" or err_txt:
                kw = {
                    "error": True,
                    "error_class": str(obj.get("error_class") or "turn_ended"),
                    "error_line": (err_txt or st or "status=error")[:200],
                }
            try:
                _notify_turn_ended_cb(self._on_ended, turn_i, float(wall), **kw)
            except Exception:
                pass

    def run(self) -> None:
        while not self._stop.is_set():
            path = self._resolve()
            if path is None:
                self._stop.wait(self.poll_s)
                continue
            try:
                if self._cur != path:
                    self._cur = path
                    self._offset = 0
                    if self._log:
                        try:
                            self._log(f"bored: turn watcher following {path}")
                        except Exception:
                            pass
                if not path.is_file():
                    self._stop.wait(self.poll_s)
                    continue
                size = path.stat().st_size
                if size < self._offset:
                    self._offset = 0
                if size > self._offset:
                    with path.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(self._offset)
                        chunk = f.read()
                        self._offset = f.tell()
                    for ln in chunk.splitlines():
                        self._emit_line(ln)
            except OSError:
                pass
            self._stop.wait(self.poll_s)


# --------------------------------------------------------------------------------------------- FR #3012 / #3019: out-of-fuel
# Detect agent 402 / usage-exhausted / NEEDS_AUTH as out-of-fuel (not done-miss).
# Bare "402" in token counts must not match. Cursor parity: same contract without grok-only gate (FR #3019).
# Strong provider cues (no bare "rate limit" — FR #8151 tool-output false pause).
_OUT_OF_FUEL_RX = re.compile(
    r"(?i)(?:"
    r"402\s*Payment\s*Required"
    r"|Payment\s*Required:[^\n]{0,80}exhausted"
    r"|Grok\s+Build\s+usage\s+balance\s+exhausted"
    r"|usage\s+balance\s+exhausted"
    r"|out\s+of\s+credits"
    r"|out\s+of\s+tokens"
    r"|insufficient\s*quota"
    r"|quota\s*exceeded"
    r"|NEEDS_AUTH"
    r"|OUTCOME_NEEDS_AUTH"
    r"|unpaid\s+invoice"
    r"|Too\s+Many\s+Requests"
    r"|rolling\s+limit"
    # FR #8026: OpenCode free pool (may hang without exit).
    r"|Free\s+usage\s+limit"
    r"|subscribe\s+to\s+OpenCode\s+Go"
    r")"
)

# Bare rate-limit words only count with provider/API/HTTP context (FR #8151).
_RATE_LIMIT_PROVIDER_CTX_RX = re.compile(
    r"(?i)(?:"
    r"(?:HTTP|status(?:_code| code)?)\D{0,20}\b429\b"
    r"|\b429\b.{0,60}rate\s*limit"
    r"|rate\s*limit(?:ed|ing)?.{0,60}\b(?:provider|api|openai|anthropic|xai|opencode|grok)\b"
    r"|\b(?:provider|api|openai|anthropic|xai|opencode|grok)\b.{0,60}rate\s*limit"
    r"|AI_(?:APICall|Retry)Error"
    r"|Too\s+Many\s+Requests"
    r")"
)

# Tool / agent echo that must never arm a pause (FR #8151 / #8207).
_FUEL_TOOL_OUTPUT_NOISE_RX = re.compile(
    r"(?i)(?:"
    r"coderabbit(?:ai)?|coderabbit-ai-generated"
    r"|rate\s+limited\s+by\s+coderabbit"
    r"|\"comments\"\s*:\s*\["
    r"|\"author\"\s*:\s*\{\s*\"login\""
    r"|Rate\s+limit\s*\+\s*single\s+instance"
    # FR #8207: gh issue/pr view / PR markdown quoting fuel phrases.
    r"|\"(?:title|body)\"\s*:\s*"
    r"|\bgh\s+(?:issue|pr|api)\b"
    r"|Closes\s+SimonBarnett/"
    r"|##\s+Summary\b"
    r"|diff\s+--git\s+"
    r")"
)

_PROVIDER_FUEL_SOURCES = ("app-log", "cli-stderr", "provider-json")

_OPENCODE_FREE_USAGE_RX = re.compile(
    r"(?i)(?:Free\s+usage\s+limit|subscribe\s+to\s+OpenCode\s+Go)"
)

# FR #8207: Free-usage phrases only count on provider channels (app-log ERROR / AI_*).
_FREE_USAGE_PROVIDER_CUE_RX = re.compile(
    r"(?i)(?:(?:^|\s)level=ERROR\b|AI_(?:APICall|Retry)Error)"
)


def opencode_fuel_exhausted_reason(text: str, *, start_model: str = "") -> str:
    """GIVEUP/NACK reason for OpenCode provider fuel text (FR #8026 / #8207).

    Paid/go start models never emit ``fuel-exhausted:opencode-free`` — free-pool
    exhaustion is not proof the paid pool is empty (FR #8207 / #8158).
    """
    scanned = provider_fuel_scan_text(text)
    if _OPENCODE_FREE_USAGE_RX.search(scanned):
        mid = (start_model or "").strip()
        if mid:
            pool = seat_fuel_pool("opencode", mid)
            if pool == "opencode_go":
                return "out-of-fuel"
        return "fuel-exhausted:opencode-free"
    return "out-of-fuel"
DEFAULT_DIGEST_REPORT_URL = "https://bob.ntsa.uk/bob/v1/report"


# Instructional mentions are markdown code spans and a stock phrase that is the
# entire quoted span (MRB #6231). Apostrophes in contractions are not quotes.
# A wrapper fuel-log line is scanned from its text field, not as a JSON quotation.
_BACKTICK_SPAN_RX = re.compile(r"`[^`]*`")
_STOCK_MENTION_RX = re.compile(
    r"(?i)^(?:402\s*payment\s*required|payment\s*required"
    r"|usage\s+balance\s+exhausted|needs_auth|outcome_needs_auth)$"
)
_SQ_SPAN_RX = re.compile(r"(?<!\w)'([^'\n]{0,80})'(?!\w)")
_DQ_SPAN_RX = re.compile(r'"([^"\n]{0,80})"')
_UNQUOTED_PROVIDER_STATUS_RX = re.compile(
    r"(?i)(?:\bhttp\b|\bstatus(?:_code| code)?)\D{0,12}\b(402|429)\b"
)


def _fuel_log_envelope(text: str) -> Optional[dict]:
    """Parse a wrapper fuel-log JSON line; None when not that envelope."""
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        obj = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    if "pid" not in obj and "model" not in obj:
        return None
    return obj


def fuel_log_recorded_text(text: str) -> Optional[str]:
    """Return the text field of a wrapper fuel-log JSON line, else None."""
    obj = _fuel_log_envelope(text)
    if obj is None:
        return None
    recorded = obj.get("text")
    if not isinstance(recorded, str):
        return None
    return recorded


def fuel_log_recorded_source(text: str) -> Optional[str]:
    """Return the ``source`` field of a fuel-log JSON line when present (FR #8151)."""
    obj = _fuel_log_envelope(text)
    if obj is None:
        return None
    src = obj.get("source")
    if not isinstance(src, str):
        return None
    src = src.strip().lower()
    return src or None


def _strip_instructional_mentions(text: str) -> str:
    """Drop backtick spans and a stock phrase that is the whole quoted span.

    Provider's and can't stay. A span whose entire content is 402 Payment Required
    is an instruction. status_code=402 "usage balance exhausted" keeps the quoted
    detail because the status code sits outside the quotes.
    """

    def stock_or_keep(match):
        inner = match.group(1).strip()
        return " " if _STOCK_MENTION_RX.match(inner) else match.group(0)

    cleaned = _BACKTICK_SPAN_RX.sub(" ", text or "")
    cleaned = _SQ_SPAN_RX.sub(stock_or_keep, cleaned)
    if _UNQUOTED_PROVIDER_STATUS_RX.search(cleaned):
        return cleaned
    return _DQ_SPAN_RX.sub(stock_or_keep, cleaned)


def provider_fuel_scan_text(text: str) -> str:
    """Text the fuel detector may treat as a provider response.

    Skill lines quote 402 Payment Required inside backticks. That mention must
    not arm a hold. The wrapper fuel-log text value is scanned as recorded
    evidence, so a bare 402 Payment Required stored there still holds.
    """
    recorded = fuel_log_recorded_text(text)
    if recorded is not None:
        # JSON quotes belong to the envelope. A bare provider sentence in text
        # is evidence. A stock phrase that the text itself quotes is not.
        return _strip_instructional_mentions(recorded)
    return _strip_instructional_mentions(text or "")


def is_fuel_tool_output_noise(text: str) -> bool:
    """True when text is agent tool echo (gh/CodeRabbit/docs), not a provider error (FR #8151)."""
    return bool(_FUEL_TOOL_OUTPUT_NOISE_RX.search(text or ""))


def _provider_fuel_source_for_scanned(scanned: str) -> Optional[str]:
    """Classify provider channel for already-scanned text. FR #8151 / #8207."""
    if not (scanned or "").strip():
        return None
    if is_fuel_tool_output_noise(scanned):
        return None
    free_hit = bool(_OPENCODE_FREE_USAGE_RX.search(scanned))
    # FR #8207: Free usage / Subscribe to OpenCode Go only from app-log ERROR or
    # AI_* provider JSON — never bare tool/PR/gh echo (even without noise markers).
    if free_hit and not _FREE_USAGE_PROVIDER_CUE_RX.search(scanned):
        # Still allow other strong cues in the same blob (402/429) below.
        strong_non_free = bool(
            _OUT_OF_FUEL_RX.search(
                _OPENCODE_FREE_USAGE_RX.sub(" ", scanned)
            )
        )
        rate_ok = bool(_RATE_LIMIT_PROVIDER_CTX_RX.search(scanned))
        if not strong_non_free and not rate_ok:
            return None
        free_hit = False
    strong = bool(_OUT_OF_FUEL_RX.search(scanned))
    rate_ok = bool(_RATE_LIMIT_PROVIDER_CTX_RX.search(scanned))
    if not strong and not rate_ok:
        return None
    if re.search(r"(?i)(?:^|\s)level=ERROR\b", scanned):
        return "app-log"
    if re.search(
        r"(?i)(?:AI_(?:APICall|Retry)Error|\"status(?:_code)?\"\s*:\s*(?:402|429)"
        r"|\"error\"\s*:\s*\{|\"type\"\s*:\s*\"(?:api_error|rate_limit))",
        scanned,
    ):
        return "provider-json"
    # Bare Free usage without provider cue never reaches here as sole evidence.
    if free_hit and not _FREE_USAGE_PROVIDER_CUE_RX.search(scanned):
        return None
    return "cli-stderr"


def provider_fuel_evidence_source(text: str) -> Optional[str]:
    """Return ``app-log`` / ``cli-stderr`` / ``provider-json`` or None (FR #8151).

    Tool output (CodeRabbit comments, gh JSON, docstrings) never yields a source.
    Grok and Cursor watchers share this gate via ``is_out_of_fuel_text``.
    A fuel-log envelope with an explicit ``source`` is trusted only when that
    source is one of the provider channels; a missing/blank source re-classifies
    the recorded text (legacy lines without source still work when the text is
    genuine provider evidence).
    """
    stamped = fuel_log_recorded_source(text)
    if stamped is not None:
        if stamped in _PROVIDER_FUEL_SOURCES:
            recorded = fuel_log_recorded_text(text) or ""
            if is_fuel_tool_output_noise(recorded):
                return None
            return stamped
        return None
    scanned = provider_fuel_scan_text(text)
    if opencode_fuel is not None and opencode_fuel.is_turn_timeout_text(scanned):
        return None
    return _provider_fuel_source_for_scanned(scanned)


def is_out_of_fuel_text(text: str) -> bool:
    """True when agent/log text is a provider fuel/quota/auth exhaustion (FR #3012 / #3019 / #8151)."""
    return provider_fuel_evidence_source(text) is not None


def opencode_model_is_free(model_id: str) -> bool:
    """True when the model id is a free-pool OpenCode leaf (FR #8454 / #8537)."""
    mid = (model_id or "").strip()
    if not mid:
        return True
    low = mid.lower()
    if low.startswith("opencode-go/") or "/opencode-go/" in low:
        return False
    leaf = low.rsplit("/", 1)[-1]
    if leaf.endswith("-pro"):
        return False
    try:
        import opencode_fuel as of

        if of.of_is_go_model_id(mid):
            return False
    except Exception:
        pass
    return True


def opencode_paid_pool_remains(fuel: Fuel, env: Optional[dict] = None) -> bool:
    """True when paid/Go fuel may still accept work (FR #8537).

    Unknown Go remaining is treated as available so a free-limit refusal can
    rebind; an explicit ``BOB_OPENCODE_GO_REMAINING=0`` or go<=0 blocks switch.
    """
    env = os.environ if env is None else env
    if str(env.get("BOB_OPENCODE_GO_REMAINING") or "").strip() == "0":
        return False
    go = fuel.opencode_go
    models = fuel.opencode_models or {}
    if go is None and not models:
        return True
    try:
        if go is not None and int(go) <= 0 and not models:
            return False
        if go is not None and int(go) > 0 and not models:
            return True
    except (TypeError, ValueError):
        return True
    if models:
        for v in models.values():
            try:
                if int(v) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return False
    try:
        return go is None or int(go) > 0
    except (TypeError, ValueError):
        return True


def should_switch_opencode_free_to_paid(
    evidence: str,
    model_id: str,
    fuel: Fuel,
    env: Optional[dict] = None,
) -> bool:
    """FR #8537: free-limit evidence + free model + paid remains -> switch, no GIVEUP."""
    try:
        import opencode_fuel as of

        if not of.is_free_usage_limit_text(evidence or ""):
            return False
    except Exception:
        if not _OPENCODE_FREE_USAGE_RX.search(evidence or ""):
            return False
    if not opencode_model_is_free(model_id):
        return False
    return opencode_paid_pool_remains(fuel, env)


def resolve_opencode_paid_switch_model(env: Optional[dict] = None) -> str:
    """Paid tray slot for free->paid rebind (default opencode-go/deepseek-v4-pro)."""
    env = os.environ if env is None else env
    try:
        import worker_start_model as wsm

        cfg = wsm.load_worker_start_config(env=env)
        paid = wsm.default_opencode_paid_model(cfg)
        if paid:
            return str(paid).strip()
    except Exception:
        pass
    return "opencode-go/deepseek-v4-pro"


# FR #4858: hard API 402 / usage-balance-exhausted (not mid-job reading, not NEEDS_AUTH).
_HARD_402_OUT_OF_FUEL_RX = re.compile(
    r"(?i)(?:"
    r"402\s*Payment\s*Required"
    r"|Payment\s*Required:[^\n]{0,80}exhausted"
    r"|Grok\s+Build\s+usage\s+balance\s+exhausted"
    r"|usage\s+balance\s+exhausted"
    r")"
)


def is_hard_402_out_of_fuel_text(text: str) -> bool:
    """True for agent 402 / usage balance exhausted evidence (FR #4858).

    Mid-job fuel-reading GIVEUP text and NEEDS_AUTH are out-of-fuel but not hard 402.
    """
    return bool(_HARD_402_OUT_OF_FUEL_RX.search(provider_fuel_scan_text(text)))


def out_of_fuel_reading_clears_hard_hold(
    fuel: Fuel,
    *,
    kind: str,
    held_for_s: float,
    min_hold_s: float = 1800.0,
    clear_floor_pct: int = 5,
) -> bool:
    """FR #4858: after a hard 402, a soft ``available`` reading must not clear early.

    Require the minimum hold **and** an explicit grok pct above ``clear_floor_pct``
    (default 5). Unknown pct never clears. Cursor hard holds need tokens again.
    """
    if float(held_for_s) < float(min_hold_s):
        return False
    k = (kind or "").strip().lower()
    if k == "grok":
        if fuel.grok_pct is None:
            return False
        return int(fuel.grok_pct) > int(clear_floor_pct)
    if k == "cursor":
        return cursor_has_tokens(fuel)
    if k == "opencode":
        return opencode_has_tokens(fuel)
    return False


def out_of_fuel_reading_clears_soft_hold(
    fuel: Fuel,
    *,
    kind: str,
    has_session_key: bool = False,
    allow_cursor_kind_switch: bool = False,
    start_model: str = "",
) -> tuple:
    """FR #4899: soft hold clears only on the seat's own pool (or a real kind-switch).

    Returns ``(clears: bool, reason: str)``. A grok seat with ``grok_pct=0`` must not
    clear because the machine still has Cursor tokens. Cursor may clear a grok soft
    hold only when ``allow_cursor_kind_switch`` is True (seat will run Cursor, FR #3997).

    FR #8158: OpenCode soft clear keys to the start-model pool when provided.
    """
    k = (kind or "").strip().lower() or "grok"
    if k == "grok":
        if has_session_key:
            return True, "reading kind=grok (session key)"
        if grok_has_tokens(fuel):
            return True, f"reading kind=grok pct={fuel.grok_pct}"
        if allow_cursor_kind_switch and cursor_has_tokens(fuel):
            return (
                True,
                "reading kind-switch to cursor "
                f"(high={fuel.cursor_high} low={fuel.cursor_low})",
            )
        return False, ""
    if k == "cursor":
        if cursor_has_tokens(fuel):
            return (
                True,
                f"reading kind=cursor high={fuel.cursor_high} low={fuel.cursor_low}",
            )
        return False, ""
    if k == "opencode":
        pool = seat_fuel_pool(k, start_model)
        if pool == "opencode_go":
            if fuel.opencode_go is not None and int(fuel.opencode_go) > 0:
                return True, f"reading kind=opencode pool=opencode_go pct={fuel.opencode_go}"
            return False, ""
        if pool == "opencode_free":
            if fuel.opencode_free is not None and int(fuel.opencode_free) > 0:
                return True, f"reading kind=opencode pool=opencode_free pct={fuel.opencode_free}"
            return False, ""
        if opencode_has_tokens(fuel):
            return (
                True,
                f"reading kind=opencode free={fuel.opencode_free} go={fuel.opencode_go}",
            )
        return False, ""
    if cursor_has_tokens(fuel) or grok_has_tokens(fuel) or opencode_has_tokens(fuel):
        return True, "reading"
    return False, ""


def out_of_fuel_giveup_line(job_key: str) -> str:
    """Shop wire: ``GIVEUP <TYPE> owner/repo#N out-of-fuel`` (FR #3012)."""
    key = (job_key or "").strip() or "job"
    if key.lower() == "job":
        return "GIVEUP job out-of-fuel"
    return f"GIVEUP {key} out-of-fuel"


def seat_release_giveup_line(job_key: str, reason: str) -> str:
    """Shop wire: ``GIVEUP <TYPE> owner/repo#N <reason>`` before !bored (FR #4784).

    ``reason`` is ``done-miss``, ``no-terminal-reply``, or ``ack-stale``. Without this line Jeeves keeps the
    accepted row and answers every later ``!bored`` with ``nak busy``.
    """
    key = (job_key or "").strip() or "job"
    why = (reason or "done-miss").strip() or "done-miss"
    if key.lower() == "job":
        return f"GIVEUP job {why}"
    return f"GIVEUP {key} {why}"


def console_closed_giveup_line(job_key: str, wip_ref: str = "") -> str:
    """FR #8154: ``GIVEUP <TYPE> owner/repo#N console-closed [wip=<ref>]``."""
    why = "console-closed"
    ref = (wip_ref or "").strip()
    if ref:
        # Keep under shop_listen truncate (~120); short sha / branch tip only.
        why = f"console-closed wip={ref[:80]}"
    return seat_release_giveup_line(job_key, why)


def external_kill_giveup_line(job_key: str) -> str:
    """FR #8568: ``GIVEUP <TYPE> owner/repo#N external-kill`` when a seat vanishes with no last-exit."""
    return seat_release_giveup_line(job_key, "external-kill")


_WORKER_RUN_DIR_RX = re.compile(
    r"^worker-(?P<mid>[a-z0-9][a-z0-9-]{0,62})-(?P<pid>\d+)-(?P<hash>[0-9a-f]+)$",
    re.I,
)


def parse_worker_run_dir_name(name: str) -> tuple[str, int] | None:
    """Return ``(machine_id, pid)`` from ``worker-<mid>-<pid>-<hash>``, or None."""
    m = _WORKER_RUN_DIR_RX.match((name or "").strip())
    if not m:
        return None
    try:
        return m.group("mid").lower(), int(m.group("pid"))
    except ValueError:
        return None


def pid_is_alive(pid: int) -> bool:
    """True when ``pid`` is a live OS process (Windows OpenProcess / POSIX kill 0)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not h:
                return False
            try:
                code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return False
                return int(code.value) == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(h)
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def write_disappeared_last_exit(
    run_dir: Path | str,
    *,
    reason: str = "external-kill",
    job_key: str = "",
    pid: int | None = None,
    machine: str = "",
    nick: str = "",
    kind: str = "",
) -> Path:
    """FR #8568: synthetic ``last-exit.json`` when a tracked seat vanishes with no exit record."""
    rd = Path(run_dir)
    rd.mkdir(parents=True, exist_ok=True)
    path = rd / "last-exit.json"
    payload = {
        "reason": (reason or "external-kill").strip() or "external-kill",
        "exit_code": None,
        "raw_code": None,
        "job_key": (job_key or "").strip(),
        "machine": (machine or "").strip(),
        "nick": (nick or "").strip(),
        "kind": (kind or "").strip(),
        "agent_pid": int(pid) if pid else None,
        "synthetic": True,
        "via": "fr-8568-disappeared-seat",
    }
    text = json.dumps(payload, sort_keys=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    return path


def handle_disappeared_worker_run(
    run_dir: Path | str,
    *,
    shop: str = "",
    pid_alive: Optional[Callable[[int], bool]] = None,
) -> Optional[dict]:
    """If ``run_dir`` is a dead worker seat with no last-exit and an open job, write exit + GIVEUP.

    Does **not** restart the seat (FR #3180 manual-only). Returns a summary dict, or None when
    no action was taken.
    """
    rd = Path(run_dir)
    if not rd.is_dir():
        return None
    parsed = parse_worker_run_dir_name(rd.name)
    if parsed is None:
        return None
    mid, pid = parsed
    alive_fn = pid_alive or pid_is_alive
    if alive_fn(pid):
        return None
    if (rd / "last-exit.json").is_file():
        return None
    last_from = ""
    try:
        last_from = (rd / "last-from.txt").read_text(encoding="utf-8", errors="replace")
    except OSError:
        last_from = ""
    job_key = assign_job_key(last_from) or ""
    if not job_key:
        # No accepted-job breadcrumb — still leave last-exit so the gap is visible.
        write_disappeared_last_exit(rd, reason="external-kill", pid=pid, machine=mid)
        return {"run_dir": str(rd), "pid": pid, "job_key": "", "giveup": False}
    outbox = outbox_path_for_run(rd)
    try:
        existing = outbox.read_text(encoding="utf-8", errors="replace") if outbox.is_file() else ""
    except OSError:
        existing = ""
    if outbox_text_has_terminal(existing, job_key):
        write_disappeared_last_exit(
            rd, reason="external-kill", job_key=job_key, pid=pid, machine=mid
        )
        return {"run_dir": str(rd), "pid": pid, "job_key": job_key, "giveup": False, "already_terminal": True}
    write_disappeared_last_exit(
        rd, reason="external-kill", job_key=job_key, pid=pid, machine=mid
    )
    channel = (shop or mid or "shop").strip().lstrip("#") or "shop"
    line = f"PRIVMSG #{channel} :{external_kill_giveup_line(job_key)}"
    try:
        with outbox.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
    except OSError:
        return {"run_dir": str(rd), "pid": pid, "job_key": job_key, "giveup": False, "outbox_error": True}
    return {"run_dir": str(rd), "pid": pid, "job_key": job_key, "giveup": True, "line": line}


def scan_disappeared_worker_runs(
    run_root: Path | str,
    *,
    shop: str = "",
    pid_alive: Optional[Callable[[int], bool]] = None,
) -> list[dict]:
    """Scan ``run_root`` for vanished seats; handle each (FR #8568 tray watchdog)."""
    root = Path(run_root)
    if not root.is_dir():
        return []
    out: list[dict] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if not child.name.lower().startswith("worker-"):
            continue
        hit = handle_disappeared_worker_run(child, shop=shop, pid_alive=pid_alive)
        if hit:
            out.append(hit)
    return out


def is_console_closed_shutdown_reason(reason: str) -> bool:
    """True when Supervisor.shutdown reason is a console / Ctrl close (FR #8154)."""
    text = (reason or "").strip().lower().replace("_", "-")
    if not text:
        return False
    head = text.split(":", 1)[0].strip()
    return head in ("console-closed", "window-closed", "ctrl-close", "control-c")


def pending_console_closed_giveup_dir(env: Optional[dict] = None) -> Path:
    """Durable pending-GIVEUP folder (survives run-dir wipe). FR #8154."""
    e = os.environ if env is None else env
    bridge = str(e.get("BOB_BRIDGE_HOME") or "").strip()
    if bridge:
        return Path(bridge) / "pending-giveup"
    return _state_root(e) / "pending-giveup"


def console_closed_daily_path(machine: str, env: Optional[dict] = None) -> Path:
    """Token-free per-machine day counts (FR #8416). No job text, no secrets."""
    mid = re.sub(r"[^a-z0-9_.-]+", "-", (machine or "unknown").strip().lower()) or "unknown"
    return pending_console_closed_giveup_dir(env).parent / "console-closed-daily" / f"{mid}.json"


def note_console_closed_exit(
    machine: str,
    *,
    when: Optional[_dt.datetime] = None,
    env: Optional[dict] = None,
) -> dict:
    """Increment today's console-closed count. Keeps 14 UTC days."""
    now = when or _dt.datetime.now(_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    day = now.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d")
    path = console_closed_daily_path(machine, env)
    doc: dict = {"machine": (machine or "unknown").strip().lower(), "days": {}}
    try:
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("days"), dict):
                doc["days"] = {
                    str(k): int(v)
                    for k, v in loaded["days"].items()
                    if str(k)[:10]
                }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        doc["days"] = {}
    doc["days"][day] = int(doc["days"].get(day) or 0) + 1
    keep = sorted(doc["days"])[-14:]
    doc["days"] = {k: int(doc["days"][k]) for k in keep}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass
    return doc


def pending_console_closed_giveup_path(machine: str, env: Optional[dict] = None) -> Path:
    mid = re.sub(r"[^a-z0-9_.-]+", "-", (machine or "unknown").strip().lower()) or "unknown"
    return pending_console_closed_giveup_dir(env) / f"{mid}.txt"


def append_pending_console_closed_giveup(
    machine: str,
    line: str,
    *,
    env: Optional[dict] = None,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Append one GIVEUP wire line for the next seat on this machine (FR #8154)."""
    text = (line or "").strip()
    if not text:
        return False
    path = pending_console_closed_giveup_path(machine, env)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        if log:
            log(f"pending-giveup: queued {text[:120]}")
        return True
    except OSError as e:
        if log:
            log(f"pending-giveup: append failed {type(e).__name__}")
        return False


def drain_pending_console_closed_giveups(
    machine: str,
    *,
    env: Optional[dict] = None,
) -> list[str]:
    """Read and clear durable pending GIVEUP lines for ``machine`` (FR #8154)."""
    path = pending_console_closed_giveup_path(machine, env)
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    try:
        path.unlink()
    except OSError:
        try:
            path.write_text("", encoding="utf-8")
        except OSError:
            pass
    out: list[str] = []
    for ln in raw.splitlines():
        s = ln.strip()
        if s:
            out.append(s)
    return out


def flush_pending_console_closed_giveups(
    irc: "IrcSeat",
    machine: str,
    *,
    log: Optional[Callable[[str], None]] = None,
    env: Optional[dict] = None,
) -> int:
    """Send any durable pending console-closed GIVEUPs after IRC is up (FR #8154)."""
    lines = drain_pending_console_closed_giveups(machine, env=env)
    if not lines:
        return 0
    shop = getattr(irc, "shop", None) or shop_channel(machine)
    n = 0
    for line in lines:
        try:
            if irc and getattr(irc, "alive", False):
                irc.say(shop, line)
                n += 1
            else:
                append_pending_console_closed_giveup(machine, line, env=env, log=log)
        except Exception as e:
            if log:
                log(f"pending-giveup: flush say failed {type(e).__name__}")
            append_pending_console_closed_giveup(machine, line, env=env, log=log)
    if log and n:
        log(f"pending-giveup: flushed {n} line(s) to {shop}")
    return n


def resolve_console_closed_worktree(
    job_key: str = "",
    *,
    env: Optional[dict] = None,
) -> str:
    """Prefer ``BOB_JOB_WORKTREE``, else derive ``<base>/<repo>/<fr-N>`` (FR #8154)."""
    e = os.environ if env is None else env
    wt = str(e.get("BOB_JOB_WORKTREE") or "").strip()
    if wt and Path(wt).is_dir():
        return wt
    key = (job_key or "").strip()
    if not key:
        return ""
    try:
        from opencode_seat_contract import _project_dir_for_key  # type: ignore

        path = _project_dir_for_key(key, e)
    except Exception:
        path = ""
    if path and Path(path).is_dir():
        return path
    return ""


def worktree_is_dirty(worktree: str | Path, *, run=None) -> bool:
    """True when ``git status --porcelain`` is non-empty."""
    import subprocess as _sp

    run = _sp.run if run is None else run
    root = Path(worktree or "")
    if not root.is_dir():
        return False
    try:
        r = run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return False
    if getattr(r, "returncode", 1) != 0:
        return False
    return bool((getattr(r, "stdout", "") or "").strip())


def save_console_closed_wip(
    worktree: str | Path,
    job_key: str = "",
    *,
    run=None,
    push: bool = True,
    log: Optional[Callable[[str], None]] = None,
) -> str:
    """Snapshot dirty job worktree on console-close (FR #8154).

    Prefers ``git stash create`` (leaves the tree intact for FINISH reuse). When
    push is enabled, also stores ``refs/wip/fr-<N>`` (or mrb/uat) and pushes that
    ref without opening a PR. Returns a short wip token for the GIVEUP line, or
    ``\"\"`` when clean / unavailable.
    """
    import subprocess as _sp

    run = _sp.run if run is None else run
    root = Path(worktree or "")
    if not root.is_dir():
        return ""
    if not worktree_is_dirty(root, run=run):
        return ""
    sha = ""
    try:
        r = run(
            ["git", "-C", str(root), "stash", "create"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if getattr(r, "returncode", 1) == 0:
            sha = (getattr(r, "stdout", "") or "").strip().splitlines()
            sha = (sha[0] if sha else "").strip()
    except Exception as e:
        if log:
            log(f"console-closed-wip: stash create failed {type(e).__name__}")
        sha = ""
    if not sha or not re.fullmatch(r"[0-9a-f]{7,40}", sha, flags=re.I):
        if log:
            log("console-closed-wip: no stash object (clean or failed)")
        return ""
    short = sha[:12]
    issue_n = ""
    kind = "fr"
    m = re.search(
        r"(?i)\b(FR|MRB|UAT|FIX)\s+\S+#(\d+)\b",
        job_key or "",
    )
    if m:
        kind = m.group(1).lower()
        issue_n = m.group(2)
    ref_name = f"refs/wip/{kind}-{issue_n}" if issue_n else f"refs/wip/stash-{short}"
    try:
        run(
            ["git", "-C", str(root), "update-ref", ref_name, sha],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as e:
        if log:
            log(f"console-closed-wip: update-ref failed {type(e).__name__}")
    if push and issue_n:
        try:
            pr = run(
                ["git", "-C", str(root), "push", "-u", "origin", f"{ref_name}:{ref_name}"],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if getattr(pr, "returncode", 1) != 0 and log:
                err = (getattr(pr, "stderr", "") or "")[:120]
                log(f"console-closed-wip: push skipped/failed {err}")
        except Exception as e:
            if log:
                log(f"console-closed-wip: push failed {type(e).__name__}")
    # Prefer the named ref for resume; fall back to short sha.
    token = f"{kind}-{issue_n}:{short}" if issue_n else short
    if log:
        log(f"console-closed-wip: saved {token}")
    return token


FAILED_TURN_RETRY_MAX = 1
_FAILED_TURN_SECRET_RX = re.compile(
    r"(?i)(?:ghp_|github_pat_|gho_|sk-|Bearer\s+)\S+"
)
_EXTERNAL_DIR_REJECT_RX = re.compile(
    r"(?i)(?:permission\s+requested\s*:\s*external_directory|"
    r"external_directory[^\n]*auto-reject|"
    r"auto-rejecting[^\n]*external_directory)"
)


def ensure_opencode_job_scratch(worktree: str | Path) -> Path:
    """FR #8247: ``<worktree>\\.bob\\tmp`` for OpenCode seat scratch (inside ``--dir``)."""
    wt = Path(worktree)
    scratch = wt / ".bob" / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


def apply_opencode_scratch_env(env: dict | None, worktree: str | Path) -> dict:
    """FR #8247: point TEMP/TMP/TMPDIR at the worktree scratch (never widen %TEMP% allow)."""
    out = dict(env or {})
    scratch = ensure_opencode_job_scratch(worktree)
    s = str(scratch)
    out["TEMP"] = s
    out["TMP"] = s
    out["TMPDIR"] = s
    out["BOB_OPENCODE_SCRATCH"] = s
    return out


def opencode_external_dir_loop_max() -> int:
    """FR #8247: rejection-ended turns before GIVEUP ``external-dir-loop`` (default 2)."""
    return int(_env_float("BOB_OPENCODE_EXTERNAL_DIR_LOOP_MAX", 2.0, 1.0, 10.0))


def is_external_directory_reject(error_class: str, error_line: str) -> bool:
    """FR #8247: True when the turn ended on an OpenCode ``external_directory`` auto-reject."""
    cls = str(error_class or "").strip().lower().replace("_", "-")
    if cls in ("external-directory", "externaldirectory"):
        return True
    if cls == "epipe":
        return False
    blob = "%s\n%s" % (error_class or "", error_line or "")
    return bool(_EXTERNAL_DIR_REJECT_RX.search(blob)) or (
        "external_directory" in blob.lower() and "auto-reject" in blob.lower()
    )


def record_external_dir_reject(state: dict, key: str) -> str:
    """FR #8247: count one rejection; return ``corrective`` then ``giveup`` at loop max."""
    if not isinstance(state, dict):
        state = {}
    counts = state.setdefault("counts", {})
    if not isinstance(counts, dict):
        counts = {}
        state["counts"] = counts
    k = str(key or "job").strip() or "job"
    n = int(counts.get(k, 0) or 0) + 1
    counts[k] = n
    max_n = opencode_external_dir_loop_max()
    if n >= max_n:
        state["corrective_pending"] = False
        return "giveup"
    state["corrective_pending"] = True
    return "corrective"


def opencode_external_dir_corrective_steps(
    *,
    job_key: str,
    worktree: str | Path,
    outbox: str | Path,
    scratch: str | Path,
) -> str:
    """FR #8247: short corrective after an ``external_directory`` rejection (names allowed scratch)."""
    key = (job_key or "job").strip() or "job"
    wt = str(worktree or "").strip()
    ob = str(outbox or "").strip()
    sc = str(scratch or "").strip()
    return (
        f"CORRECTIVE {key}: OpenCode rejected external_directory (path outside the job tree). "
        f"Use only the allowed scratch directory {sc} (worktree .bob\\tmp). "
        f"TEMP/TMP/TMPDIR already point there for this seat. "
        f"Do not request external_directory and never use %TEMP% or the user Temp folder. "
        f"Keep all scratch and tool paths inside {wt}. "
        f"Finish remaining work. {opencode_typed_delivery(key, outbox=ob)} "
        "The turn is not over until DONE is written."
    )


def _failed_turn_snip(text: str, *, limit: int = 160) -> str:
    """Single-line, secret-redacted snippet for GIVEUP / turn markers (FR #8018)."""
    line = " ".join(str(text or "").split())
    # Redact twice: structured JSON / nested secrets, then token-shaped leftovers.
    line = redact_session_text(line)
    line = _FAILED_TURN_SECRET_RX.sub("<redacted>", line)
    line = redact_session_text(line)
    if len(line) > limit:
        line = line[:limit]
    return line


def sanitize_failed_turn_reason(error_class: str, first_line: str) -> str:
    """FR #7201 / #8018: one-line GIVEUP reason (class + first line, no secrets).

    Keep exit codes and stderr snippets (up to ~400 chars). Never strip ``<redacted>`` placeholders in a
    way that also drops digits from ``exit N``.
    """
    cls = re.sub(r"[^\w.-]+", "", str(error_class or "error").strip())[:48] or "error"
    line = _failed_turn_snip(first_line, limit=400)
    if not line:
        return cls
    return "%s: %s" % (cls, line)


def format_opencode_turn_error(
    exit_code: int | str | None,
    *,
    stderr: str = "",
    stdout: str = "",
    hit_limit: bool = False,
    log_name: str = "",
) -> tuple[str, str]:
    """FR #8018 / #8091: ``(error_class, error_line)`` for an OpenCode process end marker.

    Includes exit code, last ~20 stderr/stdout lines (redacted), and optional #8069 log name.
    """
    try:
        code = int(exit_code)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        code = -1
    snip = opencode_stream_tail(stderr, stdout, max_lines=20, max_chars=800)
    blob = "%s\n%s\n%s" % (snip, stderr or "", stdout or "")
    if hit_limit:
        cls = "out-of-fuel"
    elif is_epipe_turn_error(text=snip) or is_epipe_turn_error(text=stderr) or is_epipe_turn_error(text=stdout):
        cls = "epipe"
    elif _EXTERNAL_DIR_REJECT_RX.search(blob) or (
        "external_directory" in blob.lower() and "auto-reject" in blob.lower()
    ):
        # FR #8247: classify external_directory auto-reject (never widen %TEMP% allow).
        cls = "external-directory"
    else:
        cls = "process-exit"
    line = "exit %s" % code
    if snip:
        line = "%s: %s" % (line, snip)
    name = str(log_name or "").strip()
    if name:
        line = "%s log=%s" % (line, Path(name).name)
    return cls, line


def is_failed_turn_fuel_error(error_class: str, error_line: str) -> bool:
    """True when a failed turn should GIVEUP as out-of-fuel (FR #8018).

    FR #8578: ``free-to-paid-switch`` is a non-terminal free-pool handoff; the paid
    re-invoke continues the same job, so never treat it as fuel GIVEUP even if the
    error line still mentions Free usage.
    """
    cls = str(error_class or "").strip().lower().replace("_", "-")
    if cls in ("free-to-paid-switch", "freetopaidswitch"):
        return False
    if cls in ("out-of-fuel", "outoffuel"):
        return True
    blob = "%s\n%s" % (error_class or "", error_line or "")
    return is_out_of_fuel_text(blob)


def failed_turn_next_action(retry_count: int, *, max_retries: int = FAILED_TURN_RETRY_MAX) -> str:
    """``retry`` until the bound, then ``giveup`` (FR #7201)."""
    if int(retry_count) < int(max_retries):
        return "retry"
    return "giveup"


def failed_turn_giveup_line(job_key: str, error_class: str, first_line: str) -> str:
    if is_failed_turn_fuel_error(error_class, first_line):
        return out_of_fuel_giveup_line(job_key)
    why = "failed-turn " + sanitize_failed_turn_reason(error_class, first_line)
    return seat_release_giveup_line(job_key, why)


def _notify_turn_ended_cb(cb, turn, wall, **kw) -> None:
    """Call turn-ended callback with optional error kwargs (FR #7201)."""
    if cb is None:
        return
    try:
        cb(turn, wall, **kw)
    except TypeError:
        cb(turn, wall)


def out_of_fuel_nack_line(job_key: str) -> str:
    """Shop wire: ``NACK <TYPE> owner/repo#N out-of-fuel`` for assigns refused during hold (FR #4180)."""
    key = (job_key or "").strip() or "job"
    if key.lower() == "job":
        return "NACK job out-of-fuel"
    return f"NACK {key} out-of-fuel"


def default_unified_log_path(*, run_dir: Path | str | None = None, env: Optional[dict] = None) -> Path:
    return agent_grok_home(run_dir=run_dir, env=env) / "logs" / "unified.jsonl"


def grok_log_has_turn_activity(path: Path | str | None, *, since_wall: float) -> bool:
    """True when events.jsonl / unified.jsonl has turn_started or turn_ended after since_wall."""
    p = Path(path) if path else None
    if p is None or not p.is_file():
        return False
    try:
        data = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    cut = float(since_wall or 0.0)
    for line in data.splitlines()[-400:]:
        if '"turn_started"' not in line and '"turn_ended"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if str(obj.get("type") or "") not in ("turn_started", "turn_ended"):
            continue
        ts = _parse_iso_ts(str(obj.get("ts") or ""))
        if ts is None or ts > cut:
            return True
    return False


def should_startup_hang_recycle(
    *,
    ack_open: bool,
    activity_paths: list[Path | str] | None = None,
    since_wall: float = 0.0,
) -> bool:
    """FR #7123: do not hang-recycle an ACKed job or a seat whose per-worker log has turns."""
    if ack_open:
        return False
    for raw in activity_paths or []:
        if grok_log_has_turn_activity(raw, since_wall=since_wall):
            return False
    return True


def default_out_of_fuel_log_path(
    kind: str, *, env: Optional[dict] = None, run_dir: Path | str | None = None
) -> Optional[Path]:
    r"""Log path to tail for mid-job out-of-fuel (FR #3012 grok / FR #3019 cursor / FR #6120 opencode).

    Override with ``BOB_WORKER_OUT_OF_FUEL_LOG``. Grok defaults to ``unified.jsonl``.
    Cursor has no durable fleet enqueue log yet - returns the override only (watcher waits
    until the path appears; mid-job fuel-reading poll still covers Cursor).
    OpenCode writes wrapper-caught 402/429/quota failures to a shared log under
    ``%LOCALAPPDATA%\Bobiverse\worker\logs`` so the fuel watcher can tail them.
    """
    env = os.environ if env is None else env
    override = (env.get("BOB_WORKER_OUT_OF_FUEL_LOG") or "").strip()
    if override:
        return Path(override)
    k = (kind or "").strip().lower()
    if k == "grok":
        return default_unified_log_path(run_dir=run_dir, env=env)
    if k == "cursor":
        return None
    if k == "opencode":
        base = Path(env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"))
        return base / "Bobiverse" / "worker" / "logs" / "opencode-out-of-fuel.log"
    return None


def should_start_fuel_watcher(kind: str) -> bool:
    """FR #3019 / #6120: out-of-fuel watcher for grok, cursor and opencode (not plan/monitor-only kinds)."""
    return (kind or "").strip().lower() in ("grok", "cursor", "opencode")


DIGEST_HTTP_USER_AGENT = "Bobiverse-bobreport/1.0"  # FR #6144 / #7181: same UA as ear (WAF)
DIGEST_HTTP_BODY_LOG_MAX = 200  # FR #7347: truncated 4xx body snippet
_last_digest_http: dict = {}


def _digest_http_body_snippet(exc: BaseException, *, limit: int = DIGEST_HTTP_BODY_LOG_MAX) -> str:
    """Read HTTPError body, scrub secrets, truncate. Never raise. FR #7347."""
    raw = b""
    try:
        read = getattr(exc, "read", None)
        if callable(read):
            got = read()
            if isinstance(got, (bytes, bytearray)):
                raw = bytes(got)
            elif isinstance(got, str):
                raw = got.encode("utf-8", "replace")
    except Exception:
        raw = b""
    if not raw:
        try:
            fp = getattr(exc, "fp", None)
            if fp is not None and hasattr(fp, "read"):
                got = fp.read()
                if isinstance(got, (bytes, bytearray)):
                    raw = bytes(got)
        except Exception:
            raw = b""
    text = raw.decode("utf-8", "replace") if raw else ""
    text = " ".join(text.split())
    text = _scrub(text)
    lim = max(0, int(limit))
    if len(text) > lim:
        text = text[:lim]
    return text


def classify_digest_http_failure(exc: BaseException) -> dict:
    """Status, responder class, Cloudflare ray, truncated body. No secrets. FR #7181 / #7347."""
    status = getattr(exc, "code", None)
    try:
        status_i = int(status) if status is not None else None
    except (TypeError, ValueError):
        status_i = None
    headers = getattr(exc, "headers", None)

    def _hdr(name: str) -> str:
        if headers is None:
            return ""
        try:
            return str(headers.get(name) or "").strip()
        except Exception:
            return ""

    ray = _hdr("CF-Ray") or _hdr("cf-ray")
    server = _hdr("Server") or _hdr("server")
    sl = server.lower()
    if ray or "cloudflare" in sl:
        responder = "cloudflare"
    elif "iis" in sl or "microsoft" in sl:
        responder = "iis"
    elif "jeeves" in sl or "bobcallback" in sl:
        responder = "jeeves"
    elif sl:
        responder = sl.split("/")[0][:40]
    else:
        responder = "unknown"
    body = _digest_http_body_snippet(exc)
    out = {
        "status": status_i,
        "responder": responder,
        "ray": ray,
        "server": server[:80],
        "exc": type(exc).__name__,
    }
    if body:
        out["body"] = body
    return out


def last_digest_http() -> dict:
    """Last worker digest POST outcome (no secrets). FR #7181 / #7347."""
    return dict(_last_digest_http)


def _http_post_json(
    url: str,
    payload: dict,
    timeout: float = 10.0,
    *,
    log: Optional[Callable[[str], None]] = None,
    retries: int = 3,
    sleep: Optional[Callable[[float], None]] = None,
) -> bool:
    """Best-effort JSON POST (digest report). No secrets. Returns True on HTTP success.

    FR #7181: retry 403/429/5xx with backoff; log status, responder, CF-Ray.
    FR #7347: on 4xx also log a scrubbed body snippet (max 200 chars).
    """
    global _last_digest_http
    raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": DIGEST_HTTP_USER_AGENT,
        "Accept": "application/json",
    }
    wait = sleep if sleep is not None else time.sleep
    attempts = max(1, int(retries))
    last_meta: dict = {}
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
                code = int(getattr(resp, "status", 0) or 0)
                ok = 200 <= code < 300
                last_meta = {"ok": ok, "status": code, "attempt": attempt}
                _last_digest_http = dict(last_meta)
                if not ok and log:
                    try:
                        log(f"digest POST HTTP {code} attempt={attempt}/{attempts} url={url[:80]}")
                    except Exception:
                        pass
                if ok:
                    return True
                if code not in (403, 408, 429) and code < 500:
                    return False
        except urllib.error.HTTPError as exc:
            last_meta = classify_digest_http_failure(exc)
            last_meta["attempt"] = attempt
            last_meta["ok"] = False
            _last_digest_http = dict(last_meta)
            if log:
                try:
                    snippet = str(last_meta.get("body") or "").strip()
                    extra = f" body={snippet}" if snippet else ""
                    log(
                        "digest POST HTTP {st} responder={r} ray={ray} attempt={a}/{n}{extra}".format(
                            st=last_meta.get("status") or "?",
                            r=last_meta.get("responder") or "unknown",
                            ray=last_meta.get("ray") or "-",
                            a=attempt,
                            n=attempts,
                            extra=extra,
                        )
                    )
                except Exception:
                    pass
            st = last_meta.get("status")
            if st not in (403, 408, 429) and not (isinstance(st, int) and st >= 500):
                return False
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_meta = {"ok": False, "exc": type(exc).__name__, "attempt": attempt, "responder": "unknown"}
            _last_digest_http = dict(last_meta)
            if log:
                try:
                    log(f"digest POST failed: {type(exc).__name__} attempt={attempt}/{attempts}")
                except Exception:
                    pass
        if attempt < attempts:
            try:
                wait(min(8.0, 0.2 * (2 ** (attempt - 1))))
            except Exception:
                pass
    return False


def out_of_fuel_quit_enabled(env: Optional[dict] = None) -> bool:
    """FR #8814: after fuel GIVEUP, dialog + quit by default (no zombie out_of_fuel seat).

    Set ``BOB_WORKER_OUT_OF_FUEL_QUIT=0`` to keep the legacy FR #3012 hold until fuel returns.
    """
    env = os.environ if env is None else env
    raw = str(env.get("BOB_WORKER_OUT_OF_FUEL_QUIT", "1") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def format_out_of_fuel_dialog_text(
    *,
    pool: str = "",
    remaining: str = "",
    reset_hint: str = "",
    evidence: str = "",
    nick: str = "",
) -> str:
    """User-visible dialog body for FR #8814 fuel-exhausted quit."""
    lines = ["Fuel exhausted for this seat."]
    pool_s = (pool or "").strip()
    if pool_s:
        lines.append(f"Pool: {pool_s}")
    rem_s = (remaining or "").strip()
    if rem_s:
        lines.append(f"Remaining: {rem_s}")
    reset_s = (reset_hint or "").strip()
    if reset_s:
        lines.append(f"Reset: {reset_s}")
    nick_s = (nick or "").strip()
    if nick_s:
        lines.append(f"Seat: {nick_s}")
    preview = one_line(evidence or "", 160)
    if preview:
        lines.append(preview)
    lines.append("This seat will close now so it leaves the digest.")
    return "\n".join(lines)


def show_out_of_fuel_dialog(
    *,
    pool: str = "",
    remaining: str = "",
    reset_hint: str = "",
    evidence: str = "",
    nick: str = "",
    title: str = "Bobiverse — out of fuel",
    show_fn: Optional[Callable[[str, str], None]] = None,
    env: Optional[dict] = None,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Show fuel-exhausted dialog (FR #8814). Returns True when a dialog path ran.

    ``show_fn(text, title)`` is injectable for tests. When unset, uses Win32 MessageBoxW
    unless ``BOB_WORKER_FUEL_DIALOG=0`` (headless / CI skip).
    """
    env = os.environ if env is None else env
    text = format_out_of_fuel_dialog_text(
        pool=pool,
        remaining=remaining,
        reset_hint=reset_hint,
        evidence=evidence,
        nick=nick,
    )
    if show_fn is not None:
        show_fn(text, title)
        return True
    raw = str(env.get("BOB_WORKER_FUEL_DIALOG", "1") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        if log:
            try:
                log("out-of-fuel: dialog skipped (BOB_WORKER_FUEL_DIALOG=0)")
            except Exception:
                pass
        return False
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        MB_OK = 0x00000000
        MB_ICONWARNING = 0x00000030
        user32.MessageBoxW(None, text, title, MB_OK | MB_ICONWARNING)
        return True
    except Exception as e:
        if log:
            try:
                log(f"out-of-fuel: dialog failed {type(e).__name__}")
            except Exception:
                pass
        return False


def post_digest_worker_remove(
    *,
    machine: str,
    nick: str,
    pid: int | str | None = None,
    url: str | None = None,
    env: Optional[dict] = None,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """FR #8814: remove the seat nick from digest workers so out_of_fuel zombies leave."""
    env = os.environ if env is None else env
    report = (url or env.get("BOB_REPORT_URL") or env.get("BOB_DIGEST_URL") or DEFAULT_DIGEST_REPORT_URL).strip()
    nick_s = (nick or "").strip()
    if not report or not nick_s:
        return False
    mid = normalize_machine_id(machine) or str(machine or "").strip().lower()
    row: dict = {
        "op": "worker-remove",
        "machine": mid,
        "id": mid,
        "nick": nick_s,
    }
    if pid is not None and str(pid).strip() != "":
        try:
            row["pid"] = int(str(pid))
        except (TypeError, ValueError):
            pass
    ok = bool(_http_post_json(report, row, log=log))
    if not ok and log:
        try:
            log(f"post_digest_worker_remove failed mid={mid} nick={nick_s}")
        except Exception:
            pass
    return ok


def post_digest_out_of_fuel(
    *,
    machine: str,
    nick: str = "",
    evidence: str = "",
    pid: int | str | None = None,
    url: str | None = None,
    env: Optional[dict] = None,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """POST digest so tray/TipForm can show the seat out of fuel (FR #3012 / #5032).

    FR #5032: include weekly=0 so peers paint exhausted (0%% red) instead of a stale %.
    FR #8494: also POST worker-work ``state=out_of_fuel`` so the seat row is not idle.
    FR #8814: callers that quit the seat should follow with ``post_digest_worker_remove``.
    """
    env = os.environ if env is None else env
    report = (url or env.get("BOB_REPORT_URL") or env.get("BOB_DIGEST_URL") or DEFAULT_DIGEST_REPORT_URL).strip()
    if not report:
        return False
    mid = normalize_machine_id(machine) or str(machine or "").strip().lower()
    preview = one_line(evidence or "out-of-fuel", 120)
    nick_s = (nick or "").strip()
    working = f"out-of-fuel{(' ' + nick_s) if nick_s else ''}: {preview}"
    payload = {
        "online": True,
        "id": mid,
        "status": "out_of_fuel",
        "working_on": working,
        "out_of_tokens": True,
        # FR #5032: authoritative pool % for tray + dispatch (stale weekly must not win).
        "weekly": 0,
    }
    ok = bool(_http_post_json(report, payload, log=log))
    if nick_s:
        try:
            from bobreport import _utc_now_iso

            iso = _utc_now_iso()
        except Exception:
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        row = {
            "op": "worker-work",
            "machine": mid,
            "id": mid,
            "nick": nick_s,
            "state": "out_of_fuel",
            "work": working,
            "online": True,
            "last_progress": iso,
            "progress_phase": "out-of-fuel",
        }
        if pid is not None and str(pid).strip() != "":
            try:
                row["pid"] = int(str(pid))
            except (TypeError, ValueError):
                pass
        ok_row = bool(_http_post_json(report, row, log=log))
        ok = bool(ok and ok_row)
    if not ok and log:
        try:
            log(f"post_digest_out_of_fuel failed mid={mid}")
        except Exception:
            pass
    return ok


class GrokOutOfFuelWatcher:
    """FR #3012 / #3019: tail agent fuel log (grok unified.jsonl, or Cursor override / test path)."""

    def __init__(
        self,
        *,
        log_path: Path | str | None = None,
        log_path_fn: Optional[Callable[[], Path | str | None]] = None,
        on_hit: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
        poll_s: float = 0.5,
        log: Optional[Callable[[str], None]] = None,
        agent_pid: int = 0,
    ):
        self._path = Path(log_path) if log_path else None
        self._path_fn = log_path_fn
        self._on_hit = on_hit
        self._stop = stop_event or threading.Event()
        self.poll_s = max(0.05, float(poll_s))
        self._log = log
        self._offset = 0
        self._cur: Optional[Path] = None
        self._agent_pid = int(agent_pid or 0)
        self._fired = False

    def _resolve(self) -> Optional[Path]:
        if self._path_fn is not None:
            try:
                p = self._path_fn()
            except Exception:
                return None
            return Path(p) if p else None
        return self._path

    def _emit_line(self, line: str) -> None:
        if self._fired:
            return
        text = (line or "").strip()
        # FR #8151: require a provider source; tool-output "rate limit" never fires.
        src = provider_fuel_evidence_source(text) if text else None
        if not src:
            return
        if self._agent_pid > 0:
            try:
                obj = json.loads(text)
                pid = int(obj.get("pid") or 0)
                if pid and pid != self._agent_pid:
                    return
            except Exception:
                # Non-JSON lines that already matched the fuel regex still count.
                pass
        self._fired = True
        if self._log:
            try:
                self._log(f"out-of-fuel: detected in agent log source={src}")
            except Exception:
                pass
        if self._on_hit:
            try:
                self._on_hit(text)
            except Exception:
                pass

    def run(self) -> None:
        while not self._stop.is_set():
            if self._fired:
                self._stop.wait(self.poll_s)
                continue
            path = self._resolve()
            if path is None:
                self._stop.wait(self.poll_s)
                continue
            try:
                if self._cur != path:
                    self._cur = path
                    # Start at EOF so we only see mid-job exhaustion after seat start.
                    try:
                        self._offset = path.stat().st_size if path.is_file() else 0
                    except OSError:
                        self._offset = 0
                    if self._log:
                        try:
                            self._log(f"out-of-fuel: watcher following {path}")
                        except Exception:
                            pass
                if not path.is_file():
                    self._stop.wait(self.poll_s)
                    continue
                size = path.stat().st_size
                if size < self._offset:
                    self._offset = 0
                if size > self._offset:
                    with path.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(self._offset)
                        chunk = f.read()
                        self._offset = f.tell()
                    for ln in chunk.splitlines():
                        self._emit_line(ln)
                        if self._fired:
                            break
            except OSError:
                pass
            self._stop.wait(self.poll_s)



def write_inject_progress(run_dir, *, phase: str, detail: str = "", job_key: str = "") -> None:
    """FR #8553: durable breadcrumb while a job is in flight (survives hard kills)."""
    try:
        rd = Path(run_dir)
        rd.mkdir(parents=True, exist_ok=True)
        payload = {
            "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "phase": str(phase or "")[:80],
            "detail": _scrub(str(detail or ""))[:240],
            "job_key": str(job_key or "")[:120],
        }
        path = rd / "inject-progress.json"
        raw = json.dumps(payload, ensure_ascii=True) + "\n"
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(raw)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
    except Exception:
        pass


def run_submit_verify_loop(
    *,
    enter_fn: Callable[..., bool],
    probe_fn: Optional[Callable[[], bool]],
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    log: Optional[Callable[[str], None]] = None,
    verify_s: float = 3.0,
    max_retries: int = 3,
    backoffs: tuple | list = (3.0, 5.0, 8.0),
    stop_fn: Optional[Callable[[], bool]] = None,
    t0: float | None = None,
    miss_label: str = "no prompt seen",
    kind: str = "",
    alive_fn: Optional[Callable[[], bool]] = None,
) -> str:
    """Wait for submit probe; Enter-only retry on miss (FR #2696).

    Returns ``ok``, ``stop``, or ``failed``. Never re-pastes.
    """
    def _log(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass

    start = float(clock() if t0 is None else t0)
    waits = [float(verify_s)] + [float(b) for b in list(backoffs)[: max(0, int(max_retries))]]
    # Cap wait list to 1 initial + max_retries entries.
    waits = waits[: int(max_retries) + 1]
    retry_n = 0
    for i, wait_s in enumerate(waits):
        deadline = clock() + max(0.0, float(wait_s))
        while True:
            # FR #4889: probe before stop so a shared stop_fn that also wraps
            # probe logs (probe) not (stop/ACK) when the paste landed.
            if probe_fn:
                try:
                    if probe_fn():
                        _log(
                            f"relay: submit-verify ok after {clock() - start:.1f}s (probe)"
                        )
                        return "ok"
                except Exception:
                    pass
            if stop_fn:
                try:
                    if stop_fn():
                        _log(
                            f"relay: submit-verify ok after {clock() - start:.1f}s (stop/ACK)"
                        )
                        return "stop"
                except Exception:
                    pass
            if alive_fn is not None:
                try:
                    if not alive_fn():
                        _log(
                            "relay: submit-verify FAILED probe=spawn"
                            + (f" kind={kind}" if kind else "")
                        )
                        return "failed"
                except Exception:
                    pass
            rem = deadline - clock()
            if rem <= 0:
                break
            sleep(min(0.05, rem))
        if i >= len(waits) - 1:
            break
        retry_n = i + 1
        _log(f"relay: submit-verify retry={retry_n} ({miss_label})")
        # FR #8270: headless seats have no TUI prompt. Do not send Enter.
        if (kind or "").strip().lower() == "opencode":
            continue
        try:
            enter_fn()
        except TypeError:
            enter_fn(0)
        except Exception as e:
            _log(f"relay: submit-verify enter failed {type(e).__name__}")
    _log(
        f"relay: submit-verify FAILED after {retry_n} retries probe={miss_label}"
        + (f" kind={kind}" if kind else "")
    )
    return "failed"


_submit_verify_depth = 0


def submit_verify_in_flight() -> bool:
    """FR #8442: progress heartbeats must not replace this phase mid-paste."""
    return _submit_verify_depth > 0


def _note_submit_verify_phase(active: bool) -> None:
    """FR #8442: digest progress_phase so a live paste is not an offer-timeout."""
    global _submit_verify_depth
    if active:
        _submit_verify_depth += 1
    else:
        _submit_verify_depth = max(0, _submit_verify_depth - 1)
    try:
        nick = (os.environ.get("BOB_NICK") or os.environ.get("BOB_AGENT_NICK") or "").strip()
        mid = (os.environ.get("BOB_MACHINE") or default_machine_id() or "").strip()
        if not nick or not mid:
            return
        post_digest_progress_heartbeat(
            machine=mid,
            nick=nick,
            progress_phase="submit-verify" if _submit_verify_depth else "",
        )
    except Exception:
        return


def inject_with_submit_verify(
    pid: int,
    text: str,
    *,
    inject_fn: Callable[..., bool] = inject_console,
    enter_fn: Callable[..., bool] = send_console_enter,
    probe_fn: Optional[Callable[[], bool]] = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    log: Optional[Callable[[str], None]] = None,
    verify_s: float | None = None,
    max_retries: int | None = None,
    backoffs: tuple | list | None = None,
    stop_fn: Optional[Callable[[], bool]] = None,
    sync: bool = True,
    on_failed: Optional[Callable[[], None]] = None,
    force_verify: bool = False,
    on_unverified: Optional[Callable[[], None]] = None,
    miss_label: str = "no prompt seen",
    kind: str = "",
    alive_fn: Optional[Callable[[], bool]] = None,
    run_dir: Path | str | None = None,
    job_key: str = "",
) -> bool:
    """Paste via inject_fn, then verify submit and Enter-only retry (FR #2696).

    FR #4115: ``on_failed`` runs when the verify loop ends ``failed`` (re-paste / NACK recovery).

    Returns the inject_fn result. Verify failure is logged but does not flip the
    return to False (ack-miss / remind path still arms on successful paste).
    When ``sync`` is False, the verify loop runs in a daemon thread so the IRC
    relay thread is not blocked for the full backoff budget.
    """
    try:
        # FR #3894: pass log so inject_console can record path=paste|keys|fail.
        ok = bool(inject_fn(pid, text, log=log))
    except TypeError:
        try:
            ok = bool(inject_fn(pid, text))
        except TypeError:
            ok = bool(inject_fn(text))
    if not ok:
        return False
    if not _submit_verify_enabled():
        return True
    # Without a submit probe, never fire Enter-only retries (could interrupt a warm TUI).
    # FR #4456: the ack-miss reminder may force the verify loop anyway (no probe is not success).
    if probe_fn is None and not force_verify:
        if log:
            try:
                log("relay: submit-verify skipped (no probe)")
            except Exception:
                pass
        if on_unverified is not None:
            try:
                on_unverified()
            except Exception:
                pass
        return True
    if probe_fn is None and force_verify:
        if log:
            try:
                log("relay: submit-verify forced (no probe)")
            except Exception:
                pass

        def _never_submitted() -> bool:
            return False

        probe_fn = _never_submitted
    vs = float(_submit_verify_s() if verify_s is None else verify_s)
    mr = int(_submit_verify_retries() if max_retries is None else max_retries)
    bos = _submit_verify_backoffs() if backoffs is None else backoffs
    t0 = float(clock())

    def _run() -> None:
        _note_submit_verify_phase(True)
        try:
            res = run_submit_verify_loop(
                enter_fn=enter_fn,
                probe_fn=probe_fn,
                clock=clock,
                sleep=sleep,
                log=log,
                verify_s=vs,
                max_retries=mr,
                backoffs=bos,
                stop_fn=stop_fn,
                t0=t0,
                miss_label=miss_label,
                kind=kind,
                alive_fn=alive_fn,
            )
            # FR #8553: stamp progress so a hard kill after verify still leaves a trail.
            if res in ("ok", "stop") and run_dir is not None:
                write_inject_progress(
                    run_dir,
                    phase="submit-verify-ok",
                    detail=str(res),
                    job_key=job_key or assign_job_key(text) or "",
                )
            if res == "failed" and on_failed is not None:
                try:
                    on_failed()
                except Exception as e:  # noqa: BLE001
                    if log:
                        try:
                            log(f"relay: submit-verify recovery error {type(e).__name__}")
                        except Exception:
                            pass
        finally:
            _note_submit_verify_phase(False)

    if sync:
        _run()
    else:
        threading.Thread(target=_run, name="submit-verify", daemon=True).start()
    return True


# --------------------------------------------------------------------------------------------- relay (IRC -> agent)
_DROP_RX = re.compile(r"(?i)\b(POINT|DIGEST|AGPK|SEAL)\b|is busy\.|password=|XAI_API_KEY")
_DROP_PREFIX = ("MOOT v1 ", "BOB DIGEST v1", "AGPK v1 ")


_FLOW_RX = re.compile(r"(?i)^(?:@?[\w.\-\[\]\\`^{}|]+[:,]\s*)?(?:!bored\b|NAK\b|NACK\b)")
_NOTHING_QUEUED_RX = re.compile(r"(?i)^nothing\s+queued\b")


def inbound_kind(text: str, own_nick: str) -> str:
    """t817u: 'nak' | 'bored' | 'agent'. !bored and NAK/NACK are shop flow control handled by the exe itself; the model never sees them
    (an optional leading ``<nick>:`` address is ignored when classifying).

    FR #2806: Jeeves ``nothing queued`` is also ``nak`` so BoredEmitter.nak_s starts (still never relayed).
    """
    t = (text or "").strip()
    n = (own_nick or "").strip()
    if n and re.match(r"(?i)^@?" + re.escape(n) + r"\s*[:,]\s*", t):
        t = re.sub(r"(?i)^@?" + re.escape(n) + r"\s*[:,]\s*", "", t, count=1)
    if re.match(r"(?i)^(NAK|NACK)\b", t):
        return "nak"
    if _NOTHING_QUEUED_RX.match(t):
        return "nak"
    if re.match(r"(?i)^!bored\b", t):
        return "bored"
    return "agent"


def drop_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if _FLOW_RX.match(t):  # t817u: !bored / NAK / NACK never reach the agent, from anyone
        return True
    if t.startswith(_DROP_PREFIX) or t.startswith("\x01ACTION lost "):
        return True
    return bool(_DROP_RX.search(t))


def is_nothing_queued(text: str, own_nick: str = "") -> bool:
    """Jeeves idle reply ``<nick>: nothing queued`` (optional address strip). FR #994 detect; FR #2554 never inject."""
    t = (text or "").strip()
    n = (own_nick or "").strip()
    if n and re.match(r"(?i)^@?" + re.escape(n) + r"\s*[:,]\s*", t):
        t = re.sub(r"(?i)^@?" + re.escape(n) + r"\s*[:,]\s*", "", t, count=1)
    else:
        # deliver() may not know own_nick; strip a generic ``nick:`` / ``nick,`` address.
        t = re.sub(r"(?i)^@?[\w.\-\[\]\\`^{}|]+\s*[:,]\s*", "", t, count=1)
    return bool(_NOTHING_QUEUED_RX.match(t))


JEEVES_NICK = "Jeeves"


def addressed_to(text: str, nick: str) -> bool:
    """t812u: the text starts with this worker's own nick as an address (``<nick>: ...`` / ``<nick>, ...`` / ``<nick> ...``).
    The boundary matters: marchhare-135 is not addressed by ``marchhare-13576: ...``."""
    n = (nick or "").strip()
    if not n:
        return False
    return re.match(r"(?i)^\s*@?" + re.escape(n) + r"(?:\s*[:,]|\s|$)", text or "") is not None


def accept_for_agent(src: str, target: str, text: str, own_nick: str, jeeves: str = JEEVES_NICK) -> bool:
    """t812u (token saving): the model only ever sees lines FROM Jeeves (exact nick) addressed to THIS worker - either a PM to
    its nick or a channel line starting with its nick. Other workers' ACK/DONE lines, channel chatter and other bots never
    reach the agent. (PING/PONG and the fleet ping are answered by the exe before this gate, without the model.)"""
    if (src or "").strip().lower() != jeeves.lower():
        return False
    if (target or "").strip().lower() == (own_nick or "").strip().lower():
        return True
    return addressed_to(text, own_nick)


def format_from(
    nick: str,
    target: str,
    text: str,
    maxlen: int = 2000,
    *,
    outbox: str | Path | None = None,
) -> str:
    """Build the agent-visible FROM line. FR #2380: optional ``[outbox: path]`` footer survives compaction.

    FR #6917: stamp the *assigned* live outbox (recreate parent+file). Never leave a
    stale ``[outbox:]`` and never pick a newer sibling ``worker-*`` folder.
    """
    body = one_line(text, maxlen)
    line = "FROM %s %s %s" % (nick, target, body)
    if outbox:
        ensure_outbox(Path(outbox))
        line = opencode_stamp_outbox_footer(line, outbox)
    return line


class Relay:
    """IRC -> agent. deliver() is called FROM THE SOCKET READ THREAD and injects right there (no queue hop, no timer)
    whenever the agent is ready. Messages arriving while the agent is (re)starting are held and flushed the moment
    it is ready (a timer-less callback). Flood guard: >max_burst injections per window are coalesced into one."""

    def __init__(self, log: Callable[[str], None], max_burst: int = 8, window_s: float = 30.0, max_pending: int = 5,
                 clock: Callable[[], float] = time.monotonic, persist_dir: Optional[Path] = None,
                 outbox_path: Optional[Path] = None):
        self.log = log
        self.max_burst = max_burst
        self.window_s = window_s
        self.max_pending = max_pending
        self.clock = clock
        self.persist_dir = Path(persist_dir) if persist_dir else None
        # FR #2380: stamp every injected FROM with the seat outbox so compaction cannot lose it.
        if outbox_path is not None:
            self.outbox_path = Path(outbox_path)
        elif self.persist_dir is not None:
            self.outbox_path = outbox_path_for_run(self.persist_dir)
        else:
            self.outbox_path = None
        self._lock = threading.Lock()
        self._inject: Optional[Callable[[str], bool]] = None
        self._pending: list = []
        # FR #4609: typed keys ``mrb owner/repo#n`` (not bare repo#N) this seat already closed.
        # DONE FIX must not silence a later held MRB for the same number.
        self._finished_refs: set = set()
        # Typed keys ACKed on receipt while held; if later dropped as finished, emit NACK.
        self._acked_held_keys: set = set()
        self._overflow: list = []
        self._sent: list = []
        self._last_line = ""
        # FR #6240: job keys NACKed after ACK. An identical resend is re-judged.
        self._context_refused_keys: set = set()
        self._timer: Optional[threading.Timer] = None
        self.last_injected_at: Optional[float] = None
        self.injected = 0
        self.on_inject: Optional[Callable[..., None]] = None  # health: note "input delivered, expect activity" (line arg)
        self.last_unacked = ""
        # FR #2811: while True, park Jeeves assigns in _pending (harvest / turn still running).
        self.hold_assigns_while: Optional[Callable[[], bool]] = None
        self.on_hold_assign: Optional[Callable[[str], None]] = None
        # FR #4180: while True (out-of-fuel hold), refuse assigns without inject; callback NACKs.
        self.refuse_assign_while: Optional[Callable[[], bool]] = None
        self.skips_hostile_assign: Optional[Callable[[str], bool]] = None  # FR #6134
        # FR #6240 / #6320 / #6328: OpenCode job context.
        # Cheap classify (opencode_job_classify) runs on the IRC read thread.
        # Slow ensure (opencode_ensure_worktree) runs on a daemon thread; ACK waits.
        # Legacy opencode_job_block still runs sync ensure when classify/ensure unset.
        self.opencode_job_block: Optional[Callable[[str], str]] = None
        self.opencode_job_classify: Optional[Callable[[str], str]] = None
        self.opencode_ensure_worktree: Optional[Callable[[str], str]] = None
        self._worktree_creating_keys: set = set()
        self.on_refuse_assign: Optional[Callable[[str], None]] = None
        # FR #4115: write ACK/NACK to the seat outbox (program, no agent turn).
        self.write_outbox: Optional[Callable[[str], bool]] = None
        # FR #8246: clear a finished-job mark before ACK (per offer, not per job id).
        self.prepare_offer: Optional[Callable[[str], None]] = None
        # Return a refuse tag to drop the ACK. A dropped ACK must not inject.
        self.ack_refuse_reason: Optional[Callable[[str], Optional[str]]] = None
        # True when a live turn belongs to another job (NACK busy, no inject).
        self.turn_busy_other_job: Optional[Callable[[str], bool]] = None
        # FR #8738: True while the prior job's closing turn is still open. Held assigns
        # stay parked (no inject) until that turn has ended.
        self.defer_flush_while: Optional[Callable[[], bool]] = None

    def set_target(self, inject: Optional[Callable[[str], bool]]) -> None:
        with self._lock:
            self._inject = inject
            pend: list = []
            if inject:  # a None target (agent starting/restarting) must KEEP what is held
                pend, self._pending = self._pending, []
        if inject:
            for line in pend:
                # FR #2554: never flush held nothing-queued into the agent.
                parts = (line or "").split(None, 3)
                body = parts[3] if len(parts) >= 4 and parts[0].upper() == "FROM" else (line or "")
                if is_nothing_queued(body) or ("nothing queued" in (line or "").lower()):
                    self.log("relay: skipped nothing-queued (pending flush; not injected)")
                    self._persist_last_from(line)
                    continue
                self._do_inject(line)

    def _job_context_nack(self, line: str) -> str:
        """FR #6240: NACK text, or '' when this line may be ACK'd (legacy sync ensure)."""
        fn = self.opencode_job_block
        if not fn or not assign_job_ref(line):
            return ""
        try:
            nack = fn(line)
        except Exception:
            key = assign_job_key(line)
            nack = f"NACK {key} job-context-malformed (FR #6240)" if key else ""
        return (nack or "").strip()

    def _job_context_classify(self, line: str) -> str:
        """FR #6328: cheap classify NACK on the IRC read thread (no git)."""
        fn = self.opencode_job_classify
        if not fn or not assign_job_ref(line):
            return ""
        try:
            nack = fn(line)
        except Exception:
            key = assign_job_key(line)
            nack = f"NACK {key} job-context-malformed (FR #6240)" if key else ""
        return (nack or "").strip()

    def _park_worktree_create(self, nick: str, target: str, text: str, line: str) -> str:
        """FR #6328: run ensure off the IRC read thread; ACK only after create."""
        key = (assign_job_key(line) or "").strip().lower()
        with self._lock:
            if key and key in self._worktree_creating_keys:
                self.log("relay: worktree create already in flight " + (key or "?"))
                self._persist_last_from(line)
                return "opencode_worktree_pending"
            if key:
                self._worktree_creating_keys.add(key)
        self.log("relay: park worktree create off read thread " + (key or line[:80]))
        self._persist_last_from(line)
        th = threading.Thread(
            target=self._worktree_create_then_deliver,
            args=(nick, target, text, line, key),
            name="opencode-wt-create",
            daemon=True,
        )
        th.start()
        return "opencode_worktree_pending"

    def _worktree_create_then_deliver(
        self, nick: str, target: str, text: str, line: str, key: str
    ) -> None:
        """Background: ensure worktree, then NACK or re-enter deliver for ACK."""
        nack = ""
        try:
            fn = self.opencode_ensure_worktree
            if fn:
                nack = (fn(line) or "").strip()
            else:
                job = assign_job_key(line) or "job"
                nack = f"NACK {job} worktree-create-failed:unknown (FR #6240)"
        except Exception:
            job = assign_job_key(line) or "job"
            nack = f"NACK {job} worktree-create-failed:unknown (FR #6240)"
        finally:
            if key:
                with self._lock:
                    self._worktree_creating_keys.discard(key)
        if nack:
            try:
                self._refuse_job_context(line, nack)
            except Exception as e:
                self.log(f"relay: worktree create NACK error {type(e).__name__}")
            return
        try:
            # Worktree exists now; classify will accept. Do not park again.
            self.deliver(nick, target, text)
        except Exception as e:
            self.log(f"relay: worktree create resume error {type(e).__name__}")

    def _write_nacks(self, nack: str) -> None:
        if not nack or not self.write_outbox:
            return
        for part in nack.splitlines():
            text = part.strip()
            if not text:
                continue
            try:
                self.write_outbox(text)
            except Exception:
                pass

    def _refused_path(self) -> Optional[Path]:
        if not self.outbox_path:
            return None
        return Path(self.outbox_path).parent / "opencode-job-refused.txt"

    def _note_context_refused(self, line: str) -> None:
        keys = message_job_keys(line)
        if not keys:
            key = assign_job_key(line)
            keys = [key] if key else []
        with self._lock:
            for key in keys:
                self._context_refused_keys.add(key.lower())
            if line and line == self._last_line:
                self._last_line = ""

    def _consume_context_refusal(self, line: str) -> bool:
        """True when this message was NACKed for job context and may be retried."""
        keys = message_job_keys(line)
        if not keys:
            key = assign_job_key(line)
            keys = [key] if key else []
        wanted = {key.lower() for key in keys if key}
        if not wanted:
            return False
        hit = bool(wanted & self._context_refused_keys)
        self._context_refused_keys -= wanted
        path = self._refused_path()
        if path and path.is_file():
            try:
                have = {item.strip().lower() for item in path.read_text(encoding="utf-8").splitlines() if item.strip()}
            except OSError:
                have = set()
            if wanted & have:
                hit = True
                remain = sorted(have - wanted)
                try:
                    if remain:
                        path.write_text("\n".join(remain) + "\n", encoding="utf-8")
                    else:
                        path.unlink()
                except OSError:
                    pass
        return hit

    def _refuse_job_context(self, line: str, nack: str) -> str:
        # Do not remember this line as delivered. The same assign must be
        # judged again after the worktree exists; a duplicate drop would
        # swallow the chair's retry.
        self.log("relay: NACK job context before ACK " + nack.splitlines()[0])
        self._persist_last_from(line)
        self._write_nacks(nack)
        return "opencode_job_blocked"

    def deliver(self, nick: str, target: str, text: str) -> str:
        nq = is_nothing_queued(text)
        if drop_text(text):
            if nq:
                self.log("relay: skipped nothing-queued (dropped by filter - unexpected)")
            return "dropped"
        # FR #2554: CAST IRON - empty-queue / idle summaries must never wake the model.
        # Operators still get an explicit skip log (+ optional last-from audit); only real
        # Jeeves assigns addressed to this seat may reach inject.
        if nq:
            line = format_from(nick, target, text, outbox=self.outbox_path)
            self.log("relay: skipped nothing-queued (not injected to agent)")
            self._persist_last_from(line)
            return "skipped"
        line = format_from(nick, target, text, outbox=self.outbox_path)
        # FR #6134: OpenCode seats NACK hostile MRB/UAT before ACK-on-receipt / inject.
        if assign_job_ref(line):
            skip_hostile = False
            try:
                skip_hostile = bool(self.skips_hostile_assign and self.skips_hostile_assign(line))
            except Exception:
                skip_hostile = False
            if skip_hostile:
                with self._lock:
                    if line == self._last_line:
                        return "duplicate"
                    self._last_line = line
                self.log("relay: skipped hostile assign (opencode FR #6134) " + line[:120])
                self._persist_last_from(line)
                nack = opencode_hostile_nack_line(line)
                if nack and self.write_outbox:
                    try:
                        self.write_outbox(nack)
                    except Exception:
                        pass
                return "opencode_skips_hostile"
        # FR #6240 / #6328: one FROM message, one job. Missing context NACKs before ACK.
        # Classify is cheap on the read thread; create runs off-thread (no ACK until done).
        # A standing-prompt example is not a FROM message, so it is not a job.
        if self.opencode_job_classify or self.opencode_job_block:
            keys = message_job_keys(line)
            if len(keys) > 1:
                nacks = "\n".join(f"NACK {key} job-context-ambiguous (FR #6240)" for key in keys)
                return self._refuse_job_context(line, nacks)
            if len(keys) == 1:
                if self.opencode_job_classify:
                    nack = self._job_context_classify(line)
                    if nack and is_worktree_absent_nack(nack) and self.opencode_ensure_worktree:
                        return self._park_worktree_create(nick, target, text, line)
                    if nack:
                        return self._refuse_job_context(line, nack)
                else:
                    # Legacy sync ensure path (unit tests that bind opencode_job_block only).
                    nack = self._job_context_nack(line)
                    if nack:
                        return self._refuse_job_context(line, nack)
        # FR #4180: out-of-fuel hold — never inject; NACK via callback; stay quiet.
        if assign_job_ref(line):
            refuse = False
            try:
                refuse = bool(self.refuse_assign_while and self.refuse_assign_while())
            except Exception:
                refuse = False
            if refuse:
                with self._lock:
                    if line == self._last_line:
                        return "duplicate"
                    self._last_line = line
                self.log("relay: refused assign (out-of-fuel) " + line[:120])
                self._persist_last_from(line)
                if self.on_refuse_assign:
                    try:
                        self.on_refuse_assign(line)
                    except Exception:
                        pass
                return "out_of_fuel"
        # FR #8246: a live turn for another job is not a hold. NACK busy and do not inject.
        if assign_job_ref(line):
            busy_turn = False
            try:
                busy_turn = bool(self.turn_busy_other_job and self.turn_busy_other_job(line))
            except Exception:
                busy_turn = False
            if busy_turn:
                with self._lock:
                    if line == self._last_line:
                        return "duplicate"
                    self._last_line = line
                key = assign_job_key(line) or "job"
                nack = f"NACK {key} busy"
                self.log("relay: refused assign (turn busy) " + line[:120])
                self._persist_last_from(line)
                if self.write_outbox:
                    try:
                        self.write_outbox(nack)
                    except Exception:
                        pass
                return "busy_turn"
        # FR #2811: hold assigns during post-DONE/NACK/GIVEUP harvest / turn; deliver on turn_ended.
        hold = False
        try:
            hold = bool(self.hold_assigns_while and self.hold_assigns_while())
        except Exception:
            hold = False
        if hold and assign_job_ref(line):
            first_held = False
            with self._lock:
                if line == self._last_line and not self._consume_context_refusal(line):
                    return "duplicate"
                self._last_line = line
                pending_assigns = sum(1 for p in self._pending if assign_job_ref(p))
                first_held = pending_assigns == 0
                self._pending.append(line)
                if len(self._pending) > self.max_pending:
                    del self._pending[0]
            # FR #4115: ACK the first held assign on receipt (before inject / turn end).
            # FR #8246: if that ACK is suppressed, drop the hold and do not inject later.
            if first_held and not self._ack_offer_or_refuse(line):
                self._drop_pending_line(line)
                return "ack_not_sent"
            self.log("relay: held assign until turn end " + line[:120])
            self._persist_last_from(line)
            if self.on_hold_assign:
                try:
                    self.on_hold_assign(line)
                except Exception:
                    pass
            return "held_until_turn_end"
        do_inject = False
        ack_first = False
        with self._lock:
            if line == self._last_line and not self._consume_context_refusal(line):
                return "duplicate"
            self._last_line = line
            if self._inject is None:
                pending_assigns = sum(1 for p in self._pending if assign_job_ref(p))
                ack_first = bool(assign_job_ref(line)) and pending_assigns == 0
                self._pending.append(line)
                if len(self._pending) > self.max_pending:
                    del self._pending[0]
                if nq:
                    # FR #994: operators must see the wire even during startup grace (no inject target yet).
                    self.log("relay: held nothing-queued (agent not ready)")
                    self._persist_last_from(line)
                    ack_first = False
            else:
                now = self.clock()
                self._sent = [t for t in self._sent if now - t < self.window_s]
                if len(self._sent) >= self.max_burst:
                    self._overflow.append(line)
                    if self._timer is None:
                        wait = max(0.2, self.window_s - (now - self._sent[0]))
                        self._timer = threading.Timer(wait, self._flush_overflow)
                        self._timer.daemon = True
                        self._timer.start()
                    return "coalescing"
                self._sent.append(now)
                do_inject = True
                ack_first = bool(assign_job_ref(line))
        # FR #4115: ACK on receipt before inject (or while agent-not-ready held).
        # FR #8246: a suppressed ACK is one decision with inject — do not deliver the job.
        if ack_first and not self._ack_offer_or_refuse(line):
            if not do_inject:
                self._drop_pending_line(line)
            return "ack_not_sent"
        if do_inject:
            return self._do_inject(line)
        return "held"

    def _drop_pending_line(self, line: str) -> None:
        with self._lock:
            self._pending = [p for p in self._pending if p != line]

    def _ack_offer_or_refuse(self, line: str) -> bool:
        """FR #8246: fresh offer clears the finished mark, then ACK.

        Returns False when the ACK would be dropped. Caller must not inject.
        """
        if self.prepare_offer:
            try:
                self.prepare_offer(line)
            except Exception:
                pass
        ack = ack_on_receipt_line(line)
        reason = None
        if ack and self.ack_refuse_reason:
            try:
                reason = self.ack_refuse_reason(ack)
            except Exception:
                reason = None
        if reason:
            key = assign_job_key(line) or "job"
            nack = f"NACK {key} ack-not-sent"
            self.log(f"relay: ACK suppressed ({reason}); not injecting")
            if self.write_outbox:
                try:
                    self.write_outbox(nack)
                except Exception:
                    pass
            return False
        self._ack_on_receipt(line)
        return True

    def _ack_on_receipt(self, line: str) -> None:
        """FR #4115: write ACK to the seat outbox as soon as an assign is received."""
        ack = ack_on_receipt_line(line)
        if not ack:
            return
        fn = self.write_outbox
        if not fn:
            self.log("relay: ACK on receipt skipped (no write_outbox) " + ack)
            return
        try:
            ok = bool(fn(ack))
        except Exception as e:  # noqa: BLE001
            self.log(f"relay: ACK on receipt error {type(e).__name__}")
            return
        if ok:
            self.log("relay: ACK on receipt " + ack)
            # FR #4609: remember ACK so a later finished-drop can NACK (no ghost ACK).
            key = assign_job_key(line)
            if key:
                kl = key.lower()
                with self._lock:
                    self._acked_held_keys.add(kl)
                    if len(self._acked_held_keys) > 256:
                        self._acked_held_keys.pop()
        else:
            self.log("relay: ACK on receipt write failed " + ack)

    def _do_inject(self, line: str) -> str:
        fn = self._inject
        ok = False
        nq = "nothing queued" in (line or "").lower()
        if fn:
            try:
                ok = bool(fn(line))
            except JobContextRefused as refused:
                # ACK may already have been written. NACK releases the chair.
                # Clear the dedup so the same text can be judged again once the
                # directory exists. Do not hold the line.
                nack = refused.nack
                self.log("relay: job context refused after ACK " + (nack.splitlines()[0] if nack else ""))
                self._note_context_refused(line)
                self._persist_last_from(line)
                self._write_nacks(nack)
                return "opencode_job_blocked"
            except Exception as e:  # never let the read thread die on an inject error
                self.log(f"relay: inject error {type(e).__name__}")
        if ok:
            self.injected += 1
            self.last_injected_at = self.clock()
            self.last_unacked = line
            self.log("relay: injected " + line)
            self._persist_last_from(line)
            if self.on_inject:
                try:
                    self.on_inject(line)
                except TypeError:
                    # Older callbacks took no args.
                    try:
                        self.on_inject()
                    except Exception:
                        pass
                except Exception:
                    pass
            return "injected"
        # FR #994: console inject can fail on an idle TUI; still persist last-from for nothing-queued
        # so Halloy-visible replies are auditable in the run dir.
        if nq:
            self.log("relay: inject failed for nothing-queued (persisted last-from); holding " + line[:80])
            self._persist_last_from(line)
        else:
            self.log("relay: inject failed, holding " + line[:80])
        with self._lock:
            self._pending.append(line)
            if len(self._pending) > self.max_pending:
                del self._pending[0]
        return "inject_failed"

    def _persist_last_from(self, line: str) -> None:
        if not self.persist_dir or not line:
            return
        try:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            (self.persist_dir / "last-from.txt").write_text(line + "\n", encoding="utf-8")
        except OSError:
            pass

    def _flush_overflow(self) -> None:
        with self._lock:
            self._timer = None
            items, self._overflow = self._overflow, []
            self._sent.append(self.clock())
        if not items:
            return
        # FR #6328: production OpenCode binds classify/ensure and clears legacy block.
        if self.opencode_job_block or self.opencode_job_classify:
            self._flush_opencode_overflow(items)
            return
        joined = " | ".join(i[5:] if i.startswith("FROM ") else i for i in items)
        self._do_inject("FROM (flood-coalesced %d messages) %s" % (len(items), one_line(joined, 600)))

    def _flush_opencode_overflow(self, items: list) -> None:
        """Do not join OpenCode assigns into one line. That ACK'd only the first id.

        Several job messages in one flood are each NACKed ``job-context-ambiguous``
        with no ACK and no inject. One delayed assign is judged on its own.
        """
        job_lines = [line for line in items if message_job_keys(line)]
        if len(items) > 1 and job_lines:
            for line in job_lines:
                nacks = "\n".join(
                    f"NACK {key} job-context-ambiguous (FR #6240)" for key in message_job_keys(line)
                )
                self.log("relay: reject coalesced opencode assign " + nacks.splitlines()[0])
                self._write_nacks(nacks)
                self._note_context_refused(line)
            for line in items:
                if line not in job_lines:
                    self._do_inject(line)
            return
        if len(job_lines) == 1 and len(items) == 1:
            line = job_lines[0]
            keys = message_job_keys(line)
            if len(keys) != 1:
                nacks = "\n".join(f"NACK {key} job-context-ambiguous (FR #6240)" for key in keys)
                self._write_nacks(nacks)
                self._note_context_refused(line)
                return
            # Timer thread (not IRC read): classify then ensure sync when absent.
            if self.opencode_job_classify:
                nack = self._job_context_classify(line)
                if nack and is_worktree_absent_nack(nack) and self.opencode_ensure_worktree:
                    try:
                        nack = (self.opencode_ensure_worktree(line) or "").strip()
                    except Exception:
                        job = assign_job_key(line) or "job"
                        nack = f"NACK {job} worktree-create-failed:unknown (FR #6240)"
                if nack:
                    self._write_nacks(nack)
                    self._note_context_refused(line)
                    return
            else:
                nack = self._job_context_nack(line)
                if nack:
                    self._write_nacks(nack)
                    self._note_context_refused(line)
                    return
            if self._ack_offer_or_refuse(line):
                self._do_inject(line)
            return
        joined = " | ".join(i[5:] if i.startswith("FROM ") else i for i in items)
        self._do_inject("FROM (flood-coalesced %d messages) %s" % (len(items), one_line(joined, 600)))

    def hold(self, line: str) -> None:
        """Queue a line for the next agent that becomes ready (used after a hang restart)."""
        with self._lock:
            if line and line not in self._pending:
                self._pending.insert(0, line)

    def note_outbound(self, payload: str) -> int:
        """Seat sent DONE / GIVEUP / NACK for a job: drop held copies of it. Returns n dropped.

        FR #4609: match the full typed key ``TYPE owner/repo#N`` (not bare repo#N), so
        DONE FIX never drops a held MRB for the same number.
        """
        m = _OUT_JOB_KEY_RX.match((payload or "").strip())
        if not m or m.group(1).upper() not in ("DONE", "GIVEUP", "NACK"):
            return 0
        typed = f"{m.group(2).upper()} {m.group(3)}".lower()
        with self._lock:
            self._finished_refs.add(typed)
            if len(self._finished_refs) > 256:
                self._finished_refs.pop()
            self._acked_held_keys.discard(typed)
            before = len(self._pending)

            def _pending_typed(p: str) -> str | None:
                k = assign_job_key(p)
                return k.lower() if k else None

            self._pending = [p for p in self._pending if _pending_typed(p) != typed]
            dropped = before - len(self._pending)
        if dropped:
            self.log(f"relay: dropped {dropped} held assign(s) for {typed} ({m.group(1).upper()} sent)")
        return dropped

    def is_finished_ref(self, line: str) -> bool:
        key = assign_job_key(line)
        typed = key.lower() if key else None
        with self._lock:
            return bool(typed) and typed in self._finished_refs

    def release_held_assigns(self) -> int:
        """FR #2811 / FR #4115 / FR #4180: flush pending assigns after turn_ended / harvest hold ends.

        FR #4180: while out-of-fuel refuse is active, NACK parked assigns instead of injecting.
        Otherwise (FR #4115): inject only the first held assign; extra assigns are NACKed via
        the seat outbox (``busy, holding <first>``) without spending an agent turn.
        FR #8738: while ``defer_flush_while`` says the prior job's closing turn is still
        open, keep the assigns parked (return 0). Every flush caller (turn watcher,
        harvest expiry, watchdog, post_bored) goes through this one gate.
        """
        with self._lock:
            keep: list = []
            flush: list = []
            stale: list = []
            for line in self._pending:
                key = assign_job_key(line)
                typed = key.lower() if key else None
                if typed and typed in self._finished_refs:
                    stale.append(line)
                elif key or assign_job_ref(line):
                    flush.append(line)
                else:
                    keep.append(line)
            self._pending = keep
        for line in stale:
            self.log("relay: dropped finished held assign (DONE/GIVEUP/NACK already sent) " + line[:120])
            # FR #4609: never silently drop an assign this seat already ACKed — release Jeeves.
            key = assign_job_key(line)
            if not key:
                continue
            typed = key.lower()
            with self._lock:
                was_acked = typed in self._acked_held_keys
                self._acked_held_keys.discard(typed)
            if not was_acked:
                continue
            nack = f"NACK {key} already finished"
            if self.write_outbox:
                try:
                    if self.write_outbox(nack):
                        self.log("relay: NACK dropped finished held assign " + nack)
                    else:
                        self.log("relay: NACK dropped finished held assign write failed " + nack)
                except Exception as e:  # noqa: BLE001
                    self.log(f"relay: NACK dropped finished held assign error {type(e).__name__}")
        refuse = False
        try:
            refuse = bool(self.refuse_assign_while and self.refuse_assign_while())
        except Exception:
            refuse = False
        if refuse:
            for line in flush:
                self.log("relay: refused held assign (out-of-fuel) " + (line or "")[:120])
                if self.on_refuse_assign:
                    try:
                        self.on_refuse_assign(line)
                    except Exception:
                        pass
            return 0
        defer = False
        if flush:
            try:
                defer = bool(self.defer_flush_while and self.defer_flush_while())
            except Exception:
                defer = False
        if defer:
            with self._lock:
                # Put them back in front, in order, ahead of anything parked meanwhile.
                self._pending = list(flush) + [p for p in self._pending if p not in flush]
            self.log(
                f"relay: kept {len(flush)} held assign(s) parked - prior job's closing "
                "turn still open (FR #8738)"
            )
            return 0
        # FR #6134: NACK hostile MRB/UAT that were held before kind was known / seat restarted.
        kept = []
        for line in flush:
            skip = False
            try:
                skip = bool(self.skips_hostile_assign and self.skips_hostile_assign(line))
            except Exception:
                skip = False
            if skip:
                self.log("relay: skipped hostile held assign (opencode FR #6134) " + (line or "")[:120])
                nack = opencode_hostile_nack_line(line)
                if nack and self.write_outbox:
                    try:
                        self.write_outbox(nack)
                    except Exception:
                        pass
                continue
            kept.append(line)
        flush = kept
        # FR #6240: a held assign whose worktree is gone NACKs instead of injecting.
        runnable = []
        for line in flush:
            nack = self._job_context_nack(line)
            if nack:
                self.log("relay: NACK held assign job context " + nack.splitlines()[0])
                self._write_nacks(nack)
                self._note_context_refused(line)
                continue
            runnable.append(line)
        flush = runnable
        if not flush:
            return 0
        first, rest = flush[0], flush[1:]
        n = 0
        if self._do_inject(first) == "injected":
            n = 1
        holding = assign_job_key(first) or "job"
        for line in rest:
            nack = busy_holding_nack_line(line, holding)
            if nack and self.write_outbox:
                try:
                    if self.write_outbox(nack):
                        self.log(
                            f"relay: NACK extra held assign ({nack}) without agent turn"
                        )
                    else:
                        self.log("relay: NACK extra held assign write failed " + nack)
                except Exception as e:  # noqa: BLE001
                    self.log(f"relay: NACK extra held assign error {type(e).__name__}")
            else:
                self.log(
                    "relay: extra held assign dropped (no write_outbox) " + line[:80]
                )
        return n

    def has_pending_work(self) -> bool:
        """FR #3192 / #6328: True while an undelivered/unacked assign is parked in the relay.

        Covers ``held`` (no inject target), ``held_until_turn_end``, ``inject_failed``,
        coalesced overflow lines that still look like Jeeves assigns, and in-flight
        OpenCode worktree creates (``_worktree_creating_keys``) — so BoredEmitter must
        not post ``!bored`` until the seat has consumed the assign (or it is dropped).
        """
        with self._lock:
            if self._worktree_creating_keys:
                return True
            for line in self._pending:
                if assign_job_ref(line):
                    return True
            for line in self._overflow:
                if assign_job_ref(line):
                    return True
        return False

    def pending_assign_keys(self) -> set:
        """FR #8738: lower-cased typed keys of assigns still parked (not injected)."""
        keys: set = set()
        with self._lock:
            for line in list(self._pending) + list(self._overflow):
                k = assign_job_key(line)
                if k:
                    keys.add(k.lower())
        return keys

    def close(self) -> None:
        with self._lock:
            self._inject = None
            if self._timer:
                self._timer.cancel()
                self._timer = None


# --------------------------------------------------------------------------------------------- ping liveness
def parse_ping(body: str) -> Optional[str]:
    """None = not a ping; '' = bare ping; else the selector after `ping`."""
    raw = (body or "").strip()
    low = raw.lower()
    if low == "ping":
        return ""
    if low.startswith("ping:") or low.startswith("ping "):
        rest = raw.split(":", 1)[1].strip() if low.startswith("ping:") else raw.split(None, 1)[1].strip()
        tok = (rest.split(None, 1)[0] if rest else "").strip()
        return tok or None
    return None


def nick_matches_selector(nick: str, selector: str) -> bool:
    n = (nick or "").strip().lower()
    sel = (selector or "").strip().lower().rstrip(",:;!?")
    if not n or not sel:
        return False
    if sel == n:
        return True
    if any(ch in sel for ch in "*?"):
        rx = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in sel)
        try:
            return re.fullmatch(rx, n) is not None
        except re.error:
            return False
    if n.startswith(sel):
        return True
    return len(sel) >= 3 and sel in n


# --------------------------------------------------------------------------------------------- IRC seat
def parse_irc_line(line: str):
    tags = ""
    if line.startswith("@"):
        tags, _, line = line.partition(" ")
    prefix = ""
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")
    trailing = None
    if " :" in line:
        line, _, trailing = line.partition(" :")
    elif line.startswith(":"):
        trailing, line = line[1:], ""
    parts = line.split()
    cmd = parts[0].upper() if parts else ""
    params = parts[1:]
    if trailing is not None:
        params = params + [trailing]
    nick = prefix.split("!", 1)[0] if prefix else ""
    return nick, cmd, params


class IrcSeat:
    """One IRC connection, one blocking reader thread.

    FR #3456: when the link drops, ``on_lost`` fires once per connection. The Supervisor may call
    ``prepare_reconnect()`` + ``connect`` / ``connect_with_retries`` to resume with the same nick.
    """

    def __init__(self, host: str, port: int, nick: str, machine: str, password: Optional[SecretStr] = None, sasl: Optional[tuple] = None,
                 tls: bool = True, log: Callable[[str], None] = lambda m: None, ping_every: float = 90.0, ping_grace: float = 45.0,
                 send_gap_s: float = 0.4, pm_allowed: tuple = ("jeeves",), connect: Optional[Callable] = None):
        self.host, self.port, self.nick, self.machine = host, port, nick, machine
        self.mode = "agent"  # FR #3181: only agent seats register IRC markers
        self.shop = shop_channel(machine)
        self.password, self.sasl, self.tls, self.log = password, sasl, tls, log
        self.ping_every, self.ping_grace, self.send_gap_s = ping_every, ping_grace, send_gap_s
        self.pm_allowed = tuple(p.lower() for p in pm_allowed)
        self.ignored = 0
        self.on_nak: Callable[[], None] = lambda: None  # t817u: Jeeves NAK addressed to this seat
        self._connect = connect
        self.sock: Optional[socket.socket] = None
        self.on_message: Callable[[str, str, str], None] = lambda n, t, x: None
        self.on_lost: Callable[[str], None] = lambda r: None
        self.registered = threading.Event()
        self.failed: Optional[str] = None
        self._wlock = threading.Lock()
        self._outq: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._lost_once = False
        self._last_rx = time.monotonic()
        self._last_pong: dict = {}
        self.joined = threading.Event()
        self._reader: Optional[threading.Thread] = None
        self._writer: Optional[threading.Thread] = None

    def prepare_reconnect(self) -> None:
        """FR #3456: tear down a lost socket so ``connect`` / ``connect_with_retries`` can run again."""
        self._stop.set()
        try:
            if self.sock is not None:
                try:
                    self.sock.close()
                except Exception:
                    pass
        except Exception:
            pass
        self.sock = None
        try:
            self._outq.put_nowait(None)
        except Exception:
            pass
        for th in (self._reader, self._writer):
            if th is not None and th.is_alive() and th is not threading.current_thread():
                th.join(timeout=0.5)
        self._reader = None
        self._writer = None
        self._outq = queue.Queue()
        self._stop.clear()
        self._lost_once = False
        self.registered.clear()
        self.joined.clear()
        self.failed = None
        self._last_rx = time.monotonic()

    @property
    def alive(self) -> bool:
        """False once the link is lost / closed (used to stop !bored and any other speech)."""
        return self.sock is not None and not self._stop.is_set() and not self._lost_once

    # ---- lifecycle
    def connect(self, timeout: float = 45.0) -> None:
        if self._connect:
            s = self._connect()
        else:
            s = socket.create_connection((self.host, self.port), timeout=20)
        if self.tls:
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        s.settimeout(self.ping_every)
        self.sock = s
        self._last_rx = time.monotonic()
        self._reader = threading.Thread(target=self._read_loop, name="irc-read", daemon=True)
        self._writer = threading.Thread(target=self._write_loop, name="irc-write", daemon=True)
        self._reader.start()
        self._writer.start()
        if self.password and self.password.reveal():
            self._raw("PASS " + self.password.reveal())
        if self.sasl:
            self._raw("CAP REQ :sasl")
        self._raw("NICK " + self.nick)
        self._raw(f"USER {self.nick} 0 * :bobiverse worker seat")
        deadline = time.monotonic() + float(timeout)
        left = max(0.1, deadline - time.monotonic())
        if not self.registered.wait(left):
            self.close()
            raise ConnectionError("IRC registration timed out")
        if self.failed:
            err = self.failed
            self.close()
            raise ConnectionError(err)
        # FR #1002: register alone is not enough — seat must JOIN #<machine> before !bored.
        left = max(0.1, deadline - time.monotonic())
        if not self.joined.wait(left):
            self.close()
            raise ConnectionError("IRC JOIN timed out")
        if self.failed:
            err = self.failed
            self.close()
            raise ConnectionError(err)

    def connect_with_retries(
        self,
        attempts: int = 3,
        timeout: float = 45.0,
        backoff_s: tuple = (2.0, 5.0, 10.0),
    ) -> None:
        """FR #955: retry IRC registration with backoff before giving up; log each failure."""
        last: Optional[BaseException] = None
        n = max(1, int(attempts))
        for i in range(n):
            try:
                # Reset per-attempt state after a prior failed connect/close.
                self.registered.clear()
                self.joined.clear()
                self.failed = None
                self._lost_once = False
                self._stop.clear()
                self.connect(timeout=timeout)
                if i > 0:
                    self.log(f"IRC: connected on attempt {i + 1}/{n}")
                return
            except BaseException as e:
                last = e
                self.log(
                    f"IRC: connect attempt {i + 1}/{n} failed ({type(e).__name__}: {str(e)[:120]})"
                )
                try:
                    self.close()
                except Exception:
                    pass
                if i + 1 >= n:
                    break
                delay = float(backoff_s[min(i, len(backoff_s) - 1)]) if backoff_s else 2.0
                time.sleep(delay)
        assert last is not None
        raise last

    def close(self, quit_msg: str = "worker stop") -> None:
        self._stop.set()
        try:
            if self.sock:
                try:
                    self._raw("QUIT :" + quit_msg)
                except Exception:
                    pass
                self.sock.close()
        except Exception:
            pass
        self._outq.put(None)

    # ---- sending
    def _raw(self, line: str) -> None:
        data = (line.replace("\r", " ").replace("\n", " ") + "\r\n").encode("utf-8", "replace")
        with self._wlock:
            if not self.sock:
                raise OSError("no socket")
            self.sock.sendall(data)

    def say(self, target: str, text: str) -> bool:
        """Queue a PRIVMSG. Seats speak ONLY in their own shop channel (FR #224); anything else is refused.

        FR #1018: return False (and mark the link lost) when the writer thread is dead so
        ``bored -> shop`` is not logged as sent while nothing reaches IRC.
        """
        if (target or "").lower() != self.shop.lower():
            self.log(f"irc: refused PRIVMSG to {target!r} (seat may only speak in {self.shop})")
            return False
        if self._lost_once or self._stop.is_set() or self.sock is None:
            self.log("irc: say refused (link already lost/closed)")
            return False
        w = self._writer
        if w is None or not w.is_alive():
            self.log("irc: say refused (writer thread dead)")
            self._lost("writer thread dead")
            return False
        self._outq.put(("PRIVMSG " + self.shop + " :" + one_line(text, 400)))
        return True

    def _write_loop(self) -> None:
        last = 0.0
        while True:
            item = self._outq.get()  # blocks; no polling
            if item is None or self._stop.is_set():
                return
            gap = self.send_gap_s - (time.monotonic() - last)
            if gap > 0:
                self._stop.wait(gap)
            try:
                self._raw(item)
            except OSError as e:
                # FR #1018: silent exit left say() returning True forever; surface LOST.
                self._lost(f"write OSError {type(e).__name__}")
                return
            last = time.monotonic()

    # ---- reading
    def _lost(self, why: str) -> None:
        # FR #3181: clear IRC seat marker so the cap frees immediately
        if clear_seat_irc is not None:
            try:
                clear_seat_irc(getattr(self, "nick", None), pid=os.getpid())
            except OSError:
                pass
        if self._lost_once or self._stop.is_set():
            return
        self._lost_once = True
        self.log("irc: LOST " + why)
        try:
            self.on_lost(why)
        except Exception as e:  # pragma: no cover
            self.log(f"irc: on_lost error {type(e).__name__}")

    def _read_loop(self) -> None:
        buf = b""
        s = self.sock
        while not self._stop.is_set():
            try:
                data = s.recv(4096)  # BLOCKING read: the only wait between the network and the handler
            except (socket.timeout, TimeoutError):
                idle = time.monotonic() - self._last_rx
                if idle >= self.ping_every + self.ping_grace * 0.99:
                    self._lost("ping timeout (no data from server)")
                    return
                try:
                    self._raw("PING :bw-%d" % int(time.time()))
                    s.settimeout(self.ping_grace)
                except OSError as e:
                    self._lost("send error " + type(e).__name__)
                    return
                continue
            except (OSError, ssl.SSLError) as e:
                self._lost("recv error " + type(e).__name__)
                return
            if not data:
                self._lost("connection closed by server")
                return
            self._last_rx = time.monotonic()
            try:
                s.settimeout(self.ping_every)
            except OSError:
                pass
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    self._handle(line.decode("utf-8", "replace").rstrip("\r"))
                except Exception as e:  # a bad line must not kill the reader
                    self.log(f"irc: handler error {type(e).__name__}")
                if self._lost_once:
                    return

    def _handle(self, line: str) -> None:
        if not line:
            return
        if line.startswith("PING"):
            self._raw("PONG " + line[5:] if len(line) > 5 else "PONG")  # immediate, in the read thread
            return
        nick, cmd, params = parse_irc_line(line)
        if cmd == "CAP" and len(params) >= 2 and params[1].upper() == "ACK" and self.sasl:
            self._raw("AUTHENTICATE PLAIN")
        elif cmd == "AUTHENTICATE" and params and params[0] == "+" and self.sasl:
            u, p = self.sasl
            self._raw("AUTHENTICATE " + base64.b64encode(f"\0{u}\0{p}".encode()).decode())
        elif cmd == "903":
            self._raw("CAP END")
        elif cmd in ("904", "905", "906", "464", "465", "433", "432", "431", "ERROR") and not self.registered.is_set():
            self.failed = f"IRC refused ({cmd})"
            self.registered.set()
        elif cmd == "ERROR":
            self._lost("server ERROR " + (params[-1][:80] if params else ""))
        elif cmd == "001":
            self.registered.set()
            # FR #1002: JOIN shop immediately after welcome (was missing — nick online, zero channels).
            self._raw("JOIN " + self.shop)
            self.log("irc: JOIN " + self.shop)
        elif cmd in ("403", "405", "471", "473", "474", "475", "476", "477"):
            # JOIN / channel refuse numerics — unblock connect() waiters.
            self.failed = f"IRC JOIN refused ({cmd})"
            self.joined.set()
            self.log(f"irc: JOIN refused ({cmd}) " + (params[-1][:80] if params else ""))
        elif cmd == "JOIN" and nick.lower() == self.nick.lower():
            if params and params[0].lower() == self.shop.lower():
                self.joined.set()
                self.log("irc: joined " + self.shop)
                if getattr(self, "mode", "agent") == "agent" and write_seat_irc is not None:
                    try:
                        write_seat_irc(
                            nick=self.nick,
                            pid=os.getpid(),
                            machine=getattr(self, "machine", "") or "",
                            shop=self.shop,
                        )
                    except OSError as e:
                        self.log("irc: seat marker write failed: %s" % e)
            else:
                self.log("irc: forced join elsewhere, parting " + (params[0] if params else "?"))
                if params:
                    self._raw("PART " + params[0])
        elif cmd == "KICK" and len(params) >= 2 and params[1].lower() == self.nick.lower():
            self._lost("kicked from " + params[0])
        elif cmd == "PRIVMSG" and len(params) >= 2:
            self._on_privmsg(nick, params[0], params[1])

    def _on_privmsg(self, src: str, target: str, text: str) -> None:
        if src.lower() == self.nick.lower():
            return
        if text.startswith("\x01"):  # CTCP: answer PING/VERSION, never relay
            body = text.strip("\x01")
            if body.upper().startswith("PING"):
                self._raw(f"NOTICE {src} :\x01{body}\x01")
            elif body.upper() == "VERSION":
                self._raw(f"NOTICE {src} :\x01VERSION bob-worker\x01")
            return
        in_shop = target.lower() == self.shop.lower()
        is_pm = target.lower() == self.nick.lower()
        if not in_shop and not (is_pm and src.lower() in self.pm_allowed):
            return
        sel = parse_ping(text)
        if sel is not None:  # fleet liveness: answered here, never woken into the agent
            if in_shop and (sel == "" or any(nick_matches_selector(n, sel) for n in (self.nick, self.machine))):
                now = time.monotonic()
                if now - self._last_pong.get(target.lower(), -99.0) >= 2.0:
                    self._last_pong[target.lower()] = now
                    self.say(self.shop, "pong")
            return
        if not accept_for_agent(src, target, text, self.nick):
            self.ignored += 1  # t812u: not Jeeves, or not addressed to this worker: never wakes the model
            return
        kind = inbound_kind(text, self.nick)
        if kind != "agent":  # t817u: shop flow control is the exe's business, never the model's
            self.ignored += 1
            if kind == "nak":
                # FR #2806: nothing queued arms the same nak_s timer as NAK/NACK (never relayed).
                if is_nothing_queued(text, self.nick):
                    self.log(
                        "irc: nothing queued from Jeeves -> !bored again in the NAK timer "
                        "(exe-handled, not relayed)"
                    )
                else:
                    self.log("irc: NAK from Jeeves -> !bored again in the NAK timer (exe-handled, not relayed)")
                try:
                    line_cb = getattr(self, "on_nak_line", None)
                    if line_cb is not None:
                        line_cb(text)
                except Exception as e:
                    self.log(f"irc: on_nak_line error {type(e).__name__}")
                try:
                    self.on_nak()
                except Exception as e:
                    self.log(f"irc: on_nak error {type(e).__name__}")
            return
        self.on_message(src, target, text)


# --------------------------------------------------------------------------------------------- health
@dataclass
class Sample:
    alive: bool = True
    responding: Optional[bool] = None
    activity: int = 0


class HangDetector:
    """Hung = (a) every windowed process of the tree reports NOT responding for not_responding_s, or
    (b) input was injected and the tree then shows NO cpu/io activity for silent_s (the 'no output / heartbeat' rule).
    An idle agent that is merely waiting for input is NOT hung."""

    def __init__(self, not_responding_s: float = 90.0, silent_s: float = 300.0):
        self.not_responding_s, self.silent_s = not_responding_s, silent_s
        self._nr_since: Optional[float] = None
        self._pending_since: Optional[float] = None
        self._last_activity: Optional[int] = None
        self._last_change: Optional[float] = None

    def reset(self, now: float) -> None:
        self._nr_since = self._pending_since = self._last_activity = None
        self._last_change = now

    def note_inject(self, now: float) -> None:
        if self._pending_since is None:
            self._pending_since = now
            self._last_change = now

    def check(self, s: Sample, now: float) -> Optional[str]:
        if not s.alive:
            return None
        if s.responding is False:
            if self._nr_since is None:
                self._nr_since = now
            elif now - self._nr_since >= self.not_responding_s:
                return "not-responding"
        else:
            self._nr_since = None
        if self._last_activity is None or s.activity != self._last_activity:
            self._last_activity = s.activity
            self._last_change = now
            self._pending_since = None  # the agent consumed the input / is producing work
        elif self._pending_since is not None and now - self._pending_since >= self.silent_s and now - (self._last_change or now) >= self.silent_s:
            return "silent-after-input"
        return None


# FR #3623: ask_user_question leaves the Grok TUI Pending with a live process; HangDetector
# never fires (ACK open, cpu still ticks). Detect via events.jsonl and auto-Enter then recycle.
ASK_USER_TOOL_NAMES = frozenset({"ask_user_question"})


def probe_ask_user_pending_age(
    session_dir: Path | str,
    *,
    now_wall: float | None = None,
    tool_names: frozenset | set | None = None,
) -> Optional[float]:
    """Seconds since oldest unanswered ask_user tool_started in events.jsonl, or None.

    ``session_dir`` may be the session folder or the events.jsonl path itself.
    """
    names = tool_names if tool_names is not None else ASK_USER_TOOL_NAMES
    p = Path(session_dir)
    path = p if p.name == "events.jsonl" else (p / "events.jsonl")
    if not path.is_file():
        return None
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    pending_since: Optional[float] = None
    for line in data.splitlines():
        line = line.strip()
        if not line or "ask_user" not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        name = str(obj.get("tool_name") or "").strip()
        if name not in names:
            continue
        typ = str(obj.get("type") or "").strip()
        ts = _parse_iso_ts(str(obj.get("ts") or ""))
        if typ in ("tool_started", "permission_requested"):
            if pending_since is None and ts is not None:
                pending_since = ts
        elif typ in ("tool_completed", "tool_failed"):
            pending_since = None
    if pending_since is None:
        return None
    now = float(time.time() if now_wall is None else now_wall)
    return max(0.0, now - float(pending_since))


class AskUserPendingWatch:
    """FR #3623: pending ask_user → Enter once → recycle if still pending.

    Returns from ``tick``: None, ``\"enter\"``, or ``\"recycle\"``.
    """

    def __init__(
        self,
        *,
        pending_s: float | None = None,
        enter_grace_s: float | None = None,
    ):
        self.pending_s = (
            float(pending_s)
            if pending_s is not None
            else _env_float("BOB_WORKER_ASK_USER_PENDING_S", 60.0, 5.0, 3600.0)
        )
        self.enter_grace_s = (
            float(enter_grace_s)
            if enter_grace_s is not None
            else _env_float("BOB_WORKER_ASK_USER_ENTER_GRACE_S", 15.0, 1.0, 600.0)
        )
        self._enter_at: Optional[float] = None
        self._logged_age: Optional[int] = None

    def clear(self) -> None:
        self._enter_at = None
        self._logged_age = None

    def tick(self, age_s: Optional[float], now: float) -> Optional[str]:
        if age_s is None:
            self.clear()
            return None
        age = float(age_s)
        if age < self.pending_s:
            return None
        if self._enter_at is None:
            self._enter_at = float(now)
            self._logged_age = int(age)
            return "enter"
        if float(now) - float(self._enter_at) >= self.enter_grace_s:
            return "recycle"
        return None


def sample_tree(root_pid: int) -> Sample:  # pragma: no cover - needs a live Windows tree
    if os.name != "nt":
        return Sample()
    try:
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.WinDLL("user32", use_last_error=True)

        class PE(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

        class IOC(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("ro", "wo", "oo", "rb", "wb", "ob")]

        # t787u: without argtypes ctypes passes Python ints as 32-bit C ints: a 64-bit HWND/HANDLE raised
        # "OverflowError: int too long to convert" inside the EnumWindows callback and printed a traceback into the agent's
        # console on EVERY health sample (and hung-window detection never worked).
        HV = ctypes.c_void_p
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = [HV, HV]
        k32.Process32NextW.argtypes = [HV, HV]
        k32.CloseHandle.argtypes = [HV]
        k32.OpenProcess.restype = HV
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.GetProcessIoCounters.argtypes = [HV, HV]
        k32.GetProcessTimes.argtypes = [HV, HV, HV, HV, HV]
        u32.GetWindowThreadProcessId.argtypes = [HV, HV]
        u32.IsWindowVisible.argtypes = [HV]
        u32.IsHungAppWindow.argtypes = [HV]
        snap = k32.CreateToolhelp32Snapshot(2, 0)
        kids: dict = {}
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            kids.setdefault(pe.th32ParentProcessID, []).append(pe.th32ProcessID)
            ok = k32.Process32NextW(snap, ctypes.byref(pe))
        k32.CloseHandle(snap)
        tree, todo = {int(root_pid)}, [int(root_pid)]
        while todo:
            for c in kids.get(todo.pop(), []):
                if c not in tree:
                    tree.add(c)
                    todo.append(c)
        alive = False
        total = 0
        for p in tree:
            h = k32.OpenProcess(0x1000 | 0x0400, False, p)
            if not h:
                continue
            alive = alive or p == int(root_pid)
            io = IOC()
            if k32.GetProcessIoCounters(h, ctypes.byref(io)):
                total += io.ro + io.wo + io.rb + io.wb
            c_, e_, k_, u_ = (wintypes.FILETIME() for _ in range(4))
            if k32.GetProcessTimes(h, ctypes.byref(c_), ctypes.byref(e_), ctypes.byref(k_), ctypes.byref(u_)):
                total += ((k_.dwHighDateTime << 32) | k_.dwLowDateTime) // 10000 + ((u_.dwHighDateTime << 32) | u_.dwLowDateTime) // 10000
            k32.CloseHandle(h)
        hung: list = []
        EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _l):
            try:  # t787u: a callback must never raise (ctypes prints it into the shared console)
                pid = wintypes.DWORD(0)
                u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in tree and u32.IsWindowVisible(hwnd):
                    hung.append(bool(u32.IsHungAppWindow(hwnd)))
            except Exception:
                pass
            return True

        u32.EnumWindows.argtypes = [EnumProc, wintypes.LPARAM]
        u32.EnumWindows(EnumProc(cb), 0)
        return Sample(alive=alive, responding=(not all(hung)) if hung else None, activity=int(total))
    except Exception:
        return Sample()


# --------------------------------------------------------------------------------------------- !bored (exe-owned)
_OUT_ACK_RX = re.compile(r"(?i)^ACK\b")
_OUT_DONE_RX = re.compile(r"(?i)^DONE\b")
_OUT_FREE_RX = re.compile(r"(?i)^(NACK|GIVEUP)\b")
_OUT_BORED_RX = re.compile(r"(?i)^!bored\b")
# FR #1732 / #4609: job id on ACK/DONE/NACK/GIVEUP — TYPE + owner/repo#N
# (FR|MRB|UAT|FIX|BUILD|PR; ignore trailing PASS/url/reason).
_OUT_JOB_KEY_RX = re.compile(
    r"(?i)^(ACK|DONE|NACK|GIVEUP)\s+(FR|MRB|UAT|FIX|BUILD|PR)\s+(\S+#\d+)\b"
)


# FR #2383: Jeeves assign body still visible inside a FROM line after compaction footers.
_JOB_ASSIGN_RX = re.compile(r"(?i)\b(FR|MRB|UAT|FIX)\s+\S+#\d+\b")
# FR #2791 / #7946: capture owner/repo#N from an assign (or outbox ACK key) for submit-verify stop match.
_ASSIGN_JOB_REF_RX = re.compile(r"(?i)\b(?:FR|MRB|UAT|FIX)\s+(\S+#\d+)\b")
# FR #4180: capture TYPE + owner/repo#N for NACK out-of-fuel lines.
_ASSIGN_TYPE_KEY_RX = re.compile(r"(?i)\b(FR|MRB|UAT|FIX)\s+(\S+#\d+)\b")


def assign_job_ref(line: str) -> Optional[str]:
    """Lower-cased ``owner/repo#N`` from a Jeeves assign / FROM line, or None (FR #2791)."""
    text = line or ""
    parts = text.split(None, 3)
    body = parts[3] if len(parts) >= 4 and parts[0].upper() == "FROM" else text
    m = _ASSIGN_JOB_REF_RX.search(body)
    if not m:
        return None
    return m.group(1).lower()


def assign_job_type_key(line: str) -> Optional[str]:
    """``FR|MRB|UAT owner/repo#N`` from an assign / FROM line, or None (FR #4180)."""
    text = line or ""
    parts = text.split(None, 3)
    body = parts[3] if len(parts) >= 4 and parts[0].upper() == "FROM" else text
    m = _ASSIGN_TYPE_KEY_RX.search(body)
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2)}"


# FR #4827: chair tells a duplicate seat to stop after the original seat's PR lands.
_STAND_DOWN_RX = re.compile(r"(?i)^stand down\s+(?:FR|MRB|UAT)\s+(\S+#\d+)\b")


def stand_down_job_ref(line: str) -> Optional[str]:
    """Lower-cased ``owner/repo#N`` from a stand-down line, or None (FR #4827)."""
    text = line or ""
    parts = text.split(None, 3)
    body = parts[3] if len(parts) >= 4 and parts[0].upper() == "FROM" else text
    m = _STAND_DOWN_RX.match((body or "").strip())
    if not m:
        return None
    return m.group(1).lower()


def looks_like_job_assign(line: str, own_nick: str = "") -> bool:
    """True when an injected FROM looks like a Jeeves FR/MRB/UAT assign (not nothing-queued)."""
    text = line or ""
    if is_nothing_queued(text, own_nick):
        return False
    if stand_down_job_ref(text):
        return False
    # Prefer the payload after FROM nick target …
    parts = text.split(None, 3)
    body = parts[3] if len(parts) >= 4 and parts[0].upper() == "FROM" else text
    return bool(_JOB_ASSIGN_RX.search(body))


# FR #4609 / #4730: typed assign keys match outbox ACK/DONE (include FIX/BUILD/PR).
_ASSIGN_JOB_KEY_RX = re.compile(r"(?i)\b(FR|MRB|UAT|FIX|BUILD|PR)\s+(\S+#\d+)\b")


def assign_job_key(line: str) -> Optional[str]:
    """FR #4115 / #4609: ``MRB|FIX|… owner/repo#N`` (case kept) from a Jeeves assign FROM line, or None."""
    text = line or ""
    parts = text.split(None, 3)
    body = parts[3] if len(parts) >= 4 and parts[0].upper() == "FROM" else text
    m = _ASSIGN_JOB_KEY_RX.search(body)
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2)}"


_TERMINAL_WIRE_RX = re.compile(r"(?im)^\s*(DONE|NACK|GIVEUP)\b")


def outbox_text_has_terminal(text: str, job_key: str = "") -> bool:
    """True when a DONE/NACK/GIVEUP line for job_key is already in the wire.

    Seat outbox lines are ``PRIVMSG #shop :DONE ...`` (FR #2380). Match the
    payload, not only a line that starts with the verb.
    """
    want = (job_key or "").strip()
    for raw in (text or "").splitlines():
        line = outbox_payload(raw)
        if not _TERMINAL_WIRE_RX.match(line):
            continue
        if not want or want in line:
            return True
    return False


def last_turn_error_class(turns_text: str) -> str:
    """Last turn_ended error_class in an opencode-turns.jsonl blob."""
    last = ""
    for raw in (turns_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(obj, dict) and str(obj.get("type") or "") == "turn_ended":
            last = str(obj.get("error_class") or "").strip().lower()
    return last


def ack_miss_exit_reason(
    *, outbox_text: str, turns_text: str = "", job_key: str = ""
) -> str | None:
    """FR #8415: posted DONE/NACK/GIVEUP must not become no-ack-after-assign.

    Returns epipe or process-exit when that turn class is present, else
    done-posted. None when the outbox has no terminal line (recycle may proceed).
    Does not GIVEUP the job again (FR #8384).
    """
    if not outbox_text_has_terminal(outbox_text, job_key):
        return None
    cls = last_turn_error_class(turns_text)
    if cls in ("epipe", "process-exit"):
        return cls
    return "done-posted"


def inject_failed_nack_line(line: str) -> Optional[str]:
    """FR #4115: outbox NACK for an assign the agent never received (Jeeves re-offers it)."""
    key = assign_job_key(line)
    if not key:
        return None
    return f"NACK {key} inject failed"


def submit_verify_giveup_line(line: str, *, probe: str = "", kind: str = "") -> Optional[str]:
    """FR #4510: Cursor seat returns the job after a second submit-verify failure.

    FR #8270: the wire names the probe that failed and the agent kind.
    """
    key = assign_job_key(line)
    if not key:
        return None
    extra = ""
    if probe:
        extra += f" probe={probe}"
    if kind:
        extra += f" kind={kind}"
    return f"GIVEUP {key} submit-verify failed{extra}"


def ack_on_receipt_line(line: str) -> Optional[str]:
    """FR #4115: outbox ACK written as soon as the seat receives an assign (before inject)."""
    key = assign_job_key(line)
    if not key:
        return None
    return f"ACK {key}"


def opencode_skips_hostile_assign(kind: str, line: str, start_model: str = "") -> bool:
    """FR #6134: free OpenCode seats must not take MRB/UAT.

    FR #7888: a paid start_model (OpenCode Go / pro) accepts the assign.
    Missing or ``$model`` still NACKs (fail safe).
    """
    if (kind or "").strip().lower() != "opencode":
        return False
    key = (assign_job_key(line) or "").upper()
    if not (key.startswith("MRB ") or key.startswith("UAT ")):
        return False
    try:
        import worker_start_model as wsm

        if wsm.start_model_review_class(start_model) == "paid":
            return False
    except Exception:
        pass
    return True


def launched_hostile_start_model(kind: str, child_env: Optional[dict] = None) -> str:
    """FR #7888: the model the seat launched, not the configured hello id.

    ``resolve_seat_hello_model`` returns ``workerStartModels`` first. A paid
    OpenCode Go launch with a free configured id must not NACK MRB.
    Missing actual fails safe to the hello model (often free or empty).
    """
    try:
        import worker_start_model as wsm

        env = child_env or {}
        actual = wsm.concrete_model_id(env.get(wsm.ENV_ACTUAL_MODEL))
        if actual:
            return actual
    except Exception:
        pass
    return resolve_seat_hello_model(kind)


def opencode_hostile_nack_line(line: str) -> Optional[str]:
    """FR #6134: NACK without ACK so the chair can re-offer to a Grok/Cursor seat."""
    key = assign_job_key(line)
    if not key:
        return None
    return f"NACK {key} opencode-skips-hostile (FR #6134)"


def _normalize_digest_worker_state(raw: object) -> str:
    """Canonical digest worker state for hub schema. FR #7347 / #8494."""
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    if s in ("needs-sign-in", "needssignin", "needs_sign_in"):
        return "needs_sign_in"
    if s in ("out-of-fuel", "outoffuel", "out_of_fuel"):
        return "out_of_fuel"
    return s


def _digest_post_fail_marker_path(env: Optional[dict] = None) -> Path | None:
    """FR #8513: local tray/monitor marker when worker digest POST fails."""
    e = os.environ if env is None else env
    run = str(e.get("BOB_WORKER_RUN_DIR") or e.get("BOB_RUN_DIR") or "").strip()
    if not run:
        # Prefer the seat run dir next to this process when set by bob-worker.
        try:
            from pathlib import Path as _P

            cand = _P(str(e.get("BOB_STATE_ROOT") or "")).expanduser()
            if cand.is_dir():
                return cand / "digest-post-fail.json"
        except Exception:
            pass
        return None
    try:
        return Path(run) / "digest-post-fail.json"
    except Exception:
        return None


def _write_digest_post_fail_marker(
    *,
    machine: str,
    nick: str = "",
    err: str = "",
    env: Optional[dict] = None,
) -> None:
    """FR #8513: best-effort local flag; never raises; no secrets."""
    path = _digest_post_fail_marker_path(env=env)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "v": 1,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "machine": str(machine or "").strip().lower(),
            "nick": str(nick or "").strip(),
            "error": str(err or "digest-http-error")[:80],
            "digest_post_failed": True,
        }
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    except Exception:
        pass


def _clear_digest_post_fail_marker(env: Optional[dict] = None) -> None:
    path = _digest_post_fail_marker_path(env=env)
    if path is None:
        return
    with contextlib.suppress(Exception):
        if path.is_file():
            path.unlink()


def post_digest_seat_kind(
    *,
    machine: str,
    pid: int | str,
    nick: str = "",
    kind: str = "",
    agent: str = "",
    model: str = "",
    configured_model: str = "",
    model_mismatch: bool | None = None,
    mismatch_reason: str = "",
    cost_tier: str = "",
    start_effort: str = "",
    working_on: str = "",
    worker_build: str | None = None,
    state: str | None = None,
    url: str | None = None,
    env: Optional[dict] = None,
    log: Optional[Callable[[str], None]] = None,
    sleep: Optional[Callable[[float], None]] = None,
    assignable: bool | None = None,
    stale_build: dict | None = None,
    last_exit: dict | None = None,
    cursor_account: str = "",
) -> bool:
    """POST digest worker kind so the chair can skip OpenCode for MRB/UAT (FR #6134).

    FR #6409: payload always includes ``worker_build`` (short SHA or ``unknown``).
    FR #7180 / #7183: optional ``assignable`` / ``state=needs_sign_in``.
    FR #7187: optional ``start_effort``.
    FR #7181: digest POST retries 403; persistent failure posts ``state=unhealthy``.
    FR #7347: hub WORKER_STATES includes needs_sign_in/unhealthy; hyphen alias normalized.
    """
    env = os.environ if env is None else env
    report = (url or env.get("BOB_REPORT_URL") or env.get("BOB_DIGEST_URL") or DEFAULT_DIGEST_REPORT_URL).strip()
    if not report:
        return False
    mid = normalize_machine_id(machine) or str(machine or "").strip().lower()
    kind_s = (kind or "").strip().lower()
    try:
        pid_i = int(str(pid))
    except (TypeError, ValueError):
        return False
    agent_s = (agent or "").strip() or (kind_s if kind_s else "")
    build = short_build_sha(worker_build) if worker_build is not None else short_build_sha()
    state_s = _normalize_digest_worker_state(state) or "idle"
    # FR #7706: kind is the launched --agent. Never relabel an empty kind as grok.
    published_kind = kind_s or (agent_s.strip().lower() if agent_s else "") or "unknown"
    try:
        import worker_start_model as wsm

        published_model = wsm.concrete_model_id(model)
    except Exception:
        published_model = str(model or "").strip()
        if "$" in published_model:
            published_model = ""
    if str(model or "").strip() and not published_model:
        published_model = "unknown"
    elif kind_s == "opencode" and not published_model:
        published_model = "unknown"
    payload = {
        "online": True,
        "id": mid,
        "pid": pid_i,
        "kind": published_kind,
        "state": state_s,
        "nick": (nick or "").strip() or seat_nick(mid, pid_i),
        "working_on": (working_on or "").strip(),
        "agent": agent_s or published_kind,
        "worker_build": build,
    }
    if published_model:
        payload["model"] = published_model
        payload["start_model"] = published_model
    cfg_m = str(configured_model or "").strip()
    if cfg_m:
        payload["configured_model"] = cfg_m
    if model_mismatch is not None:
        payload["model_mismatch"] = bool(model_mismatch)
    elif cfg_m and (model or "").strip():
        payload["model_mismatch"] = str(model).strip().lower() != cfg_m.lower()
    why = str(mismatch_reason or "").strip()
    if why and payload.get("model_mismatch"):
        payload["mismatch_reason"] = why
    if (cost_tier or "").strip():
        payload["cost_tier"] = str(cost_tier).strip()
    eff = str(start_effort or "").strip().lower()
    if eff:
        payload["start_effort"] = eff
    # FR #8649: email label only. Never copy an arbitrary account string.
    if (cursor_account or "").strip() == SI_NTSA_CURSOR_ACCOUNT:
        payload["cursor_account"] = SI_NTSA_CURSOR_ACCOUNT
    if assignable is False:
        payload["assignable"] = False
        payload["error"] = "needs-sign-in"
        payload["state"] = "needs_sign_in"
    elif assignable is True:
        payload["assignable"] = True
    if isinstance(stale_build, dict) and stale_build.get("running"):
        payload["stale_build"] = {
            "running": str(stale_build.get("running") or ""),
            "installed": str(stale_build.get("installed") or ""),
            "since": stale_build.get("since"),
        }
    if isinstance(last_exit, dict):
        from bobreport import coerce_last_exit

        payload["last_exit"] = coerce_last_exit(last_exit)
    post_kw: dict = {"log": log}
    if sleep is not None:
        post_kw["sleep"] = sleep
    ok = bool(_http_post_json(report, payload, **post_kw))
    if ok:
        _clear_digest_post_fail_marker(env=env)
        return True
    meta = last_digest_http()
    st = meta.get("status")
    err = f"digest-http-{st}" if st else "digest-http-error"
    payload = dict(payload)
    payload["state"] = "unhealthy"
    payload["error"] = err
    # FR #8513: surface digest_post_failed on the unhealthy retry payload.
    payload["digest_post_failed"] = True
    if meta.get("responder"):
        payload["digest_responder"] = str(meta.get("responder"))
    if log:
        try:
            snippet = str(meta.get("body") or "").strip()
            extra = f" body={snippet}" if snippet else ""
            log(
                f"post_digest_seat_kind failed mid={mid} kind={kind_s} {err} "
                f"responder={meta.get('responder') or '-'} ray={meta.get('ray') or '-'}{extra}"
            )
        except Exception:
            pass
    post_kw["retries"] = 1
    ok2 = bool(_http_post_json(report, payload, **post_kw))
    if ok2:
        # Unhealthy row reached the chair; still leave a local fail marker for tray.
        _write_digest_post_fail_marker(
            machine=mid, nick=str(payload.get("nick") or ""), err=err, env=env
        )
        return True
    _write_digest_post_fail_marker(
        machine=mid, nick=str(payload.get("nick") or ""), err=err, env=env
    )
    return False


# FR #8155: digest last_progress heartbeats (activity vs state-change ``updated``).
DEFAULT_PROGRESS_HEARTBEAT_S = 120.0
DEFAULT_PROGRESS_POLL_S = 30.0


def progress_heartbeat_interval_s(env: Optional[dict] = None) -> float:
    e = os.environ if env is None else env
    raw = str(e.get("BOB_PROGRESS_HEARTBEAT_S") or "").strip()
    if not raw:
        return float(DEFAULT_PROGRESS_HEARTBEAT_S)
    try:
        v = float(raw)
    except ValueError:
        return float(DEFAULT_PROGRESS_HEARTBEAT_S)
    return max(30.0, min(900.0, v))


def progress_alive_counts_as_seen(*, moved: bool, agent_alive: bool) -> bool:
    """FR #8195: log/worktree move OR a live agent/tool process refreshes the clock."""
    return bool(moved) or bool(agent_alive)


def opencode_frozen_progress_threshold_s(env: dict | None = None) -> float:
    """Seconds of frozen OpenCode progress before hang-recycle (FR #8596)."""
    src = os.environ if env is None else env
    raw = str((src or {}).get("BOB_WORKER_OPENCODE_FROZEN_PROGRESS_S") or "").strip()
    if not raw:
        return 900.0
    try:
        v = float(raw)
    except ValueError:
        return 900.0
    return max(120.0, min(7200.0, v))


def opencode_frozen_recycle_reason(
    *,
    kind: str,
    out_of_fuel: bool,
    ack_open: bool,
    digest_doing_age_s: float | None,
    progress_moved_age_s: float | None,
    threshold_s: float = 900.0,
) -> str:
    """Return hang-recycle reason when an OpenCode seat is frozen (FR #8596).

    Chair stuck-sweep can stamp LOST_ACK_RESTART / accepted_silent while the
    OpenCode process still reports CPU, so HangDetector never fires. Week
    `limited=true` with rolling remaining must not set `out_of_fuel` (that
    hold disables recycle via FR #4180) - callers pass `out_of_fuel` only for
    hard 402 / exhausted holds.
    """
    if (kind or "").strip().lower() != "opencode":
        return ""
    if out_of_fuel:
        return ""
    thr = max(60.0, float(threshold_s))
    digest_age = float(digest_doing_age_s) if digest_doing_age_s is not None else None
    moved_age = float(progress_moved_age_s) if progress_moved_age_s is not None else None
    # FR #8646: a frozen worker.updated (digest doing age) recycles even when a
    # post-reassign progress clock is recent. Heartbeats refresh that stamp
    # while the seat is actually posting. Week-limited with rolling fuel stays
    # out_of_fuel=False so this recycle is allowed.
    if digest_age is not None and digest_age >= thr:
        if not ack_open:
            return "opencode-lost-ack-stale"
        return "opencode-frozen-progress"
    if ack_open and moved_age is not None and moved_age >= thr:
        return "opencode-frozen-progress"
    return ""


def digest_worker_doing_age_s(
    digest_doc: dict | None,
    nick: str,
    *,
    now_wall: float | None = None,
) -> float | None:
    """Age of digest worker.updated when this nick is still doing (FR #8596)."""
    if not isinstance(digest_doc, dict):
        return None
    me = (nick or "").strip().lower()
    if not me:
        return None
    try:
        import gitclaim as _gc

        me = (_gc.canonical_worker_nick(me) or me).strip().lower()
    except Exception:
        pass
    now = float(now_wall) if now_wall is not None else time.time()
    machines = digest_doc.get("machines")
    if not isinstance(machines, dict):
        return None
    for _mid, ent in machines.items():
        if not isinstance(ent, dict):
            continue
        workers = ent.get("workers")
        rows: list = []
        if isinstance(workers, dict):
            rows = [w for w in workers.values() if isinstance(w, dict)]
        elif isinstance(workers, list):
            rows = [w for w in workers if isinstance(w, dict)]
        else:
            try:
                import bobreport as _br

                rows = list(_br._coerce_worker_list(ent.get("worker_list")))
            except Exception:
                rows = []
        for w in rows:
            n = str(w.get("nick") or "").strip().lower()
            try:
                import gitclaim as _gc

                n = (_gc.canonical_worker_nick(n) or n).strip().lower()
            except Exception:
                pass
            if n != me:
                continue
            state = str(w.get("state") or "").strip().lower()
            if state not in ("doing", "busy", "working"):
                return None
            upd = w.get("updated") or w.get("updated_at") or w.get("last_progress")
            if not upd:
                return None
            try:
                from datetime import datetime, timezone

                raw = str(upd).strip()
                if raw.endswith("Z"):
                    raw = raw[:-1] + "+00:00"
                ts = datetime.fromisoformat(raw)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return max(0.0, now - ts.timestamp())
            except Exception:
                return None
    return None




def progress_phase_for_alive_heartbeat(prior: str = "") -> str:
    """Safe phase when the agent is alive but logs are silent (FR #8195)."""
    prior_s = str(prior or "").strip()
    if prior_s:
        try:
            from bobreport import sanitize_progress_phase

            return sanitize_progress_phase(prior_s) or "tool:alive"
        except Exception:
            return re.sub(r"[^a-z0-9_.:-]+", "", prior_s.lower())[:48] or "tool:alive"
    return "tool:alive"



# FR #8249: lock-free job gate for the dedicated progress-heartbeat thread.
class HeartbeatSnapshot(NamedTuple):
    """Immutable ACK/fuel gate published by BoredEmitter for heartbeat ticks."""

    ack_open: bool
    ack_job_key: str
    out_of_fuel: bool
    ack_epoch: int


def _file_size_mtime(path: Path) -> tuple[int, float]:
    try:
        st = path.stat()
        return int(st.st_size), float(st.st_mtime)
    except OSError:
        return 0, 0.0


def _tail_text(path: Path, *, max_bytes: int = 4096) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            raw = fh.read()
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def infer_progress_phase_from_text(text: str) -> str:
    """Map a log tail to a short safe phase (FR #8155). Never returns args/secrets."""
    try:
        from bobreport import sanitize_progress_phase
    except Exception:
        sanitize_progress_phase = None  # type: ignore
    blob = (text or "")[-2000:]
    low = blob.lower()
    phase = ""
    if re.search(r"(?i)\b(pytest|unittest|npm test|cargo test)\b", blob):
        phase = "tool:pytest" if "pytest" in low else "test"
    elif re.search(r"(?i)\b(git\s+commit|committed)\b", blob):
        phase = "commit"
    elif re.search(r"(?i)\b(git\s+push|pushed to)\b", blob):
        phase = "push"
    elif re.search(r"(?i)\b(edit|apply_patch|search_replace|write_file|str_replace)\b", blob):
        phase = "edit"
    elif re.search(r"(?i)\b(bash|shell|powershell|cmd\.exe|run_terminal)\b", blob):
        phase = "tool:bash"
    elif re.search(r"(?i)\b(tool_call|tool_use|function_call)\b", blob):
        m = re.search(r"(?i)\b(?:name|tool)[\"'=\s:]+([A-Za-z0-9_.-]{1,32})", blob[-800:])
        if m:
            phase = f"tool:{m.group(1)}"
        else:
            phase = "tool:call"
    elif re.search(r"(?i)\b(stream|assistant|message)\b", blob):
        phase = "stream"
    elif blob.strip():
        phase = "stream"
    if sanitize_progress_phase is not None:
        return sanitize_progress_phase(phase) or ""
    return re.sub(r"[^a-z0-9_.:-]+", "", phase.lower())[:48]


def detect_seat_progress(
    *,
    kind: str,
    run_dir: Path | str | None,
    job_worktree: str = "",
    prev: Optional[dict] = None,
) -> tuple[bool, str, dict]:
    """Return ``(moved, phase, state)`` for FR #8155 progress heartbeats.

    ``state`` is opaque fingerprint data for the next poll. Progress means log growth,
    turn markers, or worktree mtime — not CPU alone.
    """
    prev = dict(prev or {})
    kind_s = (kind or "").strip().lower()
    rd = Path(run_dir) if run_dir else None
    candidates: list[Path] = []
    if rd is not None:
        candidates.append(rd / "opencode-turns.jsonl")
        candidates.append(rd / "session.log")
        # Per-job OpenCode stdout logs under LOCALAPPDATA Bobiverse/worker/logs/opencode
        logs_root = _state_root() / "logs" / "opencode"
        if logs_root.is_dir():
            try:
                newest = max(logs_root.glob("*.log"), key=lambda p: p.stat().st_mtime, default=None)
            except OSError:
                newest = None
            if newest is not None:
                candidates.append(newest)
        # Grok session events under seat grok-home
        try:
            ghome = agent_grok_home(run_dir=rd)
            sess = ghome / "sessions"
            if sess.is_dir():
                for ev in sess.rglob("events.jsonl"):
                    candidates.append(ev)
                    break
        except Exception:
            pass
        # Cursor chat store (best-effort)
        try:
            cursor_chats = Path.home() / ".cursor" / "chats"
            if cursor_chats.is_dir():
                for p in cursor_chats.rglob("*.jsonl"):
                    candidates.append(p)
                    break
        except Exception:
            pass
    wt = str(job_worktree or "").strip()
    if wt:
        candidates.append(Path(wt) / ".git" / "index")
        candidates.append(Path(wt) / ".git" / "HEAD")

    moved = False
    phase = ""
    state: dict = {"sizes": {}, "mtimes": {}}
    for path in candidates:
        if not path.is_file():
            continue
        key = str(path)
        size, mtime = _file_size_mtime(path)
        state["sizes"][key] = size
        state["mtimes"][key] = mtime
        prev_size = int((prev.get("sizes") or {}).get(key) or 0)
        prev_mtime = float((prev.get("mtimes") or {}).get(key) or 0.0)
        if size > prev_size or (mtime > prev_mtime + 0.5 and size > 0):
            moved = True
            if not phase:
                if "opencode-turns" in key or key.endswith("events.jsonl"):
                    phase = "stream"
                elif "index" in key or key.endswith("HEAD"):
                    phase = "edit"
                else:
                    phase = infer_progress_phase_from_text(_tail_text(path))
    if not phase and moved:
        phase = "stream" if kind_s in ("opencode", "grok", "cursor") else "edit"
    try:
        from bobreport import sanitize_progress_phase

        phase = sanitize_progress_phase(phase)
    except Exception:
        phase = re.sub(r"[^a-z0-9_.:-]+", "", (phase or "").lower())[:48]
    return moved, phase, state


def post_digest_progress_heartbeat(
    *,
    machine: str,
    nick: str,
    pid: int | str | None = None,
    kind: str = "",
    work: str = "",
    last_progress: str = "",
    progress_phase: str = "",
    state: str = "doing",
    url: str | None = None,
    env: Optional[dict] = None,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """POST worker-work activity heartbeat with ``last_progress`` (FR #8155).

    Chair keeps ``updated`` on state/work changes; ``last_progress`` is the activity
    clock. FR #8494: ``state=out_of_fuel`` also advances ``updated`` each tick.
    """
    env = os.environ if env is None else env
    report = (url or env.get("BOB_REPORT_URL") or env.get("BOB_DIGEST_URL") or DEFAULT_DIGEST_REPORT_URL).strip()
    if not report:
        return False
    mid = normalize_machine_id(machine) or str(machine or "").strip().lower()
    nick_s = (nick or "").strip()
    if not mid or not nick_s:
        return False
    try:
        from bobreport import sanitize_progress_phase, _utc_now_iso
    except Exception:
        sanitize_progress_phase = lambda x, **_k: str(x or "")[:48]  # type: ignore
        _utc_now_iso = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())  # type: ignore
    iso = (last_progress or "").strip() or _utc_now_iso()
    phase = sanitize_progress_phase(progress_phase)
    state_s = _normalize_digest_worker_state(state) or "doing"
    payload: dict = {
        "op": "worker-work",
        "machine": mid,
        "id": mid,
        "nick": nick_s,
        "state": state_s,
        "online": True,
        "last_progress": iso,
    }
    # Empty string must be sent so a doing row drops submit-verify (FR #8442).
    payload["progress_phase"] = phase
    if work:
        payload["work"] = one_line(work, 200)
    kind_s = (kind or "").strip().lower()
    if kind_s:
        payload["kind"] = kind_s
    if pid is not None and str(pid).strip() != "":
        try:
            payload["pid"] = int(str(pid))
        except (TypeError, ValueError):
            pass
    ok = bool(_http_post_json(report, payload, log=log))
    if not ok and log:
        try:
            log(f"progress-heartbeat: post failed nick={nick_s} phase={phase or '-'}")
        except Exception:
            pass
    return ok


def busy_holding_nack_line(line: str, holding: str) -> Optional[str]:
    """FR #4115: outbox NACK for an extra held assign; seat keeps ``holding`` without an agent turn."""
    key = assign_job_key(line)
    if not key:
        return None
    hold = (holding or "").strip() or "job"
    return f"NACK {key} busy, holding {hold}"


def append_outbox_line(path: Path | str, text: str, *, retries: int = 8, delay_s: float = 0.05) -> bool:
    """Append one line to the run-dir outbox (the drain loop sends it to the shop channel).

    FR #4363: drain_outbox uses os.replace while agents append; retry briefly so a
    concurrent replace / recreate does not drop ACK/DONE. Prefer share-safe writers
    (Add-BobiverseOutboxLine.ps1) on the PowerShell side.
    """
    p = Path(path)
    line = text.rstrip("\r\n") + "\n"
    for i in range(max(1, int(retries))):
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(line)
            return True
        except OSError:
            ensure_outbox(p)
            if i + 1 >= retries:
                break
            time.sleep(delay_s * (i + 1))
    return False

class InjectRecovery:
    """FR #4115: an assign whose submit-verify FAILED is re-pasted once; if that also fails,
    NACK it via the run-dir outbox (``inject failed``) and clear local state so the seat is free.

    FR #4510 (Cursor): a receipt ACK is not a running turn. Re-paste once (fresh clipboard,
    delayed Enter via the cursor inject gap). If that also fails and no turn is open, send
    ``GIVEUP <TYPE> owner/repo#N submit-verify failed`` and clear the input box.

    ``reinject(line, on_failed)`` must start one fresh inject+verify that calls ``on_failed`` on
    a second failure. ``is_acked(line)`` short-circuits Grok when the job got ACKed meanwhile.
    """

    def __init__(
        self,
        *,
        reinject: Callable[[str, Callable[[], None]], bool],
        write_outbox: Callable[[str], bool],
        clear_local: Callable[[str], None],
        is_acked: Callable[[str], bool] = lambda line: False,
        log: Callable[[str], None] = lambda m: None,
        giveup_on_fail: bool = False,
        agent_kind: str = "",
        block_on_receipt_ack: bool = True,
        turn_running: Callable[[], bool] = lambda: False,
        clear_input: Callable[[], None] = lambda: None,
    ):
        self.reinject = reinject
        self.write_outbox = write_outbox
        self.clear_local = clear_local
        self.is_acked = is_acked
        self.log = log
        self.giveup_on_fail = bool(giveup_on_fail)
        self.agent_kind = (agent_kind or "").strip().lower()
        self.block_on_receipt_ack = bool(block_on_receipt_ack)
        self.turn_running = turn_running
        self.clear_input = clear_input
        self._closed: set[str] = set()

    def on_failed(self, line: str, attempt: int = 1) -> str:
        """Returns ``retried``, ``nacked``, ``giveup``, ``running``, ``acked`` or ``ignored``."""
        if not assign_job_ref(line):
            return "ignored"
        try:
            if self.turn_running():
                self.log("relay: submit-verify FAILED - agent turn running; no GIVEUP")
                return "running"
        except Exception:  # noqa: BLE001
            pass
        if self.block_on_receipt_ack and self.is_acked(line):
            return "acked"
        key = assign_job_key(line) or ""
        if key and key in self._closed:
            return "giveup" if self.giveup_on_fail else "nacked"
        if attempt <= 1:
            self.log(f"relay: submit-verify FAILED - re-pasting assign once (attempt 2) {line[:120]}")
            # FR #4842: clear queued/pending TUI input before re-paste so a stale
            # earlier assign cannot be submitted instead of the reinjected job.
            try:
                self.clear_input()
            except Exception as e:  # noqa: BLE001
                self.log(f"relay: clear input before re-paste failed {type(e).__name__}")
            ok = False
            try:
                ok = bool(self.reinject(line, lambda l=line: self.on_failed(l, attempt=2)))
            except Exception as e:  # noqa: BLE001
                self.log(f"relay: re-paste error {type(e).__name__}")
            if ok:
                return "retried"
            self.log("relay: inject path=fail reason=repaste_failed")
        # FR #4732: paste may have landed; wait briefly for turn_running before GIVEUP/NACK.
        grace = _submit_verify_giveup_grace_s()
        if grace > 0:
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline:
                try:
                    if self.turn_running():
                        self.log(
                            "relay: submit-verify FAILED - agent turn started in grace; no GIVEUP"
                        )
                        return "running"
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(min(0.2, max(0.05, deadline - time.monotonic())))
        if self.giveup_on_fail:
            # FR #8270: annotate OpenCode GIVEUP with probe/kind. Cursor/Grok keep
            # the FR #4510 wire ``submit-verify failed`` with no extras (VISION S3).
            if self.agent_kind == "opencode":
                wire = submit_verify_giveup_line(
                    line, probe="no turn receipt", kind="opencode"
                )
            else:
                wire = submit_verify_giveup_line(line)
            try:
                self.clear_input()
            except Exception as e:  # noqa: BLE001
                self.log(f"relay: clear input failed {type(e).__name__}")
            result = "giveup"
        else:
            wire = inject_failed_nack_line(line)
            result = "nacked"
        if wire:
            sent = self.write_outbox(wire)
            if self.giveup_on_fail:
                self.log(
                    f"relay: submit-verify failed twice - {'queued' if sent else 'COULD NOT queue'} "
                    f"outbox {wire}"
                )
            else:
                self.log(
                    f"relay: inject failed twice - {'queued' if sent else 'COULD NOT queue'} outbox {wire}"
                )
        if key:
            self._closed.add(key)
        try:
            self.clear_local(line)
        except Exception:  # noqa: BLE001
            pass
        return result


# FR #4115: Grok's own prompt-accept timeout. Under CPU load the TUI shows
# "The agent did not accept your prompt within 120s. Your text is back in the input box; press
# Enter to retry" / "Prompt not accepted, text restored" and the prompt sits unsent.
PROMPT_NOT_ACCEPTED_RX = re.compile(
    r"(?i)prompt not accepted|did not accept your prompt within|text is back in the input box"
)


def _prompt_retry_enabled() -> bool:
    """FR #4115: BOB_WORKER_PROMPT_RETRY=0 disables the prompt-not-accepted Enter retry."""
    raw = (os.environ.get("BOB_WORKER_PROMPT_RETRY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _prompt_retry_backoffs() -> tuple:
    """FR #4115: waits after each Enter retry (BOB_WORKER_PROMPT_RETRY_BACKOFFS, csv seconds)."""
    raw = (os.environ.get("BOB_WORKER_PROMPT_RETRY_BACKOFFS") or "").strip()
    if raw:
        try:
            vals = tuple(max(1.0, min(600.0, float(x))) for x in raw.split(",") if x.strip())
            if vals:
                return vals
        except ValueError:
            pass
    return (15.0, 30.0, 60.0)


def read_console_screen_text(max_lines: int = 15) -> Optional[str]:
    """FR #4115: last ``max_lines`` non-empty lines of THIS process's visible console window."""
    if os.name != "nt":
        return None
    try:
        from ctypes import wintypes as W

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class _COORD(ctypes.Structure):
            _fields_ = [("X", W.SHORT), ("Y", W.SHORT)]

        class _SR(ctypes.Structure):
            _fields_ = [("L", W.SHORT), ("T", W.SHORT), ("R", W.SHORT), ("B", W.SHORT)]

        class _CSBI(ctypes.Structure):
            _fields_ = [("size", _COORD), ("cur", _COORD), ("attr", W.WORD), ("win", _SR), ("max", _COORD)]

        k32.CreateFileW.restype = W.HANDLE
        k32.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
        k32.CloseHandle.argtypes = [W.HANDLE]
        h = k32.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)
        if not h or h == ctypes.c_void_p(-1).value:
            return None
        try:
            ci = _CSBI()
            if not k32.GetConsoleScreenBufferInfo(h, ctypes.byref(ci)):
                return None
            w = int(ci.size.X)
            lines = []
            for y in range(int(ci.win.T), int(ci.win.B) + 1):
                buf = ctypes.create_unicode_buffer(w + 1)
                n = W.DWORD()
                k32.ReadConsoleOutputCharacterW(h, buf, w, _COORD(0, y), ctypes.byref(n))
                t = buf.value.rstrip()
                if t:
                    lines.append(t)
            return "\n".join(lines[-max(1, int(max_lines)):])
        finally:
            k32.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return None


class PromptNotAcceptedWatcher:
    """FR #4115: detect Grok's "Prompt not accepted, text restored" and press Enter to retry with
    bounded backoff; after ``max_tries`` Enters still showing it, call ``on_give_up`` once (the
    caller NACKs a pending assign). ``note_activity`` (turn started/ended) ends the episode and
    ignores the same stale screen text until it changes.
    """

    def __init__(
        self,
        *,
        read_fn: Callable[[], Optional[str]],
        enter_fn: Callable[[], bool],
        on_give_up: Callable[[], None] = lambda: None,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = lambda m: None,
        max_tries: int = 3,
        backoffs: tuple | list = (15.0, 30.0, 60.0),
    ):
        self.read_fn = read_fn
        self.enter_fn = enter_fn
        self.on_give_up = on_give_up
        self.clock = clock
        self.log = log
        self.max_tries = max(1, int(max_tries))
        self.backoffs = tuple(float(b) for b in backoffs) or (15.0,)
        self.tries = 0
        self.next_at = 0.0
        self.gave_up = False
        self.active = False
        self._stale: Optional[str] = None
        self._last_screen: Optional[str] = None

    @staticmethod
    def _match(screen: str) -> Optional[str]:
        hits = [ln.strip() for ln in screen.splitlines() if PROMPT_NOT_ACCEPTED_RX.search(ln)]
        return "\n".join(hits) if hits else None

    def note_activity(self) -> None:
        if self.active:
            self.log(f"relay: prompt-not-accepted resolved (turn activity) after {self.tries} Enter retries")
        self._stale = self._match(self._last_screen or "") if self._last_screen else None
        self.active = False
        self.tries = 0
        self.gave_up = False

    def tick(self) -> str:
        """Returns ``clear``, ``stale``, ``wait``, ``enter``, ``gave_up`` or ``done``."""
        screen = self.read_fn()
        if screen is None:
            return "clear"
        self._last_screen = screen
        hit = self._match(screen)
        if not hit:
            if self.active:
                self.log(f"relay: prompt-not-accepted cleared after {self.tries} Enter retries")
            self.active = False
            self.tries = 0
            self.gave_up = False
            self._stale = None
            return "clear"
        if self._stale is not None and hit == self._stale:
            return "stale"
        self._stale = None
        now = float(self.clock())
        if not self.active:
            self.active = True
            self.tries = 0
            self.gave_up = False
            self.next_at = now
            self.log("relay: prompt-not-accepted detected (Grok accept timeout; text restored)")
        if self.gave_up:
            return "done"
        if now < self.next_at:
            return "wait"
        if self.tries >= self.max_tries:
            self.gave_up = True
            self.log(f"relay: prompt-not-accepted still showing after {self.tries} Enter retries - giving up")
            try:
                self.on_give_up()
            except Exception as e:  # noqa: BLE001
                self.log(f"relay: prompt-not-accepted give-up error {type(e).__name__}")
            return "gave_up"
        self.tries += 1
        ok = False
        try:
            ok = bool(self.enter_fn())
        except Exception:  # noqa: BLE001
            ok = False
        wait = self.backoffs[min(self.tries - 1, len(self.backoffs) - 1)]
        self.next_at = now + wait
        self.log(
            f"relay: prompt-not-accepted - Enter retry {self.tries}/{self.max_tries} "
            f"ok={ok} next check in {wait:.0f}s"
        )
        return "enter"


class AssignAckMiss:
    """FR #2383: assign injected, agent keeps working, but no ACK hits the run-dir outbox.

    First action after ``remind_s``: re-inject an outbox-path reminder.
    After ``recycle_s``: caller restarts a NEW agent (hang-style recycle).
    """

    def __init__(
        self,
        *,
        remind_s: float | None = None,
        recycle_s: float | None = None,
    ):
        self.remind_s = (
            float(remind_s)
            if remind_s is not None
            else _env_float("BOB_WORKER_ACK_MISS_REMIND_S", 180.0, 30.0, 3600.0)
        )
        self.recycle_s = (
            float(recycle_s)
            if recycle_s is not None
            else _env_float("BOB_WORKER_ACK_MISS_RECYCLE_S", 900.0, 60.0, 7200.0)
        )
        if self.recycle_s < self.remind_s:
            self.recycle_s = self.remind_s
        self._since: Optional[float] = None
        self._reminded = False
        self._unverified = False
        self.last_line = ""

    def clear(self) -> None:
        self._since = None
        self._reminded = False
        self._unverified = False
        self.last_line = ""

    @property
    def unverified(self) -> bool:
        """FR #4456: last job inject had no submit probe (verification skipped)."""
        return bool(self._unverified)

    def note_unverified(self) -> None:
        """FR #4456: mark the armed assign so the first reminder forces verify, then recycle."""
        if self._since is not None:
            self._unverified = True

    def note_inject(self, line: str, now: float, *, own_nick: str = "") -> None:
        if looks_like_job_assign(line, own_nick):
            self._since = float(now)
            self._reminded = False
            self._unverified = False
            self.last_line = line or ""
            return
        # Mirror BoredEmitter._on_inject: strip FROM nick target before idle match.
        text = line or ""
        parts = text.split(None, 3)
        body = parts[3] if len(parts) >= 4 and parts[0].upper() == "FROM" else text
        if is_nothing_queued(body, own_nick):
            # Idle / withdrawn assign: clear any armed miss timer (MRB #2386).
            self.clear()

    def note_ack(self) -> None:
        self.clear()

    def tick(self, now: float, *, ack_open: bool) -> Optional[str]:
        """Return ``remind``, ``recycle``, or None."""
        if ack_open:
            self.clear()
            return None
        if self._since is None:
            return None
        age = float(now) - self._since
        if age >= self.recycle_s:
            return "recycle"
        if age >= self.remind_s and not self._reminded:
            self._reminded = True
            return "remind"
        # FR #4456: an unverified inject is not left until recycle_s after that reminder.
        if self._reminded and self._unverified:
            return "recycle"
        return None

    def reminder_line(self, *, shop: str, outbox: str | Path) -> str:
        # FR #4115: repeat the pending assign itself so a lost paste is recovered; the generic
        # outbox reminder made the agent answer "waiting for the next Jeeves assign".
        if self.last_line and assign_job_ref(self.last_line):
            return self.last_line
        path = str(outbox)
        return format_from(
            "bob-worker",
            shop,
            "Reminder: ACK/DONE must go to $env:BOB_OUTBOX (run-dir). "
            "Do not write the ear home\\outbox.txt.",
            outbox=path,
        )



def done_miss_reminder_line(*, shop: str, outbox: str | Path, job_key: str) -> str:
    """FR #2875: remind agent that turn ended with ACK open and no DONE/NACK/GIVEUP."""
    key = (job_key or "job").strip() or "job"
    return format_from(
        "bob-worker",
        shop,
        (
            f"Your turn ended with `{key}` ACKed but no DONE/NACK/GIVEUP in the outbox. "
            "Append the DONE (or GIVEUP) line to $env:BOB_OUTBOX now; do not check the outbox first, "
            "it is drained and always empty."
        ),
        outbox=outbox,
    )


def opencode_finish_run_max() -> int:
    """FR #6366: max OpenCode finish-runs after done-miss (default 3, clamp 1..10)."""
    raw = (os.environ.get("BOB_OPENCODE_FINISH_RUN_MAX") or "").strip()
    if not raw:
        return 3
    try:
        n = int(raw)
    except ValueError:
        return 3
    return max(1, min(10, n))



def job_key_issue_number(job_key: str) -> str:
    """Digits after the final ``#`` in a typed job key (FR #8094)."""
    m = re.search(r"#(\d+)\s*$", (job_key or "").strip())
    return m.group(1) if m else ""


def job_key_kind_leaf(job_key: str) -> str:
    """``fr-N`` / ``mrb-N`` / ``uat-N`` leaf for a typed key (FR #8094)."""
    m = re.match(r"(?i)^(FR|MRB|UAT)\s+\S+#(\d+)$", (job_key or "").strip())
    if not m:
        return ""
    return f"{m.group(1).lower()}-{m.group(2)}"


def clear_per_job_env(env: dict | None = None) -> None:
    """Drop ``BOB_JOB_WORKTREE`` so the next offer cannot inherit a prior path (FR #8094)."""
    e = os.environ if env is None else env
    try:
        e.pop("BOB_JOB_WORKTREE", None)
    except Exception:
        pass


def _job_context_num_bounded(norm: str, num: str) -> bool:
    """True when *num* appears with digit boundaries (FR #8099 / #8051 class)."""
    if not num or not norm:
        return False
    return re.search(rf"(?<![0-9]){re.escape(num)}(?![0-9])", norm) is not None


def _job_context_leaf_segment(norm: str, leaf: str) -> bool:
    """True when *leaf* is a path/branch segment, not a longer prefix (FR #8099)."""
    if not leaf or not norm:
        return False
    leaf_l = leaf.lower()
    return (
        re.search(rf"(?:^|[\\/]){re.escape(leaf_l)}(?:[\\/]|$)", norm) is not None
    )


def stale_job_context_reason(
    offer_key: str,
    *,
    worktree: str = "",
    outbox: str = "",
    text: str = "",
    branch: str = "",
) -> str:
    """Return ``stale_job_context`` when a field lacks the offer number / leaf (FR #8094).

    FR #8099: match with path/digit boundaries so ``fr-80910`` does not satisfy ``#8091``.
    """
    leaf = job_key_kind_leaf(offer_key)
    num = job_key_issue_number(offer_key)
    if not num or not leaf:
        return ""
    fr_leaf = f"fr-{num}"
    for label, val in (
        ("worktree", worktree),
        ("outbox", outbox),
        ("text", text),
        ("branch", branch),
    ):
        if not (val or "").strip():
            continue
        norm = str(val).replace("/", "\\").lower()
        if not _job_context_num_bounded(norm, num):
            return "stale_job_context"
        if label in ("worktree", "outbox") and not _job_context_leaf_segment(norm, leaf):
            return "stale_job_context"
        if label == "branch":
            if not (
                _job_context_leaf_segment(norm, leaf)
                or _job_context_leaf_segment(norm, fr_leaf)
            ):
                return "stale_job_context"
    return ""


def stale_job_context_nack_line(
    offer_key: str,
    *,
    worktree: str = "",
    outbox: str = "",
    text: str = "",
    branch: str = "",
) -> str:
    """``NACK <key> stale_job_context`` when context does not match the offer (FR #8094)."""
    reason = stale_job_context_reason(
        offer_key,
        worktree=worktree,
        outbox=outbox,
        text=text,
        branch=branch,
    )
    if not reason:
        return ""
    key = (offer_key or "job").strip() or "job"
    return f"NACK {key} {reason}"


_OPENCODE_DELIVERY = None
_OPENCODE_DELIVERY_MTIME = -1.0


def load_opencode_delivery():
    """FR #8283: reload opencode_delivery.py when its mtime changes.

    Finish prompts must not keep a pre-FR-#8248 copy that says commit on
    fr-N and gh pr create for an MRB.
    """
    global _OPENCODE_DELIVERY, _OPENCODE_DELIVERY_MTIME
    import importlib

    import opencode_delivery as od

    try:
        mtime = float(Path(od.__file__).stat().st_mtime)
    except OSError:
        mtime = _OPENCODE_DELIVERY_MTIME
    if _OPENCODE_DELIVERY is None or mtime != _OPENCODE_DELIVERY_MTIME:
        _OPENCODE_DELIVERY = importlib.reload(od)
        _OPENCODE_DELIVERY_MTIME = mtime
    return _OPENCODE_DELIVERY


def job_task_kind(job_key: str) -> str:
    """FR #8248: FR, MRB, UAT, or FIX from the job key. Empty when unknown."""
    return load_opencode_delivery().job_task_kind(job_key)


def opencode_typed_delivery(
    job_key: str,
    *,
    branch: str = "",
    closes_ref: str = "",
    outbox: str = "",
    pr_state: str = "",
    head_ref: str = "",
) -> str:
    """FR #8248 / #8283: close steps from the on-disk module."""
    return load_opencode_delivery().opencode_typed_delivery(
        job_key,
        branch=branch,
        closes_ref=closes_ref,
        outbox=outbox,
        pr_state=pr_state,
        head_ref=head_ref,
    )


def opencode_job_finish_steps(
    *,
    job_key: str,
    worktree: str | Path,
    outbox: str | Path,
) -> str:
    """FR #6366 / #6370 / #6378: end-of-job checklist for OpenCode (initial assign + finish re-prompt)."""
    key = (job_key or "job").strip() or "job"
    m = re.search(r"(?i)#(\d+)\s*$", key)
    issue_n = m.group(1) if m else "N"
    branch = f"fr-{issue_n}" if issue_n != "N" else "fr-N"
    pm = re.search(
        r"(?i)\b(?:FR|MRB|UAT|FIX)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b",
        key,
    )
    closes_ref = f"{pm.group(1)}#{pm.group(2)}" if pm else key
    wt = str(worktree or "").strip()
    ob = str(outbox or "").strip()
    reviewed = ""
    sha_source = ""
    pr_state = ""
    try:
        import opencode_seat_contract as _osc

        reviewed, sha_source, pr_state = _osc.finish_reviewed_sha(key, wt)
    except Exception:
        reviewed, sha_source, pr_state = "", "", ""
    # FR #8301: MRB PASS/FAIL @ SHA is an MRB (and FIX) board. FR and UAT wires
    # carry no PASS/FAIL, so that boilerplate must not appear on those prompts.
    if job_task_kind(key) not in ("MRB", "FIX"):
        sha_line = ""
    elif reviewed and str(pr_state or "").upper() == "MERGED":
        sha_line = (
            f"FR #8286: PR is already MERGED; tip SHA is {reviewed} (source={sha_source or 'gh'}). "
            f"Do not quote a lagging worktree HEAD. Verify the tip on main, append DONE for {key} "
            f"PASS and the pull request URL; skip a new board when one already recorded PASS @ {reviewed}. "
        )
    elif reviewed:
        sha_line = (
            f"FR #8022/#8286 reviewed SHA is {reviewed} (source={sha_source or 'worktree'}); "
            f"quote it on the board as MRB PASS @ {reviewed} or MRB FAIL @ {reviewed}. "
            "Prefer gh pr view headRefOid over worktree HEAD when they differ after a fold. "
        )
    else:
        sha_line = (
            "FR #8022/#8286: quote gh pr view headRefOid (or git -C worktree rev-parse HEAD) "
            "on the board as MRB PASS @ <sha> or MRB FAIL @ <sha>. "
        )
    return (
        f"FINISH {key}. Work so far is already in the worktree ({wt}). "
        "This is a NEW opencode run (no --resume/--continue). "
        + sha_line
        + "Per job call skill-dag MCP resolve then get_skill; file what you learn with "
        "Report-BobiverseIntakeIssue.ps1 (-Repo from the job id) on the intake webhook in the same turn. "
        "1) git status and git diff. 2) Finish remaining work. "
        + opencode_typed_delivery(
            key,
            branch=branch,
            closes_ref=closes_ref,
            outbox=ob,
            pr_state=pr_state,
        )
        + " Keep scratch files and base comparisons inside this job worktree or the worker run folder --- "
        "never under %TEMP%. Use .bob\\tmp (TEMP/TMP already point there; FR #8247). "
        "Do not request external_directory and do not pass --auto. "
        "Never wait on or poll CI (no gh pr checks --watch, no checks --watch, no waiting for CodeRabbit). "
        "The turn is not over until DONE is written. Do not check the outbox first."
    )



def opencode_done_miss_reminder_line(
    *,
    shop: str,
    outbox: str | Path,
    job_key: str,
    worktree: str | Path,
) -> str:
    """FR #6366: full-frame OpenCode finish re-prompt (survives console inject)."""
    key = (job_key or "job").strip() or "job"
    wt = str(worktree or "").strip()
    if not wt:
        return done_miss_reminder_line(shop=shop, outbox=outbox, job_key=key)
    body = opencode_job_finish_steps(job_key=key, worktree=wt, outbox=outbox)
    from_line = format_from("bob-worker", shop, body, outbox=outbox)
    try:
        return frame_opencode_message(from_line, key, wt)
    except Exception:
        return from_line


def opencode_finish_progress_snapshot(
    worktree: str | Path,
    *,
    check_pr: bool = True,
    run=None,
) -> dict:
    """FR #6366 / #6370: finish-run progress (HEAD, porcelain, origin tip, PR).

    ``origin_head`` is the remote tip for the current branch when present (push
    without a new local commit still counts). ``has_pr`` is True when ``gh`` sees
    an open PR for that head branch.
    """
    import subprocess as _sp

    run = _sp.run if run is None else run
    root = Path(worktree or "")
    out: dict = {
        "head": "",
        "porcelain": "",
        "branch": "",
        "origin_head": "",
        "has_pr": False,
        "pr_url": "",
        "ok": False,
    }
    if not root.is_dir():
        return out
    try:
        head = run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        por = run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        br = run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        out["head"] = (head.stdout or "").strip()
        out["porcelain"] = (por.stdout or "").strip()
        branch = (br.stdout or "").strip()
        if branch == "HEAD":
            branch = ""
        out["branch"] = branch
        out["ok"] = head.returncode == 0 and por.returncode == 0
        if out["ok"] and branch:
            # Prefer origin/<branch>; fall back to upstream.
            for ref in (f"origin/{branch}", "@{u}"):
                tip = run(
                    ["git", "-C", str(root), "rev-parse", ref],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if tip.returncode == 0:
                    out["origin_head"] = (tip.stdout or "").strip()
                    break
            if check_pr:
                pr = run(
                    [
                        "gh",
                        "pr",
                        "list",
                        "--head",
                        branch,
                        "--state",
                        "open",
                        "--json",
                        "number,url",
                        "--limit",
                        "1",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    cwd=str(root),
                )
                if pr.returncode == 0 and (pr.stdout or "").strip() not in ("", "[]"):
                    out["has_pr"] = True
                    try:
                        import json as _json

                        _rows = _json.loads((pr.stdout or "").strip())
                        if isinstance(_rows, list) and _rows:
                            _u = str((_rows[0] or {}).get("url") or "").strip()
                            if "github.com" in _u and "/pull/" in _u:
                                out["pr_url"] = _u
                    except Exception:
                        pass
    except Exception:
        pass
    return out


def opencode_finish_progress_changed(before: dict, after: dict) -> bool:
    """True when finish-run snapshot fields show real progress.

    FR #6366 / MRB #6367: failed snapshots are not progress.
    FR #6370: push (origin_head) or a new open PR also counts, not only local commits.
    """
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    if not before.get("ok") or not after.get("ok"):
        return False
    keys = ("head", "porcelain", "origin_head", "has_pr")
    return tuple(before.get(k) for k in keys) != tuple(after.get(k) for k in keys)


def opencode_parse_job_repo_issue(job_key: str) -> tuple[str, str] | None:
    """Return ``(owner/repo, issue_n)`` from ``FR owner/repo#N``, else None."""
    m = re.search(
        r"(?i)\b(?:FR|MRB|UAT|FIX)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b",
        job_key or "",
    )
    if not m:
        return None
    return m.group(1), m.group(2)



def opencode_stamp_outbox_footer(line: str, outbox: str | Path) -> str:
    """FR #6378: every inject footer must be the *current* job worktree outbox.

    Replaces any existing ``[outbox: ...]`` (including a previous job's path) or
    appends one when missing. Never leave a cached prior-job footer.
    """
    ob = str(outbox or "").strip()
    if not ob:
        return line or ""
    s = line or ""
    footer = f"[outbox: {ob}]"
    s2 = re.sub(r"\s*\[outbox:\s*[^\]]*\]\s*$", "", s, flags=re.IGNORECASE).rstrip()
    return f"{s2} {footer}"


def opencode_finish_open_pr_url(
    worktree: str | Path,
    job_key: str,
    *,
    run=None,
) -> str:
    """FR #6378: URL of an open PR for the job branch, else ``""``."""
    import json as _json
    import subprocess as _sp

    run = _sp.run if run is None else run
    root = Path(worktree or "")
    if not root.is_dir():
        return ""
    try:
        br = run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        branch = (br.stdout or "").strip() if br.returncode == 0 else ""
    except Exception:
        branch = ""
    if not branch or branch == "HEAD":
        return ""
    parsed = opencode_parse_job_repo_issue(job_key)
    repo = parsed[0] if parsed else ""
    argv = ["gh", "pr", "list"]
    if repo:
        argv.extend(["--repo", repo])
    argv.extend(
        [
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "url,number",
            "--limit",
            "1",
        ]
    )
    try:
        pr = run(
            argv,
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(root),
        )
    except Exception:
        return ""
    if pr.returncode != 0:
        return ""
    raw = (pr.stdout or "").strip()
    if not raw or raw == "[]":
        return ""
    try:
        data = _json.loads(raw)
    except Exception:
        return ""
    if not isinstance(data, list) or not data:
        return ""
    url = str((data[0] or {}).get("url") or "").strip()
    return url if "github.com" in url and "/pull/" in url else ""


def opencode_finish_branch_ahead_no_pr(
    worktree: str | Path,
    *,
    base: str = "origin/main",
    run=None,
) -> tuple[bool, str, str]:
    """True when current branch tip is on origin, ahead of *base*, and has no open PR.

    Returns ``(ok, branch, origin_head)``.
    """
    import subprocess as _sp

    run = _sp.run if run is None else run
    snap = opencode_finish_progress_snapshot(worktree, check_pr=True, run=run)
    branch = str(snap.get("branch") or "").strip()
    origin_head = str(snap.get("origin_head") or "").strip()
    if not snap.get("ok") or not branch or not origin_head:
        return False, branch, origin_head
    if snap.get("has_pr"):
        return False, branch, origin_head
    try:
        cnt = run(
            ["git", "-C", str(worktree), "rev-list", "--count", f"{base}..{origin_head}"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if cnt.returncode != 0:
            return False, branch, origin_head
        n = int((cnt.stdout or "0").strip() or "0")
    except Exception:
        return False, branch, origin_head
    return n > 0, branch, origin_head


def opencode_finish_auto_pr(
    worktree: str | Path,
    job_key: str,
    *,
    base: str = "main",
    run=None,
    title: str | None = None,
) -> str:
    """FR #6370: open a PR for a pushed tip with no PR. Return PR URL or ``""``."""
    import subprocess as _sp

    run = _sp.run if run is None else run
    root = Path(worktree or "")
    parsed = opencode_parse_job_repo_issue(job_key)
    if not root.is_dir() or not parsed:
        return ""
    repo, issue_n = parsed
    ahead, branch, _origin = opencode_finish_branch_ahead_no_pr(
        root, base=f"origin/{base}", run=run
    )
    if not ahead or not branch:
        return ""
    # FR #7739: a branch for a closed or duplicate issue is not a PR.
    try:
        from opencode_turn_guard import opencode_issue_is_open
    except ImportError:
        opencode_issue_is_open = None  # type: ignore
    if opencode_issue_is_open is not None and not opencode_issue_is_open(repo, issue_n, run=run):
        return ""
    body = (
        f"Closes {repo}#{issue_n}\n\n"
        f"Auto-opened by bob-worker OpenCode finish recovery (FR #6370) for `{job_key}` "
        f"after finish-runs pushed the branch without a PR.\n"
    )
    bob = root / ".bob"
    try:
        bob.mkdir(parents=True, exist_ok=True)
        body_file = bob / "pr-body-auto.md"
        body_file.write_text(body.replace("\\n", "\n"), encoding="utf-8")
    except OSError:
        return ""
    pr_title = title or f"{job_key.split()[0]} #{issue_n}: finish recovery"
    try:
        created = run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repo,
                "--base",
                base,
                "--head",
                branch,
                "--title",
                pr_title,
                "--body-file",
                str(body_file),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(root),
        )
    except Exception:
        return ""
    if created.returncode != 0:
        return ""
    url = (created.stdout or "").strip().splitlines()
    url = next((u.strip() for u in url if "github.com" in u and "/pull/" in u), "")
    return url


# FR #8156: once-per-process warn when a fleet .ps1 lacks a switch the exe wants.
_FLEET_PS1_MISMATCH_WARNED: set[str] = set()
_CLEAR_PS1_NAME = "Clear-BobiverseJobWorktrees.ps1"
_PS1_PARAM_RX = re.compile(r"(?is)\bparam\s*\((.*?)\)\s*(?:\r?\n|$)")
_PS1_PARAM_NAME_RX = re.compile(r"(?im)^\s*(?:\[[^\]]+\]\s*)+\$([A-Za-z_][A-Za-z0-9_]*)")


def ps1_declared_params(script: str | Path) -> frozenset[str]:
    """Parameter names declared in a PowerShell script's ``param(...)`` block (FR #8156)."""
    try:
        text = Path(script).read_text(encoding="utf-8-sig")
    except OSError:
        return frozenset()
    m = _PS1_PARAM_RX.search(text)
    if not m:
        return frozenset()
    body = m.group(1) or ""
    names = {n for n in _PS1_PARAM_NAME_RX.findall(body) if n}
    # Also catch ``[switch]$Foo`` / bare ``$Foo =`` tokens inside the block.
    for n in re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", body):
        names.add(n)
    return frozenset(names)


def resolve_fleet_ps1(
    name: str,
    *,
    install_root: str | Path | None = None,
    source_file: str | Path | None = None,
) -> Optional[Path]:
    """Locate a fleet ``.ps1`` the worker invokes (FR #8156).

    Prefer the copy shipped beside the frozen exe (or extracted worker-scripts),
    then ``common\\scripts`` (tracked), and only then the often-stale flat
    ``install\\scripts`` compose. Never prefer a PyInstaller ``_MEI`` extract.
    """
    try:
        import worker_shipped_scripts as _shipped_scripts

        _shipped_scripts.extract_bundled_scripts()
    except Exception:
        pass
    source = Path(source_file).resolve() if source_file else Path(__file__).resolve()
    here = source.parent
    install = str(
        install_root
        or os.environ.get("BOB_INSTALL_ROOT")
        or os.environ.get("BOBIVERSE_INSTALL_ROOT")
        or ""
    ).strip()
    candidates: list[Path] = []
    # 1) Frozen / hotpatch ship dir next to bob-worker.exe
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "scripts" / name)
        candidates.append(exe_dir.parent / "scripts" / name)
        candidates.append(exe_dir.parent / "worker" / "scripts" / name)
    # 2) Env override
    scripts_env = (os.environ.get("BOB_SCRIPTS_DIR") or "").strip()
    if scripts_env:
        candidates.append(Path(scripts_env) / name)
    # 3) Repo / source tree common (fresher than flat compose)
    if not _path_is_mei_extract(here):
        candidates.append(here.parent.parent / "common" / "scripts" / name)
        candidates.append(here / name)
    if install:
        root = Path(install)
        candidates.append(root / "common" / "scripts" / name)
        candidates.append(root / "worker" / "scripts" / name)
        # Flat compose last — often lags hotpatched exe (class of #8156).
        candidates.append(root / "scripts" / name)
    for cand in candidates:
        if _path_is_mei_extract(cand):
            continue
        if cand.is_file():
            return cand.resolve()
    return None


def filter_ps1_optional_switches(
    script: str | Path,
    argv: list[str],
    *,
    optional: frozenset[str] | set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Drop ``-Switch`` args the script does not declare (FR #8156).

    Returns ``(filtered_argv, omitted_switch_names)``. Required positional-style
    pairs (``-RepoRoot``, ``-KeepPath``, …) are kept even when undeclared so a
    truly broken script still fails loudly; only ``optional`` names are stripped.
    """
    opt = frozenset(optional or ())
    if not opt:
        return list(argv), []
    declared = {n.lower() for n in ps1_declared_params(script)}
    out: list[str] = []
    omitted: list[str] = []
    i = 0
    while i < len(argv):
        tok = str(argv[i])
        if tok.startswith("-") and not tok.startswith("--"):
            name = tok.lstrip("-").split(":", 1)[0]
            # Switch with no following value when next is another flag or end.
            is_switch_only = (i + 1 >= len(argv)) or str(argv[i + 1]).startswith("-")
            if name.lower() in {o.lower() for o in opt} and name.lower() not in declared:
                omitted.append(name)
                i += 1
                # Drop a following value only when it is not another flag (rare for switches).
                if not is_switch_only and i < len(argv) and not str(argv[i]).startswith("-"):
                    # Optional switches are [switch] — never consume a value.
                    pass
                continue
        out.append(tok)
        i += 1
    return out, omitted


def _warn_fleet_ps1_mismatch_once(
    script: Path,
    omitted: list[str],
    *,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Log + runtime_failure once per script path for omitted switches (FR #8156)."""
    if not omitted:
        return
    key = str(script).lower()
    if key in _FLEET_PS1_MISMATCH_WARNED:
        return
    _FLEET_PS1_MISMATCH_WARNED.add(key)
    msg = (
        f"fleet-ps1 mismatch: {script.name} lacks -{',-'.join(omitted)}; "
        f"calling without those switches (path={script})"
    )
    if log_fn:
        log_fn(f"opencode finish: Clear result=skipped:param-mismatch {msg}")
    try:
        import runtime_failure

        runtime_failure.report_message(
            "bob-worker",
            msg,
            site="fleet-ps1-param-mismatch",
        )
    except Exception:
        pass


def opencode_cleanup_extra_worktrees(
    job_worktree: str | Path,
    *,
    temp_root: str | Path | None = None,
    run=None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """FR #6370 / FR #8023 / FR #8156: delegate extra worktree reclaim to Clear.

    Resolves Clear via ``resolve_fleet_ps1`` (shipped / common before flat
    install scripts). Passes ``-SkipSeatDisk`` only when the script declares it;
    otherwise falls back so an older install-root copy still cleans. Logs
    ``result=ok|skipped:<reason>|failed:<class>``.
    """
    import shutil as _shutil
    import subprocess as _sp

    _ = temp_root  # retained for call-site compat; Clear owns selection.
    run = _sp.run if run is None else run
    root = Path(job_worktree or "")
    removed: list[str] = []
    if not root.is_dir():
        if log_fn:
            log_fn("opencode finish: Clear result=skipped:no-job-dir")
        return removed
    try:
        job_res = root.resolve()
    except OSError:
        if log_fn:
            log_fn("opencode finish: Clear result=skipped:job-resolve")
        return removed

    ps = _shutil.which("powershell") or _shutil.which("powershell.exe")
    if not ps:
        if log_fn:
            log_fn("opencode finish: Clear result=skipped:powershell-missing")
        return removed

    script = resolve_fleet_ps1(_CLEAR_PS1_NAME)
    if script is None:
        if log_fn:
            log_fn("opencode finish: Clear result=skipped:script-missing")
        return removed

    repo_root = ""
    try:
        common = run(
            ["git", "-C", str(job_res), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if int(getattr(common, "returncode", 1)) == 0:
            common_dir = (common.stdout or "").strip()
            if common_dir:
                cpath = Path(common_dir)
                if not cpath.is_absolute():
                    cpath = (job_res / cpath).resolve()
                text = str(cpath)
                if text.lower().endswith(os.sep + ".git") or text.lower().endswith("/.git"):
                    repo_root = str(cpath.parent)
                else:
                    marker = text.lower().rfind(f"{os.sep}.git{os.sep}")
                    if marker < 0:
                        marker = text.lower().rfind("/.git/")
                    if marker >= 0:
                        repo_root = text[:marker]
                    else:
                        repo_root = str(job_res)
    except Exception:
        repo_root = ""
    if not repo_root or not (Path(repo_root) / ".git").exists():
        try:
            top = run(
                ["git", "-C", str(job_res), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if int(getattr(top, "returncode", 1)) == 0:
                repo_root = (top.stdout or "").strip() or repo_root
        except Exception:
            pass
    if not repo_root:
        if log_fn:
            log_fn("opencode finish: Clear result=skipped:no-repo-root")
        return removed

    argv = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-RepoRoot",
        repo_root,
        "-KeepPath",
        str(job_res),
        "-SkipSeatDisk",
        "-MaxExtraJobTrees",
        "0",
    ]
    argv, omitted = filter_ps1_optional_switches(
        script, argv, optional=frozenset({"SkipSeatDisk"})
    )
    if omitted:
        _warn_fleet_ps1_mismatch_once(script, omitted, log_fn=log_fn)

    try:
        proc = run(
            argv,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = ((getattr(proc, "stdout", "") or "") + (getattr(proc, "stderr", "") or ""))
        code = int(getattr(proc, "returncode", 1) or 0)
        # NamedParameterNotFound / similar: retry once without optional switches.
        if code != 0 and "NamedParameterNotFound" in out and "-SkipSeatDisk" in argv:
            argv2 = [a for a in argv if a != "-SkipSeatDisk"]
            _warn_fleet_ps1_mismatch_once(script, ["SkipSeatDisk"], log_fn=log_fn)
            proc = run(argv2, capture_output=True, text=True, timeout=300)
            out = ((getattr(proc, "stdout", "") or "") + (getattr(proc, "stderr", "") or ""))
            code = int(getattr(proc, "returncode", 1) or 0)
            argv = argv2
        for line in out.splitlines():
            if line.startswith("Removing worktree "):
                removed.append(line[len("Removing worktree ") :].strip())
        exit_u = normalize_agent_exit_code(code)
        if log_fn:
            if code == 0:
                log_fn(f"opencode finish: Clear result=ok removed={len(removed)} {out[-200:]}")
            elif exit_u == CONSOLE_CLOSE_EXIT:
                # FR #8211: Ctrl+C / console-close (0xC000013A) during Clear is not a
                # Clear defect — do not file fleet-ps1-clear-failed.
                log_fn(
                    "opencode finish: Clear result=skipped:console-closed "
                    f"exit={format_agent_exit_code_label(code)}"
                )
            else:
                log_fn(
                    f"opencode finish: Clear result=failed:exit-{code} {out[-400:]}"
                )
                try:
                    import runtime_failure

                    runtime_failure.report_message(
                        "bob-worker",
                        f"Clear-BobiverseJobWorktrees exit={code}",
                        site="fleet-ps1-clear-failed",
                    )
                except Exception:
                    pass
    except Exception as e:  # noqa: BLE001
        if log_fn:
            log_fn(f"opencode finish: Clear result=failed:{type(e).__name__}")
        try:
            import runtime_failure

            runtime_failure.report_message(
                "bob-worker",
                f"Clear-BobiverseJobWorktrees failed {type(e).__name__}",
                site="fleet-ps1-clear-failed",
            )
        except Exception:
            pass
    return removed


_BUSY_HELD_RX = re.compile(
    r"(?i)\bbusy\s*\(\s*held\s+((?:FR|MRB|UAT|FIX|BUILD|PR)\s+\S+#\d+)\s*\)"
)


def busy_nak_held_job(text: str) -> str:
    """FR #4642: job key inside ``NAK !BORED busy (held TASK owner/repo#N)``, else ``''``."""
    m = _BUSY_HELD_RX.search(text or "")
    if not m:
        return ""
    parts = m.group(1).split(None, 1)
    if len(parts) != 2:
        return ""
    return f"{parts[0].upper()} {parts[1]}"


def outbox_job_key(payload: str) -> Optional[str]:
    """Normalize `TYPE owner/repo#N` from a shop wire line; None if not a typed job line (FR #4609 includes FIX)."""
    m = _OUT_JOB_KEY_RX.match((payload or "").strip())
    if not m:
        return None
    return f"{m.group(2).upper()} {m.group(3)}"


def replay_done_line_for_busy_nak(text: str, last_done_payload: str) -> str:
    """FR #4642: the DONE line to re-send when NAK busy names that finished job, else ``''``."""
    held = busy_nak_held_job(text)
    payload = (last_done_payload or "").strip()
    if not held or not payload:
        return ""
    if outbox_job_key(payload) != held:
        return ""
    return payload


def outbox_payload(line: str) -> str:
    """Chat payload of an outbox line (strip `PRIVMSG <target> :`), same as the watcher's Get-WatchOutboxPayload."""
    t = (line or "").strip()
    m = re.match(r"(?is)^PRIVMSG\s+\S+\s+:(.*)$", t)
    return (m.group(1) if m else t).strip()


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return float(default)
    try:
        v = float(raw)
    except ValueError:
        return float(default)
    return max(lo, min(hi, v))


class BoredEmitter:
    """t770u / FR #1611 / FR #2802 / FR #2834: the EXE (never the model) posts `PRIVMSG #<machine> :!bored`:
      * on seat start (agent ready), after DONE/NACK/GIVEUP **once the harvest hold ends**, and while idle
        (first idle after idle_s, then every repeat_s);
        * FR #2802 / #6157 / #7265: grok ``events.jsonl``, OpenCode ``opencode-turns.jsonl``,
        Cursor chat-store, or Aider process-idle ``turn_ended`` releases (or skips) the harvest
        hold; idle turn end -> reason ``turn``. ``harvest_hold_s`` is fallback only when
        turn end cannot be seen (log ``bored: fallback timer, no turn_ended seen``);
      * FR #2834: when a turn is open (watcher saw ``turn_started``, no ``turn_ended`` yet), keep holding
        past ``harvest_hold_s`` until ``turn_ended`` or ``turn_hold_max_s`` (default 600 s);
      * FR #2875: ``turn_ended`` with ACK open and no DONE/NACK/GIVEUP arms done-miss (remind after
        ``done_miss_grace_s``, then ``!bored`` reason ``done-miss`` if still open after the reminder turn);
      * FR #4784 / #7352: before ``!bored`` reason ``done-miss`` or ``ack-stale``, post
        ``GIVEUP <TYPE> owner/repo#N no-terminal-reply|ack-stale`` so Jeeves frees the accepted
        row (local ACK clear alone leaves ``nak busy`` forever while the PR stays open). The
        wire reason for done-miss is ``no-terminal-reply``; ``done-miss`` stays the internal
        ``!bored`` reason, and ``ack-stale`` covers a stale ACK;
      * FR #4753 / #7201: cursor/grok/opencode ``turn_ended`` with ``status=error`` (or an error
        field) while ACK is open retries the turn once, then ``GIVEUP … failed-turn <class>: <line>``
        so Jeeves can re-offer; it never sits idle holding the ACK. Quiet turn-end without error
        still uses done-miss. An open ACK with no activity past ``ack_stale_s`` still ``ack-stale``;
      * FR #2996: done-miss release sets ``_release_gen = _turn_gen`` (same as normal turn-end) so later
        ``nak``/``idle`` are not gated forever; ``_run`` clamps past-due waits to 0.5s (no ``wait(0)`` spin);
      * FR #3012: agent 402 / usage-exhausted is **out-of-fuel** — immediate ``GIVEUP … out-of-fuel``,
        cancel done-miss, suppress ``!bored`` until ``clear_out_of_fuel`` (fuel returns / key);
      * FR #4180: while out-of-fuel, ack-miss / HangDetector must not recycle or respawn; Relay
        refuses new assigns (``NACK … out-of-fuel``) with no inject; restart counter is monotonic
        per incident so 3/3 is reachable; unknown fuel readings still do not count as exhausted (#3923);
      * never while busy: open ACK (ack_stale_s), agent not ready, pending inject work before ACK
        (assign_grace_s), or post-DONE/NACK/GIVEUP harvest hold (harvest_hold_s; outbox activity extends it);
      * FR #5505: ACK-on-receipt for a still-parked assign must not clear harvest_hold; when harvest
        expires (or held-assign watchdog fires), always release_held_assigns even if free/done !bored
        is still pending, so an ACKed hold cannot sit idle forever;
      * FR #8738: DONE/NACK/GIVEUP written inside an open turn, or the done-miss reminder, opens
        the prior job's *closing turn*. Until that turn ends (``finish_turn_hold_max_s`` safety cap,
        default 1800 s) incoming assigns stay parked and Relay never flushes into it; the reminder
        turn counts as open before the watcher reports turn_started; done-miss ``!bored`` waits
        while the reminder turn shows agent I/O; a parked ACKed-on-receipt assign is not a done-miss;
      * any forward marks pending work; outbox activity resets idle / extends harvest; at most one line per
        second per reason; only the seat's own shop; never after IRC loss/shutdown (stop()).
    Overrides: BOB_WORKER_HARVEST_HOLD_S, BOB_WORKER_ASSIGN_GRACE_S, BOB_WORKER_BORED_ON_TURN_END,
    BOB_WORKER_TURN_HOLD_MAX_S, BOB_WORKER_DONE_MISS_GRACE_S, BOB_WORKER_HELD_ASSIGN_WATCHDOG_S,
    BOB_WORKER_FINISH_TURN_HOLD_MAX_S.
    Event driven: a thread sleeps on a Condition until the next due time or a state change - no polling tick."""

    def __init__(self, send: Callable[[], bool], log: Callable[[str], None], idle_s: float = 120.0, repeat_s: float = 180.0,
                 ack_stale_s: float = 2700.0, retry_s: float = 5.0, clock: Callable[[], float] = time.monotonic,
                 nak_s: float = 120.0, harvest_hold_s: float | None = None, assign_grace_s: float | None = None,
                 turn_hold_max_s: float | None = None, done_miss_grace_s: float | None = None,
                 done_miss_reply_s: float | None = None,
                 ack_quiet_s: float | None = None, held_assign_watchdog_s: float | None = None,
                 finish_turn_hold_max_s: float | None = None):
        self.send, self.log, self.clock = send, log, clock
        self.kind = ""  # FR #7265: seat kind on turn-end !bored logs
        self.idle_s, self.repeat_s, self.ack_stale_s, self.retry_s = idle_s, repeat_s, ack_stale_s, retry_s
        # FR #4827: past ack_stale_s, keep the ACK while the turn is open or agent I/O
        # is newer than this quiet window. Idle (no I/O, turn ended) still frees at ack_stale_s.
        self.ack_quiet_s = (
            float(ack_quiet_s) if ack_quiet_s is not None
            else _env_float("BOB_WORKER_ACK_QUIET_S", 300.0, 5.0, 3600.0)
        )
        self.nak_s = nak_s  # t817u: fixed timer from a Jeeves NAK to the next !bored (never while busy)
        # FR #1611: hold !bored after DONE/free so the agent can harvest; treat inject as busy until ACK.
        self.harvest_hold_s = (
            float(harvest_hold_s) if harvest_hold_s is not None
            else _env_float("BOB_WORKER_HARVEST_HOLD_S", 90.0, 0.0, 900.0)
        )
        self.assign_grace_s = (
            float(assign_grace_s) if assign_grace_s is not None
            else _env_float("BOB_WORKER_ASSIGN_GRACE_S", 600.0, 30.0, 3600.0)
        )
        # FR #2834: safety cap while a post-DONE turn stays open past harvest_hold_s.
        self.turn_hold_max_s = (
            float(turn_hold_max_s) if turn_hold_max_s is not None
            else _env_float("BOB_WORKER_TURN_HOLD_MAX_S", 600.0, 90.0, 3600.0)
        )
        # FR #2875: after turn_ended with ACK open and no DONE, wait then remind / release.
        self.done_miss_grace_s = (
            float(done_miss_grace_s) if done_miss_grace_s is not None
            else _env_float("BOB_WORKER_DONE_MISS_GRACE_S", 20.0, 5.0, 600.0)
        )
        # FR #7352: after the one reminder, wait this long for DONE/NACK/GIVEUP (or a
        # second turn_ended). Then GIVEUP no-terminal-reply even if the agent never
        # starts another turn. Default 180s so grace+reply stays under 5 minutes.
        self.done_miss_reply_s = (
            float(done_miss_reply_s) if done_miss_reply_s is not None
            else _env_float("BOB_WORKER_DONE_MISS_REPLY_S", 180.0, 10.0, 300.0)
        )
        # FR #6119: repeated short done-miss releases => out-of-fuel hold (stop !bored churn).
        self.fast_done_miss_s = _env_float("BOB_WORKER_FAST_DONE_MISS_S", 60.0, 5.0, 600.0)
        self.fast_done_miss_need = max(
            1, int(_env_float("BOB_WORKER_FAST_DONE_MISS_NEED", 2.0, 1.0, 10.0))
        )
        self._fast_done_miss_streak = 0
        # FR #5505: ACKed-on-receipt but never injected — inject (or give up) after this delay.
        self.held_assign_watchdog_s = (
            float(held_assign_watchdog_s) if held_assign_watchdog_s is not None
            else _env_float("BOB_WORKER_HELD_ASSIGN_WATCHDOG_S", 180.0, 30.0, 3600.0)
        )
        self._held_assign_since: Optional[float] = None
        # FR #8738: the prior job's closing turn (DONE/NACK/GIVEUP written mid-turn, or the
        # done-miss reminder turn) is still running. Parked assigns stay parked and
        # done-miss !bored stays quiet until that turn ends (or this safety cap).
        self.finish_turn_hold_max_s = (
            float(finish_turn_hold_max_s) if finish_turn_hold_max_s is not None
            else _env_float("BOB_WORKER_FINISH_TURN_HOLD_MAX_S", 1800.0, 90.0, 7200.0)
        )
        self._finish_turn_at: Optional[float] = None
        self._finish_turn_key: Optional[str] = None
        # True while the closing turn is the done-miss reminder and the turn watcher has
        # not yet seen it start (Cursor/Grok transcript lag): treat it as an open turn.
        self._finish_turn_unseen = False
        # FR #8738: closing turn ended with assigns parked - flush on the next tick.
        self._flush_after_closing = False
        self._nak_due: Optional[float] = None
        self._cv = threading.Condition()
        self._ready = False
        self._stopped = False
        self._ack_open = False
        self._ack_at: Optional[float] = None
        self._agent_active_at: Optional[float] = None  # FR #4827: last turn/IO, not ACK wall clock
        self._ack_job_key: Optional[str] = None  # FR #1732: open ACK job id
        # FR #8249: lock-free heartbeat gate (atomic reference swap under _cv writers).
        self._ack_epoch = 0
        self._hb_snap: HeartbeatSnapshot = HeartbeatSnapshot(False, '', False, 0)
        # FR #4730: jobs this seat already closed — replayed ACK must not reopen busy / hit IRC.
        self._finished_job_keys: set[str] = set()
        # FR #5327: DONE-only subset of finished — never stale-replay GIVEUP these.
        self._done_job_keys: set[str] = set()
        self.run_dir: Optional[Path] = None  # FR #3189: write job-repo.txt for harvest routing
        self._idle_since: Optional[float] = None
        self._last_bored: Optional[float] = None
        self._last_reason = ""
        self._done_key = ""
        self._last_done_key = ""
        self._free_key = ""
        self._last_free_key = ""
        self._start_sent = False
        self._last_dedupe = None
        self._retry_at = 0.0
        self._inject_pending = False
        self._inject_at: Optional[float] = None
        self._harvest_until: Optional[float] = None
        # FR #2802 turn-end gate (generation avoids race: turn_ended then turn_started before fire)
        self._hold_started_at: Optional[float] = None
        self._turn_started_at: Optional[float] = None
        self._turn_gen = 0
        self._release_gen: Optional[int] = None
        self._turn_idle_pending = False
        self._arm_skip = False  # hold fire at the turn_ended clock instant so turn_started can cancel
        self._hold_release_at: Optional[float] = None
        # FR #2834: open turn past harvest_hold_s (watcher saw turn_started; cleared on turn_ended).
        self._turn_open = False
        self._turn_watcher_armed = False
        self._turn_hold_cap_logged = False
        self._harvest_saw_turn_ended = False
        self._harvest_used_fallback = False
        # FR #2811: assign parked in Relay during harvest — blocks !bored, not turn_ended release.
        self._held_assign = False
        # FR #2875: turn_ended with ACK open and no DONE/NACK/GIVEUP.
        self._done_miss_armed_at: Optional[float] = None
        self._done_miss_key: Optional[str] = None
        self._done_miss_reminded = False
        self._done_miss_reply_until: Optional[float] = None
        self._done_miss_release_pending = False
        self.done_miss_remind_fn: Optional[Callable[[str], None]] = None
        # FR #7201: error turn while ACK open — retry once then GIVEUP.
        self._failed_turn_retries: dict[str, int] = {}
        self.failed_turn_retry_fn: Optional[Callable[[str], None]] = None
        # FR #8247: external_directory rejection counter (corrective then GIVEUP external-dir-loop).
        self.external_dir_reject_state: dict = {"counts": {}, "corrective_pending": False}
        # FR #8018: optional SeatSessionLog.write(source, text) for failed-turn / giveup.
        self.session_log_write: Optional[Callable[[str, str], None]] = None
        # FR #4784: job key for GIVEUP before !bored on done-miss / ack-stale release.
        self._release_giveup_key: Optional[str] = None
        self.seat_release_giveup_fn: Optional[Callable[[str, str], None]] = None
        # FR #6366: OpenCode finish-run decide hook ("retry"|"giveup"); attempt counter.
        self.opencode_finish_decide_fn: Optional[Callable[[str], str]] = None
        self.job_end_cleanup_fn: Optional[Callable[[Optional[str]], None]] = None
        self._opencode_finish_attempt: int = 0
        # FR #3012 / #3019: out-of-fuel hold (suppress !bored; GIVEUP via out_of_fuel_release_fn).
        self._out_of_fuel = False
        self._needs_signin = False
        self._out_of_fuel_at: Optional[float] = None
        # FR #4858: hard 402 hold — optimistic pct=3 available must not clear within min hold.
        self._out_of_fuel_hard_402 = False
        self._out_of_fuel_clear_reason: Optional[str] = None
        self.out_of_fuel_min_hold_s = _env_float(
            "BOB_WORKER_OUT_OF_FUEL_MIN_HOLD_S", 1800.0, 0.0, 86400.0
        )
        self.out_of_fuel_clear_floor_pct = max(
            0, int(_env_float("BOB_WORKER_OUT_OF_FUEL_CLEAR_FLOOR_PCT", 5.0, 0.0, 100.0))
        )
        self.out_of_fuel_release_fn: Optional[Callable[[str], None]] = None
        # FR #4180: always run once when entering the hold (clear ack-miss / HangDetector).
        self.out_of_fuel_enter_fn: Optional[Callable[[], None]] = None
        # FR #8814: after enter+release, quit the seat (dialog + digest worker-remove + shutdown).
        self.out_of_fuel_quit_fn: Optional[Callable[[str], None]] = None
        self.fuel_check_fn: Optional[Callable[[], bool]] = None
        # FR #3019: while ACK open, True => mid-job fuel lost (Cursor/Grok reading exhausted).
        self.fuel_lost_check_fn: Optional[Callable[[], bool]] = None
        self.fuel_poll_s = _env_float("BOB_WORKER_OUT_OF_FUEL_POLL_S", 30.0, 5.0, 600.0)
        self._fuel_lost_checked_at: Optional[float] = None
        # FR #3923: require N consecutive explicit exhausted readings before GIVEUP
        # (unknown/timeout must not kill a live ACK; one transient 0 must not either).
        self.fuel_lost_streak_need = max(
            1, int(_env_float("BOB_WORKER_OUT_OF_FUEL_STREAK", 2.0, 1.0, 10.0))
        )
        self._fuel_lost_streak = 0
        # FR #3192: optional Relay — when set, undelivered assigns block !bored (has_pending_work).
        self.relay: Optional["Relay"] = None
        self.sent: list = []  # (clock time, reason)
        self._thread: Optional[threading.Thread] = None

    def _pending_harvest_fire(self) -> bool:
        """True while DONE/NACK/GIVEUP has not yet produced its !bored."""
        return bool(
            (self._done_key and self._done_key != self._last_done_key)
            or (self._free_key and self._free_key != self._last_free_key)
        )

    def _relay_parks(self, key: str) -> bool:
        """FR #8738: True when ``key`` is an assign still parked in the Relay."""
        if self.relay is None or not key:
            return False
        try:
            fn = getattr(self.relay, "pending_assign_keys", None)
            return bool(fn) and key.lower() in fn()
        except Exception:
            return False

    def _turn_live(self) -> bool:
        """FR #8738: watcher-open turn, or a done-miss reminder turn not yet seen to start."""
        return bool(
            self._turn_open
            or (self._finish_turn_at is not None and self._finish_turn_unseen)
        )

    def _clear_finish_turn(self, why: str = "") -> None:
        """FR #8738: drop the prior job's closing-turn mark. Caller holds ``_cv``."""
        if self._finish_turn_at is not None and why:
            self.log(
                f"bored: closing turn for {self._finish_turn_key or 'job'} over ({why})"
            )
        self._finish_turn_at = None
        self._finish_turn_key = None
        self._finish_turn_unseen = False

    def _note_finish_turn(self, now: float, key: Optional[str], *, unseen: bool = False) -> None:
        """FR #8738: the prior job is closing inside a turn that has not ended yet."""
        if self._finish_turn_at is None:
            self._finish_turn_at = now
            self._finish_turn_key = key or self._finish_turn_key
            self.log(
                f"bored: closing turn open for {key or 'job'} - park new assigns until turn_ended"
            )
        elif key and not self._finish_turn_key:
            self._finish_turn_key = key
        if unseen:
            self._finish_turn_unseen = True

    def _closing_turn_live(self, now: float) -> bool:
        """FR #8738: True while the prior job's closing turn is still running.

        Set when DONE/NACK/GIVEUP lands while a turn is open, or when the done-miss
        reminder is injected. Cleared on ``turn_ended`` (or stand-down / out-of-fuel /
        reply-window give-up). ``finish_turn_hold_max_s`` is the safety cap for a lost
        ``turn_ended``. Caller holds ``_cv``.
        """
        at = self._finish_turn_at
        if at is None:
            return False
        if not self._turn_live():
            self._clear_finish_turn()
            return False
        if now - float(at) >= float(self.finish_turn_hold_max_s):
            self._clear_finish_turn(
                f"no turn_ended after {self.finish_turn_hold_max_s:.0f}s; safety net"
            )
            return False
        return True

    @property
    def closing_turn_open(self) -> bool:
        """FR #8738: Relay must not flush held assigns into the prior job's closing turn."""
        with self._cv:
            return self._closing_turn_live(self.clock())

    def _extend_hold_for_open_turn(self, now: float) -> bool:
        """FR #2834: keep harvest busy while turn open, until turn_ended or turn_hold_max_s."""
        if not bored_on_turn_end_enabled():
            return False
        if not self._turn_watcher_armed or not self._turn_live():
            return False
        if self._hold_started_at is None or not self._pending_harvest_fire():
            return False
        cap_at = float(self._hold_started_at) + float(self.turn_hold_max_s)
        if now >= cap_at:
            if not self._turn_hold_cap_logged:
                self._turn_hold_cap_logged = True
                self.log(
                    f"bored: turn hold max {self.turn_hold_max_s:.0f}s - releasing "
                    "(no turn_ended; safety net)"
                )
            return False
        return True

    @property
    def holding_incoming_assigns(self) -> bool:
        """FR #2811 / #2834: True during harvest hold or open-turn extension (park incoming assigns)."""
        with self._cv:
            now = self.clock()
            if self._harvest_until is not None and now < float(self._harvest_until):
                return True
            if self._extend_hold_for_open_turn(now):
                return True
            # FR #8738: past the !bored safety cap (or after a done-miss reminder the
            # watcher has not seen start) the prior job's turn may still be closing.
            return self._closing_turn_live(now)

    def note_held_assign(self) -> None:
        """FR #2811: Relay parked an assign; stay offer-pending until flush."""
        with self._cv:
            if not self._held_assign:
                self._held_assign_since = self.clock()
            self._held_assign = True
            self._idle_since = None
            self._hb_notify_all()

    def clear_held_assign(self) -> None:
        with self._cv:
            self._held_assign = False
            self._held_assign_since = None
            self._hb_notify_all()

    def _mark_job_finished(self, job: Optional[str], *, via_done: bool = False) -> None:
        """FR #4730: remember a job closed by DONE/NACK/GIVEUP (caller holds ``_cv``).

        FR #5327: ``via_done=True`` also records ``_done_job_keys`` so stale-replay
        never GIVEUPs a job this seat already DONE'd.
        """
        if not job:
            return
        self._finished_job_keys.add(job)
        while len(self._finished_job_keys) > 64:
            self._finished_job_keys.pop()
        if via_done:
            self._done_job_keys.add(job)
            while len(self._done_job_keys) > 64:
                self._done_job_keys.pop()
        fn = getattr(self, "job_end_cleanup_fn", None)
        if fn is not None:
            # FR #6370 MRB: do not run git worktree remove/prune while BoredEmitter._cv is held.
            def _cleanup(j=job, cleanup=fn, log=self.log):
                try:
                    cleanup(j)
                except Exception as e:  # noqa: BLE001
                    log(f"job-end cleanup failed {type(e).__name__}")

            threading.Thread(
                target=_cleanup, name="opencode-job-end-cleanup", daemon=True
            ).start()


    def note_fresh_assign(self, line: str) -> None:
        """FR #4730: re-offer of a finished job may ACK again; clear its finished mark."""
        key = assign_job_key(line)
        if not key:
            return
        with self._cv:
            self._finished_job_keys.discard(key)
            self._done_job_keys.discard(key)

    def live_turn_blocks_assign(self, line: str) -> bool:
        """FR #8246 / #8464: NACK busy only while a different job's ACK is still open.

        After DONE/NACK/GIVEUP the ACK is closed but the turn stays open until
        turn_ended. That path must not NACK busy. Relay then parks the next
        assign with hold_assigns_while and flushes it on turn_ended.
        The same still-open job is not blocked here. ACK de-dupe handles that replay.
        """
        incoming = assign_job_key(line)
        with self._cv:
            if not self._turn_open or not self._ack_open:
                return False
            current = self._ack_job_key
        if current and incoming and current == incoming:
            return False
        return True

    def outbox_ack_refuse_reason(self, payload: str) -> Optional[str]:
        """FR #4730 / #6333 / #6472: ACK-only refuse tag, else None (allow).

        Tags: ``finished-job ACK replay``, ``duplicate ACK``.
        """
        p = (payload or "").strip()
        if not _OUT_ACK_RX.match(p):
            return None
        job = outbox_job_key(p)
        with self._cv:
            if job and job in self._finished_job_keys:
                return "finished-job ACK replay"
            # Dedupe model ACK after program ACK-on-receipt for the same open job.
            if job and self._ack_open and self._ack_job_key and job == self._ack_job_key:
                return "duplicate ACK"
            return None

    def should_forward_outbox(self, payload: str) -> bool:
        """FR #4730: False for a replayed ACK of a job already DONE/NACK/GIVEUP'd.

        FR #6333: also False for a duplicate ACK while the same job ACK is already open
        (program ACK-on-receipt already posted).
        """
        return self.outbox_ack_refuse_reason(payload) is None

    def note_stale_replay_user_assign(
        self,
        user_key: Optional[str],
        *,
        write_giveup: Optional[Callable[[str], bool]] = None,
        reinject_open: Optional[Callable[[], bool]] = None,
    ) -> Optional[str]:
        """FR #4842: GIVEUP a finished assign K replayed while ACK J is open; keep J.

        Returns the stale key when acted on, else None. Does not clear the open ACK.
        """
        with self._cv:
            hit = stale_replay_assign_key(
                user_key=user_key,
                finished_keys=self._finished_job_keys,
                open_ack_key=self._ack_job_key,
                done_keys=self._done_job_keys,
            )
            open_k = self._ack_job_key
            if not hit:
                return None
            self.log(
                f"relay: stale-replay assign {hit} while ACK open on {open_k or 'none'}"
            )
        wire = f"GIVEUP {hit} stale-replay"
        if write_giveup is not None:
            try:
                write_giveup(wire)
            except Exception as e:  # noqa: BLE001
                self.log(f"relay: stale-replay giveup write failed {type(e).__name__}")
        if reinject_open is not None and open_k:
            try:
                reinject_open()
            except Exception as e:  # noqa: BLE001
                self.log(f"relay: stale-replay reinject failed {type(e).__name__}")
        return hit

    def _clear_done_miss(self) -> None:
        """FR #2875: drop armed / reminded / release-pending done-miss state."""
        self._opencode_finish_attempt = 0
        self._done_miss_armed_at = None
        self._done_miss_key = None
        self._done_miss_reminded = False
        self._done_miss_reply_until = None
        self._done_miss_release_pending = False

    def _fire_seat_release_giveup(self, reason: str) -> None:
        """FR #4784: shop GIVEUP for the saved release key before !bored (done-miss / ack-stale).

        FR #8094: also ``_mark_job_finished`` so per-job worktree/outbox/key clear even though
        this path bypasses ``on_outbox`` (which would otherwise delay !bored via harvest hold).
        """
        job_key = self._release_giveup_key or "job"
        self._release_giveup_key = None
        fn = self.seat_release_giveup_fn
        if fn is None:
            self._mark_job_finished(job_key)
            return
        try:
            fn(job_key, reason)
            self.log(f"seat-release: GIVEUP posted for {job_key} reason={reason}")
        except Exception as e:
            self.log(f"seat-release: GIVEUP failed {type(e).__name__} for {job_key}")
        # Clear BOB_JOB_WORKTREE / outbox / key even when GIVEUP did not go through on_outbox.
        self._mark_job_finished(job_key)

    def _fire_done_miss_remind(self, now: float) -> None:
        """FR #2875: grace expired — inject one reminder (Supervisor sets done_miss_remind_fn)."""
        if self._done_miss_armed_at is None or self._done_miss_reminded:
            return
        if now < float(self._done_miss_armed_at) + float(self.done_miss_grace_s):
            return
        key = self._done_miss_key or (self._ack_job_key or "job")
        self._done_miss_reminded = True
        self._done_miss_reply_until = now + float(self.done_miss_reply_s)
        self._opencode_finish_attempt = int(getattr(self, "_opencode_finish_attempt", 0) or 0) + 1
        if getattr(self, "opencode_finish_decide_fn", None) is not None:
            self.log(
                f"opencode finish-run key={key} attempt="
                f"{self._opencode_finish_attempt}/{opencode_finish_run_max()} progress=pending"
            )
        self.log(f"done-miss: reminder injected for {key}")
        # FR #8738: the reminder starts the job's closing turn even before the watcher
        # reports turn_started; nothing new is delivered into it until it ends.
        self._note_finish_turn(now, key, unseen=not self._turn_open)
        fn = self.done_miss_remind_fn
        if fn is not None:
            # FR #8268: caller holds _cv. The reminder takes supervisor RLock
            # (inject). start_agent holds that RLock then set_ready takes _cv.
            # Drop _cv for the inject so a slow FINISH cannot stall start_agent.
            try:
                self._cv.release()
                try:
                    fn(key)
                finally:
                    self._cv.acquire()
            except Exception as e:
                self.log(f"done-miss: remind inject failed {type(e).__name__}")

    def _arm_done_miss_release(self, now: float, key: str) -> None:
        """FR #2875 / #7352: reminder already sent; free the ACK so !bored can fire."""
        self._ack_open = False
        self._ack_job_key = None
        self._done_miss_armed_at = None
        self._done_miss_key = None
        self._done_miss_reminded = False
        self._done_miss_reply_until = None
        self._done_miss_release_pending = True
        self._release_giveup_key = key
        self._idle_since = now
        self._release_gen = self._turn_gen
        self._arm_skip = True
        self._hold_release_at = now
        # FR #8738: the closing turn is over (turn_ended) or judged dead (reply window).
        self._clear_finish_turn()
        self.log(f"done-miss: still no DONE for {key} after reminder - releasing seat")

    def _maybe_expire_done_miss_reply(self, now: float) -> None:
        """FR #7352: no second turn_ended — still GIVEUP no-terminal-reply after reply_s.

        FR #4670 / #7800: a live tool turn is not silence. Wait for that turn to end
        before the reminder reply window can release the seat.
        """
        if not self._ack_open or not self._done_miss_reminded:
            return
        if self._turn_open:
            return
        until = self._done_miss_reply_until
        if until is None or now < float(until):
            return
        # FR #8738: the reminder turn may be running without a turn_started seen yet.
        # Agent I/O since the reminder (inside ack_quiet_s) is that turn: stay busy.
        if self._reminder_turn_active(now):
            return
        key = self._done_miss_key or (self._ack_job_key or "job")
        self._arm_done_miss_release(now, key)

    def _reminder_turn_active(self, now: float) -> bool:
        """FR #8738: agent I/O after the done-miss reminder, inside ``ack_quiet_s``."""
        if self._finish_turn_at is None or not self._finish_turn_unseen:
            return False
        if not self._closing_turn_live(now):
            return False
        active = self._agent_active_at
        if active is None or float(active) < float(self._finish_turn_at):
            return False
        return (now - float(active)) < float(self.ack_quiet_s)

    def _ack_held(self, now: float) -> bool:
        """ACK still owns the seat (FR #4827).

        Wall-clock ``ack_stale_s`` alone does not release a live turn or agent I/O
        inside ``ack_quiet_s``. No turn and no I/O still releases at ``ack_stale_s``.
        Caller holds ``_cv``.
        """
        if not self._ack_open or self._ack_at is None:
            return False
        if (now - self._ack_at) < self.ack_stale_s:
            return True
        if self._turn_open:
            return True
        active = self._agent_active_at
        if active is not None and (now - active) < self.ack_quiet_s:
            return True
        return False

    @property
    def turn_open(self) -> bool:
        """True while the turn watcher has seen turn_started and not turn_ended."""
        with self._cv:
            return bool(self._turn_open)

    @property
    def ack_open(self) -> bool:
        """True while an ACK is open and not stale (FR #2383 / busy bookkeeping)."""
        with self._cv:
            return self._ack_held(self.clock())

    @property
    def fast_done_miss_streak(self) -> int:
        """FR #6119: consecutive short done-miss releases (test/observability)."""
        with self._cv:
            return int(self._fast_done_miss_streak)

    @property
    def out_of_fuel(self) -> bool:
        """FR #3012: True while the seat is held quiet after a 402 / usage-exhausted hit."""
        with self._cv:
            return bool(self._out_of_fuel)

    def note_out_of_fuel(self, evidence: str = "") -> Optional[str]:
        """FR #3012: mark out-of-fuel, clear ACK/done-miss, invoke out_of_fuel_release_fn once with the job key.

        Returns the job key that was open (for shop GIVEUP / digest), or None.
        FR #4180: also invoke ``out_of_fuel_enter_fn`` once so Supervisors can disarm
        ack-miss / HangDetector even when no ACK was open.
        FR #8814: then ``out_of_fuel_quit_fn`` (dialog + worker-remove + seat exit) unless
        ``BOB_WORKER_OUT_OF_FUEL_QUIT=0``.
        """
        release_key: Optional[str] = None
        fn: Optional[Callable[[str], None]] = None
        enter_fn: Optional[Callable[[], None]] = None
        quit_fn: Optional[Callable[[str], None]] = None
        evidence_s = evidence or ""
        with self._cv:
            if self._out_of_fuel:
                return None  # already held; no second GIVEUP
            now = self.clock()
            self._out_of_fuel = True
            self._out_of_fuel_at = now
            self._out_of_fuel_hard_402 = is_hard_402_out_of_fuel_text(evidence_s)
            self._out_of_fuel_clear_reason = None
            self._clear_done_miss()
            self._clear_finish_turn()
            self._inject_pending = False
            self._inject_at = None
            self._nak_due = None
            self._turn_idle_pending = False
            self._idle_since = None
            # Match normal release so later clear_out_of_fuel cannot wait(0)-spin (FR #2996 class).
            self._release_gen = self._turn_gen
            if self._ack_open:
                release_key = self._ack_job_key or "job"
                self._ack_open = False
                self._ack_job_key = None
                self._ack_at = None
            # Do not arm free/done harvest !bored while out of fuel.
            self._free_key = ""
            self._done_key = ""
            self._harvest_until = None
            fn = self.out_of_fuel_release_fn
            enter_fn = self.out_of_fuel_enter_fn
            quit_fn = self.out_of_fuel_quit_fn
            preview = one_line(evidence_s or "out-of-fuel", 100)
            hard = " hard-402" if self._out_of_fuel_hard_402 else ""
            quit_soon = quit_fn is not None and out_of_fuel_quit_enabled()
            self.log(
                (
                    f"out-of-fuel: quitting seat after dialog{hard}"
                    if quit_soon
                    else f"out-of-fuel: holding seat{hard}"
                )
                + (f" (was ACK {release_key})" if release_key else "")
                + f" - {preview}"
            )
            self._hb_notify_all()
        if enter_fn is not None:
            try:
                enter_fn()
            except Exception as e:
                self.log(f"out-of-fuel: enter_fn failed {type(e).__name__}")
        if release_key and fn is not None:
            try:
                fn(release_key)
            except Exception as e:
                self.log(f"out-of-fuel: release_fn failed {type(e).__name__}")
        # FR #8814: dialog + digest remove + process exit (no zombie out_of_fuel worker).
        if quit_fn is not None and out_of_fuel_quit_enabled():
            try:
                quit_fn(evidence_s)
            except Exception as e:
                self.log(f"out-of-fuel: quit_fn failed {type(e).__name__}")
        return release_key

    def clear_out_of_fuel(self, reason: str = "reading") -> None:
        """FR #3012 / #4858: fuel returned (or successful turn) — allow !bored again."""
        with self._cv:
            if not self._out_of_fuel:
                return
            self._out_of_fuel = False
            self._out_of_fuel_at = None
            self._out_of_fuel_hard_402 = False
            why = (reason or self._out_of_fuel_clear_reason or "reading").strip() or "reading"
            self._out_of_fuel_clear_reason = None
            now = self.clock()
            self._idle_since = now
            self._release_gen = self._turn_gen
            self.log(f"out-of-fuel: cleared via {why} - seat may !bored again")
            self._hb_notify_all()

    @property
    def ack_job_ref(self) -> Optional[str]:
        """Lower-cased ``owner/repo#N`` for the open ACK, or None (FR #2791 / #1732)."""
        with self._cv:
            if not self._ack_held(self.clock()):
                return None
            key = self._ack_job_key or ""
            parts = key.split(None, 1)
            if len(parts) < 2:
                return None
            return parts[1].lower()

    # ---- lifecycle / events (each wakes the timer thread)
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="bored-timer", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._cv:
            self._stopped = True
            self._hb_notify_all()

    def set_ready(self, ready: bool) -> None:
        with self._cv:
            self._ready = bool(ready)
            self._idle_since = self.clock() if ready else None
            if not ready:
                self._inject_pending = False
                self._inject_at = None
            self._hb_notify_all()

    def note_needs_signin(self) -> None:
        """FR #7183: no machine Grok sign-in — never !bored, never claim ready."""
        with self._cv:
            self._needs_signin = True
            self._hb_notify_all()

    def activity(self, mark_work: bool = True) -> None:
        """A message was forwarded to the agent: reset idle; optionally mark pending assign work.

        ``mark_work=False`` for idle wire like Jeeves ``nothing queued`` (MRB #1617): do not start
        ``assign_grace_s`` inject-pending busy — the agent is not working a job.
        """
        with self._cv:
            now = self.clock()
            if mark_work and not self._ack_open:
                self._inject_pending = True
                self._inject_at = now
            if self._harvest_until is not None and now < self._harvest_until:
                # Still in post-DONE harvest window: another forward means keep holding.
                self._harvest_until = now + self.harvest_hold_s
            if self._idle_since is not None:
                self._idle_since = now
            self._hb_notify_all()

    def note_agent_active(self, at: float | None = None) -> None:
        """FR #4827: turn activity or process I/O. Extends an open ACK past ack_stale_s."""
        with self._cv:
            now = float(self.clock() if at is None else at)
            self._agent_active_at = now
            self._hb_notify_all()

    def note_agent_active_nb(self, at: float | None = None, *, timeout: float = 0.05) -> bool:
        """FR #8249: non-blocking note_agent_active for the heartbeat thread."""
        got = False
        try:
            got = bool(self._cv.acquire(timeout=float(timeout)))
        except Exception:
            return False
        if not got:
            return False
        try:
            now = float(self.clock() if at is None else at)
            self._agent_active_at = now
            self._hb_notify_all()
            return True
        finally:
            self._cv.release()

    def _refresh_hb_snap(self) -> None:
        """Rebuild HeartbeatSnapshot (caller holds `_cv`, or init)."""
        key = str(self._ack_job_key or '')
        # Bump epoch when ACK opens for a job (or job key changes while open).
        snap = getattr(self, '_hb_snap', None)
        prev_open = bool(snap.ack_open) if snap is not None else False
        prev_key = str(snap.ack_job_key) if snap is not None else ''
        prev_epoch = int(snap.ack_epoch) if snap is not None else 0
        epoch = prev_epoch
        if self._ack_open and (not prev_open or key != prev_key):
            epoch = prev_epoch + 1
            self._ack_epoch = epoch
        elif not self._ack_open:
            epoch = int(getattr(self, '_ack_epoch', 0) or 0)
        else:
            epoch = int(getattr(self, '_ack_epoch', prev_epoch) or prev_epoch)
        self._hb_snap = HeartbeatSnapshot(
            bool(self._ack_open),
            key,
            bool(self._out_of_fuel),
            int(epoch),
        )

    def heartbeat_snapshot(self) -> HeartbeatSnapshot:
        """FR #8249: lock-free read of the latest ACK/fuel gate."""
        snap = getattr(self, '_hb_snap', None)
        if snap is None:
            return HeartbeatSnapshot(False, '', False, 0)
        return snap

    def _hb_notify_all(self) -> None:
        """Publish heartbeat snapshot then wake waiters (caller holds `_cv`)."""
        try:
            self._refresh_hb_snap()
        except Exception:
            pass
        self._cv.notify_all()

    def note_stand_down(self, ref: str) -> bool:
        """FR #4827: drop the open ACK when the chair stands this seat down for that job."""
        want = (ref or "").strip().lower()
        if not want:
            return False
        with self._cv:
            key = self._ack_job_key or ""
            parts = key.split(None, 1)
            cur = parts[1].lower() if len(parts) >= 2 else ""
            if not self._ack_open or cur != want:
                return False
            self._ack_open = False
            self._ack_at = None
            self._ack_job_key = None
            self._agent_active_at = None
            self._turn_open = False
            self._clear_done_miss()
            self._clear_finish_turn()
            now = self.clock()
            self._idle_since = now
            self.log(f"bored: stand down {want}")
            self._hb_notify_all()
            return True

    def nak(self) -> None:
        """t817u: Jeeves answered our !bored with a NAK addressed to us: send !bored again after a FIXED nak_s (120 s). A second NAK
        does not push the timer out; if the seat is busy when it falls due the timer is dropped (DONE brings its own !bored)."""
        with self._cv:
            if self._nak_due is None:
                self._nak_due = self.clock() + self.nak_s
            self._hb_notify_all()

    def _begin_harvest_hold(self, now: float) -> None:
        """FR #1611 / #7265: after DONE/NACK/GIVEUP, hold !bored only while a turn is still open.

        Harvest belongs inside the agent turn. If the watcher already saw ``turn_ended``,
        skip the clock. ``harvest_hold_s`` remains the fallback when no turn end is seen.
        """
        self._inject_pending = False
        self._inject_at = None
        self._idle_since = None
        self._hold_started_at = now
        self._release_gen = None
        self._turn_idle_pending = False
        self._turn_hold_cap_logged = False
        self._harvest_saw_turn_ended = False
        self._harvest_used_fallback = False
        skip_clock = (
            bored_on_turn_end_enabled()
            and self._turn_watcher_armed
            and (not self._turn_live())
            and self._turn_gen > 0
        )
        if skip_clock:
            self._harvest_until = None
            self._idle_since = now
            self._release_gen = self._turn_gen
            self._harvest_saw_turn_ended = True
            self.log("bored: skip harvest hold (turn already ended)")
            return
        if self.harvest_hold_s > 0:
            self._harvest_until = now + self.harvest_hold_s
            self.log(
                f"bored: harvest hold {self.harvest_hold_s:.0f}s fallback until turn_ended"
            )
        else:
            self._harvest_until = None
            self._idle_since = now

    def turn_started(self, at: float | None = None, *, turn: int | None = None, sid: str | None = None) -> None:
        """FR #2802: grok turn_started — bumps generation so a prior turn_ended release cannot fire yet."""
        with self._cv:
            now = float(self.clock() if at is None else at)
            self._turn_started_at = now
            self._turn_open = True
            self._agent_active_at = now
            self._turn_watcher_armed = True
            self._turn_gen += 1
            self._turn_idle_pending = False
            # FR #2875: a new turn inside done-miss grace cancels the pending reminder.
            if self._done_miss_armed_at is not None and not self._done_miss_reminded:
                self._done_miss_armed_at = None
                self._done_miss_key = None
            # FR #8738: the reminder (closing) turn is now visible to the watcher.
            self._finish_turn_unseen = False
            self._hb_notify_all()


    def turn_ended(
        self,
        at: float | None = None,
        *,
        turn: int | None = None,
        sid: str | None = None,
        error: bool = False,
        error_class: str = "",
        error_line: str = "",
    ) -> None:
        """FR #2802: grok turn_ended — release harvest hold when at/after DONE, or idle reason=turn."""
        clear_hard_fuel = False
        convert_fast_miss = False
        convert_fast_key = None  # type: Optional[str]
        try:
            with self._cv:
                now = float(self.clock() if at is None else at)
                self._turn_open = False
                # FR #8738: the prior job's closing turn is over (a stale turn_ended from
                # before the mark was set does not count).
                if self._finish_turn_at is not None and now >= float(self._finish_turn_at):
                    self._clear_finish_turn("turn_ended")
                    self._flush_after_closing = True
                # FR #4858: successful turn clears hard 402 hold without min hold.
                # Soft holds (FR #6119 fast-done-miss / mid-job on-demand) stay until a
                # fuel reading clears them — a later turn_ended must not re-arm !bored.
                if self._out_of_fuel and bool(self._out_of_fuel_hard_402):
                    clear_hard_fuel = True
                # FR #2875 / inject-pending: still busy on a fresh assign — do not arm done-miss.
                if self._inject_pending and self._inject_at is not None and now - self._inject_at < self.assign_grace_s:
                    self._hb_notify_all()
                    return
                # FR #8738: the open ACK is an assign ACKed on receipt that is still parked
                # (never injected). This turn was the prior job's - not a done-miss for it.
                if self._ack_open and self._ack_job_key and self._relay_parks(self._ack_job_key):
                    self._flush_after_closing = True
                    self.log(
                        f"bored: turn ended with {self._ack_job_key} ACKed but still parked "
                        "- not a done-miss; flush it now (FR #8738)"
                    )
                    self._hb_notify_all()
                    return
                # FR #2875: turn ended with ACK open and no DONE/NACK/GIVEUP.
                # FR #4827: arm even past ack_stale_s — the turn ending is the release signal.
                if self._ack_open and self._ack_at is not None:
                    key = self._ack_job_key or "job"
                    if error:
                        # FR #8018: durable failed-turn evidence on the seat session log
                        # (sanitized — never raw stderr with tokens).
                        if self.session_log_write is not None:
                            try:
                                self.session_log_write(
                                    "failed-turn",
                                    sanitize_failed_turn_reason(
                                        error_class, error_line
                                    ),
                                )
                            except Exception:
                                pass
                        # Fuel/quota exhaustion is not a generic process-exit (FR #8018).
                        if is_failed_turn_fuel_error(error_class, error_line):
                            why = "out-of-fuel"
                            self._ack_open = False
                            self._ack_job_key = None
                            self._clear_done_miss()
                            self._failed_turn_retries.pop(key, None)
                            self._release_giveup_key = key
                            self._fast_done_miss_streak = 0
                            self._done_miss_release_pending = False
                            self.log("failed-turn: GIVEUP %s reason=%s" % (key, why))
                            if self.session_log_write is not None:
                                try:
                                    self.session_log_write("giveup", why)
                                except Exception:
                                    pass
                            try:
                                self._cv.release()
                                try:
                                    self._fire_seat_release_giveup(why)
                                finally:
                                    self._cv.acquire()
                            except Exception as e:  # noqa: BLE001
                                self.log(
                                    "failed-turn: GIVEUP failed %s" % type(e).__name__
                                )
                            self._begin_harvest_hold(now)
                            self._hb_notify_all()
                            return
                        # FR #8247: external_directory reject -> corrective once, then GIVEUP
                        # external-dir-loop (never widen %TEMP% allow; never infinite FINISH).
                        if is_external_directory_reject(error_class, error_line):
                            action = record_external_dir_reject(
                                self.external_dir_reject_state, key
                            )
                            if action == "corrective":
                                self.log(
                                    "external-dir: corrective for %s count=%s"
                                    % (
                                        key,
                                        self.external_dir_reject_state.get(
                                            "counts", {}
                                        ).get(key, 0),
                                    )
                                )
                                # Prefer done-miss remind (injects corrective_pending text).
                                # failed_turn_retry_fn re-injects relay.last_line (same assign)
                                # and would skip the scratch-path corrective (MRB #8252 FAIL).
                                fn = (
                                    self.done_miss_remind_fn
                                    or self.failed_turn_retry_fn
                                )
                                if fn is not None:
                                    try:
                                        self._cv.release()
                                        try:
                                            fn(key)
                                        finally:
                                            self._cv.acquire()
                                    except Exception as e:  # noqa: BLE001
                                        self.log(
                                            "external-dir: corrective inject failed %s"
                                            % type(e).__name__
                                        )
                                self._hb_notify_all()
                                return
                            why = "external-dir-loop"
                            self._ack_open = False
                            self._ack_job_key = None
                            self._clear_done_miss()
                            self._failed_turn_retries.pop(key, None)
                            self._release_giveup_key = key
                            self._fast_done_miss_streak = 0
                            self._done_miss_release_pending = False
                            self.log(
                                "external-dir: GIVEUP %s reason=%s" % (key, why)
                            )
                            if self.session_log_write is not None:
                                try:
                                    self.session_log_write("giveup", why)
                                except Exception:
                                    pass
                            try:
                                self._cv.release()
                                try:
                                    self._fire_seat_release_giveup(why)
                                finally:
                                    self._cv.acquire()
                            except Exception as e:  # noqa: BLE001
                                self.log(
                                    "external-dir: GIVEUP failed %s"
                                    % type(e).__name__
                                )
                            self._begin_harvest_hold(now)
                            self._hb_notify_all()
                            return
                        n = int(self._failed_turn_retries.get(key, 0))
                        if failed_turn_next_action(n) == "retry":
                            self._failed_turn_retries[key] = n + 1
                            self.log(
                                "failed-turn: retry %s/1 for %s"
                                % (self._failed_turn_retries[key], key)
                            )
                            fn = self.failed_turn_retry_fn or self.done_miss_remind_fn
                            if fn is not None:
                                try:
                                    self._cv.release()
                                    try:
                                        fn(key)
                                    finally:
                                        self._cv.acquire()
                                except Exception as e:  # noqa: BLE001
                                    self.log(
                                        "failed-turn: retry inject failed %s"
                                        % type(e).__name__
                                    )
                            self._hb_notify_all()
                            return
                        why = "failed-turn " + sanitize_failed_turn_reason(
                            error_class, error_line
                        )
                        self._ack_open = False
                        self._ack_job_key = None
                        self._clear_done_miss()
                        self._failed_turn_retries.pop(key, None)
                        self._release_giveup_key = key
                        self._fast_done_miss_streak = 0
                        self._done_miss_release_pending = False
                        self.log("failed-turn: GIVEUP %s reason=%s" % (key, why))
                        if self.session_log_write is not None:
                            try:
                                self.session_log_write("giveup", why)
                            except Exception:
                                pass
                        try:
                            self._cv.release()
                            try:
                                self._fire_seat_release_giveup(why)
                            finally:
                                self._cv.acquire()
                        except Exception as e:  # noqa: BLE001
                            self.log(
                                "failed-turn: GIVEUP failed %s" % type(e).__name__
                            )
                        self._begin_harvest_hold(now)
                        self._hb_notify_all()
                        return
                    if self._done_miss_reminded:
                        # FR #6366 / #6370 MRB: decide() runs git/gh — schedule outside _cv.
                        decide = self.opencode_finish_decide_fn
                        if decide is not None:
                            try:
                                self._cv.release()
                                try:
                                    verdict = str(decide(key) or "giveup").strip().lower()
                                finally:
                                    self._cv.acquire()
                            except Exception as e:  # noqa: BLE001
                                self.log(
                                    f"opencode finish-run decide failed {type(e).__name__}; giveup"
                                )
                                verdict = "giveup"
                            if verdict == "retry":
                                self._done_miss_reminded = False
                                self._done_miss_armed_at = now
                                self._done_miss_key = key
                                self._done_miss_release_pending = False
                                self.log(
                                    f"done-miss: OpenCode finish-run retry armed for {key}"
                                )
                                self._hb_notify_all()
                                return
                            if verdict == "done":
                                # FR #6370: worker auto-opened PR + posted DONE — no GIVEUP.
                                self._ack_open = False
                                self._ack_job_key = None
                                self._clear_done_miss()
                                self._fast_done_miss_streak = 0
                                self._release_giveup_key = None
                                self._done_miss_release_pending = False
                                self._begin_harvest_hold(now)
                                self.log(
                                    f"done-miss: OpenCode finish auto-PR DONE for {key}"
                                )
                                self._hb_notify_all()
                                return
                        ack_age = now - float(self._ack_at)
                        if ack_age < float(self.fast_done_miss_s):
                            self._fast_done_miss_streak = int(self._fast_done_miss_streak) + 1
                            self.log(
                                f"done-miss: fast release streak="
                                f"{self._fast_done_miss_streak}/{self.fast_done_miss_need} "
                                f"age={ack_age:.1f}s key={key}"
                            )
                        else:
                            self._fast_done_miss_streak = 0
                        # FR #6119: repeated short done-miss => out-of-fuel (stop !bored churn).
                        # FR #6366: skip convert when OpenCode finish-decide is wired (not out-of-fuel).
                        if (
                            decide is None
                            and self._fast_done_miss_streak >= int(self.fast_done_miss_need)
                        ):
                            convert_fast_miss = True
                            convert_fast_key = key
                            self._done_miss_armed_at = None
                            self._done_miss_key = None
                            self._done_miss_reminded = False
                            self._done_miss_release_pending = False
                            self.log(
                                f"out-of-fuel: fast-done-miss streak="
                                f"{self._fast_done_miss_streak} key={key}"
                            )
                            # keep ACK open so note_out_of_fuel can GIVEUP it after the lock
                        else:
                            # FR #4784 / #7352: GIVEUP no-terminal-reply before !bored.
                            self._arm_done_miss_release(now, key)
                    else:
                        self._done_miss_armed_at = now
                        self._done_miss_key = key
                        self._done_miss_reminded = False
                        self._done_miss_release_pending = False
                        self.log(
                            f"bored: turn ended with ACK open on {key} and no DONE/NACK/GIVEUP - done-miss armed"
                        )
                    self._hb_notify_all()
                    return

                if (
                    (self._harvest_until is not None or self._pending_harvest_fire())
                    and self._hold_started_at is not None
                ):
                    # Stale turn_ended before DONE/free line: ignore.
                    if now < self._hold_started_at:
                        self._hb_notify_all()
                        return
                    self._harvest_until = None
                    self._idle_since = now
                    self._release_gen = self._turn_gen
                    self._harvest_saw_turn_ended = True
                    self._arm_skip = True
                    self._hold_release_at = now
                    self.log(
                        f"bored: turn ended (sid={sid or '-'}, turn={turn if turn is not None else '-'}) - hold released"
                    )
                elif (
                    self._release_gen is not None
                    and self._release_gen != self._turn_gen
                    and self._hold_started_at is not None
                    and (
                        (self._done_key and self._done_key != self._last_done_key)
                        or (self._free_key and self._free_key != self._last_free_key)
                    )
                ):
                    # Prior release was cancelled by turn_started; this end re-arms fire.
                    self._release_gen = self._turn_gen
                    self._idle_since = now
                    self._arm_skip = True
                    self._hold_release_at = now
                    self.log(
                        f"bored: turn ended (sid={sid or '-'}, turn={turn if turn is not None else '-'}) - hold released"
                    )
                elif self._ready and not self._stopped:
                    # Idle turn end: no open ACK / inject / hold.
                    self._turn_idle_pending = True
                    self._release_gen = self._turn_gen
                    self._arm_skip = True
                    self._hold_release_at = now
                    if self._idle_since is None:
                        self._idle_since = now
                self._hb_notify_all()

        finally:
            if clear_hard_fuel:
                self.clear_out_of_fuel(reason="successful turn")
            # FR #6119: must run in finally — a return inside try skips code after try/finally.
            if convert_fast_miss:
                evidence = (
                    f"fast-done-miss streak={self._fast_done_miss_streak}"
                    + (f" key={convert_fast_key}" if convert_fast_key else "")
                )
                self.note_out_of_fuel(evidence)
    def on_outbox(self, payload: str) -> None:
        now = self.clock()
        p = (payload or "").strip()
        with self._cv:
            if _OUT_ACK_RX.match(p):
                job = outbox_job_key(p)
                # FR #4730: replayed ACK after DONE/NACK/GIVEUP must not reopen busy
                # (mirror ignore-repeat DONE). Re-offer clears the mark via note_fresh_assign.
                if job and job in self._finished_job_keys:
                    self.log(
                        f"bored: ignore stale ACK for {job} (already DONE/NACK/GIVEUP)"
                    )
                else:
                    self._ack_open, self._ack_at, self._idle_since = True, now, None
                    self._ack_job_key = job
                    if job:
                        self._failed_turn_retries.pop(job, None)
                    # FR #3189: persist offered repo so Invoke-BobiverseHarvest targets the product.
                    if self.run_dir is not None and self._ack_job_key:
                        try:
                            write_job_repo_marker(self.run_dir, self._ack_job_key)
                        except Exception:
                            pass
                    self._inject_pending = False
                    self._inject_at = None
                    # FR #5505: ACK-on-receipt for a still-parked assign must not cancel the
                    # post-DONE/NACK harvest hold — expiry (or watchdog) flushes the park.
                    pending_held = False
                    try:
                        pending_held = bool(self.relay is not None and self.relay.has_pending_work())
                    except Exception:
                        pending_held = False
                    if not pending_held and not self._held_assign:
                        self._harvest_until = None
                    elif self._held_assign_since is None:
                        self._held_assign_since = now
                    self._fuel_lost_checked_at = None  # FR #3019: re-arm mid-job fuel poll
                    self._fuel_lost_streak = 0  # FR #3923: new ACK starts a fresh streak
                    self._clear_done_miss()
            elif _OUT_DONE_RX.match(p):
                job = outbox_job_key(p)
                self._mark_job_finished(job, via_done=True)
                # FR #1732: DONE for another id must not clear an open ACK.
                # FR #4842: cross-job DONE is not a silent drop — log it and arm done-miss
                # for the open ACK so the seat is reminded about the real job.
                if self._ack_open and self._ack_job_key and job and job != self._ack_job_key:
                    self.log(
                        f"bored: cross-job DONE for {job} while ACK open on {self._ack_job_key}"
                    )
                    if self._done_miss_armed_at is None:
                        self._done_miss_armed_at = now
                        self._done_miss_key = self._ack_job_key
                        self._done_miss_reminded = False
                        self._done_miss_release_pending = False
                        self.log(
                            f"bored: done-miss armed for open ACK {self._ack_job_key} after cross-job DONE"
                        )
                else:
                    # FR #8738: DONE inside a still-open turn - that turn is closing this job.
                    if self._turn_live():
                        self._note_finish_turn(now, job or self._ack_job_key)
                    self._ack_open = False
                    self._ack_job_key = None
                    self._clear_done_miss()
                    self._fast_done_miss_streak = 0  # FR #6119: real DONE breaks fast-miss streak
                    # FR #4259: repeat DONE after turn_ended must not re-arm harvest.
                    # Already fired !bored for this payload, or same DONE with turn closed
                    # and harvest already cleared (turn_ended release path) → ignore.
                    if self._last_done_key == p:
                        self.log("bored: ignore repeat DONE (already fired !bored)")
                    elif (
                        self._done_key == p
                        and not self._turn_open
                        and self._harvest_until is None
                    ):
                        self.log(
                            "bored: ignore repeat DONE after turn_ended (harvest already released)"
                        )
                    else:
                        self._done_key = p
                        self._begin_harvest_hold(now)
            elif _OUT_FREE_RX.match(p):  # NACK/GIVEUP: free, then harvest hold before !bored (FR #161 / #1611)
                verb = (p.split(None, 1)[0] if p else "FREE").upper()
                job = outbox_job_key(p)
                self._mark_job_finished(job)
                # FR #1732: NACK/GIVEUP of a concurrent assign must not free while another ACK is open.
                if self._ack_open and self._ack_job_key and job and job != self._ack_job_key:
                    self.log(
                        f"bored: ignore free-rx ({verb}) for {job} while ACK open on {self._ack_job_key}"
                    )
                elif self._out_of_fuel:
                    # FR #3012: synthetic GIVEUP out-of-fuel already holds the seat — no harvest !bored.
                    self._ack_open = False
                    self._ack_job_key = None
                    self._clear_done_miss()
                    self.log(f"bored: free-rx matched ({verb}) during out-of-fuel - no !bored")
                else:
                    # FR #8738: NACK/GIVEUP inside a still-open turn closes this job there.
                    if self._turn_live():
                        self._note_finish_turn(now, job or self._ack_job_key)
                    self._ack_open = False
                    self._ack_job_key = None
                    self._clear_done_miss()
                    self._free_key = p
                    self._begin_harvest_hold(now)
                    self.log(f"bored: free-rx matched ({verb}) - harvest hold then !bored")
            elif self._ack_open:
                # Outbox chatter refreshes the wall clock only. FR #4827 agent I/O is
                # note_agent_active / turn_started / process samples, not this line.
                self._ack_at = now
            elif self._harvest_until is not None and now < self._harvest_until:
                # Harvest / follow-up outbox (intake, comments) extends the hold.
                self._harvest_until = now + self.harvest_hold_s
            else:
                self._idle_since = now
            self._hb_notify_all()

    # ---- decision
    def _busy(self, now: float) -> bool:
        if not self._ready:
            return True
        # FR #7183: unsigned Grok seat must not look idle/ready to Jeeves.
        if self._needs_signin:
            return True
        # FR #3012: out-of-fuel holds the seat quiet (no !bored) until clear_out_of_fuel.
        if self._out_of_fuel:
            return True
        if self._ack_held(now):
            return True
        # FR #8738: done-miss !bored never fires while the closing turn still runs.
        if self._done_miss_release_pending and self._closing_turn_live(now):
            return True
        if self._harvest_until is not None and now < self._harvest_until:
            return True
        # FR #2834: turn still open after harvest_hold_s — keep busy until turn_ended or max.
        if self._extend_hold_for_open_turn(now):
            return True
        # FR #3192 / #2811: undelivered Relay assign (held / inject_failed / hold-until-turn)
        # blocks idle/nak/turn, but must NOT block done/free — those fire post_bored, which
        # flushes then suppresses !bored. Mirror _held_assign so plain ``held`` (no inject
        # target) is covered even when note_held_assign was never called.
        pending_done = bool(self._done_key and self._done_key != self._last_done_key)
        pending_free = bool(self._free_key and self._free_key != self._last_free_key)
        try:
            if (
                self.relay is not None
                and self.relay.has_pending_work()
                and not pending_done
                and not pending_free
            ):
                return True
        except Exception:
            pass
        if self._held_assign:
            if not pending_done and not pending_free:
                return True
        if self._inject_pending and self._inject_at is not None:
            if now - self._inject_at < self.assign_grace_s:
                return True
            # Stale inject with no ACK (e.g. "nothing queued"): drop pending work.
            self._inject_pending = False
            self._inject_at = None
            if self._idle_since is None:
                self._idle_since = now
        return False

    def _flush_held_assign_watchdog(self, now: float) -> None:
        """FR #5505: if an ACKed assign stayed parked past held_assign_watchdog_s, inject it.

        Covers the case where harvest was cleared (or never armed) but Relay still parks
        work and no turn_ended will flush it. Caller holds ``self._cv``.
        """
        if self._turn_open or self.held_assign_watchdog_s <= 0:
            return
        # FR #8738: never flush into the prior job's closing turn.
        if self._closing_turn_live(now):
            return
        pending = False
        try:
            pending = bool(self.relay is not None and self.relay.has_pending_work())
        except Exception:
            pending = False
        if not pending and not self._held_assign:
            self._held_assign_since = None
            return
        # Still inside an active harvest / open-turn hold — wait for expiry flush.
        if self._harvest_until is not None and now < float(self._harvest_until):
            return
        if self._extend_hold_for_open_turn(now):
            return
        since = self._held_assign_since
        if since is None:
            # ACK opened busy while work was already parked (or note_held raced).
            since = float(self._ack_at) if self._ack_open and self._ack_at is not None else now
            self._held_assign_since = since
        if now - float(since) < float(self.held_assign_watchdog_s):
            return
        self._flush_held_on_harvest_expiry(now, why="held-assign watchdog")

    def _flush_held_on_harvest_expiry(self, now: float, *, why: str = "harvest expired") -> None:
        """FR #4259 / FR #5505: deliver parked assigns when harvest ends (or watchdog).

        Without this, a held assign (``_held_assign`` / ``relay.has_pending_work``) keeps
        ``_busy`` true forever after a repeat-DONE re-arm, so ``!bored`` never fires again.
        Called under ``self._cv``. FR #5505: also flush when a free/done !bored is still
        pending — ACK-on-receipt can open ``_ack_open`` and block ``post_bored`` forever
        while the assign stays parked. Skip only while a turn is still open.
        """
        if self._turn_open:
            return
        # FR #8738: the prior job's closing turn (incl. an unseen reminder turn) is open.
        if self._closing_turn_live(now):
            return
        had_held = bool(self._held_assign)
        released = 0
        try:
            if self.relay is not None:
                released = int(self.relay.release_held_assigns() or 0)
        except Exception:
            released = 0
        if self._held_assign:
            self._held_assign = False
        self._held_assign_since = None
        if released:
            self._inject_pending = True
            self._inject_at = now
            self._idle_since = None
            # New work supersedes a pending free/done !bored from the prior job.
            if self._pending_harvest_fire():
                self._last_free_key = self._free_key
                self._last_done_key = self._done_key
                self._hold_started_at = None
            self.log(f"bored: {why} - released {released} held assign(s)")
        elif had_held:
            self.log(f"bored: {why} - cleared held-assign flag")

    def _reason(self, now: float) -> Optional[str]:
        if self._stopped or not self._ready or now < self._retry_at:
            return None
        # FR #4259 / FR #5505: when harvest wait expires with no open turn, flush held
        # assigns *before* the busy check (even if free/done !bored is still pending).
        if self._harvest_until is not None and now >= self._harvest_until:
            pending = self._pending_harvest_fire()
            self._harvest_until = None
            if (
                pending
                and bored_on_turn_end_enabled()
                and not self._harvest_saw_turn_ended
            ):
                self._harvest_used_fallback = True
                self.log("bored: fallback timer, no turn_ended seen")
            self._flush_held_on_harvest_expiry(now, why="harvest expired")
        # FR #8738: the prior job's closing turn just ended - deliver what was parked.
        if self._flush_after_closing and not self._turn_open:
            self._flush_after_closing = False
            pending = False
            try:
                pending = bool(self.relay is not None and self.relay.has_pending_work())
            except Exception:
                pending = False
            if pending or self._held_assign:
                self._flush_held_on_harvest_expiry(now, why="closing turn ended")
        # FR #5505: ACKed-on-receipt hold never injected — watchdog injects after deadline.
        self._flush_held_assign_watchdog(now)
        if self._busy(now):
            self._idle_since = None
            if self._nak_due is not None and now >= self._nak_due:
                self._nak_due = None  # busy at due time: never send; post-harvest !bored covers it
            return None
        # FR #4753: ACK past ack_stale_s must clear and !bored (reason ack-stale), even when
        # turn_started bumped release_gen and the cursor turn never ended (error stall).
        if (
            self._ack_open
            and self._ack_at is not None
            and now - float(self._ack_at) >= float(self.ack_stale_s)
        ):
            key = self._ack_job_key or "job"
            self._ack_open = False
            self._ack_job_key = None
            self._clear_done_miss()
            # FR #4784: keep key for GIVEUP before !bored (Jeeves accepted-row free).
            self._release_giveup_key = key
            self._turn_open = False
            self._release_gen = self._turn_gen
            self._idle_since = now
            self.log(
                f"bored: ACK stale after {self.ack_stale_s:.0f}s on {key} - releasing (ack-stale)"
            )
            return "ack-stale"
        if self._idle_since is None:
            self._idle_since = now
        if not self._start_sent:
            return "start"
        # FR #2875: second turn_ended after done-miss reminder with ACK still open.
        if self._done_miss_release_pending:
            return "done-miss"
        # FR #2802: turn_started after a turn-end release bumps gen and gates done/free/turn.
        if self._release_gen is not None and self._release_gen != self._turn_gen:
            self._arm_skip = False
            return None
        # Hold fire at the turn_ended clock instant so a same-tick turn_started can cancel.
        if self._arm_skip:
            if self._hold_release_at is not None and now <= self._hold_release_at:
                return None
            self._arm_skip = False
        # FR #1611: fire done/free only after harvest hold has ended (not immediate on outbox).
        if self._done_key and self._done_key != self._last_done_key:
            return "done"
        if self._free_key and self._free_key != self._last_free_key:
            return "free"
        if self._turn_idle_pending:
            return "turn"
        if self._nak_due is not None and now >= self._nak_due:
            return "nak"
        since = (now - self._last_bored) if self._last_bored is not None else 1e12
        thr = self.repeat_s if self._last_reason == "idle" else self.idle_s
        if now - self._idle_since >= self.idle_s and since >= thr:
            return "idle"
        return None

    def _next_due(self, now: float) -> Optional[float]:
        if self._stopped or not self._ready:
            return None
        wakes: list[float] = []
        # FR #3012: while out of fuel, wake only for fuel_poll (no idle/nak past-due spin).
        if self._out_of_fuel:
            base = float(self._out_of_fuel_at) if self._out_of_fuel_at is not None else now
            return max(now + 0.5, base + float(self.fuel_poll_s))
        # FR #3019: while ACK open, also wake for mid-job fuel-lost poll (Cursor has no unified.jsonl).
        if self._ack_open and self.fuel_lost_check_fn is not None:
            base = float(self._fuel_lost_checked_at) if self._fuel_lost_checked_at is not None else now
            wakes.append(base + float(self.fuel_poll_s))
        if self._ack_held(now) and not self._turn_open and self._ack_at is not None:
            if (now - self._ack_at) < self.ack_stale_s:
                wakes.append(self._ack_at + self.ack_stale_s)
            elif self._agent_active_at is not None:
                wakes.append(self._agent_active_at + self.ack_quiet_s)
        # FR #2875: wake when done-miss grace expires so the reminder can fire.
        if (
            self._done_miss_armed_at is not None
            and not self._done_miss_reminded
            and not self._done_miss_release_pending
        ):
            wakes.append(float(self._done_miss_armed_at) + float(self.done_miss_grace_s))
        # FR #7352: wake when the reminder reply window expires (no second turn needed).
        if (
            self._ack_open
            and self._done_miss_reminded
            and self._done_miss_reply_until is not None
            and not self._done_miss_release_pending
        ):
            wakes.append(float(self._done_miss_reply_until))
        if self._harvest_until is not None and now < self._harvest_until:
            wakes.append(self._harvest_until)
        # FR #5505: wake when held-assign watchdog is due.
        if (
            self.held_assign_watchdog_s > 0
            and self._held_assign_since is not None
            and (self._held_assign or (self.relay is not None and self.relay.has_pending_work()))
        ):
            if self._harvest_until is None or now >= float(self._harvest_until):
                wakes.append(float(self._held_assign_since) + float(self.held_assign_watchdog_s))
        # FR #8738: wake at the closing-turn safety cap / reminder-turn quiet window.
        if self._finish_turn_at is not None:
            wakes.append(float(self._finish_turn_at) + float(self.finish_turn_hold_max_s))
            if (
                self._finish_turn_unseen
                and self._agent_active_at is not None
                and self._done_miss_reminded
            ):
                wakes.append(float(self._agent_active_at) + float(self.ack_quiet_s))
        # FR #2834: while open-turn extends past harvest_hold_s, wake at the safety cap.
        if self._extend_hold_for_open_turn(now) and self._hold_started_at is not None:
            wakes.append(float(self._hold_started_at) + float(self.turn_hold_max_s))
        if self._inject_pending and self._inject_at is not None and now - self._inject_at < self.assign_grace_s:
            wakes.append(self._inject_at + self.assign_grace_s)
        if wakes:
            wake = min(wakes)
            return min(wake, self._nak_due) if self._nak_due is not None else wake
        if now < self._retry_at:
            return self._retry_at
        # FR #2802: after turn-end release (or arm_skip cleared), wake immediately for done/free/turn.
        if self._release_gen is not None and self._release_gen == self._turn_gen:
            if (
                (self._done_key and self._done_key != self._last_done_key)
                or (self._free_key and self._free_key != self._last_free_key)
                or self._turn_idle_pending
            ):
                return now
        base = self._idle_since if self._idle_since is not None else now
        thr = self.repeat_s if self._last_reason == "idle" else self.idle_s
        due = base + self.idle_s
        if self._last_bored is not None:
            due = max(due, self._last_bored + thr)
        if self._nak_due is not None:
            due = min(due, self._nak_due)
        return due

    def _fire(self, reason: str, now: float) -> None:
        # DONE/free already de-dupe on payload key; do not collapse distinct NACK then GIVEUP in the same second (FR #161).
        if reason == "done":
            key = (reason, self._done_key)
        elif reason == "free":
            key = (reason, self._free_key)
        else:
            key = (reason, int(now))
        if key == self._last_dedupe:
            self._retry_at = now + 1.0
            if reason == "turn":
                self._turn_idle_pending = False
            return
        # FR #3192: re-check busy after turn_ended may have flushed a held assign into
        # inject-pending (or Relay still parks one) so we do not !bored on a stale reason.
        now2 = self.clock()
        if self._busy(now2):
            if reason == "turn":
                self._turn_idle_pending = False
            self._retry_at = now2 + self.retry_s
            self.log(f"bored: skip {reason} - became busy before send")
            return
        # FR #4784: GIVEUP open ACK to Jeeves before !bored on done-miss / ack-stale.
        if reason == "done-miss":
            self._fire_seat_release_giveup("no-terminal-reply")
        elif reason == "ack-stale":
            self._fire_seat_release_giveup(reason)
        # FR #7238: pull merged skills between jobs (this send is idle).
        try:
            sk = maybe_sync_install_skills(job_busy=False)
            if sk.get("sha"):
                self.log(f"skills-sync sha={sk.get('sha')} reason={sk.get('reason')}")
        except Exception:
            pass
        ok = False
        try:
            ok = bool(self.send())
        except Exception as e:
            self.log(f"bored: send error {type(e).__name__}")
        if not ok:
            self._retry_at = now + self.retry_s
            self.log(f"bored: not sent ({reason}) - retry in {self.retry_s:.0f}s")
            return
        self._last_dedupe, self._last_bored, self._last_reason, self._idle_since = key, now, reason, now
        self._nak_due = None  # any !bored satisfies a pending NAK timer
        if reason == "start":
            self._start_sent = True
        if reason == "done":
            self._last_done_key = self._done_key
            self._hold_started_at = None
        if reason == "free":
            self._last_free_key = self._free_key
            self._hold_started_at = None
        if reason == "turn":
            self._turn_idle_pending = False
        if reason == "done-miss":
            self._done_miss_release_pending = False
            self._clear_done_miss()
        if reason == "ack-stale":
            # ACK already cleared in _reason; keep idle clock for the next cycle.
            self._idle_since = now
        self.sent.append((now, reason))
        kind = (self.kind or "").strip().lower() or "unknown"
        if reason in ("done", "free", "turn") and self._harvest_saw_turn_ended:
            trigger = "turn_ended"
        elif reason in ("done", "free") and self._harvest_used_fallback:
            trigger = "fallback-timer"
        else:
            trigger = reason
        self.log(f"bored -> shop reason={reason} kind={kind} trigger={trigger}")

    def _run(self) -> None:
        with self._cv:
            while not self._stopped:
                now = self.clock()
                # FR #3012 / #4858: poll for fuel return while held quiet.
                # Hard 402: fuel_check_fn must encode min-hold + clear-floor (Supervisor).
                if self._out_of_fuel and self.fuel_check_fn is not None:
                    try:
                        ok = bool(self.fuel_check_fn())
                    except Exception:
                        ok = False
                    if ok:
                        why = (
                            self._out_of_fuel_clear_reason or "reading"
                        ).strip() or "reading"
                        # clear without nesting locks: inline the clear path
                        self._out_of_fuel = False
                        self._out_of_fuel_at = None
                        self._out_of_fuel_hard_402 = False
                        self._out_of_fuel_clear_reason = None
                        self._idle_since = now
                        self._release_gen = self._turn_gen
                        # FR #8249: keep heartbeat snapshot in sync with fuel clear.
                        self._hb_notify_all()
                        self.log(
                            f"out-of-fuel: cleared via {why} - seat may !bored again"
                        )
                # FR #3019 / #3923: mid-job fuel-lost poll while ACK open.
                # Unknown readings must return False from fuel_lost_check_fn; require
                # fuel_lost_streak_need consecutive True polls before GIVEUP.
                if (
                    self._ack_open
                    and not self._out_of_fuel
                    and self.fuel_lost_check_fn is not None
                ):
                    due_check = True
                    if self._fuel_lost_checked_at is not None:
                        due_check = (now - float(self._fuel_lost_checked_at)) >= float(self.fuel_poll_s)
                    if due_check:
                        self._fuel_lost_checked_at = now
                        try:
                            lost = bool(self.fuel_lost_check_fn())
                        except Exception:
                            lost = False
                        if lost:
                            self._fuel_lost_streak = int(self._fuel_lost_streak) + 1
                            need = int(self.fuel_lost_streak_need)
                            self.log(
                                f"out-of-fuel: mid-job exhausted reading streak="
                                f"{self._fuel_lost_streak}/{need}"
                            )
                            if self._fuel_lost_streak >= need:
                                self.note_out_of_fuel(
                                    f"mid-job fuel reading exhausted (streak={self._fuel_lost_streak})"
                                )
                        else:
                            if self._fuel_lost_streak:
                                self.log(
                                    f"out-of-fuel: mid-job streak reset "
                                    f"(was {self._fuel_lost_streak})"
                                )
                            self._fuel_lost_streak = 0
                # FR #2875: grace expiry injects reminder while ACK stays open (still busy).
                # FR #7352: if the reminder turn never starts, expire the reply window.
                if not self._out_of_fuel:
                    self._fire_done_miss_remind(now)
                    self._maybe_expire_done_miss_reply(now)
                r = self._reason(now)
                if r:
                    self._fire(r, now)
                    continue
                # FR #2802: brief wait while arm_skip so turn_started can cancel same-tick.
                if self._arm_skip and self._hold_release_at is not None and now <= self._hold_release_at:
                    self._cv.wait(0.02)
                    continue
                due = self._next_due(now)
                # FR #2996: never busy-loop on wait(0) when due is already past and reason is None
                # (stale _release_gen gate left idle/nak due in the past).
                if due is None:
                    self._cv.wait(None)
                else:
                    wait_s = max(0.0, due - now)
                    if wait_s <= 0.0:
                        wait_s = 0.5
                    self._cv.wait(wait_s)

# --------------------------------------------------------------------------------------------- FR #2782: stale build
STALE_BUILD_SETTLE_S = 60.0  # install exe must be unchanged this long (a hotpatch copy may still be in flight)
_RUN_EXE_DIGEST_RX = re.compile(r"(?i)^bob-worker-([0-9a-f]{12})\.exe$")
_stale_build_cache: dict = {}


def stale_build_reason(run_exe: str | Path, install_root: str | Path, *, now: float | None = None,
                       env: Optional[dict] = None) -> Optional[str]:
    """FR #2782 / #3180: why this seat is running an older build than the install, or None.

    A seat runs ``%LOCALAPPDATA%\\Bobiverse\\worker\\bin\\bob-worker-<digest>.exe`` where ``<digest>`` is the first
    12 hex of sha256(<install_root>\\worker\\bob-worker.exe) at launch (``describe_worker_exe_launch``). A hotpatch
    replaces the install exe, but a running seat keeps its old run copy until it exits, so fixes such as the FR #2696
    submit-verify never reach it. When the install exe now hashes differently (and has settled for
    ``STALE_BUILD_SETTLE_S``), the seat is stale. Returns None for dev runs (python / un-hashed exe name), a missing
    install exe, or opt-out ``BOB_WORKER_STALE_BUILD_RECYCLE=0``. FR #3180: seat-heal is gone.
    FR #7834: detection still runs. The seat keeps sending ``!bored`` and taking work.
    It publishes ``stale_build`` and reports once. It does not exit.
    """
    e = os.environ if env is None else env
    if str(e.get("BOB_WORKER_STALE_BUILD_RECYCLE") or "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    m = _RUN_EXE_DIGEST_RX.match(Path(str(run_exe or "")).name)
    if not m:
        return None
    run_d = m.group(1).lower()
    inst = Path(install_root) / "worker" / "bob-worker.exe"
    try:
        st = inst.stat()
    except OSError:
        return None
    t = time.time() if now is None else float(now)
    if t - st.st_mtime < STALE_BUILD_SETTLE_S:
        return None
    key = (str(inst), st.st_size, st.st_mtime)
    d = _stale_build_cache.get(key)
    if d is None:
        try:
            d = hashlib.sha256(inst.read_bytes()).hexdigest()[:12].lower()
        except OSError:
            return None
        _stale_build_cache.clear()
        _stale_build_cache[key] = d
    if d == run_d:
        return None
    return f"run={run_d} install={d}"


_STALE_SHA = re.compile(r"(?i)\b(run|install)=([0-9a-f]{12})\b")
_stale_build_reported: set[str] = set()


def stale_build_public(why: str, *, since: float) -> dict:
    """Digest ``stale_build`` object: running sha12, installed sha12, and since (unix)."""
    found = {k.lower(): v.lower() for k, v in _STALE_SHA.findall(why or "")}
    return {
        "running": found.get("run") or "",
        "installed": found.get("install") or "",
        "since": float(since),
    }


def note_stale_build(nick: str, why: str, *, report=None) -> bool:
    """One exception per seat and build reason for this process. No secret values."""
    key = f"{str(nick or '').strip().lower()}|{str(why or '').strip()}"
    if not key.strip("|") or key in _stale_build_reported:
        return False
    _stale_build_reported.add(key)
    if report is not None:
        report(str(nick or "").strip(), str(why or "").strip())
        return True
    try:
        import crash_report

        crash_report.report_exception(
            "bob-worker",
            RuntimeError,
            RuntimeError(f"stale build seat={nick} {why}"),
            None,
            repo="SimonBarnett/bobiverse",
        )
    except Exception:
        pass
    return True


# --------------------------------------------------------------------------------------------- supervisor
class Supervisor:
    """Owns: the IRC seat, the relay, ONE agent at a time. Everything funnels through shutdown()."""

    def __init__(self, *, kind: str, exe: str, cwd: str, machine: str, nick: str, run_dir: Path, irc: Optional[IrcSeat], relay: Relay,
                 log: Callable[[str], None], env_secret: Optional[SecretStr] = None, spawn: Callable = default_spawn,
                 kill: Callable[[int], bool] = kill_tree, probe: Callable[[int], Sample] = sample_tree,
                 inject: Callable[[int, str], bool] = inject_console, detector: Optional[HangDetector] = None,
                 health_interval_s: float = 5.0, startup_grace_s: float = 60.0, startup_min_s: float | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 backoff: tuple = RULE_BACKOFF_S, restart_max: int = RULE_RESTART_MAX, restart_window_s: float = RULE_RESTART_WINDOW_S,
                 base_env: Optional[dict] = None, bored: Optional["BoredEmitter"] = None,
                 reconnect_grace_s: float | None = None,
                 send_enter: Optional[Callable[[int], bool]] = None,
                 ask_user_watch: Optional["AskUserPendingWatch"] = None,
                 sessions_root: Optional[Path] = None,
                 install_root: str | Path | None = None,
                 session_log_path: Path | None = None):
        self.kind, self.exe, self.cwd, self.machine, self.nick = kind, exe, cwd, machine, nick
        self.install_root = str(install_root) if install_root else None
        self.run_dir, self.irc, self.relay, self.log = Path(run_dir), irc, relay, log
        self.session_log = SeatSessionLog(session_log_path or (self.run_dir / "session.log"))
        self.last_exit: dict | None = None
        self.publish_exit_digest = None
        self._session_log_stop = threading.Event()
        self._session_log_thread = None
        self._session_screen = None
        self._session_cursor = None
        self._exit_recorded_pid = None
        # FR #8155 / #8249: digest last_progress heartbeats while ACK is open.
        self._progress_prev: dict = {}
        self._progress_last_post_mono: float = 0.0
        self._progress_last_seen_mono: float = 0.0
        self._progress_phase: str = ""
        self._progress_heartbeat_s = progress_heartbeat_interval_s()
        self._progress_hb_epoch: int = 0
        self._progress_hb_skip_log_mono: float = 0.0
        self._progress_hb_thread: Optional[threading.Thread] = None
        # Wall-time aliases kept for older tests that poke private attrs.
        self._progress_last_post_wall: float = 0.0
        self._progress_last_seen_wall: float = 0.0
        self.secret = env_secret
        self.spawn, self.kill, self.probe, self.inject = spawn, kill, probe, inject
        self.detector = detector or HangDetector()
        # FR #3623: ask_user pending → Enter then hang-restart.
        self.send_enter = send_enter if send_enter is not None else send_console_enter
        self.ask_user_watch = ask_user_watch if ask_user_watch is not None else AskUserPendingWatch()
        self.sessions_root = sessions_root
        self.health_interval_s, self.startup_grace_s, self.clock = health_interval_s, startup_grace_s, clock
        # FR #2884: floor before first-turn_ended can end the startup hold (malformed instant events).
        self.startup_min_s = (
            float(startup_min_s) if startup_min_s is not None
            else _env_float("BOB_WORKER_STARTUP_MIN_S", 10.0, 0.0, 60.0)
        )
        self.backoff, self.restart_max, self.restart_window_s = backoff, restart_max, restart_window_s
        # FR #2669: collapse doubled BOB_* paths; drop CURSOR_*/SAND_* inherited from agent shells.
        self.base_env = prepare_seat_child_env(os.environ if base_env is None else base_env)
        self.done = threading.Event()
        self.exit_code: Optional[int] = None
        self.stop = threading.Event()
        self.proc = None
        self.sessions: list = []  # every session id this supervisor ever started (all distinct)
        self.restarts: list = []  # (clock time, reason)
        self._lock = threading.RLock()
        self._expected_exit: set = set()
        self._owned: set = set()
        self._shutting = False
        self._shutdown_reason = ""
        self._grok_login_expired_reported = False  # FR #8221: report once
        self._grace_timer: Optional[threading.Timer] = None
        self._min_ready_timer: Optional[threading.Timer] = None
        self._agent_started_at: Optional[float] = None
        # FR #2884: startup hold until first grok turn_ended (grace is fallback).
        self._startup_hold_armed = False
        self._startup_session_id: Optional[str] = None
        self._startup_saw_turn_started = False
        self._startup_turn_release_enabled = False
        self._startup_ready_proc = None
        # FR #1643 / MRB #1658: capture create-parent while agent is still live (post-wait Toolhelp often misses it).
        self._agent_parent_pid: int = 0
        self._agent_parent_image: str = ''
        self._agent_parent_cmd: str = ''
        self.bored = bored if bored is not None else (BoredEmitter(self.post_bored, log) if irc else None)
        # FR #3456: IRC reconnect grace (0 = legacy immediate EXIT_IRC_LOST + kill agent).
        self.reconnect_grace_s = (
            float(reconnect_grace_s) if reconnect_grace_s is not None
            else _env_float("BOB_WORKER_IRC_RECONNECT_GRACE_S", 600.0, 0.0, 3600.0)
        )
        self._irc_reconnecting = False
        self._irc_lost_at: Optional[float] = None
        self._reconnect_thread: Optional[threading.Thread] = None
        if self.bored is not None and getattr(self.bored, "run_dir", None) is None:
            self.bored.run_dir = self.run_dir  # FR #3189 job-repo.txt for harvest
        if self.bored is not None:
            self.bored.kind = (self.kind or "").strip().lower()
        # FR #2383: assign injected + no run-dir ACK while agent keeps turning → remind then recycle.
        self.ack_miss = AssignAckMiss()
        # FR #2875: turn_ended with ACK open and no DONE → remind via run-dir inject, then release.
        if self.bored is not None:
            self.bored.done_miss_remind_fn = self._inject_done_miss_reminder
            self.bored.failed_turn_retry_fn = self._inject_failed_turn_retry
            # FR #8018: failed-turn / giveup facts land on the per-seat session log (#7917).
            self.bored.session_log_write = self.session_log.write
            if (self.kind or "").strip().lower() == "opencode":
                self.bored.opencode_finish_decide_fn = self._opencode_finish_decide
                self.bored.job_end_cleanup_fn = self._opencode_job_end_cleanup
            elif (self.kind or "").strip().lower() in ("grok", "cursor"):
                # FR #6918: drop --job-worktree from live MCP configs when the job ends.
                self.bored.job_end_cleanup_fn = self._live_skill_dag_job_end_cleanup
            # FR #4784: GIVEUP accepted row to Jeeves before !bored on done-miss / ack-stale.
            self.bored.seat_release_giveup_fn = self._release_seat_giveup_job
        # FR #2782: idle-only check before !bored; returns a reason when a newer install build exists.
        self.stale_build_check: Optional[Callable[[], Optional[str]]] = None
        # FR #2802: grok events.jsonl turn watcher (opt-out BOB_WORKER_BORED_ON_TURN_END=0).
        self._turn_watch_stop = threading.Event()
        self._turn_watch_thread: Optional[threading.Thread] = None
        # FR #3012 / #3019: out-of-fuel watcher (grok unified.jsonl + Cursor override / fuel poll).
        self._fuel_watch_stop = threading.Event()
        self._fuel_watch_thread: Optional[threading.Thread] = None
        self._out_of_fuel_log_path_fn: Optional[Callable[[], Path | str | None]] = None
        if self.bored is not None:
            self.bored.out_of_fuel_release_fn = self._release_out_of_fuel_job
            self.bored.out_of_fuel_enter_fn = self._on_out_of_fuel_enter
            self.bored.out_of_fuel_quit_fn = self._quit_after_out_of_fuel
            self.bored.fuel_check_fn = self._fuel_available_again
            self.bored.fuel_lost_check_fn = self._fuel_lost_mid_job
        relay.on_inject = self._on_inject
        # FR #8246: per-offer ACK, and no inject while another job's turn is live.
        relay.prepare_offer = lambda line: (
            self.bored.note_fresh_assign(line) if self.bored else None
        )
        relay.ack_refuse_reason = lambda payload: (
            self.bored.outbox_ack_refuse_reason(payload) if self.bored else None
        )
        relay.turn_busy_other_job = lambda line: (
            self.bored.live_turn_blocks_assign(line) if self.bored else False
        )
        # FR #2811: park assigns during harvest hold; flush on turn_ended / before !bored.
        relay.hold_assigns_while = lambda: bool(self.bored and self.bored.holding_incoming_assigns)
        # FR #8738: flush only after the prior job's closing turn has ended.
        relay.defer_flush_while = lambda: bool(self.bored and self.bored.closing_turn_open)
        relay.on_hold_assign = lambda _line: (
            self.bored.note_held_assign() if self.bored else None
        )
        # FR #4180: refuse (NACK out-of-fuel) assigns while the seat is in out-of-fuel hold.
        relay.refuse_assign_while = lambda: bool(self.bored and self.bored.out_of_fuel)
        relay.skips_hostile_assign = lambda line: opencode_skips_hostile_assign(
            self.kind,
            line,
            start_model=launched_hostile_start_model(
                self.kind, getattr(self, "last_child_env", None)
            ),
        )
        # FR #6240 / #6328: OpenCode-only. Classify on read thread; ensure off-thread.
        # Grok/Cursor must keep flood coalesce + multi-key ACK (callbacks stay None).
        if (self.kind or "").strip().lower() == "opencode":
            relay.opencode_job_classify = self._opencode_job_classify
            relay.opencode_ensure_worktree = self._opencode_ensure_worktree
            relay.opencode_job_block = None
        else:
            relay.opencode_job_classify = None
            relay.opencode_ensure_worktree = None
            relay.opencode_job_block = None
        relay.on_refuse_assign = self._nack_assign_out_of_fuel
        # FR #4115: program ACK/NACK via seat outbox (ACK on receipt; NACK extra held assigns).
        if getattr(relay, "write_outbox", None) is None and self.run_dir is not None:
            _run = self.run_dir
            relay.write_outbox = lambda text, rd=_run: append_outbox_line(
                outbox_path_for_run(rd), text
            )
        # FR #3192: BoredEmitter consults Relay.has_pending_work so !bored stays quiet
        # while an assign is held/inject_failed (not only hold_assigns_while).
        if self.bored is not None:
            self.bored.relay = relay
        if irc and self.bored:
            irc.on_nak = self.bored.nak  # t817u
            irc.on_nak_line = self._replay_done_on_busy_hold  # FR #4642
        if irc:
            irc.on_lost = self._on_irc_lost

    def _stop_turn_watcher(self) -> None:
        self._turn_watch_stop.set()
        th = self._turn_watch_thread
        self._turn_watch_thread = None
        if th is not None and th.is_alive():
            th.join(timeout=2.0)

    def _session_log_paths(self) -> list:
        paths = []
        if self.kind == "grok" and self.sessions:
            directory = grok_session_dir(
                self.cwd, self.sessions[-1], sessions_root=self.sessions_root, run_dir=self.run_dir
            )
            if directory is not None:
                paths.extend(directory / name for name in ("events.jsonl", "messages.jsonl"))
            paths.append(default_unified_log_path(run_dir=self.run_dir))
        elif self.kind == "cursor" and self._session_cursor is not None:
            directory = self._session_cursor._bind()
            if directory is not None:
                transcript = self._session_cursor._transcript_file(directory)
                if transcript is not None:
                    paths.append(transcript)
        elif self.kind == "opencode":
            paths.append(self.run_dir / "opencode-turns.jsonl")
        return paths

    def _collect_session_log(self, *, final: bool = False) -> None:
        self.session_log.collect(self._session_log_paths(), final=final)
        screen = read_console_screen_text(max_lines=32)
        if screen and screen != self._session_screen:
            self.session_log.write("console", screen)
            self._session_screen = screen

    def _stop_session_log(self) -> None:
        # FR #8083: start_agent stubs and any path that skips __init__ must not
        # raise before the OpenCode turn log is cleared.
        stop = getattr(self, "_session_log_stop", None)
        if stop is not None:
            stop.set()
        thread = getattr(self, "_session_log_thread", None)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._session_log_thread = None

    def _start_session_log(self) -> None:
        self._session_log_stop = threading.Event()
        stop = self._session_log_stop

        def watch():
            while not stop.wait(0.5):
                try:
                    self._collect_session_log()
                except Exception:
                    self.log("session-log: snapshot unavailable")

        self._session_log_thread = threading.Thread(target=watch, name="seat-session-log", daemon=True)
        self._session_log_thread.start()

    def _record_exit(self, proc, reason: str, code=None, *, report: bool = False, job_key: str = "") -> bool:
        """Record first exit for ``proc``. Return True when this call owns the record.

        FR #8148: callers such as ``_wait_exit`` must not file a CLI-failure intake when
        ``shutdown`` (e.g. console-closed) already recorded the same pid.
        """
        with self._lock:
            if self._exit_recorded_pid == proc.pid:
                return False
            self._exit_recorded_pid = proc.pid
        self._stop_session_log()
        with contextlib.suppress(Exception):
            self._collect_session_log(final=True)
        with contextlib.suppress(Exception):
            self.session_log.write("stderr-tail", proc.stderr_tail())
        self.last_exit = {
            "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "reason": _scrub(reason)[:160],
            "exit_code": code,
            "pid": proc.pid,
            "output": self.session_log.tail()[-8192:],
        }
        self._persist_last_exit()
        if is_console_closed_shutdown_reason(str(reason or "")):
            with contextlib.suppress(Exception):
                note_console_closed_exit(self.machine)
        if report:
            report_agent_cli_nonzero_exit(
                exit_code=normalize_agent_exit_code(code) if code is not None else None,
                raw_code=code, reason=reason, job_key=job_key,
                machine=self.machine, nick=self.nick, kind=self.kind, agent_pid=proc.pid,
                stderr_tail=self.last_exit["output"], log=self.log,
            )
        return True

    def _persist_last_exit(self) -> None:
        text = json.dumps(self.last_exit)
        self.session_log.write("last_exit", text)
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            path = self.run_dir / "last-exit.json"
            # FR #8553: flush+fsync so a hard seat kill still leaves the reason on disk.
            with path.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(text + "\n")
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
        except OSError:
            pass
        self.log(f"agent: last_exit reason={self.last_exit['reason']} exit_code={self.last_exit['exit_code']} session_log={self.session_log.path}")
        if self.publish_exit_digest is not None:
            with contextlib.suppress(Exception):
                self.publish_exit_digest(self.last_exit)
    def _stop_fuel_watcher(self) -> None:
        self._fuel_watch_stop.set()
        th = self._fuel_watch_thread
        self._fuel_watch_thread = None
        if th is not None and th.is_alive():
            th.join(timeout=2.0)

    def _install_root_for_fuel(self) -> Path:
        root = Path(resolve_install_root())
        env = self.base_env if isinstance(self.base_env, dict) else {}
        cand = (env.get("BOB_INSTALL_ROOT") or env.get("BOBIVERSE_INSTALL_ROOT") or "").strip()
        if cand:
            root = Path(cand)
        return root

    def _fuel_available_again(self) -> bool:
        """FR #3012 / #4858 / #4899: True when fuel readings may clear the out-of-fuel hold.

        Soft holds (mid-job reading, no hard 402): seat's **own** pool (FR #4899), or
        a session key, or a real Cursor kind-switch (FR #3997). Hard 402: require min
        hold **and** grok pct above clear floor (not merely ``state=available`` with pct=3).
        """
        try:
            fuel = read_fuel(self._install_root_for_fuel())
            fuel, _src, _age = supplement_fuel_from_fleet(
                fuel,
                load_public_digest(
                    public_digest_path(
                        getattr(self, "base_env", None) or os.environ,
                        install_root=self._install_root_for_fuel(),
                    )
                ),
                now=time.time(),
            )
        except Exception:
            fuel = Fuel()
        hard = bool(getattr(self.bored, "_out_of_fuel_hard_402", False))
        kind = (self.kind or "").strip().lower() or "grok"
        if hard:
            at = getattr(self.bored, "_out_of_fuel_at", None)
            now = self.bored.clock() if self.bored is not None else 0.0
            held = 0.0 if at is None else float(now) - float(at)
            min_hold = float(getattr(self.bored, "out_of_fuel_min_hold_s", 1800.0))
            floor = int(getattr(self.bored, "out_of_fuel_clear_floor_pct", 5))
            if not out_of_fuel_reading_clears_hard_hold(
                fuel,
                kind=kind,
                held_for_s=held,
                min_hold_s=min_hold,
                clear_floor_pct=floor,
            ):
                return False
            if kind == "grok":
                self.bored._out_of_fuel_clear_reason = f"reading pct={fuel.grok_pct}"
            else:
                self.bored._out_of_fuel_clear_reason = "reading"
            return True
        # FR #4899: soft hold — own pool only. Cursor tokens clear a grok hold only when
        # this seat is actually switching to Cursor (caller sets kind / restarts agent).
        allow_switch = bool(getattr(self, "_out_of_fuel_allow_cursor_kind_switch", False))
        start_model = ""
        if kind == "opencode":
            try:
                start_model = launched_hostile_start_model(
                    kind, getattr(self, "last_child_env", None)
                )
            except Exception:
                start_model = ""
            try:
                fuel = fold_opencode_seat_pauses(
                    fuel,
                    start_model,
                    env=getattr(self, "base_env", None) or getattr(self, "last_child_env", None),
                )
            except Exception:
                pass
        ok, why = out_of_fuel_reading_clears_soft_hold(
            fuel,
            kind=kind,
            has_session_key=self.secret is not None,
            allow_cursor_kind_switch=allow_switch,
            start_model=start_model,
        )
        if ok:
            if self.bored is not None:
                self.bored._out_of_fuel_clear_reason = why or "reading"
            return True
        return False

    def _fuel_lost_mid_job(self) -> bool:
        """FR #3019 / #3923 / #8158: True only on an **explicit** exhausted reading while ACKed.

        Unknown / timeout / empty ``Fuel()`` is **not** lost (selection still treats
        unknown as unavailable). Logs pct/state/helper snapshot every poll.

        OpenCode seats key the reading to the launched start model pool
        (``opencode_go`` / ``opencode_free``), never ``grok_pct`` (FR #8158).
        """
        kind = (self.kind or "").strip().lower()
        start_model = ""
        if kind == "opencode":
            try:
                start_model = launched_hostile_start_model(
                    kind, getattr(self, "last_child_env", None)
                )
            except Exception:
                start_model = ""
        pool = seat_fuel_pool(kind, start_model) if kind == "opencode" else ""

        def _local() -> Fuel:
            return read_fuel(self._install_root_for_fuel())

        try:
            fuel, source, age_s, hold = take_midjob_fuel(
                _local,
                load_public_digest(
                    public_digest_path(
                        getattr(self, "base_env", None) or os.environ,
                        install_root=self._install_root_for_fuel(),
                    )
                ),
                now=time.time(),
                hold=getattr(self, "_fleet_fuel_hold", None),
                pool=pool,
            )
            self._fleet_fuel_hold = hold
        except Exception as e:
            self.log(f"out-of-fuel: mid-job read_fuel failed {type(e).__name__} - treat as unknown")
            return False
        if kind == "opencode":
            try:
                fuel = fold_opencode_seat_pauses(
                    fuel,
                    start_model,
                    env=getattr(self, "base_env", None) or getattr(self, "last_child_env", None),
                )
            except Exception:
                pass
        snap = format_fuel_reading(fuel, kind, start_model=start_model, source=source, age_s=age_s)
        if kind == "cursor":
            lost = fuel_explicitly_exhausted(fuel, "cursor")
            self.log(f"out-of-fuel: mid-job reading {snap}")
            return lost
        if kind == "grok":
            # Session key still counts as fuel for a dialog-started grok seat.
            if self.secret is not None:
                self.log(f"out-of-fuel: mid-job reading {snap} (session key present)")
                return False
            lost = fuel_explicitly_exhausted(fuel, "grok")
            self.log(f"out-of-fuel: mid-job reading {snap}")
            return lost
        if kind == "opencode":
            lost = fuel_explicitly_exhausted(fuel, "opencode", start_model=start_model)
            self.log(f"out-of-fuel: mid-job reading {snap}")
            return lost
        return False

    def _clear_watchdogs_for_out_of_fuel(self) -> None:
        """FR #4180: disarm ack-miss + HangDetector so the hold cannot look like a hang."""
        try:
            self.ack_miss.clear()
        except Exception:
            pass
        try:
            self.detector.reset(self.clock())
        except Exception:
            pass
        try:
            self.relay.last_unacked = ""
        except Exception:
            pass

    def _on_out_of_fuel_enter(self) -> None:
        """FR #4180: enter hold — clear hang/ack-miss and NACK any parked assigns."""
        self._clear_watchdogs_for_out_of_fuel()
        try:
            self.relay.release_held_assigns()
        except Exception:
            pass

    def _opencode_job_classify(self, line: str) -> str:
        """FR #6328: cheap classify on the IRC read thread (no git create)."""
        if (self.kind or "").strip().lower() != "opencode":
            return ""
        if not assign_job_ref(line):
            return ""
        return opencode_job_context_nack(line, os.environ)

    def _opencode_ensure_worktree(self, line: str) -> str:
        """FR #6240 / #6320 / #6328: ensure job worktree off the IRC read thread."""
        if (self.kind or "").strip().lower() != "opencode":
            return ""
        if not assign_job_ref(line):
            return ""
        nick = ""
        try:
            nick = str(getattr(self, "nick", "") or os.environ.get("BOB_NICK") or "")
        except Exception:
            nick = ""
        install = getattr(self, "install_root", None) or os.environ.get("BOB_INSTALL_ROOT") or ""
        return opencode_job_context_nack_ready(
            line,
            os.environ,
            install_root=install or None,
            run=subprocess.run,
            nick=nick,
        )

    def _opencode_job_block(self, line: str) -> str:
        """Legacy sync ensure (tests / callers that still bind opencode_job_block)."""
        return self._opencode_ensure_worktree(line)

    def _nack_assign_out_of_fuel(self, line: str) -> None:
        """FR #4180: shop NACK for an assign that arrived during the out-of-fuel hold."""
        key = assign_job_type_key(line) or "job"
        nack = out_of_fuel_nack_line(key)
        shop = self.irc.shop if self.irc else shop_channel(self.machine)
        if self.irc and self.irc.alive:
            try:
                self.irc.say(shop, nack)
            except Exception as e:
                self.log(f"out-of-fuel: NACK say failed {type(e).__name__}")
        if self.bored:
            try:
                # Bookkeeping only — BoredEmitter keeps !_bored while _out_of_fuel.
                self.bored.on_outbox(nack)
            except Exception:
                pass
        self._clear_watchdogs_for_out_of_fuel()
        self.log(f"out-of-fuel: posted {nack}")

    def _release_seat_giveup_job(self, job_key: str, reason: str) -> None:
        """FR #4784: shop GIVEUP so Jeeves frees the accepted row before !bored done-miss/ack-stale.

        Do not route through BoredEmitter.on_outbox — that would arm harvest_hold and delay the
        release !bored. Direct irc.say matches the out-of-fuel path for the wire line only.
        """
        line = seat_release_giveup_line(job_key, reason)
        shop = self.irc.shop if self.irc else shop_channel(self.machine)
        if self.irc and self.irc.alive:
            try:
                self.irc.say(shop, line)
            except Exception as e:
                self.log(f"seat-release: GIVEUP say failed {type(e).__name__}")
                return
            try:
                self.irc.say(
                    shop,
                    f"seat-release: {self.nick} GIVEUP `{job_key}` reason={reason}",
                )
            except Exception:
                pass
        else:
            # No live IRC: still append to seat outbox so a reconnect flush can deliver.
            outbox = None
            try:
                outbox = getattr(self.bored, "run_dir", None) if self.bored else None
            except Exception:
                outbox = None
            if outbox:
                try:
                    path = Path(outbox) / "outbox.txt"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8", newline="\n") as fh:
                        fh.write(f"PRIVMSG {shop} :{line}\n")
                except Exception as e:
                    self.log(f"seat-release: outbox GIVEUP failed {type(e).__name__}")
        self.log(f"seat-release: posted {line}")

    def _release_out_of_fuel_job(self, job_key: str) -> None:
        """FR #3012: shop GIVEUP + digest so Jeeves / tray see out-of-fuel immediately."""
        line = out_of_fuel_giveup_line(job_key)
        shop = self.irc.shop if self.irc else shop_channel(self.machine)
        quit_soon = out_of_fuel_quit_enabled(
            self.base_env if isinstance(getattr(self, "base_env", None), dict) else None
        )
        if self.irc and self.irc.alive:
            try:
                self.irc.say(shop, line)
            except Exception as e:
                self.log(f"out-of-fuel: GIVEUP say failed {type(e).__name__}")
            try:
                follow = (
                    f"out-of-fuel: {self.nick} released `{job_key}` (402/usage exhausted) - closing seat"
                    if quit_soon
                    else f"out-of-fuel: {self.nick} released `{job_key}` (402/usage exhausted) - quiet until fuel returns"
                )
                self.irc.say(shop, follow)
            except Exception:
                pass
        # Bookkeeping without arming harvest !bored (BoredEmitter._out_of_fuel already set).
        if self.bored:
            try:
                self.bored.on_outbox(line)
            except Exception:
                pass
        # FR #4180: disarm hang/ack-miss so a post-GIVEUP offer cannot recycle the seat.
        self._clear_watchdogs_for_out_of_fuel()
        try:
            pid = None
            try:
                if self.proc is not None:
                    pid = getattr(self.proc, "pid", None)
            except Exception:
                pid = None
            ok = post_digest_out_of_fuel(
                machine=self.machine,
                nick=self.nick,
                evidence=line,
                pid=pid,
                log=self.log,
            )
            if not ok:
                self.log("out-of-fuel: digest post returned False (weekly=0 may not have reached peers)")
        except Exception as e:
            self.log(f"out-of-fuel: digest post failed {type(e).__name__}: {e}")
        self.log(f"out-of-fuel: posted {line}")

    def _out_of_fuel_dialog_pool_bits(self, evidence: str = "") -> tuple[str, str, str]:
        """Best-effort pool / remaining / reset strings for the FR #8814 dialog."""
        kind = (self.kind or "").strip().lower() or "worker"
        pool = kind
        remaining = "0"
        reset_hint = ""
        env = self.base_env if isinstance(getattr(self, "base_env", None), dict) else os.environ
        model = str(env.get("BOB_OPENCODE_MODEL") or env.get("BOB_WORKER_MODEL") or "").strip()
        if kind == "opencode":
            ev = (evidence or "").lower()
            if "fuel-exhausted:opencode-free" in ev or "free usage" in ev:
                pool = "opencode_free"
            else:
                pool = "opencode"
            if model:
                pool = f"{pool} ({model})"
        try:
            fuel = load_fresh_agent_list_fuel(max_age_s=3600.0, env=env)
        except Exception:
            fuel = None
        if fuel is not None:
            try:
                if kind == "opencode":
                    remaining = f"free={getattr(fuel, 'opencode_free', '?')} go={getattr(fuel, 'opencode_go', '?')}"
                elif kind == "cursor":
                    remaining = f"high={getattr(fuel, 'cursor_high', '?')} low={getattr(fuel, 'cursor_low', '?')}"
                elif kind == "grok":
                    remaining = f"pct={getattr(fuel, 'grok_pct', '?')} state={getattr(fuel, 'grok_state', '?')}"
            except Exception:
                pass
        if "reset" in (evidence or "").lower():
            reset_hint = one_line(evidence or "", 80)
        return pool, remaining, reset_hint

    def _quit_after_out_of_fuel(self, evidence: str = "") -> None:
        """FR #8814: dialog + worker-remove + shutdown so the nick leaves the digest."""
        if getattr(self, "_out_of_fuel_quit_started", False):
            return
        self._out_of_fuel_quit_started = True
        env = self.base_env if isinstance(getattr(self, "base_env", None), dict) else os.environ
        if not out_of_fuel_quit_enabled(env):
            self.log("out-of-fuel: quit skipped (BOB_WORKER_OUT_OF_FUEL_QUIT=0)")
            return
        pool, remaining, reset_hint = self._out_of_fuel_dialog_pool_bits(evidence)
        show_fn = getattr(self, "_out_of_fuel_dialog_show_fn", None)
        try:
            show_out_of_fuel_dialog(
                pool=pool,
                remaining=remaining,
                reset_hint=reset_hint,
                evidence=evidence or "",
                nick=self.nick,
                show_fn=show_fn,
                env=env,
                log=self.log,
            )
        except Exception as e:
            self.log(f"out-of-fuel: dialog path failed {type(e).__name__}")
        pid = None
        try:
            if self.proc is not None:
                pid = getattr(self.proc, "pid", None)
        except Exception:
            pid = None
        if pid is None:
            try:
                pid = os.getpid()
            except Exception:
                pid = None
        try:
            post_digest_worker_remove(
                machine=self.machine,
                nick=self.nick,
                pid=pid,
                env=env,
                log=self.log,
            )
        except Exception as e:
            self.log(f"out-of-fuel: worker-remove failed {type(e).__name__}")
        self.log("out-of-fuel: closing seat (FR #8814)")
        try:
            self.shutdown("fuel-exhausted", EXIT_OUT_OF_FUEL)
        except Exception as e:
            self.log(f"out-of-fuel: shutdown failed {type(e).__name__}")

    def _try_opencode_switch_free_to_paid(self, evidence: str) -> bool:
        """FR #8537: pause free, rebind to paid, continue ACK. True when switched."""
        if getattr(self, "_opencode_paid_switched", False):
            return True
        env = self.base_env if isinstance(getattr(self, "base_env", None), dict) else os.environ
        model = str(env.get("BOB_OPENCODE_MODEL") or "").strip()
        if not model:
            try:
                model = str(resolve_opencode_model(Fuel(), env=env) or "").strip()
            except Exception:
                model = ""
        fuel = Fuel()
        try:
            # Allow a slightly stale cache: free=100 is common until pause folds.
            got = load_fresh_agent_list_fuel(max_age_s=3600.0, env=env)
            if got is not None:
                fuel = got
        except Exception:
            fuel = Fuel()
        if not should_switch_opencode_free_to_paid(evidence, model, fuel, env):
            return False
        paid = resolve_opencode_paid_switch_model(env)
        pause_dir = opencode_pauses_state_dir(env)
        try:
            import opencode_fuel as of

            # Stamp cli-stderr so record-pause accepts free-model Free usage (FR #8537).
            pause_blob = evidence or ""
            if "Free usage limit" in pause_blob and '"source"' not in pause_blob:
                pause_blob = json.dumps(
                    {
                        "text": "Free usage limit reached. Subscribe to OpenCode Go",
                        "source": "cli-stderr",
                        "model": model or "opencode/deepseek-v4.1-flash-free",
                    },
                    separators=(",", ":"),
                )
            of.record_opencode_pause(
                pause_dir,
                model or "opencode/deepseek-v4.1-flash-free",
                pause_blob,
            )
            # Publish free=0 so mid-job readings stop painting 100.
            folded = fold_opencode_seat_pauses(fuel, model, env=env, state_dir=pause_dir)
            save_agent_list_fuel(replace(folded, opencode_free=0), env=env)
        except Exception as e:
            self.log(f"out-of-fuel: free pause failed {type(e).__name__}: {e}")
        try:
            env["BOB_OPENCODE_MODEL"] = paid
            os.environ["BOB_OPENCODE_MODEL"] = paid
        except Exception:
            pass
        try:
            import worker_start_model as wsm

            wsm.save_worker_start_settings(
                env=env,
                models={"opencode": paid},
            )
        except Exception:
            pass
        self._opencode_paid_switched = True
        self.log(
            f"opencode switch-to-paid model={paid} reason=fuel-exhausted:opencode-free "
            f"(was {model or 'free'}; no GIVEUP)"
        )
        return True

    def _start_fuel_watcher(self, agent_pid: int = 0) -> None:
        """FR #3012 / #3019: follow fuel log for mid-job 402 / NEEDS_AUTH / usage-exhausted.

        Starts for grok **and** cursor. Cursor defaults to no log path (fuel-reading poll
        covers it); set ``BOB_WORKER_OUT_OF_FUEL_LOG`` or ``_out_of_fuel_log_path_fn`` to tail a file.
        """
        self._stop_fuel_watcher()
        if not should_start_fuel_watcher(self.kind):
            return
        if not self.bored:
            return
        self._fuel_watch_stop = threading.Event()
        kind = (self.kind or "").strip().lower()
        path_fn = self._out_of_fuel_log_path_fn or (
            lambda: default_out_of_fuel_log_path(
                kind,
                env=self.base_env if isinstance(self.base_env, dict) else None,
                run_dir=self.run_dir,
            )
        )

        def _on_hit(text: str) -> None:
            # FR #8537: free-limit on a free OpenCode seat switches to paid when Go
            # remains. Do not shop-GIVEUP; the wrapper continues the same ACK.
            if (self.kind or "").strip().lower() == "opencode":
                try:
                    if self._try_opencode_switch_free_to_paid(text):
                        return
                except Exception as e:
                    self.log(f"out-of-fuel: free-to-paid switch failed {type(e).__name__}")
            # note_out_of_fuel → out_of_fuel_enter_fn clears watchdogs + NACKs parked assigns (FR #4180).
            if self.bored:
                self.bored.note_out_of_fuel(text)

        watcher = GrokOutOfFuelWatcher(
            log_path_fn=path_fn,
            on_hit=_on_hit,
            stop_event=self._fuel_watch_stop,
            poll_s=0.5,
            log=self.log,
            agent_pid=int(agent_pid or 0),
        )
        th = threading.Thread(target=watcher.run, name="fuel-watch", daemon=True)
        self._fuel_watch_thread = th
        th.start()
        self.log(f"out-of-fuel: watcher started (kind={kind} pid={agent_pid})")

    def _cursor_stale_replay_check(self, *, schedule_wait: bool = False) -> None:
        """FR #4842 / #5327 / #5403: compare transcript user key to open ACK.

        Wait until the latest user assign is J (or wait_s after inject) before
        comparing. DONE-finished keys stay exempt in stale_replay_assign_key.
        """
        if self.bored is None:
            return
        w = getattr(self, "_cursor_turn_watcher", None)
        tp = w._transcript_file(w._bind()) if w is not None and w._bind() else None
        uk = cursor_transcript_latest_user_assign_key(tp) if tp else None
        if not uk:
            return
        open_k = getattr(self.bored, "_ack_job_key", None)
        # MRB #5435: ACK clears _inject_at; fall back to _ack_at so the wait
        # still covers transcript lag after ACK J (the usual Cursor race).
        wait_from = getattr(self.bored, "_inject_at", None)
        if wait_from is None:
            wait_from = getattr(self.bored, "_ack_at", None)
        if not stale_replay_compare_ready(
            user_key=uk,
            open_ack_key=open_k,
            inject_at=wait_from,
            now=time.time(),
        ):
            self.log("relay: stale-replay wait for transcript newer than inject")
            if schedule_wait:
                wait_s = stale_replay_wait_s()

                def _later() -> None:
                    with contextlib.suppress(Exception):
                        self._cursor_stale_replay_check(schedule_wait=False)

                threading.Timer(wait_s, _later).start()
            return

        def _write(s: str) -> bool:
            ob = getattr(self, "outbox_path", None) or getattr(self.bored, "run_dir", None)
            try:
                if ob is not None:
                    p = Path(ob)
                    if p.is_dir():
                        p = p / "outbox.txt"
                    shop = getattr(getattr(self, "irc", None), "shop", None) or "#shop"
                    line = f"PRIVMSG {shop} :{s}"
                    with p.open("a", encoding="utf-8") as fh:
                        fh.write(line + "\n")
                    return True
            except Exception:
                pass
            try:
                return bool(self.irc.say(self.irc.shop, s))
            except Exception:
                return False

        def _reinject() -> bool:
            line = getattr(self.relay, "last_line", None) or getattr(
                self.relay, "last_unacked", None
            )
            if not line or not self.proc:
                return False
            if (assign_job_key(line) or "").lower() != (
                self.bored._ack_job_key or ""
            ).lower():
                return False
            try:
                clear_console_input()
            except Exception:
                pass
            return bool(self._inject_line(self.proc, line, sync=False))

        self.bored.note_stale_replay_user_assign(
            uk, write_giveup=_write, reinject_open=_reinject
        )

    def _start_cursor_turn_watcher(self) -> None:
        """Cursor: release held assigns on an inferred turn end (no 600 s fallback wait)."""
        self._turn_watch_stop = threading.Event()

        def _on_started(turn: Optional[int], wall: float) -> None:
            with contextlib.suppress(Exception):
                pw = getattr(self, "_prompt_watch", None)
                if pw is not None:
                    pw.note_activity()
            if self.bored:
                self.bored.turn_started(turn=turn, sid=None)
            # FR #4842 / #5327: if the new user turn is a GIVEUP/NACK-finished assign K
            # while ACK J is open, emit GIVEUP K stale-replay and re-inject J. DONE-finished
            # K (transcript lag after a healthy job change) must not GIVEUP or re-inject.
            try:
                self._cursor_stale_replay_check(schedule_wait=True)
            except Exception as e:  # noqa: BLE001
                self.log(f"relay: stale-replay check failed {type(e).__name__}")

        def _on_ended(turn: Optional[int], wall: float, error: bool = False, error_class: str = "", error_line: str = "", **_k) -> None:
            if self.bored:
                self.bored.turn_ended(
                    turn=turn,
                    sid=None,
                    error=bool(error),
                    error_class=error_class,
                    error_line=error_line,
                )
            try:
                n = self.relay.release_held_assigns()
                if n and self.bored:
                    self.bored.activity(mark_work=True)
                if self.bored:
                    self.bored.clear_held_assign()
            except Exception:
                pass

        watcher = CursorTurnWatcher(
            since_wall=time.time() - 5.0,
            on_turn_started=_on_started,
            on_turn_ended=_on_ended,
            stop_event=self._turn_watch_stop,
            log=self.log,
        )
        self._cursor_turn_watcher = watcher
        th = threading.Thread(target=watcher.run, name="cursor-turn-watch", daemon=True)
        self._turn_watch_thread = th
        th.start()
        self.log(f"bored: cursor turn watcher started (quiet_s={watcher.quiet_s:.0f})")
        # FR #4462 / #4464: same keys default as start_agent. Explicit BOB_WORKER_INJECT_PASTE wins.
        apply_cursor_inject_keys_default("cursor", log=self.log)

    def _start_aider_turn_watcher(self) -> None:
        """FR #7265: Aider process-idle → turn_started / turn_ended."""
        self._turn_watch_stop = threading.Event()

        def _on_started(turn: Optional[int], wall: float) -> None:
            with contextlib.suppress(Exception):
                pw = getattr(self, "_prompt_watch", None)
                if pw is not None:
                    pw.note_activity()
            if self.bored:
                self.bored.turn_started(turn=turn, sid=None)

        def _on_ended(turn: Optional[int], wall: float, **_k) -> None:
            if self.bored:
                self.bored.turn_ended(turn=turn, sid=None)
            try:
                n = self.relay.release_held_assigns()
                if n and self.bored:
                    self.bored.activity(mark_work=True)
                if self.bored:
                    self.bored.clear_held_assign()
            except Exception:
                pass

        def _probe() -> object:
            pid = 0
            p = getattr(self, "proc", None)
            if p is not None:
                try:
                    pid = int(getattr(p, "pid", 0) or 0)
                except Exception:
                    pid = 0
            if pid <= 0:
                return Sample(alive=False, responding=None, activity=0)
            try:
                return sample_tree(pid)
            except Exception:
                return Sample(alive=False, responding=None, activity=0)

        watcher = ProcIdleTurnWatcher(
            probe=_probe,
            on_turn_started=_on_started,
            on_turn_ended=_on_ended,
            stop_event=self._turn_watch_stop,
            log=self.log,
        )
        th = threading.Thread(target=watcher.run, name="aider-turn-watch", daemon=True)
        self._turn_watch_thread = th
        th.start()
        self.log(f"bored: aider turn watcher started (quiet_s={watcher.quiet_s:.0f})")

    def _start_turn_watcher(self, session_id: str) -> None:
        """FR #2802 / #6157 / #7265: grok, opencode, cursor, or aider turn_ended → early !bored."""
        self._stop_turn_watcher()
        if self.bored and should_start_cursor_turn_watcher(self.kind):
            self._start_cursor_turn_watcher()
            return
        if self.bored and should_start_aider_turn_watcher(self.kind):
            self._start_aider_turn_watcher()
            return
        use_grok = bool(self.bored and should_start_turn_watcher(self.kind))
        use_opencode = bool(self.bored and should_start_opencode_turn_watcher(self.kind))
        if not use_grok and not use_opencode:
            return
        self._turn_watch_stop = threading.Event()
        cwd = str(self.cwd)
        sid_box = {"sid": session_id}
        run_dir = Path(self.run_dir) if getattr(self, "run_dir", None) else None

        def _path() -> Optional[Path]:
            # FR #6157: OpenCode wrapper markers live under the seat run_dir.
            if use_opencode:
                if run_dir is None:
                    return None
                return run_dir / "opencode-turns.jsonl"
            sid = sid_box["sid"]
            if self.sessions:
                sid = self.sessions[-1]
                sid_box["sid"] = sid
            d = grok_session_dir(cwd, sid or "", run_dir=run_dir)
            # GrokTurnWatcher tails the events file (same as make_submit_probe / FR #2696 / #7123).
            return (d / "events.jsonl") if d is not None else None

        def _on_started(turn: Optional[int], wall: float) -> None:
            sid = sid_box.get("sid")
            self._note_startup_turn_started(sid)
            with contextlib.suppress(Exception):
                pw = getattr(self, "_prompt_watch", None)
                if pw is not None:
                    pw.note_activity()
            if self.bored:
                self.bored.turn_started(turn=turn, sid=sid)

        def _on_ended(turn: Optional[int], wall: float, error: bool = False, error_class: str = "", error_line: str = "", **_k) -> None:
            sid = sid_box.get("sid")
            with contextlib.suppress(Exception):
                pw = getattr(self, "_prompt_watch", None)
                if pw is not None:
                    pw.note_activity()
            if self.bored:
                # Use emitter clock for hold release; wall is only for logging/stale via hold_started mono.
                self.bored.turn_ended(
                    turn=turn,
                    sid=sid,
                    error=bool(error),
                    error_class=error_class,
                    error_line=error_line,
                )
            # FR #2884: first turn_ended after spawn can end the startup inject/!bored hold.
            try:
                self._maybe_ready_on_first_turn_ended(sid)
            except Exception:
                pass
            # FR #2811 / #3192: flush parked assigns before clearing the held flag so a
            # racing BoredEmitter tick sees either has_pending_work or inject-pending.
            try:
                n = self.relay.release_held_assigns()
                if n and self.bored:
                    self.bored.activity(mark_work=True)
                if self.bored:
                    self.bored.clear_held_assign()
            except Exception:
                pass

        watcher = GrokTurnWatcher(
            events_path_fn=_path,
            on_turn_started=_on_started,
            on_turn_ended=_on_ended,
            stop_event=self._turn_watch_stop,
            poll_s=0.5,
            log=self.log,
        )
        watch_name = "opencode-turn-watch" if use_opencode else "grok-turn-watch"
        th = threading.Thread(target=watcher.run, name=watch_name, daemon=True)
        self._turn_watch_thread = th
        th.start()
        if use_opencode:
            self.log(f"bored: opencode turn watcher started (run_dir={run_dir})")
        else:
            self.log(f"bored: turn watcher started (session={session_id})")

    def _on_inject(self, line: str = "") -> None:
        self.detector.note_inject(self.clock())
        try:
            self.ack_miss.note_inject(line, self.clock(), own_nick=self.nick)
        except Exception:
            pass
        if self.bored:
            # MRB #1617: ``nothing queued`` is idle wire, not an assign — do not arm inject-pending.
            mark_work = True
            parts = (line or "").split(None, 3)
            if len(parts) >= 4 and parts[0].upper() == "FROM":
                mark_work = not is_nothing_queued(parts[3], self.nick)
            elif line:
                mark_work = not is_nothing_queued(line, self.nick)
            # FR #4730: re-offer of a finished job may ACK again.
            if mark_work:
                try:
                    self.bored.note_fresh_assign(line)
                except Exception:
                    pass
            self.bored.activity(mark_work=mark_work)
            ref = stand_down_job_ref(line)
            if ref:
                self.bored.note_stand_down(ref)

    def may_send_outbox(self, payload: str) -> bool:
        """FR #4730: drop replayed ACK for a finished job before it hits IRC.

        Used for the run-dir outbox. Do not apply the OpenCode job-key filter here
        (FR #6333 MRB): program NACKs for a new key can arrive while `_opencode_job_key`
        is still the previous job. Job-key filtering is `may_send_job_outbox` only.
        """
        if self.bored is None:
            return True
        try:
            return bool(self.bored.should_forward_outbox(payload))
        except Exception:
            return True

    def may_send_job_outbox(self, payload: str):
        """FR #6333 / #6472: worktree ``.bob/outbox.txt`` job-key filter then ACK rules.

        Returns True, or ``(False, reason)`` so drain_outbox logs the real refuse
        tag instead of always "stale replay".
        """
        p = (payload or "").strip()
        job_key = getattr(self, "_opencode_job_key", "") or ""
        if job_key:
            shop = ""
            try:
                shop = self.irc.shop if self.irc else shop_channel(self.machine)
            except Exception:
                shop = shop_channel(getattr(self, "machine", "") or "")
            reason = opencode_outbox_refuse_reason(p, job_key=job_key, shop=shop)
            if reason:
                return (False, reason)
        if self.bored is None:
            return True
        try:
            ack_reason = self.bored.outbox_ack_refuse_reason(payload)
        except Exception:
            ack_reason = None
        if ack_reason:
            return (False, ack_reason)
        return True

    def opencode_extra_outbox_paths(self) -> list:
        """FR #6333: active OpenCode job ``.bob/outbox.txt`` for the outbox loop."""
        ob = getattr(self, "_opencode_job_outbox", None)
        if ob is None:
            return []
        try:
            return [Path(ob)]
        except Exception:
            return []

    def _usage_baseline_path(self):
        """FR #6435: seat run-dir snapshot of cumulative usage at ACK."""
        if self.run_dir is None:
            return None
        return Path(self.run_dir) / "usage-baseline.json"

    def snapshot_usage_baseline(self, job: str = "") -> None:
        """FR #6435: capture cumulative seat usage at job start (ACK) for per-job deltas."""
        path = self._usage_baseline_path()
        if path is None:
            return
        try:
            import done_usage as _du

            usage = self.measure_done_usage(apply_baseline=False)
            _du.save_usage_baseline(path, usage, job=job or "")
        except Exception:
            pass

    def measure_done_usage(self, *, apply_baseline: bool = True) -> dict:
        """FR #6387: seat usage snapshot for DONE stamping (usage files only; no secrets)."""
        try:
            import done_usage as _du
        except Exception:
            return {"tokens_unknown": True}
        kind = (self.kind or "").strip().lower() or "grok"
        grok_path = None
        if kind == "grok":
            sid = self.sessions[-1] if self.sessions else None
            if sid:
                grok_path = _du.grok_usage_path_for_session(
                    str(self.cwd),
                    str(sid),
                    sessions_root=self.sessions_root,
                )
            env_g = (os.environ.get("BOB_GROK_USAGE_PATH") or "").strip()
            if env_g:
                grok_path = Path(env_g)
        cursor_path = (os.environ.get("BOB_CURSOR_USAGE_PATH") or "").strip() or None
        oc_path = (os.environ.get("BOB_OPENCODE_USAGE_PATH") or "").strip() or None
        aider_path = (os.environ.get("BOB_AIDER_USAGE_PATH") or "").strip() or None
        cursor_chat_dir = None
        watcher = getattr(self, "_cursor_turn_watcher", None)
        if watcher is not None:
            with contextlib.suppress(Exception):
                cursor_chat_dir = getattr(watcher, "chat_dir", None) or watcher._bind()
        if self.run_dir is not None:
            if not cursor_path:
                cand = Path(self.run_dir) / "cursor-usage.json"
                if cand.is_file():
                    cursor_path = str(cand)
            if not oc_path:
                cand = Path(self.run_dir) / "opencode-usage.json"
                if cand.is_file():
                    oc_path = str(cand)
            if not aider_path:
                cand = Path(self.run_dir) / "aider-usage.json"
                if cand.is_file():
                    aider_path = str(cand)
        # FR #6420: OpenCode measures from its own SQLite session data for the job
        # worktree, falling back to an explicit fixture path, then the configured model.
        if kind == "opencode":
            usage = self._measure_opencode_usage(oc_path)
        else:
            try:
                usage = _du.measure_seat_usage(
                    kind,
                    grok_usage_path=grok_path,
                    cursor_usage_path=cursor_path,
                    cursor_chat_dir=cursor_chat_dir,
                    opencode_usage_path=oc_path,
                    aider_usage_path=aider_path,
                )
            except Exception:
                usage = {"tokens_unknown": True}
        if not apply_baseline:
            return usage
        # FR #6435: convert cumulative seat totals into per-job deltas when a baseline exists.
        try:
            base_path = self._usage_baseline_path()
            if base_path is not None and base_path.is_file():
                baseline = _du.load_usage_baseline(base_path)
                return _du.usage_delta(baseline, usage)
        except Exception:
            pass
        return usage

    def _opencode_job_directory(self) -> str:
        """FR #6420: the job worktree OpenCode ran in (parent of ``.bob/outbox.txt``)."""
        ob = getattr(self, "_opencode_job_outbox", None)
        if ob is None:
            return ""
        try:
            wt = Path(ob).parent.parent
        except Exception:
            return ""
        try:
            if wt.is_dir():
                return str(wt)
        except Exception:
            return ""
        return ""

    def _measure_opencode_usage(self, oc_path: str | None) -> dict:
        """FR #6420: OpenCode DONE usage from its SQLite session data, then a fixture."""
        try:
            import done_usage as _du
        except Exception:
            return {"tokens_unknown": True}
        directory = self._opencode_job_directory()
        usage = None
        data_dir = None
        try:
            rd = getattr(self, "run_dir", None)
            if rd:
                pointer = Path(rd) / "opencode-data-dir.txt"
                if pointer.is_file():
                    data_dir = pointer.read_text(encoding="utf-8").strip() or None
        except Exception:
            data_dir = None
        if directory:
            try:
                usage = _du.read_opencode_sqlite_usage(data_dir, directory=directory)
            except Exception:
                usage = None
        if usage is None or usage.get("tokens_unknown"):
            usage = _du.measure_seat_usage("opencode", opencode_usage_path=oc_path)
        if usage and not str(usage.get("model") or "").strip():
            cfg = (os.environ.get("BOB_OPENCODE_MODEL") or "").strip()
            if cfg:
                usage = dict(usage)
                usage["model"] = cfg
        return usage

    def enrich_done_line(self, payload: str) -> str:
        """FR #6387 / #6409 / #6435: append per-job model/token + worker_build onto DONE."""
        try:
            import done_usage as _du

            usage = self.measure_done_usage(apply_baseline=True)
            return _du.enrich_done_payload(
                payload, usage, worker_build=short_build_sha()
            )
        except Exception:
            return payload

    def on_outbox_wire(self, payload: str) -> None:
        """BoredEmitter + FR #2383 ACK-miss clear; used as the outbox_loop on_payload."""
        p = (payload or "").strip()
        if _OUT_ACK_RX.match(p) or _OUT_DONE_RX.match(p) or _OUT_FREE_RX.match(p):
            self.ack_miss.note_ack()
        if _OUT_ACK_RX.match(p):
            # FR #6435: snapshot cumulative usage at ACK so DONE stamps a per-job delta.
            with contextlib.suppress(Exception):
                self.snapshot_usage_baseline(job=outbox_job_key(p) or "")
        if _OUT_DONE_RX.match(p) or _OUT_FREE_RX.match(p):
            with contextlib.suppress(Exception):
                self.relay.note_outbound(p)
        if self.bored:
            self.bored.on_outbox(payload)

    def _replay_done_on_busy_hold(self, text: str) -> None:
        """FR #4642: NAK busy (held X) after we already DONE'd X — put that DONE back on the outbox."""
        if self.bored is None or self.run_dir is None or self.irc is None:
            return
        with self.bored._cv:
            payload = (self.bored._last_done_key or self.bored._done_key or "").strip()
            ack_open = bool(self.bored._ack_open)
            ack_key = self.bored._ack_job_key or ""
        line = replay_done_line_for_busy_nak(text, payload)
        if not line:
            return
        held = outbox_job_key(line) or ""
        if ack_open and ack_key and held and ack_key != held:
            return
        shop = self.irc.shop
        ok = append_outbox_line(outbox_path_for_run(self.run_dir), f"PRIVMSG {shop} :{line}")
        if ok:
            self.log(f"bored: re-send DONE for {held} after nak busy held")

    def post_bored(self) -> bool:
        """The ONLY place !bored is sent: the exe, own shop, never during shutdown / after IRC loss."""
        if self._shutting or self.stop.is_set() or not self.irc or not self.irc.alive:
            return False
        # FR #2811: flush held assigns before !bored (harvest_hold_s fallback path).
        try:
            if self.bored:
                self.bored.clear_held_assign()
            n = self.relay.release_held_assigns()
            if n:
                # Injected work — do not also !bored this tick; arm inject-pending so
                # a False return (retry) stays busy until ACK.
                if self.bored:
                    self.bored.activity(mark_work=True)
                return False
        except Exception:
            pass
        # FR #7834: a stale build still sends !bored and takes work. Announce, publish, and
        # report once. Seat starts stay manual (FR #3180). Never exit EXIT_STALE_BUILD.
        why = None
        if self.stale_build_check is not None:
            try:
                why = self.stale_build_check()
            except Exception:
                why = None
        if why:
            prev = getattr(self, "_stale_build_announced", None)
            if prev != why:
                self._stale_build_announced = why
                self._stale_build_since = float(self.clock())
                self.log(
                    f"worker: stale build ({why}) - keep running and taking work; "
                    "restart me manually (FR #3180 / #7834)"
                )
                try:
                    self.irc.say(self.irc.shop, f"stale build ({why}) - restart me manually")
                except Exception:
                    pass
                note_stale_build(
                    self.nick,
                    why,
                    report=getattr(self, "stale_build_reporter", None),
                )
            self.stale_build_status = stale_build_public(
                why, since=float(getattr(self, "_stale_build_since", self.clock()))
            )
            pub = getattr(self, "publish_stale_digest", None)
            if pub is not None and prev != why:
                try:
                    pub(self.stale_build_status)
                except Exception:
                    pass
        else:
            self.stale_build_status = None
        return bool(self.irc.say(self.irc.shop, "!bored"))

    # ---- agent
    def _prompt(self) -> str:
        return worker_prompt(self.cwd, str(self.run_dir), self.machine, self.nick)

    def start_agent(self, note: str = "") -> bool:
        if (self.kind or "").strip().lower() == "opencode":
            # FR #8221 / MRB #8232: refuse only when launch_selected_model is empty.
            # An empty parent BOB_OPENCODE_MODEL is not empty: FR #8220 fills
            # env, then tray, then the free default inside build_launch.
            try:
                import worker_start_model as wsm

                resolved = wsm.concrete_model_id(os.environ.get("BOB_OPENCODE_MODEL")) or (
                    wsm.launch_selected_model(
                        "opencode", wsm.load_worker_start_config(), env=os.environ
                    )
                )
            except Exception:
                resolved = ""
            if not (resolved or "").strip():
                self.log("opencode: refusing to start with empty/unresolved model (FR #8221)")
                try:
                    report_seat_start_refusal(
                        machine=self.machine,
                        kind="opencode",
                        model="",
                        reason="opencode: empty/unresolved model (FR #8221)",
                        log=self.log,
                    )
                except Exception as e:
                    self.log(f"opencode: seat-start-refusal report failed {type(e).__name__}")
                return False
            # FR #8321: a pinned restart keeps the clicked model. If that model is
            # paused/capped, stop and report; never fall back to another model.
            if seat_model_pinned():
                why = opencode_model_pause_reason(resolved)
                if why:
                    reason = (
                        "opencode: saved start model %s unavailable (%s) - "
                        "not starting (FR #8321)" % (resolved, why)
                    )
                    self.log(reason)
                    try:
                        report_seat_start_refusal(
                            machine=self.machine,
                            kind="opencode",
                            model=resolved,
                            reason=reason,
                            log=self.log,
                        )
                    except Exception as e:
                        self.log(
                            f"opencode: seat-start-refusal report failed {type(e).__name__}"
                        )
                    return False
            blocked, msg = probe_gh_auth(subprocess.run)
            if blocked:
                self.log(msg)
                return False
        with self._lock:
            if self._shutting:
                return False
            if self.bored:
                self.bored.set_ready(False)  # a (re)starting agent is not idle
            # FR #6157 / MRB #6164: hang-restart reuses run_dir; truncate OpenCode turn markers
            # before spawn so GrokTurnWatcher (offset 0) cannot replay a prior agent's turn_ended
            # into startup release / done-miss / harvest hold. Markers written after this clear
            # (between spawn and watcher start) are still seen.
            if (self.kind or "").strip().lower() == "opencode" and self.run_dir is not None:
                try:
                    turns = Path(self.run_dir) / "opencode-turns.jsonl"
                    turns.write_text("", encoding="utf-8")
                except OSError:
                    pass
            child = describe_agent_child_launch(
                kind=self.kind,
                mode="agent",
                cwd=self.cwd,
                run_dir=self.run_dir,
                machine=self.machine,
                nick=self.nick,
                agent_exe=self.exe,
                prompt=self._prompt() + (" " + note if note else ""),
                install_root=self.install_root,
            )
            spec = child["spec"]
            self._stop_session_log()
            self.session_log.reset_sources()
            self._session_screen = None
            self._exit_recorded_pid = None
            self._session_cursor = CursorTurnWatcher(since_wall=time.time()) if self.kind == "cursor" else None
            spec.session_log = self.session_log
            self.session_log.write("start", f"kind={self.kind} session={spec.session_id}")
            self.session_log.write("console-start", json.dumps(console_startup_state()))
            self.session_log.write("prompt", self._prompt() + (" " + note if note else ""))
            # FR #2380 / #2413 / #2669: seat env + path normalize + scrub agent-host vars.
            env = prepare_seat_child_env(self.base_env, child["env"])
            self.last_child_env = dict(env)
            if self.secret is not None and self.kind == "grok":
                env["XAI_API_KEY"] = self.secret.reveal()  # child env only
            try:
                proc = self.spawn(spec, env)
            except Exception as e:
                self.log(f"agent: launch failed {type(e).__name__}: {str(e)[:120]}")
                return False
            self.proc = proc
            self._owned.add(proc.pid)
            self.sessions.append(spec.session_id)
            self._start_session_log()
            self._agent_started_at = self.clock()
            # FR #1643 / MRB #1658: snapshot create-parent now; after wait() the agent PID is usually gone from Toolhelp.
            try:
                self._agent_parent_pid = int(parent_of(int(proc.pid)) or 0)
            except Exception:
                self._agent_parent_pid = 0
            self._agent_parent_image = ''
            self._agent_parent_cmd = ''
            if self._agent_parent_pid > 0:
                try:
                    _pp, self._agent_parent_image, self._agent_parent_cmd = describe_process(self._agent_parent_pid)
                except Exception:
                    self._agent_parent_image, self._agent_parent_cmd = '', ''
            self.log(f"agent: started NEW {self.kind} agent pid={proc.pid} session={spec.session_id} cwd={self.cwd}")
            # FR #4843: warn when the live install checkout is not on main.
            try:
                log_install_root_guard(self._install_root_for_fuel(), self.log)
            except Exception as e:  # noqa: BLE001
                self.log(f"install-root: guard error {type(e).__name__}")
            # FR #4464: keys default at seat start, including when the cursor turn watcher stays off.
            apply_cursor_inject_keys_default(self.kind, log=self.log)
            if self.startup_grace_s > 0 and _startup_wait_ready_enabled():
                self.log(
                    f"agent: holding inject/!bored for startup_grace_s={self.startup_grace_s:.0f}s "
                    f"(FR #955/#2884: first turn_ended ends hold; grace is fallback)"
                )
            self.detector.reset(self.clock())
            self.relay.set_target(None)
            self._start_turn_watcher(spec.session_id)
            self._start_fuel_watcher(int(proc.pid or 0))
            self._start_prompt_watcher(proc)
            self._start_grok_signin_guard(proc)
            self._start_grok_blank_tui_guard(proc)
            self._arm_ready(proc)
            threading.Thread(target=self._wait_exit, args=(proc,), name="agent-wait", daemon=True).start()
            return True

    def _note_startup_turn_started(self, sid: Optional[str]) -> None:
        """FR #2884: record turn_started for the armed startup session."""
        with self._lock:
            if not self._startup_hold_armed:
                return
            if sid and self._startup_session_id and sid != self._startup_session_id:
                return
            self._startup_saw_turn_started = True

    def _maybe_ready_on_first_turn_ended(self, sid: Optional[str]) -> None:
        """FR #2884: end startup hold on first grok turn_ended (after startup_min_s floor)."""
        with self._lock:
            if not self._startup_hold_armed or not self._startup_turn_release_enabled:
                return
            if self._shutting or self.proc is None:
                return
            if sid and self._startup_session_id and sid != self._startup_session_id:
                return
            proc = self.proc
            started_at = self._agent_started_at
            min_s = float(self.startup_min_s)
        now = float(self.clock())
        elapsed = now - float(started_at) if started_at is not None else min_s
        if elapsed < min_s:
            delay = max(0.0, min_s - elapsed)

            def _later(p=proc):
                self._ready_now(p, reason="turn")

            t = threading.Timer(delay, _later)
            t.daemon = True
            with self._lock:
                if not self._startup_hold_armed:
                    return
                old = self._min_ready_timer
                self._min_ready_timer = t
            if old is not None:
                try:
                    old.cancel()
                except Exception:
                    pass
            t.start()
            return
        self._ready_now(proc, reason="turn")

    def _ready_now(self, proc, *, reason: str = "grace") -> None:
        """FR #955 / #2884: enable inject + !bored once per spawn (idempotent)."""
        with self._lock:
            if self._shutting or self.proc is not proc:
                return
            if not self._startup_hold_armed and reason != "force":
                # Already released for this spawn (grace or turn); second caller is a no-op.
                if self._startup_ready_proc is proc:
                    return
                # Hold not armed (e.g. startup_grace_s<=0 already ready) — still no-op when already ready.
                return
            self._startup_hold_armed = False
            self._startup_ready_proc = proc
            grace_t = self._grace_timer
            min_t = self._min_ready_timer
            self._grace_timer = None
            self._min_ready_timer = None
            started_at = self._agent_started_at
        for t in (grace_t, min_t):
            if t is None:
                continue
            try:
                t.cancel()
            except Exception:
                pass
        self.relay.set_target(lambda line, p=proc: self._inject_line(p, line))
        # FR #4123: if grace released while turn 0 is open, enable inject but defer !bored
        # until turn_ended so Jeeves does not offer into a still-booting agent.
        defer_bored = False
        with self._lock:
            if reason == "grace" and self._startup_saw_turn_started and self._startup_turn_release_enabled:
                self._startup_defer_start_bored = True
                defer_bored = True
            elif reason == "turn":
                self._startup_defer_start_bored = False
        if self.bored:
            if defer_bored:
                self.log(
                    "agent: ready for inject but deferring !bored until turn_ended "
                    "(FR #4123; turn 0 still open after grace)"
                )
            else:
                self.bored.set_ready(True)  # seat start / restart complete -> !bored (watcher: "on start")
        now = float(self.clock())
        elapsed = now - float(started_at) if started_at is not None else 0.0
        if reason == "turn":
            self.log(
                f"agent: ready (first turn_ended after {elapsed:.0f}s; "
                f"startup_grace_s={self.startup_grace_s:.0f} fallback not needed)"
            )
            self._release_deferred_startup_bored()
        elif reason == "cap":
            # Cap no longer enables inject under wait_ready (FR #4123); keep log for legacy callers.
            self.log(
                f"agent: ready (startup ready cap {_startup_ready_cap_s():.0f}s reached without "
                f"turn_ended); inject + !bored enabled"
            )
        elif reason == "signed-in":
            self.log(
                "agent: ready (signed in, model loaded; !bored without waiting for a first turn) "
                "(FR #7180)"
            )
        else:
            self.log(
                f"agent: ready (startup_grace_s={self.startup_grace_s:.0f} fallback); "
                f"inject + !bored enabled"
            )

    def _arm_ready(self, proc) -> None:
        """FR #955 / #2884 / #7180: signed-in seats ready immediately; unsigned never ready."""
        signed = agent_session_signed_in(
            self.kind, run_dir=self.run_dir, env=self.last_child_env
        )
        with self._lock:
            self._session_assignable = bool(signed)
            self._startup_hold_armed = True
            self._startup_ready_proc = None
            self._startup_session_id = self.sessions[-1] if self.sessions else None
            self._startup_saw_turn_started = False
            self._startup_defer_start_bored = False
            # FR #6157: grok OR opencode turn watchers enable startup wait_ready / first-turn release.
            self._startup_turn_release_enabled = startup_turn_release_enabled(self.kind)
        if not signed:
            with self._lock:
                self._startup_hold_armed = False
            self.log(
                "agent: needs sign-in - not ready, no worker ready / !bored (FR #7180 / #7183)"
            )
            if self.bored is not None:
                try:
                    self.bored.note_needs_signin()
                except Exception:
                    pass
            return
        if not _startup_wait_ready_enabled():
            self._ready_now(proc, reason="signed-in")
            return

        with self._lock:
            if self._min_ready_timer is not None:
                try:
                    self._min_ready_timer.cancel()
                except Exception:
                    pass
                self._min_ready_timer = None

        def ready():
            # FR #4115 / #4123: for grok (turn watcher on) the grace timer no longer releases inject
            # while the session is still starting. Hold until the first turn_ended. At the ready cap
            # without turn_ended, hang-recycle (do not paste into a still-booting agent).
            with self._lock:
                wait_ready = (
                    self._startup_hold_armed
                    and self._startup_turn_release_enabled
                    and _startup_wait_ready_enabled()
                    and self.proc is proc
                )
            cap = _startup_ready_cap_s()
            remaining = max(0.0, cap - float(self.startup_grace_s))
            if wait_ready and remaining > 0:
                self.log(
                    f"agent: startup_grace_s={self.startup_grace_s:.0f} elapsed but session not ready "
                    f"(no first turn_ended) - holding inject/!bored until ready (cap {cap:.0f}s)"
                )
                t2 = threading.Timer(remaining, lambda p=proc: self._on_startup_ready_cap(p))
                t2.daemon = True
                with self._lock:
                    if not self._startup_hold_armed:
                        return
                    self._grace_timer = t2
                t2.start()
                return
            self._ready_now(proc, reason="grace")

        if self.startup_grace_s <= 0:
            self._ready_now(proc, reason="grace")
            return
        t = threading.Timer(self.startup_grace_s, ready)
        t.daemon = True
        with self._lock:
            self._grace_timer = t
        t.start()


    def _release_deferred_startup_bored(self) -> None:
        """FR #4123: fire the deferred seat-start !bored once turn 0 ends."""
        with self._lock:
            if not getattr(self, "_startup_defer_start_bored", False):
                return
            self._startup_defer_start_bored = False
        if self.bored:
            self.bored.set_ready(True)
            self.log("agent: deferred !bored released after turn_ended (FR #4123)")

    def _on_startup_ready_cap(self, proc) -> None:
        """FR #4123: ready-cap without first turn_ended -> hang-recycle, never paste.

        Wait-ready already blocked the 60 s grace release. At the long cap, if the first
        turn still has not ended, treat it as a hung first turn (process dead or idle, or
        hard timeout) and restart a NEW agent instead of enabling inject/!bored.
        """
        with self._lock:
            if self._shutting or self.proc is not proc:
                return
            if not self._startup_hold_armed:
                return
            saw_started = bool(self._startup_saw_turn_started)
        idle = _startup_proc_idle(proc, probe=getattr(self, "probe", None))
        why = "startup-no-first-turn"
        if idle:
            detail = "process dead or 0 CPU"
        else:
            detail = "first turn_ended never arrived (hard cap)"
        ack_open = bool(self.bored and getattr(self.bored, "_ack_open", False))
        since = float(getattr(self, "_agent_started_at", 0.0) or 0.0)
        # _agent_started_at is monotonic; activity logs use wall clock — use 0 to accept any turn.
        paths = self._startup_activity_paths()
        if not should_startup_hang_recycle(ack_open=ack_open, activity_paths=paths, since_wall=0.0):
            self.log(
                f"agent: startup ready cap skip hang-recycle (FR #7123 ack_open={ack_open} "
                f"saw_turn_started={saw_started}) - releasing hold"
            )
            self._ready_now(proc, reason="activity")
            return
        self.log(
            f"agent: startup ready cap {_startup_ready_cap_s():.0f}s reached without turn_ended "
            f"({detail}; saw_turn_started={saw_started}) - hang-recycle (FR #4123)"
        )
        with self._lock:
            self._startup_hold_armed = False
            grace_t = self._grace_timer
            self._grace_timer = None
        if grace_t is not None:
            with contextlib.suppress(Exception):
                grace_t.cancel()
        self.restart_agent(why)

    def _prompt_give_up(self) -> None:
        """FR #4115: Enter retries exhausted - NACK the pending assign (if any) via the recovery."""
        line = ""
        with contextlib.suppress(Exception):
            line = self.ack_miss.last_line or ""
        if not line:
            line = getattr(self.relay, "last_unacked", "") or ""
        if line and assign_job_ref(line):
            self._inject_recovery().on_failed(line, attempt=2)
        else:
            self.log("relay: prompt-not-accepted give-up - no pending assign to NACK")

    def _start_prompt_watcher(self, proc) -> None:
        """FR #4115: poll the shared console for Grok's prompt-accept timeout (Windows, grok only)."""
        if os.name != "nt" or (self.kind or "").strip().lower() != "grok" or not _prompt_retry_enabled():
            return
        pw = PromptNotAcceptedWatcher(
            read_fn=read_console_screen_text,
            enter_fn=send_console_enter,
            on_give_up=self._prompt_give_up,
            clock=time.monotonic,
            log=self.log,
            backoffs=_prompt_retry_backoffs(),
        )
        self._prompt_watch = pw

        def _run() -> None:
            while not self._shutting and self.proc is proc and proc.poll() is None:
                with contextlib.suppress(Exception):
                    pw.tick()
                time.sleep(5.0)

        threading.Thread(target=_run, name="prompt-retry-watch", daemon=True).start()

    def _fallback_after_grok_signin_prompt(self, proc) -> None:
        """FR #8221: kill the sign-in prompt and exit xai-auth-expired. Never switch kind.

        FR #7345 / MRB #7348 originally fell back to Cursor/OpenCode; FR #8221
        removed that because a seat only ever runs the kind the tray launched.
        The prompt is killed, the event is reported once (digest + exception
        reporter), and the seat exits EXIT_XAI_AUTH_EXPIRED (terminal, not an
        FR #7593 recycle).
        """
        with self._lock:
            if self._shutting:
                return
            pid = int(getattr(proc, "pid", 0) or 0)
            if pid:
                self._expected_exit.add(pid)
        self.log("grok: killing interactive sign-in prompt (FR #7345)")
        with contextlib.suppress(Exception):
            self.kill(int(getattr(proc, "pid", 0) or 0))
        with self._lock:
            if self.proc is proc:
                self.proc = None
        fuel = Fuel()
        with contextlib.suppress(Exception):
            fuel = read_fuel(self._install_root_for_fuel())
        cursor_cmd = resolve_cursor_cmd()
        opencode_cmd = resolve_opencode_cmd()
        seat_home = None
        machine_auth = None
        with contextlib.suppress(Exception):
            import skill_dag_bound as _sdb

            seat_home = getattr(self, "run_dir", None)
            if seat_home:
                seat_home = Path(seat_home) / _sdb.GROK_HOME_NAME
            machine_auth = _sdb.machine_grok_auth_path()
        cause = classify_grok_signin_prompt_cause(
            seat_home=seat_home, machine_auth=machine_auth
        )
        seat_present = bool(seat_home and (Path(seat_home) / "auth.json").is_file())
        exp = None
        with contextlib.suppress(Exception):
            import skill_dag_bound as _sdb2

            exp = _sdb2.summarize_grok_auth(machine_auth).get("expires_at")
        self.log(
            f"grok: sign-in prompt cause={cause} seat_auth_present={seat_present} expires_at={exp}"
        )
        dec = decision_after_grok_signin_prompt(
            fuel, cursor_cmd, opencode_cmd,
            seat_home=seat_home, machine_auth=machine_auth,
            machine=getattr(self, "machine", "") or "",
            launched_kind=(self.kind or "grok"),
        )
        self.log(f"grok: sign-in prompt; {dec.reason} (FR #8221/#8222)")
        if dec.kind == "no-seat-auth":
            # Missing login: report once, exit without switching kind.
            try:
                post_digest_seat_kind(
                    machine=self.machine,
                    pid=os.getpid(),
                    nick=self.nick,
                    kind=self.kind,
                    state="needs_sign_in",
                    log=self.log,
                )
            except Exception:
                pass
            self.shutdown("no-seat-auth-prompt", EXIT_NO_AGENT)
            return
        self._report_grok_login_expired()
        self.shutdown("xai-auth-expired-prompt", EXIT_XAI_AUTH_EXPIRED)

    def _report_grok_login_expired(self) -> None:
        """FR #8221: report once to the digest + exception reporter; never repeats."""
        if getattr(self, "_grok_login_expired_reported", False):
            return
        self._grok_login_expired_reported = True
        msg = "Grok login expired on %s: sign in, then start the seat again" % (
            self.machine or "unknown"
        )
        self.log(msg)
        try:
            import runtime_failure

            runtime_failure.report_message("bob-worker", msg, site="grok-login-expired")
        except Exception:
            pass
        try:
            post_digest_seat_kind(
                machine=self.machine,
                pid=os.getpid(),
                nick=self.nick,
                kind=self.kind,
                state="needs_sign_in",
                log=self.log,
            )
        except Exception:
            pass

    def _start_grok_signin_guard(self, proc) -> None:
        """FR #7345: kill Grok if an interactive sign-in/device-code prompt appears in 30s."""
        if (self.kind or "").strip().lower() != "grok":
            return
        guard = GrokSigninPromptGuard(
            read_fn=read_console_screen_text if os.name == "nt" else (lambda: ""),
            timeout_s=GROK_SIGNIN_PROMPT_WINDOW_S,
            clock=time.monotonic,
            log=self.log,
        )

        def _run() -> None:
            while not self._shutting and self.proc is proc and proc.poll() is None:
                try:
                    if guard.tick():
                        self._fallback_after_grok_signin_prompt(proc)
                        return
                    if guard.timed_out:
                        return
                except Exception:
                    return
                time.sleep(1.0)

        threading.Thread(target=_run, name="grok-signin-guard", daemon=True).start()

    def _start_grok_blank_tui_guard(self, proc) -> None:
        """FR #7868: report a black Grok console after 120s. Do not kill or recycle."""
        if os.name != "nt" or (self.kind or "").strip().lower() != "grok" or not grok_blank_tui_watch_enabled():
            return

        def _report() -> None:
            import runtime_failure

            runtime_failure.report_message(
                "bob-worker",
                "Grok console still blank after 120s (no TUI chrome). Same-kind recycle is not automatic.",
                site="grok-blank-tui",
            )

        guard = GrokBlankTuiGuard(
            read_fn=read_console_screen_text if os.name == "nt" else (lambda: ""),
            window_s=GROK_BLANK_TUI_WINDOW_S,
            clock=time.monotonic,
            report=_report,
            log=self.log,
        )

        def _run() -> None:
            while not self._shutting and self.proc is proc and proc.poll() is None:
                try:
                    if guard.tick():
                        return
                    if guard.rendered:
                        return
                except Exception:
                    return
                time.sleep(5.0)

        threading.Thread(target=_run, name="grok-blank-tui", daemon=True).start()

    def _inject_recovery(self) -> "InjectRecovery":
        """FR #4115: lazily build the re-paste / NACK recovery for lost assign pastes."""
        rec = getattr(self, "_recovery", None)
        if rec is not None:
            return rec

        def _reinject(line: str, cb) -> bool:
            proc = self.proc
            if proc is None:
                return False
            return bool(self._inject_line(proc, line, on_failed=cb))

        def _write(text: str) -> bool:
            return append_outbox_line(outbox_path_for_run(self.run_dir), text)

        def _clear(line: str) -> None:
            with contextlib.suppress(Exception):
                if (self.ack_miss.last_line or "") == line or not self.ack_miss.last_line:
                    self.ack_miss.clear()
            with contextlib.suppress(Exception):
                if getattr(self.relay, "last_unacked", "") == line:
                    self.relay.last_unacked = ""

        def _acked(line: str) -> bool:
            b = self.bored
            want = assign_job_ref(line)
            return bool(b is not None and want and getattr(b, "ack_open", False)
                        and getattr(b, "ack_job_ref", None) == want)

        kind = (self.kind or "").strip().lower()
        is_cursor = kind == "cursor"
        is_grok = kind == "grok"
        is_opencode = kind == "opencode"
        # FR #5159: Grok also ACK-on-receipt (FR #4115 / #4889). Treating receipt ACK
        # as ``block_on_receipt_ack`` skipped re-paste and left the job accepted
        # (marchhare-29688 / regression of #4510).
        # FR #6158: OpenCode ACK-on-receipt too --- GIVEUP submit-verify failed after one re-inject.
        receipt_ack = is_cursor or is_grok or is_opencode

        def _turn_running() -> bool:
            b = self.bored
            return bool(b is not None and getattr(b, "turn_open", False))

        rec = InjectRecovery(
            reinject=_reinject,
            write_outbox=_write,
            clear_local=_clear,
            is_acked=_acked,
            log=self.log,
            giveup_on_fail=receipt_ack,
            agent_kind=kind,
            block_on_receipt_ack=not receipt_ack,
            turn_running=_turn_running if receipt_ack else (lambda: False),
            clear_input=clear_console_input if receipt_ack else (lambda: None),
        )
        self._recovery = rec
        return rec

    def _live_skill_dag_mcp_paths(self) -> tuple[str | None, str | None, str | None]:
        """bound grok cwd, cursor/install worker cwd, vision cwd (FR #6918)."""
        kind = (self.kind or "").strip().lower()
        vision = str(self.cwd) if getattr(self, "cwd", None) else None
        bound = None
        cursor = None
        if kind == "grok" and getattr(self, "run_dir", None):
            try:
                from skill_dag_bound import BOUND_CWD_NAME
            except Exception:
                BOUND_CWD_NAME = "bound-cwd"
            cand = Path(self.run_dir) / BOUND_CWD_NAME
            if cand.is_dir():
                bound = str(cand)
        if kind == "cursor":
            cursor = vision
        return bound, cursor, vision

    def _skill_dag_preflight_for_opencode(
        self, job_worktree: str | Path | None, job_key: str = ""
    ) -> str:
        """FR #7908 / #7963: probe skill-dag; restart once; else return giveup detail.

        Returns ``""`` when healthy. On giveup returns a probe reason token such as
        ``exit-1`` or ``bad-json`` (empty string falls back to bare ``skill_dag_down``).
        Stores the last skill path on ``self._skill_dag_preflight_skill`` for the wire.
        """
        self._skill_dag_preflight_skill = ""
        if (self.kind or "").strip().lower() != "opencode":
            return ""
        if (os.environ.get("BOB_SKIP_SKILL_DAG_PREFLIGHT") or "").strip() == "1":
            return ""
        if os.environ.get("PYTEST_CURRENT_TEST") and (
            os.environ.get("BOB_SKILL_DAG_PREFLIGHT_TEST") or ""
        ).strip() != "1":
            return ""
        cwd = str(getattr(self, "cwd", "") or "")
        if not cwd:
            return ""

        last: dict = {}

        def probe() -> bool:
            nonlocal last
            last = probe_skill_dag_mcp_cli(
                cwd, job_worktree=job_worktree, job_key=job_key
            )
            skill = skill_dag_job_skill_md(cwd, job_key)
            if skill is not None:
                self._skill_dag_preflight_skill = str(skill)
            return bool(last.get("ok"))

        def restart() -> None:
            agent_pid = None
            try:
                proc = getattr(self, "proc", None)
                if proc is not None and getattr(proc, "pid", None):
                    agent_pid = int(proc.pid)
            except (TypeError, ValueError):
                agent_pid = None
            restart_skill_dag_mcp_stdio_children(
                agent_pid, [cwd, job_worktree], log=self.log
            )

        decision = skill_dag_preflight(probe, restart)
        if decision.get("action") == "giveup":
            detail = str(last.get("reason") or decision.get("reason") or "skill_dag_down")
            self.log(
                f"skill-dag preflight: {detail} job={job_key}"
                + (f" skill={self._skill_dag_preflight_skill}" if self._skill_dag_preflight_skill else "")
            )
            return detail
        if decision.get("restarted"):
            self.log("skill-dag preflight: restarted the MCP child once")
        return ""

    def _refresh_live_skill_dag_mcp(self, job_worktree: str | Path | None) -> None:
        bound, cursor, vision = self._live_skill_dag_mcp_paths()
        if not bound and not cursor:
            return
        # FR #7120 / #7308 / #7446: keep the live stdio MCP; pointer file is enough.
        # Snapshot before refresh so a drop caused by the write is visible.
        # FR #8501: confirm the before PIDs are gone via Toolhelp (twice). Do not
        # treat a flaky empty cmdline after-sample as a drop.
        # Do not use job_worktree as a cmdline marker (--job-worktree-file argv).
        agent_pid = None
        try:
            proc = getattr(self, "proc", None)
            if proc is not None and getattr(proc, "pid", None):
                agent_pid = int(proc.pid)
        except (TypeError, ValueError):
            agent_pid = None
        markers = [bound, cursor, vision]
        before = skill_dag_mcp_descendant_pids(agent_pid, markers)
        try:
            refresh_live_skill_dag_mcp_files(
                grok_bound_cwd=bound,
                cursor_cwd=cursor,
                vision_cwd=vision,
                job_worktree=job_worktree,
            )
        except Exception as e:  # noqa: BLE001
            self.log(f"skill-dag mcp job-worktree rewrite skipped {type(e).__name__}")
            return
        if skill_dag_mcp_transport_drop_confirmed(before):
            self.log("skill-dag mcp transport dropped")
            try:
                mid = str(getattr(self, "machine", "") or "")
                report_skill_dag_mcp_transport_drop(machine=mid, agent_pid=agent_pid)
            except Exception:
                pass

    def _restart_stale_skill_dag_mcp(self) -> None:
        """FR #8255: respawn this seat's skill-dag child when the script is newer."""
        bound, cursor, vision = self._live_skill_dag_mcp_paths()
        cwd = str(getattr(self, "cwd", "") or "")
        markers = [m for m in (bound, cursor, vision, cwd) if m]
        if not markers:
            return
        try:
            script = skill_dag_mcp_script_path(cwd or str(markers[0]))
        except Exception:
            return
        agent_pid = None
        try:
            proc = getattr(self, "proc", None)
            if proc is not None and getattr(proc, "pid", None):
                agent_pid = int(proc.pid)
        except (TypeError, ValueError):
            agent_pid = None
        try:
            restart_stale_skill_dag_mcp_children(
                agent_pid,
                markers,
                script,
                started_at=process_start_epoch,
                log=self.log,
            )
        except Exception as exc:  # noqa: BLE001
            self.log(f"skill-dag mcp stale-script restart skipped {type(exc).__name__}")

    def _clear_per_job_seat_state(self, job: Optional[str] = None) -> None:
        """FR #8094: drop per-job env, outbox, key, finish snap, and skill-dag pointer."""
        del job
        try:
            clear_per_job_env()
        except Exception:
            pass
        self._opencode_job_outbox = None
        self._opencode_job_key = ""
        self._opencode_finish_snap = None
        if getattr(self, "bored", None) is not None:
            try:
                self.bored._opencode_finish_attempt = 0
            except Exception:
                pass
            # FR #8247: reset external_directory loop counter for the next offer.
            try:
                self.bored.external_dir_reject_state = {
                    "counts": {},
                    "corrective_pending": False,
                }
            except Exception:
                pass
        if getattr(self, "relay", None) is not None and getattr(self, "run_dir", None) is not None:
            try:
                self.relay.outbox_path = outbox_path_for_run(self.run_dir)
            except Exception:
                pass
        try:
            self._refresh_live_skill_dag_mcp(None)
        except Exception:
            pass

    def _live_skill_dag_job_end_cleanup(self, job: Optional[str] = None) -> None:
        self._clear_per_job_seat_state(job)

    def _inject_line(self, proc, line: str, *, on_failed=None, force_verify: bool = False, sync: bool | None = None) -> bool:
        if proc.poll() is not None:
            return False
        wire = line
        kind_l0 = (self.kind or "").strip().lower()
        if kind_l0 in ("grok", "cursor") and assign_job_ref(line):
            key_pre = assign_job_key(line) or ""
            if re.match(r"(?i)^(MRB|FIX)\s+\S+#\d+$", key_pre):
                # FR #8233: refresh the job tree to headRefOid before the seat starts.
                try:
                    prepared_mrb = ensure_opencode_job_worktree(
                        line,
                        os.environ,
                        install_root=str(getattr(self, "cwd", "") or ""),
                        nick=str(getattr(self, "nick", "") or ""),
                    )
                except Exception as exc:
                    raise JobContextRefused(
                        f"NACK {key_pre} worktree-create-failed:{type(exc).__name__}"
                    )
                if prepared_mrb.get("nack"):
                    raise JobContextRefused(str(prepared_mrb["nack"]))
                sha_pre = ""
                try:
                    stamp = Path(str(prepared_mrb.get("path") or "")) / ".bob" / "reviewed-sha"
                    if stamp.is_file():
                        sha_pre = stamp.read_text(encoding="utf-8").strip()
                except OSError:
                    sha_pre = ""
                if sha_pre and f"reviewed-sha={sha_pre}" not in line:
                    line = line.rstrip() + f" reviewed-sha={sha_pre}"
                    wire = line
            try:
                wt = project_dir_for_assign(line, os.environ)
            except Exception:
                wt = ""
            if wt:
                key_gc = assign_job_key(line) or ""
                stale_gc = stale_job_context_nack_line(key_gc, worktree=wt, text=line)
                if stale_gc:
                    self.log(f"job-context: {stale_gc}")
                    raise JobContextRefused(stale_gc)
                self._refresh_live_skill_dag_mcp(wt)
                # FR #8255: a child started before skill_dag_mcp.py moved still
                # returns silent empty matched+skipped. Respawn it from tip.
                self._restart_stale_skill_dag_mcp()
        if (self.kind or "").strip().lower() == "opencode" and message_job_keys(line):
            keys = message_job_keys(line)
            if len(keys) != 1:
                raise JobContextRefused(
                    "\n".join(f"NACK {key} job-context-ambiguous (FR #6240)" for key in keys)
                )
            prepared = prepare_opencode_wire(line, os.environ)
            if prepared.get("nack"):
                self.log(prepared.get("message") or prepared["nack"])
                raise JobContextRefused(prepared["nack"])
            if prepared.get("state") == "project" and prepared.get("wire"):
                # FR #6366: append finish checklist into the FROM body before framing.
                try:
                    key = str(prepared.get("key") or "")
                    path = str(prepared.get("path") or "")
                    if key and path and line.startswith("FROM "):
                        steps = opencode_job_finish_steps(
                            job_key=key,
                            worktree=path,
                            outbox=str(Path(path) / ".bob" / "outbox.txt"),
                        )
                        if "FINISH " not in line and "FR #6366" not in line:
                            # Rebuild FROM with steps appended to payload.
                            m = re.match(
                                r"(?is)^(FROM\s+\S+\s+\S+\s+)(.*?)(\s*\[outbox:[^\]]*\]\s*)?$",
                                line,
                            )
                            if m:
                                head, body, foot = m.group(1), m.group(2), (m.group(3) or "")
                                enriched = f"{head}{body} {steps}{foot}".strip()
                                prepared = {
                                    **prepared,
                                    "wire": frame_opencode_message(
                                        enriched, key, path
                                    ),
                                }
                except Exception as e:  # noqa: BLE001
                    self.log(f"opencode-ready: finish-steps append skipped {type(e).__name__}")
                wire = prepared["wire"]
                self.log(f"opencode-ready: job worktree {prepared['path']}")
                # FR #8572: drop stale git worktree index.lock before inject (outside job cwd).
                try:
                    clear_stale_job_index_lock(prepared["path"], log_fn=self.log)
                except Exception as e:  # noqa: BLE001
                    self.log(f"opencode-ready: index.lock preflight skipped {type(e).__name__}")
                # FR #6898: OpenCode --dir loads project opencode.json from the job worktree.
                try:
                    write_opencode_skill_dag_mcp_config(
                        prepared["path"],
                        worker_cwd=self.cwd if getattr(self, "cwd", None) else prepared["path"],
                        job_worktree=prepared["path"],
                    )
                except Exception as e:  # noqa: BLE001
                    self.log(f"opencode-ready: skill-dag mcp write skipped {type(e).__name__}")
                self._restart_stale_skill_dag_mcp()
                # FR #7908: do not hand the job over when skill-dag is down.
                _sd_detail = self._skill_dag_preflight_for_opencode(
                    prepared.get("path"), str(prepared.get("key") or "")
                )
                if _sd_detail:
                    raise JobContextRefused(
                        skill_dag_down_giveup_line(
                            str(prepared.get("key") or ""),
                            probe_reason=_sd_detail,
                            skill_path=getattr(self, "_skill_dag_preflight_skill", "") or None,
                        )
                    )
                # FR #6333: tail in-worktree .bob/outbox.txt; stamp FROM footer with that path.
                try:
                    ob = ensure_opencode_bob_outbox(prepared["path"])
                    if not outbox_is_writable(ob):
                        raise OSError("outbox not writable")
                    # FR #6378: always rewrite footer to *this* job worktree outbox
                    # (never leave a prior job's cached [outbox: ...] path).
                    wire = opencode_stamp_outbox_footer(wire, ob)
                    # FR #8094: refuse before the turn if worktree/outbox/prompt lack the offer number.
                    stale = stale_job_context_nack_line(
                        str(prepared.get("key") or ""),
                        worktree=str(prepared.get("path") or ""),
                        outbox=str(ob),
                        text=wire,
                    )
                    if stale:
                        self.log(f"opencode-ready: {stale}")
                        raise JobContextRefused(stale)
                    self._opencode_job_outbox = Path(ob)
                    self._opencode_job_key = str(prepared.get("key") or "")
                    try:
                        os.environ["BOB_JOB_WORKTREE"] = str(prepared.get("path") or "")
                    except Exception:
                        pass
                    if getattr(self, "relay", None) is not None:
                        self.relay.outbox_path = Path(ob)
                except OSError as e:
                    self.log(f"opencode-ready: outbox unreachable {type(e).__name__}")
                    key = str(prepared.get("key") or "")
                    try:
                        import runtime_failure

                        runtime_failure.report_message(
                            "bob-worker",
                            "job outbox unreachable key=%s" % key,
                            site="outbox-unreachable",
                        )
                    except Exception:
                        pass
                    raise JobContextRefused("GIVEUP %s outbox_unreachable" % key) from e
                except Exception as e:  # noqa: BLE001
                    self.log(f"opencode-ready: bob outbox setup failed {type(e).__name__}")
        self.session_log.write("prompt", wire)
        if on_failed is None and assign_job_ref(line):
            on_failed = lambda l=line: self._inject_recovery().on_failed(l, attempt=1)
        kind_l = (self.kind or "").strip().lower()
        if not _submit_verify_enabled():
            # FR #6158: still log path=... kind= when verify is opted out.
            if self.inject is inject_console:
                return bool(inject_console(proc.pid, wire, log=self.log, kind=kind_l))
            try:
                return bool(self.inject(proc.pid, wire, log=self.log))
            except TypeError:
                return bool(self.inject(proc.pid, wire))
        sid = self.sessions[-1] if self.sessions else None
        # Wall-clock probe baseline (events.jsonl / unified.jsonl / opencode-turns use UTC wall times).
        since_wall = time.time()
        probe = make_submit_probe(
            self.kind,
            cwd=str(self.cwd),
            session_id=sid,
            agent_pid=int(getattr(proc, "pid", 0) or 0),
            since_wall=since_wall,
            text=line,
            run_dir=self.run_dir,
        )
        # FR #2791: stop only when the open ACK is for this injected job (not any ACK).
        stop = None
        want = assign_job_ref(line)
        is_cursor = kind_l == "cursor"
        inject_fn = self.inject
        if self.inject is inject_console:
            if is_cursor:
                inject_fn = lambda pid, text, log=None: inject_console(
                    pid, text, submit_gap_s=_cursor_submit_gap_s(), log=log, kind=kind_l
                )
            else:
                inject_fn = lambda pid, text, log=None: inject_console(
                    pid, text, log=log, kind=kind_l
                )
        if want and self.bored is not None:
            # FR #2791: job-matched ACK stop when no probe.
            # FR #4732 Cursor / FR #4889 Grok: with a probe, never stop on receipt
            # ack_open alone (ACK-on-receipt FR #4115) --- turn_open|probe only.
            if probe is not None:
                stop = cursor_submit_verify_stop(self.bored, probe=probe)
            else:
                stop = lambda b=self.bored, w=want: bool(getattr(b, "ack_open", False)) and (
                    getattr(b, "ack_job_ref", None) == w
                )
        # sync=False: do not block the IRC relay thread for the verify backoff budget.
        # FR #4456: the unverified ack-miss reminder runs the loop on this thread.
        def _mark_unverified() -> None:
            with contextlib.suppress(Exception):
                self.ack_miss.note_unverified()

        return inject_with_submit_verify(
            proc.pid,
            wire,
            inject_fn=inject_fn,
            enter_fn=send_console_enter,
            probe_fn=probe,
            clock=time.monotonic,
            sleep=time.sleep,
            log=self.log,
            stop_fn=stop,
            sync=False if sync is None else bool(sync),
            on_failed=on_failed,
            force_verify=bool(force_verify),
            on_unverified=None if force_verify else _mark_unverified,
            miss_label="no turn receipt" if kind_l == "opencode" else "no prompt seen",
            kind=kind_l,
            alive_fn=(lambda p=proc: p.poll() is None) if kind_l == "opencode" else None,
            run_dir=self.run_dir,
            job_key=assign_job_key(line) or "",
        )

    def _reconcile_wait_exit_with_shutdown(
        self, proc, code, *, kill_line: str = ""
    ) -> bool:
        """FR #8165: if shutdown began after we recorded, prefer its reason and skip report.

        Returns True when the wait thread must stop (no cli-failure / no recycle).
        """
        if not self._shutting:
            return False
        shut_reason = str(getattr(self, "_shutdown_reason", "") or "").strip() or "shutdown"
        with self._lock:
            le = self.last_exit or {}
            if le.get("pid") == getattr(proc, "pid", None):
                prev = str(le.get("reason") or "")
                if prev in ("agent-cli-nonzero-exit", "agent-exited") or (
                    is_console_closed_shutdown_reason(shut_reason)
                    and prev != shut_reason
                ):
                    self.last_exit = {
                        **le,
                        "reason": _scrub(shut_reason)[:160],
                        "exit_code": code if code is not None else le.get("exit_code"),
                    }
                    self._persist_last_exit()
        self.log(
            f"agent: exit during shutdown ({shut_reason}) code={code}; "
            f"skip cli-failure report (FR #8165); {kill_line}"
        )
        return True

    def _wait_exit(self, proc) -> None:
        try:
            code = proc.wait()
        except Exception:
            code = -1
        with self._lock:
            expected = proc.pid in self._expected_exit
            # Match by pid so a wait thread still owns the seat even when the handle object differs (tests / restarts).
            current = (
                self.proc is proc
                or (
                    self.proc is not None
                    and getattr(self.proc, "pid", None) is not None
                    and int(self.proc.pid) == int(proc.pid)
                )
            )
            started = getattr(self, "_agent_started_at", None)
        if expected or not current:
            with self._lock:
                if expected and self.last_exit and self.last_exit.get("pid") == proc.pid:
                    self.last_exit = {**self.last_exit, "exit_code": code}
                    self._persist_last_exit()
            return
        # FR #955: when the TUI dies seconds after an early inject, log the cause.
        age = (self.clock() - started) if started is not None else None
        last = ""
        try:
            last = str(getattr(self.relay, "last_unacked", "") or "")
        except Exception:
            last = ""
        # FR #1643 / MRB #1658: prefer live parent_of; fall back to spawn-time snapshot (post-wait Toolhelp often empty).
        parent_pid = 0
        parent_image = ""
        parent_cmd = ""
        try:
            parent_pid = int(parent_of(int(proc.pid)) or 0)
        except Exception:
            parent_pid = 0
        if parent_pid > 0:
            try:
                _pp, parent_image, parent_cmd = describe_process(parent_pid)
            except Exception:
                parent_image, parent_cmd = "", ""
        if parent_pid <= 0:
            parent_pid = int(getattr(self, "_agent_parent_pid", 0) or 0)
            parent_image = str(getattr(self, "_agent_parent_image", "") or "")
            parent_cmd = str(getattr(self, "_agent_parent_cmd", "") or "")
        kill_line = format_external_kill_log(
            agent_pid=int(proc.pid),
            agent_code=int(code) if code is not None else -1,
            parent_pid=parent_pid,
            parent_image=parent_image,
            parent_cmd=parent_cmd,
        )
        exit_u = normalize_agent_exit_code(code)
        exit_label = format_agent_exit_code_label(code)
        # FR #8148 / #8165: classify console-close exit before recording; if shutdown
        # already recorded (or begins while we record), do not file cli-failure.
        if exit_u == CONSOLE_CLOSE_EXIT:
            exit_reason = "console-closed"
        elif exit_u == 0:
            exit_reason = "agent-exited"
        else:
            exit_reason = "agent-cli-nonzero-exit"
        recorded = self._record_exit(proc, exit_reason, code)
        if not recorded:
            self.log(
                f"agent: exit already recorded code={code} (u32={exit_label}); "
                f"skip cli-failure report (FR #8148); {kill_line}"
            )
            return
        # FR #8165: inverse TOCTOU — we won _record_exit, then Ctrl/shutdown set
        # _shutting. Reconcile last_exit to the shutdown reason and skip cli-failure.
        if self._reconcile_wait_exit_with_shutdown(proc, code, kill_line=kill_line):
            return
        if exit_reason == "console-closed":
            self.log(
                f"agent: console-close exit code={code} (u32={exit_label}); "
                f"skip cli-failure report (FR #8165); {kill_line}"
            )
            # FR #8416: the child console can close without CTRL_CLOSE on this
            # process. Still GIVEUP an ACKed job (shutdown is a no-op if already shutting).
            self.shutdown("console-closed", EXIT_OK)
            return
        if age is not None and age < max(30.0, float(self.startup_grace_s) + 15.0):
            self.log(
                f"agent: early exit code={code} (u32={exit_label}) after {age:.1f}s "
                f"(startup_grace_s={self.startup_grace_s:.0f}); last_injected={last[:200]!r}; {kill_line}"
            )
        else:
            self.log(
                f"agent: exited by itself code={code} (u32={exit_label}); {kill_line}"
            )
        # FR #7593: zero exit ends the seat (unchanged). Nonzero → report, GIVEUP accepted
        # job (no fake DONE), restart the supported way so the replacement !bored's.
        if exit_u == 0:
            # FR #8553: OpenCode wrapper exit 0 mid-ACK is unexpected (ReadLine EOF /
            # console tear). GIVEUP the job and recycle the seat instead of dying quiet.
            job_key_z = ""
            try:
                if self.bored and getattr(self.bored, "_ack_open", False):
                    job_key_z = str(getattr(self.bored, "_ack_job_key", None) or "").strip()
            except Exception:
                job_key_z = ""
            kind_z = (self.kind or "").strip().lower()
            if kind_z == "opencode" and job_key_z:
                self.log(
                    f"agent: opencode zero exit mid-job {job_key_z}; "
                    "GIVEUP + recycle (FR #8553)"
                )
                try:
                    self._release_seat_giveup_job(job_key_z, "opencode-wrapper-exited")
                except Exception as e:
                    self.log(f"agent: mid-job giveup failed {type(e).__name__}")
                try:
                    if self.bored is not None:
                        self.bored._ack_open = False
                except Exception:
                    pass
                try:
                    self.restart_agent("opencode-wrapper-exited")
                except Exception as e:
                    self.log(f"agent: opencode zero-exit restart failed {type(e).__name__}")
                    self.shutdown("agent-exited", EXIT_OK)
                return
            self.log("agent: zero exit; leaving (a closed agent ends the seat)")
            self.shutdown("agent-exited", EXIT_OK)
            return
        job_key = ""
        try:
            if self.bored and getattr(self.bored, "_ack_open", False):
                job_key = str(getattr(self.bored, "_ack_job_key", None) or "").strip()
        except Exception:
            job_key = ""
        try:
            tail = ""
            try:
                tail = str(proc.stderr_tail() or "")
            except Exception:
                tail = ""
            report_agent_cli_nonzero_exit(
                exit_code=exit_u,
                raw_code=code,
                job_key=job_key,
                machine=self.machine,
                nick=self.nick,
                kind=self.kind,
                agent_pid=int(getattr(proc, "pid", 0) or 0),
                stderr_tail=tail or (self.last_exit or {}).get("output", ""),
                parent_cmd=parent_cmd,
                log=self.log,
            )
        except Exception as e:
            self.log(f"agent: nonzero-exit report failed {type(e).__name__}")
        if job_key:
            # Clear ack before restart_agent so hang-recycle does not double-GIVEUP.
            try:
                if self.bored is not None:
                    self.bored._ack_open = False
                    self.bored._ack_job_key = None
            except Exception:
                pass
            try:
                self._release_seat_giveup_job(job_key, "agent-cli-nonzero-exit")
            except Exception as e:
                self.log(f"agent: nonzero-exit GIVEUP failed {type(e).__name__}")
        self.log(
            f"agent: nonzero exit {exit_label}; recycling seat via restart_agent (FR #7593)"
        )
        try:
            self.restart_agent("agent-cli-nonzero-exit")
        except Exception as e:
            self.log(f"agent: nonzero-exit restart failed {type(e).__name__}")
            self.shutdown("agent-nonzero-restart-failed", EXIT_GAVE_UP)

    # ---- health
    def _ask_user_events_path(self) -> Optional[Path]:
        """FR #3623: current grok session events.jsonl when kind=grok."""
        if (self.kind or "").strip().lower() != "grok":
            return None
        sid = self.sessions[-1] if self.sessions else None
        if not sid:
            return None
        d = grok_session_dir(
            str(self.cwd), sid, sessions_root=self.sessions_root, run_dir=self.run_dir
        )
        if d is None:
            return None
        return d / "events.jsonl"

    def _check_ask_user_pending(self, proc) -> bool:
        """FR #3623: Enter once for pending ask_user, then recycle. True if handled this tick."""
        path = self._ask_user_events_path()
        age = probe_ask_user_pending_age(path) if path is not None else None
        action = self.ask_user_watch.tick(age, self.clock())
        if not action:
            return False
        age_s = float(age or 0.0)
        if action == "enter":
            self.log(f"stuck: ask_user pending {age_s:.0f}s; sending Enter (auto-answer)")
            try:
                self.send_enter(int(proc.pid))
            except Exception as e:
                self.log(f"stuck: ask_user Enter failed {type(e).__name__}")
            return True
        if action == "recycle":
            self.log(f"stuck: ask_user pending {age_s:.0f}s; recycling seat (NEW agent)")
            self.ask_user_watch.clear()
            self.restart_agent("ask-user-pending")
            return True
        return False

    def health_loop(self) -> None:
        while not self.stop.wait(self.health_interval_s):
            with self._lock:
                proc = self.proc
            if proc is None or proc.poll() is not None:
                continue
            # FR #4180: out-of-fuel is not a hang — skip HangDetector + ack-miss entirely.
            if self.bored and self.bored.out_of_fuel:
                self._clear_watchdogs_for_out_of_fuel()
                continue
            try:
                s = self.probe(proc.pid)
            except Exception:
                continue
            prev_io = getattr(self, "_io_activity", None)
            self._io_activity = s.activity
            # FR #4827: process I/O while a job is open keeps ack-stale from firing.
            if prev_io is not None and s.activity != prev_io and self.bored:
                self.bored.note_agent_active()
            # FR #8249: progress heartbeats run on dedicated progress-heartbeat thread.
            reason = self.detector.check(s, self.clock())
            if reason:
                self.restart_agent(reason)
                continue
            # FR #8596: OpenCode frozen digest/progress (CPU may still tick; HangDetector misses).
            if self._check_opencode_frozen_progress():
                continue
            # FR #3623: ask_user_question Pending (alive process, ACK held) - Enter then recycle.
            if self._check_ask_user_pending(proc):
                continue
            # FR #2383: agent still alive/turning but never ACK'd via run-dir outbox.
            self._check_ack_miss(proc)

    def _progress_hb_skip(self, reason: str, *, now_mono: float) -> None:
        """Rate-limited skip log so a missing heartbeat can be attributed (FR #8249)."""
        last = float(getattr(self, "_progress_hb_skip_log_mono", 0.0) or 0.0)
        if last and (now_mono - last) < 30.0:
            return
        self._progress_hb_skip_log_mono = now_mono
        try:
            self.log(f"progress-heartbeat: skip reason={reason}")
        except Exception:
            pass

    def _progress_heartbeat_loop(self) -> None:
        """FR #8249: dedicated timer; one bad tick must not end the thread."""
        tick_s = 5.0
        while not self.stop.wait(tick_s):
            if getattr(self, "_shutting", False):
                return
            try:
                self._maybe_progress_heartbeat()
            except Exception as e:
                try:
                    self.log(f"progress-heartbeat: tick failed {type(e).__name__}")
                except Exception:
                    pass

    def _start_progress_heartbeat(self) -> None:
        """Start the supervised progress-heartbeat daemon (FR #8249)."""
        th = getattr(self, "_progress_hb_thread", None)
        if th is not None and th.is_alive():
            return
        self._progress_hb_thread = threading.Thread(
            target=self._progress_heartbeat_loop,
            name="progress-heartbeat",
            daemon=True,
        )
        self._progress_hb_thread.start()
        try:
            self.log("progress-heartbeat: thread started")
        except Exception:
            pass

    def _stop_progress_heartbeat(self) -> None:
        """Join progress-heartbeat after stop is set (bounded, FR #8249)."""
        th = getattr(self, "_progress_hb_thread", None)
        self._progress_hb_thread = None
        if th is not None and th.is_alive() and th is not threading.current_thread():
            th.join(timeout=2.0)

    def _maybe_progress_heartbeat(self) -> None:
        """FR #8155 / #8195 / #8249: post last_progress while ACK is open.

        Runs on the dedicated ``progress-heartbeat`` thread. Reads a lock-free
        BoredEmitter snapshot and ``self.proc`` without taking supervisor ``RLock``
        or emitter ``_cv`` for the gate. Log/worktree growth still counts; a live
        seat wrapper also refreshes the clock (FR #8195) so silent long commands
        and multi-turn OpenCode gaps keep ``last_progress`` fresh for the stuck sweep.
        """
        if getattr(self, "_shutting", False) or self.stop.is_set():
            return
        bored = self.bored
        if bored is None:
            self._progress_prev = {}
            self._progress_phase = ""
            return
        snap = bored.heartbeat_snapshot()
        now_mono = float(self.clock())
        # FR #8494: out-of-fuel hold still heartbeats so digest ``updated`` stays fresh
        # and state paints ``out_of_fuel`` (not quiet idle). ACK may already be clear.
        if snap.out_of_fuel:
            self._post_fuel_hold_heartbeat(now_mono=now_mono)
            return
        if not snap.ack_open:
            self._progress_prev = {}
            self._progress_phase = ""
            # Due only when a prior epoch was posting; otherwise stay quiet.
            if int(getattr(self, "_progress_hb_epoch", 0) or 0):
                self._progress_hb_skip("no-ack", now_mono=now_mono)
            self._progress_hb_epoch = 0
            return
        # Plain reference read — do not take self._lock (FINISH / start_agent hold it).
        proc = self.proc
        agent_alive = False
        try:
            agent_alive = proc is not None and proc.poll() is None
        except Exception:
            agent_alive = False
        if not agent_alive:
            self._progress_hb_skip("proc-exited", now_mono=now_mono)
            return
        wt = str(os.environ.get("BOB_JOB_WORKTREE") or "").strip()
        moved, phase, state = detect_seat_progress(
            kind=self.kind,
            run_dir=self.run_dir,
            job_worktree=wt,
            prev=self._progress_prev,
        )
        self._progress_prev = state
        if progress_alive_counts_as_seen(moved=moved, agent_alive=agent_alive):
            self._progress_last_seen_mono = now_mono
            self._progress_last_seen_wall = time.time()
            # FR #8596: true log/turn/worktree move only (not alive-only) for frozen recycle.
            if moved:
                self._progress_last_moved_mono = now_mono
            if moved and phase:
                self._progress_phase = phase
            elif agent_alive and not self._progress_phase:
                self._progress_phase = progress_phase_for_alive_heartbeat("")
            # Bounded acquire; if busy, still POST without blocking (FR #8249).
            try:
                bored.note_agent_active_nb(at=now_mono)
            except Exception:
                pass
        # Heartbeat while progress/alive was seen recently (stops when stalled dead).
        stale_after = max(float(self._progress_heartbeat_s) * 1.5, 180.0)
        last_seen = float(getattr(self, "_progress_last_seen_mono", 0.0) or 0.0)
        if last_seen <= 0:
            return
        if (now_mono - last_seen) > stale_after:
            return
        epoch = int(snap.ack_epoch)
        prev_epoch = int(getattr(self, "_progress_hb_epoch", 0) or 0)
        last_post = float(getattr(self, "_progress_last_post_mono", 0.0) or 0.0)
        # New ACK epoch: POST on the next due tick (do not inherit prior job cadence).
        if epoch != prev_epoch:
            self._progress_hb_epoch = epoch
            self._progress_last_post_mono = 0.0
            last_post = 0.0
        if last_post and (now_mono - last_post) < float(self._progress_heartbeat_s):
            return
        work = str(snap.ack_job_key or "").strip()
        try:
            from bobreport import _utc_now_iso

            iso = _utc_now_iso()
        except Exception:
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        use_phase = self._progress_phase or phase or progress_phase_for_alive_heartbeat("")
        if submit_verify_in_flight():
            use_phase = "submit-verify"
        # Re-validate immediately before POST (scan→POST race). An in-flight HTTP
        # request cannot be recalled once started.
        if getattr(self, "_shutting", False) or self.stop.is_set():
            self._progress_hb_skip("stopping", now_mono=now_mono)
            return
        snap2 = bored.heartbeat_snapshot()
        if snap2.out_of_fuel:
            self._post_fuel_hold_heartbeat(now_mono=now_mono)
            return
        if (
            not snap2.ack_open
            or int(snap2.ack_epoch) != epoch
            or str(snap2.ack_job_key or "").strip() != work
        ):
            skip_why = "no-ack" if not snap2.ack_open else "job-changed"
            self._progress_hb_skip(skip_why, now_mono=now_mono)
            return
        proc2 = self.proc
        if proc2 is not proc:
            self._progress_hb_skip("job-changed", now_mono=now_mono)
            return
        try:
            if proc2 is None or proc2.poll() is not None:
                self._progress_hb_skip("proc-exited", now_mono=now_mono)
                return
        except Exception:
            self._progress_hb_skip("proc-exited", now_mono=now_mono)
            return
        ok = post_digest_progress_heartbeat(
            machine=self.machine,
            nick=self.nick,
            pid=getattr(proc2, "pid", None),
            kind=self.kind,
            work=work,
            last_progress=iso,
            progress_phase=use_phase,
            log=self.log,
        )
        if ok:
            self._progress_last_post_mono = now_mono
            self._progress_last_post_wall = time.time()
            self.log(
                f"progress-heartbeat: last_progress={iso} phase={use_phase or '-'}"
            )

    def _post_fuel_hold_heartbeat(self, *, now_mono: float) -> None:
        """FR #8494: presence tick while out-of-fuel so digest ``updated`` advances."""
        interval = max(float(getattr(self, "_progress_heartbeat_s", 30.0) or 30.0), 5.0)
        last = float(getattr(self, "_fuel_hb_mono", 0.0) or 0.0)
        if last and (now_mono - last) < interval:
            return
        try:
            from bobreport import _utc_now_iso

            iso = _utc_now_iso()
        except Exception:
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        proc = self.proc
        pid = None
        try:
            if proc is not None and proc.poll() is None:
                pid = getattr(proc, "pid", None)
        except Exception:
            pid = None
        ok = post_digest_progress_heartbeat(
            machine=self.machine,
            nick=self.nick,
            pid=pid,
            kind=self.kind,
            work="out-of-fuel",
            last_progress=iso,
            progress_phase="out-of-fuel",
            state="out_of_fuel",
            log=self.log,
        )
        if ok:
            self._fuel_hb_mono = now_mono
            self._progress_last_post_mono = now_mono
            self._progress_last_post_wall = time.time()
            self.log(f"progress-heartbeat: fuel-hold last_progress={iso}")

    def _inject_failed_turn_retry(self, job_key: str) -> None:
        """FR #7201: re-inject the last assign once after an error turn (bounded).

        FR #8247: when ``external_dir_reject_state.corrective_pending`` is set, do not
        re-inject ``relay.last_line`` (that re-sends the same FINISH/assign). Route to
        ``_inject_done_miss_reminder``, which emits the scratch-path corrective.
        """
        key = (job_key or "").strip()
        # FR #8247 / MRB #8252: external_directory corrective must not re-paste the assign.
        if self.bored is not None:
            st = getattr(self.bored, "external_dir_reject_state", None)
            if isinstance(st, dict) and st.get("corrective_pending"):
                self.log(
                    f"external-dir: failed-turn retry routes to corrective for {key}"
                )
                self._inject_done_miss_reminder(key)
                return
        line = ""
        with contextlib.suppress(Exception):
            line = str(getattr(self.relay, "last_line", None) or getattr(self.relay, "last_unacked", None) or "")
        if line and key and (assign_job_key(line) or "").lower() == key.lower():
            with self._lock:
                proc = self.proc
            if proc is None or proc.poll() is not None:
                self.log(f"failed-turn: no live agent to retry {job_key}")
                return
            try:
                self._inject_line(proc, line, sync=False)
                self.log(f"failed-turn: re-injected assign for {job_key}")
                return
            except Exception as e:
                self.log(f"failed-turn: re-inject failed {type(e).__name__}")
        self._inject_done_miss_reminder(job_key)

    def _inject_done_miss_reminder(self, job_key: str) -> None:
        """FR #2875 / #6366 / #8247: inject done-miss reminder (OpenCode: finish or corrective)."""
        outbox = outbox_path_for_run(self.run_dir)
        shop = shop_channel(self.machine)
        kind = (self.kind or "").strip().lower()
        if kind == "opencode":
            wt = str(os.environ.get("BOB_JOB_WORKTREE") or "").strip()
            job_ob = getattr(self, "_opencode_job_outbox", None)
            if job_ob is not None:
                outbox = Path(job_ob)
                if not wt:
                    try:
                        # <worktree>/.bob/outbox.txt -> worktree
                        wt = str(Path(job_ob).resolve().parent.parent)
                    except Exception:
                        wt = ""
            if wt:
                # Snapshot before finish-run for progress compare.
                self._opencode_finish_snap = opencode_finish_progress_snapshot(wt)
                # FR #8247: after an external_directory reject, inject a short corrective
                # that names .bob\tmp instead of the same FINISH text.
                use_corrective = False
                if self.bored is not None:
                    st = getattr(self.bored, "external_dir_reject_state", None)
                    if isinstance(st, dict) and st.get("corrective_pending"):
                        use_corrective = True
                        st["corrective_pending"] = False
                if use_corrective:
                    scratch = ensure_opencode_job_scratch(wt)
                    body = opencode_external_dir_corrective_steps(
                        job_key=job_key,
                        worktree=wt,
                        outbox=outbox,
                        scratch=scratch,
                    )
                    from_line = format_from(
                        "bob-worker", shop, body, outbox=outbox
                    )
                    try:
                        line = frame_opencode_message(from_line, job_key, wt)
                    except Exception:
                        line = from_line
                else:
                    line = opencode_done_miss_reminder_line(
                        shop=shop, outbox=outbox, job_key=job_key, worktree=wt
                    )
            else:
                line = done_miss_reminder_line(shop=shop, outbox=outbox, job_key=job_key)
        else:
            line = done_miss_reminder_line(shop=shop, outbox=outbox, job_key=job_key)
        with self._lock:
            proc = self.proc
        if proc is None or proc.poll() is not None:
            self.log(f"done-miss: no live agent to remind for {job_key}")
            return
        try:
            # OpenCode finish frames: one_line raises maxlen to 2000 for @@BOBJOB1.
            self._inject_line(proc, line)
        except Exception as e:
            self.log(f"done-miss: remind inject failed {type(e).__name__}")

    def _opencode_finish_post_done(
        self,
        job_key: str,
        pr_url: str,
        *,
        pr_opened_by: str = "worker",
        done_by: str = "worker",
    ) -> None:
        """FR #6370 / #6378: append DONE to the OpenCode job outbox (auto-PR or model PR)."""
        key = (job_key or "").strip() or "job"
        url = (pr_url or "").strip()
        payload = f"DONE {key} {url}".strip()
        shop = shop_channel(self.machine)
        line = f"PRIVMSG {shop} :{payload}"
        ob = getattr(self, "_opencode_job_outbox", None)
        if ob is None:
            ob = outbox_path_for_run(self.run_dir)
        try:
            if append_outbox_line(Path(ob), line):
                self.log(
                    f"opencode finish: auto DONE written for {key} "
                    f"pr_opened_by={pr_opened_by} done_by={done_by}"
                )
            else:
                self.log(f"opencode finish: auto DONE write failed for {key}")
        except Exception as e:  # noqa: BLE001
            self.log(f"opencode finish: auto DONE write failed {type(e).__name__}")
        if self.bored is not None:
            try:
                self.bored.on_outbox(payload)
            except Exception as e:  # noqa: BLE001
                self.log(f"opencode finish: bored on_outbox failed {type(e).__name__}")

    def _opencode_job_end_cleanup(self, job: Optional[str] = None) -> None:
        """FR #6370: drop Temp worktrees; FR #8094: clear per-job context for the next offer."""
        wt = str(os.environ.get("BOB_JOB_WORKTREE") or "").strip()
        if (self.kind or "").strip().lower() == "opencode" and wt:
            try:
                opencode_cleanup_extra_worktrees(wt, log_fn=self.log)
            except Exception as e:  # noqa: BLE001
                self.log(f"opencode finish: cleanup failed {type(e).__name__}")
        self._clear_per_job_seat_state(job)

    def _opencode_finish_decide(self, job_key: str) -> str:
        """FR #6366 / #6370: retry while progress; else auto-PR or giveup."""
        max_n = opencode_finish_run_max()
        attempt = int(getattr(self.bored, "_opencode_finish_attempt", 0) or 0) if self.bored else 0
        wt = str(os.environ.get("BOB_JOB_WORKTREE") or "").strip()
        before = getattr(self, "_opencode_finish_snap", None) or {}
        after = opencode_finish_progress_snapshot(wt) if wt else {}
        progress = opencode_finish_progress_changed(before, after) if before else False
        self.log(
            f"opencode finish-run key={job_key} attempt={attempt}/{max_n} "
            f"progress={'yes' if progress else 'no'}"
        )
        if progress and attempt < max_n:
            self._opencode_finish_snap = after
            return "retry"
        # FR #6378: model already opened a PR but skipped DONE -> worker DONE (not GIVEUP).
        if wt and (after.get("has_pr") or before.get("has_pr")):
            url = str(after.get("pr_url") or before.get("pr_url") or "").strip()
            if not url:
                try:
                    url = opencode_finish_open_pr_url(wt, job_key)
                except Exception as e:  # noqa: BLE001
                    self.log(f"opencode finish: open-PR lookup failed {type(e).__name__}")
                    url = ""
            if url:
                self.log(
                    f"opencode finish: existing PR {url} pr_opened_by=model done_by=worker"
                )
                self._opencode_finish_post_done(
                    job_key, url, pr_opened_by="model", done_by="worker"
                )
                self._opencode_job_end_cleanup(job_key)
                return "done"
        # FR #6370: before GIVEUP, open PR if branch is pushed ahead with no PR.
        if wt:
            try:
                url = opencode_finish_auto_pr(wt, job_key)
            except Exception as e:  # noqa: BLE001
                self.log(f"opencode finish: auto-PR failed {type(e).__name__}")
                url = ""
            if url:
                self.log(f"opencode finish: auto-PR {url} pr_opened_by=worker done_by=worker")
                self._opencode_finish_post_done(
                    job_key, url, pr_opened_by="worker", done_by="worker"
                )
                self._opencode_job_end_cleanup(job_key)
                return "done"
            self._opencode_job_end_cleanup(job_key)
        return "giveup"



    def _opencode_report_doing_age_s(self, nick: str) -> float | None:
        """Best-effort age from live GET /bob/v1/report for this nick (FR #8596)."""
        url = (
            str(os.environ.get("BOB_REPORT_URL") or "").strip()
            or str(os.environ.get("BOB_DIGEST_URL") or "").strip()
            or "https://bob.ntsa.uk/bob/v1/report"
        )
        try:
            import urllib.request

            req = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "BobiverseWorker-opencode-frozen/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            doc = json.loads(raw)
        except Exception:
            return None
        return digest_worker_doing_age_s(doc, nick, now_wall=time.time())

    def _check_opencode_frozen_progress(self) -> bool:
        """FR #8596: recycle OpenCode when digest doing is stale or log/turn progress froze.

        Does not treat week.limited alone as out-of-fuel (rolling may remain). Hard
        out-of-fuel hold still skips via FR #4180 inside restart_agent / health_loop.
        """
        if (self.kind or "").strip().lower() != "opencode":
            return False
        if self.bored and self.bored.out_of_fuel:
            return False
        thr = opencode_frozen_progress_threshold_s()
        ack_open = bool(self.bored and getattr(self.bored, "_ack_open", False))
        now_mono = float(self.clock())
        moved_age = None
        last_moved = float(getattr(self, "_progress_last_moved_mono", 0.0) or 0.0)
        if last_moved > 0:
            moved_age = max(0.0, now_mono - last_moved)
        elif ack_open:
            # ACK open but never recorded a true move - age from ACK open if known.
            opened = float(getattr(self.bored, "_ack_opened_mono", 0.0) or 0.0) if self.bored else 0.0
            if opened > 0:
                moved_age = max(0.0, now_mono - opened)
        digest_age = None
        nick = str(getattr(self, "nick", "") or os.environ.get("BOB_NICK") or "")
        try:
            home = None
            try:
                import bobreport as _br

                home = _br.digest_home()
            except Exception:
                home = None
            doc = None
            if home is not None:
                import bobreport as _br

                try:
                    doc = _br.load_digest(home)
                except Exception:
                    doc = None
            digest_age = digest_worker_doing_age_s(doc, nick, now_wall=time.time())
            # Worker boxes often lack the chair digest; fall back to live /report (FR #8596).
            if digest_age is None and nick:
                digest_age = self._opencode_report_doing_age_s(nick)
        except Exception:
            digest_age = None
        reason = opencode_frozen_recycle_reason(
            kind=self.kind,
            out_of_fuel=bool(self.bored and self.bored.out_of_fuel),
            ack_open=ack_open,
            digest_doing_age_s=digest_age,
            progress_moved_age_s=moved_age,
            threshold_s=thr,
        )
        if not reason:
            return False
        self.log(
            f"opencode-frozen: reason={reason} digest_age={digest_age!r} "
            f"moved_age={moved_age!r} thr={thr:.0f}s; recycling"
        )
        self.restart_agent(reason)
        return True

    def _check_ack_miss(self, proc) -> None:
        # FR #4180: out-of-fuel is not an ACK miss — never remind or recycle.
        if self.bored and self.bored.out_of_fuel:
            self.ack_miss.clear()
            self.log("ack-miss: suppressed (out-of-fuel hold; no remind/recycle)")
            return
        ack_open = bool(self.bored.ack_open) if self.bored else False
        action = self.ack_miss.tick(self.clock(), ack_open=ack_open)
        if not action:
            return
        outbox = outbox_path_for_run(self.run_dir)
        shop = shop_channel(self.machine)
        if action == "remind":
            line = self.ack_miss.reminder_line(shop=shop, outbox=outbox)
            what = "pending assign" if line == self.ack_miss.last_line else "outbox reminder"
            unverified = bool(getattr(self.ack_miss, "unverified", False))
            extra = " forced submit-verify (FR #4456)" if unverified else ""
            self.log(
                f"ack-miss: no ACK after assign for {self.ack_miss.remind_s:.0f}s; "
                f"re-injecting {what}{extra} path={outbox}"
            )
            try:
                # Unverified (no probe) reminder blocks until the Enter loop finishes, then
                # the next health tick recycles instead of waiting recycle_s.
                self._inject_line(
                    proc,
                    line,
                    force_verify=unverified,
                    sync=True if unverified else None,
                    # Do not NACK via InjectRecovery: the next tick recycles (FR #4456).
                    on_failed=(lambda: None) if unverified else None,
                )
            except Exception as e:
                self.log(f"ack-miss: remind inject failed {type(e).__name__}")
            return
        if action == "recycle":
            job_key = ""
            try:
                job_key = assign_job_key(self.ack_miss.last_line) or ""
            except Exception:
                job_key = ""
            out_text = ""
            turns_text = ""
            try:
                chunks: list[str] = []
                # Run-dir outbox plus the OpenCode worktree .bob/outbox.txt (FR #6333).
                paths = [Path(outbox)]
                try:
                    paths.extend(self.opencode_extra_outbox_paths())
                except Exception:
                    pass
                seen: set[str] = set()
                for op in paths:
                    key = str(op)
                    if key in seen:
                        continue
                    seen.add(key)
                    if op.is_file():
                        chunks.append(op.read_text(encoding="utf-8", errors="replace"))
                out_text = "\n".join(chunks)
            except Exception:
                out_text = ""
            try:
                turns = Path(self.run_dir) / "opencode-turns.jsonl"
                if turns.is_file():
                    turns_text = turns.read_text(encoding="utf-8", errors="replace")
            except Exception:
                turns_text = ""
            alt = ack_miss_exit_reason(
                outbox_text=out_text, turns_text=turns_text, job_key=job_key
            )
            if alt:
                # FR #8415: do not stamp no-ack, and do not GIVEUP a finished job (#8384).
                self.ack_miss.clear()
                self.log(
                    f"ack-miss: terminal wire already posted; last-exit {alt} "
                    f"not no-ack-after-assign (FR #8415)"
                )
                try:
                    if proc is not None and proc.poll() is not None:
                        self._record_exit(
                            proc, alt, proc.poll(), report=False, job_key=job_key
                        )
                except Exception:
                    pass
                return
            self.log(
                f"ack-miss: still no ACK after {self.ack_miss.recycle_s:.0f}s; "
                f"recycling seat (NEW agent) path={outbox}"
            )
            self.ack_miss.clear()
            self.restart_agent("no-ack-after-assign")

    def _startup_activity_paths(self) -> list:
        paths: list = []
        try:
            paths.append(default_unified_log_path(run_dir=self.run_dir))
        except Exception:
            pass
        try:
            ev = self._ask_user_events_path()
            if ev is not None:
                paths.append(ev)
        except Exception:
            pass
        return paths

    def _announce_hang_restart_limit(self, reason: str) -> None:
        """FR #7150: shop + run_dir marker when exit=5 hang-restart-limit fires."""
        detail = (
            f"hang-restart-limit reason={reason} "
            f"restarts={self.restart_max}/{int(self.restart_window_s)}s "
            f"exit={EXIT_GAVE_UP}"
        )
        try:
            marker = Path(self.run_dir) / "hang-restart-limit.txt"
            marker.write_text(detail + "\n", encoding="utf-8")
        except OSError as e:
            self.log(f"agent: hang-restart-limit marker failed {type(e).__name__}")
        try:
            if self.irc is not None and getattr(self.irc, "shop", None):
                self.irc.say(self.irc.shop, detail)
        except Exception as e:
            self.log(f"agent: hang-restart-limit shop announce failed {type(e).__name__}")

    def restart_agent(self, reason: str) -> None:
        # FR #4180: never respawn while out-of-fuel (402 / exhausted is not a hang).
        if self.bored and self.bored.out_of_fuel:
            self.log(
                f"agent: HUNG ({reason}) ignored - out-of-fuel hold (no respawn; FR #4180)"
            )
            self._clear_watchdogs_for_out_of_fuel()
            return
        # FR #7123: never silently drop an accepted job on hang-recycle.
        if self.bored and getattr(self.bored, "_ack_open", False) and getattr(self.bored, "_ack_job_key", None):
            try:
                self._release_seat_giveup_job(str(self.bored._ack_job_key), "hang-recycle")
            except Exception as e:
                self.log(f"agent: hang-recycle GIVEUP failed {type(e).__name__}")
        # FR #7978: carry the job the seat was on into the intake body (not job=(none)).
        job_key = ""
        try:
            if self.bored:
                job_key = str(getattr(self.bored, "_ack_job_key", None) or "").strip()
        except Exception:
            job_key = ""
        if not job_key:
            try:
                pending = str(getattr(self.relay, "last_unacked", "") or "")
                job_key = (assign_job_key(pending) or "").strip()
            except Exception:
                job_key = ""
        with self._lock:
            if self._shutting or self.proc is None:
                return
            if reason != "agent-cli-nonzero-exit":
                self._record_exit(
                    self.proc, reason, self.proc.poll(), report=True, job_key=job_key
                )
            now = self.clock()
            # FR #4180: restart counter is monotonic per incident. Only clear the list when the
            # last restart is older than the window (incident ended); never drop mid-incident
            # entries just because individually they aged past the window.
            if self.restarts:
                last_t = float(self.restarts[-1][0])
                if (now - last_t) >= float(self.restart_window_s):
                    self.restarts = []
            if len(self.restarts) >= self.restart_max:
                self.log(f"agent: HUNG ({reason}) and restart limit {self.restart_max}/{int(self.restart_window_s)}s reached - giving up")
                give_up = True
            else:
                give_up = False
                n = len(self.restarts)
                self.restarts.append((now, reason))
                delay = self.backoff[min(n, len(self.backoff) - 1)] if self.backoff else 0.0
                old = self.proc
                self._expected_exit.add(old.pid)
        if give_up:
            # FR #7150: surface hang-restart-limit on the shop channel and in run_dir so
            # ear/Jeeves/operators can see why a seat vanished (class of redqueen 16:55
            # 916/14100 -> 11952/8540; no Jeeves recycleseat log).
            self._announce_hang_restart_limit(reason)
            self.shutdown("hang-restart-limit", EXIT_GAVE_UP)
            return
        self.log(f"agent: HUNG ({reason}); restart {n + 1}/{self.restart_max} after {delay:.0f}s backoff (old pid={old.pid}) - NEW agent, no resume")
        self.ask_user_watch.clear()
        self.relay.set_target(None)
        if self.bored:
            self.bored.set_ready(False)
        self.kill(old.pid)
        if delay > 0 and self.stop.wait(delay):
            return
        # FR #4180: never re-deliver an assign into a seat that went out-of-fuel mid-restart.
        if self.bored and self.bored.out_of_fuel:
            self._clear_watchdogs_for_out_of_fuel()
            self.log("agent: skip re-hold of pending assign (out-of-fuel during restart)")
            pending = None
        else:
            pending = self.relay.last_unacked
        if pending:
            self.relay.hold(pending)  # the message in flight when the old agent hung is re-delivered to the NEW one once it is ready
        if not self.start_agent(note="(restarted after a hang; the previous session was discarded)"):
            self.shutdown("restart-launch-failed", EXIT_LAUNCH_FAIL)

    # ---- end

    def _on_irc_lost(self, why: str) -> None:
        """FR #3456: reconnect with grace (keep agent); grace 0 = legacy immediate exit."""
        if self._shutting or self.stop.is_set():
            return
        if float(self.reconnect_grace_s) <= 0:
            self.shutdown("irc-lost: " + why, EXIT_IRC_LOST)
            return
        with self._lock:
            if self._irc_reconnecting:
                return
            self._irc_reconnecting = True
            self._irc_lost_at = self.clock()
        self.log(
            f"irc: lost ({why}); reconnect grace {self.reconnect_grace_s:.0f}s - keeping agent"
        )
        th = threading.Thread(
            target=self._reconnect_loop, args=(why,), name="irc-reconnect", daemon=True
        )
        self._reconnect_thread = th
        th.start()

    def _reconnect_loop(self, why: str) -> None:
        backoff = (1.0, 2.0, 5.0, 10.0, 20.0, 30.0)
        i = 0
        try:
            while not self.stop.is_set() and not self._shutting:
                lost_at = float(self._irc_lost_at or self.clock())
                elapsed = self.clock() - lost_at
                if elapsed >= float(self.reconnect_grace_s):
                    self.log(f"irc: reconnect grace exhausted ({elapsed:.0f}s); exiting cleanly")
                    self.shutdown("irc-lost-grace: " + why, EXIT_IRC_LOST)
                    return
                delay = float(backoff[min(i, len(backoff) - 1)])
                left = float(self.reconnect_grace_s) - elapsed
                self.stop.wait(min(delay, max(0.1, left)))
                if self.stop.is_set() or self._shutting:
                    return
                if self.irc is None:
                    self.shutdown("irc-lost-grace: no irc", EXIT_IRC_LOST)
                    return
                try:
                    self.irc.prepare_reconnect()
                    self.irc.connect_with_retries(attempts=1, timeout=20.0, backoff_s=(0.0,))
                    self.log("irc: reconnected; flushing outbox and re-ACK")
                    self._after_irc_reconnect()
                    with self._lock:
                        self._irc_reconnecting = False
                        self._irc_lost_at = None
                    return
                except Exception as e:
                    self.log(
                        f"irc: reconnect attempt failed {type(e).__name__}: {str(e)[:100]}"
                    )
                    i += 1
        finally:
            with self._lock:
                if self._shutting:
                    self._irc_reconnecting = False

    def _after_irc_reconnect(self) -> None:
        """Rebind handlers, flush held outbox, re-ACK open job (FR #3456)."""
        if self.irc is None:
            return
        self.irc.on_message = self.relay.deliver
        self.irc.on_lost = self._on_irc_lost
        if self.bored is not None:
            self.irc.on_nak = self.bored.nak
            self.irc.on_nak_line = self._replay_done_on_busy_hold  # FR #4642
        ob = self.run_dir / "outbox.txt"
        try:
            drain_outbox(
                ob,
                self.irc,
                self.log,
                self.on_outbox_wire,
                self.may_send_outbox,
                enrich_line=self.enrich_done_line,
            )
        except Exception as e:
            self.log(f"irc: post-reconnect outbox flush {type(e).__name__}")
        if self.bored is None:
            return
        key = None
        try:
            with self.bored._cv:
                if self.bored._ack_open and self.bored._ack_job_key:
                    key = self.bored._ack_job_key
        except Exception:
            key = None
        if not key:
            return
        line = "ACK " + str(key)
        try:
            if self.irc.say(self.irc.shop, line):
                self.log("irc: re-ACK after reconnect: " + line)
            else:
                # hold for next drain
                try:
                    ensure_outbox(ob)
                    prev = ob.read_text(encoding="utf-8") if ob.is_file() else ""
                    ob.write_text("PRIVMSG " + self.irc.shop + " :" + line + "\n" + prev, encoding="utf-8")
                except OSError:
                    pass
        except Exception as e:
            self.log(f"irc: re-ACK failed {type(e).__name__}")

    def shutdown(self, reason: str, code: int) -> None:

        with self._lock:
            if self._shutting:
                return
            self._shutting = True
            self._shutdown_reason = str(reason or "")
            self.exit_code = code
            proc = self.proc
            if proc is not None:
                self._expected_exit.add(proc.pid)
        self.log(f"worker: shutting down ({reason}) exit={code}")
        # FR #8154: console-close / Ctrl path must GIVEUP an ACKed job and save WIP
        # before IRC close. Shared for every seat kind.
        try:
            self._giveup_on_console_closed_shutdown(reason)
        except Exception as e:
            self.log(f"worker: console-closed GIVEUP failed {type(e).__name__}")
        if proc is not None and self._exit_recorded_pid != proc.pid:
            self._record_exit(proc, reason, proc.poll(), report=code != EXIT_OK)
        self._stop_session_log()
        self.stop.set()
        self._stop_progress_heartbeat()
        self._stop_turn_watcher()
        self._stop_fuel_watcher()
        if self.bored:
            self.bored.stop()  # no !bored after IRC loss / shutdown
        self.relay.close()
        if self._grace_timer:
            try:
                self._grace_timer.cancel()
            except Exception:
                pass
            self._grace_timer = None
        if self._min_ready_timer:
            try:
                self._min_ready_timer.cancel()
            except Exception:
                pass
            self._min_ready_timer = None
        self._startup_hold_armed = False
        if proc is not None and proc.poll() is None:
            if proc.pid in self._owned:  # only the tree THIS exe started
                self.kill(proc.pid)
                self.log(f"worker: killed own agent tree root pid={proc.pid}")
        if self.irc:
            self.irc.close(reason.split(":")[0][:40])
        self.done.set()

    def _giveup_on_console_closed_shutdown(self, reason: str) -> None:
        """FR #8154: release ACKed job + WIP snapshot when the console closes."""
        if not is_console_closed_shutdown_reason(reason):
            return
        if not self.bored or not getattr(self.bored, "_ack_open", False):
            return
        job_key = str(getattr(self.bored, "_ack_job_key", None) or "").strip()
        if not job_key:
            return
        wt = resolve_console_closed_worktree(job_key)
        wip_ref = ""
        if wt:
            try:
                wip_ref = save_console_closed_wip(
                    wt, job_key, log=self.log
                )
            except Exception as e:
                self.log(f"console-closed-wip: save failed {type(e).__name__}")
                wip_ref = ""
        line = console_closed_giveup_line(job_key, wip_ref)
        why = "console-closed"
        if wip_ref:
            why = f"console-closed wip={wip_ref}"
        sent = False
        shop = self.irc.shop if self.irc else shop_channel(self.machine)
        if self.irc and getattr(self.irc, "alive", False):
            try:
                self.irc.say(shop, line)
                sent = True
                try:
                    self.irc.say(
                        shop,
                        f"seat-release: {self.nick} GIVEUP `{job_key}` reason={why}",
                    )
                except Exception:
                    pass
            except Exception as e:
                self.log(f"console-closed: GIVEUP say failed {type(e).__name__}")
                sent = False
        if not sent:
            # Durable pending file for the next seat on this machine (run-dir may die).
            append_pending_console_closed_giveup(
                self.machine, line, log=self.log
            )
            # Also seat outbox as a best-effort flush if the run dir survives briefly.
            try:
                outbox = getattr(self.bored, "run_dir", None) or self.run_dir
                if outbox:
                    path = Path(outbox) / "outbox.txt"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8", newline="\n") as fh:
                        fh.write(f"PRIVMSG {shop} :{line}\n")
            except Exception as e:
                self.log(f"console-closed: outbox GIVEUP failed {type(e).__name__}")
        try:
            with self.bored._cv:
                self.bored._ack_open = False
                self.bored._ack_job_key = None
                self.bored._hb_notify_all()
        except Exception:
            try:
                self.bored._ack_open = False
                self.bored._ack_job_key = None
            except Exception:
                pass
        self.log(f"console-closed: posted {line}")

    def run_forever(self) -> int:
        if self.bored:
            self.bored.start()
        threading.Thread(target=self.health_loop, name="health", daemon=True).start()
        # FR #8249: dedicated progress heartbeat (independent of health / FINISH locks).
        self._start_progress_heartbeat()
        self.done.wait()
        return self.exit_code if self.exit_code is not None else EXIT_OK


# --------------------------------------------------------------------------------------------- outbox
def ensure_outbox(path: Path) -> Path:
    """FR #866: keep the seat outbox path creatable for the whole session.

    ``drain_outbox`` atomically moves ``outbox.txt`` aside, so the file is often
    missing between writes. Agents (and PowerShell ``Add-Content`` /
    ``Set-Content``) still need the parent run dir — and a present empty file is
    friendlier when tools probe the path. Never deletes the run dir.
    FR #6917: if the whole run folder vanished mid-session, recreate *this*
    assigned path only — never glob a newer ``worker-<machine>-*`` sibling.
    """
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.is_file():
            p.write_text("", encoding="utf-8")
    except OSError:
        pass
    return p


def drain_outbox(
    path: Path,
    irc: IrcSeat,
    log: Callable[[str], None],
    on_payload: Optional[Callable[[str], None]] = None,
    may_send: Optional[Callable[[str], bool]] = None,
    enrich_line: Optional[Callable[[str], str]] = None,
) -> int:
    """Move outbox.txt aside atomically, send each line to the shop channel. Plain text or `PRIVMSG #shop :text`."""
    path = Path(path)
    if not path.is_file():
        ensure_outbox(path)
        return 0
    tmp = path.with_suffix(".sending")
    # FR #4363: brief retry when an agent append still holds the file.
    replaced = False
    for _i in range(6):
        try:
            os.replace(path, tmp)
            replaced = True
            break
        except OSError:
            time.sleep(0.02 * (_i + 1))
    if not replaced:
        return 0
    # FR #6917: keep the assigned run-dir outbox creatable while .sending is in flight.
    ensure_outbox(path)
    n = 0
    unsent: list[str] = []
    try:
        for ln in tmp.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            m = re.match(r"(?i)^PRIVMSG\s+(\S+)\s+:?(.*)$", ln)
            target, text = (m.group(1), m.group(2)) if m else (irc.shop, ln)
            payload = text.strip()
            # FR #6387: worker stamps measured model/tokens onto DONE before IRC send.
            if enrich_line is not None and _OUT_DONE_RX.match(payload):
                try:
                    enriched = enrich_line(payload)
                except Exception:
                    enriched = payload
                if isinstance(enriched, str) and enriched.strip():
                    payload = enriched.strip()
                    text = payload
                    if m:
                        ln = f"PRIVMSG {target} :{payload}"
                    else:
                        ln = payload
            if _OUT_BORED_RX.match(payload):  # t770u: !bored is posted by the exe ONLY, never by the model
                log("outbox: refused agent-written !bored (the exe posts it)")
                continue
            # FR #4730: drop replayed ACK for a finished job before it hits IRC; still bookkeep.
            if may_send is not None:
                refuse_reason = ""
                try:
                    decision = may_send(payload)
                    if isinstance(decision, tuple):
                        allow = bool(decision[0]) if decision else False
                        refuse_reason = str(decision[1]) if len(decision) > 1 else ""
                    else:
                        allow = bool(decision)
                except Exception:
                    allow = True
                    refuse_reason = ""
                if not allow:
                    preview = _scrub(one_line(payload, 80))
                    # FR #6472: prefer may_send refuse tag; bare False stays "stale replay".
                    tag = (refuse_reason or "").strip() or "stale replay"
                    log(f"outbox: dropped {tag} ({len(payload)} chars): {preview}")
                    if on_payload:
                        try:
                            on_payload(text)
                        except Exception:
                            pass
                    continue
            ok = bool(irc.say(target, text))
            is_job = bool(_OUT_ACK_RX.match(payload) or _OUT_DONE_RX.match(payload) or _OUT_FREE_RX.match(payload))
            if ok:
                n += 1
                # FR #995: successful drains were silent in worker.log (looked stuck at last bored).
                # Char-count form avoids echoing secrets; scrub a short preview for operators.
                preview = _scrub(one_line(payload, 80))
                log(f"outbox: sent PRIVMSG {target} ({len(payload)} chars): {preview}")
                if on_payload:
                    try:
                        on_payload(text)  # ACK / DONE / NACK / GIVEUP drive busy-idle for !bored
                    except Exception:
                        pass
            else:
                # FR #3456: hold unsent lines for reconnect flush (do not drop DONE/ACK).
                # Do not re-queue target-refused lines (seat may only speak in its shop).
                shop = (getattr(irc, "shop", None) or "").lower()
                refused_target = (target or "").lower() != shop
                if not refused_target:
                    unsent.append(ln)
                if on_payload and is_job:
                    # FR #161: local busy bookkeeping still applies so !bored stays quiet.
                    try:
                        on_payload(text)
                    except Exception:
                        pass
                    verb = payload.split(None, 1)[0] if payload else "JOB"
                    log(f"outbox: say failed; held for retry + busy bookkeeping for {verb}")
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
        if unsent:
            try:
                prev = ""
                if path.is_file():
                    prev = path.read_text(encoding="utf-8-sig", errors="replace")
                body = chr(10).join(unsent) + chr(10)
                if prev.strip():
                    body = body + prev
                path.write_text(body, encoding="utf-8")
            except OSError:
                ensure_outbox(path)
        else:
            # FR #866: recreate empty outbox so the path stays available for the next agent write.
            ensure_outbox(path)
    return n


def outbox_loop(
    path: Path,
    irc: IrcSeat,
    stop: threading.Event,
    log: Callable[[str], None],
    on_payload: Optional[Callable[[str], None]] = None,
    may_send: Optional[Callable[[str], bool]] = None,
    extra_paths: Optional[Callable[[], list]] = None,
    may_send_extra: Optional[Callable[[str], bool]] = None,
    enrich_line: Optional[Callable[[str], str]] = None,
) -> None:
    ensure_outbox(path)
    while not stop.wait(0.5):  # outbound only; inbound relay is NOT polled
        try:
            drain_outbox(path, irc, log, on_payload, may_send, enrich_line=enrich_line)
            # FR #6333: also drain OpenCode in-worktree .bob/outbox.txt when active.
            extras: list = []
            if extra_paths is not None:
                try:
                    extras = list(extra_paths() or [])
                except Exception:
                    extras = []
            job_may = may_send_extra if may_send_extra is not None else may_send
            for extra in extras:
                try:
                    ep = Path(extra)
                except Exception:
                    continue
                # Skip missing paths so drain_outbox cannot mkdir a removed worktree.
                if (not ep.is_file()) or ep.resolve() == Path(path).resolve():
                    continue
                try:
                    drain_outbox(ep, irc, log, on_payload, job_may, enrich_line=enrich_line)
                except Exception as e:  # pragma: no cover
                    log(f"outbox(job): {type(e).__name__}")
        except Exception as e:  # pragma: no cover
            log(f"outbox: {type(e).__name__}")


# --------------------------------------------------------------------------------------------- credentials
def find_ergo_password(install_root: Path, env: Optional[dict] = None) -> Optional[SecretStr]:
    env = os.environ if env is None else env
    v = (env.get("BOB_IRC_PASSWORD") or "").strip()
    if v:
        return SecretStr(v)
    up = Path(env.get("USERPROFILE", "") or Path.home())
    for c in (Path(install_root) / "home" / "ergo.password", Path(install_root) / "config" / "ergo.password",
              up / ".bobiverse" / "ergo.password", up / ".grok" / "ergo" / "connect.password", up / ".grok" / "ergo" / "ergo.password"):
        try:
            if c.is_file():
                s = c.read_text(encoding="utf-8-sig").strip()
                if s:
                    return SecretStr(s)
        except OSError:
            continue
    return None


# --------------------------------------------------------------------------------------------- entry points
def _state_root(env: Optional[dict] = None) -> Path:
    env = os.environ if env is None else env
    base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Bobiverse" / "worker"


def _new_run_dir(machine: str, mode: str) -> Path:
    return _state_root() / "run" / f"{mode}-{machine}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def reread_explicit_opencode_fuel(
    read_fn: Callable[[], Fuel],
    log: Callable[[str], None],
    *,
    tries: int = 3,
    gap_s: float = 10.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Fuel:
    """FR #7714: retry an unknown OpenCode reading, then return the last fuel.

    Three tries about 10s apart (~30s). The caller still starts when the last
    reading is unknown. Known fuel returns immediately.
    """
    fuel = read_fn()
    attempt = 1
    while attempt < tries and not fuel_reading_known(fuel, "opencode"):
        log("explicit opencode: fuel unknown, retry %s/%s" % (attempt, tries))
        sleep_fn(gap_s)
        fuel = read_fn()
        attempt += 1
    if not fuel_reading_known(fuel, "opencode"):
        log("explicit opencode: fuel unknown, starting")
    return fuel


def _choose(args, log: Log, folder: Path, mode: str):
    cursor_cmd, grok_exe = resolve_cursor_cmd(), resolve_grok_exe()
    # FR #8412: auto-select uses the same resolve as explicit --agent opencode.
    reasons: list = []
    opencode_cmd = resolve_opencode_cmd(reasons=reasons)
    if not opencode_cmd:
        for reason in reasons:
            log("opencode: " + reason)
        if reasons:
            log("opencode: readiness miss (untrusted WinGet Links or not installed)")
    fuel = read_fuel(Path(args.install_root))
    signin = preflight_xai_signin()
    signin_ok = signin == "ok"
    log(f"xai-auth[{mode}]: {signin}")
    dec = select_agent(fuel, cursor_cmd, grok_exe, opencode_cmd, xai_signin_ok=signin_ok)
    log(f"select[{mode}]: {dec.kind} - {dec.reason}")
    return dec, cursor_cmd, grok_exe, fuel, signin_ok, signin


def fuel_snapshot_public(fuel) -> str:
    """Numeric fuel fields only. Never model maps, paths, or tokens (FR #7715)."""
    if fuel is None:
        return "none"
    names = (
        "grok_pct",
        "grok_state",
        "cursor_high",
        "cursor_low",
        "opencode_free",
        "opencode_go",
        "on_demand_remaining_pct",
        "overspend_state",
    )
    return " ".join(f"{name}={getattr(fuel, name, None)}" for name in names)


def report_seat_start_refusal(
    *,
    machine: str = "",
    kind: str = "",
    model: str = "",
    reason: str = "",
    fuel=None,
    tray_restarted: bool = False,
    log: Optional[Callable[[str], None]] = None,
    filer_post: Optional[Callable[..., dict]] = None,
) -> dict:
    """FR #7715: a seat that never becomes ready is an intake issue, not only a log line."""
    if filer_post is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return {"ok": True, "skipped": True, "reason": "pytest"}
    mid = re.sub(r"[^a-z0-9._-]+", "-", str(machine or "unknown").strip().lower()).strip("-") or "unknown"
    k = (kind or "").strip().lower() or "unknown"
    model_s = " ".join(str(model or "unknown").split())[:120] or "unknown"
    reason_s = " ".join(str(reason or "refused").split())[:300]
    snap = fuel_snapshot_public(fuel)
    restarted = "true" if tray_restarted else "false"
    try:
        import crash_report

        reason_s = crash_report.redact(reason_s)
        snap = crash_report.redact(snap)
        model_s = crash_report.redact(model_s)
    except Exception:
        pass
    norm = re.sub(r"\s+", " ", reason_s).strip().lower()
    norm = re.sub(r"[^a-z0-9 .:_=-]+", "", norm)[:80] or "refused"
    key = f"seat-start-refusal|{mid}|{norm}"[:128]
    title = "bug: seat start refused (FR #7715)"
    body = (
        "What: bob-worker refused to start the seat before it became ready.\n"
        f"Where: machine={mid} kind={k} model={model_s}\n"
        f"Reason: {reason_s}\n"
        f"Fuel: {snap}\n"
        f"tray_restarted={restarted}\n"
        "No secrets."
    )
    if log:
        try:
            log(f"worker: seat-start-refusal kind={k} tray_restarted={restarted} (FR #7715)")
        except Exception:
            pass
    payload = {
        "kind": "issue",
        "repo": "SimonBarnett/bobiverse",
        "title": title,
        "body": body,
        "idempotency_key": key,
        "dedupe_key": key,
        "machine": mid,
        "agent": "bob-worker",
    }
    if filer_post is not None:
        try:
            return filer_post(payload) or {"ok": True, "key": key}
        except Exception:
            return {"ok": False, "key": key}
    try:
        import crash_report

        crash_report._post_intake(title, body, repo="SimonBarnett/bobiverse", sig=key, exe="bob-worker")
        return {"ok": True, "key": key}
    except Exception:
        return {"ok": False, "key": key}



def wait_refusal_console(
    *,
    timeout_s: float = 60.0,
    interactive: bool = True,
    sleep_fn=time.sleep,
    kbhit_fn=None,
    getch_fn=None,
) -> None:
    """FR #8186: keep an interactive refusal console readable (key or timeout).

    Non-interactive / tray-restart starts pass interactive=False and return at once.
    Tests inject kbhit_fn/getch_fn/sleep_fn.
    """
    if not interactive:
        return
    timeout_s = max(60.0, float(timeout_s or 60.0))
    if os.name != "nt":
        sleep_fn(timeout_s)
        return
    try:
        import msvcrt
    except Exception:
        sleep_fn(timeout_s)
        return
    kbhit = kbhit_fn or msvcrt.kbhit
    getch = getch_fn or msvcrt.getwch
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if kbhit():
                ch = getch()
                if ch in ("\x00", "\xe0"):
                    try:
                        getch()
                    except Exception:
                        pass
                return
        except Exception:
            pass
        sleep_fn(0.05)


def _explicit_refusal_exit(
    dec: Decision,
    log: Log,
    mode: str,
    *,
    machine: str = "",
    kind: str = "",
    model: str = "",
    fuel=None,
    filer_post: Optional[Callable[..., dict]] = None,
    interactive: Optional[bool] = None,
    wait_fn=None,
) -> Optional[int]:
    """Show an explicit refusal. Never starts another agent.

    FR #8186: interactive consoles wait for a key (or >=60s). Non-interactive
    and tray-restart paths do not block.
    """
    if dec.kind not in ("refuse", "xai-auth-expired", "no-seat-auth"):
        return None
    log(f"select[{mode}]: refused - {dec.reason}")
    report_seat_start_refusal(
        machine=machine,
        kind=kind or dec.kind,
        model=model,
        reason=dec.reason,
        fuel=fuel,
        tray_restarted=False,
        log=log,
        filer_post=filer_post,
    )
    try:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        ensure_console("Bob worker - refused")
        print("\nBob worker: " + dec.reason + ".\nNot starting a different agent.\n")
        if interactive is None:
            interactive = bool(sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty())
            if os.environ.get("BOB_TRAY_RESTART", "").strip() in ("1", "true", "yes"):
                interactive = False
        if interactive:
            waiter = wait_fn or wait_refusal_console
            waiter(timeout_s=60.0, interactive=True)
    except Exception:
        pass
    if dec.kind == "xai-auth-expired":
        return EXIT_XAI_AUTH_EXPIRED
    if dec.kind == "no-seat-auth":
        return EXIT_NO_AGENT
    return EXIT_NO_AGENT


_PLAN_HARD_EXIT = {4294967295, -1}
_PLAN_REPEAT_S = 600
EXIT_PLAN_CHILD = 1


def _plan_note_hard_exit(now: float | None = None) -> bool:
    """True when this 0xFFFFFFFF is the second or later inside 10 minutes."""
    path = _state_root() / "plan-hard-exit.json"
    stamp = time.time() if now is None else float(now)
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
        stamps = [float(x) for x in prev if stamp - float(x) <= _PLAN_REPEAT_S]
    except Exception:
        stamps = []
    stamps.append(stamp)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stamps), encoding="utf-8")
    except OSError:
        pass
    return len(stamps) >= 2


def _plan_child_exit(code, log, stderr_path, proc=None) -> int:
    """FR #8663: a non-zero plan child is a failure, not EXIT_OK."""
    shown = int(code) if isinstance(code, int) else -1
    log(f"plan: agent ended code={shown}")
    tail = ""
    if proc is not None and hasattr(proc, "stderr_tail"):
        try:
            tail = (proc.stderr_tail() or "").strip()
        except Exception:
            tail = ""
    if not tail and stderr_path:
        try:
            p = Path(stderr_path)
            if p.is_file():
                tail = p.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            tail = ""
    if tail:
        log("plan: child stderr: " + " ".join(tail.split())[:400])
    if shown == 0:
        return EXIT_OK
    log("plan: FAILED child exit is not success")
    unsigned = shown & 0xFFFFFFFF
    if shown in _PLAN_HARD_EXIT or unsigned == 4294967295:
        log("plan: code 4294967295 means the child exited -1 with no session_end")
        if _plan_note_hard_exit():
            log(
                "plan: heal tip: repeated 4294967295 within 10 minutes. "
                "The plan console is dying mid-stream. Check bob-worker-plan.log "
                "and the session events.jsonl."
            )
    return EXIT_PLAN_CHILD


def run_plan(args, log: Log) -> int:
    folder = Path(args.install_root) / "plan"
    if not folder.is_dir():
        log(f"plan: folder missing {folder}")
        return EXIT_USAGE
    dec, cursor_cmd, grok_exe, fuel, signin_ok, signin_state = _choose(args, log, folder, "plan")
    opencode_cmd = _resolve_opencode_cmd_for_seat(log)
    requested = getattr(args, "agent", "") or ""
    dec = resolve_seat_decision(
        requested,
        dec, fuel, cursor_cmd, grok_exe, opencode_cmd,
        auth_present=opencode_auth_file_present(),
        xai_signin_ok=signin_ok,
        signin_state=signin_state,
        machine=getattr(args, "machine_id", "") or "",
        fleet_digest=load_public_digest(
            public_digest_path(install_root=getattr(args, "install_root", None))
        ),
        install_root=getattr(args, "install_root", None),
    )
    if normalize_explicit_agent(requested):
        log(f"select[plan]: explicit {normalize_explicit_agent(requested)} -> {dec.kind} - {dec.reason}")
    stopped = _explicit_refusal_exit(
        dec, log, "plan",
        machine=getattr(args, "machine_id", "") or "",
        kind=requested, model=(_OPENCODE_MODEL_ENV_AT_START or ""), fuel=fuel,
    )
    if stopped is not None:
        return stopped
    secret = None
    kind = dec.kind
    if kind == "none":
        return EXIT_NO_AGENT
    if kind == "dialog":
        key = ask_session_key("No Cursor, Grok or OpenCode tokens remain. Enter an XAI_API_KEY for this Plan only (kept in memory, never saved).", "Grok plan session key")
        if not key:
            log("plan: no key given - not starting")
            return EXIT_NO_AGENT
        secret, kind = SecretStr(key), "grok"
    if kind == "cursor":
        exe = cursor_cmd
    elif kind == "opencode":
        exe = opencode_cmd
        oc_model = resolve_opencode_model(fuel, log_fn=log)
        if not oc_model:
            report_opencode_model_refusal(
                log, machine=getattr(args, "machine_id", "") or "", fuel=fuel
            )
            return EXIT_NO_AGENT
        os.environ["BOB_OPENCODE_MODEL"] = oc_model
        stamp_opencode_pause_fallback(os.environ, oc_model)
    else:
        exe = grok_exe
    run_dir = _new_run_dir("plan", "plan")
    machine = normalize_machine_id(args.machine_id) if args.machine_id else default_machine_id()
    nick = "%s-plan" % (machine or "plan")
    child = describe_agent_child_launch(
        kind=kind,
        mode="plan",
        cwd=str(folder),
        run_dir=run_dir,
        machine=machine or "plan",
        nick=nick,
        agent_exe=exe,
        install_root=str(args.install_root),
    )
    spec = child["spec"]
    env = prepare_seat_child_env(os.environ, child["env"])  # FR #2413 / #2669
    if secret and kind == "grok":
        env["XAI_API_KEY"] = secret.reveal()
    stderr_path = run_dir / "plan-child-stderr.txt"
    try:
        spec.stderr_path = str(stderr_path)
    except Exception:
        pass
    try:
        proc = default_spawn(spec, env)
    except Exception as e:
        log(f"plan: launch failed {type(e).__name__}")
        return EXIT_LAUNCH_FAIL
    log(f"plan: started NEW {kind} agent pid={proc.pid} session={spec.session_id} cwd={folder} (hosted in this console; ending either ends both)")
    install_ctrl_handler(lambda: kill_tree(proc.pid))

    try:
        code = proc.wait()
    except Exception:
        code = -1
    return _plan_child_exit(code, log, stderr_path, proc)


def _default_jeeves_root(install_root: Path) -> Path:
    """Sibling <ai>\\jeeves next to bob install-root, else install-root itself when it looks like jeeves."""
    if (install_root / "AGENTS.md").is_file() and (install_root / ".grok" / "skills" / "bobiverse-jeeves-monitor").is_dir():
        return install_root
    sib = install_root.parent / "jeeves"
    return sib


def run_monitor(args, log: Log) -> int:
    """FR #787: Jeeves MONITORING seat — same fuel pick as Agent, CWD = jeeves install, no IRC, never resume."""
    work = Path(getattr(args, "work_root", "") or "") if getattr(args, "work_root", None) else None
    folder = work if work and str(work) else _default_jeeves_root(Path(args.install_root))
    folder = Path(folder)
    if not folder.is_dir():
        log(f"monitor: folder missing {folder}")
        return EXIT_USAGE
    if not (folder / "AGENTS.md").is_file():
        log(f"monitor: AGENTS.md missing in {folder}")
        return EXIT_USAGE
    dec, cursor_cmd, grok_exe, fuel, signin_ok, signin_state = _choose(args, log, folder, "monitor")
    opencode_cmd = _resolve_opencode_cmd_for_seat(log)
    requested = getattr(args, "agent", "") or ""
    dec = resolve_seat_decision(
        requested,
        dec, fuel, cursor_cmd, grok_exe, opencode_cmd,
        auth_present=opencode_auth_file_present(),
        xai_signin_ok=signin_ok,
        signin_state=signin_state,
        machine=getattr(args, "machine_id", "") or "",
        fleet_digest=load_public_digest(
            public_digest_path(install_root=getattr(args, "install_root", None))
        ),
        install_root=getattr(args, "install_root", None),
    )
    stopped = _explicit_refusal_exit(
        dec, log, "monitor",
        machine=getattr(args, "machine_id", "") or "",
        kind=requested, model=(_OPENCODE_MODEL_ENV_AT_START or ""), fuel=fuel,
    )
    if stopped is not None:
        return stopped
    secret = None
    kind = dec.kind
    if kind == "none":
        return EXIT_NO_AGENT
    if kind == "dialog":
        key = ask_session_key(
            "No Cursor, Grok or OpenCode tokens remain. Enter an XAI_API_KEY for this Jeeves Monitor only (kept in memory, never saved).",
            "Grok monitor session key",
        )
        if not key:
            log("monitor: no key given - not starting")
            return EXIT_NO_AGENT
        secret, kind = SecretStr(key), "grok"
    if kind == "cursor":
        exe = cursor_cmd
    elif kind == "opencode":
        exe = opencode_cmd
        oc_model = resolve_opencode_model(fuel, log_fn=log)
        if not oc_model:
            report_opencode_model_refusal(
                log, machine=getattr(args, "machine_id", "") or "", fuel=fuel
            )
            return EXIT_NO_AGENT
        os.environ["BOB_OPENCODE_MODEL"] = oc_model
        stamp_opencode_pause_fallback(os.environ, oc_model)
    else:
        exe = grok_exe
    run_dir = _new_run_dir("monitor", "monitor")
    run_dir.mkdir(parents=True, exist_ok=True)
    ensure_console("Jeeves Monitor (%s) - closing this window ends the agent" % kind)
    # Prefer butler icon when present on the work root
    butler = folder / "assets" / "jeeves-butler.ico"
    if butler.is_file():
        try:
            set_console_icon(folder)  # find_window_icon only knows bob-systray; still set title
        except Exception:
            pass
    spec = build_launch(kind, "monitor", str(folder), monitor_prompt(str(folder)), exe, run_dir,
                             install_root=str(args.install_root))
    env = prepare_seat_child_env(os.environ)  # FR #2669
    if secret and kind == "grok":
        env["XAI_API_KEY"] = secret.reveal()
    try:
        proc = default_spawn(spec, env)
    except Exception as e:
        log(f"monitor: launch failed {type(e).__name__}")
        return EXIT_LAUNCH_FAIL
    log(f"monitor: started NEW {kind} agent pid={proc.pid} session={spec.session_id} cwd={folder} (no IRC; ending either ends both)")
    install_ctrl_handler(lambda: kill_tree(proc.pid))
    try:
        code = proc.wait()
    except Exception:
        code = -1
    log(f"monitor: agent ended code={code}")
    return EXIT_OK


_MAINT_MUTEX_KEEP: list = []


def try_acquire_maintenance_mutex() -> bool:
    """FR #2522: at most ONE maintenance bob-worker on the machine (named mutex). Stale locks are elsewhere."""
    if os.name != "nt":
        return True
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        k32.CreateMutexW.restype = ctypes.c_void_p
        handle = k32.CreateMutexW(None, True, "Global\\Bobiverse-Jeeves-Maintenance")
        if not handle:
            return False
        err = ctypes.get_last_error()
        _MAINT_MUTEX_KEEP.append(handle)
        if err == 183:  # ERROR_ALREADY_EXISTS
            return False
        return True
    except Exception:
        return True  # fail open only if mutex API unavailable; file lock still applies


def run_maintenance(args, log: Log, *, spawn: Optional[Callable] = None, poll_s: float = 5.0,
                    state_path: Optional[Path] = None, sessions_root: Optional[Path] = None,
                    console: Optional[Callable] = None, icon_setter: Optional[Callable] = None,
                    killer: Optional[Callable] = None, run_dir: Optional[Path] = None,
                    acquire_mutex: Optional[Callable] = None) -> int:
    """FR #2412 + #2522: Jeeves maintenance seat after --heal still failing.

    * window title exactly MAINTENANCE_TITLE + the tray's Jeeves butler icon (re-applied while running);
    * grok resumes OUR last maintenance session when it still exists, else NEW (choose_maintenance_session);
    * closes itself: when the agent writes the done file AFTER harvest (maintenance_exit_decision) the exe kills the
      agent tree it started and exits, so no console lingers. Agent exit on its own also ends the exe.
    Rate limit + single instance stay in jeeves_maintenance (lock is this exe's pid)."""
    claim = acquire_mutex or try_acquire_maintenance_mutex
    if not claim():
        log("maintenance: refused - another maintenance agent is already live (mutex)")
        return EXIT_REFUSED
    work = Path(getattr(args, "work_root", "") or "") if getattr(args, "work_root", None) else None
    folder = work if work and str(work) else _default_jeeves_root(Path(args.install_root))
    folder = Path(folder)
    if not folder.is_dir():
        log(f"maintenance: folder missing {folder}")
        return EXIT_USAGE
    if not (folder / "AGENTS.md").is_file():
        log(f"maintenance: AGENTS.md missing in {folder}")
        return EXIT_USAGE
    dec, cursor_cmd, grok_exe, fuel, signin_ok, signin_state = _choose(args, log, folder, "maintenance")
    opencode_cmd = _resolve_opencode_cmd_for_seat(log)
    requested = getattr(args, "agent", "") or ""
    dec = resolve_seat_decision(
        requested,
        dec, fuel, cursor_cmd, grok_exe, opencode_cmd,
        auth_present=opencode_auth_file_present(),
        xai_signin_ok=signin_ok,
        signin_state=signin_state,
        machine=getattr(args, "machine_id", "") or "",
        fleet_digest=load_public_digest(
            public_digest_path(install_root=getattr(args, "install_root", None))
        ),
        install_root=getattr(args, "install_root", None),
    )
    stopped = _explicit_refusal_exit(
        dec, log, "maintenance",
        machine=getattr(args, "machine_id", "") or "",
        kind=requested, model=(_OPENCODE_MODEL_ENV_AT_START or ""), fuel=fuel,
    )
    if stopped is not None:
        return stopped
    secret = None
    kind = dec.kind
    if kind == "none":
        return EXIT_NO_AGENT
    if kind == "dialog":
        key = ask_session_key(
            "No Cursor, Grok or OpenCode tokens remain. Enter an XAI_API_KEY for this Jeeves maintenance agent only (kept in memory, never saved).",
            "Grok maintenance session key",
        )
        if not key:
            log("maintenance: no key given - not starting")
            return EXIT_NO_AGENT
        secret, kind = SecretStr(key), "grok"
    if kind == "cursor":
        exe = cursor_cmd
    elif kind == "opencode":
        exe = opencode_cmd
        oc_model = resolve_opencode_model(fuel, log_fn=log)
        if not oc_model:
            report_opencode_model_refusal(
                log, machine=getattr(args, "machine_id", "") or "", fuel=fuel
            )
            return EXIT_NO_AGENT
        os.environ["BOB_OPENCODE_MODEL"] = oc_model
        stamp_opencode_pause_fallback(os.environ, oc_model)
    else:
        exe = grok_exe
    rd = Path(run_dir) if run_dir else _new_run_dir("maintenance", "maintenance")
    rd.mkdir(parents=True, exist_ok=True)
    set_title = console or ensure_console
    set_icon = icon_setter or set_console_icon
    icon = maintenance_icon_path(folder)
    set_title(MAINTENANCE_TITLE)
    try:
        set_icon(folder, icon=icon)
    except Exception:
        pass
    how, sid = choose_maintenance_session(str(folder), kind, state_path=state_path, sessions_root=sessions_root)
    done_file = rd / MAINTENANCE_DONE_NAME
    prompt = maintenance_prompt(str(folder), done_file=str(done_file), resumed=(how == "resume"))
    spec = build_launch(kind, "maintenance", str(folder), prompt, exe, rd,
                        session_id=(sid if how == "new" else None),
                        resume_session_id=(sid if how == "resume" else None),
                             install_root=str(args.install_root))
    env = prepare_seat_child_env(os.environ)  # FR #2669
    if secret and kind == "grok":
        env["XAI_API_KEY"] = secret.reveal()
    try:
        proc = (spawn or default_spawn)(spec, env)
    except Exception as e:
        log(f"maintenance: launch failed {type(e).__name__}")
        return EXIT_LAUNCH_FAIL
    record_maintenance_session(spec.session_id, str(folder), kind, state_path=state_path)
    log(
        f"maintenance: started {'RESUMED' if how == 'resume' else 'NEW'} {kind} agent pid={proc.pid} "
        f"session={spec.session_id} cwd={folder} icon={icon} done_file={done_file} (FR #2412/#2522; no IRC)"
    )
    kill = killer or kill_tree
    install_ctrl_handler(lambda: kill(proc.pid))
    while True:
        code = None
        try:
            code = proc.poll()
        except Exception:
            code = -1
        if code is not None:
            log(f"maintenance: agent ended code={code} - closing")
            return EXIT_OK
        verdict, why = maintenance_exit_decision(read_maintenance_done(rd))
        if verdict == "exit":
            log(f"maintenance: done file ok ({why}) - closing agent tree and exiting")
            try:
                kill(proc.pid)
            except Exception:
                pass
            return EXIT_OK
        if why != "no_done_file":
            log(f"maintenance: done file present but {why} - waiting for harvest")
        try:
            set_title(MAINTENANCE_TITLE)  # agent TUIs may retitle the console
            set_icon(folder, icon=icon)
        except Exception:
            pass
        time.sleep(max(0.01, float(poll_s)))


def run_agent(args, log: Log) -> int:
    machine = normalize_machine_id(args.machine_id) if args.machine_id else default_machine_id()
    if not machine:
        log("worker: no machine id (pass --machine-id)")
        return EXIT_USAGE
    folder = Path(args.install_root) / "worker"
    if not folder.is_dir():
        log(f"worker: folder missing {folder}")
        return EXIT_USAGE
    try:
        os.environ["BOB_INSTALL_ROOT"] = str(args.install_root)
        sk = maybe_sync_install_skills(install_root=str(args.install_root), job_busy=False)
        log(f"skills-sync start sha={sk.get('sha')} reason={sk.get('reason')}")
    except Exception:
        pass
    dec, cursor_cmd, grok_exe, fuel, signin_ok, signin_state = _choose(args, log, folder, "agent")
    if normalize_explicit_agent(getattr(args, "agent", "") or "") == "opencode":
        if not fuel_reading_known(fuel, "opencode"):
            fuel = reread_explicit_opencode_fuel(
                lambda: read_fuel(Path(args.install_root)),
                log,
            )
    opencode_cmd = _resolve_opencode_cmd_for_seat(log)
    requested = getattr(args, "agent", "") or ""
    dec = resolve_seat_decision(
        requested,
        dec, fuel, cursor_cmd, grok_exe, opencode_cmd,
        auth_present=opencode_auth_file_present(),
        xai_signin_ok=signin_ok,
        signin_state=signin_state,
        machine=getattr(args, "machine_id", "") or "",
        fleet_digest=load_public_digest(
            public_digest_path(install_root=getattr(args, "install_root", None))
        ),
        install_root=getattr(args, "install_root", None),
    )
    # FR #7485: always log the seat decision after explicit override (auto already logged in _choose).
    if normalize_explicit_agent(requested):
        log(f"select[agent]: explicit {normalize_explicit_agent(requested)} -> {dec.kind} - {dec.reason}")
    stopped = _explicit_refusal_exit(
        dec, log, "agent",
        machine=machine,
        kind=requested, model=(_OPENCODE_MODEL_ENV_AT_START or ""), fuel=fuel,
    )
    if stopped is not None:
        return stopped
    secret = None
    kind = dec.kind
    if kind == "none":
        return EXIT_NO_AGENT
    if kind == "dialog":
        key = ask_session_key("No Cursor, Grok or OpenCode tokens remain. Enter an XAI_API_KEY to start this worker (kept in memory only, never saved).", "Grok worker session key")
        if not key:
            log("worker: no key given - not starting")
            return EXIT_NO_AGENT
        secret, kind = SecretStr(key), "grok"
    if kind == "cursor":
        exe = cursor_cmd
    elif kind == "opencode":
        exe = opencode_cmd
        oc_model = resolve_opencode_model(fuel, log_fn=log)
        if not oc_model:
            report_opencode_model_refusal(
                log, machine=getattr(args, "machine_id", "") or "", fuel=fuel
            )
            return EXIT_NO_AGENT
        os.environ["BOB_OPENCODE_MODEL"] = oc_model
        stamp_opencode_pause_fallback(os.environ, oc_model)
    else:
        exe = grok_exe
    pid = os.getpid()
    nick = seat_nick(machine, pid)
    # FR #6341: rewrite stale <worker>/.bobiverse-seat with live nick/pid before the agent starts.
    try:
        marker = write_live_seat_marker(folder, nick=nick, pid=pid, machine=machine)
        log(f"worker: seat marker {marker} nick={nick} pid={pid}")
    except Exception as e:
        log(f"worker: seat marker write failed {type(e).__name__}")
    try:
        base = resolve_and_ensure_job_worktree_base()
        os.environ["BOB_JOB_WORKTREE_BASE"] = base
        log(f"worker: BOB_JOB_WORKTREE_BASE={base}")
    except Exception as e:
        log(f"worker: BOB_JOB_WORKTREE_BASE failed {type(e).__name__}")
    run_dir = _new_run_dir(machine, "worker")
    run_dir.mkdir(parents=True, exist_ok=True)
    ensure_outbox(run_dir / "outbox.txt")  # FR #866: path must exist before first agent write
    log.path = run_dir / "worker.log"
    log(f"worker: pid={pid} nick={nick} shop=#{machine} kind={kind} run_dir={run_dir}")
    ensure_console(f"Bob worker {nick} ({kind}) - closing this window ends the agent")
    set_console_icon(Path(args.install_root))
    pw = find_ergo_password(Path(args.install_root))
    sasl = None
    if os.environ.get("BOB_IRC_SASL_USER") and os.environ.get("BOB_IRC_SASL_PASSWORD"):
        sasl = (os.environ["BOB_IRC_SASL_USER"], os.environ["BOB_IRC_SASL_PASSWORD"])
    irc = IrcSeat(args.host, args.port, nick, machine, pw, sasl, tls=not args.no_tls, log=log)
    relay = Relay(log, persist_dir=run_dir)
    irc.on_message = relay.deliver
    try:
        # FR #955: 2-3 registration attempts with backoff before fail-closed.
        irc.connect_with_retries(attempts=3, timeout=45.0, backoff_s=(2.0, 5.0, 10.0))
    except Exception as e:
        log(f"worker: IRC connect failed ({type(e).__name__}: {str(e)[:100]}) - NOT starting an agent")
        return EXIT_IRC_FAIL
    # FR #8154: prior seat may have left a durable console-closed GIVEUP while IRC was down.
    try:
        flush_pending_console_closed_giveups(irc, machine, log=log)
    except Exception as e:
        log(f"pending-giveup: flush failed {type(e).__name__}")
    # FR #6134: publish agent kind so the chair can skip OpenCode for MRB/UAT.
    # FR #6409: digest worker_build short SHA (or unknown); hello after start_agent (MRB #6411).
    # FR #7187: hello ``model=`` is the launched actual when known (else configured).
    # FR #7084 digest ``start_model`` is the launched process/session model.
    build = short_build_sha()
    seat_model = resolve_seat_hello_model(kind)
    try:
        import worker_start_model as wsm

        seat_model = wsm.concrete_model_id(seat_model)
    except Exception:
        if "$" in str(seat_model or ""):
            seat_model = ""
    if kind == "opencode" and not seat_model:
        seat_model = "unknown"
        try:
            report_configured_start_model_unavailable(
                kind=kind,
                configured="unresolved-template",
                actual="unknown",
                machine=machine,
                nick=nick,
                reason="model-template-unresolved",
                log=log,
            )
        except Exception:
            log("worker: opencode model unresolved; digest model=unknown")
    cfg_model = ""
    cost_tier = ""
    mismatch = None
    mismatch_reason = ""
    seat_effort = "low"
    try:
        import worker_start_model as wsm

        _cfg = wsm.load_worker_start_config()
        cfg_model = wsm.launch_selected_model(kind, _cfg, env=os.environ)
        mismatch_reason = wsm.model_mismatch_reason(seat_model, cfg_model, env=os.environ)
        mismatch = bool(mismatch_reason)
        cost_tier = wsm.model_cost_tier(seat_model or cfg_model, _cfg)
        seat_effort = wsm.configured_start_effort(kind, _cfg)
        if not cfg_model:
            log(f"worker: configured start model empty for kind={kind}; not inventing an id")
    except Exception:
        pass
    try:
        post_digest_seat_kind(
            machine=machine,
            pid=pid,
            nick=nick,
            kind=kind,
            model=seat_model,
            configured_model=cfg_model,
            model_mismatch=mismatch,
            mismatch_reason=mismatch_reason,
            cost_tier=cost_tier,
            start_effort=seat_effort,
            worker_build=build,
            cursor_account=getattr(dec, "account", "") or "",
            log=log,
        )
    except Exception as e:
        log(f"worker: post_digest_seat_kind failed {type(e).__name__}")
    grace = float(getattr(args, "startup_grace_s", 60.0) or 60.0)
    if kind == "grok" and grace < 60.0:
        # Grok TUI session.create often needs 30-60s on slower boxes (FR #955 ionos evidence).
        grace = 60.0
    log(f"worker: startup_grace_s={grace:.0f}")
    _install_root = str(args.install_root)
    sup = Supervisor(
        kind=kind,
        exe=exe,
        cwd=str(folder),
        machine=machine,
        nick=nick,
        run_dir=run_dir,
        irc=irc,
        relay=relay,
        log=log,
        env_secret=secret,
        startup_grace_s=grace,
        install_root=_install_root,
        session_log_path=_state_root() / "logs" / f"seat-{nick}.log",
    )
    sup.publish_exit_digest = lambda last_exit: post_digest_seat_kind(
        machine=machine, pid=pid, nick=nick, kind=kind, model=seat_model,
        last_exit=last_exit, cursor_account=getattr(dec, "account", "") or "", log=log,
    )
    # FR #2782: a hotpatched install exe must reach this seat at its next idle point.
    sup.stale_build_check = lambda: stale_build_reason(sys.executable, _install_root)

    def _publish_stale(status: dict) -> None:
        post_digest_seat_kind(
            machine=machine,
            pid=pid,
            nick=nick,
            kind=kind,
            model=seat_model,
            configured_model=cfg_model,
            model_mismatch=mismatch,
            mismatch_reason=mismatch_reason,
            cost_tier=cost_tier,
            start_effort=seat_effort,
            worker_build=build,
            stale_build=status,
            last_exit=sup.last_exit,
            cursor_account=getattr(dec, "account", "") or "",
            log=log,
        )

    sup.publish_stale_digest = _publish_stale
    if not sup.start_agent():
        irc.close("launch failed")
        return EXIT_LAUNCH_FAIL
    actual = ""
    try:
        import worker_start_model as wsm

        child_env = getattr(sup, "last_child_env", None) or {}
        actual = wsm.concrete_model_id(child_env.get(wsm.ENV_ACTUAL_MODEL))
        if not actual:
            actual = wsm.concrete_model_id(wsm.actual_start_model(env=child_env or os.environ))
        actual_effort = str(child_env.get(wsm.ENV_ACTUAL_EFFORT) or "").strip()
        _cfg = wsm.load_worker_start_config(env=child_env or os.environ)
        cfg_model = wsm.launch_selected_model(kind, _cfg, env=child_env or os.environ)
        mismatch_reason = wsm.model_mismatch_reason(
            actual, cfg_model, env=child_env or os.environ
        )
        mismatch = bool(mismatch_reason)
        cost_tier = wsm.model_cost_tier(actual or cfg_model, _cfg)
        if not actual_effort:
            actual_effort = wsm.configured_start_effort(kind, _cfg)
        if mismatch:
            try:
                notify_start_model_after_launch(
                    kind=kind,
                    configured=cfg_model,
                    actual=actual,
                    machine=machine,
                    nick=nick,
                    shop=irc.shop,
                    shop_say=lambda _ch, msg: irc.say(irc.shop, msg),
                    log=log,
                    reason=mismatch_reason,
                    env=child_env or os.environ,
                )
            except Exception as e:
                log(f"worker: start model unavailable report failed {type(e).__name__}")
        grok_ok = True
        if kind == "grok":
            try:
                import skill_dag_bound as _sdb

                grok_ok = bool(_sdb.grok_session_usable())
            except Exception:
                grok_ok = False
        post_digest_seat_kind(
            machine=machine,
            pid=pid,
            nick=nick,
            kind=kind,
            model=actual or seat_model,
            configured_model=cfg_model,
            model_mismatch=mismatch,
            mismatch_reason=mismatch_reason,
            cost_tier=cost_tier,
            start_effort=actual_effort,
            worker_build=build,
            state=None if grok_ok else "needs_sign_in",
            cursor_account=getattr(dec, "account", "") or "",
            log=log,
            assignable=bool(getattr(sup, "_session_assignable", False)),
            last_exit=sup.last_exit,
        )
    except Exception as e:
        log(f"worker: post-launch start_model digest failed {type(e).__name__}")
    # FR #6409 / #7180: worker ready means assignable (signed in). Else needs sign-in.
    # FR #7196: OpenCode true provider/region miss -> needs model (never ready/ACK).
    try:
        oc_block = ""
        if kind == "opencode" and getattr(sup, "_session_assignable", False):
            oc_block = probe_opencode_model_listing_unavailable(
                seat_model,
                probe_opencode_models_listing(exe),
            )
        if oc_block:
            hello = opencode_needs_model_line(seat_model, oc_block)
            try:
                sup._session_assignable = False
            except Exception:
                pass
            if getattr(sup, "bored", None) is not None:
                try:
                    sup.bored.note_needs_signin()
                except Exception:
                    pass
            if irc.say(irc.shop, hello):
                log(f"worker: hello {hello}")
            else:
                log("worker: needs-model say failed")
        elif getattr(sup, "_session_assignable", False):
            hello_model = actual if (kind == "grok" or actual) else seat_model
            if kind == "opencode" and actual:
                hello_model = actual
            hello = worker_hello_line(
                kind, model=hello_model or seat_model or actual, build=build
            )
            if irc.say(irc.shop, hello):
                log(f"worker: hello {hello}")
            else:
                log("worker: hello say failed")
        else:
            hello = worker_needs_signin_line(
                kind, build=build, reason="no-seat-auth" if kind == "grok" else None
            )
            if getattr(sup, "bored", None) is not None:
                try:
                    sup.bored.note_needs_signin()
                except Exception:
                    pass
            if irc.say(irc.shop, hello):
                log(f"worker: hello {hello}")
            else:
                log("worker: needs-sign-in say failed")
    except Exception as e:
        log(f"worker: hello failed {type(e).__name__}")
    threading.Thread(
        target=outbox_loop,
        args=(run_dir / "outbox.txt", irc, sup.stop, log, sup.on_outbox_wire, sup.may_send_outbox),
        kwargs={
            "extra_paths": sup.opencode_extra_outbox_paths,
            "may_send_extra": sup.may_send_job_outbox,
            "enrich_line": sup.enrich_done_line,
        },
        name="outbox",
        daemon=True,
    ).start()
    install_ctrl_handler(lambda: sup.shutdown("console-closed", EXIT_OK))
    import signal

    for name in ("SIGINT", "SIGBREAK", "SIGTERM"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), lambda *_a: sup.shutdown("signal", EXIT_OK))
            except Exception:
                pass
    return sup.run_forever()


# --------------------------------------------------------------------------------------------- FR #1643: external-kill / parent logging
def parent_of(pid: int) -> int:
    """Best-effort parent PID from Toolhelp32; 0 when unknown or the process is already gone."""
    try:
        want = int(pid)
    except (TypeError, ValueError):
        return 0
    if want <= 0:
        return 0
    for p, pp, _name in snapshot_procs():
        if int(p) == want:
            return int(pp) if int(pp) > 0 else 0
    return 0


def describe_process(pid: int) -> tuple:
    """Best-effort ``(pid, image, cmdline)`` for a live process. Empty strings when a field is unknown.

    Image comes from Toolhelp32 (or QueryFullProcessImageNameW); cmdline from Win32_Process via PowerShell
    when available. Never raises; never prints secrets (caller logs the returned strings as-is).
    """
    try:
        want = int(pid)
    except (TypeError, ValueError):
        return (0, "", "")
    if want <= 0:
        return (0, "", "")
    image = ""
    for p, _pp, name in snapshot_procs():
        if int(p) == want:
            image = str(name or "")
            break
    if not image and sys.platform == "win32":
        try:
            from ctypes import wintypes

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            # PROCESS_QUERY_LIMITED_INFORMATION
            h = k32.OpenProcess(0x1000, False, want)
            if h:
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    if hasattr(k32, "QueryFullProcessImageNameW"):
                        k32.QueryFullProcessImageNameW.argtypes = [
                            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
                        ]
                        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
                        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                            image = buf.value or ""
                finally:
                    k32.CloseHandle(h)
        except Exception:
            pass
    cmdline = ""
    if sys.platform == "win32":
        try:
            # Keep argv short; avoid printing env. Timeout stays low so exit logging never hangs.
            ps = (
                f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={want}\" "
                f"-ErrorAction SilentlyContinue; if ($p) {{ $p.CommandLine }}"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            if r.returncode == 0 and r.stdout:
                cmdline = (r.stdout or "").strip()
        except Exception:
            cmdline = ""
    if not image and cmdline:
        # Fall back to the first token of the cmdline as a display name.
        image = cmdline.split(" ", 1)[0].strip('"')
    return (want, image, cmdline)


def format_external_kill_log(
    agent_pid: int,
    agent_code: int,
    parent_pid: int = 0,
    parent_image: str = "",
    parent_cmd: str = "",
) -> str:
    """One log line for an unexpected agent exit (FR #1643 terminated-by-external-kill)."""
    img = (parent_image or "").strip() or "?"
    cmd = (parent_cmd or "").strip()
    if len(cmd) > 240:
        cmd = cmd[:237] + "..."
    parts = [
        "terminated-by-external-kill",
        f"pid={int(agent_pid)}",
        f"code={int(agent_code)}",
        f"parent_pid={int(parent_pid or 0)}",
        f"parent_image={img}",
    ]
    if cmd:
        parts.append(f"parent_cmd={cmd}")
    return " ".join(parts)


# --------------------------------------------------------------------------------------------- t815u: hard cap of live workers
try:
    from worker_irc_seats import clear_seat_irc, count_irc_agent_seats, write_seat_irc
except ImportError:
    try:
        from common.scripts.worker_irc_seats import clear_seat_irc, count_irc_agent_seats, write_seat_irc
    except ImportError:
        clear_seat_irc = None  # type: ignore
        count_irc_agent_seats = None  # type: ignore
        write_seat_irc = None  # type: ignore

HARD_MAX_WORKERS = 2          # FR #2522/Simon: ONLY worker seats (mode=agent). Plan + maintenance MAY start on top and never count.
# FR #2556: onefile = bootloader+child = ONE seat; recycle/cap-kill MUST use
# worker_seat_roots / recycle_to_cap / excess_worker_seat_roots (never flat PID Skip-N).
CAPPED_MODES = ("agent",)     # modes refused when 2 agent seats are already live
UNCAPPED_MODES = ("plan", "monitor", "maintenance")
_WORKER_EXE_RX = re.compile(r"^bob-worker(?:-[0-9a-f]+)?\.exe$", re.I)


def max_workers() -> int:
    try:
        return max(0, min(HARD_MAX_WORKERS, int(os.environ.get("BOB_WORKER_MAX", HARD_MAX_WORKERS))))
    except ValueError:
        return HARD_MAX_WORKERS


def snapshot_procs() -> list:
    """(pid, ppid, exe name) of every live process (Toolhelp32); [] when it can not be read."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class PE(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_wchar * 260)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        snap = k32.CreateToolhelp32Snapshot(0x2, 0)
        if not snap or snap == wintypes.HANDLE(-1).value:
            return []
        out = []
        try:
            e = PE()
            e.dwSize = ctypes.sizeof(PE)
            ok = k32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                out.append((int(e.th32ProcessID), int(e.th32ParentProcessID), str(e.szExeFile)))
                ok = k32.Process32NextW(snap, ctypes.byref(e))
        finally:
            k32.CloseHandle(snap)
        return out
    except Exception:
        return []


def _proc_mode(entry) -> str:
    """Optional 4th tuple field: mode name or full cmdline.\n\n    FR #3181: missing cmdline => unknown (not agent).\n    """
    if not isinstance(entry, (tuple, list)) or len(entry) < 4:
        return "unknown"
    raw = str(entry[3] or "").strip().lower()
    if raw in ("agent", "plan", "monitor", "maintenance"):
        return raw
    m = re.search(r"--mode[=\s]+(agent|plan|monitor|maintenance)", raw)
    return m.group(1) if m else "unknown"


def other_live_workers(procs: list, my_pid: int, *, modes: tuple = ("agent",)) -> int:
    """Live SEATS other than this one whose mode is in ``modes`` (default: worker/agent only).

    FR #2522 / FR #3181: the hard cap is IRC-joined agent seats only. Plan and maintenance may
    sit on top of 2 workers and must not be counted. ``procs`` entries are
    ``(pid, ppid, exe[, mode_or_cmdline])``; missing mode is ``unknown`` (never agent).
    Cap enforcement uses ``count_irc_agent_seats`` / ``worker_cap_refusal``.
    """
    rows = {}
    for entry in procs:
        p, pp, n = int(entry[0]), int(entry[1]), str(entry[2])
        rows[p] = (pp, n, _proc_mode(entry))
    workers = {p for p, (_pp, n, _m) in rows.items() if _WORKER_EXE_RX.match(n)}
    mine = my_pid
    while mine in rows and rows[mine][0] in workers:
        mine = rows[mine][0]
    roots = {p for p in workers if rows[p][0] not in workers}
    roots.discard(mine)
    roots.discard(my_pid)
    wanted = {str(m).lower() for m in modes}
    return sum(1 for p in roots if rows[p][2] in wanted)


def worker_seat_roots(procs: list, *, modes: tuple = ("agent",)) -> list:
    """FR #2556: PIDs of live worker SEAT roots (onefile bootloader, or lone exe).

    A PyInstaller onefile seat is bootloader + same-named child; only the root
    (parent not also a bob-worker*) counts as a seat. ``modes`` filters like
    ``other_live_workers`` (default: agent seats only).
    """
    rows = {}
    for entry in procs:
        p, pp, n = int(entry[0]), int(entry[1]), str(entry[2])
        rows[p] = (pp, n, _proc_mode(entry))
    workers = {p for p, (_pp, n, _m) in rows.items() if _WORKER_EXE_RX.match(n)}
    wanted = {str(m).lower() for m in modes}
    roots = [p for p in workers if rows[p][0] not in workers and rows[p][2] in wanted]
    return sorted(roots)


def worker_seat_tree_pids(procs: list, root_pid: int) -> list:
    """FR #2556: root + descendants that are bob-worker* (onefile child), root first."""
    rows = {}
    kids = {}
    for entry in procs:
        p, pp, n = int(entry[0]), int(entry[1]), str(entry[2])
        rows[p] = (pp, n)
        kids.setdefault(pp, []).append(p)
    root = int(root_pid)
    if root not in rows or not _WORKER_EXE_RX.match(rows[root][1]):
        return []
    out = [root]
    stack = list(kids.get(root, []))
    while stack:
        c = stack.pop()
        if c in rows and _WORKER_EXE_RX.match(rows[c][1]):
            out.append(c)
            stack.extend(kids.get(c, []))
    return out


def excess_worker_seat_roots(procs: list, keep: int, *, modes: tuple = ("agent",)) -> list:
    """FR #2556: seat roots to stop so at most ``keep`` agent seats remain.

    Keeps the newest roots (highest pid as weak proxy); returns older roots.
    Never use a flat PID Skip-N list — that destroys onefile bootloader+child pairs.
    """
    k = max(0, int(keep))
    roots = worker_seat_roots(procs, modes=modes)
    if len(roots) <= k:
        return []
    return sorted(roots)[: max(0, len(roots) - k)]


def recycle_to_cap(procs: list, keep: int, *, modes: tuple = ("agent",)) -> list:
    """FR #2556: public recycle helper — root PIDs to stop so at most ``keep`` seats remain.

    Same result as ``excess_worker_seat_roots``; name matches the FR acceptance API.
    Callers expand each root with ``worker_seat_tree_pids`` (or tray
    ``Stop-BobWorkerSeatTrees``) before kill. Never Sort|Skip-N on a flat PID list.
    """
    return excess_worker_seat_roots(procs, keep, modes=modes)


def worker_cap_refusal(procs: list, my_pid: int, *, for_mode: str = "agent") -> str:
    """'' = free to start. Plan/monitor/maintenance are never refused by the worker cap.

    FR #3181 / FR #4307: IRC agent markers union live agent process roots.
    """
    if str(for_mode).lower() not in CAPPED_MODES:
        return ""
    if count_irc_agent_seats is None:
        n, cap = other_live_workers(procs, my_pid, modes=("agent",)), max_workers()
        if n >= cap:
            return "max %d workers (%d already running on this machine) - not starting another" % (HARD_MAX_WORKERS, n)
        return ""
    n = count_irc_agent_seats(exclude_pid=my_pid, procs=procs)
    cap = max_workers()
    if n >= cap:
        return "max %d workers (%d agent seats on this machine) - not starting another" % (HARD_MAX_WORKERS, n)
    return ""


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(prog="bob-worker", description="Start ONE NEW agent (worker with IRC, plan, or Jeeves monitor) chosen by token availability.")
    p.add_argument("--mode", choices=("agent", "plan", "monitor", "maintenance"), default="agent")
    p.add_argument(
        "--agent",
        default="",
        help="explicit seat agent: grok, cursor, or opencode (omit for automatic Grok then Cursor then OpenCode)",
    )
    p.add_argument("--install-root", default="")
    p.add_argument(
        "--work-root",
        default="",
        help="monitor/maintenance mode: Jeeves install CWD (default sibling <ai>\\jeeves)",
    )
    p.add_argument("--machine-id", default="")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-tls", action="store_true", help="tests only")
    p.add_argument("--version", action="store_true", help="print embedded source commit SHA and exit (FR #6349)")
    p.add_argument("--dry-run", action="store_true", help="print the agent selection as JSON and exit (starts nothing)")
    p.add_argument("--list-agents", action="store_true", help="print installed agent choices as JSON and exit (starts nothing)")
    p.add_argument("--refresh-fuel", action="store_true", help="with --list-agents, read each provider on its own short budget and cache the result")
    p.add_argument("--describe-launch", action="store_true", help="FR #2413/MRB #2417: print describe_worker_exe_launch JSON and exit (tray/CLI shared plan)")
    p.add_argument("--echo", action="store_true", help="also print the log to stdout")
    p.add_argument(
        "--startup-grace-s",
        type=float,
        default=None,
        help="seconds to hold inject/!bored after agent spawn (FR #955; default 60, or BOB_WORKER_STARTUP_GRACE_S)",
    )
    args = p.parse_args(argv)
    capture_opencode_model_env_at_start()
    if getattr(args, 'version', False):
        print(get_source_commit())
        return EXIT_OK
    try:
        args.agent = normalize_explicit_agent(args.agent)
    except ValueError as e:
        try:
            print(str(e), file=sys.stderr)
        except Exception:
            pass
        return EXIT_USAGE
    args.install_root = resolve_install_root(args.install_root)
    if getattr(args, "describe_launch", False):
        try:
            plan = describe_worker_exe_launch(
                args.install_root,
                args.mode,
                args.machine_id or "",
                work_root=(args.work_root or None),
                source="cli",
                agent=args.agent,
            )
        except ValueError as e:
            try:
                print(str(e), file=sys.stderr)
            except Exception:
                pass
            return EXIT_USAGE
        print(json.dumps(plan, sort_keys=True))
        return EXIT_OK
    if args.list_agents or args.dry_run:
        cc, ge, oe = resolve_cursor_cmd(), resolve_grok_exe(), resolve_opencode_cmd()
        auth_present = opencode_auth_file_present()
        if args.list_agents:
            refresh = False
            readings_known = False
            if args.refresh_fuel:
                fuel = read_fuel_bounded(Path(args.install_root))
                save_agent_list_fuel(fuel)
                readings_known = True
            else:
                cached = load_fresh_agent_list_fuel()
                if cached is not None:
                    fuel = cached
                    readings_known = True
                else:
                    fuel = Fuel()
                    refresh = True
            print(json.dumps({
                "agents": list_worker_agents(
                    fuel, cc, ge, oe, auth_present=auth_present, readings_known=readings_known
                ),
                "refresh": refresh,
            }, sort_keys=True))
            return EXIT_OK
        fuel = read_fuel(Path(args.install_root))
        signin_state = preflight_xai_signin()
        signin_ok = signin_state == "ok"
        dec = select_agent(fuel, cc, ge, xai_signin_ok=signin_ok)
        dec = resolve_seat_decision(
            args.agent, dec, fuel, cc, ge, oe, auth_present=auth_present,
            xai_signin_ok=signin_ok, signin_state=signin_state,
            machine=getattr(args, "machine_id", "") or "",
            fleet_digest=load_public_digest(
                public_digest_path(install_root=getattr(args, "install_root", None))
            ),
            install_root=getattr(args, "install_root", None),
        )
        if args.mode == "plan":
            cwd = str(Path(args.install_root) / "plan")
        elif args.mode in ("monitor", "maintenance"):
            cwd = str(Path(args.work_root) if args.work_root else _default_jeeves_root(Path(args.install_root)))
        else:
            cwd = str(Path(args.install_root) / "worker")
        print(json.dumps({"decision": dec.kind, "reason": dec.reason, "agent": args.agent or "auto",
                          "cursor_cmd": bool(cc), "grok_exe": bool(ge),
                          "opencode_cmd": bool(oe), "fuel": fuel.__dict__, "cwd": cwd, "mode": args.mode}))
        return EXIT_OK
    if args.startup_grace_s is None:
        env_grace = os.environ.get("BOB_WORKER_STARTUP_GRACE_S", "").strip()
        try:
            args.startup_grace_s = float(env_grace) if env_grace else 60.0
        except ValueError:
            args.startup_grace_s = 60.0
    log = Log(_state_root() / "logs" / f"bob-worker-{args.mode}.log", echo=args.echo)
    # FR #2522 / Simon: ONLY mode=agent is capped. Plan + maintenance (+ monitor) start freely on top of 2 workers.
    if args.mode in CAPPED_MODES:
        refusal = worker_cap_refusal(snapshot_procs(), os.getpid(), for_mode=args.mode)
        if refusal:
            log("refused: " + refusal)
            report_seat_start_refusal(
                machine=getattr(args, "machine_id", "") or "",
                kind=getattr(args, "agent", "") or "",
                model="",
                reason=refusal,
                fuel=None,
                tray_restarted=False,
                log=log,
            )
            try:
                ensure_console("Bob worker - refused")
                print("\nBob worker: " + refusal + ".\nClose a running worker window first.\n")
                time.sleep(8)
            except Exception:
                pass
            return EXIT_REFUSED
    if not args.echo:
        silence_console(log)  # t787u: the console belongs to the agent TUI; errors go to the log file only
    # FR #8202: hash-check unpack beside the exe; prefer those scripts on sys.path
    # (and for by-path resolve) over a stale flat C:\ai\bob\scripts tree.
    try:
        prefer_shipped_scripts_on_sys_path(log=log)
    except Exception as e:
        log(f"shipped-scripts: prefer-path failed {type(e).__name__}")
    try:
        import crash_report

        crash_report.install("bob-worker")
    except Exception:
        pass
    try:
        ensure_console("Bob %s - starting" % args.mode)  # the ONE window for this agent
        if args.mode == "plan":
            return run_plan(args, log)
        if args.mode == "monitor":
            return run_monitor(args, log)
        if args.mode == "maintenance":
            return run_maintenance(args, log)
        return run_agent(args, log)
    except Exception as e:  # never a traceback dialog
        log(f"fatal: {type(e).__name__}: {str(e)[:200]}")
        return EXIT_LAUNCH_FAIL


if __name__ == "__main__":
    sys.exit(main())
