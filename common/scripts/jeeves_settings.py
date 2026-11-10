"""FR #6436 foundation: Jeeves appliance settings schema + LAN-only API helpers.

Off by default: importing this module never starts a server.
FR #6442: migrate NSSM/env inventory into appliance-settings.json and apply
file-backed values into the process environment (env still overrides).
HTTP UI is FR #6440; AD/CredMan auth is FR #6441.
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


def _spec(
    key: str,
    typ: str,
    default: str,
    *,
    store: str = "file",
    restart: bool = False,
    secret: bool = False,
    description: str = "",
) -> SettingSpec:
    return SettingSpec(
        key=key,
        type=typ,
        default=default,
        store=store,
        restart=restart,
        secret=secret or typ == "secret",
        description=description,
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

