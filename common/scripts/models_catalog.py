"""BOB-01 / FR #8707: fleet agent Weights rows (GET /bob/v1/models).

Public JSON shape::

    {"agents":[{"agent":"Plan","cli":"Grok","model":"","context":"","effort":""}, ...]}

Rows match ``bob/docs/mocks/systray-agents-workers/weights.html``. Optional
digest-home ``models-catalog.json`` overrides defaults (PUT/PATCH is BOB-02).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

MODELS_CATALOG_NAME = "models-catalog.json"
MODELS_PATH = "/bob/v1/models"

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


# --- BOB-02 / FR #8708: PUT replace Weights ---

import contextlib
import os
import tempfile
import threading
import time

MODELS_LOCK_NAME = "models-catalog.lock"
MODELS_PUT_MAX_BYTES = 64 * 1024
_KNOWN_AGENTS = frozenset(a for a, _cli in _DEFAULT_ROWS)
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
    """Atomically replace models-catalog.json. Return True when content changed."""
    path = catalog_path(home)
    new_bytes = catalog_to_json(rows)
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
    return 200, catalog_to_json(rows)

