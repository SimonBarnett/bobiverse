"""OpenCode fuel helpers for Bob Fleet worker seats.

OpenCode Go has per-model monthly dollar allowances with rolling caps.  There is no
public remaining-quota API, so we estimate remaining % from local ``opencode stats``
cost vs the known caps.  ``opencode-free`` is a separate fuel id for the no-account
free models.

All functions are pure / testable and never touch credentials.
"""
from __future__ import annotations

import json
import re
from typing import Optional

# Fuel ids published to the digest webhook.
FUEL_ID_FREE = "opencode-free"
FUEL_ID_GO = "opencode-go"

# Provider prefix used by the opencode CLI ``-m`` flag.
PROVIDER_FREE = "opencode-free"
PROVIDER_GO = "opencode-go"

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
CAP_WINDOWS: dict[str, float] = {
    "5h": 0.20,
    "week": 0.50,
    "month": 1.00,
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
    # All three rolling windows are required; a failed stats call must not be
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


def _free_models_available(stats: dict) -> bool:
    """True when the stats doc reports at least one free model as available."""
    free = stats.get("free_models") if isinstance(stats.get("free_models"), (list, tuple)) else None
    if free is None:
        # No data: free tier availability is unknown, not assumed.
        return False
    return any(str(m).strip() in OPENCODE_FREE_MODELS for m in free)


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


def _looks_like_models_list(text: str) -> bool:
    """True when text looks like plain ``opencode models`` output.

    Each non-empty line should be a ``provider/model`` id and there must be no
    stats table markers.
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
    return all(model_line_re.match(ln) for ln in lines)


def parse_opencode_models_text(text: str | None) -> list[str]:
    """Translate plain ``opencode models`` output to a list of known free slugs.

    Returns recognised free model slugs (e.g. ``beam-free``) found in the
    catalogue output, which is one ``provider/model`` id per line.
    """
    if not text or not isinstance(text, str):
        return []
    slugs: list[str] = []
    for line in _strip_ansi(text).splitlines():
        line = line.strip()
        if not line or "/" not in line:
            continue
        provider = line.split("/")[0]
        slug = line.split("/")[-1]
        if provider == PROVIDER_FREE and slug in OPENCODE_FREE_MODELS:
            slugs.append(slug)
    return slugs


def parse_opencode_stats_text(text: str | None) -> dict:
    """Translate plain ``opencode stats`` table output to the fuel helper shape.

    Reads the ``Total Cost`` row and per-model ``Cost`` rows from the box-drawing
    table emitted by ``opencode stats --models``.  Returns
    ``{"costs": {"model": usd, ...}, "free_models": [...], "total_cost": usd_or_none,
    "parse_success": bool}``.  When parsing fails the function returns empty
    containers, ``None`` totals and ``parse_success=False`` rather than guessing.
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
    model_re = re.compile(r"(opencode-(?:go|free)/[\w.\-]+)")
    cost_re = re.compile(r"Cost\s+\$?([\d,]+\.\d+)", re.IGNORECASE)
    total_re = re.compile(r"Total Cost\s+\$?([\d,]+\.\d+)", re.IGNORECASE)

    # First pass: locate sections and total cost.
    for line in lines:
        upper = line.upper()
        if "COST & TOKENS" in upper:
            in_cost_tokens = True
            in_model_usage = False
            saw_table_marker = True
            continue
        if "MODEL USAGE" in upper:
            in_cost_tokens = False
            in_model_usage = True
            saw_table_marker = True
            continue
        if "TOOL USAGE" in upper or "SESSIONS" in upper:
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
        if "MODEL USAGE" in upper:
            in_model_usage = True
            current_model = None
            continue
        if "TOOL USAGE" in upper or "COST & TOKENS" in upper or "OVERVIEW" in upper:
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
                elif provider == PROVIDER_FREE and slug in OPENCODE_FREE_MODELS:
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
    Unknown shapes return empty containers and ``parse_success=False`` rather than
    raising.
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
            if provider == PROVIDER_FREE and slug in OPENCODE_FREE_MODELS:
                free_models.append(slug)

    parse_success = bool(costs or free_models or models is not None)
    return {"costs": costs, "free_models": free_models, "parse_success": parse_success}


def fuel_from_stats(stats: dict | None) -> dict:
    """Build digest fuel numbers from an OpenCode stats document.

    The returned dict contains the two digest fuel ids (``opencode-free``,
    ``opencode-go``) plus a per-model breakdown under ``models``.  ``None`` means
    unknown (handled like other digest pools), ``0`` means exhausted.

    ``stats`` shape (kept minimal and CLI-output-agnostic):

        {
          "costs": {"glm-5.3": 7.50, "kimi-k2.7-code": 12.00, ...},
          "free_models": ["beam-free", "iceman-contributor-free"]
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
    return {
        FUEL_ID_FREE: free_remaining,
        FUEL_ID_GO: go_remaining,
        "models": go_by_model,
    }


def fuel_from_windowed_stats(windowed: dict[str, dict] | None) -> dict:
    """Build digest fuel numbers from rolling cap windows.

    ``windowed`` maps window names (``5h``, ``week``, ``month``) to stats docs
    produced by ``opencode stats --days <N>``.  Per-model remaining % is driven
    by the most-utilised window, because Go caps are rolling and a model is
    exhausted when any window limit is hit.
    """
    windowed = windowed if isinstance(windowed, dict) else {}
    go_by_model = _go_models_remaining_for_windows(windowed)
    go_remaining: Optional[int] = None
    if go_by_model:
        go_remaining = max(go_by_model.values())
    free_remaining: Optional[int] = None
    if any(_free_models_available(windowed.get(w) or {}) for w in CAP_WINDOWS):
        free_remaining = 100
    return {
        FUEL_ID_FREE: free_remaining,
        FUEL_ID_GO: go_remaining,
        "models": go_by_model,
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
    if preferred.startswith(f"{PROVIDER_FREE}/"):
        preferred = preferred[len(f"{PROVIDER_FREE}/") :]

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
