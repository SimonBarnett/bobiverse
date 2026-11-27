"""FR #10032: GET /bob/v1/ask/health and POST /bob/v1/ask."""
from __future__ import annotations

import json
import re

ASK_PATH = "/bob/v1/ask"
HEALTH_PATH = "/bob/v1/ask/health"
_SC = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CORR = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_SECRET_KEY = re.compile(r"password|token|secret|authorization|api_key", re.I)


def health() -> tuple[int, bytes]:
    return 200, json.dumps({"ok": True, "service": "ask"}).encode("utf-8")


def validate_ask(raw: bytes | str) -> tuple[dict | None, str]:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        doc = json.loads(text or "")
    except json.JSONDecodeError:
        return None, "malformed"
    if not isinstance(doc, dict):
        return None, "malformed"
    for key in doc:
        if _SECRET_KEY.search(str(key)):
            return None, "secret_field"
    sc = str(doc.get("sc") or "").strip()
    corr = str(doc.get("correlation_id") or "").strip()
    if not _SC.match(sc):
        return None, "bad_sc"
    if not _CORR.match(corr):
        return None, "bad_correlation_id"
    body = doc.get("text")
    if body is not None and (not isinstance(body, str) or len(body) > 4000):
        return None, "bad_text"
    return {"sc": sc, "correlation_id": corr}, ""


def handle_post(raw: bytes | str) -> tuple[int, bytes]:
    row, why = validate_ask(raw)
    if row is None:
        return 400, json.dumps({"error": why}).encode("utf-8")
    return 202, json.dumps({"ok": True, "correlation_id": row["correlation_id"]}).encode("utf-8")
