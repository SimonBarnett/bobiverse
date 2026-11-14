"""FR #7255: Jeeves fetches fleet-wide OpenCode + Copilot pools once per minute.

Deterministic chair code. Credentials stay on the Jeeves box (token / Go key);
digest names the source tag only. Per-pool backoff on rate-limit/error.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

FLEET_POOL_FETCH_S = 60.0
FLEET_POOL_BACKOFF_CAP_S = 600.0
STATE_NAME = "fleet-pools-state.json"
POOL_COPILOT = "copilot"
POOL_OC_FREE = "opencode-free"
POOL_OC_GO = "opencode-go"

# FR #7288: walrus CredMan targets (generic credentials; secret in password blob).
CREDMAN_GITHUB_TARGET = "bobiverse/jeeves/github-token"
CREDMAN_OPENCODE_GO_TARGET = "bobiverse/jeeves/opencode-go-key"


def read_credman_secret(target: str) -> dict[str, str]:
    """Read a CredMan generic credential. Never log the secret.

    Returns {"username", "password"} or {}. Thin wrapper over
    jeeves_settings_auth.read_credman_generic so tests can monkeypatch here.
    """
    try:
        import jeeves_settings_auth as jsa

        return dict(jsa.read_credman_generic(target) or {})
    except Exception:
        return {}


def fleet_jeeves_install_root(
    env: dict[str, str] | None = None,
    *,
    explicit: str | Path | None = None,
) -> Path | None:
    """Jeeves product install root for fleet credential file fallbacks (FR #7288).

    Prefer ``JEEVES_INSTALL_ROOT``, then ``resolve_jeeves_install_root`` (frozen
    ``<InstallRoot>\\jeeves\\jeeves.exe`` / env). Do not use ear
    ``opencode_install_root`` (``scripts\\bob-ear.exe`` layout).
    """
    e = os.environ if env is None else env
    if explicit is not None and str(explicit).strip():
        return Path(str(explicit).strip()).resolve()
    override = (e.get("JEEVES_INSTALL_ROOT") or "").strip()
    if override:
        return Path(override).resolve()
    try:
        import chair_commands as cc

        root = cc.resolve_jeeves_install_root(env=e)
        if root is not None:
            return Path(root).resolve()
    except Exception:
        pass
    try:
        import ai_root

        return Path(ai_root.product_root("jeeves")).resolve()
    except Exception:
        return None


def _credman_blob(target: str) -> str:
    cred = read_credman_secret(target) or {}
    secret = str(cred.get("password") or "").strip()
    if not secret:
        secret = str(cred.get("username") or "").strip()
    return secret


def resolve_fleet_github_token(
    env: dict[str, str] | None = None,
    *,
    install_root: str | Path | None = None,
) -> tuple[str, str, list[str]]:
    """Return ``(token, source_tag, tried)`` for Jeeves fleet Copilot (FR #7288).

    Order: CredMan target, env ``GH_TOKEN``/``GITHUB_TOKEN``,
    ``<jeeves_root>/config/github.token``, ``BOB_CONFIG_DIR/github.token``.
    ``source_tag`` never includes the secret. On miss, source is
    ``none:<tried comma list>``.
    """
    e = os.environ if env is None else env
    tried: list[str] = []
    tag = f"credman:{CREDMAN_GITHUB_TARGET}"
    tried.append(tag)
    secret = _credman_blob(CREDMAN_GITHUB_TARGET)
    if secret:
        return secret, tag, tried
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        tag = f"env:{name}"
        tried.append(tag)
        raw = (e.get(name) or "").strip()
        if raw:
            return raw, tag, tried
    root = fleet_jeeves_install_root(e, explicit=install_root)
    if root is not None:
        path = Path(root) / "config" / "github.token"
        tag = "file:github.token"
        tried.append(tag)
        try:
            if path.is_file():
                tok = path.read_text(encoding="utf-8").strip()
                if tok:
                    return tok, tag, tried
        except OSError:
            pass
    cfg = (e.get("BOB_CONFIG_DIR") or "").strip()
    if cfg:
        path = Path(cfg).expanduser() / "github.token"
        tag = "file:BOB_CONFIG_DIR/github.token"
        tried.append(tag)
        try:
            if path.is_file():
                tok = path.read_text(encoding="utf-8").strip()
                if tok:
                    return tok, tag, tried
        except OSError:
            pass
    return "", "none:" + ",".join(tried), tried


def resolve_fleet_opencode_go_key(
    env: dict[str, str] | None = None,
    *,
    install_root: str | Path | None = None,
) -> tuple[str, str, list[str]]:
    """Return ``(api_key, source_tag, tried)`` for Jeeves fleet OpenCode Go (FR #7288)."""
    e = os.environ if env is None else env
    tried: list[str] = []
    tag = f"credman:{CREDMAN_OPENCODE_GO_TARGET}"
    tried.append(tag)
    secret = _credman_blob(CREDMAN_OPENCODE_GO_TARGET)
    if secret:
        return secret, tag, tried
    tag = "env:BOB_OPENCODE_GO_API_KEY"
    tried.append(tag)
    env_key = (e.get("BOB_OPENCODE_GO_API_KEY") or "").strip()
    if env_key:
        return env_key, tag, tried
    root = fleet_jeeves_install_root(e, explicit=install_root)
    if root is not None:
        try:
            import bobreport

            sel = bobreport.resolve_opencode_go_api_key_selection(
                e, install_root=root, tighten_acl=False
            )
            key = str(sel.get("api_key") or "").strip()
            src = str(sel.get("key_source") or "")
            if src == "env":
                tag = "env:BOB_OPENCODE_GO_API_KEY"
            elif src == "config-file":
                tag = "file:opencode-go.apikey"
            elif src == "labelled-file":
                tag = "file:opencode-keys"
            elif src:
                tag = f"file:{src}"
            else:
                tag = "file:opencode-go.apikey"
            tried.append(tag)
            if key:
                return key, tag, tried
        except Exception:
            tag = "file:opencode-go.apikey"
            tried.append(tag)
            try:
                path = Path(root) / "config" / "opencode-go.apikey"
                if path.is_file():
                    key = path.read_text(encoding="utf-8").strip()
                    if key:
                        return key, tag, tried
            except OSError:
                pass
    else:
        tried.append("file:opencode-go.apikey")
    return "", "none:" + ",".join(tried), tried


def iso_utc(now: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(now)))


def empty_meter(*, pool_id: str, source: str, error: str | None = None, now: float | None = None) -> dict:
    stamp = iso_utc(now if now is not None else time.time())
    return {
        "id": pool_id,
        "remaining": None,
        "fetched_at": None,
        "last_attempt_at": stamp,
        "error": error,
        "source": source,
        "fresh": False,
    }


def _load_state(home: Path) -> dict:
    path = Path(home) / STATE_NAME
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _save_state(home: Path, doc: dict) -> None:
    path = Path(home) / STATE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def pool_due(state: dict, name: str, now: float, *, force: bool = False) -> bool:
    if force:
        return True
    st = state.get(name) if isinstance(state.get(name), dict) else {}
    until = float(st.get("backoff_until") or 0.0)
    if now < until:
        return False
    last = float(st.get("last_attempt") or 0.0)
    if last <= 0.0:
        return True
    return (now - last) >= FLEET_POOL_FETCH_S


def mark_attempt(
    state: dict,
    name: str,
    now: float,
    *,
    ok: bool,
    error: str | None = None,
    rate_limited: bool = False,
) -> None:
    st = dict(state.get(name) if isinstance(state.get(name), dict) else {})
    st["last_attempt"] = float(now)
    st["error"] = error
    if ok:
        st["last_ok"] = float(now)
        st["fail_streak"] = 0
        st["backoff_until"] = 0.0
    else:
        streak = int(st.get("fail_streak") or 0) + 1
        st["fail_streak"] = streak
        delay = min(FLEET_POOL_BACKOFF_CAP_S, FLEET_POOL_FETCH_S * (2 ** min(streak, 4)))
        if rate_limited or error:
            st["backoff_until"] = float(now) + delay
    state[name] = st


def _keep_last(prev: dict | None, *, error: str, now: float, pool_id: str, source: str) -> dict:
    base = dict(prev) if isinstance(prev, dict) else empty_meter(pool_id=pool_id, source=source, now=now)
    base["id"] = pool_id
    base["source"] = source or base.get("source") or source
    base["fresh"] = False
    base["error"] = error
    base["last_attempt_at"] = iso_utc(now)
    # Do not advance fetched_at on failure; never copy period_end.
    if not base.get("fetched_at"):
        base["fetched_at"] = None
    return base


def fetch_copilot_default(home: Path, now: float) -> dict:
    import copilot_dispatch as cd

    token, src, tried = resolve_fleet_github_token()
    if not token:

        def boom() -> dict:
            raise RuntimeError("no_token")

        fetch_user: Callable[[], dict] = boom
        cred_source = src if src.startswith("none:") else ("none:" + ",".join(tried))
    else:
        import bobreport

        def fetch_user() -> dict:
            return bobreport._github_get_copilot_user(token)

        cred_source = src
    try:
        cd.observe_quota(Path(home), fetch_user=fetch_user, now=now)
        pool = cd.ensure_public_pool(cd.pool_for_digest(Path(home)))
    except Exception as exc:  # noqa: BLE001
        iso = iso_utc(now)
        return empty_meter(
            pool_id=POOL_COPILOT,
            source=cred_source,
            error=type(exc).__name__,
            now=now,
        )
    iso = iso_utc(now)
    err = pool.get("last_error")
    ok = str(pool.get("state") or "") in ("ok", "exhausted")
    remaining = pool.get("remaining")
    if not token:
        ok = False
        err = err or "no_token"
    return {
        "id": POOL_COPILOT,
        "remaining": remaining,
        "entitlement": pool.get("entitlement"),
        "reset_at": pool.get("reset_at") or "",
        "fetched_at": pool.get("fetched_at") if ok else (pool.get("fetched_at") or None),
        "last_attempt_at": pool.get("attempted_at") or iso,
        "error": None if ok else (err or "unread"),
        "source": cred_source,
        "fresh": bool(ok),
        "state": pool.get("state"),
        "unlimited": pool.get("unlimited"),
    }


def fetch_opencode_default(home: Path, now: float) -> dict:
    """Go zen usage with the service Go key. Free remaining only when the body has it."""
    import opencode_fuel as of

    iso = iso_utc(now)
    key, source_tag, _tried = resolve_fleet_opencode_go_key()
    if not key:
        err = "no_key"
        return {
            POOL_OC_FREE: empty_meter(pool_id=POOL_OC_FREE, source=source_tag, error=err, now=now),
            POOL_OC_GO: empty_meter(pool_id=POOL_OC_GO, source=source_tag, error=err, now=now),
            "windows": {},
        }
    read = of.fetch_go_zen_usage(key)
    kind = str((read or {}).get("kind") or "unavailable")
    doc = of.fuel_doc_from_go_zen_read(read, fetched_at=iso)
    go_ok = kind == "json"
    go_rem = doc.get("opencode-go")
    free_rem = doc.get("opencode-free")
    go = {
        "id": POOL_OC_GO,
        "remaining": go_rem if go_ok else None,
        "fetched_at": iso if go_ok else None,
        "last_attempt_at": iso,
        "error": None if go_ok else kind,
        "source": source_tag,
        "fresh": bool(go_ok),
        "windows": doc.get("windows") if go_ok else {},
        "usage_source": of.GO_ZEN_USAGE_SOURCE,
    }
    if not go_ok:
        go["remaining"] = go_rem
        go["fetched_at"] = None
    free_ok = go_ok and free_rem is not None
    free = {
        "id": POOL_OC_FREE,
        "remaining": free_rem if free_ok else None,
        "fetched_at": iso if free_ok else (iso if go_ok else None),
        "last_attempt_at": iso,
        "error": None if (free_ok or go_ok) else kind,
        "source": source_tag,
        "fresh": bool(free_ok),
        "usage_source": of.GO_ZEN_USAGE_SOURCE,
    }
    if go_ok and not free_ok:
        free["error"] = None
        free["fetched_at"] = iso
        free["fresh"] = True
    return {POOL_OC_FREE: free, POOL_OC_GO: go, "windows": doc.get("windows") or {}}


def apply_fleet_pools_to_digest(home: Path, fleet: dict) -> None:
    import bobreport

    doc = bobreport.load_digest(Path(home))
    doc["fleet_pools"] = fleet
    copilot = fleet.get(POOL_COPILOT)
    if isinstance(copilot, dict):
        doc["copilot"] = copilot
    oc = {
        "free": (fleet.get(POOL_OC_FREE) or {}).get("remaining"),
        "go": (fleet.get(POOL_OC_GO) or {}).get("remaining"),
        "windows": fleet.get("windows") or (fleet.get(POOL_OC_GO) or {}).get("windows"),
        "fetched_at": (fleet.get(POOL_OC_GO) or {}).get("fetched_at")
        or (fleet.get(POOL_OC_FREE) or {}).get("fetched_at"),
        POOL_OC_FREE: fleet.get(POOL_OC_FREE),
        POOL_OC_GO: fleet.get(POOL_OC_GO),
    }
    doc["opencode"] = oc
    bobreport.save_digest(Path(home), doc)


def public_fleet_section(fleet: dict | None) -> dict:
    if not isinstance(fleet, dict):
        return {}
    out = {}
    for key in (POOL_COPILOT, POOL_OC_FREE, POOL_OC_GO):
        row = fleet.get(key)
        if isinstance(row, dict):
            out[key] = row
    if fleet.get("windows"):
        out["windows"] = fleet.get("windows")
    return out


def tick_fleet_pools(
    home: Path,
    *,
    now: float | None = None,
    force: bool = False,
    fetch_copilot: Callable[[Path, float], dict] | None = None,
    fetch_opencode: Callable[[Path, float], dict] | None = None,
) -> dict:
    """Fetch due OpenCode/Copilot pools; persist digest fleet_pools. No secrets in return."""
    now_f = time.time() if now is None else float(now)
    home_p = Path(home)
    state = _load_state(home_p)
    prev = {}
    try:
        import bobreport

        digest = bobreport.load_digest(home_p)
        prev = digest.get("fleet_pools") if isinstance(digest.get("fleet_pools"), dict) else {}
    except Exception:
        prev = {}
    fleet = dict(prev)
    copilot_fn = fetch_copilot or fetch_copilot_default
    oc_fn = fetch_opencode or fetch_opencode_default

    if pool_due(state, POOL_COPILOT, now_f, force=force):
        try:
            row = copilot_fn(home_p, now_f)
            if not isinstance(row, dict):
                raise RuntimeError("parse")
            ok = bool(row.get("fresh")) and not row.get("error")
            err = str(row.get("error") or "") or None
            rate = "429" in str(err or "") or "rate" in str(err or "").lower()
            if ok:
                fleet[POOL_COPILOT] = row
            else:
                fleet[POOL_COPILOT] = _keep_last(
                    prev.get(POOL_COPILOT),
                    error=err or "unread",
                    now=now_f,
                    pool_id=POOL_COPILOT,
                    source=str(row.get("source") or "copilot_internal/user"),
                )
                if row.get("remaining") is not None and fleet[POOL_COPILOT].get("remaining") is None:
                    fleet[POOL_COPILOT]["remaining"] = row.get("remaining")
                if row.get("fetched_at"):
                    fleet[POOL_COPILOT]["fetched_at"] = row.get("fetched_at")
            mark_attempt(state, POOL_COPILOT, now_f, ok=ok, error=err, rate_limited=rate)
        except Exception as exc:  # noqa: BLE001
            fleet[POOL_COPILOT] = _keep_last(
                prev.get(POOL_COPILOT),
                error=type(exc).__name__,
                now=now_f,
                pool_id=POOL_COPILOT,
                source="copilot_internal/user",
            )
            mark_attempt(state, POOL_COPILOT, now_f, ok=False, error=type(exc).__name__)

    if pool_due(state, POOL_OC_GO, now_f, force=force) or pool_due(
        state, POOL_OC_FREE, now_f, force=force
    ):
        try:
            pack = oc_fn(home_p, now_f)
            if not isinstance(pack, dict):
                raise RuntimeError("parse")
            for pid in (POOL_OC_FREE, POOL_OC_GO):
                row = pack.get(pid) if isinstance(pack.get(pid), dict) else None
                if row is None:
                    continue
                ok = bool(row.get("fresh")) and not row.get("error")
                err = str(row.get("error") or "") or None
                rate = "429" in str(err or "") or str(err or "") in ("unavailable",)
                if ok:
                    fleet[pid] = row
                else:
                    fleet[pid] = _keep_last(
                        prev.get(pid),
                        error=err or "unread",
                        now=now_f,
                        pool_id=pid,
                        source=str(row.get("source") or "go-zen-usage"),
                    )
                mark_attempt(state, pid, now_f, ok=ok, error=err, rate_limited=rate)
            if pack.get("windows"):
                fleet["windows"] = pack.get("windows")
        except Exception as exc:  # noqa: BLE001
            for pid in (POOL_OC_FREE, POOL_OC_GO):
                fleet[pid] = _keep_last(
                    prev.get(pid),
                    error=type(exc).__name__,
                    now=now_f,
                    pool_id=pid,
                    source="go-zen-usage",
                )
                mark_attempt(state, pid, now_f, ok=False, error=type(exc).__name__)

    _save_state(home_p, state)
    apply_fleet_pools_to_digest(home_p, fleet)
    return public_fleet_section(fleet)
