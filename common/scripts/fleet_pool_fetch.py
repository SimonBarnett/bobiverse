"""FR #7255 / #7288 / #7326: Jeeves fetches fleet OpenCode Go and Copilot only.

Deterministic chair code. Credentials stay on the Jeeves box (token / Go key).
Digest names the source tag only. Per-pool backoff. Cursor / Grok chat is a
per-machine ear pool on the xAI weekly line (FR #7326), not a fleet meter.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

FLEET_POOL_FETCH_S = 60.0
FLEET_POOL_BACKOFF_CAP_S = 600.0
# FR #7504: no real live fetch for this long -> exception report (Si: stale is a bug).
FLEET_POOL_STALE_S = 120.0
FLEET_POOL_STALE_COMMENT_S = 600.0
FLEET_POOL_STALE_REPO = "SimonBarnett/bobiverse"
STATE_NAME = "fleet-pools-state.json"
POOL_COPILOT = "copilot"
POOL_OC_FREE = "opencode-free"
POOL_OC_GO = "opencode-go"
POOL_CURSOR = "cursor"
STALE_REPORT_POOLS = (POOL_COPILOT, POOL_OC_GO)
CURSOR_CREDMAN_TARGET = "Bobiverse/CursorAccess"

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

    Prefer ``JEEVES_INSTALL_ROOT``, then the frozen ``jeeves.exe`` *product*
    directory (``<InstallRoot>\\jeeves``), then ``ai_root.product_root("jeeves")``.
    Never ``BOB_INSTALL_ROOT`` / ear ``scripts\\bob-ear.exe``: chair
    ``resolve_jeeves_install_root`` treats ``BOB_INSTALL_ROOT`` as the MSI
    install root and would steal ear ``config\\github.token``.
    """
    e = os.environ if env is None else env
    if explicit is not None and str(explicit).strip():
        return Path(str(explicit).strip()).resolve()
    override = (e.get("JEEVES_INSTALL_ROOT") or "").strip()
    if override:
        return Path(override).resolve()
    try:
        import sys

        is_frozen = bool(getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"))
        if is_frozen:
            exe = Path(sys.executable).resolve()
            if exe.parent.name.lower() == "jeeves":
                return exe.parent
            if exe.name.lower() in ("jeeves.exe", "jeeves"):
                return exe.parent
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
    if not st.get("first_attempt"):
        st["first_attempt"] = float(now)
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
        cred_source = src if src.startswith("none:") else ("none:" + ",".join(tried))
        return empty_meter(
            pool_id=POOL_COPILOT,
            source=cred_source,
            error="no_token",
            now=now,
        )
    import bobreport

    def fetch_user() -> dict:
        return bobreport._github_get_copilot_user(token)

    cred_source = src
    try:
        cd.observe_quota(Path(home), fetch_user=fetch_user, now=now)
        pool = cd.ensure_public_pool(cd.pool_for_digest(Path(home)))
    except Exception as exc:  # noqa: BLE001
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


def cursor_remaining_from_period(period: dict | None) -> int | None:
    """Low-cost / auto pool remaining percent from Cursor period JSON."""
    if not isinstance(period, dict):
        return None
    pu = period.get("planUsage") if isinstance(period.get("planUsage"), dict) else {}
    raw = pu.get("autoPercentUsed")
    if raw is None or raw == "":
        raw = period.get("autoPercentUsed")
    if raw is None or raw == "":
        return None
    try:
        used = float(raw)
    except (TypeError, ValueError):
        return None
    remain = int(round(100.0 - used))
    if remain < 0:
        return 0
    if remain > 100:
        return 100
    return remain


def resolve_cursor_token() -> tuple[str, str]:
    """Walrus CredMan first, then env. Never log or return the value in *source*."""
    target = (os.environ.get("BOB_CURSOR_CREDMAN_TARGET") or CURSOR_CREDMAN_TARGET).strip()
    source = "credman:" + target
    try:
        import jeeves_settings_auth as ja

        cred = ja.read_credman_generic(target)
        pw = str((cred or {}).get("password") or "").strip()
        if pw:
            return pw, source
    except Exception:
        pass
    env = (os.environ.get("BOB_CURSOR_ACCESS_TOKEN") or "").strip()
    if env:
        return env, "env:BOB_CURSOR_ACCESS_TOKEN"
    return "", source


def fetch_cursor_period(token: str) -> dict:
    """POST Cursor dashboard GetCurrentPeriodUsage. Token never in errors."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage",
        data=b"{}",
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("http-%s" % int(exc.code)) from None
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(type(exc).__name__) from None
    if not isinstance(body, dict):
        raise RuntimeError("parse")
    return body


def fetch_cursor_default(home: Path, now: float) -> dict:
    iso = iso_utc(now)
    token, source = resolve_cursor_token()
    if not token:
        return empty_meter(pool_id=POOL_CURSOR, source=source, error="no_key", now=now)
    try:
        period = fetch_cursor_period(token)
    except Exception as exc:  # noqa: BLE001
        return empty_meter(
            pool_id=POOL_CURSOR, source=source, error=str(exc) or type(exc).__name__, now=now
        )
    rem = cursor_remaining_from_period(period)
    ok = rem is not None
    return {
        "id": POOL_CURSOR,
        "remaining": rem,
        "fetched_at": iso if ok else None,
        "last_attempt_at": iso,
        "error": None if ok else "no-usage-data",
        "source": source,
        "fresh": bool(ok),
    }


def apply_fleet_pools_to_digest(home: Path, fleet: dict) -> None:
    import bobreport

    doc = bobreport.load_digest(Path(home))
    doc["fleet_pools"] = fleet
    copilot = fleet.get(POOL_COPILOT)
    if isinstance(copilot, dict):
        doc["copilot"] = copilot
    oc = {
        "go": (fleet.get(POOL_OC_GO) or {}).get("remaining"),
        "windows": fleet.get("windows") or (fleet.get(POOL_OC_GO) or {}).get("windows"),
        "fetched_at": (fleet.get(POOL_OC_GO) or {}).get("fetched_at"),
        POOL_OC_GO: fleet.get(POOL_OC_GO),
    }
    doc["opencode"] = oc
    bobreport.save_digest(Path(home), doc)


def public_fleet_section(fleet: dict | None) -> dict:
    if not isinstance(fleet, dict):
        return {}
    out = {}
    for key in (POOL_COPILOT, POOL_OC_GO):
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
    fetch_cursor: Callable[[Path, float], dict] | None = None,
) -> dict:
    """Fetch due OpenCode Go / Copilot; persist digest fleet_pools. No secrets."""
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
    cursor_fn = fetch_cursor or fetch_cursor_default

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

    if pool_due(state, POOL_OC_GO, now_f, force=force):
        try:
            pack = oc_fn(home_p, now_f)
            if not isinstance(pack, dict):
                raise RuntimeError("parse")
            pid = POOL_OC_GO
            row = pack.get(pid) if isinstance(pack.get(pid), dict) else None
            if row is not None:
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
            fleet[POOL_OC_GO] = _keep_last(
                prev.get(POOL_OC_GO),
                error=type(exc).__name__,
                now=now_f,
                pool_id=POOL_OC_GO,
                source="go-zen-usage",
            )
            mark_attempt(state, POOL_OC_GO, now_f, ok=False, error=type(exc).__name__)
    # FR #7326: no OpenCode Free meter; no fleet Cursor fetch.
    fleet.pop(POOL_OC_FREE, None)
    fleet.pop(POOL_CURSOR, None)
    _ = cursor_fn

    _save_state(home_p, state)
    apply_fleet_pools_to_digest(home_p, fleet)
    try:
        maybe_report_fleet_pool_staleness(home_p, now=now_f)
    except Exception:
        pass
    return public_fleet_section(fleet)


def fleet_pool_stale_sig(pool: str) -> str:
    return f"fleet-pool-stale:{pool}"


def pool_seconds_without_live_fetch(state_row: dict | None, now: float) -> float | None:
    """Seconds since last successful live fetch, or since first attempt if never ok."""
    if not isinstance(state_row, dict):
        return None
    last_ok = float(state_row.get("last_ok") or 0.0)
    if last_ok > 0.0:
        return float(now) - last_ok
    first = float(state_row.get("first_attempt") or state_row.get("last_attempt") or 0.0)
    if first <= 0.0:
        return None
    return float(now) - first


def _safe_text(value: object, *, limit: int = 240) -> str:
    try:
        import crash_report as cr

        text = cr.redact(str(value if value is not None else ""))
    except Exception:
        text = str(value if value is not None else "")
    text = text.replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def build_fleet_pool_stale_report(
    pool: str,
    *,
    fetched_at: str | None,
    error: str | None,
    age_s: float,
    version: str | None = None,
) -> tuple[str, str, str]:
    """Title, body, sig for a stale fleet pool. Never includes secrets."""
    try:
        import crash_report as cr

        ver = (version or cr.read_version() or "unknown").strip()[:64]
    except Exception:
        ver = (version or "unknown").strip()[:64]
    sig = fleet_pool_stale_sig(pool)
    title = f"Jeeves fleet pool stale: {pool} (FR #7504)"
    last_good = _safe_text(fetched_at or "(none)")
    err = _safe_text(error or "(none)")
    body = (
        f"<!-- {sig} -->\n"
        f"## Stale fleet pool\n\n"
        f"- pool: `{_safe_text(pool, limit=64)}`\n"
        f"- age_without_live_fetch_s: {int(age_s)}\n"
        f"- last_good_fetched_at: `{last_good}`\n"
        f"- last_fetch_error: `{err}`\n"
        f"- jeeves_version: `{_safe_text(ver, limit=64)}`\n\n"
        "Si rule: stale is a bug — report like any other exception. "
        "No auto-close; comment on recovery.\n"
    )
    return title, body, sig


def file_fleet_pool_stale_exception(
    *,
    pool: str,
    title: str,
    body: str,
    sig: str,
    repo: str = FLEET_POOL_STALE_REPO,
) -> dict:
    """File via intake (same path as crash_report). Injectable in tests."""
    import crash_report as cr

    result = cr._post_intake(title, body, repo=repo, sig=sig, exe="jeeves")
    number = None
    if isinstance(result, dict):
        number = result.get("number") or (result.get("issue") or {}).get("number")
        if number is None and result.get("url"):
            # best-effort parse .../issues/N
            try:
                number = int(str(result.get("url")).rstrip("/").rsplit("/", 1)[-1])
            except (TypeError, ValueError):
                number = None
    if number is None:
        number = cr._gh_search_open_sig(repo, sig)
    return {"ok": True, "deduped": False, "number": number, "result": result, "pool": pool, "body": body}


def comment_fleet_pool_stale_issue(
    *,
    number: int,
    body: str,
    repo: str = FLEET_POOL_STALE_REPO,
) -> bool:
    import crash_report as cr

    return bool(cr._gh_comment(repo, int(number), body))


def maybe_report_fleet_pool_staleness(
    home: Path,
    *,
    now: float | None = None,
    repo: str = FLEET_POOL_STALE_REPO,
) -> dict:
    """FR #7504: one open report per stale fleet pool; comment on prolong/recovery."""
    now_f = time.time() if now is None else float(now)
    home_p = Path(home)
    state = _load_state(home_p)
    fleet: dict = {}
    try:
        import bobreport

        digest = bobreport.load_digest(home_p)
        fleet = digest.get("fleet_pools") if isinstance(digest.get("fleet_pools"), dict) else {}
    except Exception:
        fleet = {}
    out: dict = {}
    changed = False
    for pool in STALE_REPORT_POOLS:
        st = dict(state.get(pool) if isinstance(state.get(pool), dict) else {})
        age = pool_seconds_without_live_fetch(st, now_f)
        row = fleet.get(pool) if isinstance(fleet.get(pool), dict) else {}
        fetched_at = row.get("fetched_at") if isinstance(row, dict) else None
        err = st.get("error") or (row.get("error") if isinstance(row, dict) else None)
        issue_n = st.get("stale_issue")
        try:
            issue_n = int(issue_n) if issue_n not in (None, "") else None
        except (TypeError, ValueError):
            issue_n = None
        open_flag = bool(st.get("stale_open"))
        if age is None or age < float(FLEET_POOL_STALE_S):
            # recovery path
            if open_flag and issue_n:
                body = (
                    f"<!-- {fleet_pool_stale_sig(pool)} -->\n"
                    f"Fleet pool `{pool}` recovered live fetch "
                    f"(age_s={0 if age is None else int(age)}; "
                    f"fetched_at=`{_safe_text(fetched_at or '')}`).\n"
                    "Leaving issue open (no auto-close).\n"
                )
                comment_fleet_pool_stale_issue(number=issue_n, body=body, repo=repo)
                st["stale_open"] = False
                st["stale_recovered"] = True
                st["stale_recovered_at"] = float(now_f)
                state[pool] = st
                changed = True
                out[pool] = {"action": "recovered", "number": issue_n}
            else:
                out[pool] = {"action": "ok"}
            continue
        # stale
        title, body, sig = build_fleet_pool_stale_report(
            pool, fetched_at=str(fetched_at) if fetched_at else None, error=str(err) if err else None, age_s=age
        )
        if issue_n and open_flag:
            last_c = float(st.get("stale_comment_at") or 0.0)
            if (now_f - last_c) >= float(FLEET_POOL_STALE_COMMENT_S):
                prolong = (
                    f"<!-- {sig} -->\n"
                    f"Still stale: pool=`{pool}` age_s={int(age)} "
                    f"last_good_fetched_at=`{_safe_text(fetched_at or '(none)')}` "
                    f"last_fetch_error=`{_safe_text(err or '(none)')}`\n"
                )
                comment_fleet_pool_stale_issue(number=issue_n, body=prolong, repo=repo)
                st["stale_comment_at"] = float(now_f)
                state[pool] = st
                changed = True
                out[pool] = {"action": "commented", "number": issue_n}
            else:
                out[pool] = {"action": "deduped", "number": issue_n}
            continue
        # find existing open or file new
        existing = None
        try:
            import crash_report as cr

            existing = cr._gh_search_open_sig(repo, sig)
        except Exception:
            existing = None
        if existing:
            st["stale_issue"] = int(existing)
            st["stale_open"] = True
            st["stale_comment_at"] = float(now_f)
            state[pool] = st
            changed = True
            comment_fleet_pool_stale_issue(number=int(existing), body=body, repo=repo)
            out[pool] = {"action": "deduped", "number": int(existing)}
            continue
        filed = file_fleet_pool_stale_exception(
            pool=pool, title=title, body=body, sig=sig, repo=repo
        )
        num = filed.get("number")
        if num is not None:
            st["stale_issue"] = int(num)
            st["stale_open"] = True
            st["stale_comment_at"] = float(now_f)
            st["stale_recovered"] = False
            state[pool] = st
            changed = True
            out[pool] = {"action": "filed", "number": int(num)}
        else:
            out[pool] = {"action": "filed", "number": None, "spooled": True}
    if changed:
        _save_state(home_p, state)
    return out
