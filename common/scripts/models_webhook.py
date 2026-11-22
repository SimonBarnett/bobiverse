"""BOB-15 / FR #8711: fetch GET /bob/v1/models rows for start-contract settings.

Transport failures return None (caller falls back to local settings). Never invent
model ids. Process-local cache: one successful or failed fetch per process unless
``force``.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

DEFAULT_MODELS_URL = "https://bob.ntsa.uk/bob/v1/models"
ENV_MODELS_URL = "BOB_MODELS_WEBHOOK_URL"
USER_AGENT = "bobiverse-models-webhook/1.0"
# Model ids land in generated PowerShell; reject injection-prone chars.
_BAD_MODEL = re.compile(r"""[\s'"$;`|&<>]""")

# Kind / OpenCode slot -> Weights agent row name (BOB-01).
_KIND_ROW = {
    "grok": "Grok",
    "cursor": "Cursor",
    "aider": "Grok",  # no dedicated Weights row; treat as Grok CLI settings
    "opencode": "Opencode",
}
_OPENCODE_SLOT_ROW = {
    "free": "Opencode-Free",
    "paid": "Opencode",
}

_cache: dict[str, Any] | None = None
_cache_key: str | None = None


def models_webhook_url(*, env: dict[str, str] | None = None) -> str | None:
    """URL for GET models. Empty env value disables the source. Missing -> default."""
    e = os.environ if env is None else env
    if ENV_MODELS_URL in (e or {}):
        got = str((e or {}).get(ENV_MODELS_URL) or "").strip()
        return got or None
    return DEFAULT_MODELS_URL


def clear_models_webhook_cache() -> None:
    global _cache, _cache_key
    _cache = None
    _cache_key = None


def _safe_model(raw: object) -> tuple[str, str]:
    mid = str(raw or "").strip()
    if not mid:
        return "", ""
    if _BAD_MODEL.search(mid):
        return "", "model_metachar"
    return mid, ""


def normalize_agent_row(
    obj: Any,
    *,
    valid_contexts: set[str] | None = None,
    valid_efforts: set[str] | None = None,
) -> tuple[dict[str, str] | None, dict[str, str]]:
    """Normalise one BOB-01 agent row. Drop invalid context/effort with reasons."""
    reasons: dict[str, str] = {}
    if not isinstance(obj, dict):
        return None, {"row": "not_object"}
    agent = str(obj.get("agent") or "").strip()
    cli = str(obj.get("cli") or "").strip()
    if not agent or not cli:
        return None, {"row": "missing_agent_or_cli"}
    model, why_m = _safe_model(obj.get("model"))
    if why_m:
        reasons["model"] = why_m
        model = ""
    context = str(obj.get("context") or "").strip()
    if context and valid_contexts is not None and context not in valid_contexts:
        reasons["context"] = "invalid_context"
        context = ""
    effort = str(obj.get("effort") or "").strip()
    if effort and valid_efforts is not None and effort not in valid_efforts:
        reasons["effort"] = "invalid_effort"
        effort = ""
    return {
        "row": agent,
        "cli": cli,
        "model": model,
        "context": context,
        "effort": effort,
    }, reasons


def _valid_sets_from_seed() -> tuple[set[str], set[str]]:
    """Union of contexts/efforts from shipped BOB-04 seed (best-effort)."""
    contexts: set[str] = set()
    efforts: set[str] = set()
    try:
        import models_catalog as mc

        seed = mc.resolve_valid_combos_seed_path()
        if seed is None or not seed.is_file():
            return contexts, efforts
        doc = mc.load_seed_document(seed)
        clis = doc.get("clis") or {}
        if not isinstance(clis, dict):
            return contexts, efforts
        for rows in clis.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for c in row.get("contexts") or []:
                    if isinstance(c, str) and c.strip():
                        contexts.add(c.strip())
                for e in row.get("efforts") or []:
                    if isinstance(e, str) and e.strip():
                        efforts.add(e.strip())
    except Exception:
        return set(), set()
    return contexts, efforts


def fetch_models_webhook(
    *,
    url: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 5.0,
    force: bool = False,
    opener=None,
) -> dict[str, Any] | None:
    """GET models JSON. Returns ``{"agents":[...], "url":...}`` or None."""
    global _cache, _cache_key
    target = url if url is not None else models_webhook_url(env=env)
    if not target:
        return None
    key = target
    if not force and _cache_key == key:
        return _cache
    open_fn = opener or urllib.request.urlopen
    try:
        req = urllib.request.Request(
            target,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        with open_fn(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        doc = json.loads(raw or "{}")
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
        ValueError,
        TypeError,
    ):
        _cache = None
        _cache_key = key
        return None
    if not isinstance(doc, dict):
        _cache = None
        _cache_key = key
        return None
    agents = doc.get("agents")
    if not isinstance(agents, list):
        _cache = None
        _cache_key = key
        return None
    contexts, efforts = _valid_sets_from_seed()
    rows: list[dict[str, str]] = []
    for item in agents:
        row, _reasons = normalize_agent_row(
            item,
            valid_contexts=contexts or None,
            valid_efforts=efforts or None,
        )
        if row is not None:
            rows.append(row)
    out = {"agents": rows, "url": target}
    _cache = out
    _cache_key = key
    return out


def lookup_webhook_row(
    kind: str,
    *,
    opencode_slot: str | None = None,
    doc: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Return normalised row for a worker kind (and OpenCode free/paid slot)."""
    payload = doc if doc is not None else fetch_models_webhook(env=env)
    if not payload:
        return None
    agents = payload.get("agents") or []
    cli = str(kind or "").strip().lower()
    if cli == "opencode" and opencode_slot:
        want = _OPENCODE_SLOT_ROW.get(str(opencode_slot).strip().lower(), "")
    else:
        want = _KIND_ROW.get(cli, "")
    if not want:
        return None
    for row in agents:
        if isinstance(row, dict) and str(row.get("row") or "") == want:
            return row
    return None


def webhook_settings_for_cli(
    kind: str,
    *,
    opencode_slot: str | None = None,
    env: dict[str, str] | None = None,
    doc: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Settings overlay for one CLI. Empty strings when missing."""
    row = lookup_webhook_row(kind, opencode_slot=opencode_slot, doc=doc, env=env)
    if not row:
        return {"model": "", "context": "", "effort": "", "source": "missing"}
    return {
        "model": str(row.get("model") or ""),
        "context": str(row.get("context") or ""),
        "effort": str(row.get("effort") or ""),
        "source": "webhook",
        "row": str(row.get("row") or ""),
    }
