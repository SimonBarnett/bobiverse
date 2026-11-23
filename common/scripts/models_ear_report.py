# -*- coding: utf-8 -*-
"""FR #9250: Bob ear reports local CLI model lists; chair merges (no chair CLI spawn).

Ears collect ``grok models`` / ``agent models`` / ``opencode models`` on the
machine that holds the signed-in CLI, then POST ``/bob/v1/models/report``.
The chair unions per-CLI reporters with TTL age-out and never shells out to
those CLIs on the domain controller.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import models_catalog as mc
import models_refresh as mr

log = logging.getLogger("models_ear_report")

MODELS_REPORT_PATH = "/bob/v1/models/report"
REFRESH_CLIS: tuple[str, ...] = mr.REFRESH_CLIS

# Default reporter TTL (2h). Env BOB_MODELS_REPORTER_TTL_S (min 300).
DEFAULT_REPORTER_TTL_S = 7200.0
# Ear publish at most once per hour unless refresh-wanted is newer.
DEFAULT_EAR_INTERVAL_S = 3600.0

STATUS_OK = "ok"
STATUS_STALE = "stale"
STATUS_NO_REPORTER = "no_reporter"
STATUS_FAILED = "failed"

ClockFn = Callable[[], float]


def reporter_ttl_s() -> float:
    raw = (os.environ.get("BOB_MODELS_REPORTER_TTL_S") or "").strip()
    try:
        val = float(raw) if raw else DEFAULT_REPORTER_TTL_S
    except ValueError:
        val = DEFAULT_REPORTER_TTL_S
    return max(300.0, val)


def ear_interval_s() -> float:
    raw = (os.environ.get("BOB_MODELS_EAR_INTERVAL_S") or "").strip()
    try:
        val = float(raw) if raw else DEFAULT_EAR_INTERVAL_S
    except ValueError:
        val = DEFAULT_EAR_INTERVAL_S
    # Cap at 1h (acceptance); allow shorter intervals for tests via env.
    return max(60.0, min(3600.0, val))


def _utc_iso(now: float | None = None) -> str:
    ts = time.time() if now is None else float(now)
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_iso_ts(raw: Any) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def refresh_wanted_path(home: Path | str) -> Path:
    return Path(home) / "models-refresh-wanted.json"


def stamp_refresh_wanted(home: Path | str, *, now: float | None = None) -> str:
    """Chair refresh stamps a wanted file ears can see via shared digest home / sync."""
    at = _utc_iso(now)
    path = refresh_wanted_path(home)
    try:
        path.write_text(
            json.dumps({"wanted_at": at}, separators=(",", ":")),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("models_refresh_wanted write failed err=%s", type(exc).__name__)
    return at


def load_refresh_wanted_at(home: Path | str) -> str | None:
    path = refresh_wanted_path(home)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    at = doc.get("wanted_at")
    return str(at).strip() if at else None


def collect_local_cli_listings(
    home: Path | str | None = None,
    *,
    listers: dict[str, Callable[[], list[str]]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run local CLIs (ear host). Never include tokens. Soft-fail per CLI."""
    h = Path(home) if home else Path(".")
    fns = listers if listers is not None else mr.default_listers(h)
    out: dict[str, dict[str, Any]] = {}
    for cli in REFRESH_CLIS:
        fn = fns.get(cli)
        if fn is None:
            out[cli] = {"status": STATUS_FAILED, "reason": mr.REASON_NOT_INSTALLED, "models": []}
            continue
        try:
            ids = [str(x).strip() for x in fn() if str(x).strip()]
            if not ids:
                out[cli] = {
                    "status": STATUS_FAILED,
                    "reason": mr.REASON_EMPTY_LISTING,
                    "models": [],
                }
                continue
            out[cli] = {"status": STATUS_OK, "models": ids, "reason": None}
        except mr.ListingError as exc:
            out[cli] = {"status": STATUS_FAILED, "reason": exc.reason, "models": []}
        except Exception:
            out[cli] = {
                "status": STATUS_FAILED,
                "reason": mr.REASON_SPAWN_ERROR,
                "models": [],
            }
    return out


def build_ear_report_payload(
    machine: str,
    clis: dict[str, dict[str, Any]],
    *,
    refreshed_at: str | None = None,
) -> dict[str, Any]:
    mid = str(machine or "").strip().lower()
    at = refreshed_at or _utc_iso()
    clean: dict[str, Any] = {}
    for cli in REFRESH_CLIS:
        raw = clis.get(cli) if isinstance(clis, dict) else None
        if not isinstance(raw, dict):
            continue
        models = raw.get("models") if isinstance(raw.get("models"), list) else []
        ids = [str(x).strip() for x in models if str(x).strip()]
        # Strip anything that looks secret-ish (tokens never belong here).
        ids = [i for i in ids if "token" not in i.lower() and "bearer" not in i.lower()]
        entry = {
            "status": str(raw.get("status") or STATUS_OK).strip().lower() or STATUS_OK,
            "models": ids,
        }
        reason = raw.get("reason")
        if reason:
            entry["reason"] = str(reason).strip()[:80]
        clean[cli] = entry
    return {
        "op": "models_cli_report",
        "machine": mid,
        "id": mid,
        "refreshed_at": at,
        "clis": clean,
    }


def apply_machine_cli_report(
    home: Path | str,
    machine: str,
    clis: dict[str, Any],
    *,
    refreshed_at: str | None = None,
    now: float | None = None,
    ttl_s: float | None = None,
) -> dict[str, Any]:
    """Ingest one machine's CLI lists into models-catalog.json and rebuild unions."""
    mid = str(machine or "").strip().lower()
    if not mid:
        raise ValueError("machine required")
    at = refreshed_at or _utc_iso(now)
    ttl = reporter_ttl_s() if ttl_s is None else max(300.0, float(ttl_s))

    def _mutate(doc: dict[str, Any]) -> None:
        sources = doc.setdefault("clis_reporters", {})
        if not isinstance(sources, dict):
            sources = {}
            doc["clis_reporters"] = sources
        for cli in REFRESH_CLIS:
            raw = clis.get(cli) if isinstance(clis, dict) else None
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status") or "").strip().lower()
            models = raw.get("models") if isinstance(raw.get("models"), list) else []
            ids = [str(x).strip() for x in models if str(x).strip()]
            by_cli = sources.setdefault(cli, {})
            if not isinstance(by_cli, dict):
                by_cli = {}
                sources[cli] = by_cli
            if status == STATUS_FAILED or not ids:
                # Keep last good reporter models; record failure stamp only.
                prev = by_cli.get(mid) if isinstance(by_cli.get(mid), dict) else {}
                by_cli[mid] = {
                    "models": list(prev.get("models") or []) if isinstance(prev, dict) else [],
                    "refreshed_at": prev.get("refreshed_at") if isinstance(prev, dict) else None,
                    "last_error_at": at,
                    "last_error": str(raw.get("reason") or "failed")[:80],
                    "status": STATUS_FAILED,
                }
                continue
            by_cli[mid] = {
                "models": ids,
                "refreshed_at": at,
                "status": STATUS_OK,
                "last_error": None,
                "last_error_at": None,
            }
        rebuild_clis_from_reporters(doc, now=now, ttl_s=ttl)

    return mc.mutate_catalog_document(home, _mutate)


def rebuild_clis_from_reporters(
    doc: dict[str, Any],
    *,
    now: float | None = None,
    ttl_s: float | None = None,
) -> None:
    """Union fresh reporters into ``doc['clis']``; age out stale machines."""
    now_ts = time.time() if now is None else float(now)
    ttl = reporter_ttl_s() if ttl_s is None else max(300.0, float(ttl_s))
    sources = doc.get("clis_reporters")
    if not isinstance(sources, dict):
        sources = {}
    clis = doc.setdefault("clis", {})
    if not isinstance(clis, dict):
        clis = {}
        doc["clis"] = clis
    for cli in REFRESH_CLIS:
        by_machine = sources.get(cli) if isinstance(sources.get(cli), dict) else {}
        fresh: dict[str, list[str]] = {}
        latest_at: str | None = None
        latest_ts = -1.0
        for mid, row in list(by_machine.items()):
            if not isinstance(row, dict):
                continue
            at = row.get("refreshed_at")
            ts = _parse_iso_ts(at)
            if ts is None or (now_ts - ts) > ttl:
                # Age out reporter contribution without deleting the row history
                # for debugging — drop from union only.
                continue
            models = row.get("models") if isinstance(row.get("models"), list) else []
            ids = [str(x).strip() for x in models if str(x).strip()]
            if not ids:
                continue
            fresh[str(mid)] = ids
            if ts > latest_ts:
                latest_ts = ts
                latest_at = str(at)
        # Union preserving first-seen order across machines (sorted machine keys).
        seen: set[str] = set()
        ordered: list[str] = []
        for mid in sorted(fresh.keys()):
            for mid_id in fresh[mid]:
                if mid_id not in seen:
                    seen.add(mid_id)
                    ordered.append(mid_id)
        existing = clis.get(cli) if isinstance(clis.get(cli), dict) else None
        entry, _added, _removed = mr.merge_cli_models(
            existing, ordered, refreshed_at=latest_at or (existing or {}).get("refreshed_at")
        )
        entry["machines"] = sorted(fresh.keys())
        if not fresh:
            # No live reporters: keep prior models (hand-load / last good) but
            # clear machines list and leave refreshed_at as-was.
            if isinstance(existing, dict):
                entry = dict(existing)
                entry["machines"] = []
            else:
                entry = {"models": [], "refreshed_at": None, "machines": []}
        clis[cli] = entry


def reporter_status_for_cli(
    doc: dict[str, Any],
    cli: str,
    *,
    now: float | None = None,
    ttl_s: float | None = None,
) -> dict[str, Any]:
    """ok / stale / no_reporter for POST refresh response."""
    now_ts = time.time() if now is None else float(now)
    ttl = reporter_ttl_s() if ttl_s is None else max(300.0, float(ttl_s))
    sources = doc.get("clis_reporters") if isinstance(doc, dict) else None
    by_cli = (
        sources.get(cli)
        if isinstance(sources, dict) and isinstance(sources.get(cli), dict)
        else {}
    )
    if not by_cli:
        return {"status": STATUS_NO_REPORTER, "machines": [], "refreshed_at": None}
    fresh_machines: list[str] = []
    stale_machines: list[str] = []
    latest_at: str | None = None
    latest_ts = -1.0
    for mid, row in by_cli.items():
        if not isinstance(row, dict):
            continue
        at = row.get("refreshed_at")
        ts = _parse_iso_ts(at)
        if ts is None:
            stale_machines.append(str(mid))
            continue
        if (now_ts - ts) > ttl:
            stale_machines.append(str(mid))
        else:
            fresh_machines.append(str(mid))
            if ts > latest_ts:
                latest_ts = ts
                latest_at = str(at)
    if fresh_machines:
        return {
            "status": STATUS_OK,
            "machines": sorted(fresh_machines),
            "refreshed_at": latest_at,
        }
    if stale_machines:
        return {
            "status": STATUS_STALE,
            "machines": sorted(stale_machines),
            "refreshed_at": latest_at,
        }
    return {"status": STATUS_NO_REPORTER, "machines": [], "refreshed_at": None}


def handle_models_report_post(
    body: bytes | str | None,
    home: Path | str,
) -> tuple[int, bytes]:
    """POST /bob/v1/models/report body handler."""
    if body is None or body == b"" or body == "":
        return 400, _json({"error": "empty_body"})
    try:
        if isinstance(body, bytes):
            payload = json.loads(body.decode("utf-8"))
        else:
            payload = json.loads(body)
    except (UnicodeError, json.JSONDecodeError):
        return 400, _json({"error": "bad_json"})
    if not isinstance(payload, dict):
        return 400, _json({"error": "bad_json"})
    mid = str(payload.get("machine") or payload.get("id") or "").strip().lower()
    if not mid:
        return 400, _json({"error": "machine_required"})
    clis = payload.get("clis")
    if not isinstance(clis, dict) or not clis:
        return 400, _json({"error": "clis_required"})
    at = payload.get("refreshed_at")
    at_s = str(at).strip() if at else None
    try:
        doc = apply_machine_cli_report(home, mid, clis, refreshed_at=at_s)
    except mc.CatalogUnavailable:
        return 503, _json({"error": "catalog_unavailable"})
    except mc.ModelsCatalogBusy:
        return 503, _json({"error": "busy"})
    except OSError:
        return 503, _json({"error": "catalog_unavailable"})
    except ValueError as exc:
        return 400, _json({"error": str(exc)})
    # Deduped intake on parse/CLI failure (standing rule) — one message per cli reason.
    for cli, row in clis.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").lower() == STATUS_FAILED:
            _maybe_file_parse_failure(mid, str(cli), str(row.get("reason") or "failed"))
    public = mc.clis_public_from_document(doc)
    return 200, _json({"ok": True, "machine": mid, "clis": public})


_intake_lock = threading.Lock()
_intake_last: dict[str, float] = {}


def _maybe_file_parse_failure(machine: str, cli: str, reason: str) -> None:
    key = f"{machine}|{cli}|{reason}"
    now = time.time()
    with _intake_lock:
        last = _intake_last.get(key, 0.0)
        if now - last < 3600.0:
            return
        _intake_last[key] = now
    try:
        import runtime_failure

        runtime_failure.report_message(
            "bob-ear",
            f"models CLI report failed machine={machine} cli={cli} reason={reason}",
            site="models-ear-report",
        )
    except Exception:
        log.info(
            "models_ear_report failure machine=%s cli=%s reason=%s",
            machine,
            cli,
            reason,
        )


def _json(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")


def publish_local_models_cli_report(
    home: Path | str,
    machine: str,
    *,
    listers: dict[str, Callable[[], list[str]]] | None = None,
    post_fn: Callable[[dict], int | None] | None = None,
) -> int | None:
    """Ear: collect local listings and POST to chair models/report (or report URL)."""
    import bobreport

    clis = collect_local_cli_listings(home, listers=listers)
    payload = build_ear_report_payload(machine, clis)
    # Prefer dedicated models/report URL derived from digest base.
    if post_fn is not None:
        return post_fn(payload)
    base = (bobreport.report_post_url() or bobreport.digest_url() or "").rstrip("/")
    if base.endswith("/report"):
        url = base[: -len("/report")] + "/models/report"
    elif "/bob/v1/" in base:
        url = base.rsplit("/bob/v1/", 1)[0] + "/bob/v1/models/report"
    else:
        url = "https://bob.ntsa.uk/bob/v1/models/report"
    return bobreport.post_report_json(payload, url=url)
