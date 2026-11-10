"""FR #6387: measure seat model + token usage and stamp DONE lines.

The worker (not the model) appends measured counters when it relays DONE.
Never fabricate a zero: missing sources become ``tokens=unknown``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

_DONE_RX = re.compile(r"(?i)^DONE\b")
_MODEL_RX = re.compile(r"(?i)\bmodel=([^\s]+)")
_TOKENS_UNKNOWN_RX = re.compile(r"(?i)\btokens=unknown\b")
_LEGACY_TOKENS_RX = re.compile(r"(?i)\btokens=(\d+)\b")
_TOKENS_IN_RX = re.compile(r"(?i)\btokens_in=(\d+)\b")
_TOKENS_OUT_RX = re.compile(r"(?i)\btokens_out=(\d+)\b")
_TOKENS_CACHED_RX = re.compile(r"(?i)\btokens_cached=(\d+)\b")
# Strip model-written counters when a measured stamp replaces them.
_STRIP_USAGE_RX = re.compile(
    r"(?i)\s*\b(?:model|tokens|tokens_in|tokens_out|tokens_cached)=[^\s]+"
)


def _empty(*, unknown: bool = True) -> dict[str, Any]:
    return {
        "model": "",
        "tokens_in": None,
        "tokens_out": None,
        "tokens_cached": None,
        "legacy_tokens": None,
        "tokens_unknown": bool(unknown),
        "tokens_total": None,
    }


def _int_or_none(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _normalize_model(raw: Any, *, default_provider: str = "") -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if "/" in s:
        return s
    if default_provider:
        return f"{default_provider}/{s}"
    return s


def parse_done_usage(rest: str) -> dict[str, Any]:
    """Parse measured / legacy token fields from the text after the DONE verb+job."""
    text = rest or ""
    out = _empty(unknown=False)
    m = _MODEL_RX.search(text)
    if m:
        out["model"] = str(m.group(1)).strip()
    tin = _TOKENS_IN_RX.search(text)
    tout = _TOKENS_OUT_RX.search(text)
    tc = _TOKENS_CACHED_RX.search(text)
    if tin:
        out["tokens_in"] = int(tin.group(1))
    if tout:
        out["tokens_out"] = int(tout.group(1))
    if tc:
        out["tokens_cached"] = int(tc.group(1))
    if _TOKENS_UNKNOWN_RX.search(text):
        out["tokens_unknown"] = True
        out["legacy_tokens"] = None
    else:
        leg = _LEGACY_TOKENS_RX.search(text)
        if leg:
            out["legacy_tokens"] = int(leg.group(1))
    measured = any(out[k] is not None for k in ("tokens_in", "tokens_out", "tokens_cached"))
    if measured:
        out["tokens_unknown"] = False
        total = 0
        for k in ("tokens_in", "tokens_out"):
            if out[k] is not None:
                total += int(out[k])
        out["tokens_total"] = total
    elif out["legacy_tokens"] is not None:
        out["tokens_unknown"] = False
        out["tokens_total"] = int(out["legacy_tokens"])
    else:
        out["tokens_unknown"] = True
        out["tokens_total"] = None
    return out


def format_done_usage_suffix(usage: Mapping[str, Any] | None) -> str:
    """Wire suffix: measured fields, or ``tokens=unknown`` (never a fabricated 0)."""
    u = dict(usage or {})
    model = str(u.get("model") or "").strip()
    tin = _int_or_none(u.get("tokens_in"))
    tout = _int_or_none(u.get("tokens_out"))
    tc = _int_or_none(u.get("tokens_cached"))
    unknown = bool(u.get("tokens_unknown"))
    measured = tin is not None or tout is not None or tc is not None
    parts: list[str] = []
    if model:
        parts.append(f"model={model}")
    if measured and not unknown:
        # Emit only fields the source actually provided (a real 0 is fine; a missing
        # field must not become a fabricated 0 on the wire).
        if tin is not None:
            parts.append(f"tokens_in={tin}")
        if tout is not None:
            parts.append(f"tokens_out={tout}")
        if tc is not None:
            parts.append(f"tokens_cached={tc}")
    else:
        parts.append("tokens=unknown")
    return " ".join(parts)


def _strip_usage_fields(text: str) -> str:
    return _STRIP_USAGE_RX.sub("", text or "").rstrip()


def enrich_done_payload(payload: str, usage: Mapping[str, Any] | None) -> str:
    """Append a measured usage stamp to a DONE line; leave non-DONE lines alone.

    When a measured value exists, model-written ``tokens=`` / ``model=`` counters
    on the line are removed so the measured stamp wins.
    """
    text = (payload or "").strip()
    if not text or not _DONE_RX.match(text):
        return payload if payload is not None else ""
    cleaned = _strip_usage_fields(text).rstrip()
    suffix = format_done_usage_suffix(usage)
    if not suffix:
        return cleaned
    return f"{cleaned} {suffix}".rstrip()


def _from_token_map(
    raw: Mapping[str, Any],
    *,
    model: str = "",
    default_provider: str = "",
) -> dict[str, Any]:
    out = _empty(unknown=True)
    if model:
        out["model"] = _normalize_model(model, default_provider=default_provider)
    # Accept several common key shapes from agent CLIs / fixtures.
    tin = (
        _int_or_none(raw.get("tokens_in"))
        if "tokens_in" in raw
        else _int_or_none(raw.get("inputTokens"))
        if "inputTokens" in raw
        else _int_or_none(raw.get("input_tokens"))
        if "input_tokens" in raw
        else _int_or_none(raw.get("prompt_tokens"))
        if "prompt_tokens" in raw
        else _int_or_none(raw.get("input"))
        if "input" in raw
        else None
    )
    tout = (
        _int_or_none(raw.get("tokens_out"))
        if "tokens_out" in raw
        else _int_or_none(raw.get("outputTokens"))
        if "outputTokens" in raw
        else _int_or_none(raw.get("output_tokens"))
        if "output_tokens" in raw
        else _int_or_none(raw.get("completion_tokens"))
        if "completion_tokens" in raw
        else _int_or_none(raw.get("output"))
        if "output" in raw
        else None
    )
    tc = (
        _int_or_none(raw.get("tokens_cached"))
        if "tokens_cached" in raw
        else _int_or_none(raw.get("cachedReadTokens"))
        if "cachedReadTokens" in raw
        else _int_or_none(raw.get("cache_read_tokens"))
        if "cache_read_tokens" in raw
        else _int_or_none(raw.get("cached_tokens"))
        if "cached_tokens" in raw
        else _int_or_none(raw.get("cache"))
        if "cache" in raw
        else None
    )
    if tin is None and tout is None and tc is None:
        return out
    out["tokens_in"] = tin
    out["tokens_out"] = tout
    out["tokens_cached"] = tc
    out["tokens_unknown"] = False
    total = 0
    if tin is not None:
        total += tin
    if tout is not None:
        total += tout
    out["tokens_total"] = total
    return out


def _load_json(path: Path | str | None) -> Any:
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_grok_usage(path: Path | str | None) -> dict[str, Any]:
    """Read ``~/.grok/sessions/.../<uuid>/usage.json`` (usage only; no auth files)."""
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    session = doc.get("session") if isinstance(doc.get("session"), dict) else doc
    if not isinstance(session, dict):
        return _empty(unknown=True)
    model = (
        session.get("primaryModelId")
        or doc.get("primaryModelId")
        or doc.get("model")
        or ""
    )
    return _from_token_map(session, model=str(model), default_provider="xai")


def read_cursor_usage(path: Path | str | None) -> dict[str, Any]:
    """Read a Cursor agent usage/export JSON fixture (no secrets)."""
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    model = doc.get("model") or doc.get("modelId") or doc.get("primaryModelId") or ""
    usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else doc
    return _from_token_map(usage, model=str(model), default_provider="cursor")


def read_opencode_usage(path: Path | str | None) -> dict[str, Any]:
    """Read an OpenCode session export / stats JSON fixture (no secrets)."""
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    model = doc.get("model") or doc.get("modelId") or doc.get("primaryModelId") or ""
    tokens = doc.get("tokens") if isinstance(doc.get("tokens"), dict) else None
    if tokens is not None:
        return _from_token_map(tokens, model=str(model), default_provider="opencode")
    usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else doc
    return _from_token_map(usage, model=str(model), default_provider="opencode")


def read_aider_usage(path: Path | str | None) -> dict[str, Any]:
    """Read an Aider usage/cost JSON fixture (no secrets)."""
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return _empty(unknown=True)
    model = doc.get("model") or doc.get("main_model") or ""
    return _from_token_map(doc, model=str(model), default_provider="aider")


def measure_seat_usage(
    kind: str,
    *,
    grok_usage_path: Path | str | None = None,
    cursor_usage_path: Path | str | None = None,
    opencode_usage_path: Path | str | None = None,
    aider_usage_path: Path | str | None = None,
) -> dict[str, Any]:
    """Dispatch to the agent-kind usage reader. Missing source → tokens=unknown."""
    k = (kind or "").strip().lower()
    if k == "grok":
        return read_grok_usage(grok_usage_path)
    if k in ("cursor", "cursor-agent", "agent"):
        return read_cursor_usage(cursor_usage_path)
    if k in ("opencode", "oc"):
        return read_opencode_usage(opencode_usage_path)
    if k == "aider":
        return read_aider_usage(aider_usage_path)
    return _empty(unknown=True)


def grok_usage_path_for_session(
    cwd: str,
    session_id: str,
    sessions_root: Path | str | None = None,
) -> Optional[Path]:
    """Resolve ``usage.json`` beside the grok session ``events.jsonl``."""
    from urllib.parse import quote

    if not session_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", str(session_id)):
        return None
    root = Path(sessions_root) if sessions_root else Path.home() / ".grok" / "sessions"
    for key in (quote(str(cwd), safe=""), quote(str(cwd).rstrip("\\"), safe="")):
        d = root / key / str(session_id)
        if d.is_dir():
            return d / "usage.json"
    return None
