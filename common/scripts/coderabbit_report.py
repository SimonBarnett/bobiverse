"""FR #5865: per-PR CodeRabbit / MRB token measurement for the digest report."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def make_row(
    *,
    pr: str,
    seat: str = "",
    cr_mode: str = "off",
    review: str = "full",
    tokens: int = 0,
    cr_findings: int = 0,
    fixed: int = 0,
    rejected: int = 0,
    na: int = 0,
) -> dict[str, Any]:
    return {
        "pr": str(pr or ""),
        "seat": str(seat or ""),
        "cr_mode": str(cr_mode or "off").strip().lower(),
        "review": str(review or "full").strip().lower(),
        "tokens": int(tokens or 0),
        "cr_findings": int(cr_findings or 0),
        "fixed": int(fixed or 0),
        "rejected": int(rejected or 0),
        "na": int(na or 0),
    }


def _median(vals: list[int]) -> int:
    if not vals:
        return 0
    ordered = sorted(vals)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return int(ordered[mid])
    return int((ordered[mid - 1] + ordered[mid]) // 2)


def summarize(rows: Iterable[dict] | None) -> dict[str, Any]:
    """Running comparison: light vs full median/total tokens and CodeRabbit-fix count."""
    light_tokens: list[int] = []
    full_tokens: list[int] = []
    fixed_total = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        review = str(row.get("review") or "").strip().lower()
        tok = int(row.get("tokens") or 0)
        if review == "light":
            light_tokens.append(tok)
        else:
            full_tokens.append(tok)
        fixed_total += int(row.get("fixed") or 0)
    return {
        "light": {
            "count": len(light_tokens),
            "median_tokens": _median(light_tokens),
            "total_tokens": int(sum(light_tokens)),
        },
        "full": {
            "count": len(full_tokens),
            "median_tokens": _median(full_tokens),
            "total_tokens": int(sum(full_tokens)),
        },
        "coderabbit_fix_count": int(fixed_total),
    }


def append_row(store: list[dict], row: dict) -> list[dict]:
    """Append a normalized row onto an in-memory / digest list."""
    store.append(make_row(**{k: row.get(k) for k in (
        "pr", "seat", "cr_mode", "review", "tokens",
        "cr_findings", "fixed", "rejected", "na",
    )}))
    return store


def report_path(home: Path) -> Path:
    return Path(home) / "coderabbit-mrb-report.json"


def load_rows(home: Path) -> list[dict]:
    path = report_path(home)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("rows") if isinstance(data, dict) else data
    return [r for r in (rows or []) if isinstance(r, dict)]


def save_rows(home: Path, rows: list[dict]) -> None:
    path = report_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)
    payload = {"rows": list(rows)[-500:], "summary": summary}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def record_done(
    home: Path,
    *,
    repo: str,
    ident: str,
    seat: str = "",
    rest: str = "",
) -> dict[str, Any]:
    """Append one DONE MRB measurement row from shop rest tokens."""
    try:
        import shop_listen
    except Exception:
        shop_listen = None  # type: ignore
    meta = shop_listen.mrb_cr_meta(rest) if shop_listen else {}
    counters = shop_listen.mrb_cr_counters(rest) if shop_listen else {}
    # Prefer new fixed/rejected/na; fall back to confirmed/fp.
    fixed = int(counters.get("fixed") or counters.get("confirmed") or 0)
    rejected = int(counters.get("rejected") or counters.get("fp") or 0)
    row = make_row(
        pr=f"{repo}{ident}",
        seat=seat,
        cr_mode=str(meta.get("cr_mode") or "off"),
        review=str(meta.get("review") or "full"),
        tokens=int(meta.get("tokens") or counters.get("tokens") or 0),
        cr_findings=int(counters.get("cr_findings") or 0),
        fixed=fixed,
        rejected=rejected,
        na=int(counters.get("na") or 0),
    )
    rows = load_rows(home)
    rows.append(row)
    save_rows(home, rows)
    return row
