r"""bob-worker: one compiled EXE that starts ONE NEW agent (Cursor agent.cmd or Grok agent.exe), keeps ITS OWN IRC
connection for that agent and relays IRC -> agent the instant a message arrives.

Modes
  --mode agent   worker seat: cwd <install>\worker, IRC nick <machine>-<pid>, joins ONLY #<machine>
  --mode plan    plan agent: cwd <install>\plan, no IRC, fire-and-forget launch
  --mode monitor Jeeves MONITORING agent: cwd --work-root (default <ai>\\jeeves), no IRC; same fuel pick as agent
  --mode maintenance Jeeves maintenance after --heal still failing (FR #2412): cwd --work-root, diagnose/fix, file intake

Rules (CAST IRON, Simon t762u-t765u)
  * Agent choice is ALWAYS automatic by token availability (FR #3997): Grok (local weekly > 0 or unknown read)
    -> Cursor (high or low pool > 0) -> dialog asking for a Grok session key (kept in memory only, handed to the child env, never written/printed).
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

EXIT_OK = 0
EXIT_USAGE = 64
EXIT_IRC_FAIL = 2  # could not connect / register: no agent was started
EXIT_IRC_LOST = 3  # IRC lost for good (grace 0 immediate, or reconnect grace exhausted): agent tree killed
EXIT_NO_AGENT = 4  # nothing to start (no key given / no agent installed)
EXIT_GAVE_UP = 5  # hang-restart bound exceeded
EXIT_LAUNCH_FAIL = 6
EXIT_REFUSED = 7  # t815u: already the maximum number of workers running
EXIT_STALE_BUILD = 8  # FR #2782 legacy; FR #3180 keeps the seat running and asks for a manual restart instead

def _default_install_root() -> str:
    """<drive>:\\ai\\bob on the fixed disk that really holds the fleet (t780u); never a hard-coded C:."""
    try:
        import ai_root

        return ai_root.product_root("bob")
    except Exception:  # pragma: no cover - standalone fallback
        return r"C:\ai\bob"


DEFAULT_INSTALL_ROOT = _default_install_root()


def _common_scripts_dir() -> Path:
    """Resolve common/scripts beside bob/scripts (worktree or install layout)."""
    here = Path(__file__).resolve().parent
    for cand in (here.parent.parent / "common" / "scripts", here.parent / "common" / "scripts"):
        if cand.is_dir():
            return cand
    return here.parent.parent / "common" / "scripts"


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

DEFAULT_HOST = "irc.ntsa.uk"
DEFAULT_PORT = 6697
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
FORBIDDEN_FLAGS = ("--resume", "-r", "--continue", "-c", "--resume-session", "--session", "--chat")
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000

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
            self.log("stderr: " + t[:300])
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
    return _SECRET_RX.sub(lambda m: m.group(1) + "=<redacted>", s)


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
    return Fuel(_i(cur.get("high")), _i(cur.get("low")), _i(grok.get("remaining_pct")), str(grok.get("state") or "unknown").lower())


def read_fuel(install_root: Path, run: Callable = subprocess.run, timeout: float = 90.0) -> Fuel:
    helper = Path(install_root) / "tools" / "Get-BobAgentFuel.ps1"
    if not helper.is_file():
        return Fuel()
    try:
        r = run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper), "-InstallRoot", str(install_root)],
                capture_output=True, text=True, timeout=timeout, creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
        return parse_fuel(r.stdout or "")
    except Exception:
        return Fuel()


def cursor_has_tokens(f: Fuel) -> bool:
    return any(v is not None and v > 0 for v in (f.cursor_high, f.cursor_low))


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


def fuel_reading_known(f: Fuel, kind: str) -> bool:
    """True when the helper returned a parseable reading for this seat kind (FR #3923).

    Empty ``Fuel()`` (helper missing / timeout / unreadable) is **unknown**, not exhausted.
    """
    k = (kind or "").strip().lower()
    if k == "grok":
        if f.grok_pct is not None:
            return True
        st = (f.grok_state or "unknown").strip().lower()
        return st != "unknown"
    # Cursor: relay ACKs on receipt (#4115), so _inject_line uses this probe, not stop_fn.
    if k == "cursor":
        return f.cursor_high is not None or f.cursor_low is not None
    return False


def fuel_explicitly_exhausted(f: Fuel, kind: str) -> bool:
    """True only for an explicit zero/exhausted reading (FR #3923 mid-job gate).

    Unknown / unreadable readings must **not** trip mid-job GIVEUP. Seat *selection*
    still uses ``grok_has_tokens`` / ``cursor_has_tokens`` (unknown = not available).
    """
    k = (kind or "").strip().lower()
    if not fuel_reading_known(f, k):
        return False
    if k == "grok":
        if f.grok_pct is not None:
            return int(f.grok_pct) <= 0
        st = (f.grok_state or "").strip().lower()
        return st in ("exhausted", "empty", "none", "unavailable")
    if k == "cursor":
        return not cursor_has_tokens(f)
    return False


def format_fuel_reading(f: Fuel, kind: str = "") -> str:
    """One-line fuel snapshot for mid-job logs (no secrets)."""
    k = (kind or "").strip().lower()
    return (
        f"kind={k or '-'} pct={f.grok_pct!s} state={f.grok_state!s} "
        f"cursor_high={f.cursor_high!s} cursor_low={f.cursor_low!s} "
        f"known={fuel_reading_known(f, k)} exhausted={fuel_explicitly_exhausted(f, k)}"
    )


@dataclass(frozen=True)
class Decision:
    kind: str  # cursor | grok | dialog | none
    reason: str


def select_agent(fuel: Fuel, cursor_cmd: Optional[str], grok_exe: Optional[str]) -> Decision:
    """grok (local weekly > 0 or unknown) -> cursor (high/low pool > 0) -> dialog (session key). Pure; no I/O. FR #3997."""
    if grok_exe and grok_has_tokens(fuel):
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
    if not grok_exe:
        return Decision("none", f"{why_grok}; {why_cur}")
    return Decision(
        "dialog",
        f"{why_grok}; {why_cur} -> ask for a session key",
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
    return scrub_agent_host_env(normalize_bob_path_envs(env))


_WORKER_EXE_MODES = ("agent", "plan", "monitor", "maintenance")


def describe_worker_exe_launch(
    install_root: str | Path,
    mode: str,
    machine_id: str = "",
    *,
    work_root: str | Path | None = None,
    local_app_data: str | Path | None = None,
    source: str = "tray",
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
) -> dict:
    """Canonical cursor/grok child launch for agent and plan (FR #2413).

    Always includes ``seat_env_extra`` (BOB_OUTBOX / BOB_SHOP / BOB_NICK / BOB_AGENT_NICK / BOB_MACHINE)
    and the mode prompt that points at ``.grok/skills`` + AGENTS.md under ``cwd``.
    """
    mode_l = (mode or "agent").strip().lower()
    folder = str(cwd)
    rd = Path(run_dir)
    if prompt is None:
        if mode_l == "plan":
            prompt = plan_prompt(folder)
        elif mode_l == "monitor":
            prompt = monitor_prompt(folder)
        else:
            prompt = worker_prompt(folder, str(rd), machine, nick)
    launch_mode = mode_l if mode_l in ("agent", "plan", "monitor") else "agent"
    spec = build_launch(kind, launch_mode, folder, prompt, agent_exe, rd, session_id=session_id)
    env = seat_env_extra(rd, machine, nick)
    skills = str(Path(folder) / ".grok" / "skills")
    return {
        "kind": kind,
        "mode": mode_l,
        "cwd": folder,
        "run_dir": str(rd),
        "argv": list(spec.argv),
        "env": dict(env),
        "prompt": prompt,
        "skills_dir": skills,
        "session_id": spec.session_id,
        "files": dict(spec.files or {}),
        "spec": spec,
    }


def worker_prompt(worker_dir: str, home: str, machine: str, nick: str) -> str:
    outbox = str(outbox_path_for_run(home))
    return (
        f"You are a NEW Bobiverse worker agent (fresh session - never resume or continue an older one). "
        f"Your working folder is {worker_dir}. FIRST read the skills in {worker_dir}\\.grok\\skills and {worker_dir}\\AGENTS.md "
        f"(start with bobiverse-worker-seat, then bobiverse-bob-worker, harvest). "
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
        f"CAST IRON (FR #4843): never git checkout/switch/commit/merge in the install root ({Path(worker_dir).parent}); always `git -C <install> worktree add -b fr-N <job-wt> origin/main` (e.g. C:\\ai\\bob-wt-fr-<n> or %TEMP%\\bobiverse-fr-<n>). An install root left on fr-* means live seats read unreviewed skills. "
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


def grok_sessions_root() -> Path:
    return Path(os.environ.get("GROK_HOME") or (Path.home() / ".grok")) / "sessions"


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
        "monitor": "JEEVES MONITORING ONLY: no IRC shop claims; never act as chair; prefer token-free monitor scripts; self-harvest after every finding.",
        "maintenance": "JEEVES MAINTENANCE ONLY (FR #2412/#2522): diagnose after heal still failing; safe hotpatch only; file intake issue; check/test changes only via PR+MRB; harvest BEFORE writing the done file; never Ergo/BobIrcd; never act as chair.",
        # FR #3623: headless shop seats must never block on interactive ask_user_question.
        "agent": (
            "Worker seat: IRC is handled for you. "
            "Never call ask_user_question (or any interactive ask-user tool); there is no human at this console. "
            "If blocked, proceed with a safe default or NACK/GIVEUP."
        ),
    }.get(kind, "Worker seat: IRC is handled for you.")
    head = ("Maintenance session (resumed when a previous one exists, else new). " if kind == "maintenance" else "NEW session. ")
    return (f"{head}Read the skills in {folder}\\.grok\\skills and {folder}\\AGENTS.md before doing anything. "
            f"CAST IRON harvest rule: harvest skills and file every issue/FR/bug with Report-BobiverseIntakeIssue.ps1 (intake webhook) in the same turn. "
            f"One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too. "
            f"Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), it must close all open issues for that skill book (every harvest/skill issue targeting the same book), open one consolidated PR for them, and cite every issue it closes (Closes #N for each); no per-issue PRs for the same skill book; the worker closes the issues itself as part of DONE. "
            f"Never file the worker status receipt itself (DONE/NACK/GIVEUP/SKIP/self-MRB/twin/duplicate/merged or an FR/MRB/UAT #N receipt) as an issue/FR; only a separate genuine defect or gap is filed. "
            f"If an FR worker finds the assigned issue is a duplicate/twin or already done, close it with a comment linking the first issue or covering PR before sending DONE. "
            + extra)


# --------------------------------------------------------------------------------------------- launching (always NEW)
@dataclass
class LaunchSpec:
    argv: list
    cwd: str
    session_id: str
    files: dict = field(default_factory=dict)  # path -> text written before spawn (cursor launcher + prompt)
    env_extra: dict = field(default_factory=dict)


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
                 resume_session_id: Optional[str] = None) -> LaunchSpec:
    if resume_session_id and not (mode == "maintenance" and kind == "grok"):
        raise ValueError("refusing to launch: only grok maintenance may resume (FR #2522)")
    sid = resume_session_id or session_id or str(uuid.uuid4())
    rules = rules_text(cwd, mode)
    files: dict = {}
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
    elif kind == "cursor":
        # The prompt goes through a FILE read by a fixed launcher: text never lands on a command line (no shell injection).
        pfile = str(Path(run_dir) / "prompt.txt")
        lfile = str(Path(run_dir) / "launch-cursor.ps1")
        esc = lambda s: str(s).replace("'", "''")  # noqa: E731
        agent_line = (f"& '{esc(exe)}' --plan --model auto --workspace '{esc(cwd)}' $prompt" if mode == "plan"
                      else f"& '{esc(exe)}' --trust --force --workspace '{esc(cwd)}' -- $prompt")
        files[pfile] = prompt
        files[lfile] = "\n".join(["$ErrorActionPreference = 'Stop'", f"$prompt = [IO.File]::ReadAllText('{esc(pfile)}')",
                                  f"Set-Location -LiteralPath '{esc(cwd)}'", agent_line, "exit $LASTEXITCODE"])
        argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", lfile]
    else:
        raise ValueError(f"unknown agent kind {kind!r}")
    assert_fresh(argv, {k: v for k, v in files.items() if k.endswith(".ps1")}, allow_resume=bool(resume_session_id))
    return LaunchSpec(argv=argv, cwd=cwd, session_id=sid, files=files)


class ProcHandle:
    """Thin wrapper so tests can fake processes."""

    def __init__(self, popen: subprocess.Popen):
        self._p = popen
        self.pid = popen.pid

    def poll(self):
        return self._p.poll()

    def wait(self, timeout=None):
        return self._p.wait(timeout)


def default_spawn(spec: LaunchSpec, env: dict) -> ProcHandle:
    for path, text in spec.files.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
    # t771u: ONE window. The agent INHERITS this exe's console (no CREATE_NEW_CONSOLE, no second console); a kill-on-close job object
    # makes the agent die with us even if we are killed. "New agent every time" is about the SESSION, not the window: the exe's
    # window IS the agent's window and a new click opens a new exe + window.
    popen = subprocess.Popen(spec.argv, cwd=spec.cwd, env=env, creationflags=0, close_fds=True)
    try:
        owned_job().assign(popen)
    except Exception:
        pass
    return ProcHandle(popen)


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
    return True


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
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:maxlen]


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
    """FR #4115: BOB_WORKER_STARTUP_WAIT_READY=0 restores the old 60 s grace-paste behaviour."""
    raw = (os.environ.get("BOB_WORKER_STARTUP_WAIT_READY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


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
    if os.name != "nt":
        return False
    text = one_line(text)
    if not text:
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
) -> Optional[Path]:
    """Resolve ``~/.grok/sessions/<url-quoted cwd>/<uuid>`` when present (FR #2696)."""
    from urllib.parse import quote

    if not session_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", str(session_id)):
        return None
    root = Path(sessions_root) if sessions_root else grok_sessions_root()
    for key in (quote(str(cwd), safe=""), quote(str(cwd).rstrip("\\"), safe="")):
        d = root / key / str(session_id)
        if d.is_dir():
            return d
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
    path = Path(log_path) if log_path else (Path(os.environ.get("GROK_HOME") or (Path.home() / ".grok")) / "logs" / "unified.jsonl")
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
) -> Optional[Callable[[], bool]]:
    """Build a submit probe for the agent kind (FR #2696). None = no probe available."""
    k = (kind or "").strip().lower()
    t0 = float(time.time() if since_wall is None else since_wall)

    if k == "grok":
        sdir = grok_session_dir(cwd, session_id or "", sessions_root=sessions_root) if session_id else None

        def _probe() -> bool:
            if sdir and probe_grok_session_submit(sdir, since_wall=t0):
                return True
            if agent_pid and probe_unified_prompt_enqueue(agent_pid=int(agent_pid), since_wall=t0):
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


def should_start_cursor_turn_watcher(kind: str) -> bool:
    """Cursor seats: chat-store quiet-period turn watcher (BOB_WORKER_CURSOR_TURN_WATCH=0 disables)."""
    if (kind or "").strip().lower() != "cursor" or not bored_on_turn_end_enabled():
        return False
    raw = (os.environ.get("BOB_WORKER_CURSOR_TURN_WATCH") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def apply_cursor_inject_keys_default(kind: str, log: Optional[Callable[[str], None]] = None) -> bool:
    """FR #4464: Cursor seats default to batched KEY_EVENT at seat start.

    cursor-agent treats Ctrl+V as a literal v. Set BOB_WORKER_INJECT_PASTE=0 when
    it is unset, even if the cursor turn watcher does not start. An explicit value wins.
    """
    if (kind or "").strip().lower() != "cursor":
        return False
    if (os.environ.get("BOB_WORKER_INJECT_PASTE") or "").strip():
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
        """True when a readable transcript still has a tool call or no final assistant text."""
        tp = self._transcript_file(chat_dir)
        if tp is None:
            return False
        return cursor_transcript_still_open(tp) is True

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
            if self._on_ended:
                with contextlib.suppress(Exception):
                    self._on_ended(self._turn, now)
            return fired
        if self._active and now - self._last_mtime >= self.quiet_s:
            # FR #4670: a quiet store.db during a tool call is not the end of the turn.
            if self._transcript_blocks_end(d):
                return None
            self._active = False
            fired = "ended"
            if self._on_ended:
                with contextlib.suppress(Exception):
                    self._on_ended(self._turn, now)
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
            try:
                self._on_ended(turn_i, float(wall))
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
    r"|rate\s*limit(?:ed|ing)?\b"
    r")"
)
DEFAULT_DIGEST_REPORT_URL = "https://bob.ntsa.uk/bob/v1/report"


def is_out_of_fuel_text(text: str) -> bool:
    """True when agent/log text is a provider fuel/quota/auth exhaustion (FR #3012 / #3019)."""
    return bool(_OUT_OF_FUEL_RX.search(text or ""))


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
    return bool(_HARD_402_OUT_OF_FUEL_RX.search(text or ""))


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
    return False


def out_of_fuel_reading_clears_soft_hold(
    fuel: Fuel,
    *,
    kind: str,
    has_session_key: bool = False,
    allow_cursor_kind_switch: bool = False,
) -> tuple:
    """FR #4899: soft hold clears only on the seat's own pool (or a real kind-switch).

    Returns ``(clears: bool, reason: str)``. A grok seat with ``grok_pct=0`` must not
    clear because the machine still has Cursor tokens. Cursor may clear a grok soft
    hold only when ``allow_cursor_kind_switch`` is True (seat will run Cursor, FR #3997).
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
    if cursor_has_tokens(fuel) or grok_has_tokens(fuel):
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

    ``reason`` is ``done-miss`` or ``ack-stale``. Without this line Jeeves keeps the
    accepted row and answers every later ``!bored`` with ``nak busy``.
    """
    key = (job_key or "").strip() or "job"
    why = (reason or "done-miss").strip() or "done-miss"
    if key.lower() == "job":
        return f"GIVEUP job {why}"
    return f"GIVEUP {key} {why}"


def out_of_fuel_nack_line(job_key: str) -> str:
    """Shop wire: ``NACK <TYPE> owner/repo#N out-of-fuel`` for assigns refused during hold (FR #4180)."""
    key = (job_key or "").strip() or "job"
    if key.lower() == "job":
        return "NACK job out-of-fuel"
    return f"NACK {key} out-of-fuel"


def default_unified_log_path() -> Path:
    return Path(os.environ.get("GROK_HOME") or (Path.home() / ".grok")) / "logs" / "unified.jsonl"


def default_out_of_fuel_log_path(kind: str, *, env: Optional[dict] = None) -> Optional[Path]:
    """Log path to tail for mid-job out-of-fuel (FR #3012 grok / FR #3019 cursor).

    Override with ``BOB_WORKER_OUT_OF_FUEL_LOG``. Grok defaults to ``unified.jsonl``.
    Cursor has no durable fleet enqueue log yet — returns the override only (watcher waits
    until the path appears; mid-job fuel-reading poll still covers Cursor).
    """
    env = os.environ if env is None else env
    override = (env.get("BOB_WORKER_OUT_OF_FUEL_LOG") or "").strip()
    if override:
        return Path(override)
    k = (kind or "").strip().lower()
    if k == "grok":
        return default_unified_log_path()
    if k == "cursor":
        return None
    return None


def should_start_fuel_watcher(kind: str) -> bool:
    """FR #3019: out-of-fuel watcher for grok **and** cursor (not plan/monitor-only kinds)."""
    return (kind or "").strip().lower() in ("grok", "cursor")


def _http_post_json(
    url: str,
    payload: dict,
    timeout: float = 10.0,
    *,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Best-effort JSON POST (digest report). No secrets. Returns True on HTTP success."""
    raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
            code = int(getattr(resp, "status", 0) or 0)
            ok = 200 <= code < 300
            if not ok and log:
                try:
                    log(f"digest POST HTTP {code} url={url[:80]}")
                except Exception:
                    pass
            return ok
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        if log:
            try:
                log(f"digest POST failed: {type(exc).__name__}: {exc}")
            except Exception:
                pass
        return False


def post_digest_out_of_fuel(
    *,
    machine: str,
    nick: str = "",
    evidence: str = "",
    url: str | None = None,
    env: Optional[dict] = None,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """POST digest so tray/TipForm can show the seat out of fuel (FR #3012 / #5032).

    FR #5032: include weekly=0 so peers paint exhausted (0%% red) instead of a stale %.
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
        if not text or not is_out_of_fuel_text(text):
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
                self._log("out-of-fuel: detected in agent log")
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
            rem = deadline - clock()
            if rem <= 0:
                break
            sleep(min(0.05, rem))
        if i >= len(waits) - 1:
            break
        retry_n = i + 1
        _log(f"relay: submit-verify retry={retry_n} (no prompt seen)")
        try:
            enter_fn()
        except TypeError:
            enter_fn(0)
        except Exception as e:
            _log(f"relay: submit-verify enter failed {type(e).__name__}")
    _log(f"relay: submit-verify FAILED after {retry_n} retries")
    return "failed"


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
    """Build the agent-visible FROM line. FR #2380: optional ``[outbox: path]`` footer survives compaction."""
    body = one_line(text, maxlen)
    line = "FROM %s %s %s" % (nick, target, body)
    if outbox:
        footer = "[outbox: %s]" % str(outbox)
        if footer.lower() not in line.lower():
            line = "%s %s" % (line, footer)
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
        self.on_refuse_assign: Optional[Callable[[str], None]] = None
        # FR #4115: write ACK/NACK to the seat outbox (program, no agent turn).
        self.write_outbox: Optional[Callable[[str], bool]] = None

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
        # FR #2811: hold assigns during post-DONE/NACK/GIVEUP harvest / turn; deliver on turn_ended.
        hold = False
        try:
            hold = bool(self.hold_assigns_while and self.hold_assigns_while())
        except Exception:
            hold = False
        if hold and assign_job_ref(line):
            first_held = False
            with self._lock:
                if line == self._last_line:
                    return "duplicate"
                self._last_line = line
                pending_assigns = sum(1 for p in self._pending if assign_job_ref(p))
                first_held = pending_assigns == 0
                self._pending.append(line)
                if len(self._pending) > self.max_pending:
                    del self._pending[0]
            # FR #4115: ACK the first held assign on receipt (before inject / turn end).
            if first_held:
                self._ack_on_receipt(line)
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
            if line == self._last_line:
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
        if ack_first:
            self._ack_on_receipt(line)
        if do_inject:
            return self._do_inject(line)
        return "held"

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
        if items:
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
        """FR #3192: True while an undelivered/unacked assign is parked in the relay.

        Covers ``held`` (no inject target), ``held_until_turn_end``, ``inject_failed``, and
        coalesced overflow lines that still look like Jeeves assigns — so BoredEmitter must
        not post ``!bored`` until the seat has consumed the assign (or it is dropped).
        """
        with self._lock:
            for line in self._pending:
                if assign_job_ref(line):
                    return True
            for line in self._overflow:
                if assign_job_ref(line):
                    return True
        return False

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
_JOB_ASSIGN_RX = re.compile(r"(?i)\b(FR|MRB|UAT)\s+\S+#\d+\b")
# FR #2791: capture owner/repo#N from an assign (or outbox ACK key) for submit-verify stop match.
_ASSIGN_JOB_REF_RX = re.compile(r"(?i)\b(?:FR|MRB|UAT)\s+(\S+#\d+)\b")
# FR #4180: capture TYPE + owner/repo#N for NACK out-of-fuel lines.
_ASSIGN_TYPE_KEY_RX = re.compile(r"(?i)\b(FR|MRB|UAT)\s+(\S+#\d+)\b")


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


def inject_failed_nack_line(line: str) -> Optional[str]:
    """FR #4115: outbox NACK for an assign the agent never received (Jeeves re-offers it)."""
    key = assign_job_key(line)
    if not key:
        return None
    return f"NACK {key} inject failed"


def submit_verify_giveup_line(line: str) -> Optional[str]:
    """FR #4510: Cursor seat returns the job after a second submit-verify failure."""
    key = assign_job_key(line)
    if not key:
        return None
    return f"GIVEUP {key} submit-verify failed"


def ack_on_receipt_line(line: str) -> Optional[str]:
    """FR #4115: outbox ACK written as soon as the seat receives an assign (before inject)."""
    key = assign_job_key(line)
    if not key:
        return None
    return f"ACK {key}"


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
      * FR #2802: grok ``turn_ended`` releases the harvest hold early (and idle turn end -> reason ``turn``);
        ``harvest_hold_s`` remains the fallback when no turn-end signal arrives;
      * FR #2834: when a turn is open (watcher saw ``turn_started``, no ``turn_ended`` yet), keep holding
        past ``harvest_hold_s`` until ``turn_ended`` or ``turn_hold_max_s`` (default 600 s);
      * FR #2875: ``turn_ended`` with ACK open and no DONE/NACK/GIVEUP arms done-miss (remind after
        ``done_miss_grace_s``, then ``!bored`` reason ``done-miss`` if still open after the reminder turn);
      * FR #4784: before ``!bored`` reason ``done-miss`` or ``ack-stale``, post
        ``GIVEUP <TYPE> owner/repo#N done-miss|ack-stale`` so Jeeves frees the accepted row
        (local ACK clear alone leaves ``nak busy`` forever while the PR stays open);
      * FR #4753: cursor transcript ``turn_ended`` with ``status=error`` counts as turn end (done-miss);
        an open ACK with no activity past ``ack_stale_s`` clears ACK and ``!bored`` reason ``ack-stale``
        even when ``release_gen`` was bumped by a turn that never closed;
      * FR #2996: done-miss release sets ``_release_gen = _turn_gen`` (same as normal turn-end) so later
        ``nak``/``idle`` are not gated forever; ``_run`` clamps past-due waits to 0.5s (no ``wait(0)`` spin);
      * FR #3012: agent 402 / usage-exhausted is **out-of-fuel** — immediate ``GIVEUP … out-of-fuel``,
        cancel done-miss, suppress ``!bored`` until ``clear_out_of_fuel`` (fuel returns / key);
      * FR #4180: while out-of-fuel, ack-miss / HangDetector must not recycle or respawn; Relay
        refuses new assigns (``NACK … out-of-fuel``) with no inject; restart counter is monotonic
        per incident so 3/3 is reachable; unknown fuel readings still do not count as exhausted (#3923);
      * never while busy: open ACK (ack_stale_s), agent not ready, pending inject work before ACK
        (assign_grace_s), or post-DONE/NACK/GIVEUP harvest hold (harvest_hold_s; outbox activity extends it);
      * any forward marks pending work; outbox activity resets idle / extends harvest; at most one line per
        second per reason; only the seat's own shop; never after IRC loss/shutdown (stop()).
    Overrides: BOB_WORKER_HARVEST_HOLD_S, BOB_WORKER_ASSIGN_GRACE_S, BOB_WORKER_BORED_ON_TURN_END,
    BOB_WORKER_TURN_HOLD_MAX_S, BOB_WORKER_DONE_MISS_GRACE_S.
    Event driven: a thread sleeps on a Condition until the next due time or a state change - no polling tick."""

    def __init__(self, send: Callable[[], bool], log: Callable[[str], None], idle_s: float = 120.0, repeat_s: float = 180.0,
                 ack_stale_s: float = 2700.0, retry_s: float = 5.0, clock: Callable[[], float] = time.monotonic,
                 nak_s: float = 120.0, harvest_hold_s: float | None = None, assign_grace_s: float | None = None,
                 turn_hold_max_s: float | None = None, done_miss_grace_s: float | None = None,
                 ack_quiet_s: float | None = None):
        self.send, self.log, self.clock = send, log, clock
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
        self._nak_due: Optional[float] = None
        self._cv = threading.Condition()
        self._ready = False
        self._stopped = False
        self._ack_open = False
        self._ack_at: Optional[float] = None
        self._agent_active_at: Optional[float] = None  # FR #4827: last turn/IO, not ACK wall clock
        self._ack_job_key: Optional[str] = None  # FR #1732: open ACK job id
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
        # FR #2811: assign parked in Relay during harvest — blocks !bored, not turn_ended release.
        self._held_assign = False
        # FR #2875: turn_ended with ACK open and no DONE/NACK/GIVEUP.
        self._done_miss_armed_at: Optional[float] = None
        self._done_miss_key: Optional[str] = None
        self._done_miss_reminded = False
        self._done_miss_release_pending = False
        self.done_miss_remind_fn: Optional[Callable[[str], None]] = None
        # FR #4784: job key for GIVEUP before !bored on done-miss / ack-stale release.
        self._release_giveup_key: Optional[str] = None
        self.seat_release_giveup_fn: Optional[Callable[[str, str], None]] = None
        # FR #3012 / #3019: out-of-fuel hold (suppress !bored; GIVEUP via out_of_fuel_release_fn).
        self._out_of_fuel = False
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

    def _extend_hold_for_open_turn(self, now: float) -> bool:
        """FR #2834: keep harvest busy while turn open, until turn_ended or turn_hold_max_s."""
        if not bored_on_turn_end_enabled():
            return False
        if not self._turn_watcher_armed or not self._turn_open:
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
            return self._extend_hold_for_open_turn(now)

    def note_held_assign(self) -> None:
        """FR #2811: Relay parked an assign; stay offer-pending until flush."""
        with self._cv:
            self._held_assign = True
            self._idle_since = None
            self._cv.notify_all()

    def clear_held_assign(self) -> None:
        with self._cv:
            self._held_assign = False
            self._cv.notify_all()

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

    def note_fresh_assign(self, line: str) -> None:
        """FR #4730: re-offer of a finished job may ACK again; clear its finished mark."""
        key = assign_job_key(line)
        if not key:
            return
        with self._cv:
            self._finished_job_keys.discard(key)
            self._done_job_keys.discard(key)

    def should_forward_outbox(self, payload: str) -> bool:
        """FR #4730: False for a replayed ACK of a job already DONE/NACK/GIVEUP'd."""
        p = (payload or "").strip()
        if not _OUT_ACK_RX.match(p):
            return True
        job = outbox_job_key(p)
        with self._cv:
            return not (job and job in self._finished_job_keys)

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
        self._done_miss_armed_at = None
        self._done_miss_key = None
        self._done_miss_reminded = False
        self._done_miss_release_pending = False

    def _fire_seat_release_giveup(self, reason: str) -> None:
        """FR #4784: shop GIVEUP for the saved release key before !bored (done-miss / ack-stale)."""
        job_key = self._release_giveup_key or "job"
        self._release_giveup_key = None
        fn = self.seat_release_giveup_fn
        if fn is None:
            return
        try:
            fn(job_key, reason)
            self.log(f"seat-release: GIVEUP posted for {job_key} reason={reason}")
        except Exception as e:
            self.log(f"seat-release: GIVEUP failed {type(e).__name__} for {job_key}")

    def _fire_done_miss_remind(self, now: float) -> None:
        """FR #2875: grace expired — inject one reminder (Supervisor sets done_miss_remind_fn)."""
        if self._done_miss_armed_at is None or self._done_miss_reminded:
            return
        if now < float(self._done_miss_armed_at) + float(self.done_miss_grace_s):
            return
        key = self._done_miss_key or (self._ack_job_key or "job")
        self._done_miss_reminded = True
        self.log(f"done-miss: reminder injected for {key}")
        fn = self.done_miss_remind_fn
        if fn is not None:
            try:
                fn(key)
            except Exception as e:
                self.log(f"done-miss: remind inject failed {type(e).__name__}")

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
    def out_of_fuel(self) -> bool:
        """FR #3012: True while the seat is held quiet after a 402 / usage-exhausted hit."""
        with self._cv:
            return bool(self._out_of_fuel)

    def note_out_of_fuel(self, evidence: str = "") -> Optional[str]:
        """FR #3012: mark out-of-fuel, clear ACK/done-miss, invoke release_fn once with the job key.

        Returns the job key that was open (for shop GIVEUP / digest), or None.
        FR #4180: also invoke ``out_of_fuel_enter_fn`` once so Supervisors can disarm
        ack-miss / HangDetector even when no ACK was open.
        """
        release_key: Optional[str] = None
        fn: Optional[Callable[[str], None]] = None
        enter_fn: Optional[Callable[[], None]] = None
        with self._cv:
            if self._out_of_fuel:
                return None  # already held; no second GIVEUP
            now = self.clock()
            self._out_of_fuel = True
            self._out_of_fuel_at = now
            self._out_of_fuel_hard_402 = is_hard_402_out_of_fuel_text(evidence or "")
            self._out_of_fuel_clear_reason = None
            self._clear_done_miss()
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
            preview = one_line(evidence or "out-of-fuel", 100)
            hard = " hard-402" if self._out_of_fuel_hard_402 else ""
            self.log(
                f"out-of-fuel: holding seat{hard}"
                + (f" (was ACK {release_key})" if release_key else "")
                + f" - {preview}"
            )
            self._cv.notify_all()
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
            self._cv.notify_all()

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
            self._cv.notify_all()

    def set_ready(self, ready: bool) -> None:
        with self._cv:
            self._ready = bool(ready)
            self._idle_since = self.clock() if ready else None
            if not ready:
                self._inject_pending = False
                self._inject_at = None
            self._cv.notify_all()

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
            self._cv.notify_all()

    def note_agent_active(self, at: float | None = None) -> None:
        """FR #4827: turn activity or process I/O. Extends an open ACK past ack_stale_s."""
        with self._cv:
            now = float(self.clock() if at is None else at)
            self._agent_active_at = now
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
            now = self.clock()
            self._idle_since = now
            self.log(f"bored: stand down {want}")
            self._cv.notify_all()
            return True

    def nak(self) -> None:
        """t817u: Jeeves answered our !bored with a NAK addressed to us: send !bored again after a FIXED nak_s (120 s). A second NAK
        does not push the timer out; if the seat is busy when it falls due the timer is dropped (DONE brings its own !bored)."""
        with self._cv:
            if self._nak_due is None:
                self._nak_due = self.clock() + self.nak_s
            self._cv.notify_all()

    def _begin_harvest_hold(self, now: float) -> None:
        """FR #1611: after DONE/NACK/GIVEUP, hold !bored so the agent can harvest skills/FRs first."""
        self._inject_pending = False
        self._inject_at = None
        self._idle_since = None
        self._hold_started_at = now
        self._release_gen = None
        self._turn_idle_pending = False
        self._turn_hold_cap_logged = False
        if self.harvest_hold_s > 0:
            self._harvest_until = now + self.harvest_hold_s
            self.log(f"bored: harvest hold {self.harvest_hold_s:.0f}s before next !bored")
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
            self._cv.notify_all()

    def turn_ended(
        self,
        at: float | None = None,
        *,
        turn: int | None = None,
        sid: str | None = None,
    ) -> None:
        """FR #2802: grok turn_ended — release harvest hold when at/after DONE, or idle reason=turn."""
        clear_hard_fuel = False
        try:
            with self._cv:
                now = float(self.clock() if at is None else at)
                self._turn_open = False
                # FR #4858: successful turn clears hard 402 hold without min hold.
                if self._out_of_fuel:
                    clear_hard_fuel = True
                # FR #2875 / inject-pending: still busy on a fresh assign — do not arm done-miss.
                if self._inject_pending and self._inject_at is not None and now - self._inject_at < self.assign_grace_s:
                    self._cv.notify_all()
                    return
                # FR #2875: turn ended with ACK open and no DONE/NACK/GIVEUP.
                # FR #4827: arm even past ack_stale_s — the turn ending is the release signal.
                if self._ack_open and self._ack_at is not None:
                    key = self._ack_job_key or "job"
                    if self._done_miss_reminded:
                        self._ack_open = False
                        self._ack_job_key = None
                        self._done_miss_armed_at = None
                        self._done_miss_key = None
                        self._done_miss_reminded = False
                        self._done_miss_release_pending = True
                        # FR #4784: keep key for GIVEUP before !bored (Jeeves accepted-row free).
                        self._release_giveup_key = key
                        self._idle_since = now
                        # FR #2996: match normal turn-end release — keep _release_gen == _turn_gen
                        # so post-done-miss nak/idle are not gated forever (stale gen + wait(0) spin).
                        self._release_gen = self._turn_gen
                        self._arm_skip = True
                        self._hold_release_at = now
                        self.log(
                            f"done-miss: still no DONE for {key} after reminder - releasing seat"
                        )
                    else:
                        self._done_miss_armed_at = now
                        self._done_miss_key = key
                        self._done_miss_reminded = False
                        self._done_miss_release_pending = False
                        self.log(
                            f"bored: turn ended with ACK open on {key} and no DONE/NACK/GIVEUP - done-miss armed"
                        )
                    self._cv.notify_all()
                    return

                if (
                    (self._harvest_until is not None or self._pending_harvest_fire())
                    and self._hold_started_at is not None
                ):
                    # Stale turn_ended before DONE/free line: ignore.
                    if now < self._hold_started_at:
                        self._cv.notify_all()
                        return
                    self._harvest_until = None
                    self._idle_since = now
                    self._release_gen = self._turn_gen
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
                self._cv.notify_all()

        finally:
            if clear_hard_fuel:
                self.clear_out_of_fuel(reason="successful turn")
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
                    # FR #3189: persist offered repo so Invoke-BobiverseHarvest targets the product.
                    if self.run_dir is not None and self._ack_job_key:
                        try:
                            write_job_repo_marker(self.run_dir, self._ack_job_key)
                        except Exception:
                            pass
                    self._inject_pending = False
                    self._inject_at = None
                    self._harvest_until = None
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
                    self._ack_open = False
                    self._ack_job_key = None
                    self._clear_done_miss()
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
            self._cv.notify_all()

    # ---- decision
    def _busy(self, now: float) -> bool:
        if not self._ready:
            return True
        # FR #3012: out-of-fuel holds the seat quiet (no !bored) until clear_out_of_fuel.
        if self._out_of_fuel:
            return True
        if self._ack_held(now):
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

    def _flush_held_on_harvest_expiry(self, now: float) -> None:
        """FR #4259: harvest wait ended with no open turn — deliver parked assigns.

        Without this, a held assign (``_held_assign`` / ``relay.has_pending_work``) keeps
        ``_busy`` true forever after a repeat-DONE re-arm, so ``!bored`` never fires again.
        Called under ``self._cv``. Skip when a done/free !bored is still pending — that
        path flushes via ``post_bored`` (FR #2811).
        """
        if self._turn_open or self._pending_harvest_fire():
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
        if released:
            self._inject_pending = True
            self._inject_at = now
            self._idle_since = None
            self.log(f"bored: harvest expired - released {released} held assign(s)")
        elif had_held:
            self.log("bored: harvest expired - cleared held-assign flag")

    def _reason(self, now: float) -> Optional[str]:
        if self._stopped or not self._ready or now < self._retry_at:
            return None
        # FR #4259: when harvest wait expires with no open turn and no pending done/free
        # fire, flush held assigns *before* the busy check so a parked job cannot block
        # !bored forever. Pending done/free still flush via post_bored (FR #2811).
        if self._harvest_until is not None and now >= self._harvest_until:
            self._harvest_until = None
            self._flush_held_on_harvest_expiry(now)
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
        if self._harvest_until is not None and now < self._harvest_until:
            wakes.append(self._harvest_until)
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
        if reason in ("done-miss", "ack-stale"):
            self._fire_seat_release_giveup(reason)
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
        self.log(f"bored -> shop reason={reason}")

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
                if not self._out_of_fuel:
                    self._fire_done_miss_remind(now)
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
    install exe, or opt-out ``BOB_WORKER_STALE_BUILD_RECYCLE=0``. FR #3180: seat-heal is gone; detection still runs
    so the seat can announce and skip ``!bored`` without exiting.
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
                 sessions_root: Optional[Path] = None):
        self.kind, self.exe, self.cwd, self.machine, self.nick = kind, exe, cwd, machine, nick
        self.run_dir, self.irc, self.relay, self.log = Path(run_dir), irc, relay, log
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
        # FR #2383: assign injected + no run-dir ACK while agent keeps turning → remind then recycle.
        self.ack_miss = AssignAckMiss()
        # FR #2875: turn_ended with ACK open and no DONE → remind via run-dir inject, then release.
        if self.bored is not None:
            self.bored.done_miss_remind_fn = self._inject_done_miss_reminder
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
            self.bored.fuel_check_fn = self._fuel_available_again
            self.bored.fuel_lost_check_fn = self._fuel_lost_mid_job
        relay.on_inject = self._on_inject
        # FR #2811: park assigns during harvest hold; flush on turn_ended / before !bored.
        relay.hold_assigns_while = lambda: bool(self.bored and self.bored.holding_incoming_assigns)
        relay.on_hold_assign = lambda _line: (
            self.bored.note_held_assign() if self.bored else None
        )
        # FR #4180: refuse (NACK out-of-fuel) assigns while the seat is in out-of-fuel hold.
        relay.refuse_assign_while = lambda: bool(self.bored and self.bored.out_of_fuel)
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

    def _stop_fuel_watcher(self) -> None:
        self._fuel_watch_stop.set()
        th = self._fuel_watch_thread
        self._fuel_watch_thread = None
        if th is not None and th.is_alive():
            th.join(timeout=2.0)

    def _install_root_for_fuel(self) -> Path:
        root = Path(DEFAULT_INSTALL_ROOT)
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
        ok, why = out_of_fuel_reading_clears_soft_hold(
            fuel,
            kind=kind,
            has_session_key=self.secret is not None,
            allow_cursor_kind_switch=allow_switch,
        )
        if ok:
            if self.bored is not None:
                self.bored._out_of_fuel_clear_reason = why or "reading"
            return True
        return False

    def _fuel_lost_mid_job(self) -> bool:
        """FR #3019 / #3923: True only on an **explicit** exhausted reading while ACKed.

        Unknown / timeout / empty ``Fuel()`` is **not** lost (selection still treats
        unknown as unavailable). Logs pct/state/helper snapshot every poll.
        """
        kind = (self.kind or "").strip().lower()
        try:
            fuel = read_fuel(self._install_root_for_fuel())
        except Exception as e:
            self.log(f"out-of-fuel: mid-job read_fuel failed {type(e).__name__} - treat as unknown")
            return False
        snap = format_fuel_reading(fuel, kind)
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
        if self.irc and self.irc.alive:
            try:
                self.irc.say(shop, line)
            except Exception as e:
                self.log(f"out-of-fuel: GIVEUP say failed {type(e).__name__}")
            try:
                self.irc.say(
                    shop,
                    f"out-of-fuel: {self.nick} released `{job_key}` (402/usage exhausted) - quiet until fuel returns",
                )
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
            ok = post_digest_out_of_fuel(
                machine=self.machine,
                nick=self.nick,
                evidence=line,
                log=self.log,
            )
            if not ok:
                self.log("out-of-fuel: digest post returned False (weekly=0 may not have reached peers)")
        except Exception as e:
            self.log(f"out-of-fuel: digest post failed {type(e).__name__}: {e}")
        self.log(f"out-of-fuel: posted {line}")

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
            lambda: default_out_of_fuel_log_path(kind, env=self.base_env if isinstance(self.base_env, dict) else None)
        )

        def _on_hit(text: str) -> None:
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

        def _on_ended(turn: Optional[int], wall: float) -> None:
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

    def _start_turn_watcher(self, session_id: str) -> None:
        """FR #2802: follow current grok session events.jsonl for turn_ended → early !bored."""
        self._stop_turn_watcher()
        if self.bored and should_start_cursor_turn_watcher(self.kind):
            self._start_cursor_turn_watcher()
            return
        if not self.bored or not should_start_turn_watcher(self.kind):
            return
        self._turn_watch_stop = threading.Event()
        cwd = str(self.cwd)
        sid_box = {"sid": session_id}

        def _path() -> Optional[Path]:
            sid = sid_box["sid"]
            if self.sessions:
                sid = self.sessions[-1]
                sid_box["sid"] = sid
            d = grok_session_dir(cwd, sid or "")
            # GrokTurnWatcher tails the events file (same as make_submit_probe / FR #2696).
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

        def _on_ended(turn: Optional[int], wall: float) -> None:
            sid = sid_box.get("sid")
            with contextlib.suppress(Exception):
                pw = getattr(self, "_prompt_watch", None)
                if pw is not None:
                    pw.note_activity()
            if self.bored:
                # Use emitter clock for hold release; wall is only for logging/stale via hold_started mono.
                self.bored.turn_ended(turn=turn, sid=sid)
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
        th = threading.Thread(target=watcher.run, name="grok-turn-watch", daemon=True)
        self._turn_watch_thread = th
        th.start()
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
        """FR #4730: drop replayed ACK for a finished job before it hits IRC."""
        if self.bored is None:
            return True
        try:
            return bool(self.bored.should_forward_outbox(payload))
        except Exception:
            return True

    def on_outbox_wire(self, payload: str) -> None:
        """BoredEmitter + FR #2383 ACK-miss clear; used as the outbox_loop on_payload."""
        p = (payload or "").strip()
        if _OUT_ACK_RX.match(p) or _OUT_DONE_RX.match(p) or _OUT_FREE_RX.match(p):
            self.ack_miss.note_ack()
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
        # FR #2782 / #3180: !bored is only sent when idle. A stale build must not take new work, but seat starts
        # are manual only — keep running, log, and tell the operator to restart (never EXIT_STALE_BUILD).
        why = None
        if self.stale_build_check is not None:
            try:
                why = self.stale_build_check()
            except Exception:
                why = None
        if why:
            prev = getattr(self, "_stale_build_announced", None)
            self.log(f"worker: stale build ({why}) - keep running; restart me manually (FR #3180)")
            if prev != why:
                self._stale_build_announced = why
                try:
                    self.irc.say(self.irc.shop, f"stale build ({why}) - restart me manually")
                except Exception:
                    pass
            return False
        return bool(self.irc.say(self.irc.shop, "!bored"))

    # ---- agent
    def _prompt(self) -> str:
        return worker_prompt(self.cwd, str(self.run_dir), self.machine, self.nick)

    def start_agent(self, note: str = "") -> bool:
        with self._lock:
            if self._shutting:
                return False
            if self.bored:
                self.bored.set_ready(False)  # a (re)starting agent is not idle
            child = describe_agent_child_launch(
                kind=self.kind,
                mode="agent",
                cwd=self.cwd,
                run_dir=self.run_dir,
                machine=self.machine,
                nick=self.nick,
                agent_exe=self.exe,
                prompt=self._prompt() + (" " + note if note else ""),
            )
            spec = child["spec"]
            # FR #2380 / #2413 / #2669: seat env + path normalize + scrub agent-host vars.
            env = prepare_seat_child_env(self.base_env, child["env"])
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
            if self.startup_grace_s > 0:
                self.log(
                    f"agent: holding inject/!bored for startup_grace_s={self.startup_grace_s:.0f}s "
                    f"(FR #955/#2884: first turn_ended ends hold; grace is fallback)"
                )
            self.detector.reset(self.clock())
            self.relay.set_target(None)
            self._start_turn_watcher(spec.session_id)
            self._start_fuel_watcher(int(proc.pid or 0))
            self._start_prompt_watcher(proc)
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
        else:
            self.log(
                f"agent: ready (startup_grace_s={self.startup_grace_s:.0f} fallback); "
                f"inject + !bored enabled"
            )

    def _arm_ready(self, proc) -> None:
        """FR #955 / #2884: arm grace fallback; grok first turn_ended may release earlier."""
        with self._lock:
            self._startup_hold_armed = True
            self._startup_ready_proc = None
            self._startup_session_id = self.sessions[-1] if self.sessions else None
            self._startup_saw_turn_started = False
            self._startup_defer_start_bored = False
            self._startup_turn_release_enabled = should_start_turn_watcher(self.kind)
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
        # FR #5159: Grok also ACK-on-receipt (FR #4115 / #4889). Treating receipt ACK
        # as ``block_on_receipt_ack`` skipped re-paste and left the job accepted
        # (marchhare-29688 / regression of #4510).
        receipt_ack = is_cursor or is_grok

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
            block_on_receipt_ack=not receipt_ack,
            turn_running=_turn_running if receipt_ack else (lambda: False),
            clear_input=clear_console_input if receipt_ack else (lambda: None),
        )
        self._recovery = rec
        return rec

    def _inject_line(self, proc, line: str, *, on_failed=None, force_verify: bool = False, sync: bool | None = None) -> bool:
        if proc.poll() is not None:
            return False
        if on_failed is None and assign_job_ref(line):
            on_failed = lambda l=line: self._inject_recovery().on_failed(l, attempt=1)
        if not _submit_verify_enabled():
            return bool(self.inject(proc.pid, line))
        sid = self.sessions[-1] if self.sessions else None
        # Wall-clock probe baseline (events.jsonl / unified.jsonl use UTC wall times).
        since_wall = time.time()
        probe = make_submit_probe(
            self.kind,
            cwd=str(self.cwd),
            session_id=sid,
            agent_pid=int(getattr(proc, "pid", 0) or 0),
            since_wall=since_wall,
            text=line,
        )
        # FR #2791: stop only when the open ACK is for this injected job (not any ACK).
        stop = None
        want = assign_job_ref(line)
        is_cursor = (self.kind or "").strip().lower() == "cursor"
        inject_fn = self.inject
        if is_cursor and self.inject is inject_console:
            inject_fn = lambda pid, text, log=None: inject_console(
                pid, text, submit_gap_s=_cursor_submit_gap_s(), log=log
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
            line,
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
        )

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
        if age is not None and age < max(30.0, float(self.startup_grace_s) + 15.0):
            self.log(
                f"agent: early exit code={code} after {age:.1f}s "
                f"(startup_grace_s={self.startup_grace_s:.0f}); last_injected={last[:200]!r}; {kill_line}"
            )
        else:
            self.log(f"agent: exited by itself code={code}; {kill_line}; leaving (a closed agent ends the seat)")
        self.shutdown("agent-exited", EXIT_OK)

    # ---- health
    def _ask_user_events_path(self) -> Optional[Path]:
        """FR #3623: current grok session events.jsonl when kind=grok."""
        if (self.kind or "").strip().lower() != "grok":
            return None
        sid = self.sessions[-1] if self.sessions else None
        if not sid:
            return None
        d = grok_session_dir(str(self.cwd), sid, sessions_root=self.sessions_root)
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
            reason = self.detector.check(s, self.clock())
            if reason:
                self.restart_agent(reason)
                continue
            # FR #3623: ask_user_question Pending (alive process, ACK held) — Enter then recycle.
            if self._check_ask_user_pending(proc):
                continue
            # FR #2383: agent still alive/turning but never ACK'd via run-dir outbox.
            self._check_ack_miss(proc)

    def _inject_done_miss_reminder(self, job_key: str) -> None:
        """FR #2875: inject one FROM bob-worker reminder into the live agent console."""
        outbox = outbox_path_for_run(self.run_dir)
        shop = shop_channel(self.machine)
        line = done_miss_reminder_line(shop=shop, outbox=outbox, job_key=job_key)
        with self._lock:
            proc = self.proc
        if proc is None or proc.poll() is not None:
            self.log(f"done-miss: no live agent to remind for {job_key}")
            return
        try:
            self._inject_line(proc, line)
        except Exception as e:
            self.log(f"done-miss: remind inject failed {type(e).__name__}")

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
            self.log(
                f"ack-miss: still no ACK after {self.ack_miss.recycle_s:.0f}s; "
                f"recycling seat (NEW agent) path={outbox}"
            )
            self.ack_miss.clear()
            self.restart_agent("no-ack-after-assign")

    def restart_agent(self, reason: str) -> None:
        # FR #4180: never respawn while out-of-fuel (402 / exhausted is not a hang).
        if self.bored and self.bored.out_of_fuel:
            self.log(
                f"agent: HUNG ({reason}) ignored - out-of-fuel hold (no respawn; FR #4180)"
            )
            self._clear_watchdogs_for_out_of_fuel()
            return
        with self._lock:
            if self._shutting or self.proc is None:
                return
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
            drain_outbox(ob, self.irc, self.log, self.on_outbox_wire, self.may_send_outbox)
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
            self.exit_code = code
            proc = self.proc
            if proc is not None:
                self._expected_exit.add(proc.pid)
        self.log(f"worker: shutting down ({reason}) exit={code}")
        self.stop.set()
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

    def run_forever(self) -> int:
        if self.bored:
            self.bored.start()
        threading.Thread(target=self.health_loop, name="health", daemon=True).start()
        self.done.wait()
        return self.exit_code if self.exit_code is not None else EXIT_OK


# --------------------------------------------------------------------------------------------- outbox
def ensure_outbox(path: Path) -> Path:
    """FR #866: keep the seat outbox path creatable for the whole session.

    ``drain_outbox`` atomically moves ``outbox.txt`` aside, so the file is often
    missing between writes. Agents (and PowerShell ``Add-Content`` /
    ``Set-Content``) still need the parent run dir — and a present empty file is
    friendlier when tools probe the path. Never deletes the run dir.
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
            if _OUT_BORED_RX.match(payload):  # t770u: !bored is posted by the exe ONLY, never by the model
                log("outbox: refused agent-written !bored (the exe posts it)")
                continue
            # FR #4730: drop replayed ACK for a finished job before it hits IRC; still bookkeep.
            if may_send is not None:
                try:
                    allow = bool(may_send(payload))
                except Exception:
                    allow = True
                if not allow:
                    preview = _scrub(one_line(payload, 80))
                    log(f"outbox: dropped stale replay ({len(payload)} chars): {preview}")
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
) -> None:
    ensure_outbox(path)
    while not stop.wait(0.5):  # outbound only; inbound relay is NOT polled
        try:
            drain_outbox(path, irc, log, on_payload, may_send)
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


def _choose(args, log: Log, folder: Path, mode: str):
    cursor_cmd, grok_exe = resolve_cursor_cmd(), resolve_grok_exe()
    fuel = read_fuel(Path(args.install_root))
    dec = select_agent(fuel, cursor_cmd, grok_exe)
    log(f"select[{mode}]: {dec.kind} - {dec.reason}")
    return dec, cursor_cmd, grok_exe, fuel


def run_plan(args, log: Log) -> int:
    folder = Path(args.install_root) / "plan"
    if not folder.is_dir():
        log(f"plan: folder missing {folder}")
        return EXIT_USAGE
    dec, cursor_cmd, grok_exe, fuel = _choose(args, log, folder, "plan")
    secret = None
    kind = dec.kind
    if kind == "none":
        return EXIT_NO_AGENT
    if kind == "dialog":
        key = ask_session_key("No Cursor or Grok tokens remain. Enter an XAI_API_KEY for this Plan only (kept in memory, never saved).", "Grok plan session key")
        if not key:
            log("plan: no key given - not starting")
            return EXIT_NO_AGENT
        secret, kind = SecretStr(key), "grok"
    exe = cursor_cmd if kind == "cursor" else grok_exe
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
    )
    spec = child["spec"]
    env = prepare_seat_child_env(os.environ, child["env"])  # FR #2413 / #2669
    if secret and kind == "grok":
        env["XAI_API_KEY"] = secret.reveal()
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
    log(f"plan: agent ended code={code}")
    return EXIT_OK


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
    dec, cursor_cmd, grok_exe, fuel = _choose(args, log, folder, "monitor")
    secret = None
    kind = dec.kind
    if kind == "none":
        return EXIT_NO_AGENT
    if kind == "dialog":
        key = ask_session_key(
            "No Cursor or Grok tokens remain. Enter an XAI_API_KEY for this Jeeves Monitor only (kept in memory, never saved).",
            "Grok monitor session key",
        )
        if not key:
            log("monitor: no key given - not starting")
            return EXIT_NO_AGENT
        secret, kind = SecretStr(key), "grok"
    exe = cursor_cmd if kind == "cursor" else grok_exe
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
    spec = build_launch(kind, "monitor", str(folder), monitor_prompt(str(folder)), exe, run_dir)
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
    dec, cursor_cmd, grok_exe, fuel = _choose(args, log, folder, "maintenance")
    secret = None
    kind = dec.kind
    if kind == "none":
        return EXIT_NO_AGENT
    if kind == "dialog":
        key = ask_session_key(
            "No Cursor or Grok tokens remain. Enter an XAI_API_KEY for this Jeeves maintenance agent only (kept in memory, never saved).",
            "Grok maintenance session key",
        )
        if not key:
            log("maintenance: no key given - not starting")
            return EXIT_NO_AGENT
        secret, kind = SecretStr(key), "grok"
    exe = cursor_cmd if kind == "cursor" else grok_exe
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
                        resume_session_id=(sid if how == "resume" else None))
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
    dec, cursor_cmd, grok_exe, fuel = _choose(args, log, folder, "agent")
    secret = None
    kind = dec.kind
    if kind == "none":
        return EXIT_NO_AGENT
    if kind == "dialog":
        key = ask_session_key("No Cursor or Grok tokens remain. Enter an XAI_API_KEY to start this worker (kept in memory only, never saved).", "Grok worker session key")
        if not key:
            log("worker: no key given - not starting")
            return EXIT_NO_AGENT
        secret, kind = SecretStr(key), "grok"
    exe = cursor_cmd if kind == "cursor" else grok_exe
    pid = os.getpid()
    nick = seat_nick(machine, pid)
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
    grace = float(getattr(args, "startup_grace_s", 60.0) or 60.0)
    if kind == "grok" and grace < 60.0:
        # Grok TUI session.create often needs 30-60s on slower boxes (FR #955 ionos evidence).
        grace = 60.0
    log(f"worker: startup_grace_s={grace:.0f}")
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
    )
    # FR #2782: a hotpatched install exe must reach this seat at its next idle point.
    _install_root = str(args.install_root)
    sup.stale_build_check = lambda: stale_build_reason(sys.executable, _install_root)
    if not sup.start_agent():
        irc.close("launch failed")
        return EXIT_LAUNCH_FAIL
    threading.Thread(
        target=outbox_loop,
        args=(run_dir / "outbox.txt", irc, sup.stop, log, sup.on_outbox_wire, sup.may_send_outbox),
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
    p.add_argument("--install-root", default=DEFAULT_INSTALL_ROOT)
    p.add_argument(
        "--work-root",
        default="",
        help="monitor/maintenance mode: Jeeves install CWD (default sibling <ai>\\jeeves)",
    )
    p.add_argument("--machine-id", default="")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-tls", action="store_true", help="tests only")
    p.add_argument("--dry-run", action="store_true", help="print the agent selection as JSON and exit (starts nothing)")
    p.add_argument("--describe-launch", action="store_true", help="FR #2413/MRB #2417: print describe_worker_exe_launch JSON and exit (tray/CLI shared plan)")
    p.add_argument("--echo", action="store_true", help="also print the log to stdout")
    p.add_argument(
        "--startup-grace-s",
        type=float,
        default=None,
        help="seconds to hold inject/!bored after agent spawn (FR #955; default 60, or BOB_WORKER_STARTUP_GRACE_S)",
    )
    args = p.parse_args(argv)
    if getattr(args, "describe_launch", False):
        try:
            plan = describe_worker_exe_launch(
                args.install_root,
                args.mode,
                args.machine_id or "",
                work_root=(args.work_root or None),
                source="cli",
            )
        except ValueError as e:
            try:
                print(str(e), file=sys.stderr)
            except Exception:
                pass
            return EXIT_USAGE
        print(json.dumps(plan, sort_keys=True))
        return EXIT_OK
    if args.startup_grace_s is None:
        env_grace = os.environ.get("BOB_WORKER_STARTUP_GRACE_S", "").strip()
        try:
            args.startup_grace_s = float(env_grace) if env_grace else 60.0
        except ValueError:
            args.startup_grace_s = 60.0
    log = Log(_state_root() / "logs" / f"bob-worker-{args.mode}.log", echo=args.echo)
    if args.dry_run:
        cc, ge = resolve_cursor_cmd(), resolve_grok_exe()
        fuel = read_fuel(Path(args.install_root))
        dec = select_agent(fuel, cc, ge)
        if args.mode == "plan":
            cwd = str(Path(args.install_root) / "plan")
        elif args.mode in ("monitor", "maintenance"):
            cwd = str(Path(args.work_root) if args.work_root else _default_jeeves_root(Path(args.install_root)))
        else:
            cwd = str(Path(args.install_root) / "worker")
        print(json.dumps({"decision": dec.kind, "reason": dec.reason, "cursor_cmd": bool(cc), "grok_exe": bool(ge),
                          "fuel": fuel.__dict__, "cwd": cwd, "mode": args.mode}))
        return EXIT_OK
    # FR #2522 / Simon: ONLY mode=agent is capped. Plan + maintenance (+ monitor) start freely on top of 2 workers.
    if args.mode in CAPPED_MODES:
        refusal = worker_cap_refusal(snapshot_procs(), os.getpid(), for_mode=args.mode)
        if refusal:
            log("refused: " + refusal)
            try:
                ensure_console("Bob worker - refused")
                print("\nBob worker: " + refusal + ".\nClose a running worker window first.\n")
                time.sleep(8)
            except Exception:
                pass
            return EXIT_REFUSED
    if not args.echo:
        silence_console(log)  # t787u: the console belongs to the agent TUI; errors go to the log file only
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
