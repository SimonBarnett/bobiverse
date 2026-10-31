"""In-service Priority form-walk (FR #5285).

Read path only: formStart / subform / getRows via a service-owned Python
worker and a recorded JSON fixture (or DEV allowlist form). No agent .mjs.
IRC never carries Priority passwords.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WALK_OPS = frozenset({"formstart", "subform", "getrows"})
OP_WIRE = {"formstart": "formStart", "subform": "subform", "getrows": "getRows"}
_SECRET_KEYS = frozenset({"password", "passwd", "secret", "token", "pwd"})
_ID_PREFIX_RE = re.compile(r"(?is)^id=([0-9a-f]{8})\s+(.*)$")
_KV_RE = re.compile(r"(\w+)=([^\s]+)")
_VERB_RE = re.compile(
    r"(?is)^PRIORITY\s+(formStart|subform|getRows)(?:\s+(.*))?$",
)


@dataclass(frozen=True)
class PriorityWalkResult:
    ok: bool
    exit_code: int
    job_id: str
    lines: tuple[str, ...]
    payload: dict[str, Any]


def parse_priority_command(text: str) -> tuple[str, dict[str, str]] | None:
    raw = (text or "").strip()
    leading_id = ""
    m_id = _ID_PREFIX_RE.match(raw)
    if m_id:
        leading_id = (m_id.group(1) or "").lower()
        raw = (m_id.group(2) or "").strip()
    m = _VERB_RE.match(raw)
    if not m:
        return None
    op = m.group(1)
    kv = {mm.group(1).lower(): mm.group(2) for mm in _KV_RE.finditer(m.group(2) or "")}
    if leading_id and "id" not in kv:
        kv["id"] = leading_id
    return op, kv


def default_fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "priority-worker" / "fixtures" / "form_walk.json"


def load_allowlist(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    inst = data.get("instances")
    if not isinstance(inst, list):
        return []
    return [x for x in inst if isinstance(x, dict) and str(x.get("id") or "").strip()]


def resolve_instance(allowlist: list[dict[str, Any]], instance_id: str) -> dict[str, Any] | None:
    want = (instance_id or "").strip().lower()
    for row in allowlist:
        if str(row.get("id") or "").strip().lower() == want:
            return row
    return None


def _secret_in_kv(kv: dict[str, str]) -> bool:
    return any(k.lower() in _SECRET_KEYS for k in kv)


def load_fixture(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    forms = data.get("forms")
    if not isinstance(forms, dict):
        raise ValueError("fixture missing forms")
    return forms


def walk_fixture(op: str, forms: dict[str, Any], kv: dict[str, str]) -> dict[str, Any]:
    form = (kv.get("form") or "").strip()
    rec = forms.get(form)
    if not isinstance(rec, dict):
        raise KeyError(form)
    wire = OP_WIRE[op.lower()]
    out: dict[str, Any] = {"ok": True, "op": wire, "form": form, "instance": kv.get("instance", "")}
    if wire == "subform":
        path = (kv.get("path") or "").strip()
        subs = rec.get("subforms") or {}
        if path not in subs:
            raise KeyError(path)
        out["path"] = path
        out["subform"] = subs[path]
    elif wire == "getRows":
        rows = rec.get("rows") or []
        out["rows"] = list(rows)
        out["count"] = len(rows)
    else:
        out["title"] = rec.get("title") or form
        out["subforms"] = list((rec.get("subforms") or {}).keys())
    return out


def run_priority_walk(
    *,
    text: str,
    allowlist_path: Path | None,
    fixture_path: Path | None = None,
    job_id_fallback: str = "",
) -> PriorityWalkResult:
    parsed = parse_priority_command(text)
    if parsed is None:
        jid = job_id_fallback or "-"
        return PriorityWalkResult(False, 2, jid, (f"err id={jid} code=bad_frame msg=not-priority", f"DONE id={jid} exit=2"), {})
    op, kv = parsed
    jid = (kv.get("id") or job_id_fallback or "00000000").lower()
    if _secret_in_kv(kv):
        payload = {"ok": False, "error": "password-refused"}
        body = json.dumps(payload, separators=(",", ":"))
        lines = (f"out id={jid} seq=1 {body}", f"DONE id={jid} exit=2")
        return PriorityWalkResult(False, 2, jid, lines, payload)
    inst_id = (kv.get("instance") or "").strip()
    allow = load_allowlist(allowlist_path)
    if resolve_instance(allow, inst_id) is None:
        payload = {"ok": False, "error": "unknown-instance"}
        body = json.dumps(payload, separators=(",", ":"))
        lines = (f"out id={jid} seq=1 {body}", f"DONE id={jid} exit=2")
        return PriorityWalkResult(False, 2, jid, lines, payload)
    form = (kv.get("form") or "").strip()
    if not form:
        payload = {"ok": False, "error": "missing-form"}
        body = json.dumps(payload, separators=(",", ":"))
        lines = (f"out id={jid} seq=1 {body}", f"DONE id={jid} exit=2")
        return PriorityWalkResult(False, 2, jid, lines, payload)
    fix = Path(fixture_path) if fixture_path else default_fixture_path()
    try:
        forms = load_fixture(fix)
        payload = walk_fixture(op, forms, kv)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "error": "fixture-miss", "detail": type(exc).__name__}
        body = json.dumps(payload, separators=(",", ":"))
        lines = (f"out id={jid} seq=1 {body}", f"DONE id={jid} exit=2")
        return PriorityWalkResult(False, 2, jid, lines, payload)
    body = json.dumps(payload, separators=(",", ":"))
    lines = (f"out id={jid} seq=1 {body}", f"DONE id={jid} exit=0")
    return PriorityWalkResult(True, 0, jid, lines, payload)


def resolve_allowlist_path(install_root: str | None, override: str | None) -> Path | None:
    if override:
        return Path(override)
    if not install_root:
        return None
    root = Path(install_root)
    for rel in ("priority-instances.json", "config/priority-instances.json"):
        cand = root / rel
        if cand.is_file():
            return cand
    return None
