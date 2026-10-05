r"""bob-worker: one compiled EXE that starts ONE NEW agent (Cursor agent.cmd or Grok agent.exe), keeps ITS OWN IRC
connection for that agent and relays IRC -> agent the instant a message arrives.

Modes
  --mode agent   worker seat: cwd <install>\worker, IRC nick <machine>-<pid>, joins ONLY #<machine>
  --mode plan    plan agent: cwd <install>\plan, no IRC, fire-and-forget launch
  --mode monitor Jeeves MONITORING agent: cwd --work-root (default <ai>\\jeeves), no IRC; same fuel pick as agent
  --mode maintenance Jeeves maintenance after --heal still failing (FR #2412): cwd --work-root, diagnose/fix, file intake

Rules (CAST IRON, Simon t762u-t765u)
  * Agent choice is ALWAYS automatic by token availability: Cursor (high or low pool > 0) -> Grok (local weekly > 0)
    -> dialog asking for a Grok session key (kept in memory only, handed to the child env, never written/printed).
  * EVERY launch is a NEW agent: new session id, new console window, new run dir. Never --resume/--continue/-r, never
    reuse or attach to an existing window/process (assert_fresh() enforces it; a restart after a hang is a NEW agent too).
  * IRC: blocking socket reader thread; a message is injected into the agent's console input from that very thread
    (no poll/timer between receive and inject). PING/PONG and the fleet `ping` liveness are answered here, not by the agent.
  * IRC lost  => kill the agent process tree THIS exe started (and only that) and exit. No reconnect loop, no orphan.
  * Agent hung => bounded restart (new agent) with backoff, each restart logged; give up after the bound.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
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
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

EXIT_OK = 0
EXIT_USAGE = 64
EXIT_IRC_FAIL = 2  # could not connect / register: no agent was started
EXIT_IRC_LOST = 3  # connection lost while running: agent tree killed
EXIT_NO_AGENT = 4  # nothing to start (no key given / no agent installed)
EXIT_GAVE_UP = 5  # hang-restart bound exceeded
EXIT_LAUNCH_FAIL = 6
EXIT_REFUSED = 7  # t815u: already the maximum number of workers running

def _default_install_root() -> str:
    """<drive>:\\ai\\bob on the fixed disk that really holds the fleet (t780u); never a hard-coded C:."""
    try:
        import ai_root

        return ai_root.product_root("bob")
    except Exception:  # pragma: no cover - standalone fallback
        return r"C:\ai\bob"


DEFAULT_INSTALL_ROOT = _default_install_root()
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
    """Parse Get-BobAgentFuel.ps1 JSON (last JSON line wins). Anything unreadable = unknown (= not available)."""
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
    if f.grok_pct is not None:
        return f.grok_pct > 0
    return f.grok_state == "available"  # Grok 1.0.41: no % but verified local auth + current weekly period


@dataclass(frozen=True)
class Decision:
    kind: str  # cursor | grok | dialog | none
    reason: str


def select_agent(fuel: Fuel, cursor_cmd: Optional[str], grok_exe: Optional[str]) -> Decision:
    """cursor (high/low pool > 0) -> grok (local weekly > 0) -> dialog (session key). Pure; no I/O."""
    if cursor_cmd and cursor_has_tokens(fuel):
        return Decision("cursor", f"cursor tokens remain (high={fuel.cursor_high} low={fuel.cursor_low})")
    why = "cursor: " + ("agent.cmd missing" if not cursor_cmd else f"no tokens (high={fuel.cursor_high} low={fuel.cursor_low})")
    if grok_exe and grok_has_tokens(fuel):
        return Decision("grok", f"{why}; grok tokens remain (pct={fuel.grok_pct} state={fuel.grok_state})")
    if not grok_exe:
        return Decision("none", f"{why}; grok: agent.exe missing")
    return Decision("dialog", f"{why}; grok: no tokens (pct={fuel.grok_pct} state={fuel.grok_state}) -> ask for a session key")


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


def seat_env_extra(run_dir: Path | str, machine: str, nick: str) -> dict:
    """Env vars every agent child must inherit so compaction cannot lose the outbox (FR #2380)."""
    outbox = str(outbox_path_for_run(run_dir))
    mid = (machine or "").strip().lstrip("#")
    shop = f"#{mid}"
    return {
        "BOB_OUTBOX": outbox,
        "BOB_SHOP": shop,
        "BOB_NICK": (nick or "").strip(),
        "BOB_MACHINE": mid.lower(),
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
        f"'PRIVMSG #{machine} :ACK <FR|MRB|UAT> owner/repo#N', do the work, then append 'PRIVMSG #{machine} :DONE <FR|MRB|UAT> owner/repo#N <PASS|FAIL> <url>' "
        f"(nothing after the URL); if you cannot, append 'NACK <TYPE> owner/repo#N'. After DONE/NACK/GIVEUP, CAST IRON harvest skills and file any separate genuine issue/FR/bug with {Path(worker_dir).parent}\\scripts\\Report-BobiverseIntakeIssue.ps1 "
        f"in the same turn BEFORE the program's next !bored (the exe holds !bored while you harvest). Never file the worker status receipt itself (DONE/NACK/GIVEUP/SKIP/self-MRB/twin/duplicate/merged or an FR/MRB/UAT #N receipt) as an issue/FR; only a separate genuine defect or gap is filed. See the bobiverse-bob-job-irc, -fr, -mrb and -uat skills. "
        f"One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too. "
        f"Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), it must close all open issues for that skill book (every harvest/skill issue targeting the same book), open one consolidated PR for them, and cite every issue it closes (Closes #N for each); no per-issue PRs for the same skill book; the worker closes the issues itself as part of DONE. "
        f"Never print or store secrets."
    )


def plan_prompt(plan_dir: str) -> str:
    return (
        f"You are a NEW Bobiverse plan agent (fresh session - never resume or continue an older plan). Your working folder is {plan_dir}. "
        f"FIRST read the skills in {plan_dir}\\.grok\\skills and {plan_dir}\\AGENTS.md (start with visionary). "
        f"Plan-mode only: no IRC, no builds. Create this plan's output in a NEW subfolder {plan_dir}\\work\\plan-<yyyyMMdd-HHmmss> and never touch earlier plans. "
        f"CAST IRON: harvest skills and file every issue/FR/bug with {Path(plan_dir).parent}\\scripts\\Report-BobiverseIntakeIssue.ps1 in the same turn. Never print or store secrets."
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


def maintenance_prompt(jeeves_dir: str) -> str:
    # FR #2412: one-shot maintenance after jeeves --heal still failing.
    return (
        f"You are the Jeeves MAINTENANCE agent (FR #2412). NEW session only (never resume). CWD is {jeeves_dir}. "
        f"jeeves.exe --heal / --self-test already ran and STILL reported findings or errors. "
        f"Read {jeeves_dir}\\AGENTS.md and skills under {jeeves_dir}\\.grok\\skills (bobiverse-jeeves, "
        f"bobiverse-jeeves-troubleshooting, bobiverse-fleet-ops, harvest). Diagnose why Jeeves is unhealthy, "
        f"apply safe hotpatch-only fixes (never Ergo/BobIrcd, never kill seats/tray), then file ONE GitHub issue "
        f"via {jeeves_dir}\\scripts\\Report-BobiverseIntakeIssue.ps1 with evidence (heal output, logs, what you tried). "
        f"If you fix it, say so in the issue body. Self-harvest before you finish. Never print or store secrets."
    )


def rules_text(folder: str, kind: str) -> str:
    extra = {
        "plan": "PLAN SEAT ONLY: no IRC, no builds.",
        "monitor": "JEEVES MONITORING ONLY: no IRC shop claims; never act as chair; prefer token-free monitor scripts; self-harvest after every finding.",
        "maintenance": "JEEVES MAINTENANCE ONLY (FR #2412): diagnose after heal still failing; safe hotpatch only; file intake issue; never Ergo/BobIrcd; never act as chair.",
    }.get(kind, "Worker seat: IRC is handled for you.")
    return (f"NEW session. Read the skills in {folder}\\.grok\\skills and {folder}\\AGENTS.md before doing anything. "
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


def assert_fresh(argv: list, files: Optional[dict] = None) -> None:
    """t765u: an agent is never resumed/continued/attached. Refuse any command line that says so."""
    for a in argv:
        if str(a).lower() in FORBIDDEN_FLAGS:
            raise ValueError(f"refusing to launch: '{a}' would reuse an existing agent session")
    for text in (files or {}).values():
        if re.search(r"(?i)(^|\s)(--resume|--continue|-r|-c)(\s|=|$)", str(text)):
            raise ValueError("refusing to launch: launcher script would resume/continue an agent session")


def build_launch(kind: str, mode: str, cwd: str, prompt: str, exe: str, run_dir: Path, session_id: Optional[str] = None) -> LaunchSpec:
    sid = session_id or str(uuid.uuid4())
    rules = rules_text(cwd, mode)
    files: dict = {}
    if kind == "grok":
        if mode == "plan":
            argv = [exe, "--permission-mode", "plan", "--session-id", sid, "--cwd", cwd, "--rules", rules, prompt]
        else:
            argv = [exe, "--no-auto-update", "--no-alt-screen", "--cwd", cwd, "-s", sid, "--rules", rules, prompt]
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
    assert_fresh(argv, {k: v for k, v in files.items() if k.endswith(".ps1")})
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


def set_console_icon(install_root: Optional[Path] = None) -> bool:
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
        ico = find_window_icon(install_root)
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


def inject_console(pid: int, text: str, submit_gap_s: float | None = None) -> bool:
    """Type `text` + Enter into THIS exe's console input. t771u: the agent is a child that INHERITED this console (one window,
    one console), so its keyboard input is our CONIN$ - no AttachConsole/FreeConsole dance and no second console. `pid` is
    kept for the call signature/logging only. Returns True on success."""
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
    with _CONSOLE_LOCK:
        h = k32.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
        if not h or h == ctypes.c_void_p(-1).value:
            return False
        try:
            written = wintypes.DWORD(0)
            recs = build_key_records(text, u32)
            if not k32.WriteConsoleInputW(h, recs, len(recs), ctypes.byref(written)):
                return False
            # End paste chunk so Enter SUBMITS (not a literal newline in the buffer).
            time.sleep(gap)
            enter = build_enter_records()
            if not k32.WriteConsoleInputW(h, enter, len(enter), ctypes.byref(written)):
                return False
            # Second Enter covers TUIs that consume the first as newline after a long paste.
            time.sleep(min(0.08, gap))
            enter2 = build_enter_records()
            return bool(k32.WriteConsoleInputW(h, enter2, len(enter2), ctypes.byref(written)))
        finally:
            k32.CloseHandle(h)


# --------------------------------------------------------------------------------------------- relay (IRC -> agent)
_DROP_RX = re.compile(r"(?i)\b(POINT|DIGEST|AGPK|SEAL)\b|is busy\.|password=|XAI_API_KEY")
_DROP_PREFIX = ("MOOT v1 ", "BOB DIGEST v1", "AGPK v1 ")


_FLOW_RX = re.compile(r"(?i)^(?:@?[\w.\-\[\]\\`^{}|]+[:,]\s*)?(?:!bored\b|NAK\b|NACK\b)")


def inbound_kind(text: str, own_nick: str) -> str:
    """t817u: 'nak' | 'bored' | 'agent'. !bored and NAK/NACK are shop flow control handled by the exe itself; the model never sees them
    (an optional leading ``<nick>:`` address is ignored when classifying)."""
    t = (text or "").strip()
    n = (own_nick or "").strip()
    if n and re.match(r"(?i)^@?" + re.escape(n) + r"\s*[:,]\s*", t):
        t = re.sub(r"(?i)^@?" + re.escape(n) + r"\s*[:,]\s*", "", t, count=1)
    if re.match(r"(?i)^(NAK|NACK)\b", t):
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


_NOTHING_QUEUED_RX = re.compile(r"(?i)^nothing\s+queued\b")


def is_nothing_queued(text: str, own_nick: str = "") -> bool:
    """FR #994: Jeeves idle reply ``<nick>: nothing queued`` (optional address strip)."""
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
        self._overflow: list = []
        self._sent: list = []
        self._last_line = ""
        self._timer: Optional[threading.Timer] = None
        self.last_injected_at: Optional[float] = None
        self.injected = 0
        self.on_inject: Optional[Callable[..., None]] = None  # health: note "input delivered, expect activity" (line arg)
        self.last_unacked = ""

    def set_target(self, inject: Optional[Callable[[str], bool]]) -> None:
        with self._lock:
            self._inject = inject
            pend: list = []
            if inject:  # a None target (agent starting/restarting) must KEEP what is held
                pend, self._pending = self._pending, []
        if inject:
            for line in pend:
                self._do_inject(line)

    def deliver(self, nick: str, target: str, text: str) -> str:
        nq = is_nothing_queued(text)
        if drop_text(text):
            if nq:
                self.log("relay: skipped nothing-queued (dropped by filter — unexpected)")
            return "dropped"
        line = format_from(nick, target, text, outbox=self.outbox_path)
        with self._lock:
            if line == self._last_line:
                return "duplicate"
            self._last_line = line
            if self._inject is None:
                self._pending.append(line)
                if len(self._pending) > self.max_pending:
                    del self._pending[0]
                if nq:
                    # FR #994: operators must see the wire even during startup grace (no inject target yet).
                    self.log("relay: held nothing-queued (agent not ready)")
                    self._persist_last_from(line)
                return "held"
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
        return self._do_inject(line)

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
    """One IRC connection, one blocking reader thread. No reconnect: when the link is gone on_lost fires once."""

    def __init__(self, host: str, port: int, nick: str, machine: str, password: Optional[SecretStr] = None, sasl: Optional[tuple] = None,
                 tls: bool = True, log: Callable[[str], None] = lambda m: None, ping_every: float = 90.0, ping_grace: float = 45.0,
                 send_gap_s: float = 0.4, pm_allowed: tuple = ("jeeves",), connect: Optional[Callable] = None):
        self.host, self.port, self.nick, self.machine = host, port, nick, machine
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
                self.log("irc: NAK from Jeeves -> !bored again in the NAK timer (exe-handled, not relayed)")
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
# FR #1732: job id on ACK/DONE/NACK/GIVEUP — TYPE + owner/repo#N (ignore trailing PASS/url/reason).
_OUT_JOB_KEY_RX = re.compile(
    r"(?i)^(ACK|DONE|NACK|GIVEUP)\s+(FR|MRB|UAT)\s+(\S+#\d+)\b"
)


# FR #2383: Jeeves assign body still visible inside a FROM line after compaction footers.
_JOB_ASSIGN_RX = re.compile(r"(?i)\b(FR|MRB|UAT)\s+\S+#\d+\b")


def looks_like_job_assign(line: str, own_nick: str = "") -> bool:
    """True when an injected FROM looks like a Jeeves FR/MRB/UAT assign (not nothing-queued)."""
    text = line or ""
    if is_nothing_queued(text, own_nick):
        return False
    # Prefer the payload after FROM nick target …
    parts = text.split(None, 3)
    body = parts[3] if len(parts) >= 4 and parts[0].upper() == "FROM" else text
    return bool(_JOB_ASSIGN_RX.search(body))


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
        self.last_line = ""

    def clear(self) -> None:
        self._since = None
        self._reminded = False
        self.last_line = ""

    def note_inject(self, line: str, now: float, *, own_nick: str = "") -> None:
        if looks_like_job_assign(line, own_nick):
            self._since = float(now)
            self._reminded = False
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
        return None

    def reminder_line(self, *, shop: str, outbox: str | Path) -> str:
        path = str(outbox)
        return format_from(
            "bob-worker",
            shop,
            "Reminder: ACK/DONE must go to $env:BOB_OUTBOX (run-dir). "
            "Do not write the ear home\\outbox.txt.",
            outbox=path,
        )



def outbox_job_key(payload: str) -> Optional[str]:
    """Normalize `FR owner/repo#N` from a shop wire line; None if not a typed job line."""
    m = _OUT_JOB_KEY_RX.match((payload or "").strip())
    if not m:
        return None
    return f"{m.group(2).upper()} {m.group(3)}"


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
    """t770u / FR #1611: the EXE (never the model) posts `PRIVMSG #<machine> :!bored`:
      * on seat start (agent ready), after DONE/NACK/GIVEUP **once the harvest hold ends**, and while idle
        (first idle after idle_s, then every repeat_s);
      * never while busy: open ACK (ack_stale_s), agent not ready, pending inject work before ACK
        (assign_grace_s), or post-DONE/NACK/GIVEUP harvest hold (harvest_hold_s; outbox activity extends it);
      * any forward marks pending work; outbox activity resets idle / extends harvest; at most one line per
        second per reason; only the seat's own shop; never after IRC loss/shutdown (stop()).
    Overrides: BOB_WORKER_HARVEST_HOLD_S, BOB_WORKER_ASSIGN_GRACE_S.
    Event driven: a thread sleeps on a Condition until the next due time or a state change - no polling tick."""

    def __init__(self, send: Callable[[], bool], log: Callable[[str], None], idle_s: float = 120.0, repeat_s: float = 180.0,
                 ack_stale_s: float = 2700.0, retry_s: float = 5.0, clock: Callable[[], float] = time.monotonic,
                 nak_s: float = 120.0, harvest_hold_s: float | None = None, assign_grace_s: float | None = None):
        self.send, self.log, self.clock = send, log, clock
        self.idle_s, self.repeat_s, self.ack_stale_s, self.retry_s = idle_s, repeat_s, ack_stale_s, retry_s
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
        self._nak_due: Optional[float] = None
        self._cv = threading.Condition()
        self._ready = False
        self._stopped = False
        self._ack_open = False
        self._ack_at: Optional[float] = None
        self._ack_job_key: Optional[str] = None  # FR #1732: open ACK job id
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
        self.sent: list = []  # (clock time, reason)
        self._thread: Optional[threading.Thread] = None

    @property
    def ack_open(self) -> bool:
        """True while an ACK is open and not stale (FR #2383 / busy bookkeeping)."""
        with self._cv:
            if not self._ack_open or self._ack_at is None:
                return False
            return (self.clock() - self._ack_at) < self.ack_stale_s

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
        if self.harvest_hold_s > 0:
            self._harvest_until = now + self.harvest_hold_s
            self.log(f"bored: harvest hold {self.harvest_hold_s:.0f}s before next !bored")
        else:
            self._harvest_until = None
            self._idle_since = now

    def on_outbox(self, payload: str) -> None:
        now = self.clock()
        p = (payload or "").strip()
        with self._cv:
            if _OUT_ACK_RX.match(p):
                self._ack_open, self._ack_at, self._idle_since = True, now, None
                self._ack_job_key = outbox_job_key(p)
                self._inject_pending = False
                self._inject_at = None
                self._harvest_until = None
            elif _OUT_DONE_RX.match(p):
                job = outbox_job_key(p)
                # FR #1732: DONE for another id must not clear an open ACK.
                if self._ack_open and self._ack_job_key and job and job != self._ack_job_key:
                    self.log(
                        f"bored: ignore DONE for {job} while ACK open on {self._ack_job_key}"
                    )
                else:
                    self._ack_open = False
                    self._ack_job_key = None
                    self._done_key = p
                    self._begin_harvest_hold(now)
            elif _OUT_FREE_RX.match(p):  # NACK/GIVEUP: free, then harvest hold before !bored (FR #161 / #1611)
                verb = (p.split(None, 1)[0] if p else "FREE").upper()
                job = outbox_job_key(p)
                # FR #1732: NACK/GIVEUP of a concurrent assign must not free while another ACK is open.
                if self._ack_open and self._ack_job_key and job and job != self._ack_job_key:
                    self.log(
                        f"bored: ignore free-rx ({verb}) for {job} while ACK open on {self._ack_job_key}"
                    )
                else:
                    self._ack_open = False
                    self._ack_job_key = None
                    self._free_key = p
                    self._begin_harvest_hold(now)
                    self.log(f"bored: free-rx matched ({verb}) - harvest hold then !bored")
            elif self._ack_open:
                self._ack_at = now  # outbox activity keeps an open ACK fresh (the watcher uses the outbox mtime)
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
        if self._ack_open and self._ack_at is not None and now - self._ack_at < self.ack_stale_s:
            return True
        if self._harvest_until is not None and now < self._harvest_until:
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

    def _reason(self, now: float) -> Optional[str]:
        if self._stopped or not self._ready or now < self._retry_at:
            return None
        if self._busy(now):
            self._idle_since = None
            if self._nak_due is not None and now >= self._nak_due:
                self._nak_due = None  # busy at due time: never send; post-harvest !bored covers it
            return None
        if self._harvest_until is not None and now >= self._harvest_until:
            self._harvest_until = None
        if self._idle_since is None:
            self._idle_since = now
        if not self._start_sent:
            return "start"
        # FR #1611: fire done/free only after harvest hold has ended (not immediate on outbox).
        if self._done_key and self._done_key != self._last_done_key:
            return "done"
        if self._free_key and self._free_key != self._last_free_key:
            return "free"
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
        if self._ack_open and self._ack_at is not None and now - self._ack_at < self.ack_stale_s:
            wakes.append(self._ack_at + self.ack_stale_s)
        if self._harvest_until is not None and now < self._harvest_until:
            wakes.append(self._harvest_until)
        if self._inject_pending and self._inject_at is not None and now - self._inject_at < self.assign_grace_s:
            wakes.append(self._inject_at + self.assign_grace_s)
        if wakes:
            wake = min(wakes)
            return min(wake, self._nak_due) if self._nak_due is not None else wake
        if now < self._retry_at:
            return self._retry_at
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
            return
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
        if reason == "free":
            self._last_free_key = self._free_key
        self.sent.append((now, reason))
        self.log(f"bored -> shop reason={reason}")

    def _run(self) -> None:
        with self._cv:
            while not self._stopped:
                now = self.clock()
                r = self._reason(now)
                if r:
                    self._fire(r, now)
                    continue
                due = self._next_due(now)
                self._cv.wait(None if due is None else max(0.0, due - now))

# --------------------------------------------------------------------------------------------- supervisor
class Supervisor:
    """Owns: the IRC seat, the relay, ONE agent at a time. Everything funnels through shutdown()."""

    def __init__(self, *, kind: str, exe: str, cwd: str, machine: str, nick: str, run_dir: Path, irc: Optional[IrcSeat], relay: Relay,
                 log: Callable[[str], None], env_secret: Optional[SecretStr] = None, spawn: Callable = default_spawn,
                 kill: Callable[[int], bool] = kill_tree, probe: Callable[[int], Sample] = sample_tree,
                 inject: Callable[[int, str], bool] = inject_console, detector: Optional[HangDetector] = None,
                 health_interval_s: float = 5.0, startup_grace_s: float = 60.0, clock: Callable[[], float] = time.monotonic,
                 backoff: tuple = RULE_BACKOFF_S, restart_max: int = RULE_RESTART_MAX, restart_window_s: float = RULE_RESTART_WINDOW_S,
                 base_env: Optional[dict] = None, bored: Optional["BoredEmitter"] = None):
        self.kind, self.exe, self.cwd, self.machine, self.nick = kind, exe, cwd, machine, nick
        self.run_dir, self.irc, self.relay, self.log = Path(run_dir), irc, relay, log
        self.secret = env_secret
        self.spawn, self.kill, self.probe, self.inject = spawn, kill, probe, inject
        self.detector = detector or HangDetector()
        self.health_interval_s, self.startup_grace_s, self.clock = health_interval_s, startup_grace_s, clock
        self.backoff, self.restart_max, self.restart_window_s = backoff, restart_max, restart_window_s
        self.base_env = dict(os.environ if base_env is None else base_env)
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
        self._agent_started_at: Optional[float] = None
        # FR #1643 / MRB #1658: capture create-parent while agent is still live (post-wait Toolhelp often misses it).
        self._agent_parent_pid: int = 0
        self._agent_parent_image: str = ''
        self._agent_parent_cmd: str = ''
        self.bored = bored if bored is not None else (BoredEmitter(self.post_bored, log) if irc else None)
        # FR #2383: assign injected + no run-dir ACK while agent keeps turning → remind then recycle.
        self.ack_miss = AssignAckMiss()
        relay.on_inject = self._on_inject
        if irc and self.bored:
            irc.on_nak = self.bored.nak  # t817u
        if irc:
            irc.on_lost = lambda why: self.shutdown("irc-lost: " + why, EXIT_IRC_LOST)

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
            self.bored.activity(mark_work=mark_work)

    def on_outbox_wire(self, payload: str) -> None:
        """BoredEmitter + FR #2383 ACK-miss clear; used as the outbox_loop on_payload."""
        p = (payload or "").strip()
        if _OUT_ACK_RX.match(p) or _OUT_DONE_RX.match(p) or _OUT_FREE_RX.match(p):
            self.ack_miss.note_ack()
        if self.bored:
            self.bored.on_outbox(payload)

    def post_bored(self) -> bool:
        """The ONLY place !bored is sent: the exe, own shop, never during shutdown / after IRC loss."""
        if self._shutting or self.stop.is_set() or not self.irc or not self.irc.alive:
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
            spec = build_launch(self.kind, "agent", self.cwd, self._prompt() + (" " + note if note else ""), self.exe, self.run_dir)
            env = dict(self.base_env)
            # FR #2380: seat outbox/shop/nick survive context compaction via child env (not only first prompt).
            env.update(seat_env_extra(self.run_dir, self.machine, self.nick))
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
            if self.startup_grace_s > 0:
                self.log(
                    f"agent: holding inject/!bored for startup_grace_s={self.startup_grace_s:.0f}s "
                    f"(FR #955: wait for TUI boot before first assign)"
                )
            self.detector.reset(self.clock())
            self.relay.set_target(None)
            self._arm_ready(proc)
            threading.Thread(target=self._wait_exit, args=(proc,), name="agent-wait", daemon=True).start()
            return True

    def _arm_ready(self, proc) -> None:
        def ready():
            with self._lock:
                if self.proc is not proc or self._shutting:
                    return
            self.relay.set_target(lambda line, p=proc: self._inject_line(p, line))
            if self.bored:
                self.bored.set_ready(True)  # seat start / restart complete -> !bored (watcher: "on start")
            self.log(f"agent: ready (startup_grace_s={self.startup_grace_s:.0f}); inject + !bored enabled")

        if self.startup_grace_s <= 0:
            ready()
            return
        t = threading.Timer(self.startup_grace_s, ready)
        t.daemon = True
        self._grace_timer = t
        t.start()

    def _inject_line(self, proc, line: str) -> bool:
        if proc.poll() is not None:
            return False
        return bool(self.inject(proc.pid, line))

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
    def health_loop(self) -> None:
        while not self.stop.wait(self.health_interval_s):
            with self._lock:
                proc = self.proc
            if proc is None or proc.poll() is not None:
                continue
            try:
                s = self.probe(proc.pid)
            except Exception:
                continue
            reason = self.detector.check(s, self.clock())
            if reason:
                self.restart_agent(reason)
                continue
            # FR #2383: agent still alive/turning but never ACK'd via run-dir outbox.
            self._check_ack_miss(proc)

    def _check_ack_miss(self, proc) -> None:
        ack_open = bool(self.bored.ack_open) if self.bored else False
        action = self.ack_miss.tick(self.clock(), ack_open=ack_open)
        if not action:
            return
        outbox = outbox_path_for_run(self.run_dir)
        shop = shop_channel(self.machine)
        if action == "remind":
            line = self.ack_miss.reminder_line(shop=shop, outbox=outbox)
            self.log(
                f"ack-miss: no ACK after assign for {self.ack_miss.remind_s:.0f}s; "
                f"re-injecting outbox reminder path={outbox}"
            )
            try:
                self._inject_line(proc, line)
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
        with self._lock:
            if self._shutting or self.proc is None:
                return
            now = self.clock()
            self.restarts = [(t, r) for t, r in self.restarts if now - t < self.restart_window_s]
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
        self.relay.set_target(None)
        if self.bored:
            self.bored.set_ready(False)
        self.kill(old.pid)
        if delay > 0 and self.stop.wait(delay):
            return
        pending = self.relay.last_unacked
        if pending:
            self.relay.hold(pending)  # the message in flight when the old agent hung is re-delivered to the NEW one once it is ready
        if not self.start_agent(note="(restarted after a hang; the previous session was discarded)"):
            self.shutdown("restart-launch-failed", EXIT_LAUNCH_FAIL)

    # ---- end
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
        if self.bored:
            self.bored.stop()  # no !bored after IRC loss / shutdown
        self.relay.close()
        if self._grace_timer:
            self._grace_timer.cancel()
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


def drain_outbox(path: Path, irc: IrcSeat, log: Callable[[str], None], on_payload: Optional[Callable[[str], None]] = None) -> int:
    """Move outbox.txt aside atomically, send each line to the shop channel. Plain text or `PRIVMSG #shop :text`."""
    path = Path(path)
    if not path.is_file():
        ensure_outbox(path)
        return 0
    tmp = path.with_suffix(".sending")
    try:
        os.replace(path, tmp)
    except OSError:
        return 0
    n = 0
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
            elif on_payload and is_job:
                # FR #161: say() failure must not leave the seat stuck busy (or skip DONE/free bookkeeping).
                try:
                    on_payload(text)
                except Exception:
                    pass
                verb = payload.split(None, 1)[0] if payload else "JOB"
                log(f"outbox: say failed; applied busy bookkeeping for {verb}")
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
        # FR #866: recreate empty outbox so the path stays available for the next agent write.
        ensure_outbox(path)
    return n


def outbox_loop(path: Path, irc: IrcSeat, stop: threading.Event, log: Callable[[str], None],
                on_payload: Optional[Callable[[str], None]] = None) -> None:
    ensure_outbox(path)
    while not stop.wait(0.5):  # outbound only; inbound relay is NOT polled
        try:
            drain_outbox(path, irc, log, on_payload)
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
    spec = build_launch(kind, "plan", str(folder), plan_prompt(str(folder)), exe, run_dir)
    env = dict(os.environ)
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
    env = dict(os.environ)
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


def run_maintenance(args, log: Log) -> int:
    """FR #2412: one-shot Jeeves maintenance seat after --heal still failing."""
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
    run_dir = _new_run_dir("maintenance", "maintenance")
    run_dir.mkdir(parents=True, exist_ok=True)
    ensure_console("Jeeves Maintenance (%s) - closing this window ends the agent" % kind)
    spec = build_launch(kind, "maintenance", str(folder), maintenance_prompt(str(folder)), exe, run_dir)
    env = dict(os.environ)
    if secret and kind == "grok":
        env["XAI_API_KEY"] = secret.reveal()
    try:
        proc = default_spawn(spec, env)
    except Exception as e:
        log(f"maintenance: launch failed {type(e).__name__}")
        return EXIT_LAUNCH_FAIL
    log(
        f"maintenance: started NEW {kind} agent pid={proc.pid} session={spec.session_id} "
        f"cwd={folder} (FR #2412; no IRC; ending either ends both)"
    )
    install_ctrl_handler(lambda: kill_tree(proc.pid))
    try:
        code = proc.wait()
    except Exception:
        code = -1
    log(f"maintenance: agent ended code={code}")
    return EXIT_OK


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
    if not sup.start_agent():
        irc.close("launch failed")
        return EXIT_LAUNCH_FAIL
    threading.Thread(target=outbox_loop, args=(run_dir / "outbox.txt", irc, sup.stop, log, sup.on_outbox_wire),
                     name="outbox", daemon=True).start()
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
HARD_MAX_WORKERS = 2          # slowness: never more than 2 worker seats (agent or plan) per machine; BOB_WORKER_MAX may only LOWER it
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


def other_live_workers(procs: list, my_pid: int) -> int:
    """Live worker SEATS other than this one: root bob-worker*.exe processes (a onefile exe is a bootloader plus a same-named
    child, and a plan/agent seat is one root). Counted from the live process table, never from run dirs."""
    rows = {int(p): (int(pp), str(n)) for p, pp, n in procs}
    workers = {p for p, (_pp, n) in rows.items() if _WORKER_EXE_RX.match(n)}
    mine = my_pid
    while mine in rows and rows[mine][0] in workers:       # walk up to the root of OUR tree
        mine = rows[mine][0]
    roots = {p for p in workers if rows[p][0] not in workers}
    roots.discard(mine)
    roots.discard(my_pid)
    return len(roots)


def worker_cap_refusal(procs: list, my_pid: int) -> str:
    """'' = free to start, else the refusal text."""
    n, cap = other_live_workers(procs, my_pid), max_workers()
    if n >= cap:
        return "max %d workers (%d already running on this machine) - not starting another" % (HARD_MAX_WORKERS, n)
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
    p.add_argument("--echo", action="store_true", help="also print the log to stdout")
    p.add_argument(
        "--startup-grace-s",
        type=float,
        default=None,
        help="seconds to hold inject/!bored after agent spawn (FR #955; default 60, or BOB_WORKER_STARTUP_GRACE_S)",
    )
    args = p.parse_args(argv)
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
    # Monitor/maintenance seats do not consume the worker hard-cap (they are not shop workers).
    if args.mode not in ("monitor", "maintenance"):
        refusal = worker_cap_refusal(snapshot_procs(), os.getpid())  # t815u: hard cap, before any window/agent/IRC
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