#!/usr/bin/env python3
"""FR #9847: tip merge gate then digests #9830+#9148 then walrus rebuild.

CAST IRON sequence (Si 2026-11-24):
  (1) all tip Jeeves PRs in the fixed cohort merge
  (2) digests #9830 and #9148 + recorded children CLOSED
  (3) only then rebuild Jeeves + Slab-install walrus

EXIT 0: OK_FOR_RECEIPT (every gate proven complete).
EXIT 1: NO_INSTALL (any open / closed-unmerged / unknown / empty cohort).

Token-free: unauthenticated public REST, or
``JEEVES_MONITOR_TIP_MERGE_GATE_FIXTURE`` JSON for tests. Never returns soft_ok.
Does not call !build, install, or WinRM.
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

# Fixed tip PR cohort open at Si's lock 2026-11-24 (TipPrByFr / tip-path evidence).
# Keep in sync with jeeves/docs/ARM_JEEVES_PRS_THEN_9830_9148_WALRUS.md.
DEFAULT_TIP_PRS: tuple[int, ...] = (9788, 9789, 9829, 9834, 9839, 9842)

DEFAULT_DIGESTS: tuple[int, ...] = (9830, 9148)

# Children recorded on each digest body at lock / unhold planning time.
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

_UA = "BobiverseTipMergeGate/1.0 (+https://github.com/SimonBarnett/bobiverse)"


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
            int(x.strip()) for x in kids_s.split("|") if x.strip().isdigit() or x.strip().lstrip("-").isdigit()
        )
        out[dig] = kids
    return out or None


def classify_pr(doc: Mapping[str, Any] | None) -> str:
    """Return merged|open|closed_unmerged|unknown."""
    if not isinstance(doc, Mapping):
        return "unknown"
    merged = bool(doc.get("merged")) or bool(doc.get("merged_at"))
    state = str(doc.get("state") or "").strip().lower()
    if merged:
        return "merged"
    if state == "open":
        return "open"
    if state in ("closed", "close"):
        return "closed_unmerged"
    return "unknown"


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
    tip_prs: Sequence[int],
    digests: Sequence[int],
    digest_children: Mapping[int, Sequence[int]],
    pr_states: Mapping[int, str],
    issue_states: Mapping[int, str],
) -> dict[str, Any]:
    """Pure gate. Fail closed unless every item is a proven pass."""
    reasons: list[str] = []
    findings: list[str] = []
    tip_detail: dict[str, str] = {}
    digest_detail: dict[str, str] = {}
    child_detail: dict[str, str] = {}

    if not tip_prs:
        reasons.append("cohort_undefined")
        findings.append("TIP_PRS cohort empty — refuse OK_FOR_RECEIPT")
        return {
            "verdict": "NO_INSTALL",
            "step": 1,
            "reasons": reasons,
            "findings": findings,
            "tip_prs": tip_detail,
            "digests": digest_detail,
            "children": child_detail,
            "ok": False,
        }

    step1_done = True
    for n in tip_prs:
        st = str(pr_states.get(int(n)) or "unknown")
        tip_detail[str(n)] = st
        if st == "merged":
            continue
        step1_done = False
        if st == "open":
            reasons.append("tip_pr_open")
            findings.append(f"tip PR #{n} still open")
        elif st == "closed_unmerged":
            reasons.append("tip_pr_closed_unmerged")
            findings.append(f"tip PR #{n} closed without merge")
        else:
            reasons.append("state_unknown")
            findings.append(f"tip PR #{n} state unknown")

    if not step1_done:
        # de-dupe reason codes while preserving order
        uniq: list[str] = []
        for r in reasons:
            if r not in uniq:
                uniq.append(r)
        return {
            "verdict": "NO_INSTALL",
            "step": 1,
            "reasons": uniq,
            "findings": findings,
            "tip_prs": tip_detail,
            "digests": digest_detail,
            "children": child_detail,
            "ok": False,
        }

    step2_done = True
    for d in digests:
        st = str(issue_states.get(int(d)) or "unknown")
        digest_detail[str(d)] = st
        if st == "closed":
            pass
        else:
            step2_done = False
            if st == "open":
                reasons.append("digest_open")
                findings.append(f"digest #{d} still open")
            else:
                reasons.append("state_unknown")
                findings.append(f"digest #{d} state unknown")
        for c in digest_children.get(int(d), ()):
            cst = str(issue_states.get(int(c)) or "unknown")
            child_detail[str(c)] = cst
            if cst == "closed":
                continue
            step2_done = False
            if cst == "open":
                reasons.append("digest_child_open")
                findings.append(f"digest #{d} child #{c} still open")
            else:
                reasons.append("state_unknown")
                findings.append(f"digest #{d} child #{c} state unknown")

    uniq2: list[str] = []
    for r in reasons:
        if r not in uniq2:
            uniq2.append(r)

    if not step2_done:
        return {
            "verdict": "NO_INSTALL",
            "step": 2,
            "reasons": uniq2,
            "findings": findings,
            "tip_prs": tip_detail,
            "digests": digest_detail,
            "children": child_detail,
            "ok": False,
        }

    return {
        "verdict": "OK_FOR_RECEIPT",
        "step": 3,
        "reasons": [],
        "findings": [],
        "tip_prs": tip_detail,
        "digests": digest_detail,
        "children": child_detail,
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
    tip_prs: Sequence[int],
    digests: Sequence[int],
    digest_children: Mapping[int, Sequence[int]],
) -> tuple[dict[int, str], dict[int, str], list[str]]:
    pr_states: dict[int, str] = {}
    issue_states: dict[int, str] = {}
    http_errors: list[str] = []
    owner, name = repo.split("/", 1)
    for n in tip_prs:
        doc, err = _http_json(f"https://api.github.com/repos/{owner}/{name}/pulls/{int(n)}")
        if err:
            http_errors.append(f"pr#{n}:{err}")
            pr_states[int(n)] = "unknown"
        else:
            pr_states[int(n)] = classify_pr(doc)
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
    return pr_states, issue_states, http_errors


def _load_fixture(path: str) -> tuple[dict[int, str], dict[int, str]]:
    doc = json.loads(open(path, encoding="utf-8").read())
    pr_states: dict[int, str] = {}
    issue_states: dict[int, str] = {}
    for key, val in (doc.get("prs") or {}).items():
        n = int(key)
        if isinstance(val, Mapping):
            pr_states[n] = classify_pr(val)
        else:
            pr_states[n] = str(val)
    for key, val in (doc.get("issues") or {}).items():
        n = int(key)
        if isinstance(val, Mapping):
            issue_states[n] = classify_issue(val)
        else:
            st = str(val).strip().lower()
            issue_states[n] = st if st in ("open", "closed", "unknown") else classify_issue({"state": val})
    return pr_states, issue_states


def _config() -> tuple[str, list[int], list[int], dict[int, tuple[int, ...]]]:
    repo = (os.environ.get("JEEVES_MONITOR_TIP_MERGE_GATE_REPO") or DEFAULT_REPO).strip()
    tip = _parse_int_list(os.environ.get("JEEVES_MONITOR_TIP_MERGE_GATE_TIP_PRS"))
    digs = _parse_int_list(os.environ.get("JEEVES_MONITOR_TIP_MERGE_GATE_DIGESTS"))
    kids = _parse_children_env(os.environ.get("JEEVES_MONITOR_TIP_MERGE_GATE_CHILDREN"))
    return (
        repo,
        list(tip) if tip is not None else list(DEFAULT_TIP_PRS),
        list(digs) if digs is not None else list(DEFAULT_DIGESTS),
        dict(kids) if kids is not None else {k: tuple(v) for k, v in DEFAULT_DIGEST_CHILDREN.items()},
    )


def check(args: Any) -> tuple[dict[str, Any], int]:
    repo, tip_prs, digests, digest_children = _config()
    fix = (os.environ.get("JEEVES_MONITOR_TIP_MERGE_GATE_FIXTURE") or "").strip()
    http_errors: list[str] = []
    source = "live"
    observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if fix:
        source = "fixture"
        try:
            pr_states, issue_states = _load_fixture(fix)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            payload = {
                "ok": False,
                "verdict": "NO_INSTALL",
                "step": 1,
                "reasons": ["state_unknown"],
                "findings": [f"fixture read failed: {type(exc).__name__}"],
                "fr": 9847,
                "source": "fixture",
                "auth": "none",
                "observed_at": observed_at,
                "http_errors": [str(exc)],
                "soft_ok": False,
            }
            return payload, EXIT_FINDING
        # Missing fixture rows => unknown (fail closed).
        for n in tip_prs:
            pr_states.setdefault(int(n), "unknown")
        need_issues = set(int(x) for x in digests)
        for kids in digest_children.values():
            need_issues.update(int(x) for x in kids)
        for n in need_issues:
            issue_states.setdefault(int(n), "unknown")
    else:
        pr_states, issue_states, http_errors = _live_fetch(repo, tip_prs, digests, digest_children)

    ev = evaluate_gate(
        tip_prs=tip_prs,
        digests=digests,
        digest_children=digest_children,
        pr_states=pr_states,
        issue_states=issue_states,
    )
    # Any http error forces unknown path already; still surface them.
    if http_errors and ev["verdict"] == "OK_FOR_RECEIPT":
        # Should not happen (unknowns block), belt-and-braces fail closed.
        ev = {
            **ev,
            "verdict": "NO_INSTALL",
            "ok": False,
            "step": min(int(ev.get("step") or 1), 2),
            "reasons": list(ev.get("reasons") or []) + ["state_unknown"],
            "findings": list(ev.get("findings") or []) + list(http_errors),
        }

    payload = {
        "ok": bool(ev["ok"]),
        "verdict": ev["verdict"],
        "step": ev["step"],
        "reasons": ev["reasons"],
        "findings": ev["findings"],
        "tip_prs": ev["tip_prs"],
        "digests": ev["digests"],
        "children": ev["children"],
        "fr": 9847,
        "repo": repo,
        "source": source,
        "auth": "none",
        "observed_at": observed_at,
        "http_errors": http_errors,
        "soft_ok": False,
        "arm": "jeeves/docs/ARM_JEEVES_PRS_THEN_9830_9148_WALRUS.md",
        "hint": (
            "Attach this live OK_FOR_RECEIPT JSON to the build/install receipt"
            if ev["ok"]
            else "NO_INSTALL — do not !build / -SiYes / install receipt (see ARM)"
        ),
    }
    return payload, EXIT_OK if ev["ok"] else EXIT_FINDING


def main(argv=None) -> int:
    return run_check(
        "tip_merge_gate",
        "FR #9847 tip PR merge + digest #9830/#9148 gate before walrus rebuild",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
