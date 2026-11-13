"""FR #7084: per-CLI minimum start models and digest / offer helpers.

Values come from configuration (JSON / env). This module does not invent model ids.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

WORKER_CLIS = ("grok", "cursor", "aider", "opencode")
TIER_RANK = {
    "min": 0,
    "minimum": 0,
    "cheap": 0,
    "medium": 1,
    "max": 2,
    "premium": 2,
    "high": 2,
}
DEFAULT_JOB_TIER = "min"
ENV_CONFIG_PATH = "BOB_WORKER_START_MODEL_FILE"
ENV_CONFIG_JSON = "BOB_WORKER_START_MODEL_JSON"
ENV_ACTUAL_MODEL = "BOB_WORKER_ACTUAL_MODEL"


def _cli(kind: str) -> str:
    return str(kind or "").strip().lower()


def _tier_rank(name: str) -> int:
    return TIER_RANK.get(str(name or "").strip().lower(), TIER_RANK[DEFAULT_JOB_TIER])


def load_worker_start_config(
    raw: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Parse operator config. Missing keys stay empty; never invent model names."""
    e = os.environ if env is None else env
    data: dict[str, Any] = {}
    blob = str((e or {}).get(ENV_CONFIG_JSON) or "").strip()
    if blob:
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, dict):
                data.update(parsed)
        except json.JSONDecodeError:
            pass
    src = path
    if src is None:
        p = str((e or {}).get(ENV_CONFIG_PATH) or "").strip()
        if p:
            src = Path(p)
    if src is not None and src.is_file():
        try:
            file_data = json.loads(src.read_text(encoding="utf-8"))
            if isinstance(file_data, dict):
                data.update(file_data)
        except (OSError, json.JSONDecodeError, UnicodeError):
            pass
    if isinstance(raw, dict):
        data.update(raw)
    models = data.get("workerStartModels")
    if not isinstance(models, dict):
        models = {}
    tiers = data.get("workerModelCostTiers")
    if not isinstance(tiers, dict):
        tiers = {}
    jobs = data.get("jobRequiredModelTier")
    if not isinstance(jobs, dict):
        jobs = {}
    return {
        "workerStartModels": {k: str(models.get(k) or "").strip() for k in WORKER_CLIS},
        "workerModelCostTiers": {str(k).strip(): str(v).strip().lower() for k, v in tiers.items() if str(k).strip()},
        "jobRequiredModelTier": {
            str(k).strip().upper(): str(v).strip().lower() or DEFAULT_JOB_TIER
            for k, v in jobs.items()
            if str(k).strip()
        },
    }


def configured_start_model(cli: str, cfg: dict[str, Any] | None) -> str:
    models = (cfg or {}).get("workerStartModels") or {}
    return str(models.get(_cli(cli)) or "").strip()


def model_cost_tier(model: str, cfg: dict[str, Any] | None) -> str:
    mid = str(model or "").strip()
    if not mid:
        return DEFAULT_JOB_TIER
    tiers = (cfg or {}).get("workerModelCostTiers") or {}
    return str(tiers.get(mid) or DEFAULT_JOB_TIER).strip().lower() or DEFAULT_JOB_TIER


def job_required_tier(job_task: str, cfg: dict[str, Any] | None) -> str:
    jobs = (cfg or {}).get("jobRequiredModelTier") or {}
    key = str(job_task or "").strip().upper()
    return str(jobs.get(key) or DEFAULT_JOB_TIER).strip().lower() or DEFAULT_JOB_TIER


def model_mismatch(actual: str, configured: str) -> bool:
    a = str(actual or "").strip()
    c = str(configured or "").strip()
    if not c:
        return False
    if not a:
        return True
    return a.lower() != c.lower()


def launch_argv_with_model(kind: str, argv: list[str], model: str) -> list[str]:
    """Insert ``--model <configured>`` after the executable for grok/cursor/aider/opencode.

    Does not invent a model: empty ``model`` leaves argv unchanged (no premium fallback).
    """
    args = [str(a) for a in (argv or [])]
    mid = str(model or "").strip()
    cli = _cli(kind)
    if not mid or cli not in WORKER_CLIS or not args:
        return args
    if "--model" in args:
        i = args.index("--model")
        if i + 1 < len(args):
            args[i + 1] = mid
        else:
            args.append(mid)
        return args
    # Cursor plan launcher may already pass --model auto in a PowerShell string; argv is ps1.
    args.insert(1, mid)
    args.insert(1, "--model")
    return args


def actual_start_model(*, env: dict[str, str] | None = None, argv: list[str] | None = None) -> str:
    """Process/session actual model: env stamp, else last ``--model`` on the launch argv."""
    e = os.environ if env is None else env
    stamped = str((e or {}).get(ENV_ACTUAL_MODEL) or "").strip()
    if stamped:
        return stamped
    args = [str(a) for a in (argv or [])]
    if "--model" in args:
        i = args.index("--model")
        if i + 1 < len(args):
            got = str(args[i + 1]).strip()
            if got and got.lower() != "auto":
                return got
    return ""


def digest_seat_model_fields(
    *,
    cli: str,
    actual: str,
    cfg: dict[str, Any] | None,
    state: str = "idle",
) -> dict[str, Any]:
    """Fields for held / starting / idle / busy seats (FR #7084)."""
    configured = configured_start_model(cli, cfg)
    act = str(actual or "").strip()
    mismatch = model_mismatch(act, configured)
    return {
        "kind": _cli(cli),
        "start_model": act,
        "configured_model": configured,
        "model_mismatch": mismatch,
        "cost_tier": model_cost_tier(act or configured, cfg),
        "state": str(state or "idle").strip().lower() or "idle",
    }


def seat_allows_job(fields: dict[str, Any] | None, job_task: str, cfg: dict[str, Any] | None) -> bool:
    """False when mismatch or the running model tier is below the job requirement."""
    f = fields or {}
    if bool(f.get("model_mismatch")):
        return False
    need = _tier_rank(job_required_tier(job_task, cfg))
    have = _tier_rank(str(f.get("cost_tier") or DEFAULT_JOB_TIER))
    return have >= need


def pick_cheapest_qualifying_seats(
    seats: list[dict[str, Any]],
    job_task: str,
    cfg: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Seats that may take ``job_task``, cheapest cost_tier first. Empty => stay queued."""
    ok = [s for s in seats if seat_allows_job(s, job_task, cfg)]
    ok.sort(key=lambda s: (_tier_rank(str(s.get("cost_tier") or DEFAULT_JOB_TIER)), str(s.get("nick") or "")))
    return ok
