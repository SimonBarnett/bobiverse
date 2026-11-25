#!/usr/bin/env python3
"""FR #9877: digest-level CI/build only after all digest children CLOSED.

CAST IRON (Si 2026-11-24): for an ``fr-digest`` batch, digest covering /
omnibus CI, tip rebuild + walrus install driven by that digest, unhold→drain
completion CI, and any workflow that treats the digest as ready-to-ship must
wait until **every** Depends-on child under that digest is CLOSED. Digests are
go-gates (#9552). Child FRs may still open PRs and run **per-child** CI.

Complementary to ``tip_merge_gate`` (FR #9847), which also requires a tip PR
cohort merge before walrus rebuild. This check is **children-only** (no tip
cohort) so operators can gate digest-level ``!build`` / release receipts
without waiting on unrelated tip PRs.

EXIT 0: ``ALLOW_DIGEST_CI`` (every recorded child CLOSED).
EXIT 1: ``BLOCK_DIGEST_CI`` (any open / unknown / empty cohort).

Token-free: unauthenticated public REST, or
``JEEVES_MONITOR_DIGEST_CI_GATE_FIXTURE`` JSON for tests. Never returns soft_ok.
Does not call ``!build``, install, or WinRM.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from _common import EXIT_FINDING, EXIT_OK, run_check

DEFAULT_REPO = "SimonBarnett/bobiverse"

# Align with live tip digests / ARM children (FR #9847). Override via env.
DEFAULT_DIGESTS: tuple[int, ...] = (9830, 9148)

DEFAULT_DIGEST_CHILDREN: dict[int, tuple[int, ...]] = {
    9830: (
        9831,
        9832,
        9833,
        9835,
        9836,
        9837,
        9838,
        9846,
        9847,
        9848,
        9849,
        9850,
        9854,
        9855,
        9861,
        9862,
        9863,
        9864,
        9865,
        9867,
        9871,
        9872,
        9875,
        9877,
        9878,
        9879,
        9880,
        9881,
        9882,
    ),
    9148: (8775, 8777, 8778, 8780, 8781, 8782, 8783, 8784),
}

_UA = "BobiverseDigestCiGate/1.0 (+https://github.com/SimonBarnett/bobiverse)"


def _parse_int_list(raw: str | None) -> list[int] | None:
    if raw is None or not str(raw).strip():
        return None
    out: list[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


def _parse_children_env(raw: str | None) -> dict[int, tuple[int, ...]] | None:
    """``9830:9831|9832;9148:8775|8777`` shape."""
    if raw is None or not str(raw).strip():
        return None
    out: dict[int, tuple[int, ...]] = {}
    for block in str(raw).split(";"):
        block = block.strip()
        if not block or ":" not in block:
            continue
        dig_s, kids_s = block.split(":", 1)
        dig = int(dig_s.strip())
        kids = tuple(
            int(x.strip())
            for x in kids_s.split("|")
            if x.strip().isdigit() or x.strip().lstrip("-").isdigit()
        )
        out[dig] = kids
    return out or None


def classify_issue(doc: Mapping[str, Any] | None) -> str:
    if not isinstance(doc, Mapping):
        return "unknown"
    state = str(doc.get("state") or "").strip().lower()
    if state == "closed":
        return "closed"
    if state == "open":
        return "open"
    return "unknown"


def evaluate_gate(
    *,
    digests: Sequence[int],
    digest_children: Mapping[int, Sequence[int]],
    issue_states: Mapping[int, str],
) -> dict[str, Any]:
    """Pure gate. Fail closed unless every recorded child is CLOSED."""
    reasons: list[str] = []
    findings: list[str] = []
    digest_detail: dict[str, str] = {}
    child_detail: dict[str, str] = {}
    open_children: list[int] = []

    if not digests:
        reasons.append("cohort_undefined")
        findings.append("DIGESTS cohort empty — refuse ALLOW_DIGEST_CI")
        return {
            "verdict": "BLOCK_DIGEST_CI",
            "reasons": reasons,
            "findings": findings,
            "digests": digest_detail,
            "children": child_detail,
            "open_children": open_children,
            "ok": False,
        }

    ok = True
    for d in digests:
        st = str(issue_states.get(int(d)) or "unknown")
        digest_detail[str(d)] = st
        kids = tuple(digest_children.get(int(d), ()))
        if not kids:
            ok = False
            reasons.append("children_undefined")
            findings.append(f"digest #{d} has empty recorded children — refuse ALLOW_DIGEST_CI")
            continue
        for c in kids:
            cst = str(issue_states.get(int(c)) or "unknown")
            child_detail[str(c)] = cst
            if cst == "closed":
                continue
            ok = False
            if cst == "open":
                reasons.append("digest_child_open")
                findings.append(f"digest #{d} child #{c} still open")
                open_children.append(int(c))
            else:
                reasons.append("state_unknown")
                findings.append(f"digest #{d} child #{c} state unknown")

    uniq: list[str] = []
    for r in reasons:
        if r not in uniq:
            uniq.append(r)

    if not ok:
        return {
            "verdict": "BLOCK_DIGEST_CI",
            "reasons": uniq,
            "findings": findings,
            "digests": digest_detail,
            "children": child_detail,
            "open_children": open_children,
            "ok": False,
        }

    return {
        "verdict": "ALLOW_DIGEST_CI",
        "reasons": [],
        "findings": [],
        "digests": digest_detail,
        "children": child_detail,
        "open_children": [],
        "ok": True,
    }


def _http_json(url: str, timeout: float = 30.0) -> tuple[dict[str, Any] | None, str | None]:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return None, f"{type(e).__name__}"


def _live_fetch(
    repo: str,
    digests: Sequence[int],
    digest_children: Mapping[int, Sequence[int]],
) -> tuple[dict[int, str], list[str]]:
    issue_states: dict[int, str] = {}
    http_errors: list[str] = []
    owner, name = repo.split("/", 1)
    issue_nums = set(int(x) for x in digests)
    for kids in digest_children.values():
        issue_nums.update(int(x) for x in kids)
    for n in sorted(issue_nums):
        doc, err = _http_json(f"https://api.github.com/repos/{owner}/{name}/issues/{int(n)}")
        if err:
            http_errors.append(f"issue#{n}:{err}")
            issue_states[int(n)] = "unknown"
        else:
            issue_states[int(n)] = classify_issue(doc)
    return issue_states, http_errors


def _load_fixture(path: str) -> dict[int, str]:
    doc = json.loads(open(path, encoding="utf-8").read())
    issue_states: dict[int, str] = {}
    for key, val in (doc.get("issues") or {}).items():
        n = int(key)
        if isinstance(val, Mapping):
            issue_states[n] = classify_issue(val)
        else:
            st = str(val).strip().lower()
            issue_states[n] = st if st in ("open", "closed", "unknown") else classify_issue({"state": val})
    return issue_states


def _config() -> tuple[str, list[int], dict[int, tuple[int, ...]]]:
    repo = (os.environ.get("JEEVES_MONITOR_DIGEST_CI_GATE_REPO") or DEFAULT_REPO).strip()
    digs = _parse_int_list(os.environ.get("JEEVES_MONITOR_DIGEST_CI_GATE_DIGESTS"))
    kids = _parse_children_env(os.environ.get("JEEVES_MONITOR_DIGEST_CI_GATE_CHILDREN"))
    return (
        repo,
        list(digs) if digs is not None else list(DEFAULT_DIGESTS),
        dict(kids) if kids is not None else {k: tuple(v) for k, v in DEFAULT_DIGEST_CHILDREN.items()},
    )


def check(args: Any) -> tuple[dict[str, Any], int]:
    repo, digests, digest_children = _config()
    fix = (os.environ.get("JEEVES_MONITOR_DIGEST_CI_GATE_FIXTURE") or "").strip()
    http_errors: list[str] = []
    source = "live"
    observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if fix:
        source = "fixture"
        try:
            issue_states = _load_fixture(fix)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            payload = {
                "ok": False,
                "verdict": "BLOCK_DIGEST_CI",
                "reasons": ["state_unknown"],
                "findings": [f"fixture read failed: {type(exc).__name__}"],
                "fr": 9877,
                "source": "fixture",
                "auth": "none",
                "observed_at": observed_at,
                "http_errors": [str(exc)],
                "soft_ok": False,
            }
            return payload, EXIT_FINDING
        need_issues = set(int(x) for x in digests)
        for kids in digest_children.values():
            need_issues.update(int(x) for x in kids)
        for n in need_issues:
            issue_states.setdefault(int(n), "unknown")
    else:
        issue_states, http_errors = _live_fetch(repo, digests, digest_children)

    ev = evaluate_gate(
        digests=digests,
        digest_children=digest_children,
        issue_states=issue_states,
    )
    if http_errors and ev["verdict"] == "ALLOW_DIGEST_CI":
        ev = {
            **ev,
            "verdict": "BLOCK_DIGEST_CI",
            "ok": False,
            "reasons": list(ev.get("reasons") or []) + ["state_unknown"],
            "findings": list(ev.get("findings") or []) + list(http_errors),
        }

    payload = {
        "ok": bool(ev["ok"]),
        "verdict": ev["verdict"],
        "reasons": ev["reasons"],
        "findings": ev["findings"],
        "digests": ev["digests"],
        "children": ev["children"],
        "open_children": ev["open_children"],
        "fr": 9877,
        "repo": repo,
        "source": source,
        "auth": "none",
        "observed_at": observed_at,
        "http_errors": http_errors,
        "soft_ok": False,
        "docs": "jeeves/docs/fr-digest-vs-hold-vs-depends-on.md",
        "hint": (
            "Attach this live ALLOW_DIGEST_CI JSON before digest-level !build / covering CI / install receipt"
            if ev["ok"]
            else "BLOCK_DIGEST_CI — do not stamp digest covering CI / !build / ready-to-install while children open"
        ),
    }
    return payload, EXIT_OK if ev["ok"] else EXIT_FINDING


def main(argv=None) -> int:
    return run_check(
        "digest_ci_gate",
        "FR #9877 digest-level CI/build only after all digest children CLOSED",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
