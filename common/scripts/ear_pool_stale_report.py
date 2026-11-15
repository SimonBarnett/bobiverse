"""FR #7503: bob-ear reports a stale xAI pool reading as an exception.

When the ear's own ``xai_weekly`` meter has not had a real live fetch for
``EAR_XAI_POOL_STALE_AFTER_S`` (2 minutes, same threshold as tray #7250 / #7471),
file one intake issue on SimonBarnett/bobiverse. Staying stale comments on that
report (never a new issue each minute). Recovery logs + comments; never auto-closes.

Never include secrets, tokens, or account passwords in the report body.
Generic: no host-specific branches.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import crash_report

EAR_XAI_POOL_STALE_AFTER_S = 120.0
DEFAULT_POOL = "xai_weekly"
COMPONENT = "bob-ear"
DEFAULT_COMMENT_MIN_S = 60.0
DEFAULT_REPO = crash_report.DEFAULT_REPO

_STATE: dict[str, dict[str, Any]] = {}


def reset_state() -> None:
    """Tests: clear in-memory + leave disk to the env dir override."""
    _STATE.clear()


def iso_utc_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def state_dir() -> Path:
    override = (os.environ.get("BOB_EAR_POOL_STALE_DIR") or "").strip()
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".")
    p = base / "Bobiverse" / "ear-pool-stale"
    p.mkdir(parents=True, exist_ok=True)
    return p


def fold_machine_id(machine_id: str) -> str:
    return str(machine_id or "").strip().lower()


def stale_signature(*, machine_id: str, pool: str = DEFAULT_POOL) -> str:
    mid = fold_machine_id(machine_id) or "unknown"
    pool_id = str(pool or DEFAULT_POOL).strip().lower() or DEFAULT_POOL
    return f"ear-pool-stale|{mid}|{pool_id}"


def _state_path(sig: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sig)[:120]
    return state_dir() / f"{safe}.json"


def _load_state(sig: str) -> dict[str, Any]:
    if sig in _STATE:
        return dict(_STATE[sig])
    path = _state_path(sig)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _STATE[sig] = dict(raw)
                return dict(raw)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return {}


def _save_state(sig: str, doc: dict[str, Any]) -> None:
    _STATE[sig] = dict(doc)
    try:
        _state_path(sig).write_text(
            json.dumps(doc, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass


def _parse_iso_epoch(value: object) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def reading_is_stale(
    *,
    fetched_at: object = None,
    last_ok_epoch: float | None = None,
    tracking_since: float | None = None,
    now: float,
    max_age_s: float = EAR_XAI_POOL_STALE_AFTER_S,
    remaining_pct: object = None,
    period_end: object = None,
    reset_at: object = None,
) -> bool:
    """True when the pool should raise a stale exception.

    FR #7522: 0% with a known future reset/period_end is never stale.
    """
    try:
        import pool_reading_stale as prs

        fa: object = fetched_at
        if fa in (None, ""):
            if last_ok_epoch is not None:
                fa = float(last_ok_epoch)
            elif tracking_since is not None:
                fa = float(tracking_since)
        return bool(
            prs.should_report_pool_stale_exception(
                fetched_at=fa,
                remaining_pct=remaining_pct,
                period_end=period_end,
                reset_at=reset_at,
                now=float(now),
                stale_after_s=float(max_age_s),
            )
        )
    except Exception:
        pass
    fa_epoch = _parse_iso_epoch(fetched_at)
    if fa_epoch is not None:
        return (float(now) - fa_epoch) > float(max_age_s)
    if last_ok_epoch is not None:
        try:
            return (float(now) - float(last_ok_epoch)) > float(max_age_s)
        except (TypeError, ValueError):
            pass
    if tracking_since is not None:
        try:
            return (float(now) - float(tracking_since)) > float(max_age_s)
        except (TypeError, ValueError):
            return False
    return False


def _extract_issue_number(result: object) -> int | None:
    if not isinstance(result, dict):
        return None
    for key in ("number", "issue_number", "github_number"):
        val = result.get(key)
        if val is None:
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    nested = result.get("result")
    if isinstance(nested, dict):
        return _extract_issue_number(nested)
    return None


def _build_body(
    *,
    machine_id: str,
    pool: str,
    fetched_at: object,
    last_error: object,
    version: str,
    sig: str,
    now_iso: str,
) -> str:
    err = crash_report.redact(str(last_error or "")[:400])
    fa = crash_report.redact(str(fetched_at or "none")[:80])
    mid = fold_machine_id(machine_id) or "unknown"
    return (
        f"what: bob-ear xAI pool reading stale (no live fetch for >"
        f"{int(EAR_XAI_POOL_STALE_AFTER_S)}s)\n"
        f"where: machine=`{mid}` pool=`{pool}` version=`{version}` "
        f"component=`{COMPONENT}`\n"
        f"last_good_fetched_at: {fa}\n"
        f"last_fetch_error: {err or 'none'}\n"
        f"observed_at: {now_iso}\n"
        f"fail-sig:{sig}\n"
        f"crash-sig:{sig}\n"
        f"dedupe:{sig}\n"
        f"\n---\n_via-ear-pool-stale-report FR=#7503_\n"
    )


def _build_title(*, machine_id: str, pool: str) -> str:
    mid = fold_machine_id(machine_id) or "unknown"
    return f"fail: {COMPONENT} stale pool {pool} on {mid}"[:200]


def evaluate_and_report_xai_pool_stale(
    *,
    machine_id: str,
    fetched_at: object = None,
    last_error: object = None,
    now: float | None = None,
    version: str | None = None,
    pool: str = DEFAULT_POOL,
    last_ok_epoch: float | None = None,
    remaining_pct: object = None,
    period_end: object = None,
    reset_at: object = None,
    filer_post: Callable[..., dict[str, Any]] | None = None,
    comment_fn: Callable[[str, int, str], bool] | None = None,
    comment_min_s: float | None = None,
    log_fn: Callable[[str], None] | None = None,
    repo: str = DEFAULT_REPO,
    max_age_s: float = EAR_XAI_POOL_STALE_AFTER_S,
) -> dict[str, Any]:
    """File / comment / recover for one machine+pool. Never raises."""
    try:
        now_f = time.time() if now is None else float(now)
        now_iso = iso_utc_from_epoch(now_f)
        mid = fold_machine_id(machine_id)
        pool_id = str(pool or DEFAULT_POOL).strip().lower() or DEFAULT_POOL
        sig = stale_signature(machine_id=mid, pool=pool_id)
        ver = version or crash_report.read_version()
        min_comment = (
            DEFAULT_COMMENT_MIN_S if comment_min_s is None else float(comment_min_s)
        )
        st = _load_state(sig)
        tracking_since = st.get("tracking_since")
        if tracking_since is None:
            tracking_since = now_f
            st["tracking_since"] = now_f

        stale = reading_is_stale(
            fetched_at=fetched_at,
            last_ok_epoch=last_ok_epoch,
            tracking_since=float(tracking_since),
            now=now_f,
            max_age_s=max_age_s,
            remaining_pct=remaining_pct,
            period_end=period_end,
            reset_at=reset_at,
        )

        def _log(msg: str) -> None:
            if log_fn:
                try:
                    log_fn(msg)
                except Exception:
                    pass

        # Recovery path
        if not stale:
            if st.get("stale"):
                number = st.get("open_number")
                body = (
                    f"recovery: `{pool_id}` on `{mid or 'unknown'}` is fresh again.\n"
                    f"fetched_at: {crash_report.redact(str(fetched_at or '')[:80])}\n"
                    f"observed_at: {now_iso}\n"
                    f"fail-sig:{sig}\n"
                    f"(do not auto-close; operator closes when satisfied)\n"
                )
                commented = False
                if number is not None and comment_fn is not None:
                    try:
                        commented = bool(comment_fn(repo, int(number), body))
                    except Exception:
                        commented = False
                elif filer_post is not None and number is None:
                    # No known issue number: post recovery via intake dedupe_key.
                    try:
                        filer_post(
                            _build_title(machine_id=mid, pool=pool_id),
                            body,
                            repo=repo,
                            sig=sig,
                            exe=COMPONENT,
                        )
                        commented = True
                    except Exception:
                        commented = False
                st["stale"] = False
                st["last_recovered_at"] = now_f
                st["last_fetched_at"] = fetched_at
                st["last_error"] = None
                if commented:
                    st["last_comment_at"] = now_f
                _save_state(sig, st)
                _log(
                    f"INFO ear-pool-stale recovered machine={mid} pool={pool_id} "
                    f"issue={number}"
                )
                return {
                    "ok": True,
                    "action": "recovered",
                    "sig": sig,
                    "number": number,
                    "commented": commented,
                }
            st["stale"] = False
            st["last_fetched_at"] = fetched_at
            st["last_error"] = None
            _save_state(sig, st)
            # Distinguish first tracking (no reading yet) from known-fresh.
            if fetched_at in (None, "") and last_ok_epoch is None:
                return {"ok": True, "action": "tracking", "sig": sig}
            return {"ok": True, "action": "fresh", "sig": sig}

        # Stale path
        title = _build_title(machine_id=mid, pool=pool_id)
        body = _build_body(
            machine_id=mid,
            pool=pool_id,
            fetched_at=fetched_at,
            last_error=last_error,
            version=str(ver),
            sig=sig,
            now_iso=now_iso,
        )
        number = st.get("open_number")
        already = bool(st.get("stale") and (st.get("filed") or number is not None))

        if already:
            last_c = float(st.get("last_comment_at") or st.get("last_report_at") or 0.0)
            if (now_f - last_c) < min_comment:
                st["last_error"] = last_error
                st["last_fetched_at"] = fetched_at
                _save_state(sig, st)
                return {
                    "ok": True,
                    "action": "deduped",
                    "sig": sig,
                    "number": number,
                }
            commented = False
            comment_body = (
                f"still stale: `{pool_id}` on `{mid or 'unknown'}`\n"
                f"last_good_fetched_at: "
                f"{crash_report.redact(str(fetched_at or 'none')[:80])}\n"
                f"last_fetch_error: "
                f"{crash_report.redact(str(last_error or 'none')[:400])}\n"
                f"observed_at: {now_iso}\n"
                f"fail-sig:{sig}\n"
            )
            if number is not None:
                fn = comment_fn or crash_report._gh_comment
                try:
                    commented = bool(fn(repo, int(number), comment_body))
                except Exception:
                    commented = False
            if not commented and filer_post is not None:
                # Intake dedupe_key path: same key comments rather than new issue.
                try:
                    filer_post(
                        title, comment_body, repo=repo, sig=sig, exe=COMPONENT
                    )
                    commented = True
                except Exception:
                    commented = False
            st["stale"] = True
            st["last_comment_at"] = now_f
            st["last_error"] = last_error
            st["last_fetched_at"] = fetched_at
            _save_state(sig, st)
            return {
                "ok": True,
                "action": "commented" if commented else "deduped",
                "sig": sig,
                "number": number,
                "commented": commented,
            }

        # First stale report
        post = filer_post or (
            lambda t, b, **kw: crash_report._post_intake(
                t, b, repo=kw.get("repo", repo), sig=sig, exe=COMPONENT
            )
        )
        try:
            result = post(title, body, repo=repo, sig=sig, exe=COMPONENT)
        except Exception as send_exc:  # noqa: BLE001
            path = crash_report._write_spool(
                {
                    "title": title,
                    "body": body,
                    "repo": repo,
                    "sig": sig,
                    "exe": COMPONENT,
                    "error": f"{type(send_exc).__name__}: {send_exc}",
                    "ts": now_iso,
                }
            )
            st.update(
                {
                    "stale": True,
                    "filed": False,
                    "last_report_at": now_f,
                    "last_error": last_error,
                    "last_fetched_at": fetched_at,
                    "spooled": str(path),
                }
            )
            _save_state(sig, st)
            return {
                "ok": False,
                "action": "spooled",
                "sig": sig,
                "spooled": str(path),
            }

        number = _extract_issue_number(result)
        st.update(
            {
                "stale": True,
                "filed": True,
                "open_number": number,
                "first_stale_at": st.get("first_stale_at") or now_f,
                "last_report_at": now_f,
                "last_comment_at": now_f,
                "last_error": last_error,
                "last_fetched_at": fetched_at,
                "machine": mid,
                "pool": pool_id,
                "sig": sig,
            }
        )
        _save_state(sig, st)
        _log(
            f"WARN ear-pool-stale filed machine={mid} pool={pool_id} "
            f"issue={number} sig={sig}"
        )
        out = {
            "ok": True,
            "action": "filed",
            "sig": sig,
            "number": number,
            "deduped": False,
        }
        if isinstance(result, dict):
            out["result"] = result
        return out
    except Exception as outer:  # noqa: BLE001
        return {"ok": False, "error": type(outer).__name__, "action": "error"}
