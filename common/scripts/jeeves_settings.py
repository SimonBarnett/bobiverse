"""FR #6436 foundation: Jeeves appliance settings schema + LAN-only API helpers.

Off by default: importing this module never starts a server.
FR #6442: migrate NSSM/env inventory into appliance-settings.json and apply
file-backed values into the process environment (env still overrides).
FR #6443: restart-when-idle (ircJeeves only) + read-only status.
FR #6754: read-only queue JSON (GET /api/queue).
HTTP UI is FR #6440; Auth/sessions: jeeves_settings_auth (FR #6441).
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Source roots scanned for environ.get("BOB_*"|JEEVES_*) gaps (foundation pin).
_HERE = Path(__file__).resolve().parent
SCAN_ROOTS: tuple[Path, ...] = (
    _HERE / "fuel_chain.py",
    _HERE / "jeeves_main.py",
    _HERE / "chair_health.py",
    _HERE / "gitclaim.py",
    _HERE / "bobreport.py",
    _HERE / "copilot_dispatch.py",
    _HERE / "github_api_budget.py",
    _HERE / "irc_agent.py",
)

_ENV_GET_RE = re.compile(
    r"""os\.environ\.get\(\s*['"]((?:BOB_|JEEVES_|GH_|GITHUB_)[A-Z0-9_]+)['"]"""
)

# Keys that may appear in scanned sources but are not appliance settings
# (transient / OS / install-only). Keep the gap test honest for real config.
_SCAN_ALLOW_MISSING = frozenset(
    {
        # Install / host / tool paths --- not appliance UI knobs (FR #6442).
        "BOBIVERSE_PYTHON",
        "BOB_INSTALL_ROOT",
        "JEEVES_INSTALL_ROOT",
        "BOB_MACHINE_ID",
        "BOB_WEEKLY_LOG",
        "BOB_WEEKLY_FORCE_SYSTEM_PROFILE",
        "BOB_XAI_WEEKLY_FETCH_TIMEOUT_S",
        "BOB_GROK_AUTH_PATH",
        "BOB_GROK_EXE",
        "BOB_GROK_WEEKLY_USER_HOME",
        "BOB_CURSOR_USD_GBP_RATE",
        "BOB_EAR_HOME",
        "BOB_HOME",
        "BOB_IRC_DEBUG",
        "BOB_IRC_SKIP_PRIOR_CLEAN",
        "BOB_CHANSERV_REGISTER_JOIN_WAIT_S",
        "BOB_CHANSERV_REGISTER_WAIT_S",
        "BOB_CHANSERV_SYNC_TTL_S",
        "BOB_CONSOLE_OUTBOX_FLOOD_S",
        "BOB_GITCLAIM_LOCK_S",
    }
)


@dataclass(frozen=True)
class SettingSpec:
    key: str
    type: str  # bool | int | float | str | secret
    default: str
    store: str  # env | file | nssm
    restart: bool
    secret: bool = False
    description: str = ""
    choices: tuple[str, ...] = ()


def _spec(
    key: str,
    typ: str,
    default: str,
    *,
    store: str = "file",
    restart: bool = False,
    secret: bool = False,
    description: str = "",
    choices: tuple[str, ...] = (),
) -> SettingSpec:
    return SettingSpec(
        key=key,
        type=typ,
        default=default,
        store=store,
        restart=restart,
        secret=secret or typ == "secret",
        description=description,
        choices=tuple(choices or ()),
    )


# Appliance inventory (FR #6436 + #6442): file-backed; process env still overrides.
# store=file means migrate/apply target is appliance-settings.json.
SCHEMA: tuple[SettingSpec, ...] = (
    _spec(
        "BOB_FUEL_CODERABBIT",
        "bool",
        "0",
        description="Hold MRB for CodeRabbit when 1/on/true (FR #5317/#5865).",
    ),
    _spec(
        "BOB_CODERABBIT_WAIT_MIN",
        "float",
        "12",
        description="Minutes to wait for CodeRabbit before coderabbit=timeout.",
    ),
    _spec(
        "BOB_CODERABBIT_ABSENT_SEC",
        "float",
        "120",
        description="Silence seconds before coderabbit=absent.",
    ),
    _spec(
        "BOB_FUEL_COPILOT",
        "bool",
        "0",
        description="Optional Copilot fuel stage (never required for fleet offer).",
    ),
    _spec(
        "BOB_FUEL_FLEET",
        "bool",
        "0",
        description="Optional fleet fuel stage (off by default).",
    ),
    _spec(
        "BOB_COPILOT_OBSERVE",
        "bool",
        "0",
        description="Observe-only Copilot dispatch (no live agents/tasks POST).",
    ),
    _spec("BOB_DIGEST_HOME", "str", "", description="Digest / report home directory."),
    _spec("BOB_DIGEST_URL", "str", "", description="Public digest POST URL override."),
    _spec("BOB_DIGEST_STALE_S", "float", "900", description="Digest stale threshold seconds."),
    _spec("BOB_PUBLIC_BASE", "str", "", description="Public webhook base URL."),
    _spec("BOB_BORED_IDLE_S", "float", "120", description="Idle seconds before !bored."),
    _spec("BOB_IRC_IDLE_DEAD_S", "float", "", description="IRC idle dead timeout seconds."),
    _spec("BOB_IRC_IDLE_PING_S", "float", "", description="IRC idle ping interval seconds."),
    _spec("BOB_IRC_RECONNECT_MAX", "int", "", description="Max IRC reconnect attempts."),
    _spec("BOB_IRC_RECV_TIMEOUT_S", "float", "", description="IRC recv timeout seconds."),
    _spec("BOB_IRC_THROTTLE_BASE_S", "float", "", description="IRC throttle base seconds."),
    _spec("JEEVES_HOME", "str", "", store="env", description="Chair home override."),
    _spec("BOB_JEEVES_HOME", "str", "", store="env", description="Alias chair home override."),
    _spec(
        "JEEVES_TICKET_CLOSURE_S",
        "float",
        "900",
        description="Ticket-closure backup poll interval seconds.",
    ),
    _spec(
        "JEEVES_TICKET_CLOSURE_WAKE",
        "bool",
        "0",
        description="Force legacy GrokBot wake when no wake URL.",
    ),
    _spec(
        "JEEVES_TICKET_CLOSURE_WAKE_URL",
        "str",
        "",
        description="HTTPS Bob wake URL (close + stall callbacks).",
    ),
    _spec(
        "JEEVES_BOB_WAKE_URL",
        "str",
        "",
        description="Alias for ticket-closure / Bob wake URL.",
    ),
    _spec(
        "JEEVES_TICKET_CLOSURE_WAKE_SECRET",
        "secret",
        "",
        restart=True,
        secret=True,
        description="Wake webhook Bearer secret (write-only).",
    ),
    _spec(
        "JEEVES_BOB_WAKE_SECRET",
        "secret",
        "",
        restart=True,
        secret=True,
        description="Alias wake webhook secret (write-only).",
    ),
    _spec("JEEVES_PROBE_LOCAL", "str", "", description="Local webhook probe base URL."),
    _spec("JEEVES_PROBE_PUBLIC", "str", "", description="Public webhook probe base URL."),
    _spec("JEEVES_RESYNC_REPOS", "str", "", description="Override resync repo list."),
    _spec(
        "GH_TOKEN",
        "secret",
        "",
        restart=True,
        secret=True,
        description="GitHub token for chair API (write-only; file-backed, env overrides).",
    ),
    _spec(
        "GITHUB_TOKEN",
        "secret",
        "",
        restart=True,
        secret=True,
        description="Alternate GitHub token (write-only; file-backed, env overrides).",
    ),
    _spec(
        "BOB_IRC_PASSWORD",
        "secret",
        "",
        restart=True,
        secret=True,
        description="Ergo connect password (write-only; file-backed, env overrides).",
    ),
    _spec(
        "BOB_IRC_SASL_PASSWORD",
        "secret",
        "",
        restart=True,
        secret=True,
        description="SASL password (write-only; file-backed, env overrides).",
    ),
    _spec(
        "BOB_IRC_SASL_USER",
        "str",
        "",
        restart=True,
        description="SASL username (file-backed; env overrides).",
    ),
)

SCHEMA_BY_KEY: dict[str, SettingSpec] = {s.key: s for s in SCHEMA}

CONFIG_NAME = "appliance-settings.json"
AUDIT_NAME = "settings-audit.jsonl"
BACKUP_DIR = "settings-backups"


_LAN_NETS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # unique local IPv6
)


def is_rfc1918(ip: str) -> bool:
    """True for RFC1918 private, ULA, or loopback (explicit nets; not TEST-NET)."""
    try:
        addr = ipaddress.ip_address(str(ip or "").strip())
    except ValueError:
        return False
    return any(addr in net for net in _LAN_NETS)


def is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(str(ip or "").strip()).is_loopback
    except ValueError:
        return False


def effective_client_ip(peer: str, x_forwarded_for: str | None = None) -> str:
    """LAN identity: trust X-Forwarded-For only when the TCP peer is loopback (FR #6757)."""
    peer_s = str(peer or "").strip()
    if is_loopback(peer_s):
        first = str(x_forwarded_for or "").split(",")[0].strip()
        if first:
            return first
    return peer_s


def reject_non_lan(client_ip: str) -> str | None:
    """Return an error string when *client_ip* is not LAN/loopback."""
    if is_rfc1918(client_ip):
        return None
    return "forbidden: non-LAN source"


def schema_gaps_from_source_scan(roots: Iterable[Path] | None = None) -> list[str]:
    """Keys read via os.environ.get that are missing from SCHEMA (minus allowlist)."""
    known = set(SCHEMA_BY_KEY) | set(_SCAN_ALLOW_MISSING)
    found: set[str] = set()
    for path in roots if roots is not None else SCAN_ROOTS:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _ENV_GET_RE.finditer(text):
            found.add(m.group(1))
    return sorted(k for k in found if k not in known)


def config_path(home: Path) -> Path:
    return Path(home) / CONFIG_NAME


def audit_path(home: Path) -> Path:
    return Path(home) / AUDIT_NAME


def backup_dir(home: Path) -> Path:
    return Path(home) / BACKUP_DIR


def load_config_file(home: Path) -> dict[str, Any]:
    path = config_path(home)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _truthy(raw: str) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_value(spec: SettingSpec, value: Any) -> str | None:
    """Return error text when *value* is invalid for *spec*."""
    raw = "" if value is None else str(value)
    if spec.type == "bool":
        if raw.strip().lower() not in {"0", "1", "true", "false", "yes", "no", "on", "off", ""}:
            return f"invalid bool for {spec.key}"
        return None
    if spec.type in ("int", "float"):
        if not str(raw).strip():
            return None  # empty clears to default at resolve time
        try:
            float(raw) if spec.type == "float" else int(raw)
        except (TypeError, ValueError):
            return f"invalid {spec.type} for {spec.key}"
        return None
    if spec.type in ("str", "secret"):
        if "\x00" in raw:
            return f"invalid string for {spec.key}"
        return None
    return f"unknown type {spec.type}"


def resolve_current(spec: SettingSpec, file_cfg: dict[str, Any]) -> tuple[str, str]:
    """Return (display_value, source) with env overriding file."""
    env_raw = os.environ.get(spec.key)
    if env_raw is not None and str(env_raw) != "":
        src = "env"
        raw = str(env_raw)
    elif spec.key in file_cfg and file_cfg.get(spec.key) is not None:
        src = "file"
        raw = str(file_cfg.get(spec.key))
    else:
        src = "default"
        raw = str(spec.default)
    if spec.secret:
        return ("set" if str(raw).strip() else "unset", src)
    return (raw, src)


def api_get_settings(home: Path, *, client_ip: str) -> dict[str, Any]:
    err = reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    cfg = load_config_file(home)
    rows = []
    for spec in SCHEMA:
        value, source = resolve_current(spec, cfg)
        rows.append(
            {
                "key": spec.key,
                "type": spec.type,
                "default": spec.default if not spec.secret else "",
                "value": value,
                "source": source,
                "store": spec.store,
                "restart": bool(spec.restart),
                "secret": bool(spec.secret),
                "description": spec.description,
                "choices": list(spec.choices),
            }
        )
    return {"ok": True, "settings": rows}


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_audit(home: Path, row: dict[str, Any]) -> None:
    path = audit_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _backup_config(home: Path, cfg: dict[str, Any]) -> str:
    bdir = backup_dir(home)
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    bid = f"{stamp}-{os.getpid()}"
    path = bdir / f"{bid}.json"
    _write_json(path, {"v": 1, "backup_id": bid, "settings": cfg})
    return bid


def api_put_setting(
    home: Path,
    *,
    client_ip: str,
    key: str,
    value: Any,
    actor: str = "unknown",
) -> dict[str, Any]:
    err = reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    spec = SCHEMA_BY_KEY.get(str(key or "").strip())
    if spec is None:
        return {"ok": False, "error": f"unknown setting: {key}"}
    bad = validate_value(spec, value)
    if bad:
        return {"ok": False, "error": bad}
    cfg = load_config_file(home)
    before = dict(cfg)
    bid = _backup_config(home, before)
    raw = "" if value is None else str(value)
    if spec.type == "bool":
        cfg[spec.key] = "1" if _truthy(raw) else "0"
    else:
        cfg[spec.key] = raw
    # Never persist plaintext echo of secrets into audit value fields.
    audit_val = "set" if spec.secret and raw.strip() else ("unset" if spec.secret else raw)
    _write_json(config_path(home), cfg)
    _append_audit(
        home,
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": str(actor or "unknown")[:80],
            "key": spec.key,
            "action": "set",
            "value": audit_val,
            "backup_id": bid,
            "restart": bool(spec.restart),
        },
    )
    return {
        "ok": True,
        "backup_id": bid,
        "restart": bool(spec.restart),
        "key": spec.key,
    }


def api_rollback(
    home: Path,
    *,
    client_ip: str,
    backup_id: str,
    actor: str = "unknown",
) -> dict[str, Any]:
    err = reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    bid = str(backup_id or "").strip()
    if not bid or "/" in bid or "\\" in bid or ".." in bid:
        return {"ok": False, "error": "invalid backup_id"}
    path = backup_dir(home) / f"{bid}.json"
    if not path.is_file():
        return {"ok": False, "error": "backup not found"}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"ok": False, "error": "backup unreadable"}
    settings = doc.get("settings") if isinstance(doc, dict) else None
    if not isinstance(settings, dict):
        return {"ok": False, "error": "backup malformed"}
    current = load_config_file(home)
    safety = _backup_config(home, current)
    _write_json(config_path(home), settings)
    _append_audit(
        home,
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": str(actor or "unknown")[:80],
            "key": "*",
            "action": "rollback",
            "value": bid,
            "backup_id": safety,
            "restart": True,
        },
    )
    return {"ok": True, "backup_id": safety, "restored": bid}

def apply_file_settings(home: Path) -> list[str]:
    """Load appliance-settings.json into os.environ for unset keys (FR #6442).

    Existing non-empty environment values win. Secret values are applied the
    same way but never returned by the API. Returns the list of keys applied.
    """
    cfg = load_config_file(home)
    applied: list[str] = []
    for spec in SCHEMA:
        if spec.store not in ("file", "nssm"):
            continue
        if spec.key not in cfg or cfg.get(spec.key) is None:
            continue
        cur = os.environ.get(spec.key)
        if cur is not None and str(cur) != "":
            continue
        raw = str(cfg.get(spec.key))
        os.environ[spec.key] = raw
        applied.append(spec.key)
    return applied


def migrate_nssm_env_to_file(
    home: Path,
    *,
    actor: str = "migrate",
    keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Copy schema keys from process env into appliance-settings.json (FR #6442).

    Intended one-shot when leaving NSSM AppEnvironmentExtra. Does not print or
    audit secret plaintext (audit value is set/unset). Env still overrides at
    resolve/apply time until operators remove the NSSM entries.
    """
    want = {str(k).strip() for k in (keys or []) if str(k).strip()}
    cfg = load_config_file(home)
    before = dict(cfg)
    migrated: list[str] = []
    skipped: list[str] = []
    for spec in SCHEMA:
        if want and spec.key not in want:
            continue
        if spec.store not in ("file", "nssm"):
            skipped.append(spec.key)
            continue
        env_raw = os.environ.get(spec.key)
        if env_raw is None or str(env_raw) == "":
            skipped.append(spec.key)
            continue
        bad = validate_value(spec, env_raw)
        if bad:
            skipped.append(spec.key)
            continue
        raw = str(env_raw)
        if spec.type == "bool":
            cfg[spec.key] = "1" if _truthy(raw) else "0"
        else:
            cfg[spec.key] = raw
        migrated.append(spec.key)
    if not migrated:
        return {"ok": True, "migrated": [], "skipped": skipped, "backup_id": ""}
    bid = _backup_config(home, before)
    _write_json(config_path(home), cfg)
    for key in migrated:
        spec = SCHEMA_BY_KEY[key]
        audit_val = (
            "set"
            if spec.secret and str(cfg.get(key) or "").strip()
            else ("unset" if spec.secret else str(cfg.get(key) or ""))
        )
        _append_audit(
            home,
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "actor": str(actor or "migrate")[:80],
                "key": key,
                "action": "migrate",
                "value": audit_val,
                "backup_id": bid,
                "restart": bool(spec.restart),
            },
        )
    return {"ok": True, "migrated": migrated, "skipped": skipped, "backup_id": bid}


# --- FR #6443: restart-when-idle + read-only status ---------------------------------
RESTART_PENDING_NAME = "settings-restart-pending.json"
RESTART_SERVICE_NAME = "ircJeeves"  # CAST IRON: never Ergo / BobIrcd
_PROCESS_STARTED = time.time()


def restart_pending_path(home: Path) -> Path:
    return Path(home) / RESTART_PENDING_NAME


def chair_has_accepted_work(digest_home: Path) -> tuple[bool, int]:
    """True when queue.accepted has rows (review/job running)."""
    try:
        import gitclaim

        rows = gitclaim.load_accepted(Path(digest_home))
        n = len(rows) if isinstance(rows, list) else 0
        return n > 0, n
    except Exception:
        return False, 0


def restart_ircjeeves_only() -> dict[str, Any]:
    """Restart only the ircJeeves Windows service. Never Ergo or BobIrcd."""
    import shutil
    import subprocess

    nssm = shutil.which("nssm") or shutil.which("nssm.exe")
    attempts: list[list[str]] = []
    if nssm:
        attempts.append([nssm, "restart", RESTART_SERVICE_NAME])
    # Fallback: sc.exe (no Ergo/BobIrcd names anywhere in argv).
    sc = shutil.which("sc") or shutil.which("sc.exe")
    if sc:
        attempts.append([sc, "stop", RESTART_SERVICE_NAME])
        attempts.append([sc, "start", RESTART_SERVICE_NAME])
    if not attempts:
        return {"ok": False, "error": "no_nssm_or_sc", "service": RESTART_SERVICE_NAME}
    last_err = "restart_failed"
    for cmd in attempts:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if int(proc.returncode or 0) == 0:
                return {
                    "ok": True,
                    "via": Path(cmd[0]).name,
                    "service": RESTART_SERVICE_NAME,
                }
            last_err = f"exit_{proc.returncode}"
        except Exception as e:  # noqa: BLE001
            last_err = type(e).__name__
    return {"ok": False, "error": last_err, "service": RESTART_SERVICE_NAME}


def _write_restart_pending(home: Path, *, actor: str, reason: str) -> None:
    path = restart_pending_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "v": 1,
        "requested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "actor": str(actor or "unknown")[:80],
        "reason": str(reason or "")[:160],
        "service": RESTART_SERVICE_NAME,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def clear_restart_pending(home: Path) -> None:
    path = restart_pending_path(home)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def request_restart_when_idle(
    home: Path,
    *,
    client_ip: str,
    digest_home: Path | None = None,
    actor: str = "unknown",
    restart_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Restart ircJeeves now if idle; otherwise persist pending until accepted clears."""
    err = reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    dig = Path(digest_home) if digest_home is not None else Path(home)
    busy, n = chair_has_accepted_work(dig)
    if busy:
        reason = f"accepted={n}"
        _write_restart_pending(home, actor=actor, reason=reason)
        _append_audit(
            home,
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "actor": str(actor or "unknown")[:80],
                "key": "*",
                "action": "restart_deferred",
                "value": reason,
                "backup_id": "",
                "restart": True,
            },
        )
        return {
            "ok": True,
            "deferred": True,
            "pending": True,
            "reason": reason,
            "service": RESTART_SERVICE_NAME,
        }
    fn = restart_fn or restart_ircjeeves_only
    result = fn()
    clear_restart_pending(home)
    _append_audit(
        home,
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": str(actor or "unknown")[:80],
            "key": "*",
            "action": "restart" if result.get("ok") else "restart_failed",
            "value": str(result.get("via") or result.get("error") or "")[:80],
            "backup_id": "",
            "restart": True,
        },
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "error": str(result.get("error") or "restart_failed"),
            "service": RESTART_SERVICE_NAME,
        }
    return {
        "ok": True,
        "restarted": True,
        "via": result.get("via"),
        "service": RESTART_SERVICE_NAME,
    }


def tick_restart_when_idle(
    home: Path,
    *,
    digest_home: Path | None = None,
    restart_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Chair tick: if a deferred restart is pending and queue is idle, restart now."""
    path = restart_pending_path(home)
    if not path.is_file():
        return {"ok": True, "skipped": "no_pending"}
    dig = Path(digest_home) if digest_home is not None else Path(home)
    busy, n = chair_has_accepted_work(dig)
    if busy:
        return {"ok": True, "deferred": True, "reason": f"accepted={n}"}
    try:
        pending = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pending = {}
    actor = str((pending or {}).get("actor") or "pending")[:80]
    fn = restart_fn or restart_ircjeeves_only
    result = fn()
    clear_restart_pending(home)
    _append_audit(
        home,
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": actor,
            "key": "*",
            "action": "restart" if result.get("ok") else "restart_failed",
            "value": str(result.get("via") or result.get("error") or "pending")[:80],
            "backup_id": "",
            "restart": True,
        },
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "error": str(result.get("error") or "restart_failed"),
            "service": RESTART_SERVICE_NAME,
        }
    return {
        "ok": True,
        "restarted": True,
        "via": result.get("via"),
        "service": RESTART_SERVICE_NAME,
    }


def _appliance_secret_shape_error(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Belt-and-braces: refuse JSON that still looks like a secret (FR #6443 / #6754)."""
    blob = json.dumps(doc)
    lowered = blob.lower()
    for bad in ("bearer ", "ghs_", "password=", "gh_token"):
        if bad in lowered:
            return {"ok": False, "error": "forbidden: secret-shaped payload"}
    return None


def _queue_row_public(row: Any) -> dict[str, Any]:
    """Whitelist queue JSON fields: repo, task, id, worker (FR #6754)."""
    if not isinstance(row, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("repo", "task", "id"):
        val = row.get(key)
        if val is None or str(val).strip() == "":
            continue
        out[key] = val
    worker = row.get("worker")
    if worker is None or str(worker).strip() == "":
        worker = row.get("nick")
    if worker is not None and str(worker).strip() != "":
        out["worker"] = str(worker)
    return out


def api_get_queue(
    home: Path,
    *,
    client_ip: str,
    digest_home: Path | None = None,
) -> dict[str, Any]:
    """Read-only queue JSON: unaccepted/accepted rows, whitelist only. No secrets."""
    err = reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    dig = Path(digest_home) if digest_home is not None else Path(home)
    unaccepted: list[Any] = []
    accepted: list[Any] = []
    try:
        import gitclaim

        # Read the file, not load_unaccepted: coerce drops ``worker``.
        path = gitclaim.queue_path(dig)
        raw: dict[str, Any] = {}
        if path.is_file():
            parsed = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(parsed, dict):
                raw = parsed
        unaccepted = list(raw.get("unaccepted") or [])
        accepted = list(raw.get("accepted") or [])
    except Exception:
        pass
    out = {
        "ok": True,
        "unaccepted": [_queue_row_public(r) for r in unaccepted],
        "accepted": [_queue_row_public(r) for r in accepted],
    }
    refuse = _appliance_secret_shape_error(out)
    if refuse:
        return refuse
    return out


def api_get_status(
    home: Path,
    *,
    client_ip: str,
    digest_home: Path | None = None,
    started: float | None = None,
    now: float | None = None,
    version: str | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    """Read-only appliance status: version/SHA, uptime, queue, seats, fuel. No secrets."""
    err = reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    dig = Path(digest_home) if digest_home is not None else Path(home)
    now_f = float(now if now is not None else time.time())
    started_f = float(started if started is not None else _PROCESS_STARTED)
    ver = version
    sha = source_commit
    if not ver:
        try:
            import chair_commands as cc

            ver = str(cc.read_version())
        except Exception:
            ver = ""
    if not sha:
        try:
            import jeeves_main as jm

            sha = str(jm.get_source_commit())
        except Exception:
            sha = ""
    unaccepted = accepted = 0
    try:
        import gitclaim

        unaccepted = len(gitclaim.load_unaccepted(dig) or [])
        accepted = len(gitclaim.load_accepted(dig) or [])
    except Exception:
        pass
    live: list[str] = []
    idle: list[str] = []
    try:
        import gitclaim

        live = sorted(gitclaim.live_seat_nicks(dig) or [])
        idle = sorted(gitclaim.free_seat_nicks(dig, set(live)) or [])
    except Exception:
        pass
    fuel = {"coderabbit": False, "copilot": False, "fleet": False, "active": []}
    try:
        import fuel_chain as fc

        active = list(fc.active_stages())
        fuel = {
            "coderabbit": "coderabbit" in active,
            "copilot": "copilot" in active,
            "fleet": "fleet" in active,
            "active": active,
        }
    except Exception:
        pass
    pending = restart_pending_path(home).is_file()
    out = {
        "ok": True,
        "version": ver,
        "source_commit": sha,
        "uptime_s": int(max(0, now_f - started_f)),
        "queue": {"unaccepted": int(unaccepted), "accepted": int(accepted)},
        "seats": {
            "live": live[:50],
            "idle": idle[:50],
            "live_n": len(live),
            "idle_n": len(idle),
        },
        "fuel": fuel,
        "restart_pending": bool(pending),
        "service": RESTART_SERVICE_NAME,
    }
    refuse = _appliance_secret_shape_error(out)
    if refuse:
        return refuse
    return out

