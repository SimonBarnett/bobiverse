"""OpenCode fuel helpers for Bob Fleet worker seats.

OpenCode Go has per-model monthly dollar allowances with rolling caps.  There is no
public remaining-quota API, so we estimate remaining % from local ``opencode stats``
cost vs the known caps.  ``opencode-free`` is a separate fuel id for the no-account
free models.

All functions are pure / testable and never touch credentials.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

# Fuel ids published to the digest webhook.
FUEL_ID_FREE = "opencode-free"
FUEL_ID_GO = "opencode-go"

# Provider prefix used by the opencode CLI ``-m`` flag.
# ``opencode`` and ``opencode-go`` are the documented providers for free models;
# ``opencode-free`` is kept for backward compatibility with older fixtures/catalogues.
PROVIDER_FREE = "opencode-free"
PROVIDER_GO = "opencode-go"
PROVIDER_FREE_PREFIXES = ("opencode", "opencode-go", "opencode-free")

# Known Go-plan per-model monthly USD allowances (issue #6120 / MarchHare install notes).
# Models not in this map are treated as cap-unknown and excluded from aggregate fuel.
OPENCODE_GO_CAPS: dict[str, float] = {
    "glm-5.3": 15.0,
    "glm-5.3-flash": 60.0,
    "glm-5.2": 60.0,
    "kimi-k3": 60.0,
    "kimi-k2.7-code": 60.0,
    "longcat-2.0": 60.0,
    "deepseek-v4.1-flash": 60.0,
    "qwen3.8-flash": 60.0,
}

# Rolling cap fractions of the monthly allowance.  A model is capped when any
# window is exhausted, so remaining % is driven by the most-utilised window.
# Only the 7-day and 30-day windows are read from ``opencode stats``; the 5-hour
# rolling cap is enforced at run time by the OpenCode wrapper (see
# ``record_opencode_pause``).
CAP_WINDOWS: dict[str, float] = {
    "week": 0.50,
    "month": 1.00,
}

# TipForm/Status Go windows (FR #6147 clarification). ``rolling`` is not read from
# ``opencode stats``; it is unstarted unless a fixture or runtime pause supplies it.
GO_WINDOW_IDS: tuple[str, ...] = ("rolling", "week", "month")
GO_WINDOW_LABELS: dict[str, str] = {
    "rolling": "rolling",
    "week": "weekly",
    "month": "monthly",
}

# Free models available without an account (issue #6120).
OPENCODE_FREE_MODELS: tuple[str, ...] = (
    "beam-free",
    "iceman-contributor-free",
)

# Preferred fallback order within the Go plan when the current model is capped.
# Mirrors the verified/cheap-to-expensive order from the trial notes.
OPENCODE_GO_FALLBACK_ORDER: tuple[str, ...] = (
    "glm-5.3",
    "glm-5.3-flash",
    "glm-5.2",
    "kimi-k3",
    "kimi-k2.7-code",
    "longcat-2.0",
    "deepseek-v4.1-flash",
    "qwen3.8-flash",
)

# Phrases that indicate an ``opencode run`` hit a rate / rolling / payment limit.
# Bare numeric codes (402/429) are intentionally excluded; they require HTTP/status
# context (see ``looks_like_rate_limit``) to avoid false positives from issue
# numbers, commit hashes and timings in normal output.
RATE_LIMIT_PHRASES: tuple[str, ...] = (
    "too many requests",
    "rate limit",
    "rolling limit",
    "usage balance exhausted",
    "payment required",
)

# Default pause when the provider gives no reset time (seconds).
DEFAULT_PAUSE_S = 3600


def _clamp_pct(n: Optional[float]) -> Optional[int]:
    if n is None:
        return None
    try:
        v = int(n)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return 0
    if v > 100:
        return 100
    return v


def _cost_for_model(stats: dict, model: str) -> Optional[float]:
    """Return USD cost for ``model`` from a stats doc, or None if absent."""
    costs = stats.get("costs") if isinstance(stats.get("costs"), dict) else {}
    raw = costs.get(model)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def model_remaining_pct(model: str, stats: dict) -> Optional[int]:
    """Estimated remaining % for a single Go model, or None if unknown."""
    cap = OPENCODE_GO_CAPS.get(model)
    if cap is None or cap <= 0:
        return None
    cost = _cost_for_model(stats, model)
    if cost is None:
        return None
    return _clamp_pct(100.0 - (100.0 * cost / cap))


def _go_models_remaining(stats: dict) -> dict[str, int]:
    """Map of Go model -> remaining % for models with known caps and cost data."""
    out: dict[str, int] = {}
    for model in OPENCODE_GO_FALLBACK_ORDER:
        rem = model_remaining_pct(model, stats)
        if rem is not None:
            out[model] = rem
    return out


def _cost_for_model_windowed(windowed: dict, model: str) -> dict[str, Optional[float]]:
    """Return per-window cost for ``model``.

    A successfully parsed window with no row for the model reports ``0.0``,
    but only when the model has been seen in at least one window.  A model
    that never appears in any window remains unknown, and a failed/timed-out
    or unparseable window reports ``None`` so the aggregate remains unknown.
    """
    seen = any(
        isinstance(w, dict) and model in (w.get("costs") or {})
        for w in windowed.values()
    )
    out: dict[str, Optional[float]] = {}
    for window in CAP_WINDOWS:
        stats = windowed.get(window)
        if not isinstance(stats, dict) or not stats.get("parse_success"):
            out[window] = None
        elif not seen:
            out[window] = None
        else:
            cost = _cost_for_model(stats, model)
            out[window] = 0.0 if cost is None else cost
    return out


def model_remaining_pct_for_windows(model: str, windowed: dict) -> Optional[int]:
    """Estimated remaining % for a Go model across rolling cap windows.

    A missing or failed window reading makes the model allowance unknown, so
    the seat never selects a model from incomplete cap data.
    """
    cap = OPENCODE_GO_CAPS.get(model)
    if cap is None or cap <= 0:
        return None
    costs = _cost_for_model_windowed(windowed, model)
    # All rolling windows are required; a failed stats call must not be
    # treated as zero usage.
    if any(v is None for v in costs.values()):
        return None
    max_util = 0.0
    for window, fraction in CAP_WINDOWS.items():
        cost = costs.get(window)
        if cost is None:
            continue
        limit = cap * fraction
        if limit <= 0:
            continue
        util = cost / limit
        if util > max_util:
            max_util = util
    return _clamp_pct(100.0 - (100.0 * max_util))


def _go_models_remaining_for_windows(windowed: dict) -> dict[str, int]:
    """Map of Go model -> remaining % using rolling cap windows."""
    out: dict[str, int] = {}
    for model in OPENCODE_GO_FALLBACK_ORDER:
        rem = model_remaining_pct_for_windows(model, windowed)
        if rem is not None:
            out[model] = rem
    return out


def _is_free_model(slug: str) -> bool:
    """True when a model slug is one of the known free models or ends in ``-free``."""
    slug = (slug or "").strip()
    if not slug:
        return False
    if slug in OPENCODE_FREE_MODELS:
        return True
    return slug.endswith("-free")


def _free_models_available(stats: dict) -> bool:
    """True when the stats doc reports at least one free model as available."""
    free = stats.get("free_models") if isinstance(stats.get("free_models"), (list, tuple)) else None
    if free is None:
        # No data: free tier availability is unknown, not assumed.
        return False
    return any(_is_free_model(str(m).strip()) for m in free)


def _model_id_from_entry(entry: dict) -> Optional[str]:
    """Best-effort model slug from an OpenCode ``models`` array entry."""
    if not isinstance(entry, dict):
        return None
    for key in ("id", "model", "name", "slug"):
        raw = entry.get(key)
        if raw:
            return str(raw).strip()
    return None


def _cost_from_entry(entry: dict) -> Optional[float]:
    """Best-effort USD cost from an OpenCode ``models`` array/dict entry."""
    if not isinstance(entry, dict):
        return None
    raw = entry.get("cost")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from terminal output."""
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def _parse_money(value: str) -> Optional[float]:
    """Parse a string like '$1,234.56' or '1234.5' into a float, or None."""
    if not value:
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _is_table_row(line: str) -> bool:
    """True when a line starts with a box-drawing table border or cell marker.

    Also accepts the legacy mojibake glyphs produced by some terminal
    encodings (seen in captured fixture output), so that real ``opencode
    stats`` samples are still parsed as table rows.
    """
    if not isinstance(line, str):
        return False
    stripped = line.lstrip()
    return stripped.startswith(
        ("│", "┌", "└", "├", "─", "Ôöé", "Ôöî", "Ôöö", "Ôö£", "ÔöÇ")
    )


def _looks_like_models_list(text: str) -> bool:
    """True when text looks like plain ``opencode models`` output.

    Each non-empty line should be a ``provider/model`` id, there must be no
    stats table markers, and at least one line must begin with a documented
    OpenCode provider prefix.
    """
    if not text or not isinstance(text, str):
        return False
    text = _strip_ansi(text)
    if any(marker in text for marker in ("┌", "└", "─", "MODEL USAGE", "COST & TOKENS", "Total Cost")):
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    model_line_re = re.compile(r"^[\w.\-]+/[\w.\-]+$")
    return (
        all(model_line_re.match(ln) for ln in lines)
        and any(ln.startswith(("opencode/", "opencode-go/", "opencode-free/")) for ln in lines)
    )


def _parse_model_line(line: str) -> tuple[str, str]:
    """Split a ``provider/model`` line into provider and slug."""
    line = line.strip()
    if "/" not in line:
        return ("", line)
    provider, _, slug = line.partition("/")
    return (provider.strip(), slug.strip())


def parse_opencode_models_text(text: str | None) -> list[str]:
    """Translate plain ``opencode models`` output to a list of known free slugs.

    Returns recognised free model slugs (e.g. ``beam-free``) found in the
    catalogue output, which is one ``provider/model`` id per line.  Free models
    are identified by provider (``opencode`` / ``opencode-go`` / legacy
    ``opencode-free``) and a slug ending in ``-free`` or listed in
    ``OPENCODE_FREE_MODELS``.
    """
    if not text or not isinstance(text, str):
        return []
    slugs: list[str] = []
    seen: set[str] = set()
    for line in _strip_ansi(text).splitlines():
        line = line.strip()
        if not line or "/" not in line:
            continue
        provider, slug = _parse_model_line(line)
        if provider not in PROVIDER_FREE_PREFIXES:
            continue
        if not _is_free_model(slug):
            continue
        if slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def parse_opencode_model_ids(text: str | None) -> list[str]:
    """Return full ``provider/slug`` ids for free models in catalogue output."""
    if not text or not isinstance(text, str):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for line in _strip_ansi(text).splitlines():
        line = line.strip()
        if not line or "/" not in line:
            continue
        provider, slug = _parse_model_line(line)
        if provider not in PROVIDER_FREE_PREFIXES:
            continue
        if not _is_free_model(slug):
            continue
        full_id = f"{provider}/{slug}"
        if full_id not in seen:
            seen.add(full_id)
            ids.append(full_id)
    return ids


def parse_opencode_stats_text(text: str | None) -> dict:
    """Translate plain ``opencode stats`` table output to the fuel helper shape.

    Reads the ``Total Cost`` row and per-model ``Cost`` rows from the box-drawing
    table emitted by ``opencode stats --models``.  Returns
    ``{"costs": {"model": usd, ...}, "free_models": [...], "total_cost": usd_or_none,
    "parse_success": bool}``.  When parsing fails the function returns empty
    containers, ``None`` totals and ``parse_success=False`` rather than guessing.

    Section markers such as ``MODEL USAGE`` only count when they appear on table
    rows, so error text containing those words cannot make a failed window look
    successful.
    """
    if not text or not isinstance(text, str):
        return {"costs": {}, "free_models": [], "total_cost": None, "parse_success": False}

    text = _strip_ansi(text)
    lines = text.splitlines()

    costs: dict[str, float] = {}
    free_models: list[str] = []
    total_cost: Optional[float] = None

    in_cost_tokens = False
    in_model_usage = False
    saw_table_marker = False

    # Regex for model/provider names appearing anywhere in a line.
    model_re = re.compile(r"(opencode-(?:go|free)/[\w.\-]+|opencode/[\w.\-]+)")
    cost_re = re.compile(r"Cost\s+\$?([\d,]+\.\d+)", re.IGNORECASE)
    total_re = re.compile(r"Total Cost\s+\$?([\d,]+\.\d+)", re.IGNORECASE)

    # First pass: locate sections and total cost.
    for line in lines:
        upper = line.upper()
        if _is_table_row(line) and "COST & TOKENS" in upper:
            in_cost_tokens = True
            in_model_usage = False
            saw_table_marker = True
            continue
        if _is_table_row(line) and "MODEL USAGE" in upper:
            in_cost_tokens = False
            in_model_usage = True
            saw_table_marker = True
            continue
        if _is_table_row(line) and ("TOOL USAGE" in upper or "SESSIONS" in upper):
            in_cost_tokens = False
            in_model_usage = False
            saw_table_marker = True
            continue

        if in_cost_tokens:
            match = total_re.search(line)
            if match:
                total_cost = _parse_money(match.group(1))

    # Second pass: extract per-model costs.
    current_model: Optional[str] = None
    for line in lines:
        upper = line.upper()

        # Section boundaries.
        if _is_table_row(line) and "MODEL USAGE" in upper:
            in_model_usage = True
            current_model = None
            continue
        if _is_table_row(line) and ("TOOL USAGE" in upper or "COST & TOKENS" in upper or "OVERVIEW" in upper):
            in_model_usage = False
            current_model = None
            continue

        if not in_model_usage:
            continue

        # Skip metric rows that happen to contain a slash (e.g. none today, but be safe).
        if re.search(r"\b(Messages|Input Tokens|Output Tokens|Cache Read|Cache Write)\b", line, re.IGNORECASE):
            continue

        model_match = model_re.search(line)
        if model_match:
            current_model = model_match.group(1)
            saw_table_marker = True
            continue

        cost_match = cost_re.search(line)
        if cost_match and current_model:
            cost = _parse_money(cost_match.group(1))
            if cost is not None:
                slug = current_model.split("/")[-1]
                provider = current_model.split("/")[0] if "/" in current_model else ""
                if provider == PROVIDER_GO and slug in OPENCODE_GO_CAPS:
                    costs[slug] = cost
                elif provider in PROVIDER_FREE_PREFIXES and _is_free_model(slug):
                    free_models.append(slug)
            current_model = None

    parse_success = saw_table_marker or bool(costs) or bool(free_models) or total_cost is not None
    return {"costs": costs, "free_models": free_models, "total_cost": total_cost, "parse_success": parse_success}


def parse_opencode_stats_text_or_json(raw: str | None) -> dict:
    """Accept legacy JSON fixture, plain ``opencode stats`` table, or ``opencode models`` list.

    Keeps the ``BOB_OPENCODE_FUEL_FIXTURE`` environment path working for JSON
    fixtures while allowing the live ``opencode stats --models`` text and the
    ``opencode models`` catalogue to be passed straight through stdin.
    """
    if not raw or not isinstance(raw, str):
        return {"costs": {}, "free_models": [], "parse_success": False}

    trimmed = raw.strip()
    if trimmed.startswith("{"):
        try:
            doc = json.loads(trimmed)
            if isinstance(doc, dict):
                return parse_opencode_stats_json(doc)
        except json.JSONDecodeError:
            pass

    if _looks_like_models_list(trimmed):
        return {"costs": {}, "free_models": parse_opencode_models_text(trimmed), "parse_success": True}

    parsed = parse_opencode_stats_text(raw)
    return {
        "costs": parsed["costs"],
        "free_models": parsed["free_models"],
        "parse_success": parsed["parse_success"],
    }


def parse_opencode_stats_json(doc: dict | None) -> dict:
    """Translate a legacy JSON stats fixture to the fuel helper shape.

    The live CLI only emits plain-text tables (``opencode stats --models``), but
    environment fixtures may still supply JSON.  Returns
    ``{"costs": {"model": usd, ...}, "free_models": [...], "parse_success": bool}``.
    Unknown shapes return empty containers and ``parse_success=False`` rather
    than raising.
    """
    doc = doc if isinstance(doc, dict) else {}

    # Already in the helper shape (fixture or pre-translated).
    if isinstance(doc.get("costs"), dict) or isinstance(doc.get("free_models"), (list, tuple)):
        return {
            "costs": dict(doc.get("costs") or {}),
            "free_models": list(doc.get("free_models") or []),
            "parse_success": True,
        }

    costs: dict[str, float] = {}

    # v2 / v1 JSON: models may be an array of objects or a dict keyed by model id.
    models = doc.get("models") if isinstance(doc.get("models"), (dict, list, tuple)) else None
    if models is None and isinstance(doc.get("modelUsage"), dict):
        models = doc["modelUsage"]

    if isinstance(models, dict):
        for model_id, entry in models.items():
            model_id = str(model_id).strip()
            cost = _cost_from_entry(entry) if isinstance(entry, dict) else None
            if cost is not None and model_id:
                # Strip a provider prefix if present, matching the array branch.
                slug = model_id.split("/")[-1]
                costs[slug] = cost
    elif isinstance(models, (list, tuple)):
        for entry in models:
            model_id = _model_id_from_entry(entry)
            cost = _cost_from_entry(entry)
            if model_id and cost is not None:
                # Strip a provider prefix if present.
                slug = model_id.split("/")[-1]
                costs[slug] = cost

    free_models: list[str] = []
    if isinstance(doc.get("free_models"), (list, tuple)):
        free_models = [str(m).strip() for m in doc["free_models"] if str(m).strip()]
    elif isinstance(models, (dict, list, tuple)):
        # Discover available free models from the model catalogue (``opencode models``
        # style) as well as from recorded usage. For dictionary inputs the key is the
        # model id; for arrays we parse the entry as before.
        if isinstance(models, dict):
            entries: list = []
            for model_id, entry in models.items():
                entries.append((str(model_id).strip(), entry))
        else:
            entries = [(None, entry) for entry in models]
        for model_id, entry in entries:
            if model_id is None:
                model_id = (
                    str(entry).strip()
                    if isinstance(entry, str)
                    else _model_id_from_entry(entry)
                )
            if not model_id:
                continue
            provider = model_id.split("/")[0] if "/" in model_id else ""
            slug = model_id.split("/")[-1]
            if provider in PROVIDER_FREE_PREFIXES and _is_free_model(slug):
                free_models.append(slug)

    parse_success = bool(costs or free_models or models is not None)
    return {"costs": costs, "free_models": free_models, "parse_success": parse_success}



def _window_record(
    status: str,
    *,
    used_pct: Optional[int] = None,
    remaining_pct: Optional[int] = None,
    reset_label: Optional[str] = None,
    fetched_at: Optional[str] = None,
) -> dict:
    """One Go window paint record (FR #6147). Never invent used/remaining/reset."""
    return {
        "status": status,
        "used_pct": used_pct,
        "remaining_pct": remaining_pct,
        "reset_label": reset_label,
        "fetched_at": fetched_at,
    }


def _used_from_remaining(remaining: Optional[int]) -> Optional[int]:
    if remaining is None:
        return None
    return _clamp_pct(100 - int(remaining))


def model_remaining_pct_for_single_window(
    model: str, windowed: dict, window: str
) -> Optional[int]:
    """Remaining % for one CAP window only (week or month)."""
    if window not in CAP_WINDOWS:
        return None
    cap = OPENCODE_GO_CAPS.get(model)
    if cap is None or cap <= 0:
        return None
    costs = _cost_for_model_windowed(windowed, model)
    cost = costs.get(window)
    if cost is None:
        return None
    fraction = CAP_WINDOWS[window]
    limit = cap * fraction
    if limit <= 0:
        return None
    return _clamp_pct(100.0 - (100.0 * cost / limit))


def _aggregate_remaining_for_window(windowed: dict, window: str) -> Optional[int]:
    """Best-model remaining for one CAP window, or None when unknown."""
    rems: list[int] = []
    for model in OPENCODE_GO_FALLBACK_ORDER:
        rem = model_remaining_pct_for_single_window(model, windowed, window)
        if rem is not None:
            rems.append(rem)
    if not rems:
        return None
    return max(rems)


def normalize_go_windows(raw: object) -> dict[str, dict]:
    """Normalize fixture/digest Go window maps (FR #6147).

    Accepted statuses: unknown, unstarted, known, exhausted, stale.
    Used/remaining must agree when both present (used + remaining == 100).
    Reset labels are kept only when non-empty strings are supplied.
    """
    out: dict[str, dict] = {
        wid: _window_record("unknown") for wid in GO_WINDOW_IDS
    }
    if not isinstance(raw, dict):
        return out
    for wid in GO_WINDOW_IDS:
        src = raw.get(wid)
        if not isinstance(src, dict):
            continue
        status = str(src.get("status") or "unknown").strip().lower()
        if status not in ("unknown", "unstarted", "known", "exhausted", "stale"):
            status = "unknown"
        used = _clamp_pct(src.get("used_pct")) if src.get("used_pct") is not None and str(src.get("used_pct")) != "" else None
        rem = _clamp_pct(src.get("remaining_pct")) if src.get("remaining_pct") is not None and str(src.get("remaining_pct")) != "" else None
        if rem is not None and used is None:
            used = _used_from_remaining(rem)
        elif used is not None and rem is None:
            rem = _clamp_pct(100 - int(used))
        elif used is not None and rem is not None and (used + rem) != 100:
            # Prefer remaining as source of truth when both disagree.
            used = _used_from_remaining(rem)
        reset = src.get("reset_label")
        reset_label = str(reset).strip() if reset not in (None, "") else None
        fetched = src.get("fetched_at")
        fetched_at = str(fetched).strip() if fetched not in (None, "") else None
        if status == "unstarted":
            # Clarification fixture: unstarted rolling is 0% used, no invented rem/reset.
            out[wid] = _window_record(
                "unstarted",
                used_pct=0 if used is None else used,
                remaining_pct=None,
                reset_label=None,
                fetched_at=fetched_at,
            )
        elif status == "exhausted":
            out[wid] = _window_record(
                "exhausted",
                used_pct=100 if used is None else used,
                remaining_pct=0 if rem is None else rem,
                reset_label=reset_label,
                fetched_at=fetched_at,
            )
        elif status in ("known", "stale"):
            out[wid] = _window_record(
                status,
                used_pct=used,
                remaining_pct=rem,
                reset_label=reset_label,
                fetched_at=fetched_at,
            )
        else:
            out[wid] = _window_record("unknown", fetched_at=fetched_at)
    return out


def limiting_go_window(windows: dict[str, dict] | None) -> tuple[Optional[str], Optional[int]]:
    """Return (window_id, remaining_pct) for the most-restrictive known Go window.

    Exhausted windows win (remaining 0). Unknown/unstarted do not prove availability.
    """
    windows = windows if isinstance(windows, dict) else {}
    best_id: Optional[str] = None
    best_rem: Optional[int] = None
    for wid in GO_WINDOW_IDS:
        rec = windows.get(wid) if isinstance(windows.get(wid), dict) else None
        if not rec:
            continue
        status = str(rec.get("status") or "")
        rem = rec.get("remaining_pct")
        if status == "exhausted":
            rem = 0 if rem is None else _clamp_pct(rem)
        if status not in ("known", "exhausted", "stale"):
            continue
        if rem is None:
            continue
        rem_i = int(rem)
        if best_rem is None or rem_i < best_rem:
            best_rem = rem_i
            best_id = wid
    return best_id, best_rem


def go_windows_from_windowed_stats(
    windowed: dict[str, dict] | None,
    *,
    rolling: dict | None = None,
) -> dict[str, dict]:
    """Build Go rolling/weekly/monthly paint records from CAP window stats.

    ``rolling`` is never inferred from ``opencode stats``. When omitted, rolling
    is ``unstarted`` (Starts on first use). Week/month remaining come from the
    same cost/cap math as fuel selection; reset labels are omitted unless the
    caller supplies them on ``rolling`` or via ``normalize_go_windows``.
    """
    windowed = windowed if isinstance(windowed, dict) else {}
    windows: dict[str, dict] = {}
    if isinstance(rolling, dict):
        windows["rolling"] = normalize_go_windows({"rolling": rolling})["rolling"]
    else:
        windows["rolling"] = _window_record("unstarted", used_pct=0)

    for wid in ("week", "month"):
        rem = _aggregate_remaining_for_window(windowed, wid)
        if rem is None:
            # Distinguish missing CAP data from a failed parse of that window.
            raw = windowed.get(wid)
            if isinstance(raw, dict) and raw.get("parse_success") is False:
                windows[wid] = _window_record("unknown")
            elif not isinstance(raw, dict):
                windows[wid] = _window_record("unknown")
            else:
                windows[wid] = _window_record("unknown")
        elif rem <= 0:
            windows[wid] = _window_record(
                "exhausted", used_pct=100, remaining_pct=0
            )
        else:
            windows[wid] = _window_record(
                "known",
                used_pct=_used_from_remaining(rem),
                remaining_pct=rem,
            )
    return windows


def format_go_window_line(window_id: str, rec: dict | None) -> str:
    """One TipForm/Status line for a Go window (used vs remaining; honest n/a)."""
    label = GO_WINDOW_LABELS.get(window_id, window_id)
    rec = rec if isinstance(rec, dict) else {}
    status = str(rec.get("status") or "unknown")
    if status == "unstarted":
        return f"go {label}  Starts on first use  (0% used)"
    if status == "unknown":
        return f"go {label}  n/a"
    used = rec.get("used_pct")
    rem = rec.get("remaining_pct")
    bits: list[str] = []
    if used is not None:
        bits.append(f"{int(used)}% used")
    if rem is not None:
        bits.append(f"{int(rem)}% rem")
    if not bits:
        mid = "n/a"
    else:
        mid = " · ".join(bits)
    reset = rec.get("reset_label")
    if reset:
        mid = f"{mid}  reset {reset}"
    if status == "stale":
        mid = f"{mid}  [stale]"
    if status == "exhausted" and rem is None:
        mid = "100% used · 0% rem" + (f"  reset {reset}" if reset else "")
    return f"go {label}  {mid}"


def format_opencode_paint_lines(
    free_remaining: Optional[int],
    windows: dict[str, dict] | None,
    *,
    stale: bool = False,
) -> dict:
    """Build TipForm/Status OpenCode paint payload (FR #6147).

    Returns summary line, free line, window lines, limiting window id, and
    aggregate go remaining (most restrictive known window). Free stays distinct.
    """
    windows = normalize_go_windows(windows) if windows is not None else {
        wid: _window_record("unknown") for wid in GO_WINDOW_IDS
    }
    if stale:
        for wid, rec in list(windows.items()):
            if rec.get("status") in ("known", "exhausted", "unstarted"):
                windows[wid] = dict(rec)
                windows[wid]["status"] = "stale" if rec.get("status") != "unstarted" else "unstarted"
                if rec.get("status") != "unstarted":
                    windows[wid]["used_pct"] = None
                    windows[wid]["remaining_pct"] = None
                    windows[wid]["reset_label"] = None
    lim_id, lim_rem = limiting_go_window(windows)
    free_bit = f"{int(free_remaining)}%" if free_remaining is not None else "n/a"
    window_lines = [format_go_window_line(wid, windows.get(wid)) for wid in GO_WINDOW_IDS]
    if free_remaining is None and lim_rem is None and all(
        str((windows.get(w) or {}).get("status")) in ("unknown",) for w in GO_WINDOW_IDS
    ):
        summary = "OpenCode  n/a"
    else:
        go_bit = f"{int(lim_rem)}%" if lim_rem is not None else "n/a"
        if lim_id:
            go_bit = f"{GO_WINDOW_LABELS.get(lim_id, lim_id)} {go_bit}"
        summary = f"OpenCode  free {free_bit} | go {go_bit}"
        if stale:
            summary = f"{summary} [stale]"
    return {
        "summary": summary,
        "free_line": f"OpenCode free  {free_bit}",
        "window_lines": window_lines,
        "windows": windows,
        "limiting": lim_id,
        "go_remaining": lim_rem,
        "free_remaining": free_remaining,
    }


def fuel_from_stats(stats: dict | None) -> dict:
    """Build digest fuel numbers from an OpenCode stats document.

    The returned dict contains the two digest fuel ids (``opencode-free``,
    ``opencode-go``) plus a per-model breakdown under ``models``.  ``None`` means
    unknown (handled like other digest pools), ``0`` means exhausted.

    ``free_model_ids`` holds full ``provider/slug`` ids discovered from the
    ``opencode models`` catalogue so the worker can launch a real free model.

    ``stats`` shape (kept minimal and CLI-output-agnostic):

        {
          "costs": {"glm-5.3": 7.50, "kimi-k2.7-code": 12.00, ...},
          "free_models": ["beam-free", "iceman-contributor-free"],
          "free_model_ids": ["opencode/beam-free", ...]
        }
    """
    stats = stats if isinstance(stats, dict) else {}
    go_by_model = _go_models_remaining(stats)
    go_remaining: Optional[int] = None
    if go_by_model:
        # Usable Go fuel = best remaining model, because the seat can fall back.
        go_remaining = max(go_by_model.values())
    free_remaining: Optional[int] = None
    if _free_models_available(stats):
        free_remaining = 100
    free_model_ids = stats.get("free_model_ids")
    if not isinstance(free_model_ids, (list, tuple)):
        free_model_ids = []
    windows = {
        "rolling": _window_record("unstarted", used_pct=0),
        "week": _window_record("unknown"),
        "month": _window_record(
            "exhausted" if go_remaining == 0 else ("known" if go_remaining is not None else "unknown"),
            used_pct=_used_from_remaining(go_remaining) if go_remaining is not None else None,
            remaining_pct=go_remaining,
        ),
    }
    lim_id, _lim_rem = limiting_go_window(windows)
    return {
        FUEL_ID_FREE: free_remaining,
        FUEL_ID_GO: go_remaining,
        "models": go_by_model,
        "free_model_ids": list(free_model_ids),
        "windows": windows,
        "limiting": lim_id,
    }


def fuel_from_windowed_stats(windowed: dict[str, dict] | None) -> dict:
    """Build digest fuel numbers from rolling cap windows.

    ``windowed`` maps window names (``week``, ``month``) to stats docs produced
    by ``opencode stats --days <N>``.  Per-model remaining % is driven by the
    most-utilised window, because Go caps are rolling and a model is exhausted
    when any window limit is hit.  The 5-hour cap is enforced at run time by the
    wrapper and is not part of the windowed stats reading.
    """
    windowed = windowed if isinstance(windowed, dict) else {}
    go_by_model = _go_models_remaining_for_windows(windowed)
    go_remaining: Optional[int] = None
    if go_by_model:
        go_remaining = max(go_by_model.values())
    free_remaining: Optional[int] = None
    if any(_free_models_available(windowed.get(w) or {}) for w in CAP_WINDOWS):
        free_remaining = 100
    free_model_ids: list[str] = []
    for w in CAP_WINDOWS:
        wstats = windowed.get(w) or {}
        ids = wstats.get("free_model_ids")
        if isinstance(ids, (list, tuple)):
            free_model_ids.extend(str(i) for i in ids)
    windows = go_windows_from_windowed_stats(windowed)
    lim_id, _lim_rem = limiting_go_window(windows)
    return {
        FUEL_ID_FREE: free_remaining,
        FUEL_ID_GO: go_remaining,
        "models": go_by_model,
        "free_model_ids": list(dict.fromkeys(free_model_ids)),
        "windows": windows,
        "limiting": lim_id,
    }


def select_model(preferred: Optional[str], stats: dict) -> Optional[str]:
    """Pick a model to run, falling back when the preferred model is capped.

    Returns ``None`` when no Go model has remaining allowance and no free model is
    available.  Free models are the final fallback.
    """
    preferred = (preferred or "").strip().lower()
    # Strip provider prefix if present.
    if preferred.startswith(f"{PROVIDER_GO}/"):
        preferred = preferred[len(f"{PROVIDER_GO}/") :]
    for prefix in PROVIDER_FREE_PREFIXES:
        if preferred.startswith(f"{prefix}/"):
            preferred = preferred[len(f"{prefix}/") :]
            break

    if preferred and preferred in OPENCODE_GO_CAPS:
        rem = model_remaining_pct(preferred, stats)
        if rem is not None and rem > 0:
            return preferred

    # Try Go models in fallback order, preferring those with the most remaining.
    go_rems = _go_models_remaining(stats)
    ordered = sorted(
        go_rems.items(),
        key=lambda kv: (-kv[1], OPENCODE_GO_FALLBACK_ORDER.index(kv[0]) if kv[0] in OPENCODE_GO_FALLBACK_ORDER else 999),
    )
    for model, rem in ordered:
        if rem > 0:
            return model

    # Final fallback to the free tier.
    if _free_models_available(stats):
        return OPENCODE_FREE_MODELS[0]

    return None


def model_is_capped(model: Optional[str], stats: dict) -> bool:
    """True when the model's cap is hit or no data is available."""
    if not model:
        return True
    rem = model_remaining_pct(model, stats)
    if rem is None:
        return True
    return rem <= 0


def is_exhausted(stats: dict | None) -> bool:
    """True when no Go model and no free model remains."""
    if stats is None:
        return True
    fuel = fuel_from_stats(stats)
    go = fuel.get(FUEL_ID_GO)
    free = fuel.get(FUEL_ID_FREE)
    if free is not None and free > 0:
        return False
    if go is not None and go > 0:
        return False
    return True


# ----------------------------------------------------------------------------------
# Runtime rate-limit / rolling-cap pause logic for the OpenCode wrapper.
# These helpers are pure (no I/O except the injected file-system helpers) and are
# exercised from the PowerShell wrapper generated by bob_worker.py as well as from
# unit tests.
# ----------------------------------------------------------------------------------

def _parse_iso_ts(raw: str) -> Optional[float]:
    """Parse an ISO-8601 timestamp to a Unix timestamp, or None."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        from datetime import datetime

        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def _rate_limit_scan_without_worker(text: str) -> str:
    """Quoted-stock strip when ``bob_worker.provider_fuel_scan_text`` cannot be imported.

    Drops a stock phrase only when it is the entire quoted span. Contractions,
    a bare ``402 Payment Required``, and ``status_code=402 "usage balance exhausted"``
    stay so a missing worker import does not hide a real provider limit.
    """
    cleaned = re.sub(r"`[^`]*`", " ", text or "")
    stock = (
        r"(?:402\s*Payment\s*Required|Payment\s*Required|usage\s+balance\s+exhausted"
        r"|NEEDS_AUTH|OUTCOME_NEEDS_AUTH)"
    )
    cleaned = re.sub(rf"(?<!\w)'{stock}'(?!\w)", " ", cleaned, flags=re.IGNORECASE)
    if re.search(r"(?i)(?:\bhttp\b|\bstatus(?:_code| code)?)\D{0,12}\b(402|429)\b", cleaned):
        return cleaned
    return re.sub(rf'"{stock}"', " ", cleaned, flags=re.IGNORECASE)


def looks_like_rate_limit(text: str | None) -> bool:
    """True when ``opencode run`` output text indicates a rate/rolling/payment limit.

    Bare ``402``/``429`` digits are not enough; they must appear with HTTP/status
    context (e.g. ``HTTP 429``, ``status 429``) to avoid false pauses from issue
    numbers, commit hashes and timings in normal output. Markdown backtick
    quotations (the worker skill documents the phrase) are not a provider limit.
    """
    if not text or not isinstance(text, str):
        return False
    # Same provenance rules as the worker hold (MRB #6231): backticks and a
    # stock phrase that is the whole quoted span are instructions. Apostrophes
    # stay. A fuel-log JSON line is scanned from its text field.
    scan = text
    for mod_name in ("bob_worker", "bob.scripts.bob_worker"):
        try:
            mod = __import__(mod_name, fromlist=["provider_fuel_scan_text"])
            scan = mod.provider_fuel_scan_text(text)
            break
        except Exception:
            continue
    else:
        scan = _rate_limit_scan_without_worker(text)
    t = scan.lower()
    if any(phrase in t for phrase in RATE_LIMIT_PHRASES):
        return True
    return bool(re.search(r"\b(http|status( code)?)\D{0,3}(402|429)\b", t, re.IGNORECASE))


def parse_reset_time(text: str | None, now: Optional[float] = None) -> Optional[float]:
    """Return the Unix timestamp when the rolling window resets, or None.

    Handles ``Retry-After`` (seconds), relative times (``resets in 5 minutes``),
    and absolute ISO-8601 timestamps (``reset-time: 2026-11-05T12:00:00Z``).
    """
    if not text or not isinstance(text, str):
        return None
    now = now if now is not None else time.time()

    # Retry-After seconds (HTTP header or inline).
    m = re.search(r"retry[\s\-]?after[:\s]*(\d+)", text, re.IGNORECASE)
    if m:
        try:
            return now + int(m.group(1))
        except (TypeError, ValueError):
            pass

    # Relative time, e.g. "resets in 5 minutes" / "try again in 1 hour".
    m = re.search(
        r"(?:resets?(?:\s+in|\s+after)?|try again in)[:\s]*(\d+(?:\.\d+)?)\s*(s|sec|seconds?|m|min|minutes?|h|hr|hours?)",
        text,
        re.IGNORECASE,
    )
    if m:
        try:
            value = float(m.group(1))
        except (TypeError, ValueError):
            value = None
        if value is not None:
            unit = m.group(2).lower()
            if unit.startswith("s"):
                delta = value
            elif unit.startswith("m"):
                delta = value * 60.0
            else:
                delta = value * 3600.0
            return now + delta

    # Absolute ISO timestamp.
    m = re.search(
        r"reset[\s\-]?time[:\s]*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if m:
        ts = _parse_iso_ts(m.group(1))
        if ts is not None:
            return ts

    return None


def _pause_path(state_dir: str | Path) -> Path:
    return Path(state_dir) / "opencode-pauses.json"


def _lock_path(state_dir: str | Path) -> Path:
    return _pause_path(state_dir).with_suffix(".json.lock")


def _acquire_process_lock(
    lock_path: Path,
    timeout: float = 10.0,
    stale_after_s: float = 30.0,
) -> Optional[int]:
    """Acquire an advisory lock file using ``os.open(O_CREAT | O_EXCL)``.

    The lock file is kept open for the lifetime of the lock; on Windows this
    prevents other processes from deleting it. Returns the file descriptor, or
    ``None`` if the lock could not be acquired within ``timeout`` seconds.
    """
    start = time.time()
    pid = os.getpid()
    lock_path = Path(lock_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{pid}:{time.time():.6f}\n".encode("utf-8"))
            except OSError:
                os.close(fd)
                try:
                    lock_path.unlink()
                except OSError:
                    pass
                return None
            return fd
        except (FileExistsError, PermissionError):
            try:
                if lock_path.is_file():
                    mtime = lock_path.stat().st_mtime
                    if time.time() - mtime > stale_after_s:
                        try:
                            lock_path.unlink()
                        except OSError:
                            pass
            except OSError:
                pass
            if time.time() - start > timeout:
                return None
            time.sleep(min(0.5, 0.05 + (time.time() - start) / 20.0))
        except OSError:
            return None


def _release_process_lock(fd: Optional[int], lock_path: Path) -> None:
    """Release a lock acquired with ``_acquire_process_lock``."""
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        lock_path.unlink()
    except OSError:
        pass


def load_opencode_pauses(state_dir: str | Path, now: Optional[float] = None) -> dict[str, float]:
    """Load non-expired pauses as ``{model_id: reset_timestamp}``.

    Expired entries are dropped silently.  Malformed files return an empty map.
    """
    now = now if now is not None else time.time()
    path = _pause_path(state_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, float] = {}
    for model_id, reset_ts in data.items():
        try:
            reset_ts = float(reset_ts)
        except (TypeError, ValueError):
            continue
        if reset_ts > now:
            out[str(model_id)] = reset_ts
    return out


def save_opencode_pauses(state_dir: str | Path, pauses: dict[str, float]) -> bool:
    """Persist the pause map atomically.

    Writes to a unique temporary file in the same directory and replaces the
    state file with ``os.replace`` so concurrent readers never see a partial
    file. Expired entries are pruned on load, not on save, so callers that pass
    an explicit ``now`` do not have their data discarded. Returns True when the
    state file was written successfully.
    """
    path = _pause_path(state_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f"{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(dict(pauses), f, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(tmp_path_str, path)
        except Exception:
            try:
                os.unlink(tmp_path_str)
            except OSError:
                pass
            raise
        return True
    except Exception:
        return False


def record_opencode_pause(
    state_dir: str | Path,
    model_id: str,
    output_text: str | None,
    *,
    now: Optional[float] = None,
    default_pause_s: float = DEFAULT_PAUSE_S,
    lock_timeout_s: float = 10.0,
) -> Optional[float]:
    """Record (or extend) a pause for ``model_id`` after a rate/rolling limit hit.

    Uses the reset time parsed from ``output_text`` if present; otherwise falls
    back to ``default_pause_s``.  The full load-modify-write is serialised with
    a process-scoped lock so concurrent seats sharing ``state_dir`` cannot
    overwrite one another's updates. Returns the reset timestamp, or ``None``
    when the pause could not be persisted (including lock timeout).
    """
    now = now if now is not None else time.time()
    if not model_id:
        return None
    reset_ts = parse_reset_time(output_text, now=now)
    if reset_ts is None:
        reset_ts = now + float(default_pause_s)

    lock_path = _lock_path(state_dir)
    fd = _acquire_process_lock(lock_path, timeout=lock_timeout_s)
    if fd is None:
        return None
    try:
        pauses = load_opencode_pauses(state_dir, now=now)
        existing = pauses.get(model_id)
        if existing is None or reset_ts > existing:
            pauses[model_id] = reset_ts
        if save_opencode_pauses(state_dir, pauses):
            return reset_ts
        return None
    finally:
        _release_process_lock(fd, lock_path)


def is_opencode_model_paused(
    model_id: str | None, state_dir: str | Path, now: Optional[float] = None
) -> bool:
    """True when ``model_id`` is currently paused."""
    now = now if now is not None else time.time()
    if not model_id:
        return False
    pauses = load_opencode_pauses(state_dir, now=now)
    target = str(model_id).lower()
    return any(str(k).lower() == target for k in pauses)


def opencode_pauses_state_dir(env: Optional[dict] = None) -> Path:
    """Default directory for the worker's OpenCode pause JSON file."""
    env = env if env is not None else {}
    base = env.get("BOB_OPENCODE_PAUSE_STATE_DIR") or env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Bobiverse" / "worker" / "state"


def _cli(argv: list[str] | None = None) -> int:
    """Command-line entry point used by the worker wrapper."""
    import argparse

    parser = argparse.ArgumentParser(prog="opencode_fuel")
    subs = parser.add_subparsers(dest="command")
    record = subs.add_parser("record-pause", help="Record a model pause from output on stdin")
    record.add_argument("--dir", required=True, help="Pause-state directory")
    record.add_argument("--model", required=True, help="Model id that hit the limit")
    args = parser.parse_args(argv)
    if args.command == "record-pause":
        output_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        reset_ts = record_opencode_pause(args.dir, args.model, output_text)
        return 0 if reset_ts is not None else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
