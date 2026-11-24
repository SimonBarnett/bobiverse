#!/usr/bin/env python3
"""FR #9585: public PUT /bob/v1/models must reach bobcallback (Weights Save).

Live class 2026-11-24: GET 200 JSON, PUT IIS HTML 404 (BobModelsWebhook still on
ungrouped ^GET|HEAD|POST$ omitting PUT — FR #9273 tip already fixed Install-BobWebhooks;
walrus IIS was not re-run). TipForm Weights Save then fails with status=404.

EXIT 0: PUT reached backend (2xx / 400 / 401 / 403 JSON) or soft-skip when
  fixture/env says skip / probe transport failed without IIS HTML 404.
EXIT 1: IIS HTML 404 (or empty 404) — Weights Save will fail until
  ``Install-BobWebhooks.ps1`` upserts BobModelsWebhook with ^(GET|HEAD|POST|PUT)$.
EXIT 2: bad fixture.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from _common import EXIT_ERROR, EXIT_FINDING, EXIT_OK, run_check

DEFAULT_MODELS_URL = "https://bob.ntsa.uk/bob/v1/models"
_HTTP_TIMEOUT_S = 20.0
# Cloudflare blocks Python-urllib default UA (class of intake_allowlist FR #8861).
_PROBE_USER_AGENT = "BobiverseModelsPutForward/1.0 (+https://github.com/SimonBarnett/bobiverse)"
_IIS_HTML_404_MARKERS = (
    "file or directory not found",
    "<!doctype html",
    "<title>404",
    "404 - file or directory not found",
)
# Backend statuses that prove the rewrite reached bobcallback (peer/body gates OK).
_BACKEND_REACHED = frozenset({200, 201, 204, 400, 401, 403})


def models_url() -> str:
    raw = (os.environ.get("BOB_MODELS_URL") or "").strip()
    return raw or DEFAULT_MODELS_URL


def _is_iis_html_404(status: int, body: str) -> bool:
    if int(status) != 404:
        return False
    low = (body or "").lower()
    if not low.strip():
        # Empty 404 from rewrite miss is the same class as HTML 404 for operators.
        return True
    return any(m in low for m in _IIS_HTML_404_MARKERS)


def classify_put_result(status: int, body: str, *, reason: str = "") -> dict[str, Any]:
    """Classify one PUT probe (FR #9585 / #9273)."""
    status_i = int(status)
    snippet = (body or "").strip().replace("\n", " ")[:160]
    if _is_iis_html_404(status_i, body or ""):
        return {
            "http_status": status_i,
            "reached_backend": False,
            "iis_html_404": True,
            "detail": snippet or reason or "iis_html_404",
        }
    if status_i in _BACKEND_REACHED:
        return {
            "http_status": status_i,
            "reached_backend": True,
            "iis_html_404": False,
            "detail": snippet or reason or f"status={status_i}",
        }
    # Other 404 JSON from bobcallback (unknown route) still means rewrite worked.
    err = ""
    try:
        parsed = json.loads(body) if body else {}
        if isinstance(parsed, dict):
            err = str(parsed.get("error") or "")
    except json.JSONDecodeError:
        parsed = {}
    if status_i == 404 and err:
        return {
            "http_status": status_i,
            "reached_backend": True,
            "iis_html_404": False,
            "detail": err or snippet,
        }
    if 200 <= status_i < 500:
        return {
            "http_status": status_i,
            "reached_backend": True,
            "iis_html_404": False,
            "detail": snippet or reason or f"status={status_i}",
        }
    return {
        "http_status": status_i,
        "reached_backend": False,
        "iis_html_404": False,
        "probe_error": True,
        "detail": snippet or reason or f"http_{status_i}",
    }


def probe_put(
    url: str,
    *,
    opener: Optional[Callable[..., Any]] = None,
    body: bytes | None = None,
) -> dict[str, Any]:
    """No-op empty agents PUT — never persists a real Weights matrix."""
    payload = body if body is not None else b'{"agents":[]}'
    req = urllib.request.Request(
        url,
        data=payload,
        method="PUT",
        headers={
            "Content-Type": "application/json",
            "User-Agent": _PROBE_USER_AGENT,
            "Accept": "application/json",
        },
    )
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=_HTTP_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return classify_put_result(int(getattr(resp, "status", 200) or 200), raw)
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        return classify_put_result(int(e.code), raw, reason=str(e.reason or ""))
    except Exception as e:  # noqa: BLE001 — transport soft-skip
        return {
            "http_status": 0,
            "reached_backend": False,
            "iis_html_404": False,
            "probe_error": True,
            "detail": f"transport:{type(e).__name__}:{e}",
        }


def check(args: Any, opener: Optional[Callable[..., Any]] = None) -> tuple[dict[str, Any], int]:
    if os.environ.get("JEEVES_MODELS_PUT_FORWARD_SKIP", "").strip() in {"1", "true", "yes"}:
        return (
            {
                "ok": True,
                "skipped": "JEEVES_MODELS_PUT_FORWARD_SKIP",
                "findings": [],
                "remediation": "",
            },
            EXIT_OK,
        )

    fixture = (os.environ.get("JEEVES_MODELS_PUT_FORWARD_FIXTURE") or "").strip()
    if fixture:
        path = Path(fixture)
        if not path.is_file():
            return (
                {
                    "ok": False,
                    "error": f"fixture missing: {fixture}",
                    "findings": [f"fixture missing: {fixture}"],
                },
                EXIT_ERROR,
            )
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError) as e:
            return (
                {
                    "ok": False,
                    "error": f"fixture unreadable: {e}",
                    "findings": [f"fixture unreadable: {e}"],
                },
                EXIT_ERROR,
            )
        if not isinstance(doc, dict):
            return (
                {"ok": False, "error": "fixture not object", "findings": ["fixture not object"]},
                EXIT_ERROR,
            )
        status = int(doc.get("http_status") or doc.get("status") or 0)
        body = str(doc.get("body") or "")
        row = classify_put_result(status, body, reason=str(doc.get("reason") or "fixture"))
        url = str(doc.get("url") or models_url())
    else:
        url = models_url()
        row = probe_put(url, opener=opener)

    findings: list[str] = []
    remediation = ""
    if row.get("iis_html_404"):
        findings.append(
            f"PUT {url} IIS HTML 404 (BobModelsWebhook drops PUT) — Weights Save fails"
        )
        remediation = (
            "On the IIS chair (walrus): re-run jeeves/scripts/Install-BobWebhooks.ps1 so "
            "BobModelsWebhook uses pattern ^(GET|HEAD|POST|PUT)$ (FR #9273 / #9585). "
            "Confirm post-install PUT probe is not IIS HTML 404. TipForm keeps edits on "
            "non-2xx; headless --weights-save for round-trip."
        )
    elif row.get("probe_error") and not row.get("reached_backend"):
        # Transport / 5xx: soft-ok (do not false-alarm when Cloudflare/backend flap).
        return (
            {
                "ok": True,
                "skipped": "probe_error",
                "models_url": url,
                "probe": row,
                "findings": [],
                "remediation": (
                    "PUT probe transport/5xx — not classified as IIS HTML 404; retry later."
                ),
                "notes": [str(row.get("detail") or "probe_error")],
            },
            EXIT_OK,
        )

    ok = not findings and bool(row.get("reached_backend"))
    if not ok and not findings and not row.get("reached_backend"):
        findings.append(f"PUT {url} did not reach bobcallback: {row.get('detail')}")
        remediation = (
            "Re-run Install-BobWebhooks.ps1 on the IIS chair; ensure BobCallback :7700 is up."
        )

    return (
        {
            "ok": ok,
            "models_url": url,
            "probe": row,
            "findings": findings,
            "remediation": remediation,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "models_put_forward",
        "PUT /bob/v1/models reaches bobcallback (Weights Save; FR #9585)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
