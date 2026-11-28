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
    return {"customers": []}


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
    return _normalize(doc)


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


def _task_row(raw: dict, owner: str) -> dict | None:
    kind = str(raw.get("kind") or "").strip().lower()
    title = str(raw.get("title") or "").strip()
    path = str(raw.get("path") or "").strip()
    if not _KIND.match(kind) or not title or not _TITLE.match(title) or not path:
        return None
    return {"kind": kind, "title": title, "path": path}


def _ensure_customer(by_name: dict, order: list, name: str, path: str | None) -> dict:
    node = by_name.get(name)
    if node is None:
        node = {"name": name, "path": path or name, "tasks": []}
        by_name[name] = node
        order.append(name)
    elif path:
        node["path"] = path
    return node


def _add_task(node: dict, row: dict) -> None:
    if any(t.get("path") == row["path"] and t.get("kind") == row["kind"] for t in node["tasks"]):
        return
    node["tasks"].append(row)


def _normalize(doc: dict) -> dict:
    """Customers own their tasks. A flat top-level tasks list is folded in on read."""
    if not isinstance(doc, dict):
        return _empty()
    by_name: dict = {}
    order: list = []
    for cust in doc.get("customers") or []:
        if not isinstance(cust, dict):
            continue
        name = _customer_name(cust.get("name"))
        if not name:
            continue
        node = _ensure_customer(by_name, order, name, str(cust.get("path") or name))
        for raw in cust.get("tasks") or []:
            if not isinstance(raw, dict):
                continue
            row = _task_row(raw, name)
            if row:
                _add_task(node, row)
    for raw in doc.get("tasks") or []:
        if not isinstance(raw, dict):
            continue
        owner = _customer_name(raw.get("customer"))
        if not owner:
            continue
        node = _ensure_customer(by_name, order, owner, owner)
        row = _task_row(raw, owner)
        if row:
            _add_task(node, row)
    return {"customers": [by_name[name] for name in order]}


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
        doc["customers"].append({"name": name, "path": str(payload.get("path") or name), "tasks": []})
    if task is not None:
        owner = _customer_name(task.get("customer") or name)
        row = _task_row(task, owner)
        if not owner or row is None:
            return 400, json.dumps({"error": "task_schema" if owner else "customer_or_task"}).encode("utf-8")
        node = next((c for c in doc["customers"] if str(c.get("name")) == owner), None)
        if node is None:
            node = {"name": owner, "path": owner, "tasks": []}
            doc["customers"].append(node)
        node.setdefault("tasks", [])
        _add_task(node, row)
    save_store(home, doc)
    return 202, json.dumps({"ok": True}).encode("utf-8")


_KIND_PREFIX = re.compile(r"^(SC|SO|WBS)[\s._-]*", re.I)


def classify_folder(name: str) -> str:
    upper = (name or "").strip().upper()
    if upper.startswith("SC"):
        return "sc"
    if upper.startswith("SO"):
        return "so"
    if upper.startswith("WBS"):
        return "wbs"
    return ""


def folder_title(folder: Path) -> str:
    meta = folder / "title.txt"
    if meta.is_file():
        text = meta.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if text and text[0].strip():
            return text[0].strip()[:240]
    raw = folder.name.strip()
    title = _KIND_PREFIX.sub("", raw).strip(" ._-\t")
    return title or raw


def scan_tree(root: Path) -> dict:
    """Scan customer roots. Task folders are SC/SO/WBS children. Title is never empty."""
    root = Path(root)
    customers = []
    if not root.is_dir():
        return {"customers": customers}
    for cust in sorted(p for p in root.iterdir() if p.is_dir()):
        node = {"name": cust.name, "path": cust.name, "tasks": []}
        for child in sorted(p for p in cust.iterdir() if p.is_dir()):
            kind = classify_folder(child.name)
            if not kind:
                continue
            title = folder_title(child) or child.name
            node["tasks"].append(
                {"kind": kind, "title": title, "path": f"{cust.name}/{child.name}"}
            )
        customers.append(node)
    return {"customers": customers}


def merge_scan(home: Path, root: Path) -> dict:
    found = scan_tree(root)
    doc = load_store(home)
    for cust in found["customers"]:
        node = next((c for c in doc["customers"] if c.get("name") == cust["name"]), None)
        if node is None:
            doc["customers"].append(
                {"name": cust["name"], "path": cust.get("path") or cust["name"], "tasks": list(cust.get("tasks") or [])}
            )
            continue
        node.setdefault("tasks", [])
        for task in cust.get("tasks") or []:
            _add_task(node, task)
    save_store(home, doc)
    return doc


def updater_interval_s() -> int:
    """FR #9984: catch-up scan interval. Env GITCUST_UPDATE_S, default 3600, minimum 60."""
    import os

    raw = (os.environ.get("GITCUST_UPDATE_S") or "").strip()
    try:
        val = int(raw) if raw else 3600
    except ValueError:
        val = 3600
    return max(60, val)


def run_updater(home: Path, root: Path) -> dict:
    """Periodic catch-up. Does not replace POST on create."""
    return merge_scan(home, root)
