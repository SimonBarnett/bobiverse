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
# FR #9258: Si — effort is high|medium|low only (xhigh is invalid → fallback low).
VALID_EFFORTS = ("low", "medium", "high")
DEFAULT_CONTEXT = ""  # Grok CLI default when no flag is available
# FR #9258: context is 256|500 only, and only for Grok.
VALID_CONTEXTS = ("256", "500")
# Verified on flamingo 2026-11-23: grok 1.0.92 --help has --reasoning-effort / --effort
# and no context/window flag. Seat still starts; status not-passed: unsupported-by-cli.
GROK_CONTEXT_CLI_FLAG: str | None = None
GROK_CONTEXT_CLI_VERIFIED = "1.0.92"
DEFAULT_OPENCODE_FREE = "opencode/deepseek-v4.1-flash-free"
DEFAULT_OPENCODE_PAID = "opencode-go/deepseek-v4-pro"
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
# FR #8159: per-CLI env pins (Si tray click / operator). Precedence over tray JSON.
ENV_MODEL_PINS = {
    "grok": ("BOB_GROK_MODEL", "BOB_WORKER_MODEL"),
    "cursor": ("BOB_CURSOR_MODEL", "BOB_WORKER_MODEL"),
    "aider": ("BOB_AIDER_MODEL", "BOB_WORKER_MODEL"),
    "opencode": ("BOB_OPENCODE_MODEL", "BOB_WORKER_MODEL"),
}
ENV_PAUSE_FALLBACK = "BOB_OPENCODE_PAUSE_FALLBACK"


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
    # BOB-15 / FR #8711: webhook overlay above tray/defaults, below env JSON / explicit file / raw.
    settings_source: dict[str, str] = {k: "local" for k in WORKER_CLIS}
    settings_fallback: dict[str, str] = {}
    try:
        import models_webhook as _mw

        wh_doc = _mw.fetch_models_webhook(env=e)
    except Exception:
        wh_doc = None
        settings_fallback["webhook"] = "import_or_fetch_failed"
    if wh_doc is None and "webhook" not in settings_fallback:
        settings_fallback["webhook"] = "unavailable"
    if isinstance(wh_doc, dict):
        w_models = data.get("workerStartModels")
        if not isinstance(w_models, dict):
            w_models = {}
        w_efforts = data.get("workerStartEffort")
        if not isinstance(w_efforts, dict):
            w_efforts = {}
        w_contexts = data.get("workerStartContext")
        if not isinstance(w_contexts, dict):
            w_contexts = {}
        extra = data.get("models")
        if not isinstance(extra, dict):
            extra = {}
        for cli in WORKER_CLIS:
            slot = None
            if cli == "opencode":
                # Prefer paid Opencode row for workerStartModels; free slot fills models.opencodeFree.
                free = _mw.webhook_settings_for_cli("opencode", opencode_slot="free", doc=wh_doc, env=e)
                paid = _mw.webhook_settings_for_cli("opencode", opencode_slot="paid", doc=wh_doc, env=e)
                if free.get("model"):
                    extra["opencodeFree"] = free["model"]
                    settings_source["opencode"] = "webhook"
                if paid.get("model"):
                    w_models["opencode"] = paid["model"]
                    if paid.get("effort"):
                        w_efforts["opencode"] = paid["effort"]
                    if paid.get("context"):
                        w_contexts["opencode"] = paid["context"]
                    settings_source["opencode"] = "webhook"
                elif free.get("model"):
                    w_models["opencode"] = free["model"]
                    if free.get("effort"):
                        w_efforts["opencode"] = free["effort"]
                    if free.get("context"):
                        w_contexts["opencode"] = free["context"]
                continue
            got = _mw.webhook_settings_for_cli(cli, doc=wh_doc, env=e)
            if got.get("model"):
                w_models[cli] = got["model"]
                settings_source[cli] = "webhook"
            if got.get("effort"):
                w_efforts[cli] = got["effort"]
            if got.get("context"):
                w_contexts[cli] = got["context"]
        data["workerStartModels"] = w_models
        data["workerStartEffort"] = w_efforts
        data["workerStartContext"] = w_contexts
        data["models"] = extra
    data["_settings_source"] = settings_source
    data["_settings_fallback"] = settings_fallback
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
    contexts = data.get("workerStartContext")
    if not isinstance(contexts, dict):
        contexts = {}
    extra_models = data.get("models")
    if not isinstance(extra_models, dict):
        extra_models = {}
    src_map = data.get("_settings_source")
    if not isinstance(src_map, dict):
        src_map = {k: "local" for k in WORKER_CLIS}
    # Env pin marks settings_source for that CLI (inline; env_model_pin is defined below).
    for cli in WORKER_CLIS:
        for key in ENV_MODEL_PINS.get(cli, ()):
            got = str((e or {}).get(key) or "").strip().strip("'\"")
            if got and got.lower() not in ("auto", "unknown", "none", "null") and "$" not in got:
                src_map[cli] = "env-pin"
                break
    fb = data.get("_settings_fallback")
    if not isinstance(fb, dict):
        fb = {}
    return {
        "workerStartModels": {k: str(models.get(k) or "").strip() for k in WORKER_CLIS},
        "workerStartEffort": {
            "grok": normalize_effort(efforts.get("grok") or efforts.get("default") or ""),
            **{k: "" for k in WORKER_CLIS if k != "grok"},
        },
        "workerStartContext": {
            "grok": normalize_context(contexts.get("grok") or ""),
            **{k: "" for k in WORKER_CLIS if k != "grok"},
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
        "settings_source": {k: str(src_map.get(k) or "local") for k in WORKER_CLIS},
        "settings_fallback": {str(k): str(v) for k, v in fb.items()},
    }


def normalize_effort(raw: object) -> str:
    s = str(raw or "").strip().lower()
    if s in VALID_EFFORTS:
        return s
    return ""


def normalize_context(raw: object) -> str:
    """FR #9258: only ``256`` or ``500`` (as strings)."""
    s = str(raw or "").strip()
    if s in VALID_CONTEXTS:
        return s
    return ""


def configured_start_effort(
    cli: str,
    cfg: dict[str, Any] | None,
    env: dict[str, str] | None = None,
) -> str:
    """Saved effort for Grok, else lowest. Non-Grok: empty (not applicable).

    FR #9586: child env ``BOB_GROK_EFFORT`` / ``BOB_WORKER_START_EFFORT`` from
    Weights GET ``/bob/v1/models`` wins over tray-models.json.
    """
    if _cli(cli) != "grok":
        return ""
    e = os.environ if env is None else env
    for key in ("BOB_GROK_EFFORT", "BOB_WORKER_START_EFFORT"):
        pinned = normalize_effort((e or {}).get(key))
        if pinned:
            return pinned
    efforts = (cfg or {}).get("workerStartEffort") or {}
    got = normalize_effort(efforts.get("grok"))
    return got or DEFAULT_EFFORT


def configured_start_context(
    cli: str,
    cfg: dict[str, Any] | None,
    env: dict[str, str] | None = None,
) -> str:
    """Saved context for Grok only (256|500); else empty.

    FR #9586: child env ``BOB_GROK_CONTEXT`` / ``BOB_WORKER_START_CONTEXT`` wins.
    """
    if _cli(cli) != "grok":
        return ""
    e = os.environ if env is None else env
    for key in ("BOB_GROK_CONTEXT", "BOB_WORKER_START_CONTEXT"):
        pinned = normalize_context((e or {}).get(key))
        if pinned:
            return pinned
    contexts = (cfg or {}).get("workerStartContext") or {}
    return normalize_context(contexts.get("grok"))


def default_opencode_free_model(cfg: dict[str, Any] | None = None) -> str:
    models = (cfg or {}).get("models") or {}
    got = str(models.get("opencodeFree") or "").strip()
    return got or DEFAULT_OPENCODE_FREE


def default_opencode_paid_model(cfg: dict[str, Any] | None = None) -> str:
    """Tray ``models.opencodePaid`` slot (FR #8454). Never a third invented id."""
    models = (cfg or {}).get("models") or {}
    got = str(models.get("opencodePaid") or "").strip()
    return got or DEFAULT_OPENCODE_PAID


def opencode_is_go_or_paid(model: str) -> bool:
    s = str(model or "").strip().lower()
    if not s:
        return False
    if s.startswith("opencode-go/") or "/opencode-go/" in s:
        return True
    if "v4-pro" in s or s.endswith("-pro"):
        return True
    return False


def start_model_review_class(model: str) -> str:
    """FR #7888: MRB class of the launched start_model only.

    ``paid`` is an OpenCode Go / pro id. ``free`` is a free OpenCode id.
    ``unknown`` is missing, empty, or an unexpanded ``$`` template (fail safe).
    ``other`` is a concrete non-OpenCode id (Grok, Cursor). Configured model
    and published cost_tier are not consulted.
    """
    raw = str(model or "").strip().strip("'\"")
    if not raw or "$" in raw:
        return "unknown"
    low = raw.lower()
    if low in ("auto", "unknown", "none", "null"):
        return "unknown"
    if low.endswith("-free") or "flash-free" in low:
        return "free"
    if low.startswith("opencode/") and "opencode-go/" not in low:
        return "free"
    if opencode_is_go_or_paid(raw):
        return "paid"
    return "other"


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
    context: dict[str, str] | None = None,
) -> Path:
    """Merge into tray-models.json (FR #7187 / #9258). Never wipe unrelated keys.

    FR #9258: context and effort are Grok-only — non-Grok values are dropped on write.
    """
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
    if effort is not None:
        cur_e = data.get("workerStartEffort")
        if not isinstance(cur_e, dict):
            cur_e = {}
        for k, v in effort.items():
            cli = _cli(k)
            if cli == "grok":
                cur_e["grok"] = normalize_effort(v) or DEFAULT_EFFORT
            elif cli in WORKER_CLIS:
                cur_e[cli] = ""
        # Drop any leftover non-Grok efforts on write.
        for cli in WORKER_CLIS:
            if cli != "grok":
                cur_e[cli] = ""
        data["workerStartEffort"] = cur_e
    if context is not None:
        cur_c = data.get("workerStartContext")
        if not isinstance(cur_c, dict):
            cur_c = {}
        for k, v in context.items():
            cli = _cli(k)
            if cli == "grok":
                cur_c["grok"] = normalize_context(v)
            elif cli in WORKER_CLIS:
                cur_c[cli] = ""
        for cli in WORKER_CLIS:
            if cli != "grok":
                cur_c[cli] = ""
        data["workerStartContext"] = cur_c
    elif "workerStartContext" in data and isinstance(data.get("workerStartContext"), dict):
        # Even when context= not passed, scrub non-Grok on any settings write that
        # also touches effort/models (callers that only save models still scrub below).
        pass
    # Always scrub non-Grok context/effort maps when present.
    for key in ("workerStartEffort", "workerStartContext"):
        block = data.get(key)
        if isinstance(block, dict):
            for cli in WORKER_CLIS:
                if cli != "grok":
                    block[cli] = ""
            data[key] = block
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
    context: str = "",
    settings_source: str = "",
    cli_settings_args: list[str] | None = None,
    setting_status: dict[str, str] | None = None,
) -> Path:
    """Seat launch record for the tray (model + effort actually passed)."""
    rd = Path(run_dir)
    rd.mkdir(parents=True, exist_ok=True)
    rec = {
        "kind": _cli(kind),
        "model": str(model or "").strip(),
        "effort": normalize_effort(effort) or DEFAULT_EFFORT,
        "context": str(context or "").strip(),
        "settings_source": str(settings_source or "").strip(),
        "argv": [str(a) for a in (argv or [])][:24],
        "cli_settings_args": [str(a) for a in (cli_settings_args or [])][:24],
        "setting_status": {str(k): str(v) for k, v in (setting_status or {}).items()},
    }
    dest = rd / "launch-record.json"
    dest.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return dest


def configured_start_model(cli: str, cfg: dict[str, Any] | None) -> str:
    """Tray/config workerStartModels entry only (not env pin)."""
    models = (cfg or {}).get("workerStartModels") or {}
    return str(models.get(_cli(cli)) or "").strip()


def env_model_pin(kind: str, env: dict[str, str] | None = None) -> str:
    """FR #8159: operator/Si env pin for this seat kind, if any."""
    e = os.environ if env is None else env
    for key in ENV_MODEL_PINS.get(_cli(kind), ()):
        got = concrete_model_id((e or {}).get(key))
        if got:
            return got
    return ""


def launch_selected_model(
    kind: str,
    cfg: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """FR #8159: model the seat was launched for.

    Precedence matches selection: env pin, then tray `workerStartModels`, then
    (OpenCode only) free default. An env or tray pin from Si's click counts as
    configured for digest / mismatch.
    """
    pinned = env_model_pin(kind, env)
    if pinned:
        return pinned
    tray = configured_start_model(kind, cfg)
    if tray:
        return tray
    if _cli(kind) == "opencode":
        return default_opencode_free_model(cfg)
    return ""


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


def model_mismatch_reason(
    actual: str,
    selected: str,
    *,
    env: dict[str, str] | None = None,
) -> str:
    """FR #8159: empty when match; else paused|unavailable|mismatch.

    `selected` is `launch_selected_model` (env/tray/config), not tray-only.
    """
    a = concrete_model_id(actual) or str(actual or "").strip()
    c = concrete_model_id(selected) or str(selected or "").strip()
    if not c:
        return ""
    if a and a.lower() == c.lower():
        return ""
    e = os.environ if env is None else env
    flag = str((e or {}).get(ENV_PAUSE_FALLBACK) or "").strip().lower()
    if flag in ("1", "true", "yes"):
        return "paused"
    if not a or a.lower() in ("unknown", "none", "null"):
        return "unavailable"
    return "mismatch"


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




_context_intake_last = 0.0


def _warn_settings(msg: str) -> None:
    import sys

    try:
        sys.stderr.write(f"WARN FR #9258 {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


def _file_grok_context_unsupported_intake() -> bool:
    """Deduped intake when Grok context is requested but CLI has no flag (1.0.92)."""
    global _context_intake_last
    import time

    now = time.time()
    if now - _context_intake_last < 3600.0:
        return False
    _context_intake_last = now
    try:
        import runtime_failure

        runtime_failure.report_message(
            "bob-worker",
            (
                "Grok context requested but grok CLI has no context flag "
                f"(verified {GROK_CONTEXT_CLI_VERIFIED}; GROK_CONTEXT_CLI_FLAG=None). "
                "Seat starts without context argv (FR #9258)."
            ),
            site="grok-context-unsupported-by-cli",
        )
        return True
    except Exception:
        _warn_settings("context unsupported-by-cli (intake helper unavailable)")
        return False


def cli_settings_args(
    kind: str,
    *,
    model: str = "",
    effort: str = "",
    context: str = "",
    mode: str = "agent",
) -> tuple[list[str], dict[str, str]]:
    """BOB-15 / FR #9258: capability-aware setting argv + per-setting status.

    Status values: ``passed``, ``not-passed: invalid``, ``not-passed: empty``,
    ``not-passed: unsupported-by-cli``, ``not-applicable``.

    Context and effort apply **only** to Grok. Cursor / OpenCode / Aider get
    ``not-applicable`` and never receive context/effort argv.
    """
    cli = _cli(kind)
    mid = concrete_model_id(model) or str(model or "").strip()
    # Reject PowerShell-metachar models (same rule as models_webhook).
    if mid and any(ch in mid for ch in (" ", "'", '"', "$", ";", "`", "|", "&", "<", ">")):
        mid = ""
        model_status = "not-passed: invalid"
    elif mid:
        model_status = "passed"
    else:
        model_status = "not-passed: empty"

    args: list[str] = []
    status = {"model": model_status, "effort": "not-applicable", "context": "not-applicable"}

    if cli != "grok":
        if cli == "cursor" and model_status == "passed":
            args.extend(["--model", mid])
        elif cli == "opencode" and model_status == "passed":
            args.extend(["-m", mid])
        elif cli == "aider" and model_status == "passed":
            args.extend(["--model", mid])
        elif cli not in WORKER_CLIS:
            status["model"] = "not-passed: unsupported"
        # Non-Grok: never pass context/effort (FR #9258).
        _ = mode
        return args, status

    # --- Grok ---
    eff = normalize_effort(effort)
    raw_effort = str(effort or "").strip()
    if raw_effort and not eff:
        effort_status = "not-passed: invalid"
        _warn_settings(f"invalid effort={raw_effort!r}; falling back to {DEFAULT_EFFORT}")
        eff = DEFAULT_EFFORT
    elif eff:
        effort_status = "passed"
    else:
        effort_status = "not-passed: empty"
        eff = DEFAULT_EFFORT

    raw_ctx = str(context or "").strip()
    ctx = normalize_context(raw_ctx)
    if raw_ctx and not ctx:
        context_status = "not-passed: invalid"
        _warn_settings(f"invalid context={raw_ctx!r}; using Grok CLI default (no argv)")
    elif ctx:
        if GROK_CONTEXT_CLI_FLAG:
            context_status = "passed"
        else:
            context_status = "not-passed: unsupported-by-cli"
            _file_grok_context_unsupported_intake()
    else:
        context_status = "not-passed: empty"

    status = {"model": model_status, "effort": effort_status, "context": context_status}

    if model_status == "passed":
        args.extend(["--model", mid])
    # Always pass a normalised effort for Grok (chosen or default low).
    args.extend(["--reasoning-effort", eff])
    if context_status == "passed" and GROK_CONTEXT_CLI_FLAG and ctx:
        args.extend([GROK_CONTEXT_CLI_FLAG, ctx])

    _ = mode  # reserved for Plan vs agent wrappers
    return args, status


def resolved_start_settings(
    kind: str,
    *,
    cfg: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolved model/context/effort + source for a CLI (webhook-aware config)."""
    c = cfg if cfg is not None else load_worker_start_config(env=env)
    cli = _cli(kind)
    model = launch_selected_model(cli, c, env)
    efforts = (c or {}).get("workerStartEffort") or {}
    contexts = (c or {}).get("workerStartContext") or {}
    sources = (c or {}).get("settings_source") or {}
    if cli == "grok":
        effort = configured_start_effort("grok", c, env=env)
        context = configured_start_context("grok", c, env=env)
        if not effort:
            effort = normalize_effort(efforts.get("grok")) or DEFAULT_EFFORT
        if not context:
            context = normalize_context(contexts.get("grok"))
    else:
        effort = ""
        context = ""
    source = str(sources.get(cli) or "local")
    if env_model_pin(cli, env):
        source = "env-pin"
    e = os.environ if env is None else env
    if cli == "grok" and (
        normalize_effort((e or {}).get("BOB_GROK_EFFORT"))
        or normalize_effort((e or {}).get("BOB_WORKER_START_EFFORT"))
        or normalize_context((e or {}).get("BOB_GROK_CONTEXT"))
        or normalize_context((e or {}).get("BOB_WORKER_START_CONTEXT"))
    ):
        source = "models-webhook"
    args, status = cli_settings_args(cli, model=model, effort=effort, context=context)
    return {
        "kind": cli,
        "model": model,
        "effort": effort,
        "context": context,
        "settings_source": source,
        "cli_settings_args": args,
        "setting_status": status,
    }


def launch_dryrun_path(*, env: dict[str, str] | None = None) -> Path:
    e = os.environ if env is None else env
    local = str((e or {}).get("LOCALAPPDATA") or "").strip()
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return Path(local) / "Bobiverse" / "worker" / "launch-dryrun.jsonl"


def append_launch_dryrun(
    entry: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
    path: Path | None = None,
) -> Path:
    """Append one JSON line for BOB-15 S1 evidence (no prompt/env/session ids)."""
    dest = Path(path) if path else launch_dryrun_path(env=env)
    dest.parent.mkdir(parents=True, exist_ok=True)
    safe = {
        "kind": str(entry.get("kind") or ""),
        "mode": str(entry.get("mode") or ""),
        "settings_source": str(entry.get("settings_source") or ""),
        "model": str(entry.get("model") or ""),
        "context": str(entry.get("context") or ""),
        "effort": str(entry.get("effort") or ""),
        "setting_status": entry.get("setting_status") or {},
        "cli_args": [str(a) for a in (entry.get("cli_args") or entry.get("cli_settings_args") or [])][:48],
        "executable": str(entry.get("executable") or ""),
    }
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(safe, sort_keys=True) + "\n")
    return dest



def cursor_cli_selected_model(env: dict[str, str] | None = None) -> str:
    """Model the Cursor CLI starts when the launcher passes no --model.

    Reads selectedModel.modelId, then model.modelId, from ~/.cursor/cli-config.json.
    Does not read auth fields.
    """
    e = os.environ if env is None else env
    home = str(e.get("USERPROFILE") or e.get("HOME") or "").strip()
    if not home:
        return ""
    path = Path(home) / ".cursor" / "cli-config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("selectedModel", "model"):
        block = data.get(key)
        if isinstance(block, dict):
            mid = str(block.get("modelId") or "").strip()
            if mid:
                return mid
    return ""


def concrete_model_id(raw: object) -> str:
    """A resolved model id. PowerShell templates such as ``$model`` are not ids."""
    got = str(raw or "").strip().strip("'\"")
    if not got or got.lower() in ("auto", "unknown", "none", "null"):
        return ""
    if "$" in got:
        return ""
    return got


def _model_from_argv(args: list[str]) -> str:
    if "--model" not in args:
        return ""
    i = args.index("--model")
    if i + 1 >= len(args):
        return ""
    return concrete_model_id(args[i + 1])


def _model_from_script_text(text: str) -> str:
    """Last concrete ``--model <id>`` in a launcher script. Skips ``auto`` and ``$model``."""
    found = ""
    for m in re.finditer(r"--model(?:\s+|=)(?P<q>['\"]?)(?P<id>[^\s'\"]+)(?P=q)", str(text or "")):
        got = concrete_model_id(m.group("id"))
        if got:
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
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fields for held / starting / idle / busy seats (FR #7084 / #7187 / #8159).

    `configured_model` is the launch selection (env pin > tray > config).
    """
    configured = launch_selected_model(cli, cfg, env=env)
    act = str(actual or "").strip()
    reason = model_mismatch_reason(act, configured, env=env)
    mismatch = bool(reason)
    out = {
        "kind": _cli(cli),
        "start_model": act,
        "configured_model": configured,
        "model_mismatch": mismatch,
        "cost_tier": model_cost_tier(act or configured, cfg),
        "start_effort": normalize_effort(effort) or configured_start_effort(cli, cfg),
        "state": str(state or "idle").strip().lower() or "idle",
    }
    if reason:
        out["mismatch_reason"] = reason
    return out


def start_model_is_unknown(raw: object) -> bool:
    """FR #7833: empty, missing, or an unexpanded ``$`` variable is not a model id."""
    s = str(raw or "").strip().strip("'\"")
    if not s:
        return True
    return "$" in s


_placeholder_reported: set[str] = set()


def note_placeholder_start_model(nick: str, shown: str, *, report=None) -> bool:
    """Report one placeholder ``start_model`` per seat for this process. No secret values."""
    key = str(nick or "").strip().lower()
    if not key or key in _placeholder_reported:
        return False
    _placeholder_reported.add(key)
    text = str(shown or "missing").strip()
    if len(text) > 80:
        text = text[:80]
    if report is not None:
        report(key, text)
        return True
    try:
        import crash_report

        crash_report.report_exception(
            "jeeves",
            RuntimeError,
            RuntimeError(f"placeholder start_model seat={key} value={text}"),
            None,
            repo="SimonBarnett/bobiverse",
        )
    except Exception:
        pass
    return True


def normalize_placeholder_start_model(
    fields: dict[str, Any] | None,
    cfg: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """Drop a placeholder ``start_model``. Tier follows ``configured_model``.

    Returns the fields for the tier gate and a note when the published start
    model was a placeholder (empty/missing is unknown but not filed).
    """
    f = dict(fields or {})
    raw = f.get("start_model", f.get("model"))
    published = "start_model" in f or "model" in f
    if published and not start_model_is_unknown(raw):
        return f, None
    configured = str(f.get("configured_model") or "").strip()
    placeholder = published and raw is not None and str(raw).strip() != "" and start_model_is_unknown(raw)
    f["model_mismatch"] = False
    if configured and not start_model_is_unknown(configured):
        f["start_model"] = configured
        f["cost_tier"] = model_cost_tier(configured, cfg)
    else:
        f.pop("start_model", None)
        f.pop("model", None)
        f.pop("cost_tier", None)
        f.pop("model_mismatch", None)
    return f, (str(raw).strip() if placeholder else None)


def seat_model_allows(
    fields: dict[str, Any] | None,
    job_task: str,
    cfg: dict[str, Any] | None,
    *,
    nick: str = "",
    report=None,
) -> bool:
    """FR #7084 gate after FR #7833: a placeholder start model is not a mismatch.

    FR #7888: a paid ``start_model`` stays eligible when it differs from
    ``configured_model``. Mismatch and a free published tier do not withhold.
    """
    f = fields or {}
    if not f:
        return True
    raw_start = str(f.get("start_model") or f.get("model") or "")
    if start_model_review_class(raw_start) == "paid":
        return True
    normalized, note = normalize_placeholder_start_model(f, cfg)
    if note:
        note_placeholder_start_model(nick, note, report=report)
    if (
        "model_mismatch" not in normalized
        and not normalized.get("start_model")
        and not normalized.get("cost_tier")
    ):
        return True
    return seat_allows_job(normalized, job_task, cfg)


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
