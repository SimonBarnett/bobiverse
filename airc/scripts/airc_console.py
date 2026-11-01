#!/usr/bin/env python3
"""airc console service core (FR #253).

Installable Windows service: on ChanServ-registered ``#{machinename}`` sit as
``{machinename}_console``; otherwise join ``#wonderland`` as ``{machinename}_console`` (FR #3834). Silent in channel. Authenticated
PRIVMSG sessions get a per-user console pipe.

Offline-testable: auth, channel naming, session lifecycle, silent policy.
Live IRC loop lives in ``airc_console_service.py``.
"""
from __future__ import annotations

import base64
import binascii
import fnmatch
import importlib.util
import os
import re
import subprocess
import shutil
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal
import json

from account_map import AccountMap, parse_message_tags
from airc_jobs import CAPS_OFF_ALLOWED_VERBS, JobProtocol, JobProtocolError, parse_job_verb
import airc_priority as _priority
import airc_extension as _extension
import airc_network as _network
import airc_legion as _legion


def priority_worker_argv(install_root: str | Path | None = None) -> list[str]:
    """FR #5283: only advertised invocation of the in-tree Priority worker."""
    root = Path(install_root or os.environ.get("AIRC_INSTALL_ROOT") or r"C:\ai\airc")
    entry = root / "airc" / "priority-worker" / "priority_worker.py"
    if not entry.is_file():
        entry = root / "priority-worker" / "priority_worker.py"
    return [sys.executable, str(entry), "--from-airc"]

NICK = "console"
IRC_NICK_MAX = 30
DEFAULT_SHELL = os.environ.get("COMSPEC") or "cmd.exe"
IRC_SAFE_PAYLOAD = 350
PSB64_MAX_CHARS = 24_000
SHELL_OUTPUT_MAX_BYTES = 64_000
# FR #4790: max out/err IRC lines per shell job before truncate marker (DONE still sent).
SHELL_REPLY_MAX_IRC_LINES = 48
SHELL_TIMEOUT_S = 120.0
# FR #2632: per-Query pending shell commands (beyond the one in flight). Overflow
# still fail-closes with busy DONE so Wait never hangs without a DONE (#2612).
SHELL_PENDING_MAX = 8
# FR #5613: unused DCCLISTEN offers expire; dict is size-capped.
DCCLISTEN_TTL_S = 60.0
DCCLISTEN_MAX = 32
UPDATE_PRODUCTS = frozenset({"airc", "bob", "jeeves"})
SHELL_MODE_TOKENS = frozenset({"off", "operators"})
JOBS_TOKENS = frozenset({"off", "on"})
UPDATE_CAP_TOKENS = frozenset({"off", "on"})
_PRIVMSG_RE = re.compile(
    r"^:([^!\s]+)(?:![^@\s]*@\S+)?\s+PRIVMSG\s+(\S+)\s+:?(.*)$",
    re.IGNORECASE,
)
_CHANNEL_SAFE = re.compile(r"[^A-Za-z0-9_-]+")
_CTCP_PING_RE = re.compile(r"^\x01PING(?: (.*))?\x01\s*$", re.IGNORECASE | re.DOTALL)
_CTCP_ANY_RE = re.compile(r"^\x01([A-Za-z]+)(?:[^\x01]*)\x01\s*$")
_PING_CMD_RE = re.compile(r"^\s*ping(?:\s+(\S+))?\s*$", re.IGNORECASE)
# FR #77: UPDATE airc|bob|jeeves [version] - fleet MSI via detached updater only.
# FR #5532: optional leading job id= (same framing as PRIORITY/LEGION/VERSION).
_LEADING_JOB_ID_RE = re.compile(r"(?is)^id=([0-9a-f]{8})\s+")
# FR #5678: any leading id= token (valid or not) so malformed ids fail closed.
_LEADING_ID_ANY_RE = re.compile(r"(?is)^id=(\S*)")
_UPDATE_CMD_RE = re.compile(
    r"^\s*UPDATE\s+(airc|bob|jeeves)(?:\s+v?(\d+\.\d+\.\d+(?:\.\d+)?))?\s*$",
    re.IGNORECASE,
)
# FR #5670: any line that starts with UPDATE (after optional id=) is the verb;
# malformed args must not fall through to PowerShell.
_UPDATE_VERB_RE = re.compile(r"(?is)^\s*UPDATE(?:\s|$)")
UPDATE_USAGE = "airc|bob|jeeves [x.y.z]"
# Fleet ear nick shape bob-{machine}. FR #3286: pattern alone is NOT auth - AuthPolicy
# must still require operators (+ account when --require-account / --accounts).
_BOB_FLEET_NICK_RE = re.compile(r"^bob-[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)

ShopProbeResult = Literal["registered", "missing", "unknown"]
MachineIdSource = Literal[
    "arg",
    "AIRC_CONSOLE_MACHINE",
    "BOB_MACHINE_ID",
    "COMPUTERNAME",
    "HOSTNAME",
    "default",
]


class MachineIdUnresolved(ValueError):
    """No explicit fleet machine id and hostname fallback was refused (FR #77)."""


def _sanitize_id(raw: str) -> str:
    cleaned = _CHANNEL_SAFE.sub("-", (raw or "").strip()).strip("-_")
    return (cleaned or "unknown").lower()


def resolve_machine_id(
    override: str | None = None,
    *,
    allow_hostname_fallback: bool = True,
) -> tuple[str, MachineIdSource]:
    """Canonical machine-id rule (FR #77).

    Order: explicit ``-MachineId`` / override, then ``AIRC_CONSOLE_MACHINE``,
    then ``BOB_MACHINE_ID``. Hostname (``COMPUTERNAME`` / ``HOSTNAME``) is only
    used when ``allow_hostname_fallback`` is true - callers must treat that as
    an explicit choice so the console does not silently join the wrong shop.
    """
    if override and str(override).strip():
        return _sanitize_id(str(override)), "arg"
    env_airc = (os.environ.get("AIRC_CONSOLE_MACHINE") or "").strip()
    if env_airc:
        return _sanitize_id(env_airc), "AIRC_CONSOLE_MACHINE"
    env_bob = (os.environ.get("BOB_MACHINE_ID") or "").strip()
    if env_bob:
        return _sanitize_id(env_bob), "BOB_MACHINE_ID"
    host = (os.environ.get("COMPUTERNAME") or "").strip()
    if host:
        if not allow_hostname_fallback:
            raise MachineIdUnresolved(
                "no -MachineId / AIRC_CONSOLE_MACHINE / BOB_MACHINE_ID; "
                "refusing silent COMPUTERNAME fallback"
            )
        return _sanitize_id(host), "COMPUTERNAME"
    host2 = (os.environ.get("HOSTNAME") or "").strip()
    if host2:
        if not allow_hostname_fallback:
            raise MachineIdUnresolved(
                "no -MachineId / AIRC_CONSOLE_MACHINE / BOB_MACHINE_ID; "
                "refusing silent HOSTNAME fallback"
            )
        return _sanitize_id(host2), "HOSTNAME"
    if not allow_hostname_fallback:
        raise MachineIdUnresolved("no machine id available")
    return "unknown", "default"


def machine_id(override: str | None = None) -> str:
    """Fleet shop id for ``#{machine}`` / ``{machine}_console``.

    Prefer explicit override, then ``AIRC_CONSOLE_MACHINE`` / ``BOB_MACHINE_ID``
    (fleet ids like ``ionos``), then Windows ``COMPUTERNAME``. Using bare
    COMPUTERNAME alone (e.g. ``WIN-MPRE8VI4U6U``) joins the wrong channel and
    looks like \"does not connect\" on ``#<machine>`` / ``#wonderland``.
    """
    mid, _src = resolve_machine_id(override, allow_hostname_fallback=True)
    return mid


def split_console_job_id(text: str) -> tuple[str | None, str]:
    """FR #5532: optional ``id=<8hex> `` frame before a console verb."""
    raw = (text or "").strip()
    m = _LEADING_JOB_ID_RE.match(raw)
    if not m:
        return None, raw
    return m.group(1).lower(), raw[m.end() :]



def leading_job_id_state(text: str) -> tuple[str, str | None, str]:
    """FR #5678: classify optional leading ``id=`` frame.

    Returns ``(ok|bad|none, token_or_jid, rest)``.
    ``ok`` = exactly 8 hex + whitespace; ``bad`` = leading ``id=`` that is not
    that form (too long, non-hex, empty, missing trailing space before verb).
    """
    raw = (text or "").strip()
    m_ok = _LEADING_JOB_ID_RE.match(raw)
    if m_ok:
        return "ok", m_ok.group(1).lower(), raw[m_ok.end() :]
    m_any = _LEADING_ID_ANY_RE.match(raw)
    if m_any is not None:
        return "bad", m_any.group(1) or "", raw[m_any.end() :].lstrip()
    return "none", None, raw


def format_bad_id_reply(token: str) -> str:
    """FR #5678: ``err code=bad_id`` + ``DONE exit=2``; never PowerShell."""
    tok = (token or "").strip()
    # Echo the caller token when the DONE line fits IRC_SAFE_PAYLOAD so Wait
    # can still correlate a handmade/long id; otherwise placeholder.
    done = f"DONE id={tok} exit=2" if tok else "DONE id=00000000 exit=2"
    if (
        tok
        and len(done) <= IRC_SAFE_PAYLOAD
        and "\n" not in tok
        and all(32 <= ord(c) < 127 for c in tok)
    ):
        qid = tok
    else:
        qid = "00000000"
        done = f"DONE id={qid} exit=2"
    err = f"err id={qid} seq=1 code=bad_id need-8-hex"
    if len(err) > IRC_SAFE_PAYLOAD:
        err = err[:IRC_SAFE_PAYLOAD]
    return f"{err}\n{done}"


def parse_update_command(text: str) -> tuple[str, str | None] | None:
    """Return ``(product, version|None)`` for an allowlisted UPDATE verb, else None."""
    _jid, rest = split_console_job_id(text)
    m = _UPDATE_CMD_RE.match(rest)
    if not m:
        return None
    product = m.group(1).lower()
    if product not in UPDATE_PRODUCTS:
        return None
    return product, m.group(2)


def update_usage_job_id(text: str) -> str | None:
    """FR #5670: job id when line is UPDATE-shaped but not allowlisted; else None.

    Returns ``\"\"`` when there is no leading ``id=`` (caller still emits usage).
    """
    jid, rest = split_console_job_id(text)
    if not _UPDATE_VERB_RE.match(rest or ""):
        return None
    if parse_update_command(text) is not None:
        return None
    return (jid or "").lower()


_PRIORITY_PREPARE_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?PRIORITY\s+prepare(?:\s+(.*))?$"
)


def parse_priority_prepare_command(text: str) -> dict[str, str] | None:
    """FR #5286: ``PRIORITY prepare <ENAME>`` or ``name=`` / ``instance=``."""
    m = _PRIORITY_PREPARE_RE.match((text or "").strip())
    if not m:
        return None
    rest = (m.group(2) or "").strip()
    kv = {k.lower(): v for k, v in re.findall(r"(\w+)=([^\s]+)", rest)}
    name = kv.get("name") or kv.get("ename") or ""
    if not name:
        # Prefer a positional token even when key=value tokens appear first
        # (e.g. ``PRIORITY prepare instance=dev FOO``).
        for tok in rest.split():
            if "=" not in tok:
                name = tok
                break
    out = {"name": name, "instance": kv.get("instance") or ""}
    if m.group(1):
        out["qid"] = m.group(1).lower()
    return out


def _load_priority_worker():
    # FR #5523: pack path is <install>\\airc\\priority-worker, not __file__/_MEIPASS.
    candidates: list[Path] = []
    d = _priority.resolve_priority_worker_dir()
    if d is not None:
        candidates.append(d / "priority_worker.py")
    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[1] / "airc" / "priority-worker" / "priority_worker.py",
            here.parents[1] / "priority-worker" / "priority_worker.py",
            Path(os.environ.get("AIRC_INSTALL_ROOT") or r"C:\ai\airc")
            / "airc"
            / "priority-worker"
            / "priority_worker.py",
            Path(os.environ.get("AIRC_INSTALL_ROOT") or r"C:\ai\airc")
            / "priority-worker"
            / "priority_worker.py",
        ]
    )
    seen: set[str] = set()
    for p in candidates:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            spec = importlib.util.spec_from_file_location("priority_worker", p)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


def load_priority_instances(install_root: str | Path | None = None) -> list[dict]:
    """Prefer airc_priority allowlist (same as connect/status); fall back to raw JSON."""
    try:
        al = _priority.load_priority_allowlist(
            _priority.resolve_allowlist_path(install_root)
        )
        return [inst.public_dict() for inst in al.values()]
    except Exception:  # noqa: BLE001 - missing allowlist falls through
        pass
    root = Path(install_root or os.environ.get("AIRC_INSTALL_ROOT") or r"C:\ai\airc")
    for rel in (
        Path("config") / "priority-instances.json",
        Path("config") / "priority-instances.example.json",
    ):
        pth = root / rel
        if not pth.is_file():
            pth = root.parent / "airc" / rel if root.name != "airc" else pth
        if pth.is_file():
            try:
                data = json.loads(pth.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            rows = data.get("instances") if isinstance(data, dict) else data
            return [r for r in (rows or []) if isinstance(r, dict)]
    return []


def _priority_sqlcmd_lock(
    *,
    ename: str,
    instance: dict,
    exec_type: str = "P",
    runner=None,
) -> dict | None:
    """Read EXECPREPLOCK row via sqlcmd. Never UPDATEs. Returns None when missing."""
    server = str(instance.get("sqlServer") or instance.get("sql_server") or "").strip()
    db = str(instance.get("systemDb") or instance.get("system_db") or "system").strip()
    if not server or not ename:
        return None
    # TYPE=P/R named lock join - read only.
    q = (
        "SET NOCOUNT ON; "
        "SELECT E.ENAME, E.[T$EXEC], E.[TYPE], L.UPD "
        "FROM dbo.T$EXEC E "
        "JOIN dbo.EXECPREPLOCK L ON L.[T$EXEC]=E.[T$EXEC] "
        f"WHERE E.ENAME=N'{ename.replace(chr(39), chr(39)+chr(39))}' "
        f"AND E.[TYPE]=N'{exec_type}';"
    )
    run = runner or subprocess.run
    try:
        proc = run(
            ["sqlcmd", "-S", server, "-E", "-d", db, "-Q", q, "-W", "-h", "-1", "-s", "|"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:  # noqa: BLE001
        return None
    for line in (proc.stdout or "").splitlines():
        s = line.strip()
        if not s or "rows affected" in s.lower():
            continue
        parts = [x.strip() for x in s.split("|")]
        if len(parts) < 4:
            continue
        try:
            exec_id = int(parts[1])
        except ValueError:
            continue
        return {
            "name": parts[0],
            "exec_id": exec_id,
            "exec_type": parts[2],
            "upd": parts[3],
        }
    return None


def _priority_sdk_repprep(
    *,
    ename: str,
    instance: dict,
    path: str = "REPPREPDIRECT2",
    form_prep: bool = False,
    cred_fetcher=None,
    node_runner=None,
    **_k,
) -> dict:
    """Run node mjs REPPREPDIRECT2 walk. Password via env only; never logged."""
    if form_prep or path.upper() != "REPPREPDIRECT2":
        return {"ok": False, "path": path, "reason": "refused_non_repprep"}
    root = Path(os.environ.get("AIRC_INSTALL_ROOT") or r"C:\ai\airc")
    pw = _priority.resolve_priority_worker_dir(root)
    mjs_candidates = [
        (pw / "sdk" / "run-repprep-via-exec.mjs") if pw else Path(),
        (pw / "run-repprep-via-exec.mjs") if pw else Path(),
        root / "airc" / "priority-worker" / "sdk" / "run-repprep-via-exec.mjs",
        root / "airc" / "priority-worker" / "run-repprep-via-exec.mjs",
        root / "priority-worker" / "sdk" / "run-repprep-via-exec.mjs",
        root / "priority-worker" / "run-repprep-via-exec.mjs",
        Path(os.environ.get("AIRC_PRIORITY_REPPREP_MJS") or ""),
    ]
    mjs = next((c for c in mjs_candidates if c and c.is_file()), None)
    node = (
        os.environ.get("AIRC_PRIORITY_NODE")
        or os.environ.get("NODE_EXE")
        or "node"
    )
    target = str(instance.get("credentialTarget") or "").strip()
    fetch = cred_fetcher or _priority.fetch_credman_password
    try:
        secret = fetch(target) if target else ""
    except Exception:  # noqa: BLE001
        return {"ok": False, "path": path, "reason": "no_cred"}
    if not secret:
        return {"ok": False, "path": path, "reason": "no_cred"}
    if mjs is None:
        return {"ok": False, "path": path, "reason": "sdk_mjs_missing"}
    env = os.environ.copy()
    env["PRIORITY_SDK_PASSWORD"] = secret
    run = node_runner or subprocess.run
    try:
        proc = run(
            [
                node,
                str(mjs),
                "--name",
                ename,
                "--company",
                str(instance.get("company") or ""),
                "--url",
                str(instance.get("url") or ""),
                "--user",
                str(instance.get("user") or ""),
                "--proc",
                "REPPREPDIRECT2",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "path": path, "reason": f"sdk_exec_failed:{type(e).__name__}"}
    finally:
        env.pop("PRIORITY_SDK_PASSWORD", None)
        secret = None  # noqa: F841
    raw = (proc.stdout or "").strip().splitlines()
    payload = None
    for line in reversed(raw):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "path": path,
            "reason": "sdk_bad_json",
            "node_exit": proc.returncode,
        }
    ok = bool(payload.get("ok"))
    return {"ok": ok, "path": path, "sdk": {"ended": payload.get("ended"), "errors": payload.get("errors")}}


def build_console_prepare_hooks(install_root: str | Path | None = None) -> dict:
    """Wire CredMan + sqlcmd UPD + .prp + node REPPREPDIRECT2 for PRIORITY prepare."""
    pw = _load_priority_worker()
    if pw is None or not hasattr(pw, "build_default_prepare_hooks"):
        return {}
    return pw.build_default_prepare_hooks(
        cred_fetcher=_priority.fetch_credman_password,
        lock_reader=_priority_sqlcmd_lock,
        sdk_exec=lambda **kw: _priority_sdk_repprep(
            cred_fetcher=_priority.fetch_credman_password, **kw
        ),
    )


@dataclass
class UpdateScheduleResult:
    ok: bool
    status: str
    detail: str = ""
    product: str = ""
    version: str | None = None
    job_id: str = ""

    def reply_line(self) -> str:
        ver = self.version or ""
        qid = (self.job_id or "").strip().lower() or "00000000"
        bits = [f"UPDATE {self.status}", f"id={qid}", f"product={self.product or '?'}"]
        if ver:
            bits.append(f"version={ver}")
        if self.detail:
            bits.append(self.detail)
        # FR #5584: ``current`` (already up to date) is success with
        # ``UPDATE current`` wording --- not ``UPDATE accepted`` / exit=1.
        if self.ok and self.status != "current":
            bits[0] = "UPDATE accepted"
            bits.insert(2, f"status={self.status}")
        body = " ".join(bits)[:400]
        exit_code = 0 if self.ok else 1
        return f"{body}\nDONE id={qid} exit={exit_code}"


_UPDATE_INTAKE_STATUSES = frozenset(
    {
        "updater-missing",
        "spawn-failed",
        "asset-url-rejected",
        "no-matching-asset",
        "no-sha256-asset",
        "release-lookup-failed",
        "rejected-product",
    }
)


def _redact_update_intake_text(text: str) -> str:
    """FR #5279 / MRB #5326: never put secrets on intake title/body (python path)."""
    try:
        from crash_report import redact

        return redact(text or "")
    except Exception:
        return re.sub(
            r"(?i)(password|token|secret|authorization)\s*[=:]\s*\S+",
            r"\1=<redacted>",
            text or "",
        )


def report_update_failure_intake(
    *,
    product: str,
    result: str,
    tag: str = "",
    detail: str = "",
    dry_run: bool = False,
) -> dict:
    """FR #5279 / #5766 / #5775: native shared fail-intake (packaged-safe).

    Dedupe key: ``airc-update-fail|<machine>|update|<version>|<result>``
    (version slot prefers tag, else installed airc version).
    """
    try:
        import airc_fail_intake as _fail

        out = _fail.report_update_status_failure(
            product=product,
            result=result,
            tag=tag,
            detail=detail,
            dry_run=dry_run,
        )
        # Preserve legacy callers that read idempotency_key.
        if isinstance(out, dict) and "idempotency_key" not in out and out.get("dedupe_key"):
            out["idempotency_key"] = out["dedupe_key"]
        return out
    except Exception as exc:  # noqa: BLE001 - never break UPDATE path
        return {
            "ok": False,
            "error": type(exc).__name__,
            "product": product,
            "result": result,
            "dry_run": dry_run,
        }


def _is_frozen_airc_runtime() -> bool:
    """True under PyInstaller airc.exe (FR #2949)."""
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def resolve_fleet_update_install_root(explicit: str | None = None) -> str:
    """Install tree for UPDATE Check (frozen-aware; FR #2949).

    Prefer an explicit root when it already contains the updater. Otherwise
    re-resolve from ``sys.executable`` under frozen builds so ``_MEI*`` parents
    of ``__file__`` are never used as InstallRoot.
    """
    name = "Update-BobiverseService.ps1"

    def _has_updater(root: Path) -> bool:
        return (root / "scripts" / name).is_file() or (root / name).is_file()

    if explicit:
        exp = Path(explicit)
        if _has_updater(exp):
            return str(exp.resolve())
    if _is_frozen_airc_runtime():
        exe = Path(sys.executable).resolve()
        # Pack stages ``airc\\airc.exe`` under the install root.
        cand = exe.parent.parent if exe.parent.name.lower() == "airc" else exe.parent
        if _has_updater(cand):
            return str(cand.resolve())
        return str(cand.resolve())
    if explicit:
        return str(Path(explicit).resolve())
    # Source / staged: parent of scripts/ (product tree).
    return str(Path(__file__).resolve().parents[1])


def _find_update_bobiverse_script(install_root: str, updater_script: str | None = None) -> Path | None:
    """Locate Update-BobiverseService.ps1 under the install tree (FR #2949)."""
    name = "Update-BobiverseService.ps1"
    candidates: list[Path] = []
    if updater_script:
        candidates.append(Path(updater_script))
    root = Path(install_root)
    candidates.append(root / "scripts" / name)
    candidates.append(root / name)
    # Source tree / non-frozen fallbacks (never preferred under frozen _MEI).
    if not _is_frozen_airc_runtime():
        candidates.append(Path(__file__).resolve().parent / name)
        candidates.append(
            Path(__file__).resolve().parents[2] / "common" / "scripts" / name
        )
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0] if candidates else None


def schedule_fleet_update(
    product: str,
    version: str | None = None,
    *,
    install_root: str | None = None,
    service_name: str | None = None,
    updater_script: str | None = None,
    state_dir: str | None = None,
    dry_run: bool = False,
    no_spawn: bool = False,
) -> UpdateScheduleResult:
    """Schedule ``Update-BobiverseService.ps1 -Mode Check`` (detached apply).

    Never runs ``msiexec`` in this process. The Check mode writes a plan and
    starts a scheduled-task / WMI helper; msiexec lives only in Apply.
    """
    product = (product or "").strip().lower()
    if product not in UPDATE_PRODUCTS:
        r = UpdateScheduleResult(False, "rejected-product", product=product, version=version)
        _maybe_intake_update_failure(r)
        return r
    install_root = resolve_fleet_update_install_root(install_root)
    script = _find_update_bobiverse_script(install_root, updater_script)
    if script is None or not script.is_file():
        r = UpdateScheduleResult(
            False,
            "updater-missing",
            detail=str(script or (Path(install_root) / "scripts" / "Update-BobiverseService.ps1")),
            product=product,
            version=version,
        )
        _maybe_intake_update_failure(r)
        return r
    if not service_name:
        service_name = {"bob": "ircBob", "jeeves": "ircJeeves"}.get(product, "Airc")
    ps = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32\WindowsPowerShell\v1.0\powershell.exe"
    if not Path(ps).is_file():
        ps = shutil_which_powershell()
    args = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Product",
        product,
        "-Mode",
        "Check",
        "-InstallRoot",
        str(install_root),
        "-ServiceName",
        service_name,
        "-ForceCheck",
    ]
    if version:
        args += ["-TargetVersion", version]
    if state_dir:
        args += ["-StateDir", str(state_dir)]
    if dry_run:
        args.append("-DryRun")
    if no_spawn:
        args.append("-NoSpawn")
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=90)
    except Exception as e:  # noqa: BLE001 - surface to IRC as spawn-failed
        r = UpdateScheduleResult(
            False,
            "spawn-failed",
            detail=type(e).__name__,
            product=product,
            version=version,
        )
        _maybe_intake_update_failure(r)
        return r
    out = ((p.stdout or "") + "\n" + (p.stderr or "")).lower()
    # Prefer updater log phrases when present in stdout (Write-Host).
    status = "check-ran"
    ok = p.returncode == 0
    for key in (
        "update-scheduled",
        "scheduled-nospawn",
        "would-update",
        "skipped-pending",
        "blocked-loop-guard",
        "skipped-optout",
        "asset-url-rejected",
        "no-matching-asset",
        "no-sha256-asset",
        "release-lookup-failed",
        "spawn-failed",
        "cooldown",
        "current",
        "throttled",
    ):
        if key in out.replace("result=", " "):
            status = key
            break
    if status in {"update-scheduled", "scheduled-nospawn", "would-update"}:
        ok = True
        if status == "would-update":
            status = "scheduled"
        elif status == "update-scheduled":
            status = "scheduled"
    elif status == "current":
        # FR #5584: no-op Check (local == latest) is success; callers must not
        # treat DONE exit=1 as a failure when there is nothing to install.
        ok = True
    elif status in {
        "skipped-pending",
        "blocked-loop-guard",
        "skipped-optout",
        "cooldown",
        "throttled",
        # FR #5670: lookup/asset failures must DONE exit!=0 even if updater rc=0.
        "asset-url-rejected",
        "no-matching-asset",
        "no-sha256-asset",
        "release-lookup-failed",
        "spawn-failed",
    }:
        ok = False
    detail = ""
    for line in (p.stdout or "").splitlines()[::-1]:
        if "self-update:" in line.lower() or "result=" in line.lower():
            detail = line.strip()[:200]
            break
    if not detail and p.returncode != 0:
        detail = f"exit={p.returncode}"
    r = UpdateScheduleResult(ok, status, detail=detail, product=product, version=version)
    _maybe_intake_update_failure(r)
    return r


def _maybe_intake_update_failure(result: UpdateScheduleResult) -> None:
    if result.ok or result.status not in _UPDATE_INTAKE_STATUSES:
        return
    try:
        report_update_failure_intake(
            product=result.product or "",
            result=result.status,
            tag=result.version or "",
            detail=result.detail or "",
        )
    except Exception:
        pass


def shutil_which_powershell() -> str:
    import shutil

    return shutil.which("powershell.exe") or shutil.which("powershell") or "powershell.exe"


def shop_channel(machine: str | None = None) -> str:
    mid = machine_id(machine)
    return f"#{mid}"


def _fit_nick(stem: str, suffix: str = "") -> str:
    """Build an IRC nick <= IRC_NICK_MAX, preferring to keep ``suffix`` intact."""
    stem = (stem or "unknown").strip("-_") or "unknown"
    suffix = suffix or ""
    max_stem = IRC_NICK_MAX - len(suffix)
    if max_stem < 1:
        return (stem + suffix)[:IRC_NICK_MAX]
    return (stem[:max_stem] + suffix)[:IRC_NICK_MAX]


def machine_console_nick(machine: str | None = None) -> str:
    """Nick when ``#{machine}`` is ChanServ-registered: ``{machine}_console``."""
    mid = machine_id(machine)
    return _fit_nick(mid, "_console")


def domain_lobby_nick(machine: str | None = None, suffix: int | None = None) -> str:
    """Nick for domain/workgroup lobby: ``{machine}`` or ``{machine}_{n}`` (n>=1)."""
    mid = machine_id(machine)
    if suffix is None or int(suffix) <= 0:
        return _fit_nick(mid, "")
    return _fit_nick(mid, f"_{int(suffix)}")


def console_nick(machine: str | None = None, explicit: str | None = None) -> str:
    """IRC nick for the console seat.

    Default is ``{machine}_console`` (registered-shop / provisional connect).
    Pass explicit ``console`` only on a single-console network; ``auto`` uses default.
    """
    if explicit and explicit.strip() and explicit.strip().lower() != "auto":
        return explicit.strip()[:IRC_NICK_MAX]
    return machine_console_nick(machine)


def domain_or_workgroup_id(override: str | None = None) -> str:
    """Windows domain NetBIOS name, or workgroup, sanitized for ``#{id}``.

    Order: explicit / ``AIRC_CONSOLE_DOMAIN`` → ``USERDNSDOMAIN`` first label →
    ``USERDOMAIN`` when it differs from ``COMPUTERNAME`` → short NetGetJoinInformation
    probe → ``USERDOMAIN`` → ``workgroup``. Never blocks unbounded on WMI.
    """
    if override and override.strip():
        return _sanitize_id(override)
    env = (os.environ.get("AIRC_CONSOLE_DOMAIN") or "").strip()
    if env:
        return _sanitize_id(env)

    dns = (os.environ.get("USERDNSDOMAIN") or "").strip()
    if dns:
        return _sanitize_id(dns.split(".")[0])

    userdomain = (os.environ.get("USERDOMAIN") or "").strip()
    computer = (os.environ.get("COMPUTERNAME") or "").strip()
    if userdomain and computer and userdomain.upper() != computer.upper():
        return _sanitize_id(userdomain)

    joined = _net_get_join_id(timeout_s=2.0)
    if joined:
        return joined

    if userdomain:
        return _sanitize_id(userdomain)
    return "workgroup"


def domain_channel(domain: str | None = None) -> str:
    return f"#{domain_or_workgroup_id(domain)}"


def _net_get_join_id(timeout_s: float = 2.0) -> str | None:
    """Best-effort NetGetJoinInformation (domain or workgroup name)."""
    if os.name != "nt":
        return None
    box: dict[str, str | None] = {"name": None}

    def worker() -> None:
        try:
            import ctypes
            from ctypes import wintypes

            netapi = ctypes.WinDLL("netapi32")
            NetGetJoinInformation = netapi.NetGetJoinInformation
            NetGetJoinInformation.argtypes = [
                wintypes.LPCWSTR,
                ctypes.POINTER(wintypes.LPWSTR),
                ctypes.POINTER(ctypes.c_int),
            ]
            NetGetJoinInformation.restype = wintypes.DWORD
            NetApiBufferFree = netapi.NetApiBufferFree
            NetApiBufferFree.argtypes = [wintypes.LPVOID]
            NetApiBufferFree.restype = wintypes.DWORD

            buf = wintypes.LPWSTR()
            join_type = ctypes.c_int()
            # NetSetupUnknownStatus=0, Workgroup=1, Domain=3 (values vary by SDK;
            # we only need the name string).
            rc = NetGetJoinInformation(None, ctypes.byref(buf), ctypes.byref(join_type))
            if rc == 0 and buf.value:
                box["name"] = str(buf.value)
            if buf:
                NetApiBufferFree(buf)
        except Exception:
            return

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout_s)
    if box["name"]:
        return _sanitize_id(box["name"])
    return None


def parse_chanserv_info(text: str, channel: str) -> ShopProbeResult:
    """Classify a ChanServ INFO NOTICE for ``channel``.

    Returns ``registered``, ``missing``, or ``unknown`` (keep waiting / treat as
    missing after probe timeout).
    """
    body = (text or "").strip()
    if not body:
        return "unknown"
    t = body.lower()
    ch = (channel or "").lower().lstrip("#")
    if any(
        s in t
        for s in (
            "is not registered",
            "isn't registered",
            "isnt registered",
            "not registered",
        )
    ):
        return "missing"
    if "no such channel" in t and ch and ch in t.replace("#", ""):
        return "missing"
    # Atheme / Ergo-style success. Ergo: "Channel #foo is registered" (no colon).
    if "registered:" in t or "registered on" in t or "registered at" in t:
        return "registered"
    if "is registered" in t:
        return "registered"
    if "information on" in t and ch and ch in t.replace("#", ""):
        return "registered"
    if "founder:" in t and ch and ch in t.replace("#", ""):
        return "registered"
    return "unknown"


def is_channel_target(target: str) -> bool:
    t = (target or "").strip()
    return bool(t) and t[0] in "#&+"


def nick_matches_pattern(pattern: str, nick: str, machine: str | None = None) -> bool:
    """True if IRC/client ping pattern matches this console (#298).

    Examples: ``*``, ``flam*``, ``flamingo_console``, ``flamingo``, ``flamingo_1``.
    """
    pat = (pattern or "").strip()
    if not pat or pat == "*":
        return True
    n = (nick or "").strip().lower()
    mid = machine_id(machine)
    candidates = {
        n,
        mid,
        f"console-{mid}",
        f"{mid}_console",
        machine_console_nick(mid),
        domain_lobby_nick(mid),
        f"#{mid}",
    }
    p = pat.lower()
    # Allow #channel-style patterns too.
    for c in candidates:
        if not c:
            continue
        if fnmatch.fnmatchcase(c, p) or fnmatch.fnmatchcase(c.lstrip("#"), p.lstrip("#")):
            return True
        # Prefix match without wildcard: "flam" matches flamingo / flamingo_console
        if "*" not in p and "?" not in p and (c.startswith(p) or c.lstrip("#").startswith(p)):
            return True
    return False


def parse_ctcp_ping(text: str) -> str | None:
    """Return CTCP PING payload (possibly empty string) or None if not CTCP PING."""
    m = _CTCP_PING_RE.match(text or "")
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else ""


def parse_ctcp_message(text: str) -> str | None:
    """FR #5614: any CTCP tag (VERSION, ACTION, ...) or None."""
    m = _CTCP_ANY_RE.match(text or "")
    if not m:
        return None
    return (m.group(1) or "").upper()


def format_known_verb_usage(
    job_id: str,
    verb: str,
    allowed: str,
    unknown_flag: str | None = None,
) -> str:
    """FR #5614 / #5533: usage reply, never PowerShell."""
    qid = (job_id or "").strip().lower() or "00000000"
    if unknown_flag:
        err = f"err id={qid} seq=1 code=usage unknown-flag={unknown_flag}"
    else:
        err = f"err id={qid} seq=1 code=usage {verb} {allowed}"
    return f"{err}\nDONE id={qid} exit=2"


def parse_ping_command(text: str) -> str | None:
    """Return ping pattern (``*`` if bare ``ping``) or None if not a ping command."""
    m = _PING_CMD_RE.match(text or "")
    if not m:
        return None
    return (m.group(1) or "*").strip()


def is_bob_fleet_nick(nick: str) -> bool:
    """True for fleet ear nick shape ``bob-{machinename}`` (issue #302).

    FR #3286: this is a naming helper only - never treat the pattern as authentication.
    """
    return bool(_BOB_FLEET_NICK_RE.match((nick or "").strip()))


# FR #3401: IRC channel status prefixes that grant client remote control.
_CHAN_PRIV_PREFIXES = frozenset("@%&~")  # op, half-op, admin, owner (never +voice alone)


@dataclass
class ChannelMemberMap:
    """Live NAMES/MODE/JOIN/PART map for the selected control channel (FR #3401)."""

    channel: str = ""
    synced: bool = False
    _members: dict[str, str] = field(default_factory=dict)  # nick.lower -> prefix chars

    def clear(self) -> None:
        self._members.clear()
        self.synced = False

    def set_channel(self, channel: str) -> None:
        """Bind the control channel and always drop prior prefixes (FR #3511).

        Same-channel reconnect used to keep ``synced`` and stale ``@``/``%`` for
        nicks that left while the console was offline. Always clear so auth
        refuses until a fresh NAMES/366 cycle.
        """
        ch = (channel or "").strip()
        # FR #3511: clear even when the channel name is unchanged (reconnect).
        self.clear()
        self.channel = ch

    def apply_names(self, names_blob: str) -> None:
        for tok in (names_blob or "").split():
            prefixes = ""
            nick = tok
            while nick and nick[0] in "@%&~+":
                if nick[0] in _CHAN_PRIV_PREFIXES:
                    prefixes += nick[0]
                nick = nick[1:]
            if nick:
                self._members[nick.lower()] = prefixes

    def mark_synced(self) -> None:
        self.synced = True

    def known(self, nick: str) -> bool:
        return (nick or "").strip().lower() in self._members

    def has_chan_priv(self, nick: str) -> bool:
        p = self._members.get((nick or "").strip().lower(), "")
        return any(c in _CHAN_PRIV_PREFIXES for c in p)

    def chan_priv_mode(self, nick: str) -> str | None:
        """Highest control-channel priv as ``+q``/``+a``/``+o``/``+h``, or None (FR #4067)."""
        p = self._members.get((nick or "").strip().lower(), "")
        # Owner > admin > op > half-op (voice never grants control).
        for pref, mode in (("~", "+q"), ("&", "+a"), ("@", "+o"), ("%", "+h")):
            if pref in p:
                return mode
        return None

    def on_join(self, nick: str, prefixes: str = "") -> None:
        n = (nick or "").strip()
        if not n:
            return
        cleaned = "".join(c for c in (prefixes or "") if c in _CHAN_PRIV_PREFIXES)
        self._members[n.lower()] = cleaned

    def on_part(self, nick: str) -> None:
        self._members.pop((nick or "").strip().lower(), None)

    def on_kick(self, nick: str) -> None:
        self.on_part(nick)

    def on_quit(self, nick: str) -> None:
        self.on_part(nick)

    def on_nick(self, old: str, new: str) -> None:
        o = (old or "").strip().lower()
        n = (new or "").strip()
        if not o or not n:
            return
        prefs = self._members.pop(o, None)
        if prefs is not None:
            self._members[n.lower()] = prefs

    def on_mode(self, channel: str, modes: str, mode_args: list[str]) -> None:
        ch = (channel or "").strip().lower().lstrip("#")
        mine = (self.channel or "").strip().lower().lstrip("#")
        if mine and ch and ch != mine:
            return
        args = list(mode_args or [])
        arg_i = 0
        sign = "+"
        for ch_m in modes or "":
            if ch_m in "+-":
                sign = ch_m
                continue
            if ch_m in "ohvaqOHVAQ":
                if arg_i >= len(args):
                    break
                nick = (args[arg_i] or "").strip()
                arg_i += 1
                if not nick:
                    continue
                key = nick.lower()
                prefs = list(self._members.get(key, ""))
                # Map mode letter -> prefix char.
                letter = ch_m.lower()
                pref = {"o": "@", "h": "%", "v": "+", "a": "&", "q": "~"}.get(letter)
                if pref is None:
                    continue
                if letter == "v":
                    # Voice alone never grants client control; track but ignore for auth.
                    continue
                if sign == "+":
                    if pref not in prefs:
                        prefs.append(pref)
                else:
                    prefs = [p for p in prefs if p != pref]
                self._members[key] = "".join(prefs)
            elif ch_m in "klbeI":
                # Modes that consume a parameter - skip the arg.
                if arg_i < len(args):
                    arg_i += 1


# FR #3834: fixed registered fallback control channel (replaces #<domain|workgroup>).
WONDERLAND_CHANNEL = "#wonderland"


def wonderland_channel() -> str:
    """FR #3834: single shared client fallback control channel."""
    return WONDERLAND_CHANNEL


def control_channel_reason(mode: str) -> str:
    """FR #3401 / #3834: human reason token for control-channel selection logs."""
    m = (mode or "").strip().lower()
    if m == "registered":
        return "registered-machine"
    # wonderland + legacy domain-lobby alias both log wonderland-fallback
    return "wonderland-fallback"


def control_channel_log_line(channel: str, mode: str) -> str:
    """FR #3401 / #3834: ``INFO control-channel=#name reason=registered-machine|wonderland-fallback``."""
    return (
        f"INFO control-channel={channel} reason={control_channel_reason(mode)}"
    )


def normalize_shop_mode(mode: str | None) -> str:
    """FR #3834: auto|registered|wonderland; domain-lobby is a compat alias for wonderland."""
    m = (mode or "auto").strip().lower()
    if m == "domain-lobby":
        return "wonderland"
    if m in {"auto", "registered", "wonderland"}:
        return m
    return "auto"


def resolve_crash_report_enabled_for_install(
    *,
    prior: bool | None,
    explicit: bool | None,
    profile: str | None = None,
) -> bool:
    """FR #3401: client defaults crash reports ON; workstation defaults OFF.

    Explicit MSI/CLI wins. Fleet fresh default follows prior when set, else ON
    when shell is remote-capable is handled by Install-Airc.ps1; this helper is
    the profile-aware default used by tests and shared callers.
    """
    if explicit is not None:
        return bool(explicit)
    prof = (profile or "").strip().lower()
    if prof == "workstation":
        return False
    if prof == "client":
        return True
    if prior is not None:
        return bool(prior)
    return True


@dataclass
class AuthPolicy:
    """Authorise by live IRC channel status only (FR #3401 / #3639).

    A sender may drive the console when it holds ops (``+o``) or half-ops (``+h``)
    -- or higher (``+a`` / ``+q``) -- in the console's control channel, per the live
    NAMES/MODE/JOIN/PART map. There is no operators.txt, no fleet-operators roster
    and no nick allow-list on any profile (fleet, workstation or client). Voice is
    not enough. Auth refuses until NAMES/366 has synced the map (FR #3511), and the
    console never authorises its own nick.

    ``account_map`` is only the IRCv3 ``account`` tag cache used for logging; it is
    never an allow-list.
    """

    members: ChannelMemberMap | None = None
    self_nicks: set[str] = field(default_factory=set)
    account_map: AccountMap | None = None
    # FR #3639: the only mode. Kept as a field so callers / logs can read it.
    auth_mode: Literal["irc_ops"] = "irc_ops"

    def deny_reason(self, nick: str, account: str | None = None) -> str:
        """Why ``allow`` is False (for auth-deny logs; never includes command body)."""
        n = (nick or "").strip().lower()
        if not n:
            return "no-nick"
        if n in {x.lower() for x in self.self_nicks}:
            return "self-nick"
        if self.members is None or not self.members.synced:
            return "channel-state-unknown"
        if not self.members.has_chan_priv(n):
            return "not-op"
        return ""

    def allow(self, nick: str, account: str | None = None) -> bool:
        n = (nick or "").strip().lower()
        if not n:
            return False
        if n in {x.lower() for x in self.self_nicks}:
            return False
        if self.members is None or not self.members.synced:
            return False
        return self.members.has_chan_priv(n)

    def allow_detail(self, nick: str, account: str | None = None) -> dict:
        """FR #4067: ``{ok, mode, channel}`` for auth-allow audit (no command body)."""
        channel = None
        if self.members is not None:
            channel = (self.members.channel or "").strip() or None
        ok = self.allow(nick, account)
        mode = None
        if ok and self.members is not None:
            mode = self.members.chan_priv_mode(nick)
        return {"ok": ok, "mode": mode, "channel": channel}


def format_auth_allow_log(
    *,
    nick: str,
    account: str | None,
    channel: str | None,
    mode: str | None,
    action: str,
) -> str:
    """FR #4067: ``auth-allow nick=… account=… channel=… mode=… action=shell|job|pipe|update``."""
    return (
        f"auth-allow nick={nick or '-'} account={account or '-'} "
        f"channel={channel or '-'} mode={mode or '-'} action={action}"
    )


def resolve_channel_commands(cfg: dict | None) -> bool:
    """FR #3401 / #3639: read commands from the control channel only on the client profile.

    Fleet and workstation consoles take commands by DM only and stay silent in channel
    (the fleet control channel carries chair / git-claim traffic). A missing or unknown
    profile is treated as fleet (DM only) - fail safe.
    """
    prof = str((cfg or {}).get("profile") or "").strip().lower()
    return prof == "client"


# FR #3774: fleet lobby channel for optional client presence-only JOIN.
FLEET_PRESENCE_CHANNEL = "#bobiverse"


def normalize_irc_channel(name: str) -> str:
    """Return ``#lowercase`` channel id, or ``\"\"`` when empty."""
    s = (name or "").strip()
    if not s:
        return ""
    return "#" + s.lstrip("#").lower()


def same_irc_channel(a: str, b: str) -> bool:
    """True when two IRC channel names refer to the same channel (FR #3774)."""
    return normalize_irc_channel(a) == normalize_irc_channel(b) and bool(
        normalize_irc_channel(a)
    )


def _coerce_presence_channel_list(raw: object) -> list[str] | None:
    """Parse presence_channels from JSON list / string; ``None`` means key absent."""
    if raw is None:
        return None
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",")]
        return [normalize_irc_channel(p) for p in parts if normalize_irc_channel(p)]
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for item in raw:
            ch = normalize_irc_channel(str(item or ""))
            if ch and ch not in out:
                out.append(ch)
        return out
    return None


def resolve_presence_channels(
    cfg: dict | None = None,
    *,
    profile: str | None = None,
    prefer_env: bool = True,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Extra channels to JOIN for presence only (FR #3774). Never command targets.

    Resolution order:
    1. ``presence_channels`` in ``airc.json`` when the key is present (including ``[]``).
    2. Else ``AIRC_PRESENCE_CHANNELS`` (comma-separated; empty string = none) when set.
    3. Else no extra presence channels (FR #5190: client never auto-joins
       ``#bobiverse``; control channel is shop or ``#wonderland``).
    """
    data = cfg or {}
    environ = env if env is not None else os.environ
    from_env = bool(prefer_env and "AIRC_PRESENCE_CHANNELS" in environ)
    if "presence_channels" in data:
        parsed = _coerce_presence_channel_list(data.get("presence_channels"))
        out = parsed if parsed is not None else []
    elif from_env:
        out = _coerce_presence_channel_list(environ.get("AIRC_PRESENCE_CHANNELS") or "") or []
    else:
        out = []
    # FR #5190: drop leftover FR #3774 client default unless env opted in.
    prof = (profile or str(data.get("profile") or "")).strip().lower()
    if prof == "client" and not from_env:
        out = [c for c in out if c != FLEET_PRESENCE_CHANNEL]
    return out


def legacy_operator_input_log_lines(args: object, cfg: dict | None) -> list[str]:
    """FR #3639: INFO lines for retired operator-list inputs (accepted, never read).

    Old NSSM AppParameters / airc.json may still carry ``--operators-file``,
    ``--operators``, ``--auth-mode operators``, ``--require-account`` / ``--accounts``
    or ``auth_mode=operators``. They are accepted so an upgraded service still starts,
    but authorisation is live control-channel +o/+h only.
    """
    out: list[str] = []
    if getattr(args, "operators_file", None):
        out.append("INFO FR #3639 ignoring --operators-file (no operators list; channel +o/+h auth)")
    if list(getattr(args, "operators", None) or []):
        out.append("INFO FR #3639 ignoring --operators (no operators list; channel +o/+h auth)")
    cli_mode = str(getattr(args, "auth_mode", None) or "").strip().lower()
    cfg_mode = str((cfg or {}).get("auth_mode") or "").strip().lower()
    if cli_mode == "operators" or cfg_mode == "operators":
        out.append("INFO FR #3639 auth_mode=operators is retired; using irc_ops")
    if getattr(args, "require_account", False) or list(getattr(args, "accounts", None) or []):
        out.append("INFO FR #3639 ignoring --require-account/--accounts for auth (channel +o/+h only)")
    return out


@dataclass(frozen=True)
class ConsoleCapabilities:
    """FR #3287: install-time remote capability gates (survive MSI upgrade).

    ``shell_mode``: ``off`` = STATUS/VERSION/ping only; ``operators`` = FR #75 shell for auth nicks.
    ``jobs`` / ``update`` / ``extension``: finer gates when shell is ``operators``.

    FR #3764: ``update`` is the **remote** UPDATE verb (ops-gated IRC command). It is
    not automatic MSI self-update / git sync --- those are ``self_update`` /
    ``sync_from_repo`` in ``AircStartUpdatePolicy`` (client defaults both off).

    FR #5295: ``extension`` gates the remote EXTENSION verb. Fleet default ``on``;
    client and workstation profiles default ``off``. ``update=off`` still refuses
    EXTENSION (parent S8). Cap-off reply is ``DONE exit=126 extension-disabled``.
    """

    shell_mode: Literal["off", "operators"] = "operators"
    jobs: Literal["off", "on"] = "on"
    update: Literal["on", "off"] = "on"
    extension: Literal["on", "off"] = "on"
    require_account: bool = False
    accounts: tuple[str, ...] = ()

    def log_line(self) -> str:
        # FR #3764: spell out remote UPDATE so client logs are not read as auto self-update.
        return (
            f"INFO capabilities shell={self.shell_mode} jobs={self.jobs} "
            f"update={self.update} (remote UPDATE; not auto self-update) "
            f"extension={self.extension} "
            f"require_account={int(bool(self.require_account))} "
            f"accounts={len(self.accounts)}"
        )


def normalize_shell_cli(value: str | None) -> tuple[str | None, str | None]:
    """Return ``(shell_mode, powershell_path)`` for a ``--shell`` CLI token.

    FR #3287: exact ``off`` / ``operators`` are capability modes; any other value
    remains the PowerShell executable path (legacy ``--shell``).
    """
    raw = (value or "").strip()
    if not raw:
        return None, None
    low = raw.lower()
    if low in SHELL_MODE_TOKENS:
        return low, None
    return None, raw


def _norm_on_off(value: str | None, *, default: str) -> str:
    raw = (value or "").strip().lower()
    if raw in {"on", "off"}:
        return raw
    return default


def detect_bob_machine(
    *,
    install_root: Path | str | None = None,
    bob_root: Path | str | None = None,
    service_present: bool | None = None,
) -> bool:
    """True when this box has a Bob install beside airc (or ircBob service).

    FR #4030: fleet Bob machines default remote shell ON (``operators``).
    ``install_root`` is typically ``<ai root>\\airc``; sibling ``bob\\VERSION`` counts.
    """
    if service_present is True:
        return True
    roots: list[Path] = []
    if bob_root:
        roots.append(Path(bob_root))
    if install_root:
        ir = Path(install_root)
        roots.append(ir.parent / "bob")
    elif not bob_root:
        # Live default fleet layout only when caller did not pin roots.
        roots.append(Path(r"C:\\ai\\bob"))
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if (root / "VERSION").is_file():
                return True
        except OSError:
            continue
    return False


def warn_shell_off_on_bob_line(
    *,
    shell_mode: str,
    is_bob_machine: bool,
    shell_source: str | None = None,
    profile: str | None = None,
) -> str | None:
    """FR #4030: visible WARN when shell=off on a Bob machine (do not hide)."""
    mode = (shell_mode or "").strip().lower()
    if mode != "off" or not is_bob_machine:
        return None
    src = (shell_source or "unknown").strip() or "unknown"
    return (
        f"WARN FR #4030 capabilities shell=off on Bob machine "
        f"source={src} (explicit AIRC_SHELL/ShellMode=off only; else expect operators)"
    )


def resolve_shell_mode_for_install(
    *,
    prior_shell: str | None,
    explicit: str | None,
    had_prior_service: bool,
    profile: str | None = None,
    is_bob_machine: bool = False,
    prior_shell_source: str | None = None,
    prior_shell_explicit: bool | None = None,
) -> str:
    """Resolve install-time shell mode.

    FR #3393: ``AIRC_PROFILE=workstation`` defaults ``off`` unless explicit.
    FR #3401: ``AIRC_PROFILE=client`` defaults ``operators``.
    FR #4030 / 1.0.0: fleet fresh default is ``operators`` (was ``off``); Bob detect is
    belt-and-braces. Migrate legacy ``shell_source=fresh-default`` / unmarked ``off``
    unless ``shell_source=explicit`` / ``shell_explicit`` / MSI ``AIRC_SHELL=off``.
    """
    exp = (explicit or "").strip().lower()
    if exp in SHELL_MODE_TOKENS:
        return exp
    prof = (profile or "").strip().lower()
    if prof == "workstation":
        return "off"
    if prof == "client":
        return "operators"
    prior = (prior_shell or "").strip().lower()
    src = (prior_shell_source or "").strip().lower()
    explicit_off = prior_shell_explicit is True or src == "explicit"
    if is_bob_machine:
        if prior == "off" and explicit_off:
            return "off"
        return "operators"
    if prior == "off":
        if explicit_off:
            return "off"
        # Legacy fresh-default / unmarked off (flamingo / walrus 1.0.0 class).
        if src in ("", "fresh-default") or prior_shell_source is None:
            return "operators"
        return "off"
    if prior in SHELL_MODE_TOKENS:
        return prior
    # Fleet fresh / upgrade default (FR #4030): operators.
    # had_prior_service kept for call-site compat (both paths now operators).
    if had_prior_service:
        return "operators"
    return "operators"


def load_capabilities(
    *,
    install_root: Path | str | None = None,
    console_home: Path | str | None = None,
    cli_shell: str | None = None,
    cli_shell_mode: str | None = None,
    cli_jobs: str | None = None,
    cli_update: str | None = None,
    cli_extension: str | None = None,
    cli_require_account: bool | None = None,
    cli_accounts: list[str] | tuple[str, ...] | None = None,
    default_shell_mode: str = "operators",
) -> ConsoleCapabilities:
    """Merge CLI + ``config\\airc.json`` (install root, then console home)."""
    data: dict = {}
    roots: list[Path] = []
    if install_root:
        roots.append(Path(install_root))
    if console_home:
        roots.append(Path(console_home))
    for root in roots:
        for rel in ("config/airc.json", "airc.json"):
            path = root / rel
            if not path.is_file():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            if isinstance(raw, dict):
                data.update(raw)
                break

    mode_cli, _path = normalize_shell_cli(cli_shell)
    mode = (cli_shell_mode or mode_cli or data.get("shell") or data.get("shell_mode") or default_shell_mode)
    mode = str(mode).strip().lower()
    if mode not in SHELL_MODE_TOKENS:
        mode = default_shell_mode

    jobs = _norm_on_off(cli_jobs if cli_jobs is not None else data.get("jobs"), default="on")
    update = _norm_on_off(
        cli_update if cli_update is not None else data.get("update"), default="on"
    )
    prof = str(data.get("profile") or "").strip().lower()
    ext_default = "off" if prof in {"client", "workstation"} else "on"
    extension = _norm_on_off(
        cli_extension if cli_extension is not None else data.get("extension"),
        default=ext_default,
    )

    req = cli_require_account
    if req is None:
        req = bool(data.get("require_account"))
    accts: list[str] = []
    if cli_accounts:
        accts.extend(str(x).strip() for x in cli_accounts if str(x).strip())
    cfg_accts = data.get("accounts")
    if isinstance(cfg_accts, str):
        accts.extend(x.strip() for x in re.split(r"[,;\s]+", cfg_accts) if x.strip())
    elif isinstance(cfg_accts, (list, tuple)):
        accts.extend(str(x).strip() for x in cfg_accts if str(x).strip())
    # dedupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for a in accts:
        k = a.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(a)

    return ConsoleCapabilities(
        shell_mode=mode,  # type: ignore[arg-type]
        jobs=jobs,  # type: ignore[arg-type]
        update=update,  # type: ignore[arg-type]
        extension=extension,  # type: ignore[arg-type]
        require_account=bool(req),
        accounts=tuple(uniq),
    )


def _read_airc_json_dict(install_root: Path | str | None) -> dict:
    """Load ``config\\airc.json`` (or ``airc.json``) from an install root."""
    if not install_root:
        return {}
    root = Path(install_root)
    for rel in ("config/airc.json", "airc.json"):
        path = root / rel
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict):
            return raw
    return {}


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class AircStartUpdatePolicy:
    """FR #3289: whether service start may git-sync ``main`` or run signed MSI self-update.

    Fresh MSI default: ``sync_from_repo=False`` (unsigned main must not run as SYSTEM).
    ``self_update`` defaults True (sha256-checked release MSI path); FR #3393
    ``AIRC_PROFILE=workstation`` install writes False unless MSI sets it.
    """

    sync_from_repo: bool = False
    self_update: bool = True

    def log_lines(self) -> tuple[str, ...]:
        return (
            f"INFO sync-from-repo={'on' if self.sync_from_repo else 'off'} (config)",
            f"INFO self-update={'on' if self.self_update else 'off'} (config)",
        )


def load_start_update_policy(
    install_root: Path | str | None = None,
    *,
    env: dict[str, str] | None = None,
) -> AircStartUpdatePolicy:
    """Merge env + ``config\\airc.json`` into start-hook policy (FR #3289).

    Precedence:
    - ``BOBIVERSE_NO_UPDATE=1`` → both off
    - ``BOBIVERSE_SYNC_FROM_REPO=0|1`` / ``BOBIVERSE_SELF_UPDATE=0|1`` when set
    - ``BOB_AUTOUPDATE=0`` → self_update off (updater also honours this)
    - ``airc.json`` ``sync_from_repo`` / ``self_update``
    - defaults: sync off, self_update on
    """
    e = env if env is not None else os.environ
    if (e.get("BOBIVERSE_NO_UPDATE") or "").strip() == "1":
        return AircStartUpdatePolicy(sync_from_repo=False, self_update=False)

    data = _read_airc_json_dict(install_root)
    sync = _coerce_bool(data.get("sync_from_repo"), default=False)
    self_upd = _coerce_bool(data.get("self_update"), default=True)

    sync_env = (e.get("BOBIVERSE_SYNC_FROM_REPO") or "").strip()
    if sync_env != "":
        sync = _coerce_bool(sync_env, default=sync)
    self_env = (e.get("BOBIVERSE_SELF_UPDATE") or "").strip()
    if self_env != "":
        self_upd = _coerce_bool(self_env, default=self_upd)
    if (e.get("BOB_AUTOUPDATE") or "").strip() == "0":
        self_upd = False

    return AircStartUpdatePolicy(sync_from_repo=sync, self_update=self_upd)


def resolve_sync_from_repo_for_install(
    *,
    prior: bool | None,
    explicit: bool | None,
) -> bool:
    """Fresh / omitted → False; explicit MSI/CLI wins; else keep prior (FR #3289)."""
    if explicit is not None:
        return bool(explicit)
    if prior is not None:
        return bool(prior)
    return False


def resolve_self_update_for_install(
    *,
    prior: bool | None,
    explicit: bool | None,
    profile: str | None = None,
) -> bool:
    """Fresh / omitted → True; explicit wins; else keep prior (FR #3289).

    FR #3393: ``AIRC_PROFILE=workstation`` defaults False (no SYSTEM GitHub MSI
    channel) unless MSI/CLI sets ``AIRC_SELF_UPDATE`` explicitly.
    FR #3401: ``AIRC_PROFILE=client`` also defaults False (no automatic update).
    """
    if explicit is not None:
        return bool(explicit)
    prof = (profile or "").strip().lower()
    if prof in {"workstation", "client"}:
        return False
    if prior is not None:
        return bool(prior)
    return True


def resolve_jobs_for_install(
    *,
    prior: str | None,
    explicit: str | None,
    profile: str | None = None,
) -> str:
    """Fleet default ``on``; workstation default ``off``; client default ``on`` (FR #3393/#3401)."""
    exp = (explicit or "").strip().lower()
    if exp in {"off", "on"}:
        return exp
    prof = (profile or "").strip().lower()
    if prof == "workstation":
        return "off"
    if prof == "client":
        return "on"
    prior_l = (prior or "").strip().lower()
    if prior_l in {"off", "on"}:
        return prior_l
    return "on"


def resolve_update_cap_for_install(
    *,
    prior: str | None,
    explicit: str | None,
    profile: str | None = None,
) -> str:
    """Fleet default ``on``; workstation default ``off``; client default ``on`` (ops-gated, FR #3401)."""
    exp = (explicit or "").strip().lower()
    if exp in {"off", "on"}:
        return exp
    prof = (profile or "").strip().lower()
    if prof == "workstation":
        return "off"
    if prof == "client":
        return "on"
    prior_l = (prior or "").strip().lower()
    if prior_l in {"off", "on"}:
        return prior_l
    return "on"


def resolve_extension_cap_for_install(
    *,
    prior: str | None,
    explicit: str | None,
    profile: str | None = None,
) -> str:
    """Fleet default ``on``; client and workstation default ``off`` (FR #5295)."""
    exp = (explicit or "").strip().lower()
    if exp in {"off", "on"}:
        return exp
    prof = (profile or "").strip().lower()
    if prof in {"workstation", "client"}:
        return "off"
    prior_l = (prior or "").strip().lower()
    if prior_l in {"off", "on"}:
        return prior_l
    return "on"


def resolve_require_account_for_install(
    *,
    prior: bool | None,
    explicit: bool | None,
    profile: str | None = None,
) -> bool:
    """Fleet default False; workstation default True; client default False (FR #3393/#3401)."""
    if explicit is not None:
        return bool(explicit)
    prof = (profile or "").strip().lower()
    if prof == "workstation":
        return True
    if prof == "client":
        return False
    if prior is not None:
        return bool(prior)
    return False


@dataclass
class ConsoleSession:
    nick: str
    proc: subprocess.Popen[str]
    created_at: float = field(default_factory=time.time)
    last_at: float = field(default_factory=time.time)

    def write_line(self, text: str) -> None:
        self.last_at = time.time()
        if self.proc.stdin is None:
            raise RuntimeError("console stdin closed")
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            if self.alive():
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass


class ConsoleSessionManager:
    """One interactive shell per authenticated nick."""

    def __init__(
        self,
        *,
        shell: str | None = None,
        cwd: str | None = None,
        on_output: Callable[[str, str], None] | None = None,
        idle_sec: float = 3600.0,
    ) -> None:
        self.shell = shell or DEFAULT_SHELL
        self.cwd = cwd
        self.on_output = on_output
        self.idle_sec = idle_sec
        self._lock = threading.Lock()
        self._sessions: dict[str, ConsoleSession] = {}

    def get_or_create(self, nick: str) -> ConsoleSession:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.get(key)
            if sess and sess.alive():
                sess.last_at = time.time()
                return sess
            if sess:
                sess.close()
            proc = subprocess.Popen(
                [self.shell],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                bufsize=1,
            )
            sess = ConsoleSession(nick=key, proc=proc)
            self._sessions[key] = sess
            if self.on_output and proc.stdout is not None:
                threading.Thread(
                    target=self._pump,
                    args=(key, proc),
                    name=f"airc-console-{key}",
                    daemon=True,
                ).start()
            return sess

    def _pump(self, nick: str, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                text = line.rstrip("\r\n")
                if self.on_output:
                    self.on_output(nick, text)
        except Exception:
            pass

    def pipe(self, nick: str, command: str) -> ConsoleSession:
        sess = self.get_or_create(nick)
        sess.write_line(command)
        return sess

    def close_nick(self, nick: str) -> None:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.pop(key, None)
        if sess:
            sess.close()

    def close_all(self) -> None:
        with self._lock:
            items = list(self._sessions.items())
            self._sessions.clear()
        for _, sess in items:
            sess.close()

    def reap_idle(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        dead: list[str] = []
        with self._lock:
            for k, sess in list(self._sessions.items()):
                if (not sess.alive()) or (now - sess.last_at > self.idle_sec):
                    dead.append(k)
            for k in dead:
                sess = self._sessions.pop(k, None)
                if sess:
                    sess.close()
        return len(dead)

    def active(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions.keys())


@dataclass
class HandleResult:
    action: str
    nick: str | None = None
    target: str | None = None
    text: str | None = None
    reply: str | None = None
    deny_reason: str | None = None  # FR #3401: not-op / self-nick / channel-state-unknown
    # FR #4067: populated on authorised shell/job/pipe for auth-allow audit.
    allow_mode: str | None = None
    allow_account: str | None = None
    allow_channel: str | None = None


class ShellRequestError(ValueError):
    """Malformed or oversized console shell request (FR #75)."""


ShellKind = Literal["ps", "cmd", "psb64"]


@dataclass
class ShellRequest:
    kind: ShellKind
    body: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    cancel_event: threading.Event | None = field(default=None, repr=False)


@dataclass
class ShellOutcome:
    job_id: str
    exit_code: int
    stdout: str
    stderr: str


def resolve_powershell() -> str:
    """Windows PowerShell 5.1 host (not pwsh) unless AIRC_POWERSHELL overrides."""
    env = (os.environ.get("AIRC_POWERSHELL") or "").strip()
    if env:
        return env
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    return found or "powershell.exe"


def resolve_comspec() -> str:
    return (os.environ.get("COMSPEC") or "").strip() or "cmd.exe"


# FR #2580: redirected powershell.exe defaults $OutputEncoding to ASCII, which
# best-fits non-ASCII (α→a, CJK→?) before airc UTF-8-decodes stdout (U+FFFD).
# FR #2641: also silence progress records - redirected hosts otherwise emit
# ``#< CLIXML`` / ``Preparing modules for first use`` on stderr (extra IRC flood
# and a non-empty StdErr for ExitCode 0 callers).
# FR #2910: keep each preamble statement on its own line so terminating errors
# do not fuse ``$ProgressPreference`` / ``UTF8Encoding`` into the user statement
# (char offsets / preamble leak). FR #2918: PowerShell still numbers those
# preamble lines, so ``plain_text_powershell_stderr`` rewrites ``At line:N`` by
# subtracting ``ps_utf8_preamble_line_count()`` to match the user script.
PS_UTF8_STDOUT_PREAMBLE = (
    "$ProgressPreference = 'SilentlyContinue'\n"
    "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false\n"
    "$OutputEncoding = [Console]::OutputEncoding\n"
)

_CLIXML_ERROR_S_RE = re.compile(
    r'<S\s+S="Error">(.*?)</S>',
    re.IGNORECASE | re.DOTALL,
)
_CLIXML_HEX_ESC_RE = re.compile(r"_x([0-9A-Fa-f]{4})_", re.IGNORECASE)
_AT_LINE_RE = re.compile(r"At line:(\d+)(\s+char:)", re.IGNORECASE)


def ps_utf8_preamble_line_count() -> int:
    """How many script lines ``PS_UTF8_STDOUT_PREAMBLE`` occupies before user text (FR #2918)."""
    p = PS_UTF8_STDOUT_PREAMBLE or ""
    if not p:
        return 0
    if p.endswith("\n"):
        return p.count("\n")
    return p.count("\n") + 1


def wrap_ps_script_utf8_stdout(script: str) -> str:
    """Prefix a PowerShell script for UTF-8 stdout + silent progress (FR #2580 / #2641 / #2910)."""
    return PS_UTF8_STDOUT_PREAMBLE + (script or "")


def _unescape_powershell_clixml_text(text: str) -> str:
    """Decode PowerShell CLIXML ``_xHHHH_`` escapes (CR/LF and friends)."""

    def _one(m: re.Match[str]) -> str:
        try:
            return chr(int(m.group(1), 16))
        except ValueError:
            return m.group(0)

    return _CLIXML_HEX_ESC_RE.sub(_one, text or "")


def _adjust_at_line_numbers(text: str, offset: int) -> str:
    """Rewrite ``At line:N`` to user-script coordinates (FR #2918)."""
    if offset <= 0 or not text:
        return text

    def _repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return f"At line:{max(1, n - offset)}{m.group(2)}"

    return _AT_LINE_RE.sub(_repl, text)


def plain_text_powershell_stderr(
    stderr: str, *, at_line_offset: int | None = None
) -> str:
    """Turn redirected PowerShell CLIXML stderr into plain error text (FR #2910 / #2918).

    Windows PowerShell 5.1 serialises the error stream as ``#< CLIXML`` / ``<Objs>``
    when stdout/stderr are redirected. Extract ``<S S=\"Error\">`` payloads, unescape
    ``_xHHHH_``, drop progress/noise records, and strip residual wrapper preamble
    echoes so IRC ``err`` lines carry the real message only.

    Default ``at_line_offset`` is ``ps_utf8_preamble_line_count()`` so ``At line:``
    matches the operator script (pass ``0`` for raw CLIXML fixtures that were not
    wrapped).
    """
    raw = stderr or ""
    if not raw:
        return ""
    if at_line_offset is None:
        at_line_offset = ps_utf8_preamble_line_count()
    looks_clixml = ("#< CLIXML" in raw) or ("<Objs" in raw and 'S="Error"' in raw)
    if looks_clixml:
        parts = [
            _unescape_powershell_clixml_text(m.group(1)).strip("\r\n")
            for m in _CLIXML_ERROR_S_RE.finditer(raw)
        ]
        # Drop empty / whitespace-only Error nodes.
        parts = [p for p in parts if p.strip()]
        plain = "\n".join(parts).strip()
        if not plain:
            # Fallback: strip CLIXML chrome rather than returning empty.
            plain = re.sub(r"(?is)#<\s*CLIXML\s*", "", raw)
            plain = re.sub(r"(?is)</?Objs[^>]*>", "", plain)
            plain = _unescape_powershell_clixml_text(plain).strip()
    else:
        plain = raw
    # Never leak the UTF-8 / progress wrapper into operator-visible StdErr.
    drop_markers = (
        "ProgressPreference",
        "UTF8Encoding",
        "$OutputEncoding",
        "[Console]::OutputEncoding",
    )
    kept: list[str] = []
    for line in plain.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if any(m in line for m in drop_markers):
            # Keep lines that also carry the real error after a fused preamble.
            # e.g. "... OutputEncoding; Write-Error 'boom' : boom"
            if ":" in line and any(
                tok in line for tok in ("Write-Error", "Cannot find", "Exception", "Error")
            ):
                # Prefer text after the last preamble marker when fused.
                cut = line
                for m in drop_markers:
                    if m in cut:
                        idx = cut.rfind(m)
                        # advance past ';' if present after the marker span
                        semi = cut.find(";", idx)
                        if semi != -1:
                            cut = cut[semi + 1 :].lstrip()
                if cut and cut != line:
                    kept.append(cut)
                    continue
            continue
        kept.append(line)
    plain = "\n".join(kept).strip()
    return _adjust_at_line_numbers(plain, int(at_line_offset or 0))


def encode_ps_encoded_command(script: str) -> str:
    """Base64 of UTF-16LE script text for ``powershell -EncodedCommand``.

    Always wraps with UTF-8 OutputEncoding (FR #2580) and silent progress (FR #2641).
    """
    wrapped = wrap_ps_script_utf8_stdout(script)
    return base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")


def _looks_like_utf16le_script(raw: bytes) -> bool:
    """True when bytes look like UTF-16LE (ASCII-heavy scripts have 0x00 on odd indexes)."""
    if len(raw) < 2 or len(raw) % 2:
        return False
    zeros = sum(1 for i in range(1, len(raw), 2) if raw[i] == 0)
    return zeros >= max(1, len(raw) // 4)


def prepare_psb64_encoded_command(payload: str) -> str:
    """Decode ``psb64:`` payload to an ``-EncodedCommand`` ASCII base64 string.

    Rules (FR #75): decode UTF-16LE or UTF-8 script text, then always re-encode
    via ``encode_ps_encoded_command`` so the FR #2580 UTF-8 stdout wrap applies
    (do not return raw payload bytes without the wrap).
    """
    text = (payload or "").strip()
    if not text:
        raise ShellRequestError("malformed psb64: empty")
    if len(text) > PSB64_MAX_CHARS:
        raise ShellRequestError("psb64 too large")
    try:
        raw = base64.b64decode(text, validate=True)
    except binascii.Error as exc:
        raise ShellRequestError("malformed psb64") from exc
    if _looks_like_utf16le_script(raw):
        try:
            # Re-encode via encode_ps_encoded_command so FR #2580 UTF-8 wrap applies.
            return encode_ps_encoded_command(raw.decode("utf-16-le"))
        except UnicodeDecodeError:
            pass
    try:
        script = raw.decode("utf-8")
        return encode_ps_encoded_command(script)
    except UnicodeDecodeError:
        pass
    if len(raw) % 2 == 0:
        try:
            return encode_ps_encoded_command(raw.decode("utf-16-le"))
        except UnicodeDecodeError as exc:
            raise ShellRequestError("malformed psb64") from exc
    raise ShellRequestError("malformed psb64")


_HEARD_PAYLOAD_RE = re.compile(r"(?is)\bHeard:\s*(.+)$")
_BOBTALK_PREFIX_RE = re.compile(
    r"(?is)^@\S+\s+\S+\s+here\.\s*(?:weekly=[^.]+\.)?\s*"
)


_SELF_REPLY_RE = re.compile(
    r"(?is)^(?:(?:out|err)\s+id=[0-9a-f]+\s+seq=\d+\b|"
    r"DONE\s+(?:id=[0-9a-f]+\s+)?exit=-?\d+\b|"
    r"UPDATE\s+accepted\b)"
)


def is_console_self_reply(text: str) -> bool:
    """True when the payload is an airc reply line, not an operator command (FR #5101)."""
    return bool(_SELF_REPLY_RE.match((text or "").strip()))


def sanitize_console_operator_text(text: str) -> str:
    """Strip Halloy/bobtalk nick-prefix and ``Heard:`` wrappers (FR #2570).

    Live failure: clients relay ``@marchhare_console marchhare here. weekly=27. Heard: STATUS …``
    into the console PRIVMSG; PowerShell then sees ``@marchhare_console`` as a splat.
    Prefer the payload after ``Heard:``; otherwise strip a bobtalk ``@nick mid here.`` prefix
    when the remainder looks like a console command / FR #78 verb.

    FR #2570 follow-up: bobtalk-only presence lines (no command after the prefix) return
    empty so ``handle_raw`` drops them - never pipe ``@nick`` / ``weekly=N`` into PowerShell.
    MRB #2573: do not treat PowerShell ``@(…)`` / ``@'`` / ``@"`` as nick-mentions; drop only
    ``@token`` nick-like lines. Remove unreachable duplicate sanitize tail.
    """
    raw = (text or "").strip()
    if not raw:
        return raw
    m = _HEARD_PAYLOAD_RE.search(raw)
    if m:
        return (m.group(1) or "").strip()
    m2 = _BOBTALK_PREFIX_RE.match(raw)
    if m2:
        rest = raw[m2.end() :].strip()
        # Presence-only: "@nick mid here. weekly=26." or leftover "weekly=26"
        if not rest or re.fullmatch(r"(?i)weekly=\S+", rest):
            return ""
        return rest
    # Nick-mention splat (not PowerShell array/here-string @( @' @" ).
    if raw.startswith("@") and len(raw) > 1 and raw[1] not in "('\"":
        return ""
    return raw


def parse_shell_request(text: str) -> ShellRequest:
    """Parse a console PRIVMSG into ps / cmd: / psb64: (FR #75).

    Optional leading ``id=<8 hex>`` (FR #1546) pins the DONE/out/err correlation id
    so Invoke-AircRemote can wait on ``airc-replies.jsonl``.
    """
    raw = sanitize_console_operator_text(text or "")
    if not raw:
        raise ShellRequestError("empty command")
    job_id: str | None = None
    m = re.match(r"(?is)^id=([0-9a-f]{8})\s+(.*)$", raw)
    if m:
        job_id = m.group(1).lower()
        raw = m.group(2).strip()
        if not raw:
            raise ShellRequestError("empty command after id=")
    low = raw.lower()
    if low.startswith("psb64:"):
        payload = raw[6:]
        # Validate early; body stores original payload for argv build.
        prepare_psb64_encoded_command(payload)
        req = ShellRequest(kind="psb64", body=payload)
    elif low.startswith("cmd:"):
        body = raw[4:].lstrip()
        if not body:
            raise ShellRequestError("empty cmd:")
        req = ShellRequest(kind="cmd", body=body)
    else:
        req = ShellRequest(kind="ps", body=raw)
    if job_id:
        req.job_id = job_id
    return req


def prepare_cmd_body(body: str) -> str:
    """Prefix ``chcp 65001`` for UTF-8 capture unless the operator already set CP (FR #2580)."""
    text = body or ""
    stripped = text.lstrip().lower()
    if not stripped.startswith("chcp "):
        text = "chcp 65001>nul & " + text
    return text


def build_cmd_command_line(body: str) -> str:
    """CreateProcess command line for ``cmd.exe /d /s /c`` (FR #3773).

    ``subprocess`` list argv goes through ``list2cmdline``, which doubles a
    trailing backslash before the closing quote (CreateProcess argv rules).
    cmd.exe then re-parses ``/c`` and treats ``dir C:\\\\`` as a bad path.
    Build a single string with ``/s`` so operator text such as ``dir C:\\`` and
    ``dir \"C:\\Program Files\\\"`` keeps a single trailing backslash.
    """
    com = resolve_comspec()
    prepared = prepare_cmd_body(body)
    return f'{com} /d /s /c "{prepared}"'


def build_shell_argv(req: ShellRequest) -> list[str]:
    if req.kind == "cmd":
        # Shape for inspectors/tests. Execution uses build_cmd_command_line
        # (FR #3773) - do not subprocess.run this list for trailing-\\ bodies.
        body = prepare_cmd_body(req.body or "")
        return [resolve_comspec(), "/d", "/s", "/c", body]
    if req.kind == "psb64":
        enc = prepare_psb64_encoded_command(req.body)
    else:
        enc = encode_ps_encoded_command(req.body)
    return [
        resolve_powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        enc,
    ]


def _clip_bytes(data: bytes, limit: int = SHELL_OUTPUT_MAX_BYTES) -> tuple[str, bool]:
    clipped = len(data) > limit
    chunk = data[:limit]
    if chunk.startswith((b"\xff\xfe", b"\xfe\xff")):
        return chunk.decode("utf-16", errors="replace"), clipped
    return chunk.decode("utf-8", errors="replace"), clipped


def _stop_shell_process(proc: subprocess.Popen) -> None:
    """Stop only this shell's tree; never wait on inherited stdout pipe handles."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _read_shell_capture(path: str) -> bytes:
    # Separate reader so an inherited writer does not share this seek pointer.
    # Windows exclusive NamedTemporaryFile needs share-mode CreateFile (FR #5211).
    if os.name == "nt":
        import ctypes
        import msvcrt

        generic_read = 0x80000000
        share = 0x1 | 0x2 | 0x4
        handle = ctypes.windll.kernel32.CreateFileW(
            str(path), generic_read, share, None, 3, 0, None
        )
        if handle in (-1, 0xFFFFFFFF):
            raise OSError(ctypes.GetLastError(), "CreateFileW", path)
        fd = msvcrt.open_osfhandle(int(handle), os.O_RDONLY)
        with os.fdopen(fd, "rb") as stream:
            return stream.read(SHELL_OUTPUT_MAX_BYTES + 1)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        return stream.read(SHELL_OUTPUT_MAX_BYTES + 1)


def run_shell_request(
    req: ShellRequest,
    *,
    timeout_s: float = SHELL_TIMEOUT_S,
    cwd: str | None = None,
) -> ShellOutcome:
    # FR #3773: cmd must use a pre-built command-line string, not list argv.
    args: str | list[str]
    if req.kind == "cmd":
        args = build_cmd_command_line(req.body or "")
    else:
        args = build_shell_argv(req)
    cancel = req.cancel_event or threading.Event()
    if cancel.is_set():
        return ShellOutcome(req.job_id, 130, "", "cancelled")
    # FR #5211: files instead of pipes so timeout does not wait on inherited EOF.
    # mkstemp (not NamedTemporaryFile): Windows exclusive lock blocks a second open.
    out_path = err_path = ""
    out_h = err_h = None
    out = err = ""
    out_clip = err_clip = False
    reason = ""
    exit_code = 1
    try:
        fd_out, out_path = tempfile.mkstemp(prefix="airc-sh-out-")
        fd_err, err_path = tempfile.mkstemp(prefix="airc-sh-err-")
        os.close(fd_out)
        os.close(fd_err)
        out_h = open(out_path, "wb")
        err_h = open(err_path, "wb")
        proc = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=out_h, stderr=err_h, cwd=cwd,
        )
        deadline = time.monotonic() + timeout_s
        reason = ""
        stopped = False
        try:
            while proc.poll() is None:
                if cancel.is_set():
                    reason = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    reason = f"timeout after {timeout_s:.0f}s"
                    break
                cancel.wait(min(0.05, max(0, deadline - time.monotonic())))
        finally:
            if proc.poll() is None:
                _stop_shell_process(proc)
                stopped = True
        # FR #5676: deadline can fire in the same tick the direct child exits
        # (inherited capture / slow host). Prefer the real returncode over a
        # spurious 124 when we never had to stop the process.
        if reason == "cancelled":
            exit_code = 130
        elif reason and stopped:
            exit_code = 124
        elif reason:
            exit_code = int(proc.returncode or 0)
            reason = ""
        else:
            exit_code = int(proc.returncode or 0)
        out_h.flush()
        err_h.flush()
        out, out_clip = _clip_bytes(_read_shell_capture(out_path))
        err, err_clip = _clip_bytes(_read_shell_capture(err_path))
    finally:
        for handle in (out_h, err_h):
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
        for path in (out_path, err_path):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
    # FR #2910: PowerShell 5.1 error stream is CLIXML under redirect - plain-text it.
    err = plain_text_powershell_stderr(err)
    if out_clip:
        out += "\n[clipped stdout]"
    if err_clip:
        err += "\n[clipped stderr]"
    if reason:
        err = (err + ("\n" if err else "") + reason).strip()
    return ShellOutcome(
        job_id=req.job_id,
        exit_code=exit_code,
        stdout=out,
        stderr=err,
    )


def chunk_irc_text(text: str, *, limit: int = IRC_SAFE_PAYLOAD, prefix: str = "") -> list[str]:
    """Split ``text`` so each ``prefix + chunk`` fits ``limit`` (IRC-safe)."""
    room = max(8, limit - len(prefix.encode("utf-8", errors="replace")))
    raw = text.replace("\r", "").replace("\n", " ").replace("\x00", "\ufffd")
    if not raw:
        return [prefix] if prefix else [""]
    chunks: list[str] = []
    piece = ""
    size = 0
    for char in raw:
        width = len(char.encode("utf-8", errors="replace"))
        if size + width > room:
            chunks.append(prefix + piece)
            piece, size = "", 0
        piece += char
        size += width
    chunks.append(prefix + piece)
    return chunks


@dataclass
class FormattedShellReplies:
    """One IRC reply page (FR #4790 truncate + FR #4794 CONT/RESUME).

    FR #5003: when ``via_dcc`` is set, ``lines`` are control-plane only (hint + DONE
    with bytes/sha256/via=dcc) and ``bulk_payload`` holds the bytes for reverse DCC.
    """

    lines: list[str]
    next_offset: int | None
    piece_count: int
    via_dcc: bool = False
    bulk_payload: bytes | None = None
    bulk_sha256: str = ""


_CONT_RE = re.compile(
    r"(?is)^(?:id=([0-9a-f]{8})\s+)?(CONT|RESUME)(?:\s+id=([0-9a-f]{8}))?(?:\s+offset=(\d+))?\s*$"
)


def parse_cont_request(text: str) -> tuple[str, int | None] | None:
    """Parse ``CONT`` / ``RESUME`` (+ optional leading id= / offset=). FR #4794."""
    raw = sanitize_console_operator_text(text or "")
    m = _CONT_RE.match(raw.strip())
    if not m:
        return None
    jid = (m.group(1) or m.group(3) or "").lower()
    if not jid:
        return None
    off_s = m.group(4)
    offset = int(off_s) if off_s is not None else None
    return jid, offset


def _shell_reply_pieces(
    outcome: ShellOutcome,
    *,
    irc_limit: int = IRC_SAFE_PAYLOAD,
) -> list[tuple[str, str]]:
    """Flatten stdout then stderr into IRC-safe (label, piece) tuples."""
    pieces: list[tuple[str, str]] = []

    def emit(stream: str, label: str) -> None:
        parts = stream.splitlines() if stream else []
        if stream and not parts:
            parts = [""]
        for part in parts:
            # Conservative seq width so later pages (seq=100+) still fit IRC_SAFE_PAYLOAD.
            prefix = f"{label} id={outcome.job_id} seq=99999 "
            for chunk in chunk_irc_text(part, limit=irc_limit, prefix=prefix):
                pieces.append((label, chunk[len(prefix):]))

    emit(outcome.stdout, "out")
    emit(outcome.stderr, "err")
    return pieces


def should_offer_dcc_bulk(*, piece_count: int, byte_count: int) -> bool:
    """Delegate to airc_dcc_bulk so thresholds stay single-sourced (FR #5003)."""
    import airc_dcc_bulk as _dcc

    return _dcc.should_use_dcc_bulk(piece_count=piece_count, byte_count=byte_count)


def format_shell_replies_ex(
    outcome: ShellOutcome,
    *,
    irc_limit: int = IRC_SAFE_PAYLOAD,
    max_irc_lines: int = SHELL_REPLY_MAX_IRC_LINES,
    offset: int = 0,
    prefer_dcc_bulk: bool = False,
    dcc_peer_ready: bool = False,
) -> FormattedShellReplies:
    """Page shell replies; ``next_offset`` set when more pieces remain (FR #4794).

    FR #5003: when ``prefer_dcc_bulk`` and a peer is ready and page-0 payload exceeds
    the bulk threshold, return control-plane lines + ``bulk_payload`` instead of
    flooding IRC. Callers without a peer keep the IRC CONT path.
    """
    pieces = _shell_reply_pieces(outcome, irc_limit=irc_limit)
    raw_bulk = (outcome.stdout or "").encode("utf-8") + (outcome.stderr or "").encode(
        "utf-8"
    )
    if (
        prefer_dcc_bulk
        and dcc_peer_ready
        and offset == 0
        and should_offer_dcc_bulk(piece_count=len(pieces), byte_count=len(raw_bulk))
    ):
        import airc_dcc_bulk as _dcc

        data = _dcc.build_bulk_bytes(outcome.stdout or "", outcome.stderr or "")
        digest = _dcc.sha256_hex(data)
        payload = _dcc.BulkPayload(
            job_id=outcome.job_id,
            exit_code=int(outcome.exit_code),
            data=data,
            sha256=digest,
        )
        return FormattedShellReplies(
            lines=_dcc.format_bulk_control_lines(payload),
            next_offset=None,
            piece_count=len(pieces),
            via_dcc=True,
            bulk_payload=data,
            bulk_sha256=digest,
        )
    max_body = max(1, int(max_irc_lines))
    start = max(0, int(offset))
    page = pieces[start : start + max_body]
    lines: list[str] = []
    for i, (label, piece) in enumerate(page):
        seq = start + i + 1
        prefix = f"{label} id={outcome.job_id} seq={seq} "
        room = max(8, irc_limit - len(prefix))
        lines.append(prefix + piece[:room])
    next_off: int | None = None
    if start + len(page) < len(pieces):
        next_off = start + len(page)
        omitted = len(pieces) - next_off
        seq = (start + len(page)) + 1
        marker = (
            f"err id={outcome.job_id} seq={seq} "
            f"output truncated, {omitted} lines omitted; "
            f"CONT id={outcome.job_id} (FR #4794); "
            f"file fetch / PUT (FR #4790); DCCLISTEN (FR #5003)"
        )
        if len(marker) > irc_limit:
            marker = marker[: irc_limit - 3] + "..."
        lines.append(marker)
    lines.append(f"DONE id={outcome.job_id} exit={outcome.exit_code}")
    return FormattedShellReplies(
        lines=lines, next_offset=next_off, piece_count=len(pieces)
    )


def format_shell_replies(
    outcome: ShellOutcome,
    *,
    irc_limit: int = IRC_SAFE_PAYLOAD,
    max_irc_lines: int = SHELL_REPLY_MAX_IRC_LINES,
    offset: int = 0,
) -> list[str]:
    """Stable output contract: ordered out/err seq lines + terminal DONE (FR #75).

    FR #4790: cap out/err IRC lines so base64 dumps cannot flood Ergo; emit an
    ``err`` truncate marker (lines omitted) then DONE. FR #4794: marker cites
    ``CONT id=`` so controllers can page without re-running the command.
    Controllers should still prefer file fetch / PUT for large binaries.
    FR #5003: oversized replies may use reverse DCC (``via=dcc``) when the caller
    advertised ``DCCLISTEN``; otherwise IRC CONT paging remains the fallback.
    """
    return format_shell_replies_ex(
        outcome, irc_limit=irc_limit, max_irc_lines=max_irc_lines, offset=offset
    ).lines


_DCC_FALLBACK_SEQ_RE = re.compile(
    r"^(?:out|err) id=([0-9a-f]{8}) seq=(\d+) ", re.IGNORECASE
)


def insert_dcc_fallback_notice(lines: list[str], job_id: str, notice: str) -> list[str]:
    """FR #5065: attach DCC-fail note before DONE with the next unused seq.

    Emitting ``err seq=1`` *before* ``format_shell_replies_ex`` reuses seq=1
    (FR #75 seq is global across out/err) and ConvertFrom-AircRemoteReply
    fail-closes with ``duplicate seq=1``.
    """
    jid = (job_id or "").strip().lower()
    max_seq = 0
    done_i: int | None = None
    out = list(lines)
    for i, ln in enumerate(out):
        m = _DCC_FALLBACK_SEQ_RE.match(ln)
        if m:
            max_seq = max(max_seq, int(m.group(2)))
        if ln.startswith(f"DONE id={jid}"):
            done_i = i
    err = f"err id={jid} seq={max_seq + 1} {notice}"
    if done_i is None:
        out.append(err)
    else:
        out.insert(done_i, err)
    return out


@dataclass
class _ShellPending:
    """One queued shell command (FR #2632); ``done`` signals completion for wait=True."""

    command: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    done: threading.Event = field(default_factory=threading.Event)
    cancelled: threading.Event = field(default_factory=threading.Event)
    reply_lock: threading.RLock = field(default_factory=threading.RLock)
    abandoned: bool = False
    terminal_sent: bool = False


class ShellJobRunner:
    """Run FR #75 shell requests; emit reply lines to the operator Query.

    FR #2632: one in-flight shell per Query nick plus a short pending queue so
    concurrent Invoke-AircRemote Commands both get a real DONE. Overflow still
    fail-closes with busy DONE (FR #2612: no hang / no lost DONE).
    """

    def __init__(
        self,
        *,
        on_reply: Callable[[str, str], None] | None = None,
        cwd: str | None = None,
        timeout_s: float = SHELL_TIMEOUT_S,
        wait: bool = False,
        on_inflight: Callable[[str, str], None] | None = None,
        on_idle: Callable[[str], None] | None = None,
        on_shell_done: Callable[[str, str, float, int, int], None] | None = None,
        pending_max: int = SHELL_PENDING_MAX,
    ) -> None:
        self.on_reply = on_reply
        self.cwd = cwd
        self.timeout_s = timeout_s
        self.wait = wait
        self.on_inflight = on_inflight
        self.on_idle = on_idle
        # FR #4068: nick, job_id, elapsed_s, reply_lines, exit_code after batch capture.
        self.on_shell_done = on_shell_done
        self.pending_max = max(0, int(pending_max))
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._pending: dict[str, deque[_ShellPending]] = {}
        self._inflight_cmd: dict[str, _ShellPending] = {}
        # FR #4794: (nick, job_id) -> (outcome, next_offset) for CONT/RESUME pages.
        self._resume: dict[tuple[str, str], tuple[ShellOutcome, int]] = {}
        # FR #5519: "log" entries stay CONT-able when shell=off.
        self._resume_kind: dict[tuple[str, str], str] = {}
        # FR #5003 / #5613: job_id -> (DccListenOffer, noted_mono).
        self._dcc_listen: dict[str, tuple[object, float]] = {}
        self._now = time.monotonic
        self.dcc_listen_events: list[str] = []

    def _prune_dcclisten_locked(self) -> None:
        now = float(self._now())
        dead = [
            jid
            for jid, (_off, noted) in list(self._dcc_listen.items())
            if now - float(noted) > DCCLISTEN_TTL_S
        ]
        for jid in dead:
            self._dcc_listen.pop(jid, None)
            self.dcc_listen_events.append(f"expired id={jid} ttl={int(DCCLISTEN_TTL_S)}")

    def note_dcclisten(self, text: str) -> bool:
        """Record a caller ``DCCLISTEN`` offer (FR #5003 / #5613 TTL + cap)."""
        import airc_dcc_bulk as _dcc

        offer = _dcc.parse_dcclisten(text)
        if offer is None:
            return False
        key = (offer.job_id or "").strip().lower()
        with self._lock:
            self._prune_dcclisten_locked()
            while len(self._dcc_listen) >= DCCLISTEN_MAX and key not in self._dcc_listen:
                oldest = min(self._dcc_listen.items(), key=lambda kv: kv[1][1])
                self._dcc_listen.pop(oldest[0], None)
                self.dcc_listen_events.append(f"evicted id={oldest[0]} cap={DCCLISTEN_MAX}")
            self._dcc_listen[key] = (offer, float(self._now()))
        return True

    def peek_dcc_offer(self, job_id: str):
        """FR #5194: DCCLISTEN recorded for this job, or None (leave in place for PUT fallback)."""
        key = (job_id or "").strip().lower()
        with self._lock:
            self._prune_dcclisten_locked()
            slot = self._dcc_listen.get(key)
            return slot[0] if slot else None

    def register_log_resume(
        self,
        nick: str,
        job_id: str,
        body: str,
        *,
        next_offset: int = 1,
    ) -> None:
        """FR #5519: store NETWORK/EXTENSION/LEGION IRC log body for CONT.

        Piece 0 is a marker so advertised ``CONT offset=1`` starts at the payload.
        """
        key = nick.strip().lower()
        jid = (job_id or "").strip().lower()
        if not key or not jid:
            return
        outcome = ShellOutcome(
            job_id=jid,
            exit_code=0,
            stdout="log\n" + (body or ""),
            stderr="",
        )
        with self._lock:
            self._resume[(key, jid)] = (outcome, max(1, int(next_offset)))
            self._resume_kind[(key, jid)] = "log"

    def resume_kind(self, nick: str, job_id: str) -> str:
        key = nick.strip().lower()
        jid = (job_id or "").strip().lower()
        with self._lock:
            return self._resume_kind.get((key, jid), "")

    def take_dcclisten(self, job_id: str):
        """FR #5293 / #5613: pop a live DCCLISTEN offer (expired slots are dropped)."""
        key = (job_id or "").strip().lower()
        with self._lock:
            self._prune_dcclisten_locked()
            slot = self._dcc_listen.pop(key, None)
            return slot[0] if slot else None

    def discard_dcclisten(self, job_id: str, *, reason: str = "verb-done") -> None:
        """FR #5613: drop unused offer when a non-bulk verb finishes for this id."""
        key = (job_id or "").strip().lower()
        if not key:
            return
        with self._lock:
            if self._dcc_listen.pop(key, None) is not None:
                self.dcc_listen_events.append(f"cleared id={key} reason={reason}")

    def start(self, nick: str, command: str) -> str:
        key = nick.strip().lower()
        item = _ShellPending(command=command)
        try:
            item.job_id = parse_shell_request(command).job_id
        except ShellRequestError:
            pass

        with self._lock:
            q = self._pending.setdefault(key, deque())
            prev = self._threads.get(key)
            busy = prev is not None and prev.is_alive()
            # When a shell is live, at most pending_max more may wait; overflow fail-closes.
            if busy and len(q) >= self.pending_max:
                overflow = True
            else:
                overflow = False
                q.append(item)
                if not busy:
                    t = threading.Thread(
                        target=self._drain, args=(key,), name=f"airc-shell-{key}", daemon=True
                    )
                    self._threads[key] = t
                    t.start()

        if overflow:
            # FR #2612 / #2632: queue full - fail closed with DONE (Wait must not hang).
            try:
                req = parse_shell_request(command)
                jid = req.job_id
            except ShellRequestError as exc:
                jid = uuid.uuid4().hex[:8]
                self._emit(key, f"err id={jid} seq=1 {exc}")
                self._emit(key, f"DONE id={jid} exit=2")
                return key
            self._emit(key, f"err id={jid} seq=1 busy: prior shell still emitting")
            self._emit(key, f"DONE id={jid} exit=1")
            return key

        if self.wait:
            item.done.wait(timeout=self.timeout_s + 5)
        return key

    def _drain(self, key: str) -> None:
        while True:
            with self._lock:
                if self._threads.get(key) is not threading.current_thread():
                    return
                q = self._pending.get(key)
                if not q:
                    self._pending.pop(key, None)
                    self._threads.pop(key, None)
                    self._inflight_cmd.pop(key, None)
                    return
                item = q.popleft()
                self._inflight_cmd[key] = item
            try:
                self._run_one(key, item)
            except Exception:
                # A failing reply callback must not strand the remaining queue.
                pass
            finally:
                item.done.set()
                with self._lock:
                    idle = self._inflight_cmd.get(key) is item
                    if idle:
                        self._inflight_cmd.pop(key, None)
                if idle and self.on_idle:
                    try:
                        self.on_idle(key)
                    except Exception:
                        pass

    def _run_one(self, key: str, item: _ShellPending) -> None:
        jid: str | None = None
        next_seq = 1
        try:
            try:
                req = parse_shell_request(item.command)
            except ShellRequestError as exc:
                jid = item.job_id
                self._reply_job(key, f"err id={jid} seq=1 {exc}", item)
                self._reply_job(key, f"DONE id={jid} exit=2", item)
                return
            req.job_id = item.job_id
            req.cancel_event = item.cancelled
            jid = req.job_id
            with item.reply_lock:
                if item.abandoned:
                    return
                if self.on_inflight:
                    try:
                        self.on_inflight(key, jid)
                    except Exception:
                        pass
            # FR #4068: batch capture --- first IRC out only after the process exits.
            t0 = time.monotonic()
            outcome = run_shell_request(req, timeout_s=self.timeout_s, cwd=self.cwd)
            if item.abandoned:
                return
            peer = self.take_dcclisten(jid)
            page = format_shell_replies_ex(
                outcome,
                prefer_dcc_bulk=True,
                dcc_peer_ready=peer is not None,
            )
            if page.via_dcc and page.bulk_payload is not None and peer is not None:
                import airc_dcc_bulk as _dcc

                try:
                    # FR #5008: honor tls= / relay= on the caller's DCCLISTEN offer.
                    # FR #5654: wall-clock bound so a never-reading peer cannot
                    # stall DONE into the shell run timeout (exit=124).
                    _dcc.send_offer_payload_bounded(page.bulk_payload, peer)
                except Exception as exc:
                    # Fall back to IRC CONT path when reverse DCC fails (FR #5003).
                    # FR #5065: notice uses the next seq *after* the IRC page.
                    page = format_shell_replies_ex(outcome)
                    page.lines = insert_dcc_fallback_notice(
                        page.lines,
                        jid,
                        f"dcc failed: {exc}; falling back to IRC",
                    )
            with self._lock:
                if page.next_offset is not None:
                    self._resume[(key, jid)] = (outcome, page.next_offset)
                else:
                    self._resume.pop((key, jid), None)
            for line in page.lines:
                if req.cancel_event is not None and req.cancel_event.is_set() and outcome.exit_code != 130:
                    self._reply_job(key, f"err id={jid} seq={next_seq} cancelled", item)
                    self._reply_job(key, f"DONE id={jid} exit=130", item)
                    with self._lock:
                        self._resume.pop((key, jid), None)
                    return
                match = re.match(r"^(?:out|err) id=\S+ seq=(\d+)", line)
                if match:
                    next_seq = int(match.group(1)) + 1
                self._reply_job(key, line, item)
            if self.on_shell_done:
                try:
                    self.on_shell_done(
                        key,
                        jid,
                        time.monotonic() - t0,
                        len(page.lines),
                        int(outcome.exit_code),
                    )
                except Exception:
                    pass
        except Exception:
            # Keep drain alive for queued peers; always emit DONE when we have an id.
            if jid:
                try:
                    self._reply_job(key, f"err id={jid} seq={next_seq} shell runner fault", item)
                finally:
                    self._reply_job(key, f"DONE id={jid} exit=1", item)

    def _reply_job(self, nick: str, line: str, item: _ShellPending) -> None:
        with item.reply_lock:
            if item.abandoned or item.terminal_sent:
                return
            self._emit(nick, line)
            if line.startswith("DONE "):
                item.terminal_sent = True

    def _emit(self, nick: str, line: str) -> None:
        # FR #2551: on_reply may raise ConnectionError after IRC drop; swallow so the
        # worker thread does not die with an unhandled exception (crash hook).
        if self.on_reply:
            try:
                self.on_reply(nick, line)
            except ConnectionError:
                return
            except UnicodeError:
                return

    def cancel(self, nick: str, job_id: str) -> bool:
        """Cancel an active or queued shell owned by this Query, not another nick."""
        key = nick.strip().lower()
        jid = job_id.strip().lower()
        removed: list[_ShellPending] = []
        found = False
        with self._lock:
            active = self._inflight_cmd.get(key)
            if active is not None and active.job_id == jid:
                active.cancelled.set()
                found = True
            q = self._pending.get(key)
            if q is not None:
                for item in list(q):
                    if item.job_id == jid:
                        item.cancelled.set()
                        q.remove(item)
                        removed.append(item)
                        found = True
            self._resume.pop((key, jid), None)
            self._resume_kind.pop((key, jid), None)
            if found:
                self._dcc_listen.pop(jid, None)
        for item in removed:
            try:
                self._emit(key, f"err id={jid} seq=1 cancelled")
                self._emit(key, f"DONE id={jid} exit=130")
            finally:
                item.done.set()
        return found

    def continue_replies(self, nick: str, job_id: str, offset: int | None = None) -> bool:
        """Emit the next FR #4794 page for a truncated shell job (no re-run).

        Returns True when a resume page was emitted; False when fail-closed
        (unknown / exhausted id) after emitting DONE exit=1.
        """
        key = nick.strip().lower()
        jid = (job_id or "").strip().lower()
        if not jid:
            jid = uuid.uuid4().hex[:8]
            self._emit(key, f"err id={jid} seq=1 CONT missing id=")
            self._emit(key, f"DONE id={jid} exit=2")
            return False
        with self._lock:
            held = self._resume.get((key, jid))
        if held is None:
            self._emit(key, f"err id={jid} seq=1 no resume buffer (unknown or exhausted CONT)")
            self._emit(key, f"DONE id={jid} exit=1")
            return False
        outcome, stored_off = held
        start = stored_off if offset is None else max(0, int(offset))
        page = format_shell_replies_ex(outcome, offset=start)
        with self._lock:
            if page.next_offset is not None:
                self._resume[(key, jid)] = (outcome, page.next_offset)
            else:
                self._resume.pop((key, jid), None)
                self._resume_kind.pop((key, jid), None)
        for line in page.lines:
            self._emit(key, line)
        return True

    def open_job_ids(self) -> list[tuple[str, str]]:
        """(nick, job_id) for in-flight + pending commands (FR #2640 stop flush)."""
        out: list[tuple[str, str]] = []
        with self._lock:
            for key, item in list(self._inflight_cmd.items()):
                out.append((key, item.job_id))
            for key, q in list(self._pending.items()):
                for item in list(q):
                    if self._inflight_cmd.get(key) is item:
                        continue
                    out.append((key, item.job_id))
        return out

    def abandon_open_jobs(self) -> list[tuple[str, str]]:
        """Drop pending/in-flight bookkeeping and unblock waiters; return job ids (FR #2640)."""
        with self._lock:
            items = list(self._inflight_cmd.items())
            items.extend((key, item) for key, q in self._pending.items() for item in q)
            self._pending.clear()
            self._inflight_cmd.clear()
        ids: list[tuple[str, str]] = []
        for key, item in items:
            with item.reply_lock:
                item.abandoned = True
                if not item.terminal_sent:
                    ids.append((key, item.job_id))
                item.cancelled.set()
                item.done.set()
        return ids

    def close_nick(self, nick: str) -> None:
        # Oneshoot threads are daemon; drop tracking + pending for this Query.
        key = nick.strip().lower()
        with self._lock:
            self._threads.pop(key, None)
            pending = self._pending.pop(key, None)
            active = self._inflight_cmd.pop(key, None)
        if active is not None:
            active.cancelled.set()
            active.done.set()
        if pending:
            for item in pending:
                item.cancelled.set()
                item.done.set()



class AircConsoleCore:
    """Pure handler: parse PRIVMSG, gate auth, pipe to console, stay silent on channel."""

    def __init__(
        self,
        *,
        machine: str | None = None,
        auth: AuthPolicy,
        sessions: ConsoleSessionManager | None = None,
        nick: str = NICK,
        shell_runner: ShellJobRunner | None = None,
        update_scheduler: Callable[..., UpdateScheduleResult] | None = None,
        install_root: str | None = None,
        job_protocol: JobProtocol | None = None,
        capabilities: ConsoleCapabilities | None = None,
        channel_commands: bool = False,
        presence_channels: list[str] | None = None,
        priority_runner: Callable[..., _priority.PriorityVerbResult] | None = None,
        priority_allowlist_path: str | None = None,
        priority_allowlist: str | None = None,
        priority_fixture: str | None = None,
        extension_runner: Callable[..., _extension.ExtensionVerbResult] | None = None,
        network_runner: Callable[..., _network.NetworkVerbResult] | None = None,
        legion_runner: Callable[..., _legion.LegionVerbResult] | None = None,
    ) -> None:
        self.machine = machine_id(machine)
        self.channel = shop_channel(self.machine)
        self.auth = auth
        self.nick = nick
        self.sessions = sessions or ConsoleSessionManager()
        self.shell_runner = shell_runner
        self.channel_traffic: list[str] = []
        self.update_scheduler = update_scheduler or schedule_fleet_update
        self.install_root = install_root
        self.job_protocol = job_protocol
        # FR #5284: PRIORITY connect/status (injectable for SelfTest mocks).
        self.priority_runner = priority_runner or _priority.run_priority_verb
        self.priority_allowlist_path = priority_allowlist_path or priority_allowlist
        self.priority_allowlist = priority_allowlist or priority_allowlist_path
        self.priority_fixture = priority_fixture
        # FR #5526: service binds this to _on_console_out for async PRIORITY connect.
        self.priority_reply_send: Callable[[str, str], None] | None = None
        self._priority_jobs_lock = threading.Lock()
        self._priority_jobs: dict[str, dict[str, Any]] = {}
        self.extension_runner = extension_runner or _extension.run_extension_verb
        self.network_runner = network_runner or _network.run_network_verb
        self.legion_runner = legion_runner or _legion.run_legion_verb
        # Default operators preserves pre-#3287 unit tests / hotpatched fleets without airc.json.
        self.capabilities = capabilities or ConsoleCapabilities()
        # FR #3401 / #3639: *who* may command is always live channel +o/+h (AuthPolicy).
        # *Where* commands are read is separate: client profile also reads them from the
        # control channel; fleet / workstation read DMs only and stay silent in channel,
        # because the fleet control channel (#<machine>) carries chair / git-claim
        # traffic (issue titles) that must never be executed as a shell line.
        self.channel_commands = bool(channel_commands)
        # FR #3774: extra JOIN targets for presence only (never command targets).
        self.presence_channels = [
            normalize_irc_channel(c)
            for c in (presence_channels or [])
            if normalize_irc_channel(c)
        ]

    def register_commands(self) -> list[str]:
        """NickServ register / identify sequence (password from env/file at service layer)."""
        return [
            f"NICK {self.nick}",
            f"USER {self.nick} 0 * :airc console service",
        ]

    def join_commands(self) -> list[str]:
        """JOIN control channel plus optional presence channels (FR #3774).

        Presence channels (opt-in only; FR #5190 client never auto-joins #bobiverse) are silent for commands -
        ``handle_raw`` only executes channel traffic on ``self.channel``.
        """
        ordered: list[str] = []
        ctrl = normalize_irc_channel(self.channel) or self.channel
        if ctrl:
            ordered.append(ctrl)
        for ch in self.presence_channels:
            if ch and ch not in ordered:
                ordered.append(ch)
        if not ordered:
            return []
        return [f"JOIN {','.join(ordered)}"]

    def may_speak_on_channel(self) -> bool:
        return False

    def _deny_result(
        self, nick: str, target: str, text: str, account: str | None
    ) -> HandleResult:
        """FR #3401 / #3639 / #5002: DONE exit=126 with real reason; keep id= when present.

        Parse ``id=<8 hex>`` before the auth decision so Invoke-AircRemote / the ear
        can correlate a refusal instead of timing out on a bare ``DONE exit=126 not-op``.
        """
        reason = self.auth.deny_reason(nick, account) or "not-op"
        job_id = None
        raw = sanitize_console_operator_text(text or "") or (text or "")
        m = re.match(r"(?is)^id=([0-9a-f]{8})\b", raw.strip())
        if m:
            job_id = m.group(1).lower()
        if job_id:
            reply = f"DONE id={job_id} exit=126 {reason}"
        else:
            reply = f"DONE exit=126 {reason}"
        return HandleResult(
            action="deny",
            nick=nick,
            target=target,
            text=text,
            reply=reply,
            deny_reason=reason,
        )

    def _capability_deny(
        self,
        nick: str,
        target: str,
        text: str,
        reason: str,
        qid: str | None = None,
    ) -> HandleResult:
        """FR #5552: cap-off DONE keeps id= when the operator sent one."""
        q = (qid or "").strip().lower()
        id_bit = f" id={q}" if q else ""
        return HandleResult(
            action="capability_deny",
            nick=nick,
            target=target,
            text=text,
            reply=f"DONE{id_bit} exit=126 {reason}",
        )

    def _register_verb_log_resume(self, nick: str, job_id: str, delivered: dict | None) -> None:
        """FR #5519: IRC fallback CONT must have a resume buffer (payload bytes)."""
        if not delivered or str(delivered.get("via") or "") != "irc":
            return
        runner = self.shell_runner
        if runner is None or not hasattr(runner, "register_log_resume"):
            return
        raw = delivered.get("payload")
        if isinstance(raw, bytes):
            body = raw.decode("utf-8", errors="replace")
        else:
            body = str(raw or "")
        if not body.strip():
            return
        runner.register_log_resume(nick, job_id, body, next_offset=1)

    def _register_priority_job(self, job_id: str, nick: str) -> dict[str, Any]:
        """FR #5526: track async PRIORITY connect (separate from per-nick shell inflight)."""
        jid = (job_id or "").strip().lower()
        entry: dict[str, Any] = {
            "nick": nick,
            "abandoned": False,
            "terminal": False,
        }
        with self._priority_jobs_lock:
            self._priority_jobs[jid] = entry
        return entry

    def abandon_open_priority_jobs(self) -> list[tuple[str, str]]:
        """FR #5526: mark open PRIORITY jobs abandoned; return (nick, job_id) for stop flush."""
        out: list[tuple[str, str]] = []
        with self._priority_jobs_lock:
            for jid, entry in list(self._priority_jobs.items()):
                if entry.get("terminal") or entry.get("abandoned"):
                    continue
                entry["abandoned"] = True
                nick = str(entry.get("nick") or "")
                if nick and jid:
                    out.append((nick, jid))
            self._priority_jobs.clear()
        return out

    def _allow_meta(self, nick: str, account: str | None) -> dict[str, str | None]:
        """FR #4067: mode/account/channel for auth-allow on shell/job/pipe/update."""
        detail = self.auth.allow_detail(nick, account)
        acct = (account or "").strip() or None
        if acct is None:
            amap = getattr(self.auth, "account_map", None)
            if amap is not None:
                got = amap.get(nick)
                acct = (got or "").strip() or None
        return {
            "allow_mode": detail.get("mode"),
            "allow_account": acct,
            "allow_channel": detail.get("channel"),
        }

    def _clear_unused_dcclisten(self, job_id: str, *, reason: str) -> None:
        """FR #5613: VERSION/STATUS/PRIORITY/UPDATE must not leave a stale offer."""
        runner = self.shell_runner
        if runner is None:
            return
        discard = getattr(runner, "discard_dcclisten", None)
        if callable(discard):
            discard(job_id, reason=reason)

    def handle_raw(self, line: str) -> HandleResult | None:
        """FR #5775: catch any unhandled verb fault -> intake + DONE exit=1."""
        try:
            return self._handle_raw_unguarded(line)
        except Exception as exc:  # noqa: BLE001 - CAST IRON catch-all
            try:
                import airc_fail_intake as _fail

                _fail.report_verb_failure(
                    'handle',
                    exc,
                    args={'line_len': len(line or '')},
                    wait_s=1.0,
                )
                reply = _fail.failure_reply('00000000', 'handle', exc)
            except Exception:
                reply = (
                    'err id=00000000 seq=1 code=verb-fault\n'
                    'DONE id=00000000 exit=1'
                )
            nick = 'unknown'
            try:
                _tags, rest = parse_message_tags((line or '').rstrip('\r\n'))
                m = _PRIVMSG_RE.match(rest)
                if m:
                    nick = m.group(1)
            except Exception:
                pass
            return HandleResult(
                action='shell',
                nick=nick,
                target=getattr(self, 'nick', None) or 'console',
                text=line or '',
                reply=reply,
            )

    def _handle_raw_unguarded(self, line: str) -> HandleResult | None:
        tags, rest = parse_message_tags(line.rstrip("\r\n"))
        m = _PRIVMSG_RE.match(rest)
        if not m:
            return None
        nick, target, text = m.group(1), m.group(2), m.group(3)
        self.verb_log_nick = nick
        account = tags.get("account")
        amap = getattr(self.auth, "account_map", None)
        if amap is not None and account:
            amap.set(nick, account)

        # Issue #298: CTCP PING / "ping [pattern]" - no operator auth; presence only.
        ctcp_payload = parse_ctcp_ping(text or "")
        if ctcp_payload is not None:
            return HandleResult(
                action="ctcp_pong",
                nick=nick,
                target=target,
                text=text,
                reply=ctcp_payload,
            )
        ctcp_tag = parse_ctcp_message(text or "")
        if ctcp_tag is not None:
            # FR #5614: CTCP VERSION/ACTION/... must never fall through to PowerShell.
            return HandleResult(
                action="ctcp_ignore",
                nick=nick,
                target=target,
                text=text,
            )
        ping_pat = parse_ping_command(text or "")
        if ping_pat is not None:
            if nick_matches_pattern(ping_pat, self.nick, self.machine):
                return HandleResult(
                    action="pong",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=f"pong {self.nick}",
                )
            if is_channel_target(target):
                self.channel_traffic.append(text)
                return HandleResult(action="silent_channel", nick=nick, target=target, text=text)
            # Direct ping that does not match us - ignore quietly.
            return HandleResult(action="ping_miss", nick=nick, target=target, text=text)

        if is_channel_target(target):
            # Fleet / workstation: silent in channel (DM only). Client: accept commands
            # on the selected control channel only (FR #3401). Auth is the same live
            # channel +o/+h check either way (FR #3639).
            self.channel_traffic.append(text)
            if not self.channel_commands:
                return HandleResult(action="silent_channel", nick=nick, target=target, text=text)
            ctrl = (self.channel or "").strip().lower()
            if target.strip().lower() != ctrl:
                return HandleResult(action="silent_channel", nick=nick, target=target, text=text)
            if not self.auth.allow(nick, account):
                return self._deny_result(nick, target, text, account)
            # Fall through to command routing (same as DM).
        else:
            # Direct PRIVMSG to console nick
            if not self.auth.allow(nick, account):
                return self._deny_result(nick, target, text, account)

        # FR #2570: strip Halloy/bobtalk Heard:/@nick noise before verb/shell routing.
        cmd = sanitize_console_operator_text(text or "")
        if not cmd:
            return HandleResult(action="empty", nick=nick, target=target, text=text)
        # FR #5101: Heard: unwrap of mention-ACK must not re-run out/err/DONE/UPDATE accepted.
        if is_console_self_reply(cmd):
            return HandleResult(action="ignore_reply", nick=nick, target=target, text=text)
        # FR #5678: leading id= that is not exactly 8 hex must not fall through to shell
        # (or be reassigned a fresh id). Reject before verb/shell routing.
        id_state, id_tok, _id_rest = leading_job_id_state(cmd)
        if id_state == "bad":
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="bad_id",
                nick=nick,
                target=target,
                text=text,
                reply=format_bad_id_reply(id_tok or ""),
                **meta,
            )
        if cmd.lower() in {".quit", "!quit", "exit"}:
            self.sessions.close_nick(nick)
            return HandleResult(action="close", nick=nick, target=target, text=text, reply="console closed")
        if cmd.lower() in {".help", "!help"}:
            return HandleResult(
                action="help",
                nick=nick,
                target=target,
                text=text,
                reply=(
                    "airc console (FR #75/#3287): default PowerShell -NoProfile; "
                    "cmd: COMSPEC escape (prefer cmd: dir for listings; bare dir is PS); "
                    "psb64:<base64> EncodedCommand; "
                    "replies out/err id= seq= then DONE id= exit= (batch capture + FLOOD_S); "
                    "STATUS|VERSION|PUT|CHUNK|PUTEND|RUN|GET|GETCHUNK|JOB|CANCEL; "
                    "PRIORITY prepare <ENAME> [instance=] (FR #5286 REPPREPDIRECT2); "
                    "UPDATE airc|bob|jeeves [ver] schedules detached MSI update "
                    "(ops-gated remote; not auto self-update - FR #3764); "
                    "PRIORITY connect|status [instance-id] (CredMan + allowlist, FR #5284); PRIORITY formStart|subform|getRows (FR #5285 fixture walk); "
                    "EXTENSION install|status [-WhatIf] isolated worker (FR #5290); "
                    "NETWORK|NETWORK diag isolated worker (FR #5298); "
                    "LEGION {host|ip} [-WhatIf] [-Profile fleet|client|workstation] isolated worker (FR #5308/#5758); "
                    f"capabilities shell={self.capabilities.shell_mode} "
                    f"jobs={self.capabilities.jobs} update={self.capabilities.update} "
                    f"extension={self.capabilities.extension}; "
                    ".quit closes; silent on channel; answers ping"
                ),
            )

        caps = self.capabilities

        # FR #5285: PRIORITY form walk (read path) via in-service fixture worker.
        walk = _priority.parse_priority_walk_command(cmd)
        if walk is not None:
            allow = _priority.resolve_walk_allowlist_path(
                self.install_root, self.priority_allowlist or self.priority_allowlist_path
            )
            fix = Path(self.priority_fixture) if self.priority_fixture else None
            result = _priority.run_priority_walk(
                text=cmd,
                allowlist_path=allow,
                fixture_path=fix,
            )
            # FR #5524: do not JobProtocol._emit here. on_line sends HandleResult.reply
            # for action=priority (FR #5518). Emitting plus reply doubled every walk line.
            self._clear_unused_dcclisten((walk[1] or {}).get("id") or "", reason="priority")
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="priority",
                nick=nick,
                target=target,
                text=text,
                reply="\n".join(result.lines),
                **meta,
            )

        # FR #5284: PRIORITY connect/status - allowlist + CredMan; never password on IRC.
        # FR #5526: when priority_reply_send is bound, connect runs off the receive loop.
        pri = _priority.parse_priority_command(cmd)
        if pri is not None:
            if caps.shell_mode == "off":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 shell-disabled",
                )
            job_id, subcmd, instance_id = pri
            qid = (job_id or "").strip().lower() or uuid.uuid4().hex[:8]
            send_hook = getattr(self, "priority_reply_send", None)
            use_async = (
                subcmd == "connect"
                and callable(send_hook)
                and nick
            )
            on_done = None
            if use_async:
                entry = self._register_priority_job(qid, nick)

                def _deliver(res: _priority.PriorityVerbResult, _entry=entry, _nick=nick) -> None:
                    with self._priority_jobs_lock:
                        if _entry.get("abandoned") or _entry.get("terminal"):
                            return
                        _entry["terminal"] = True
                    hook = getattr(self, "priority_reply_send", None)
                    if not callable(hook):
                        return
                    # _on_console_out flattens newlines — send each wire line alone.
                    for line in res.reply_lines():
                        try:
                            hook(str(_nick), line)
                        except Exception:
                            break

                on_done = _deliver
            try:
                if use_async:
                    result = self.priority_runner(
                        subcmd,
                        instance_id,
                        job_id=qid,
                        install_root=self.install_root,
                        allowlist_path=self.priority_allowlist_path,
                        wait=False,
                        on_done=on_done,
                    )
                else:
                    result = self.priority_runner(
                        subcmd,
                        instance_id,
                        job_id=qid,
                        install_root=self.install_root,
                        allowlist_path=self.priority_allowlist_path,
                    )
            except TypeError:
                try:
                    result = self.priority_runner(
                        subcmd,
                        instance_id,
                        job_id=qid,
                        install_root=self.install_root,
                        allowlist_path=self.priority_allowlist_path,
                    )
                except TypeError:
                    result = self.priority_runner(subcmd, instance_id, job_id=qid)
            if not isinstance(result, _priority.PriorityVerbResult):
                result = _priority.PriorityVerbResult(
                    False, 1, qid, {"ok": False}, error="bad-priority-runner"
                )
            self._clear_unused_dcclisten(qid, reason="priority")
            meta = self._allow_meta(nick, account)
            reply = "" if getattr(result, "pending", False) else result.reply_text()
            return HandleResult(
                action="priority",
                nick=nick,
                target=target,
                text=text,
                reply=reply,
                **meta,
            )

        # FR #5533: bare / unknown PRIORITY is usage, not a PowerShell command.
        usage_jid = _priority.parse_priority_usage(cmd)
        if usage_jid is not None:
            qid = usage_jid or uuid.uuid4().hex[:8]
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="priority",
                nick=nick,
                target=target,
                text=text,
                reply=_priority.format_priority_usage(qid),
                **meta,
            )

        # FR #5659: CRED id= via=dcc --- stage username/password in memory (TLS DCC only).
        cred_cmd = None
        try:
            import airc_passed_cred as _pcred
            import airc_identity as _ident

            cred_cmd = _pcred.parse_cred_command(cmd)
        except Exception:
            cred_cmd = None
        if cred_cmd is not None:
            # FR #5684: HandleResult first field is action=; never positional True/reply.
            qid = (cred_cmd.get("qid") or "").lower()
            allow = self._allow_meta(nick, account)
            if _ident.irc_line_has_plaintext_secret(cmd):
                return self._capability_deny(
                    nick, target, text, "usage secrets-on-irc", qid
                )
            if (cred_cmd.get("via") or "") != "dcc":
                return self._capability_deny(
                    nick, target, text, "usage cred-requires-dcc", qid
                )
            offer = None
            if self.shell_runner is not None and qid:
                take = getattr(self.shell_runner, "take_dcclisten", None)
                if callable(take):
                    offer = take(qid)
            if offer is None:
                return self._capability_deny(
                    nick, target, text, "usage cred-requires-dcc", qid
                )
            try:
                import airc_dcc_bulk as _dcc

                # FR #5684: real API is receive_upload_from_offer -> (bytes, sha256).
                raw, _digest = _dcc.receive_upload_from_offer(offer)
                pair = _pcred.parse_cred_json(raw)
                store = getattr(self, "passed_cred_store", None) or _pcred.GLOBAL_PASSED_CREDS
                store.put(qid, pair["username"], pair["password"])
            except Exception as exc:  # noqa: BLE001
                reason = type(exc).__name__
                if qid:
                    reply = f"err id={qid} seq=1 cred failed: {reason}\nDONE id={qid} exit=1 auth_failed"
                else:
                    reply = f"err seq=1 cred failed: {reason}\nDONE exit=1 auth_failed"
                return HandleResult(
                    action="cred",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=reply,
                    **allow,
                )
            done = f"DONE id={qid} exit=0 cred-staged account={pair['username']}"
            return HandleResult(
                action="cred",
                nick=nick,
                target=target,
                text=text,
                reply=f"out id={qid} seq=1 CRED staged identity=passed\n{done}",
                **allow,
            )

        # FR #5308: LEGION {target} --- isolated stub worker; same auth as UPDATE.
        leg = _legion.parse_legion_command(cmd)
        if leg is not None:
            qid = str(leg.get("qid") or "").strip().lower()
            if caps.shell_mode == "off":
                return self._capability_deny(
                    nick, target, text, "shell-disabled", qid
                )
            if caps.update == "off":
                return self._capability_deny(
                    nick, target, text, "update-disabled", qid
                )
            if leg.get("unknown_flag") or leg.get("error") == "unknown-flag":
                meta = self._allow_meta(nick, account)
                return HandleResult(
                    action="legion",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=format_known_verb_usage(
                        qid,
                        "LEGION",
                        "{host|ip} [-WhatIf] [-Profile fleet|client|workstation]",
                        str(leg.get("unknown_flag") or ""),
                    ),
                    **meta,
                )
            if leg.get("error") == "bad-profile":
                meta = self._allow_meta(nick, account)
                return HandleResult(
                    action="legion",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=format_known_verb_usage(
                        qid,
                        "LEGION",
                        "{host|ip} [-WhatIf] [-Profile fleet|client|workstation]",
                        f"-Profile={leg.get('profile') or ''}",
                    ),
                    **meta,
                )
            if leg.get("error"):
                # FR #5527: include id= so ear/airc-replies can correlate denies.
                reason = str(leg.get("error") or "")
                if reason == "secrets-on-irc":
                    return self._capability_deny(
                        nick, target, text, "usage secrets-on-irc", qid
                    )
                return self._capability_deny(
                    nick,
                    target,
                    text,
                    f"bad-target reason={reason}",
                    qid,
                )
            offer = None
            if self.shell_runner is not None and qid:
                take = getattr(self.shell_runner, "take_dcclisten", None)
                if callable(take):
                    offer = take(qid)
            send_fn = getattr(self, "legion_log_send", None)
            delivered: dict | None = None

            def _deliver_installer(res: _legion.LegionVerbResult) -> None:
                nonlocal delivered
                fails = list(res.failures or [])
                if not fails and res.error:
                    fails = [{"host": leg.get("target"), "error": str(res.error)}]
                # FR #5530: WhatIf plan (msi/psexec) must reach the DCC JSON.
                extra: dict = {}
                if getattr(res, "msi", ""):
                    extra["msi"] = res.msi
                if getattr(res, "psexec", ""):
                    extra["psexec"] = res.psexec
                plan = getattr(res, "plan", None)
                if isinstance(plan, dict) and plan:
                    extra["plan"] = plan
                if getattr(res, "identity", ""):
                    extra["identity_source"] = res.identity
                    extra["identity"] = res.identity
                if getattr(res, "identity_label", ""):
                    extra["identity_label"] = res.identity_label
                    if "identity" not in extra:
                        extra["identity"] = res.identity_label
                if getattr(res, "computer_account", ""):
                    extra["computer_account"] = res.computer_account
                acct = str(getattr(res, "account", "") or "")
                if isinstance(getattr(res, "plan", None), dict):
                    if not acct:
                        acct = str((res.plan or {}).get("account") or "")
                # account may live on failures / identity_label paren
                if not acct and getattr(res, "identity_label", ""):
                    lab = str(res.identity_label)
                    if "(" in lab and lab.endswith(")"):
                        acct = lab[lab.find("(") + 1 : -1]
                if acct:
                    extra["account"] = acct
                # FR #5758: profile preserve + post-install verify on JSON/DONE.
                for key in (
                    "profile",
                    "profile_before",
                    "profile_after",
                    "profile_warn",
                    "installed_version",
                    "service",
                ):
                    val = str(getattr(res, key, "") or "").strip()
                    if val:
                        extra[key] = val
                log = _legion.build_legion_log(
                    target=leg.get("target") or "",
                    whatif=bool(leg.get("whatif")),
                    summary=res.status or "",
                    failures=fails,
                    extra=extra or None,
                )
                delivered = _legion.deliver_legion_log(
                    job_id=qid or res.job_id,
                    log=log,
                    offer=offer,
                    send_fn=send_fn,
                )
                self._register_verb_log_resume(nick, qid or res.job_id, delivered)
                emit = getattr(self, "legion_log_emit", None)
                if callable(emit):
                    emit(delivered)

            try:
                result = self.legion_runner(
                    target=leg["target"],
                    whatif=leg["whatif"],
                    job_id=qid,
                    on_done=_deliver_installer,
                    cred_id=str(leg.get("cred_id") or ""),
                    profile=leg.get("profile"),
                )
            except TypeError:
                try:
                    result = self.legion_runner(
                        target=leg["target"],
                        whatif=leg["whatif"],
                        job_id=qid,
                        profile=leg.get("profile"),
                    )
                except TypeError:
                    try:
                        result = self.legion_runner(
                            target=leg["target"],
                            whatif=leg["whatif"],
                            job_id=qid,
                        )
                    except TypeError:
                        result = self.legion_runner(target=leg["target"])
            except Exception:
                result = _legion.LegionVerbResult(
                    False, "LEGION err isolated-fault", job_id=qid
                )
            if not isinstance(result, _legion.LegionVerbResult):
                result = _legion.LegionVerbResult(False, "LEGION err bad-runner")
            if delivered is None and (result.failures or result.error or result.status):
                _deliver_installer(result)
            meta = self._allow_meta(nick, account)
            reply = result.reply_text()
            if delivered is not None:
                reply = f"{reply} {delivered['summary']}"
            return HandleResult(
                action="legion",
                nick=nick,
                target=target,
                text=text,
                reply=reply,
                **meta,
            )

        # FR #5298 / #5711: NETWORK / NETWORK diag - isolated worker; same auth as UPDATE.
        net = _network.parse_network_command(cmd)
        if net is not None:
            qid = str(net.get("qid") or "").strip().lower()
            if net.get("error") == "secrets-on-irc":
                return self._capability_deny(
                    nick, target, text, "usage secrets-on-irc", qid
                )
            if net.get("usage"):
                meta = self._allow_meta(nick, account)
                return HandleResult(
                    action="network",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=format_known_verb_usage(
                        qid,
                        "NETWORK",
                        _network.NETWORK_USAGE,
                        net.get("unknown_flag") or None,
                    ),
                    **meta,
                )
            if caps.shell_mode == "off":
                return self._capability_deny(
                    nick, target, text, "shell-disabled", qid
                )
            if caps.update == "off":
                return self._capability_deny(
                    nick, target, text, "update-disabled", qid
                )
            qid = str(net.get("qid") or "").strip().lower()
            offer = None
            if self.shell_runner is not None and qid:
                take = getattr(self.shell_runner, "take_dcclisten", None)
                if callable(take):
                    offer = take(qid)
            send_fn = getattr(self, "network_log_send", None)
            delivered: dict | None = None

            def _deliver_inventory(res: _network.NetworkVerbResult) -> None:
                nonlocal delivered
                extra = res.identity_public() if hasattr(res, "identity_public") else {}
                payload = _network.build_network_payload(
                    net["action"],
                    whatif=net["whatif"],
                    hosts=list(res.hosts or []),
                    failures=list(res.failures or []),
                    extra=extra or None,
                )
                delivered = _network.deliver_network_payload(
                    job_id=qid or res.job_id,
                    payload=payload,
                    offer=offer,
                    send_fn=send_fn,
                )
                self._register_verb_log_resume(nick, qid or res.job_id, delivered)
                emit = getattr(self, "network_log_emit", None)
                if callable(emit):
                    emit(delivered)

            # FR #5711: explicit NETWORK ... cred=<id>, or job id when CRED was staged.
            cred_id = str(net.get("cred_id") or "").strip().lower()
            if not cred_id and qid:
                try:
                    import airc_passed_cred as _pcred

                    store = (
                        getattr(self, "passed_cred_store", None)
                        or _pcred.GLOBAL_PASSED_CREDS
                    )
                    if store.peek(qid):
                        cred_id = qid
                except Exception:
                    pass
            runner_kw = {
                "action": net["action"],
                "whatif": net["whatif"],
                "job_id": qid,
                "on_done": _deliver_inventory,
            }
            if cred_id:
                runner_kw["cred_id"] = cred_id
            try:
                result = self.network_runner(**runner_kw)
            except TypeError:
                try:
                    result = self.network_runner(
                        action=net["action"],
                        whatif=net["whatif"],
                        job_id=qid,
                        on_done=_deliver_inventory,
                    )
                except TypeError:
                    try:
                        result = self.network_runner(
                            action=net["action"],
                            whatif=net["whatif"],
                            job_id=qid,
                        )
                    except TypeError:
                        result = self.network_runner(action=net["action"])
            except Exception:
                result = _network.NetworkVerbResult(
                    False, "NETWORK err isolated-fault", job_id=qid
                )
            if not isinstance(result, _network.NetworkVerbResult):
                result = _network.NetworkVerbResult(False, "NETWORK err bad-runner")
            if delivered is None and (result.hosts or result.failures or result.identity):
                _deliver_inventory(result)
            meta = self._allow_meta(nick, account)
            reply = result.reply_text()
            if delivered is not None:
                reply = f"{reply} {delivered['summary']}"
            return HandleResult(
                action="network",
                nick=nick,
                target=target,
                text=text,
                reply=reply,
                **meta,
            )

        # FR #5290 / #5295: EXTENSION install/status --- isolated worker; UPDATE-style auth
        # plus dedicated extension=off (client/workstation default refuse).
        # FR #5520: DCC log joins worker via on_done (same pattern as LEGION #5385).
        ext = _extension.parse_extension_command(cmd)
        if ext is not None:
            qid = str(ext.get("qid") or "").strip().lower()
            if ext.get("error") == "secrets-on-irc":
                return self._capability_deny(
                    nick, target, text, "usage secrets-on-irc", qid
                )
            if ext.get("usage"):
                meta = self._allow_meta(nick, account)
                return HandleResult(
                    action="extension",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=format_known_verb_usage(
                        qid,
                        "EXTENSION",
                        _extension.EXTENSION_USAGE,
                        ext.get("unknown_flag") or None,
                    ),
                    **meta,
                )
            if caps.shell_mode == "off":
                return self._capability_deny(
                    nick, target, text, "shell-disabled", qid
                )
            if caps.update == "off":
                return self._capability_deny(
                    nick, target, text, "update-disabled", qid
                )
            if caps.extension == "off":
                return self._capability_deny(
                    nick, target, text, "extension-disabled", qid
                )
            qid = str(ext.get("qid") or "").strip().lower()
            offer = None
            if self.shell_runner is not None and qid:
                take = getattr(self.shell_runner, "take_dcclisten", None)
                if callable(take):
                    offer = take(qid)
            send_fn = getattr(self, "extension_log_send", None)
            delivered: dict | None = None

            def _deliver_extension(res: _extension.ExtensionVerbResult) -> None:
                nonlocal delivered
                log = _extension.extension_log_from_payload(
                    ext["action"],
                    whatif=ext["whatif"],
                    payload=getattr(res, "payload", None),
                )
                delivered = _extension.deliver_extension_log(
                    job_id=qid or res.job_id,
                    log=log,
                    offer=offer,
                    send_fn=send_fn,
                )
                self._register_verb_log_resume(nick, qid or res.job_id, delivered)
                emit = getattr(self, "extension_log_emit", None)
                if callable(emit):
                    emit(delivered)

            try:
                result = self.extension_runner(
                    action=ext["action"],
                    whatif=ext["whatif"],
                    job_id=qid,
                    on_done=_deliver_extension,
                    cred_id=str(ext.get("cred_id") or ""),
                )
            except TypeError:
                try:
                    result = self.extension_runner(
                        action=ext["action"],
                        whatif=ext["whatif"],
                        job_id=qid,
                    )
                except TypeError:
                    result = self.extension_runner(action=ext["action"])
            except Exception:
                result = _extension.ExtensionVerbResult(
                    False, "EXTENSION err isolated-fault", job_id=qid
                )
            if not isinstance(result, _extension.ExtensionVerbResult):
                result = _extension.ExtensionVerbResult(False, "EXTENSION err bad-runner")
            if delivered is None and getattr(result, "payload", None):
                _deliver_extension(result)
            meta = self._allow_meta(nick, account)
            reply = result.reply_text()
            if delivered is not None:
                reply = f"{reply} {delivered['summary']}"
            return HandleResult(
                action="extension",
                nick=nick,
                target=target,
                text=text,
                reply=reply[:IRC_SAFE_PAYLOAD],
                **meta,
            )

        # FR #77: UPDATE schedules Update-BobiverseService Check (detached); never msiexec here.
        # FR #5670: UPDATE-shaped but not allowlisted => usage exit=2 (never PowerShell).
        update_usage_qid = update_usage_job_id(cmd)
        if update_usage_qid is not None:
            qid = (update_usage_qid or "").strip().lower() or "00000000"
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="update",
                nick=nick,
                target=target,
                text=text,
                reply=format_known_verb_usage(qid, "UPDATE", UPDATE_USAGE),
                **meta,
            )
        parsed = parse_update_command(cmd)
        if parsed is not None:
            # FR #3287: shell=off is status-only; update=off refuses even when shell=operators.
            qid, _rest = split_console_job_id(cmd)
            qid = (qid or "").strip().lower() or uuid.uuid4().hex[:8]
            if caps.shell_mode == "off":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=f"DONE id={qid} exit=126 shell-disabled",
                )
            if caps.update == "off":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=f"DONE id={qid} exit=126 update-disabled",
                )
            product, ver = parsed
            try:
                result = self.update_scheduler(
                    product,
                    version=ver,
                    install_root=self.install_root,
                )
            except TypeError:
                # test doubles may omit kwargs
                result = self.update_scheduler(product, version=ver)
            if not isinstance(result, UpdateScheduleResult):
                result = UpdateScheduleResult(
                    False, "bad-scheduler", product=product, version=ver
                )
            result.job_id = qid
            self._clear_unused_dcclisten(qid, reason="update")
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="update",
                nick=nick,
                target=target,
                text=text,
                reply=result.reply_line(),
                **meta,
            )

        # FR #5286: PRIORITY prepare (TYPE=P EXEC REPPREPDIRECT2 + UPD/.prp gates).
        prep = parse_priority_prepare_command(cmd)
        if prep is not None:
            pw = _load_priority_worker()
            run = getattr(pw, "run_priority_prepare", None) if pw else None
            insts = load_priority_instances(self.install_root)
            if run:
                hooks = build_console_prepare_hooks(self.install_root)
                body = run(
                    prep.get("name") or "",
                    instance_id=prep.get("instance") or "",
                    instances=insts,
                    **hooks,
                )
            else:
                body = {
                    "ok": False,
                    "reason": "name_missing" if not (prep.get("name") or "") else "worker_missing",
                    "ename": prep.get("name") or "",
                    "sql_faked": False,
                }
            # Never put passwords on the wire.
            # FR #5525: out + DONE on separate lines (connect/status framing).
            # FR #5616: never character-slice JSON — use shared byte-budget helper.
            safe_body = {
                k: v for k, v in body.items() if "pass" not in str(k).lower()
            }
            if "action" not in safe_body:
                safe_body["action"] = "prepare"
            jid = (prep.get("qid") or "").strip() or uuid.uuid4().hex[:8]
            self._clear_unused_dcclisten(jid, reason="priority")
            exit_code = 0 if body.get("ok") else 1
            out_line, exit_code = _priority.format_bounded_priority_out(
                jid, safe_body, exit_code
            )
            done_line = f"DONE id={jid} exit={exit_code}"
            reply = f"{out_line}\n{done_line}"
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="priority",
                nick=nick,
                target=target,
                text=text,
                reply=reply,
                **meta,
            )

        # FR #5003: caller advertises reverse-DCC listen endpoint before/alongside shell.
        if self.shell_runner is not None:
            import airc_dcc_bulk as _dcc_listen

            if _dcc_listen.is_dcclisten_command(cmd) and self.shell_runner.note_dcclisten(cmd):
                meta = self._allow_meta(nick, account)
                return HandleResult(
                    action="dcc_listen", nick=nick, target=target, text=text, **meta
                )

        # FR #4794: CONT/RESUME pages truncated shell output (no re-run).
        # FR #5519: log-origin buffers stay CONT-able when shell=off.
        cont = parse_cont_request(cmd)
        if cont is not None and self.shell_runner is not None:
            jid_pre, _off_pre = cont
            log_cont = self.shell_runner.resume_kind(nick, jid_pre) == "log"
            if caps.shell_mode == "off" and not log_cont:
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 shell-disabled",
                )
            jid, off = cont
            self.shell_runner.continue_replies(nick, jid, off)
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="shell_cont", nick=nick, target=target, text=text, **meta
            )

        # FR #78: PUT/RUN/JOB/STATUS protocol (before plain shell).
        parsed = parse_job_verb(cmd)
        if parsed is not None and self.job_protocol is not None:
            verb, kv = parsed
            # FR #3287 / #5281: shell=off / jobs=off keep STATUS + VERSION (read).
            if caps.shell_mode == "off" and verb not in CAPS_OFF_ALLOWED_VERBS:
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 shell-disabled",
                )
            if caps.jobs == "off" and verb not in CAPS_OFF_ALLOWED_VERBS:
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 jobs-disabled",
                )
            if verb == "CANCEL" and self.shell_runner is not None:
                try:
                    self.job_protocol.authorize(nick, verb)
                except JobProtocolError:
                    pass  # The job protocol emits its normal permission refusal below.
                else:
                    if self.shell_runner.cancel(nick, kv.get("id") or ""):
                        meta = self._allow_meta(nick, account)
                        return HandleResult(
                            action="job", nick=nick, target=target, text=text, **meta
                        )
            self.job_protocol.handle_async(nick, verb, kv)
            if verb in {"STATUS", "VERSION"}:
                self._clear_unused_dcclisten(kv.get("id") or "", reason=verb.lower())
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="job", nick=nick, target=target, text=text, **meta
            )

        # FR #75: oneshot PowerShell / cmd: / psb64: with DONE framing.
        if self.shell_runner is not None:
            if caps.shell_mode == "off":
                return HandleResult(
                    action="capability_deny",
                    nick=nick,
                    target=target,
                    text=text,
                    reply="DONE exit=126 shell-disabled",
                )
            self.shell_runner.start(nick, cmd)
            meta = self._allow_meta(nick, account)
            return HandleResult(
                action="shell", nick=nick, target=target, text=text, **meta
            )

        # Legacy interactive pipe (tests / AIRC without runner).
        if caps.shell_mode == "off":
            return HandleResult(
                action="capability_deny",
                nick=nick,
                target=target,
                text=text,
                reply="DONE exit=126 shell-disabled",
            )
        self.sessions.pipe(nick, cmd)
        meta = self._allow_meta(nick, account)
        return HandleResult(
            action="pipe", nick=nick, target=target, text=text, **meta
        )



# FR #5775: central handle_raw catch covers these IRC verbs / entries.
try:
    import airc_fail_intake as _fail_intake

    for _verb in (
        'update',
        'version',
        'status',
        'legion',
        'extension',
        'network',
        'priority',
        'shell',
        'cred',
        'job',
        'put',
        'get',
        'dcclisten',
        'help',
        'handle',
    ):
        _fail_intake.mark_wrapped(_verb)
except Exception:
    pass


def home_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("AIRC_CONSOLE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".airc-console"


def ensure_nickserv_password(path: Path, *, mint: bool = True) -> str | None:
    """Load or mint the NickServ password (issue #271).

    First start writes a GUID into ``console.password`` and reuses it later.
    This is **not** the Ergo server PASS - that comes from env / ergo.password.
    """
    import uuid

    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    if not mint:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = str(uuid.uuid4())
    path.write_text(secret + "\n", encoding="utf-8")
    try:
        # Best-effort: owner-only on POSIX; Windows ACLs set by install/hotpatch.
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


def resolve_server_password(
    *,
    home: Path | None = None,
    password_file: Path | None = None,
) -> str | None:
    """Ergo / IRC server PASS - never invent; never use NickServ GUID file alone.

    Order: AIRC_CONSOLE_SERVER_PASSWORD, AGENTIC_IRC_PASSWORD, AIRC_CONSOLE_PASSWORD
    (legacy), then ``ergo.password`` / ``connect.password`` beside home or
    ``~/.grok/ergo/connect.password``. Explicit ``password_file`` is **not** used
    here when it is the NickServ GUID path (``console.password``).
    """
    for key in (
        "AIRC_CONSOLE_SERVER_PASSWORD",
        "BOB_IRC_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_PASSWORD",
    ):
        env = os.environ.get(key)
        if env and env.strip():
            return env.strip()
    candidates: list[Path] = []
    # Legacy: only treat password_file as server PASS when it is NOT console.password
    if password_file is not None and password_file.name.lower() != "console.password":
        candidates.append(password_file)
    if home is not None:
        candidates.extend(
            [
                home / "ergo.password",
                home / "connect.password",
            ]
        )
    # Fleet default connect.password - only when using the real user console home
    # (avoid leaking ~/.grok secrets into hermetic tests with a tmp home).
    real_home = home_dir()
    if home is None or Path(home).resolve() == real_home.resolve():
        candidates.append(Path.home() / ".grok" / "ergo" / "connect.password")
    for p in candidates:
        try:
            if p.is_file():
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return None
