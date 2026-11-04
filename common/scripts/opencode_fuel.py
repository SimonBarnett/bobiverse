"""OpenCode fuel helpers for Bob Fleet worker seats.

OpenCode Go has per-model monthly dollar allowances with rolling caps.  There is no
public remaining-quota API, so we estimate remaining % from local ``opencode stats``
cost vs the known caps.  ``opencode-free`` is a separate fuel id for the no-account
free models.

All functions are pure / testable and never touch credentials.
"""
from __future__ import annotations

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


def _free_models_available(stats: dict) -> bool:
    """True when the stats doc reports at least one free model as available."""
    free = stats.get("free_models") if isinstance(stats.get("free_models"), (list, tuple)) else None
    if free is None:
        # No data: free tier availability is unknown, not assumed.
        return False
    return any(str(m).strip() in OPENCODE_FREE_MODELS for m in free)


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
