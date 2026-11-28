"""BOB-01 / FR #8707 / FR #9746: fleet agent Weights rows (GET /bob/v1/models).

Public GET JSON shape (FR #8819 nested + FR #8820 stale)::

    {"clis":{"Grok":{"models":{...}},"Cursor":{"models":{...}},"Opencode":{"models":{...}},"Copilot":{"models":{...}}},
     "agents":[{"agent":"Plan","cli":"Grok","model":"","context":"","effort":"","stale":true?}, ...]}

``clis`` nests model -> context -> efforts from digest-home
``models-valid-combos.json`` (BOB-03/04 / FR #8819). Agent rows with a non-empty
model absent from the refresh catalog in ``models-catalog.json`` ``clis``
(lowercase keys, FR #8820) get response-only ``stale: true``.

POST /bob/v1/models/refresh (FR #8820) rebuilds the lowercase ``clis`` node
inside ``models-catalog.json`` (models list + ``refreshed_at``); it does not
rewrite agent selections or ``models-valid-combos.json``.

Rows match ``bob/docs/mocks/systray-agents-workers/weights.html``. Optional
digest-home ``models-catalog.json`` overrides agent selections and holds refresh ``clis`` (PUT is BOB-02; FR #8820).

BOB-03 / FR #8710: fail-closed valid ``(cli, model, context, effort)`` combinations
live in a **separate** digest-home file ``models-valid-combos.json`` so BOB-02 PUT
cannot wipe the allow-list. FR #9053 retired ``POST /bob/v1/models/validate`` on the
callback (JSON 404 ``no_models_validate``; no check or persist). The Weights form
limits dropdowns to the GET ``clis`` catalogue from that file; ``PUT /bob/v1/models``
persists agent rows and does not apply the combo allow-list.
"""
from __future__ import annotations

import json
import contextlib
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

MODELS_CATALOG_NAME = "models-catalog.json"
MODELS_PATH = "/bob/v1/models"
MODELS_VALID_COMBOS_NAME = "models-valid-combos.json"
MODELS_VALIDATE_PATH = "/bob/v1/models/validate"
MODELS_REFRESH_PATH = "/bob/v1/models/refresh"

# Catalog CLI keys (Weights / valid-combos). Grok/Cursor/Opencode are worker-launchable;
# Copilot is catalog-only for GitHub agent-task model pick (FR #9746; not REFRESH_CLIS).
VALID_CLI_KEYS = frozenset({"grok", "cursor", "opencode", "copilot"})

# GET /bob/v1/models public CLI keys (Weights / FR #8819). Map from VALID_CLI_KEYS.
CLI_PUBLIC_KEYS: tuple[str, ...] = ("Grok", "Cursor", "Opencode", "Copilot")
CLI_KEY_TO_PUBLIC: dict[str, str] = {
    "grok": "Grok",
    "cursor": "Cursor",
    "opencode": "Opencode",
    "copilot": "Copilot",
}

ERROR_UNKNOWN_CLI = "unknown_cli"
ERROR_UNKNOWN_MODEL = "unknown_model"
ERROR_INVALID_CONTEXT = "invalid_context"
ERROR_INVALID_EFFORT = "invalid_effort"
ERROR_EFFORT_NOT_SUPPORTED = "effort_not_supported"
ERROR_CATALOG_UNAVAILABLE = "catalog_unavailable"
ERROR_MALFORMED = "malformed"
ERROR_BUSY = "busy"


class CatalogUnavailable(Exception):
    """HTTP 503 when models-catalog.json is unreadable/malformed for writers."""


# Agent / CLI pairs from Weights mock (BOB-01 placeholders for model/context/effort).
# FR #9995: Copilot-MRB and Copilot-PR (cli Copilot). Empty model stays allowed.
_COPILOT_KIND_AGENTS: tuple[str, ...] = ("Copilot-MRB", "Copilot-PR")
_DEFAULT_ROWS: tuple[tuple[str, str], ...] = (
    ("Plan", "Grok"),
    ("Priority", "Grok"),
    ("Jeeves", "Grok"),
    ("Grok", "Grok"),
    ("Cursor", "Cursor"),
    ("Opencode", "Opencode"),
    ("Opencode-Free", "Opencode"),
    ("Copilot-MRB", "Copilot"),
    ("Copilot-PR", "Copilot"),
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


def empty_catalog_document() -> dict[str, Any]:
    """Missing-file baseline for writers (FR #8820). Agents filled by readers."""
    return {"version": 1, "clis": {}}


def load_catalog_document(home: Path | str, *, for_write: bool = False) -> dict[str, Any]:
    """Load full models-catalog.json without dropping ``clis`` / extra keys.

    Missing file → empty document (writers) or agents defaults via callers.
    Unreadable / malformed → CatalogUnavailable when for_write, else empty doc
    for read paths that fall back to defaults.
    Legacy bare-array file → ``{"agents": [...]}``.
    """
    path = catalog_path(home)
    if not path.is_file():
        return empty_catalog_document()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        if for_write:
            raise CatalogUnavailable("models-catalog unreadable") from exc
        return empty_catalog_document()
    if isinstance(raw, list):
        return {"agents": raw}
    if not isinstance(raw, dict):
        if for_write:
            raise CatalogUnavailable("models-catalog malformed")
        return empty_catalog_document()
    return raw


def _normalize_cli_models_entry(raw: Any) -> dict[str, Any] | None:
    """Minimal validate one CLI catalog entry for GET/refresh."""
    if not isinstance(raw, dict):
        return None
    models_raw = raw.get("models")
    models: list[dict[str, Any]] = []
    if isinstance(models_raw, list):
        seen: set[str] = set()
        for item in models_raw:
            if not isinstance(item, dict):
                continue
            model = str(item.get("model") or "").strip()
            if not model or model in seen:
                continue
            contexts = item.get("contexts")
            efforts = item.get("efforts")
            if not isinstance(contexts, list):
                contexts = []
            if not isinstance(efforts, list):
                efforts = []
            ctx = [str(x).strip() for x in contexts if str(x).strip()]
            eft = [str(x).strip() for x in efforts if str(x).strip()]
            seen.add(model)
            models.append({"model": model, "contexts": ctx, "efforts": eft})
    refreshed_at = raw.get("refreshed_at")
    if refreshed_at is not None:
        refreshed_at = str(refreshed_at).strip() or None
    return {"models": models, "refreshed_at": refreshed_at}


def clis_public_from_document(doc: dict[str, Any] | None) -> dict[str, Any]:
    """Public ``clis`` map (lowercase keys). Unknown/bad rows skipped."""
    out: dict[str, Any] = {
        k: {"models": [], "refreshed_at": None} for k in sorted(VALID_CLI_KEYS)
    }
    if not isinstance(doc, dict):
        return out
    raw = doc.get("clis")
    if not isinstance(raw, dict):
        return out
    for key, entry_raw in raw.items():
        cli = str(key or "").strip().lower()
        if cli not in VALID_CLI_KEYS:
            continue
        entry = _normalize_cli_models_entry(entry_raw)
        if entry is not None:
            out[cli] = entry
    return out


def model_ids_for_cli(clis: dict[str, Any], cli: str) -> set[str]:
    key = str(cli or "").strip().lower()
    entry = clis.get(key) if isinstance(clis, dict) else None
    if not isinstance(entry, dict):
        return set()
    models = entry.get("models")
    if not isinstance(models, list):
        return set()
    return {
        str(m.get("model") or "").strip()
        for m in models
        if isinstance(m, dict) and str(m.get("model") or "").strip()
    }


def agents_public_with_stale(
    rows: Iterable[dict[str, str]],
    clis: dict[str, Any],
) -> list[dict[str, Any]]:
    """Emit agent rows; add ``stale: true`` only when model missing from clis."""
    agents: list[dict[str, Any]] = []
    for row in rows:
        public: dict[str, Any] = {k: str(row.get(k) or "") for k in _ROW_KEYS}
        model = public["model"].strip()
        if model:
            ids = model_ids_for_cli(clis, public["cli"])
            if ids and model not in ids:
                public["stale"] = True
        agents.append(public)
    return agents


def _blank_copilot_kind(agent: str, model: str = "") -> dict[str, str]:
    return {
        "agent": agent,
        "cli": "Copilot",
        "model": model,
        "context": "",
        "effort": "",
    }


def _expand_legacy_copilot(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """FR #9995: one saved Copilot row becomes Copilot-MRB and Copilot-PR."""
    if not rows:
        return rows
    legacy = next((r for r in rows if r.get("agent") == "Copilot"), None)
    if legacy is None:
        return rows
    model = str(legacy.get("model") or "")
    kept = [r for r in rows if r.get("agent") != "Copilot"]
    names = {r.get("agent") for r in kept}
    for agent in _COPILOT_KIND_AGENTS:
        if agent not in names:
            kept.append(_blank_copilot_kind(agent, model))
    return kept


def _maybe_backfill_copilot_row(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Append blank Copilot-MRB/PR when saved rows are the full pre-Copilot set.

    A lone Copilot row expands to both kind rows (same model). Partial subsets
    stay as written. Does not write disk.
    """
    if not rows:
        return rows
    rows = _expand_legacy_copilot(rows)
    names = {r["agent"] for r in rows}
    if any(a in names for a in _COPILOT_KIND_AGENTS):
        return rows
    legacy = {agent for agent, _cli in _DEFAULT_ROWS if agent not in _COPILOT_KIND_AGENTS}
    if not legacy.issubset(names):
        return rows
    by_name = {r["agent"]: r for r in rows}
    for agent in _COPILOT_KIND_AGENTS:
        by_name[agent] = _blank_copilot_kind(agent)
    return [by_name[a] for a, _ in _DEFAULT_ROWS if a in by_name]


def load_catalog_file(home: Path | str) -> list[dict[str, str]]:
    """Load agent rows from home file, or built-in defaults when missing/empty."""
    doc = load_catalog_document(home, for_write=False)
    rows = _rows_from_payload(doc)
    if rows:
        return _maybe_backfill_copilot_row(rows)
    return default_agent_rows()


def catalog_to_public_doc(
    rows: Iterable[dict[str, str]],
    *,
    clis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clis_doc = (
        clis
        if clis is not None
        else {k: {"models": [], "refreshed_at": None} for k in sorted(VALID_CLI_KEYS)}
    )
    return {
        "clis": clis_doc,
        "agents": agents_public_with_stale(rows, clis_doc),
    }


def empty_clis_public_doc() -> dict[str, Any]:
    """FR #8819: every known CLI present with ``models: {}`` (no invented names)."""
    return {name: {"models": {}} for name in CLI_PUBLIC_KEYS}


def valid_combos_to_clis_public(cat: "ValidCombosCatalog") -> dict[str, Any]:
    """FR #8819 nested GET shape from BOB-03/04 allow-list.

    ``clis[DisplayCli].models[model].contexts[context].efforts = [...]``.
    Efforts are duplicated under each context (Cartesian product of the
    stored per-model lists). Missing/unavailable catalog -> empty models.
    """
    out = empty_clis_public_doc()
    if not cat or not cat.available:
        return out
    for cli_key, rows in (cat.clis or {}).items():
        pub = CLI_KEY_TO_PUBLIC.get(str(cli_key or "").strip().lower())
        if not pub:
            continue
        models: dict[str, Any] = {}
        for row in rows or ():
            model = str(row.model or "").strip()
            if not model:
                continue
            efforts = [str(e) for e in (row.efforts or ())]
            contexts: dict[str, Any] = {}
            for ctx in row.contexts or ():
                ctx_s = str(ctx or "").strip()
                if not ctx_s:
                    continue
                contexts[ctx_s] = {"efforts": list(efforts)}
            models[model] = {"contexts": contexts}
        out[pub] = {"models": models}
    return out


def valid_combos_public_doc(cat: "ValidCombosCatalog") -> dict[str, list[dict[str, Any]]]:
    """FR #8716 / BOB-14: flat allow-list rows (cli -> [{model,contexts,efforts}, ...]).

    GET /bob/v1/models uses `valid_combos_to_clis_public` (FR #8819 nested Si shape).
    Keep this serializer for Weights clients / tests that still consume the flat list.
    """
    if not cat or not cat.available:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for cli, rows in (cat.clis or {}).items():
        key = str(cli or "").strip().lower()
        if not key:
            continue
        packed: list[dict[str, Any]] = []
        for row in rows or ():
            packed.append(
                {
                    "model": str(row.model or ""),
                    "contexts": list(row.contexts or ()),
                    "efforts": list(row.efforts or ()),
                }
            )
        if packed:
            out[key] = packed
    return out


def catalog_to_json(
    rows: Iterable[dict[str, str]],
    *,
    clis: dict[str, Any] | None = None,
    home: Path | str | None = None,
) -> bytes:
    """Serialize agents (+ optional clis).

    When ``home`` is set and ``clis`` is omitted, emit FR #8819 nested ``clis``
    from valid-combos plus FR #8820 stale markers from the refresh catalog.
    """
    if home is not None and clis is None:
        doc = load_catalog_document(home, for_write=False)
        clis_nested = valid_combos_to_clis_public(load_valid_combos(home))
        agents = agents_public_with_stale(rows, clis_public_from_document(doc))
        return json.dumps(
            {"clis": clis_nested, "agents": agents},
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    return json.dumps(
        catalog_to_public_doc(rows, clis=clis),
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def handle_models_get(home: Path | str) -> tuple[int, bytes]:
    """BobCallback GET /bob/v1/models -> nested clis (FR #8819) + stale agents (FR #8820)."""
    rows = load_catalog_file(home)
    return 200, catalog_to_json(rows, home=home)


def save_catalog_document(home: Path | str, doc: dict[str, Any]) -> None:
    """Atomic replace of models-catalog.json. Callers must hold models_catalog_lock."""
    path = catalog_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(
        prefix="models-catalog.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        last_exc: Exception | None = None
        for _attempt in range(8):
            try:
                os.replace(tmp_name, path)
                last_exc = None
                break
            except OSError as exc:
                last_exc = exc
                time.sleep(0.05)
        if last_exc is not None:
            raise last_exc
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def mutate_catalog_document(
    home: Path | str,
    mutator: Any,
) -> dict[str, Any]:
    """Lock, reload, apply mutator(doc), save. Returns the saved document.

    Every writer (refresh, future PUT/PATCH, seed) must use this path so
    ``clis`` / ``agents`` / unknown keys are not dropped.
    """
    with models_catalog_lock(home):
        doc = load_catalog_document(home, for_write=True)
        if not isinstance(doc, dict):
            raise CatalogUnavailable("models-catalog malformed")
        mutator(doc)
        save_catalog_document(home, doc)
        return doc


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


def validate_combo_row(
    obj: Any, *, cli: str = ""
) -> tuple[ModelComboRow | None, str]:
    """Return ``(row, \"\")`` or ``(None, reason)`` for one model allow-list row.

    FR #9258: Grok rows require non-empty contexts (256|500) and efforts
    (high|medium|low). Cursor / OpenCode / Aider may have empty contexts and
    efforts (context/effort are Grok-only).
    """
    if not isinstance(obj, dict):
        return None, "not an object"
    model = str(obj.get("model") or "").strip()
    if not model:
        return None, "missing model"
    contexts = _as_str_list(obj.get("contexts"))
    if contexts is None:
        return None, "contexts must be a list"
    cli_l = str(cli or "").strip().lower()
    grok_only = cli_l in ("", "grok")  # default strict when cli unknown
    if grok_only and not contexts:
        return None, "contexts empty"
    efforts_raw = obj.get("efforts")
    if efforts_raw is None:
        efforts: list[str] = []
    else:
        efforts_parsed = _as_str_list(efforts_raw)
        if efforts_parsed is None:
            return None, "efforts must be a list"
        efforts = efforts_parsed
    if grok_only:
        # Normalise Si's 256|500 / high|medium|low; drop unknown tokens.
        contexts = [c for c in contexts if c in ("256", "500")]
        if not contexts:
            return None, "contexts empty"
        efforts = [e for e in efforts if e.lower() in ("high", "medium", "low")]
        efforts = [e.lower() for e in efforts]
    else:
        # Non-Grok: ignore leftover context/effort lists (treat as empty).
        contexts = []
        efforts = []
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
            row, _why = validate_combo_row(item, cli=cli)
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

    rows = cat.clis.get(cli_key) or []
    match: ModelComboRow | None = None
    for row in rows:
        if row.model == model_s:
            match = row
            break
    if match is None:
        return False, ERROR_UNKNOWN_MODEL, "model"

    # FR #9258: empty contexts (Cursor/OpenCode) → context not applicable;
    # only Grok rows carry 256|500. Absent/empty context is required then.
    if not match.contexts:
        if context is not None and str(context).strip() != "":
            return False, ERROR_INVALID_CONTEXT, "context"
    else:
        if isinstance(context, bool) or not isinstance(context, (str, int, float)):
            return False, ERROR_INVALID_CONTEXT, "context"
        context_s = str(context).strip()
        if not context_s:
            return False, ERROR_INVALID_CONTEXT, "context"
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
    """Retained non-persisting combo check (200/400/503 when called directly).

    FR #9053: bobcallback does not dispatch this helper for
    ``POST /bob/v1/models/validate``; the callback returns JSON 404
    ``no_models_validate`` for that retired route.
    """
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
# --- BOB-02 / FR #8708: PUT replace Weights ---


MODELS_LOCK_NAME = "models-catalog.lock"
MODELS_PUT_MAX_BYTES = 64 * 1024
_KNOWN_AGENTS = frozenset(a for a, _cli in _DEFAULT_ROWS)
_AGENT_CLI = {agent: cli for agent, cli in _DEFAULT_ROWS}
_MODELS_THREAD_LOCK = threading.Lock()


class ModelsCatalogBusy(Exception):
    """HTTP 503 when the catalog lock cannot be taken."""


def models_lock_path(home: Path | str) -> Path:
    return Path(home) / MODELS_LOCK_NAME


@contextlib.contextmanager
def models_catalog_lock(home: Path | str, timeout_s: float = 5.0):
    """Bounded thread lock for models-catalog.json replace (FR #8708)."""
    deadline = time.monotonic() + float(timeout_s)
    while True:
        if _MODELS_THREAD_LOCK.acquire(blocking=False):
            break
        if time.monotonic() >= deadline:
            raise ModelsCatalogBusy("models-catalog.lock busy")
        time.sleep(0.05)
    try:
        Path(home).mkdir(parents=True, exist_ok=True)
        yield
    finally:
        _MODELS_THREAD_LOCK.release()


def _row_secretish(row: dict[str, str]) -> bool:
    try:
        import bobreport
    except ImportError:
        return False
    blob = " ".join(str(row.get(k) or "") for k in _ROW_KEYS)
    return bool(bobreport.looks_like_secret(blob))


def validate_put_agents(raw: Any) -> tuple[list[dict[str, str]] | None, str]:
    """Full-replace Weights body: {\"agents\":[...]} with known agents only."""
    if not isinstance(raw, dict):
        return None, "payload must be a JSON object"
    items = raw.get("agents")
    if not isinstance(items, list):
        return None, "agents must be a list"
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        row, why = validate_agent_row(item)
        if row is None:
            return None, why or "invalid agent row"
        if row["agent"] == "Copilot":
            # FR #9995: accept a legacy Copilot row and split before known-agent checks.
            row = _blank_copilot_kind("Copilot", str(row.get("model") or ""))
            row["context"] = str(item.get("context") or "") if isinstance(item, dict) else ""
            row["effort"] = str(item.get("effort") or "") if isinstance(item, dict) else ""
            pending = []
            for agent in _COPILOT_KIND_AGENTS:
                twin = dict(row)
                twin["agent"] = agent
                pending.append(twin)
        else:
            pending = [row]
        for row in pending:
            if row["agent"] not in _KNOWN_AGENTS:
                return None, f"unknown agent {row['agent']}"
            expected_cli = _AGENT_CLI.get(row["agent"])
            if expected_cli is not None and row["cli"] != expected_cli:
                # FR #8819: agent row cli is read-only (Weights binds dropdowns from clis[row.cli]).
                return None, f"cli is read-only for {row['agent']}"
            if row["agent"] in seen:
                return None, f"duplicate agent {row['agent']}"
            if _row_secretish(row):
                return None, "malformed JSON"
            seen.add(row["agent"])
            out.append(row)
    missing = [a for a, _ in _DEFAULT_ROWS if a not in seen]
    # Legacy PUT may omit only the Copilot kind rows (merged on replace).
    if missing and missing != list(_COPILOT_KIND_AGENTS):
        return None, "missing agents: " + ",".join(missing)
    # Stable order matching defaults (Copilot may be absent until replace merge).
    by_name = {r["agent"]: r for r in out}
    ordered = [by_name[a] for a, _ in _DEFAULT_ROWS if a in by_name]
    return ordered, ""


def _merge_omitted_copilot_row(
    home: Path | str,
    rows: list[dict[str, str]],
    doc: dict[str, Any],
) -> list[dict[str, str]]:
    """FR #9746: when PUT omits Copilot, keep stored row or blank default."""
    rows = _expand_legacy_copilot(rows)
    names = {r["agent"] for r in rows}
    if any(a in names for a in _COPILOT_KIND_AGENTS):
        by_name = {r["agent"]: r for r in rows}
        return [by_name[a] for a, _ in _DEFAULT_ROWS if a in by_name]
    stored = _expand_legacy_copilot(_rows_from_payload(doc))
    by_name = {r["agent"]: r for r in rows}
    for agent in _COPILOT_KIND_AGENTS:
        found = next((r for r in stored if r.get("agent") == agent), None)
        by_name[agent] = found if found is not None else _blank_copilot_kind(agent)
    return [by_name[a] for a, _ in _DEFAULT_ROWS if a in by_name]


def replace_catalog_file(home: Path | str, rows: list[dict[str, str]]) -> bool:
    """Atomically replace agent rows; preserve ``clis`` and unknown keys (FR #8820)."""
    path = catalog_path(home)
    try:
        doc = load_catalog_document(home, for_write=True)
    except CatalogUnavailable:
        doc = empty_catalog_document()
    if not isinstance(doc, dict):
        doc = empty_catalog_document()
    rows = _merge_omitted_copilot_row(home, rows, doc)
    old_bytes = b""
    if path.is_file():
        try:
            old_bytes = path.read_bytes()
        except OSError:
            old_bytes = b""
    doc["agents"] = rows
    if "version" not in doc:
        doc["version"] = 1
    new_bytes = json.dumps(doc, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if old_bytes == new_bytes:
        return False
    save_catalog_document(home, doc)
    return True


def handle_models_put(body: bytes | str, home: Path | str) -> tuple[int, bytes]:
    """BobCallback PUT /bob/v1/models → persist Weights; 204 changed, 200 unchanged."""
    raw = body if isinstance(body, (bytes, bytearray)) else (body or "").encode("utf-8")
    if len(raw) > MODELS_PUT_MAX_BYTES:
        return 413, b'{"error":"body too large"}'
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return 400, b'{"error":"malformed JSON"}'
    try:
        import bobreport

        if bobreport.looks_like_secret(text):
            return 400, b'{"error":"malformed JSON"}'
    except ImportError:
        pass
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError:
        return 400, b'{"error":"malformed JSON"}'
    rows, why = validate_put_agents(payload)
    if rows is None:
        err = json.dumps({"error": why or "invalid"}, separators=(",", ":")).encode("utf-8")
        return 400, err
    try:
        with models_catalog_lock(home):
            changed = replace_catalog_file(home, rows)
    except ModelsCatalogBusy:
        return 503, b'{"error":"busy"}'
    except OSError:
        return 500, b'{"error":"write failed"}'
    if changed:
        return 204, b""
    return 200, catalog_to_json(rows, home=home)


# --- BOB-04 / FR #8709: seed models-valid-combos.json from shipped seed ------------

MODELS_VALID_COMBOS_SEED_NAME = "models-valid-combos.seed.json"


def resolve_valid_combos_seed_path(
    *,
    env: dict | None = None,
    file_path: str | Path | None = None,
    meipass: str | Path | None = None,
    install_root: str | Path | None = None,
) -> Path | None:
    """Locate shipped ``models-valid-combos.seed.json``.

    Order: ``BOB_MODELS_VALID_COMBOS_SEED`` → ``<install>/defaults/`` →
    source ``common/defaults/`` beside this module → PyInstaller ``_MEIPASS/defaults/``.
    """
    import sys

    e = os.environ if env is None else env
    explicit = (e.get("BOB_MODELS_VALID_COMBOS_SEED") or "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None

    candidates: list[Path] = []
    if install_root is not None and str(install_root).strip():
        root = Path(str(install_root).strip())
        candidates.append(root / "defaults" / MODELS_VALID_COMBOS_SEED_NAME)
        candidates.append(root / "jeeves" / "defaults" / MODELS_VALID_COMBOS_SEED_NAME)
    here = Path(__file__ if file_path is None else file_path).resolve().parent
    # common/scripts -> common/defaults
    candidates.append(here.parent / "defaults" / MODELS_VALID_COMBOS_SEED_NAME)
    # install root guess from source layout (repo root)
    candidates.append(here.parent.parent / "common" / "defaults" / MODELS_VALID_COMBOS_SEED_NAME)

    mp = meipass
    if mp is None:
        mp = getattr(sys, "_MEIPASS", None)
    if mp:
        candidates.append(Path(mp) / "defaults" / MODELS_VALID_COMBOS_SEED_NAME)

    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def load_seed_document(path: Path | str) -> dict[str, Any]:
    """Load and strictly validate a seed file. Raises ValueError on bad rows."""
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("seed root must be an object")
    clis_raw = raw.get("clis")
    if not isinstance(clis_raw, dict) or not clis_raw:
        raise ValueError("seed clis missing or empty")
    cleaned: dict[str, list[dict[str, Any]]] = {}
    for cli_key, rows_raw in clis_raw.items():
        cli = str(cli_key or "").strip().lower()
        if cli not in VALID_CLI_KEYS:
            raise ValueError(f"seed unknown cli: {cli_key!r}")
        if not isinstance(rows_raw, list) or not rows_raw:
            raise ValueError(f"seed cli {cli} rows missing")
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in rows_raw:
            row, why = validate_combo_row(item, cli=cli)
            if row is None:
                raise ValueError(f"seed cli {cli} invalid row: {why}")
            if row.model in seen:
                continue
            seen.add(row.model)
            rows.append(
                {
                    "model": row.model,
                    "contexts": list(row.contexts),
                    "efforts": list(row.efforts),
                }
            )
        if not rows:
            raise ValueError(f"seed cli {cli} produced no rows")
        cleaned[cli] = rows
    if set(cleaned) != VALID_CLI_KEYS:
        missing = sorted(VALID_CLI_KEYS - set(cleaned))
        raise ValueError(f"seed missing clis: {missing}")
    version_raw = raw.get("version", 1)
    try:
        version = int(version_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("seed version must be int") from exc
    out: dict[str, Any] = {"version": version, "clis": cleaned}
    prov = raw.get("provenance")
    if isinstance(prov, dict):
        out["provenance"] = prov
    return out


def _combo_rows_to_payload(clis: dict[str, list[ModelComboRow]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for cli, rows in clis.items():
        out[cli] = [
            {"model": r.model, "contexts": list(r.contexts), "efforts": list(r.efforts)}
            for r in rows
        ]
    return out


def ensure_valid_combos_seeded(
    home: Path | str,
    *,
    seed_path: Path | str | None = None,
    env: dict | None = None,
) -> dict[str, Any]:
    """Create or merge digest-home ``models-valid-combos.json`` from the shipped seed.

    - Missing store: write the full validated seed.
    - Existing valid store: append missing seeded ``(cli, model)`` rows; never remove
      or rewrite operator rows.
    - Existing malformed/unreadable store: leave unchanged and return an error status.

    Returns a small status dict for logs/tests (never raises on I/O merge paths).
    """
    home_p = Path(home)
    dest = valid_combos_path(home_p)
    status: dict[str, Any] = {
        "ok": False,
        "path": str(dest),
        "action": "none",
        "added": 0,
        "error": "",
    }
    try:
        seed_file = Path(seed_path) if seed_path is not None else resolve_valid_combos_seed_path(env=env)
        if seed_file is None or not seed_file.is_file():
            status["error"] = "seed_missing"
            print("ERROR models-valid-combos seed file missing", flush=True)
            return status
        seed_doc = load_seed_document(seed_file)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        status["error"] = f"seed_invalid:{exc}"
        print(f"ERROR models-valid-combos seed invalid err={exc}", flush=True)
        return status

    seed_clis: dict[str, list[ModelComboRow]] = {}
    for cli, rows in seed_doc["clis"].items():
        parsed: list[ModelComboRow] = []
        for item in rows:
            row, why = validate_combo_row(item, cli=cli)
            if row is None:
                status["error"] = f"seed_invalid:{cli}:{why}"
                print(f"ERROR models-valid-combos seed row err={status['error']}", flush=True)
                return status
            parsed.append(row)
        seed_clis[cli] = parsed

    if not dest.is_file():
        try:
            home_p.mkdir(parents=True, exist_ok=True)
            write_doc = {
                "version": int(seed_doc.get("version") or 1),
                "clis": _combo_rows_to_payload(seed_clis),
            }
            if isinstance(seed_doc.get("provenance"), dict):
                write_doc["provenance"] = seed_doc["provenance"]
            dest.write_text(
                json.dumps(write_doc, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        except OSError as exc:
            status["error"] = f"write_failed:{exc}"
            print(f"ERROR models-valid-combos seed write err={exc}", flush=True)
            return status
        status["ok"] = True
        status["action"] = "created"
        status["added"] = sum(len(v) for v in seed_clis.values())
        print(
            f"INFO models-valid-combos seeded created path={dest} added={status['added']}",
            flush=True,
        )
        return status

    # Existing file: merge missing models only when current catalogue loads cleanly.
    try:
        raw_text = dest.read_text(encoding="utf-8-sig")
        raw = json.loads(raw_text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        status["error"] = f"store_malformed:{exc}"
        print(
            f"ERROR models-valid-combos store malformed; leaving unchanged path={dest} err={exc}",
            flush=True,
        )
        return status

    if not isinstance(raw, dict):
        status["error"] = "store_malformed:root"
        print(
            f"ERROR models-valid-combos store malformed; leaving unchanged path={dest}",
            flush=True,
        )
        return status

    existing = load_valid_combos(home_p)
    if not existing.available:
        status["error"] = "store_unavailable"
        print(
            f"ERROR models-valid-combos store unavailable/empty; leaving unchanged path={dest}",
            flush=True,
        )
        return status

    merged_clis: dict[str, list[ModelComboRow]] = {
        cli: list(rows) for cli, rows in existing.clis.items()
    }
    added = 0
    for cli, seed_rows in seed_clis.items():
        have = {r.model for r in merged_clis.get(cli, [])}
        bucket = list(merged_clis.get(cli, []))
        for row in seed_rows:
            if row.model in have:
                continue
            bucket.append(row)
            have.add(row.model)
            added += 1
        if bucket:
            merged_clis[cli] = bucket

    if added == 0:
        status["ok"] = True
        status["action"] = "unchanged"
        return status

    try:
        version_raw = raw.get("version", existing.version or 1)
        try:
            version = int(version_raw)
        except (TypeError, ValueError):
            version = int(existing.version or 1)
        write_doc: dict[str, Any] = {
            "version": version,
            "clis": _combo_rows_to_payload(merged_clis),
        }
        if isinstance(raw.get("provenance"), dict):
            write_doc["provenance"] = raw["provenance"]
        elif isinstance(seed_doc.get("provenance"), dict):
            write_doc["provenance"] = seed_doc["provenance"]
        dest.write_text(
            json.dumps(write_doc, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        status["error"] = f"write_failed:{exc}"
        print(f"ERROR models-valid-combos merge write err={exc}", flush=True)
        return status

    status["ok"] = True
    status["action"] = "merged"
    status["added"] = added
    print(
        f"INFO models-valid-combos seeded merged path={dest} added={added}",
        flush=True,
    )
    return status
