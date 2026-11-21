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
