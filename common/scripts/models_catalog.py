"""BOB-01 / FR #8707: fleet agent Weights rows (GET /bob/v1/models).

Public JSON shape (FR #8819)::

    {"clis":{"Grok":{"models":{...}},"Cursor":{"models":{...}},"Opencode":{"models":{...}}},
     "agents":[{"agent":"Plan","cli":"Grok","model":"","context":"","effort":""}, ...]}

``clis`` nests model → context → efforts from digest-home
``models-valid-combos.json`` (BOB-03/04). A CLI with no catalog entry returns
``models: {}`` (200). Agent row ``cli`` is read-only on PUT (FR #8819).

Rows match ``bob/docs/mocks/systray-agents-workers/weights.html``. Optional
digest-home ``models-catalog.json`` overrides agent selections (PUT is BOB-02).

BOB-03 / FR #8710: fail-closed valid ``(cli, model, context, effort)`` combinations
live in a **separate** digest-home file ``models-valid-combos.json`` so BOB-02 PUT
cannot wipe the allow-list. ``POST /bob/v1/models/validate`` rejects invalid combos
with 4xx and never persists.
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

# Worker-launchable CLI keys (bob-worker --agent). Not the Weights display labels.
VALID_CLI_KEYS = frozenset({"grok", "cursor", "opencode"})

# GET /bob/v1/models public CLI keys (Weights / FR #8819). Map from VALID_CLI_KEYS.
CLI_PUBLIC_KEYS: tuple[str, ...] = ("Grok", "Cursor", "Opencode")
CLI_KEY_TO_PUBLIC: dict[str, str] = {
    "grok": "Grok",
    "cursor": "Cursor",
    "opencode": "Opencode",
}

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


def catalog_to_public_doc(
    rows: Iterable[dict[str, str]],
    *,
    clis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agents: list[dict[str, str]] = []
    for row in rows:
        agents.append({k: str(row.get(k) or "") for k in _ROW_KEYS})
    doc: dict[str, Any] = {"agents": agents}
    if clis is not None:
        doc["clis"] = clis
    return doc


def empty_clis_public_doc() -> dict[str, Any]:
    """FR #8819: every known CLI present with ``models: {}`` (no invented names)."""
    return {name: {"models": {}} for name in CLI_PUBLIC_KEYS}


def valid_combos_to_clis_public(cat: "ValidCombosCatalog") -> dict[str, Any]:
    """FR #8819 nested GET shape from BOB-03/04 allow-list.

    ``clis[DisplayCli].models[model].contexts[context].efforts = [...]``.
    Efforts are duplicated under each context (Cartesian product of the
    stored per-model lists). Missing/unavailable catalog → empty models.
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
    home: Path | str | None = None,
) -> bytes:
    clis_doc: dict[str, Any] | None = None
    if home is not None:
        # Do not auto-seed here: FR #8819 requires missing/malformed catalog → models: {}.
        # BOB-04 seeds on BobCallback start / explicit ensure path.
        clis_doc = valid_combos_to_clis_public(load_valid_combos(home))
    return json.dumps(
        catalog_to_public_doc(rows, clis=clis_doc),
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def handle_models_get(home: Path | str) -> tuple[int, bytes]:
    """BobCallback GET /bob/v1/models → agents + nested clis (never 404).

    FR #8819: ``clis`` always present (empty ``models`` when the allow-list
    file is missing/malformed). Agent selections stay in ``agents``.
    """
    rows = load_catalog_file(home)
    return 200, catalog_to_json(rows, home=home)


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
    if missing:
        return None, "missing agents: " + ",".join(missing)
    # Stable order matching defaults.
    by_name = {r["agent"]: r for r in out}
    ordered = [by_name[a] for a, _ in _DEFAULT_ROWS]
    return ordered, ""


def replace_catalog_file(home: Path | str, rows: list[dict[str, str]]) -> bool:
    """Atomically replace models-catalog.json. Return True when content changed.

    Persists agent selection rows only (no ``clis`` node). The allow-list lives
    in ``models-valid-combos.json`` so BOB-02 PUT cannot wipe it (BOB-03).
    """
    path = catalog_path(home)
    # Store agents-only; GET re-attaches nested clis from the combos file.
    new_bytes = json.dumps(
        catalog_to_public_doc(rows, clis=None),
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    old_bytes = b""
    if path.is_file():
        try:
            old_bytes = path.read_bytes()
        except OSError:
            old_bytes = b""
    if old_bytes == new_bytes:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix="models-catalog.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(new_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
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
            row, why = validate_combo_row(item)
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
            row, why = validate_combo_row(item)
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
