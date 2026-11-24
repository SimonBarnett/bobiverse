#!/usr/bin/env python3
"""Deterministic cleanup of crashed IRC priors. No LLM. Same rules every time.

Run before a bob-* ear, talk seat, or worker irc_agent connects so a hung
prior cannot keep the nick (Ergo then shows a suffixed nick such as
bob-flamingo_1 / the client _l rename).

Rules (nick N, home H). Current process and --keep-pid are never killed.
Command lines are never printed.

irc_agent.py / bob-ear.exe — kill when the command line names that script/exe and any of:
  1. --nick equals N (exact, case-insensitive)
  2. --home normalizes to the same path as H (not a child path; worker homes
     under the fleet home stay up)
  3. N is a bob-* builder nick and --nick is exactly bob (ionos bare-nick ghost)
  PyInstaller onefile parents that share argv are kept via ancestor_pids (FR #2351).

irc_listen.py — kill when the command line names that script and any of:
  1. --home normalizes to H
  2. N is a bob-* builder nick and --home's last path component is exactly
     .bobiverse-cursor (not .bobiverse-cursor-2). irc_listen does not
     join IRC; workers do not use it. This clears the hung default-cursor
     pile that stacked up beside the builder. A live legacy TSR on that
     home is started again by Start-TalkSeat / Start-IrcTsr.

After any kill, wait BOB_IRC_PRIOR_WAIT_S seconds (default 3, clamped
2–5) so the server can drop the TCP session, then scan once more and kill
stragglers. One wait per pass, two passes maximum. No wait when nothing
matched.

Verify (prints pids only, kills nothing):

  python scripts/prior_irc.py --nick bob-flamingo --home ~/.bobiverse --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field

WAIT_DEFAULT_S = 3.0
WAIT_MIN_S = 2.0
WAIT_MAX_S = 5.0
CURSOR_GHOST_HOME = ".bobiverse-cursor"
BARE_BOB_NICK = "bob"
# FR #9236: absorb transient CIM / PowerShell scan failures within one startup.
PRIOR_SCAN_ATTEMPTS_ENV = "BOB_PRIOR_SCAN_ATTEMPTS"
DEFAULT_PRIOR_SCAN_ATTEMPTS = 3
PRIOR_SCAN_BACKOFF_ENV = "BOB_PRIOR_SCAN_BACKOFF_S"
DEFAULT_PRIOR_SCAN_BACKOFF_S = 2.0

_SCRIPT_RE = {
    # FR #2351: frozen bob-ear.exe is the same process family as irc_agent.py.
    "irc_agent": re.compile(
        r"(^|[\s'\"\\/])(irc_agent\.py|bob-ear(?:\.exe)?)(?=$|[\s'\"])",
        re.I,
    ),
    "irc_listen": re.compile(r"(^|[\s'\"\\/])irc_listen\.py(?=$|[\s'\"])", re.I),
}
_FLAG_RE = re.compile(
    r"(?:^|\s)--(?P<name>nick|home)(?:=|\s+)(?P<val>\"[^\"]*\"|'[^']*'|\S+)",
    re.I,
)
_BOB_BUILDER_RE = re.compile(r"bob-.+", re.I)


@dataclass
class PriorCleanResult:
    killed: list[tuple[int, str]] = field(default_factory=list)
    would_kill: list[tuple[int, str]] = field(default_factory=list)
    wait_s: float = 0.0
    scanned: bool = True
    rounds: int = 0
    scan_attempts: int = 0


def is_bob_builder_nick(nick: str) -> bool:
    return _BOB_BUILDER_RE.fullmatch((nick or "").strip()) is not None


def normalize_home(raw: str, *, casefold: bool | None = None) -> str:
    """Path identity for --home. Not a prefix match."""
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    if not text:
        return ""
    text = os.path.expanduser(os.path.expandvars(text))
    text = text.replace("\\", "/")
    parts: list[str] = []
    absolute = text.startswith("/")
    for part in text.split("/"):
        if part in ("", "."):
            if not parts and absolute:
                parts.append("")
            continue
        if part == "..":
            if len(parts) > 1:
                parts.pop()
            continue
        parts.append(part)
    if absolute and parts[:1] != [""]:
        parts.insert(0, "")
    text = "/".join(parts)
    if len(text) > 1:
        text = text.rstrip("/")
    fold = (os.name == "nt") if casefold is None else casefold
    if fold:
        text = text.casefold()
    return text


def homes_equal(a: str, b: str) -> bool:
    left = normalize_home(a)
    right = normalize_home(b)
    return bool(left) and left == right


def ancestor_pids(pid: int) -> set[int]:
    """Parent chain for ``pid`` (exclusive of ``pid``). Used so PyInstaller onefile
    parents that share --nick/--home are never killed as priors of their child (FR #2351).
    """
    out: set[int] = set()
    if pid <= 1:
        return out
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            TH32CS_SNAPPROCESS = 0x00000002
            INVALID = ctypes.c_void_p(-1).value

            class PROCESSENTRY32W(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260),
                ]

            kernel32 = ctypes.windll.kernel32
            snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snap == INVALID:
                return out
            try:
                entry = PROCESSENTRY32W()
                entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                parents: dict[int, int] = {}
                if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                    while True:
                        parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                        if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                            break
                cur = int(pid)
                for _ in range(32):
                    parent = parents.get(cur)
                    if not parent or parent <= 1 or parent == cur or parent in out:
                        break
                    out.add(parent)
                    cur = parent
            finally:
                kernel32.CloseHandle(snap)
        except Exception:
            return out
        return out
    # POSIX: walk /proc
    cur = int(pid)
    for _ in range(32):
        try:
            with open(f"/proc/{cur}/stat", encoding="utf-8") as fh:
                body = fh.read()
            rparen = body.rfind(")")
            fields = body[rparen + 2 :].split()
            parent = int(fields[1])
        except (OSError, ValueError, IndexError):
            break
        if parent <= 1 or parent == cur or parent in out:
            break
        out.add(parent)
        cur = parent
    return out


def is_cursor_ghost_home(raw: str) -> bool:
    norm = normalize_home(raw, casefold=True)
    if not norm:
        return False
    return norm.rsplit("/", 1)[-1] == CURSOR_GHOST_HOME


def script_kind(cmdline: str) -> str | None:
    if not cmdline:
        return None
    hits = [name for name, cre in _SCRIPT_RE.items() if cre.search(cmdline)]
    if len(hits) != 1:
        return None
    return hits[0]


def flag_values(cmdline: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _FLAG_RE.finditer(cmdline or ""):
        name = match.group("name").lower()
        if name in out:
            continue
        val = match.group("val").strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[name] = val
    return out


def nicks_equal(a: str, b: str) -> bool:
    left = (a or "").strip().casefold()
    right = (b or "").strip().casefold()
    return bool(left) and left == right


def resolve_wait_s(explicit: float | None) -> float:
    """Production waits are clamped to 2–5s. Explicit 0 is the test/no-wait hook."""
    if explicit is not None:
        if explicit == 0:
            return 0.0
        return min(WAIT_MAX_S, max(WAIT_MIN_S, float(explicit)))
    raw = (os.environ.get("BOB_IRC_PRIOR_WAIT_S") or "").strip()
    if not raw:
        return WAIT_DEFAULT_S
    try:
        n = float(raw)
    except ValueError:
        return WAIT_DEFAULT_S
    return min(WAIT_MAX_S, max(WAIT_MIN_S, n))


def select_victims(
    processes: list[tuple[int, str]],
    nick: str,
    home: str,
    *,
    keep_pids: set[int] | None = None,
    include_listens: bool = True,
) -> list[tuple[int, str]]:
    """Return (pid, kind) to kill, sorted by pid. Does not kill."""
    keep = set(keep_pids or ())
    # Expand keep with ancestors of every kept pid (onefile parent shares argv).
    for kept in list(keep):
        keep.update(ancestor_pids(kept))
    builder = is_bob_builder_nick(nick)
    chosen: list[tuple[int, str]] = []
    for pid, cmdline in processes:
        if pid <= 1 or pid in keep:
            continue
        kind = script_kind(cmdline)
        if kind is None:
            continue
        flags = flag_values(cmdline)
        cmd_nick = flags.get("nick", "")
        cmd_home = flags.get("home", "")
        if kind == "irc_agent":
            if nicks_equal(cmd_nick, nick):
                chosen.append((pid, kind))
                continue
            if home and cmd_home and homes_equal(cmd_home, home):
                chosen.append((pid, kind))
                continue
            if builder and nicks_equal(cmd_nick, BARE_BOB_NICK):
                chosen.append((pid, kind))
                continue
        elif kind == "irc_listen" and include_listens:
            if home and cmd_home and homes_equal(cmd_home, home):
                chosen.append((pid, kind))
                continue
            if builder and cmd_home and is_cursor_ghost_home(cmd_home):
                chosen.append((pid, kind))
                continue
    chosen.sort(key=lambda row: row[0])
    return chosen


def list_irc_processes() -> list[tuple[int, str]]:
    if os.name == "nt":
        return _list_windows()
    return _list_posix()


def _list_posix() -> list[tuple[int, str]]:
    out = subprocess.check_output(
        ["ps", "-eo", "pid=,args="],
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    rows: list[tuple[int, str]] = []
    for line in out.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_s, _, cmd = stripped.partition(" ")
        if not pid_s.isdigit() or not cmd:
            continue
        low = cmd.casefold()
        if (
            "irc_agent.py" not in low
            and "irc_listen.py" not in low
            and "bob-ear.exe" not in low
            and "/bob-ear" not in low
            and "\\bob-ear" not in low
        ):
            continue
        rows.append((int(pid_s), cmd))
    return rows


def _parse_windows_process_json(text: str) -> list[tuple[int, str]]:
    import json

    text = (text or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    rows: list[tuple[int, str]] = []
    for row in payload or []:
        if not isinstance(row, dict):
            continue
        cmd = str(row.get("CommandLine") or "")
        try:
            pid = int(row.get("ProcessId"))
        except (TypeError, ValueError):
            continue
        rows.append((pid, cmd))
    return rows


def _list_windows_wmic() -> list[tuple[int, str]]:
    """FR #9496: WMIC fallback when Get-CimInstance powershell hangs/times out."""
    out = subprocess.check_output(
        [
            "wmic",
            "process",
            "where",
            "CommandLine is not null",
            "get",
            "ProcessId,CommandLine",
            "/FORMAT:LIST",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        stderr=subprocess.PIPE,
    )
    rows: list[tuple[int, str]] = []
    cmd = ""
    pid: int | None = None
    for raw in (out or "").splitlines():
        line = raw.strip()
        if not line:
            if pid is not None and cmd:
                low = cmd.casefold()
                if (
                    "irc_agent.py" in low
                    or "irc_listen.py" in low
                    or "bob-ear.exe" in low
                    or "\\bob-ear " in low
                    or "\\bob-ear\"" in low
                ):
                    rows.append((pid, cmd))
            cmd = ""
            pid = None
            continue
        if line.lower().startswith("commandline="):
            cmd = line.split("=", 1)[1]
        elif line.lower().startswith("processid="):
            try:
                pid = int(line.split("=", 1)[1].strip())
            except ValueError:
                pid = None
    if pid is not None and cmd:
        low = cmd.casefold()
        if (
            "irc_agent.py" in low
            or "irc_listen.py" in low
            or "bob-ear.exe" in low
            or "\\bob-ear " in low
            or "\\bob-ear\"" in low
        ):
            rows.append((pid, cmd))
    return rows


def _list_windows() -> list[tuple[int, str]]:
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -and "
        "($_.CommandLine -like '*irc_agent.py*' -or $_.CommandLine -like '*irc_listen.py*' "
        "-or $_.CommandLine -like '*bob-ear.exe*' -or $_.CommandLine -like '*\\bob-ear *' "
        "-or $_.CommandLine -like '*\\bob-ear\"*') } | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    # FR #9236: capture stderr so TimeoutExpired / CalledProcessError carry a diagnosable tail.
    # FR #9496: on CIM timeout/failure fall back to WMIC (marchhare WinRM/CIM class).
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            stderr=subprocess.PIPE,
        )
        return _parse_windows_process_json(out)
    except (OSError, subprocess.SubprocessError):
        print("INFO prior-clean windows-list fallback=wmic", flush=True)
        return _list_windows_wmic()


def _prior_scan_attempts() -> int:
    try:
        return max(1, int(os.environ.get(PRIOR_SCAN_ATTEMPTS_ENV) or DEFAULT_PRIOR_SCAN_ATTEMPTS))
    except ValueError:
        return DEFAULT_PRIOR_SCAN_ATTEMPTS


def _prior_scan_backoff_s() -> float:
    try:
        return max(0.0, float(os.environ.get(PRIOR_SCAN_BACKOFF_ENV) or DEFAULT_PRIOR_SCAN_BACKOFF_S))
    except ValueError:
        return DEFAULT_PRIOR_SCAN_BACKOFF_S


def _redact_scan_stderr(raw: str | None, *, limit: int = 200) -> str:
    text = (raw or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[-limit:]
    # Never echo credential-looking fragments.
    low = text.casefold()
    for needle in ("password", "token", "secret", "authorization"):
        if needle in low:
            return "<redacted>"
    return text


def _list_processes_with_retry(
    lister,
    *,
    pause,
    label: str = "scan",
) -> tuple[list[tuple[int, str]] | None, int]:
    """FR #9236: retry OSError / SubprocessError only. Returns (procs|None, attempts)."""
    attempts = _prior_scan_attempts()
    backoff = _prior_scan_backoff_s()
    last_exc: BaseException | None = None
    for n in range(1, attempts + 1):
        try:
            procs = lister()
            if n > 1:
                print(f"INFO prior-clean scan-recovered attempt={n} ({label})", flush=True)
            return procs, n
        except (OSError, subprocess.SubprocessError) as exc:
            last_exc = exc
            rc = getattr(exc, "returncode", None)
            err_out = getattr(exc, "stderr", None)
            if isinstance(err_out, bytes):
                err_out = err_out.decode("utf-8", errors="replace")
            stderr_s = _redact_scan_stderr(str(err_out) if err_out else "")
            print(
                f"INFO prior-clean scan-failed attempt={n}/{attempts} "
                f"err={type(exc).__name__} rc={rc if rc is not None else '-'} "
                f"stderr={stderr_s or '-'} ({label})",
                flush=True,
            )
            if n < attempts and backoff > 0:
                pause(backoff)
    _ = last_exc
    return None, attempts


def kill_pid(pid: int) -> bool:
    if pid <= 1 or pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=20,
                check=False,
            )
            return proc.returncode == 0
        os.kill(pid, signal.SIGKILL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def clean_priors(
    nick: str,
    home: str,
    *,
    self_pid: int | None = None,
    keep_pids: set[int] | None = None,
    dry_run: bool = False,
    wait_s: float | None = None,
    include_listens: bool = True,
    list_processes=None,
    killer=None,
    sleeper=None,
) -> PriorCleanResult:
    """Kill matching priors. Prints pid and kind only — never command lines.

    FR #9236: each list_processes call retries OSError / SubprocessError within
    BOB_PRIOR_SCAN_ATTEMPTS before returning scanned=False (fail-closed).
    """
    lister = list_processes or list_irc_processes
    kill = killer or kill_pid
    pause = sleeper or time.sleep
    wait = resolve_wait_s(wait_s)
    me = os.getpid() if self_pid is None else int(self_pid)
    keep = set(keep_pids or ())
    keep.add(me)
    procs, scan_attempts = _list_processes_with_retry(
        lister, pause=pause, label="initial"
    )
    if procs is None:
        return PriorCleanResult(scanned=False, scan_attempts=scan_attempts)
    victims = select_victims(
        procs, nick, home, keep_pids=keep, include_listens=include_listens
    )
    if dry_run:
        for pid, kind in victims:
            print(f"INFO prior-clean would-kill kind={kind} pid={pid}", flush=True)
        print(f"INFO prior-clean dry-run count={len(victims)}", flush=True)
        return PriorCleanResult(
            would_kill=victims, scanned=True, rounds=1, scan_attempts=scan_attempts
        )
    killed: list[tuple[int, str]] = []
    waited = 0.0
    rounds = 0
    current = victims
    while current and rounds < 2:
        rounds += 1
        for pid, kind in current:
            if kill(pid):
                killed.append((pid, kind))
                print(f"INFO prior-clean killed kind={kind} pid={pid}", flush=True)
            else:
                print(f"INFO prior-clean kill-failed kind={kind} pid={pid}", flush=True)
        if wait > 0:
            pause(wait)
            waited += wait
        procs, rescan_attempts = _list_processes_with_retry(
            lister, pause=pause, label="rescan"
        )
        scan_attempts += rescan_attempts
        if procs is None:
            return PriorCleanResult(
                killed=killed,
                wait_s=waited,
                scanned=False,
                rounds=rounds,
                scan_attempts=scan_attempts,
            )
        current = select_victims(
            procs, nick, home, keep_pids=keep, include_listens=include_listens
        )
    print(
        f"INFO prior-clean done killed={len(killed)} wait_s={waited:g}",
        flush=True,
    )
    return PriorCleanResult(
        killed=killed,
        wait_s=waited,
        scanned=True,
        rounds=rounds,
        scan_attempts=scan_attempts,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nick", required=True)
    parser.add_argument("--home", default="")
    parser.add_argument("--keep-pid", action="append", default=[], type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wait-s", type=float, default=None)
    args = parser.parse_args(argv)
    result = clean_priors(
        args.nick,
        args.home,
        keep_pids=set(args.keep_pid),
        dry_run=args.dry_run,
        wait_s=args.wait_s,
    )
    return 0 if result.scanned else 1


if __name__ == "__main__":
    raise SystemExit(main())
