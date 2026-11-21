"""BOB-01 / FR #8707: fleet agent Weights rows (GET /bob/v1/models).

Public JSON shape::

    {"agents":[{"agent":"Plan","cli":"Grok","model":"","context":"","effort":""}, ...]}

Rows match ``bob/docs/mocks/systray-agents-workers/weights.html``. Optional
digest-home ``models-catalog.json`` overrides defaults (PUT/PATCH is BOB-02).

BOB-03 / FR #8710: fail-closed valid ``(cli, model, context, effort)`` combinations
live in a **separate** digest-home file ``models-valid-combos.json`` so BOB-02 PUT
cannot wipe the allow-list. ``POST /bob/v1/models/validate`` rejects invalid combos
with 4xx and never persists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

MODELS_CATALOG_NAME = "models-catalog.json"
MODELS_PATH = "/bob/v1/models"
MODELS_VALID_COMBOS_NAME = "models-valid-combos.json"
MODELS_VALIDATE_PATH = "/bob/v1/models/validate"

# Worker-launchable CLI keys (bob-worker --agent). Not the Weights display labels.
VALID_CLI_KEYS = frozenset({"grok", "cursor", "opencode"})

ERROR_UNKNOWN_CLI = "unknown_cli"
ERROR_UNKNOWN_MODEL = "unknown_model"
ERROR_INVALID_CONTEXT = "invalid_context"
ERROR_INVALID_EFFORT = "invalid_effort"
ERROR_EFFORT_NOT_SUPPORTED = "effort_not_supported"
ERROR_CATALOG_UNAVAILABLE = "catalog_unavailable"
ERROR_MALFORMED = "malformed"

# Agent / CLI pairs from Weights mock (BOB-01 placeholders for model/context/effort).
_DEFAULT_ROWS: tuple[tuple[str, str], ...] = (
    ("Plan", "Grok"),
    ("Priority", "Grok"),
    ("Jeeves", "Grok"),
    ("Grok", "Grok"),
    ("Cursor", "Cursor"),
    ("Opencode", "Opencode"),
    ("Opencode-Free", "Opencode"),
)

_ROW_KEYS = ("agent", "cli", "model", "context", "effort")


def default_agent_rows() -> list[dict[str, str]]:
    return [
        {
            "agent": agent,
            "cli": cli,
            "model": "",
            "context": "",
            "effort": "",
        }
        for agent, cli in _DEFAULT_ROWS
    ]


def catalog_path(home: Path | str) -> Path:
    return Path(home) / MODELS_CATALOG_NAME


def validate_agent_row(obj: Any) -> tuple[dict[str, str] | None, str]:
    """Return ``(row, \"\")`` or ``(None, reason)``."""
    if not isinstance(obj, dict):
        return None, "not an object"
    agent = str(obj.get("agent") or "").strip()
    if not agent:
        return None, "missing agent"
    cli = str(obj.get("cli") or "").strip()
    if not cli:
        return None, "missing cli"
    return (
        {
            "agent": agent,
            "cli": cli,
            "model": str(obj.get("model") or "").strip(),
            "context": str(obj.get("context") or "").strip(),
            "effort": str(obj.get("effort") or "").strip(),
        },
        "",
    )


def _rows_from_payload(raw: Any) -> list[dict[str, str]]:
    if isinstance(raw, dict):
        items = raw.get("agents")
    elif isinstance(raw, list):
        items = raw
    else:
        return []
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for item in items:
        row, _why = validate_agent_row(item)
        if row is not None:
            out.append(row)
    return out


def load_catalog_file(home: Path | str) -> list[dict[str, str]]:
    """Load agent rows from home file, or built-in defaults when missing/empty."""
    path = catalog_path(home)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raw = None
        if raw is not None:
            rows = _rows_from_payload(raw)
            if rows:
                return rows
    return default_agent_rows()


def catalog_to_public_doc(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    agents: list[dict[str, str]] = []
    for row in rows:
        agents.append({k: str(row.get(k) or "") for k in _ROW_KEYS})
    return {"agents": agents}


def catalog_to_json(rows: Iterable[dict[str, str]]) -> bytes:
    return json.dumps(
        catalog_to_public_doc(rows),
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def handle_models_get(home: Path | str) -> tuple[int, bytes]:
    """BobCallback GET /bob/v1/models → fleet agent rows JSON (never 404)."""
    rows = load_catalog_file(home)
    return 200, catalog_to_json(rows)


# --- BOB-03 / FR #8710: fail-closed valid combinations -------------------------


@dataclass
class ModelComboRow:
    model: str
    contexts: list[str] = field(default_factory=list)
    efforts: list[str] = field(default_factory=list)


@dataclass
class ValidCombosCatalog:
    """Loaded allow-list. ``available`` is False when missing/malformed/empty."""

    available: bool
    version: int = 0
    clis: dict[str, list[ModelComboRow]] = field(default_factory=dict)


def valid_combos_path(home: Path | str) -> Path:
    return Path(home) / MODELS_VALID_COMBOS_NAME


def _as_str_list(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    out: list[str] = []
    for item in raw:
        if not isinstance(item, (str, int, float)):
            return None
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def validate_combo_row(obj: Any) -> tuple[ModelComboRow | None, str]:
    """Return ``(row, \"\")`` or ``(None, reason)`` for one model allow-list row."""
    if not isinstance(obj, dict):
        return None, "not an object"
    model = str(obj.get("model") or "").strip()
    if not model:
        return None, "missing model"
    contexts = _as_str_list(obj.get("contexts"))
    if contexts is None:
        return None, "contexts must be a list"
    if not contexts:
        return None, "contexts empty"
    efforts_raw = obj.get("efforts")
    if efforts_raw is None:
        efforts: list[str] = []
    else:
        efforts_parsed = _as_str_list(efforts_raw)
        if efforts_parsed is None:
            return None, "efforts must be a list"
        efforts = efforts_parsed
    return ModelComboRow(model=model, contexts=contexts, efforts=efforts), ""


def _clis_from_payload(raw: Any) -> dict[str, list[ModelComboRow]]:
    if not isinstance(raw, dict):
        return {}
    clis_raw = raw.get("clis")
    if not isinstance(clis_raw, dict):
        return {}
    out: dict[str, list[ModelComboRow]] = {}
    for cli_key, rows_raw in clis_raw.items():
        cli = str(cli_key or "").strip().lower()
        if cli not in VALID_CLI_KEYS:
            continue
        if not isinstance(rows_raw, list):
            continue
        seen: set[str] = set()
        rows: list[ModelComboRow] = []
        for item in rows_raw:
            row, _why = validate_combo_row(item)
            if row is None:
                continue
            if row.model in seen:
                continue
            seen.add(row.model)
            rows.append(row)
        if rows:
            out[cli] = rows
    return out


def load_valid_combos(home: Path | str) -> ValidCombosCatalog:
    """Fail-closed loader for ``models-valid-combos.json``.

    Missing, unreadable, malformed, or empty catalogues return
    ``available=False`` (never an empty accept-all list).
    """
    path = valid_combos_path(home)
    if not path.is_file():
        return ValidCombosCatalog(available=False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ValidCombosCatalog(available=False)
    if not isinstance(raw, dict):
        return ValidCombosCatalog(available=False)
    version_raw = raw.get("version", 0)
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        version = 0
    clis = _clis_from_payload(raw)
    if not clis:
        return ValidCombosCatalog(available=False, version=version)
    return ValidCombosCatalog(available=True, version=version, clis=clis)


def _normalize_cli(cli: Any) -> str:
    return str(cli or "").strip().lower()


def _effort_absent(effort: Any) -> bool:
    if effort is None:
        return True
    return str(effort).strip() == ""


def validate_combo(
    cli: Any,
    model: Any,
    context: Any,
    effort: Any = None,
    *,
    home: Path | str | None = None,
    catalog: ValidCombosCatalog | None = None,
) -> tuple[bool, str | None, str | None]:
    """Strict ``(cli, model, context, effort)`` check.

    Returns ``(True, None, None)`` on accept, else
    ``(False, error_code, field)``. Does not call ``normalize_effort``.
    """
    cat = catalog
    if cat is None:
        if home is None:
            return False, ERROR_CATALOG_UNAVAILABLE, None
        cat = load_valid_combos(home)
    if not cat.available:
        return False, ERROR_CATALOG_UNAVAILABLE, None

    cli_key = _normalize_cli(cli)
    if not cli_key or cli_key not in VALID_CLI_KEYS or cli_key not in cat.clis:
        return False, ERROR_UNKNOWN_CLI, "cli"

    if isinstance(model, bool) or not isinstance(model, (str, int, float)):
        return False, ERROR_UNKNOWN_MODEL, "model"
    model_s = str(model).strip()
    if not model_s:
        return False, ERROR_UNKNOWN_MODEL, "model"

    if isinstance(context, bool) or not isinstance(context, (str, int, float)):
        return False, ERROR_INVALID_CONTEXT, "context"
    context_s = str(context).strip()
    if not context_s:
        return False, ERROR_INVALID_CONTEXT, "context"

    rows = cat.clis.get(cli_key) or []
    match: ModelComboRow | None = None
    for row in rows:
        if row.model == model_s:
            match = row
            break
    if match is None:
        return False, ERROR_UNKNOWN_MODEL, "model"
    if context_s not in match.contexts:
        return False, ERROR_INVALID_CONTEXT, "context"

    if not match.efforts:
        if not _effort_absent(effort):
            return False, ERROR_EFFORT_NOT_SUPPORTED, "effort"
        return True, None, None

    if _effort_absent(effort):
        return False, ERROR_INVALID_EFFORT, "effort"
    if isinstance(effort, bool) or not isinstance(effort, (str, int, float)):
        return False, ERROR_INVALID_EFFORT, "effort"
    effort_s = str(effort).strip().lower()
    allowed = {e.lower() for e in match.efforts}
    if effort_s not in allowed:
        return False, ERROR_INVALID_EFFORT, "effort"
    return True, None, None


def _json_bytes(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def handle_models_validate(
    body: bytes | str,
    home: Path | str,
    *,
    log: Any = print,
) -> tuple[int, bytes]:
    """BobCallback POST /bob/v1/models/validate — non-persisting combo check."""
    raw_body = body if isinstance(body, (bytes, bytearray)) else str(body or "").encode("utf-8")
    try:
        payload = json.loads(raw_body.decode("utf-8") if raw_body else b"null")
    except (UnicodeError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict):
        if log is not None:
            log("INFO models validate reject error=malformed field=body", flush=True)
        return 400, _json_bytes({"error": ERROR_MALFORMED})

    for key in ("cli", "model", "context"):
        if key not in payload:
            if log is not None:
                log(f"INFO models validate reject error=malformed field={key}", flush=True)
            return 400, _json_bytes({"error": ERROR_MALFORMED})
        val = payload[key]
        if isinstance(val, bool) or not isinstance(val, (str, int, float)):
            if log is not None:
                log(f"INFO models validate reject error=malformed field={key}", flush=True)
            return 400, _json_bytes({"error": ERROR_MALFORMED})

    effort = payload.get("effort")
    if "effort" in payload and effort is not None:
        if isinstance(effort, bool) or not isinstance(effort, (str, int, float)):
            if log is not None:
                log("INFO models validate reject error=malformed field=effort", flush=True)
            return 400, _json_bytes({"error": ERROR_MALFORMED})

    cli = payload.get("cli")
    model = payload.get("model")
    context = payload.get("context")
    ok, err, err_field = validate_combo(cli, model, context, effort, home=home)
    if ok:
        return 200, _json_bytes({"ok": True})
    code = 503 if err == ERROR_CATALOG_UNAVAILABLE else 400
    doc: dict[str, Any] = {"error": err or ERROR_MALFORMED}
    if err_field:
        doc["field"] = err_field
    if log is not None:
        cli_s = _normalize_cli(cli)
        model_s = str(model or "").strip()[:80]
        context_s = str(context or "").strip()[:40]
        effort_s = "" if _effort_absent(effort) else str(effort).strip()[:20]
        log(
            "INFO models validate reject "
            f"error={err} field={err_field or '-'} cli={cli_s!r} "
            f"model={model_s!r} context={context_s!r} effort={effort_s!r}",
            flush=True,
        )
    return code, _json_bytes(doc)
