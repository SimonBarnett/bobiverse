"""FR #9982: GET/POST /bob/v1/gitcust catalog store."""
from __future__ import annotations

import json
import re
from pathlib import Path

GITCUST_PATH = "/bob/v1/gitcust"
STORE_NAME = "gitcust-catalog.json"
_KIND = re.compile(r"^(sc|so|wbs)$", re.I)
_TITLE = re.compile(r"^[\s\S]{1,240}$")


def _empty() -> dict:
    return {"customers": [], "tasks": []}


def store_path(home: Path) -> Path:
    return Path(home) / STORE_NAME


def load_store(home: Path) -> dict:
    path = store_path(home)
    if not path.is_file():
        return _empty()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    if not isinstance(doc, dict):
        return _empty()
    customers = [c for c in (doc.get("customers") or []) if isinstance(c, dict)]
    tasks = [t for t in (doc.get("tasks") or []) if isinstance(t, dict)]
    return {"customers": customers, "tasks": tasks}


def save_store(home: Path, doc: dict) -> None:
    path = store_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def catalog(home: Path) -> tuple[int, bytes]:
    body = json.dumps(load_store(home)).encode("utf-8")
    return 200, body


def _customer_name(raw) -> str:
    name = str(raw or "").strip()
    if not name or len(name) > 120 or any(c in name for c in "\\/\0"):
        return ""
    return name


def register(home: Path, raw) -> tuple[int, bytes]:
    if isinstance(raw, (bytes, str)):
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return 400, json.dumps({"error": "malformed"}).encode("utf-8")
    elif isinstance(raw, dict):
        payload = raw
    else:
        return 400, json.dumps({"error": "malformed"}).encode("utf-8")
    if not isinstance(payload, dict):
        return 400, json.dumps({"error": "malformed"}).encode("utf-8")
    name = _customer_name(payload.get("customer") or payload.get("name"))
    task = payload.get("task") if isinstance(payload.get("task"), dict) else None
    if not name and not task:
        return 400, json.dumps({"error": "customer_or_task"}).encode("utf-8")
    doc = load_store(home)
    if name and not any(str(c.get("name")) == name for c in doc["customers"]):
        doc["customers"].append({"name": name, "path": str(payload.get("path") or name)})
    if task is not None:
        kind = str(task.get("kind") or "").strip().lower()
        title = str(task.get("title") or "").strip()
        path = str(task.get("path") or "").strip()
        if not _KIND.match(kind) or not title or not _TITLE.match(title) or not path:
            return 400, json.dumps({"error": "task_schema"}).encode("utf-8")
        owner = _customer_name(task.get("customer") or name)
        if not owner:
            return 400, json.dumps({"error": "customer_or_task"}).encode("utf-8")
        if not any(str(c.get("name")) == owner for c in doc["customers"]):
            doc["customers"].append({"name": owner, "path": owner})
        row = {"customer": owner, "kind": kind, "title": title, "path": path}
        if not any(t.get("path") == path and t.get("kind") == kind for t in doc["tasks"]):
            doc["tasks"].append(row)
    save_store(home, doc)
    return 202, json.dumps({"ok": True}).encode("utf-8")
