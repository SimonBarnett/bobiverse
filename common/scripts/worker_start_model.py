"""FR #7084: per-CLI minimum start models and digest / offer helpers.

Values come from configuration (JSON / env). This module does not invent model ids.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

WORKER_CLIS = ("grok", "cursor", "aider", "opencode")
DEFAULT_EFFORT = "low"
VALID_EFFORTS = ("low", "medium", "high")
DEFAULT_OPENCODE_FREE = "opencode/deepseek-v4.1-flash-free"
ENV_ACTUAL_EFFORT = "BOB_WORKER_ACTUAL_EFFORT"
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

    def _merge_file(src: Path | None) -> None:
        if src is None or not src.is_file():
            return
        try:
            file_data = json.loads(src.read_text(encoding="utf-8"))
            if isinstance(file_data, dict):
                data.update(file_data)
        except (OSError, json.JSONDecodeError, UnicodeError):
            pass

    # Defaults then LOCALAPPDATA tray-models.json (same order as BobTray FR #6429).
    root = str((e or {}).get("BOB_INSTALL_ROOT") or (e or {}).get("BOBIVERSE_INSTALL_ROOT") or "").strip()
    if root:
        rp = Path(root)
        for rel in (
            Path("tray") / "config" / "default.json",
            Path("bob") / "tray" / "config" / "default.json",
            Path("config") / "default.json",
        ):
            _merge_file(rp / rel)
    localapp = str((e or {}).get("LOCALAPPDATA") or "").strip()
    if localapp:
        _merge_file(Path(localapp) / "Bobiverse" / "tray-models.json")
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
    _merge_file(src)
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
    efforts = data.get("workerStartEffort")
    if not isinstance(efforts, dict):
        efforts = {}
    extra_models = data.get("models")
    if not isinstance(extra_models, dict):
        extra_models = {}
    return {
        "workerStartModels": {k: str(models.get(k) or "").strip() for k in WORKER_CLIS},
        "workerStartEffort": {
            k: normalize_effort(efforts.get(k) or efforts.get("default") or "")
            for k in WORKER_CLIS
        },
        "models": {
            "opencodeFree": str(extra_models.get("opencodeFree") or "").strip(),
            "opencodePaid": str(extra_models.get("opencodePaid") or "").strip(),
        },
        "workerModelCostTiers": {str(k).strip(): str(v).strip().lower() for k, v in tiers.items() if str(k).strip()},
        "jobRequiredModelTier": {
            str(k).strip().upper(): str(v).strip().lower() or DEFAULT_JOB_TIER
            for k, v in jobs.items()
            if str(k).strip()
        },
    }


def normalize_effort(raw: object) -> str:
    s = str(raw or "").strip().lower()
    if s in VALID_EFFORTS:
        return s
    return ""


def configured_start_effort(cli: str, cfg: dict[str, Any] | None) -> str:
    """Saved effort for a CLI, else lowest (never high)."""
    efforts = (cfg or {}).get("workerStartEffort") or {}
    got = normalize_effort(efforts.get(_cli(cli)))
    return got or DEFAULT_EFFORT


def default_opencode_free_model(cfg: dict[str, Any] | None = None) -> str:
    models = (cfg or {}).get("models") or {}
    got = str(models.get("opencodeFree") or "").strip()
    return got or DEFAULT_OPENCODE_FREE


def opencode_is_go_or_paid(model: str) -> bool:
    s = str(model or "").strip().lower()
    if not s:
        return False
    if s.startswith("opencode-go/") or "/opencode-go/" in s:
        return True
    if "v4-pro" in s or s.endswith("-pro"):
        return True
    return False


def tray_models_path(*, env: dict[str, str] | None = None) -> Path:
    e = os.environ if env is None else env
    local = str((e or {}).get("LOCALAPPDATA") or "").strip()
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return Path(local) / "Bobiverse" / "tray-models.json"


def save_worker_start_settings(
    *,
    env: dict[str, str] | None = None,
    path: Path | None = None,
    models: dict[str, str] | None = None,
    effort: dict[str, str] | None = None,
) -> Path:
    """Merge into tray-models.json (FR #7187). Never wipe unrelated keys."""
    p = Path(path) if path else tray_models_path(env=env)
    data: dict[str, Any] = {}
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError, UnicodeError):
            data = {}
    if models:
        cur = data.get("workerStartModels")
        if not isinstance(cur, dict):
            cur = {}
        for k, v in models.items():
            cli = _cli(k)
            if cli in WORKER_CLIS:
                cur[cli] = str(v or "").strip()
        data["workerStartModels"] = cur
    if effort:
        cur_e = data.get("workerStartEffort")
        if not isinstance(cur_e, dict):
            cur_e = {}
        for k, v in effort.items():
            cli = _cli(k)
            if cli in WORKER_CLIS:
                cur_e[cli] = normalize_effort(v) or DEFAULT_EFFORT
        data["workerStartEffort"] = cur_e
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p


def write_launch_record(
    run_dir: str | Path,
    *,
    kind: str,
    model: str,
    effort: str,
    argv: list[str] | None = None,
) -> Path:
    """Seat launch record for the tray (model + effort actually passed)."""
    rd = Path(run_dir)
    rd.mkdir(parents=True, exist_ok=True)
    rec = {
        "kind": _cli(kind),
        "model": str(model or "").strip(),
        "effort": normalize_effort(effort) or DEFAULT_EFFORT,
        "argv": [str(a) for a in (argv or [])][:24],
    }
    dest = rd / "launch-record.json"
    dest.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return dest


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


def launch_argv_with_effort(kind: str, argv: list[str], effort: str | None = None) -> list[str]:
    """Grok: pass ``--reasoning-effort`` (default low). Other CLIs unchanged."""
    args = [str(a) for a in (argv or [])]
    if _cli(kind) != "grok" or not args:
        return args
    level = normalize_effort(effort) or DEFAULT_EFFORT
    flag = "--reasoning-effort"
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            args[i + 1] = level
        else:
            args.append(level)
        return args
    args.insert(1, level)
    args.insert(1, flag)
    return args


def _model_from_argv(args: list[str]) -> str:
    if "--model" not in args:
        return ""
    i = args.index("--model")
    if i + 1 >= len(args):
        return ""
    got = str(args[i + 1]).strip().strip("'\"")
    if got and got.lower() != "auto":
        return got
    return ""


def _model_from_script_text(text: str) -> str:
    """Last ``--model <id>`` in a launcher script (Cursor PowerShell). Never treats ``auto`` as actual."""
    found = ""
    for m in re.finditer(r"--model(?:\s+|=)(?P<q>['\"]?)(?P<id>[^\s'\"]+)(?P=q)", str(text or "")):
        got = str(m.group("id") or "").strip()
        if got and got.lower() != "auto":
            found = got
    return found


def actual_start_model(
    *,
    env: dict[str, str] | None = None,
    argv: list[str] | None = None,
    script_text: str = "",
) -> str:
    """Process/session actual model: env stamp, else launch argv / launcher script ``--model``."""
    e = os.environ if env is None else env
    stamped = str((e or {}).get(ENV_ACTUAL_MODEL) or "").strip()
    if stamped:
        return stamped
    got = _model_from_argv([str(a) for a in (argv or [])])
    if got:
        return got
    return _model_from_script_text(script_text)


def actual_from_launch_spec(kind: str, spec: Any, *, env: dict[str, str] | None = None) -> str:
    """Actual start model as launched (argv or Cursor/OpenCode script), not config-only."""
    argv = list(getattr(spec, "argv", None) or [])
    files = getattr(spec, "files", None) or {}
    blob = "\n".join(str(v) for v in (files.values() if isinstance(files, dict) else []))
    return actual_start_model(env=env if env is not None else {}, argv=argv, script_text=blob)


def digest_seat_model_fields(
    *,
    cli: str,
    actual: str,
    cfg: dict[str, Any] | None,
    state: str = "idle",
    effort: str = "",
) -> dict[str, Any]:
    """Fields for held / starting / idle / busy seats (FR #7084 / #7187)."""
    configured = configured_start_model(cli, cfg)
    act = str(actual or "").strip()
    mismatch = model_mismatch(act, configured)
    return {
        "kind": _cli(cli),
        "start_model": act,
        "configured_model": configured,
        "model_mismatch": mismatch,
        "cost_tier": model_cost_tier(act or configured, cfg),
        "start_effort": normalize_effort(effort) or configured_start_effort(cli, cfg),
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
