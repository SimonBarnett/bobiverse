"""FR #6387: durable per-job token/cost ledger and per-PR totals for the digest."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import done_usage


def ledger_path(home: Path) -> Path:
    return Path(home) / "job-cost-ledger.json"


def make_row(
    *,
    pr: str,
    task: str = "",
    seat: str = "",
    model: str = "",
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    tokens_cached: Optional[int] = None,
    legacy_tokens: Optional[int] = None,
    tokens_unknown: bool = True,
    done_at: float | None = None,
    url: str = "",
    attempt: int = 1,
    source: str = "done",
) -> dict[str, Any]:
    measured = (
        tokens_in is not None or tokens_out is not None or tokens_cached is not None
    )
    if measured:
        tokens_unknown = False
    elif legacy_tokens is not None:
        tokens_unknown = False
    else:
        tokens_unknown = True
    try:
        attempt_i = int(attempt) if attempt is not None else 1
    except (TypeError, ValueError):
        attempt_i = 1
    if attempt_i < 1:
        attempt_i = 1
    src = str(source or "").strip() or "done"
    return {
        "pr": str(pr or ""),
        "task": str(task or "").strip().upper(),
        "seat": str(seat or ""),
        "model": str(model or ""),
        "tokens_in": None if tokens_in is None else int(tokens_in),
        "tokens_out": None if tokens_out is None else int(tokens_out),
        "tokens_cached": None if tokens_cached is None else int(tokens_cached),
        "legacy_tokens": None if legacy_tokens is None else int(legacy_tokens),
        "tokens_unknown": bool(tokens_unknown),
        "done_at": float(done_at if done_at is not None else time.time()),
        "url": str(url or ""),
        "attempt": attempt_i,
        "source": src,
    }


def _row_key(row: Mapping[str, Any]) -> tuple:
    """FR #6435: idempotency key — same job/PR/attempt (and seat+task) is one row."""
    try:
        attempt = int(row.get("attempt") or 1)
    except (TypeError, ValueError):
        attempt = 1
    return (
        str(row.get("pr") or ""),
        str(row.get("task") or "").strip().upper(),
        str(row.get("seat") or ""),
        attempt,
    )


def load_rows(home: Path) -> list[dict]:
    path = ledger_path(home)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("rows") if isinstance(data, dict) else data
    return [r for r in (rows or []) if isinstance(r, dict)]


def save_rows(home: Path, rows: list[dict]) -> None:
    path = ledger_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)
    payload = {"rows": list(rows)[-2000:], "summary": summary}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sum_field(rows: Iterable[dict], key: str) -> int:
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("tokens_unknown"):
            continue
        val = row.get(key)
        if val is None:
            continue
        try:
            total += int(val)
        except (TypeError, ValueError):
            continue
    return total


def per_pr_totals(home: Path, pr: str) -> dict[str, Any]:
    """Sum FR + MRB + FIX (+ UAT) rows for one ``owner/repo#N`` key."""
    want = str(pr or "").strip()
    rows = [r for r in load_rows(home) if str(r.get("pr") or "") == want]
    measured = [r for r in rows if not r.get("tokens_unknown")]
    unknown = [r for r in rows if r.get("tokens_unknown")]
    models = sorted(
        {
            str(r.get("model") or "").strip()
            for r in rows
            if str(r.get("model") or "").strip()
        }
    )
    return {
        "pr": want,
        "jobs": len(rows),
        "measured_jobs": len(measured),
        "unknown_jobs": len(unknown),
        "tokens_in": _sum_field(rows, "tokens_in"),
        "tokens_out": _sum_field(rows, "tokens_out"),
        "tokens_cached": _sum_field(rows, "tokens_cached"),
        "legacy_tokens": _sum_field(rows, "legacy_tokens"),
        "models": models,
        "tasks": sorted({str(r.get("task") or "") for r in rows if r.get("task")}),
    }


def by_model_rollup(rows: Iterable[dict] | None) -> dict[str, Any]:
    """FR #6783: group measured ledger rows by model; unknowns stay out of sums.

    Returns ``{"by_model": [...], "unknown_jobs": N}``. Each bucket has
    ``model``, ``measured_jobs``, ``tokens_in``, ``tokens_out``, ``tokens_cached``.
    """
    buckets: dict[str, dict[str, Any]] = {}
    unknown_jobs = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("tokens_unknown"):
            unknown_jobs += 1
            continue
        model = str(row.get("model") or "").strip()
        bucket = buckets.get(model)
        if bucket is None:
            bucket = {
                "model": model,
                "measured_jobs": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "tokens_cached": 0,
            }
            buckets[model] = bucket
        bucket["measured_jobs"] += 1
        for key in ("tokens_in", "tokens_out", "tokens_cached"):
            val = row.get(key)
            if val is None:
                continue
            try:
                bucket[key] = int(bucket[key]) + int(val)
            except (TypeError, ValueError):
                continue
    by_model = [buckets[k] for k in sorted(buckets.keys())]
    return {"by_model": by_model, "unknown_jobs": unknown_jobs}


def summarize(rows: Iterable[dict] | None) -> dict[str, Any]:
    """Digest-facing rollup: per-PR totals across FR + MRB + FIX (+ UAT)."""
    by_pr: dict[str, list[dict]] = {}
    all_rows: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        all_rows.append(row)
        pr = str(row.get("pr") or "").strip()
        if not pr:
            continue
        by_pr.setdefault(pr, []).append(row)
    per_pr: list[dict[str, Any]] = []
    for pr, group in sorted(by_pr.items()):
        measured = [r for r in group if not r.get("tokens_unknown")]
        unknown = [r for r in group if r.get("tokens_unknown")]
        models = sorted(
            {
                str(r.get("model") or "").strip()
                for r in group
                if str(r.get("model") or "").strip()
            }
        )
        per_pr.append(
            {
                "pr": pr,
                "jobs": len(group),
                "measured_jobs": len(measured),
                "unknown_jobs": len(unknown),
                "tokens_in": _sum_field(group, "tokens_in"),
                "tokens_out": _sum_field(group, "tokens_out"),
                "tokens_cached": _sum_field(group, "tokens_cached"),
                "models": models,
                "tasks": sorted(
                    {str(r.get("task") or "") for r in group if r.get("task")}
                ),
            }
        )
    model_roll = by_model_rollup(all_rows)
    return {
        "pr_count": len(per_pr),
        "job_count": sum(int(p["jobs"]) for p in per_pr),
        "per_pr": per_pr[-100:],
        "by_model": list(model_roll.get("by_model") or []),
        "unknown_jobs": int(model_roll.get("unknown_jobs") or 0),
    }


def record_done(
    home: Path,
    *,
    repo: str,
    ident: str,
    task: str = "",
    seat: str = "",
    rest: str = "",
    url: str = "",
    done_at: float | None = None,
) -> dict[str, Any]:
    """Record one DONE measurement row from shop rest tokens (idempotent per job).

    FR #6435: the same ``(pr, task, seat, attempt)`` key updates the existing row
    instead of appending a duplicate (DONE replay / double relay).
    """
    meta = done_usage.parse_done_usage(rest or "")
    pr = f"{repo}{ident}"
    row = make_row(
        pr=pr,
        task=task,
        seat=seat,
        model=str(meta.get("model") or ""),
        tokens_in=meta.get("tokens_in"),
        tokens_out=meta.get("tokens_out"),
        tokens_cached=meta.get("tokens_cached"),
        legacy_tokens=meta.get("legacy_tokens"),
        tokens_unknown=bool(meta.get("tokens_unknown")),
        done_at=done_at,
        url=url or "",
        attempt=int(meta.get("attempt") or 1),
        source=str(meta.get("source") or "done"),
    )
    rows = load_rows(home)
    key = _row_key(row)
    for i, existing in enumerate(rows):
        if _row_key(existing) == key:
            # Keep the first done_at; refresh measured fields from the latest stamp.
            merged = dict(existing)
            for k in (
                "model",
                "tokens_in",
                "tokens_out",
                "tokens_cached",
                "legacy_tokens",
                "tokens_unknown",
                "url",
                "source",
                "attempt",
            ):
                if k in row:
                    merged[k] = row[k]
            rows[i] = merged
            save_rows(home, rows)
            return merged
    rows.append(row)
    save_rows(home, rows)
    return row


def digest_section(home: Path) -> dict[str, Any]:
    """Compact digest payload: recent per-PR totals + by-model rollup (no secrets)."""
    rows = load_rows(home)
    summary = summarize(rows)
    return {
        "pr_count": int(summary.get("pr_count") or 0),
        "job_count": int(summary.get("job_count") or 0),
        "per_pr": list(summary.get("per_pr") or [])[-20:],
        "by_model": list(summary.get("by_model") or []),
        "unknown_jobs": int(summary.get("unknown_jobs") or 0),
    }
