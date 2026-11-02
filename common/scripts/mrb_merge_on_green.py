"""FR #3948: MRB merge-on-green handoff — seats DONE after PASS+SHA; Jeeves merges when green.

Seats never poll CI. After hostile review + local tests + own pushes they post
MRB PASS with the head SHA, optionally enable GitHub auto-merge, and DONE.
When ``allow_auto_merge`` is off (or ``--auto`` fails), Jeeves keeps a
``merge_on_green`` ledger and merges (or re-queues) once checks settle on the
PASSed SHA. Held PRs are never auto-merged (FR #3928).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import gitclaim
import mrb_merge_gate

LEDGER_NAME = "merge-on-green.json"
SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b", re.I)
PASS_SHA_RE = re.compile(
    r"(?i)(?:MRB\s+PASS\s*@\s*|merge-on-green\s+pending[^\n]{0,120}?|"
    r"head(?:Ref)?(?:Oid)?\s*[:=]\s*|pass(?:ed)?\s+sha\s*[:=]\s*)"
    r"([0-9a-f]{7,40})"
)
# FR #4718: an MRB FAIL board names the head it refused. Only this form, not a
# later PASS or a merge-on-green line.
FAIL_SHA_RE = re.compile(r"(?i)MRB\s+FAIL\s*@\s*([0-9a-f]{7,40})")
PASS_BOARD_RE = re.compile(r"(?i)MRB\s+PASS\s*@\s*([0-9a-f]{7,40})")

Decision = str  # merge | wait | requeue_sha | requeue_ci | skip_hold | drop_merged | drop_closed

# FR #4543: leave headroom for pr_exists / !resync / offers when the sweep is large.
DEFAULT_MIN_RATE_REMAINING = 100
# FR #4566: stop re-polling Actions-only rows forever. Empty combined status is
# not a pending check. Long waits back off, then leave the ledger.
MAX_WAIT_S = 3600
# FR #4566 follow-up: a PASSed PR whose required check-run failed leaves the poll
# list but keeps its PASS SHA here so resync's ci-wait skip still recognises it
# (no MRB re-queue while the head is unchanged). FR #4706: when the tip advances
# and fails again, refresh_ci_failed_tips / check_run re-offer FIX for the new SHA
# without waiting for !resync.
CI_FAILED_KEY = "ci_failed"
# FR #4585/#4596: FIX ledger keyed by failure_signature (shared when main red; per-PR otherwise).
CI_FIX_KEY = "ci_fix"
# FR #4636: DIRTY/CONFLICTING or HTTP 405 stops merge retries for this PR+SHA.
CONFLICT_KEY = "conflict_blocked"
CONFLICT_FIX_KEY = "conflict_fix"
# FR #4718: FIX for an open PR whose newest MRB board is FAIL at the live head.
MRB_FAIL_FIX_KEY = "mrb_fail_fix"
# FR #4800: harvest light-triage dispositions (FAIL-supersede / CLOSED / MOVED).
# These tips close unmerged and must DONE PASS; chair must not enqueue FIX.
HARVEST_FAIL_DISPOSITION_RE = re.compile(
    r"(?i)\bFAIL[- ]superseded?\b|\bMRB\s+CLOSED\b|\bMRB\s+MOVED\b|"
    r"\bnot-useful\b|\bplan-content\b"
)

# FR #4639: in-flight cancelled-CI re-runs. Cap is whiterabbit + madhatter (7).
CI_RERUN_KEY = "ci_rerun"
CI_RERUN_CAP = 7
# FR #4669: DONE FIX with the same head SHA is not a permanent duplicate.
# After this many re-offers, stamp needs_human so the row stays visible.
FIX_CI_RECOVER_MAX = 2
CI_FAILED_TTL_S = 14 * 24 * 3600
# FR #4706: how often process_pending re-GETs a parked CI-failed tip.
# check_run failures bypass this and re-offer immediately.
CI_FAILED_REFRESH_S = 300
BACKOFF_BASE_S = 60
BACKOFF_CAP_S = 900
_FAIL_CONCLUSIONS = frozenset(
    {
        "failure",
        "timed_out",
        "cancelled",
        "canceled",
        "action_required",
    }
)
# FR #4630: bulk cancel waves are not per-PR CI debt.
_CANCEL_CONCLUSIONS = frozenset({"cancelled", "canceled"})
# Shared suite name(s) — tip + main both red → skip tip FIX (prefer one main-side fix).
_SHARED_SUITE_MARKERS = ("test-and-synth", "test_and_synth", "testandsynth")
# FR #4833: assert-lock / lock check needs Simon's simon-approved-rule-change label.
# Exact name ``lock`` or any assert-lock marker — seats must never forge that label.
_HUMAN_GATED_LOCK_MARKERS = ("assert-lock", "assert_lock")
HUMAN_GATED_LOCK_REASON = "needs-human: add simon-approved-rule-change"


def _utc() -> str:
    return gitclaim._utc_now()


def combined_status_is_empty(status: dict | None) -> bool:
    """True when the commit has no classic statuses.

    GitHub Actions-only repos return ``state: pending`` with ``statuses: []``.
    That is not an in-progress check (FR #4566).
    """
    if not isinstance(status, dict):
        return True
    statuses = status.get("statuses")
    if isinstance(statuses, list) and len(statuses) == 0:
        return True
    state = str(status.get("state") or "").strip().lower()
    return state in ("", "none")


def _normalize_check_detail(detail: str) -> str:
    raw = str(detail or "").strip().lower().replace(" ", "")
    if raw.startswith("completed/"):
        return raw.split("/", 1)[-1]
    return raw


def _detail_names_shared_suite(detail: str) -> bool:
    """True when detail names the shared suite (e.g. failure:test-and-synth)."""
    compact = _normalize_check_detail(detail).replace("_", "-").replace("|", ":")
    return any(m.replace("_", "-") in compact for m in _SHARED_SUITE_MARKERS)


def _detail_names_human_gated_lock(detail: str) -> bool:
    """True when detail names the assert-lock / lock human gate (FR #4833)."""
    compact = _normalize_check_detail(detail).replace("_", "-").replace("|", ":")
    if not compact:
        return False
    # Strip rollup prefixes like failure: / completed/failure:
    name = compact
    for prefix in ("completed/", "failure:", "error:"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    name = name.split(":", 1)[-1] if ":" in name else name
    if name == "lock":
        return True
    return any(m.replace("_", "-") in compact for m in _HUMAN_GATED_LOCK_MARKERS)


def shared_suite_check_name(detail: str = "") -> str:
    """Short shared-suite name from a rollup detail (default test-and-synth)."""
    compact = _normalize_check_detail(detail).replace("_", "-")
    for marker in _SHARED_SUITE_MARKERS:
        needle = marker.replace("_", "-")
        if needle in compact:
            return "test-and-synth" if "synth" in needle else needle
    return "test-and-synth"


def main_red_fix_signature(repo: str, main_sha: str, check: str = "") -> str:
    """Ledger / body fingerprint for one main-side FIX (FR #4857)."""
    repo_c = gitclaim.canonical_queue_repo(repo)
    sha = _norm_sha(main_sha)
    name = (check or "test-and-synth").strip().lower() or "test-and-synth"
    return f"main-red|{repo_c}|{sha}|{name}"


def is_main_red_fix_id(ident: str = "") -> bool:
    """True when a FIX row id is the synthetic main-side id (FR #4857)."""
    return str(ident or "").strip().lstrip("#").lower() in ("main", "main-red")


def is_main_red_fix_row(row: dict | None) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("task") or "").upper() != "FIX":
        return False
    if is_main_red_fix_id(str(row.get("id") or "")):
        return True
    sig = str(row.get("fail_signature") or "")
    return sig.startswith("main-red|")


def main_red_fix_signature_sha(row: dict | None) -> str:
    """SHA from ``main-red|<repo>|<sha>|<check>`` or row ``pass_sha`` (FR #4911)."""
    if not isinstance(row, dict):
        return ""
    sig = str(row.get("fail_signature") or "").strip()
    if sig.startswith("main-red|"):
        parts = sig.split("|")
        if len(parts) >= 3:
            return _norm_sha(parts[2])
    return _norm_sha(str(row.get("pass_sha") or ""))


def main_red_fix_obsolete(
    row: dict | None,
    *,
    main_red: bool | None = None,
    main_sha: str = "",
) -> bool:
    """True when a main-red FIX should be retired (FR #4911).

    Retire when the default branch shared suite is green again, or when the
    signature's main SHA is no longer the default-branch head.
    """
    if not is_main_red_fix_row(row):
        return False
    if main_red is False:
        return True
    head = _norm_sha(main_sha)
    row_sha = main_red_fix_signature_sha(row)
    if head and row_sha and not shas_match(row_sha, head):
        return True
    return False


def fix_ci_skip_reason(detail: str = "", *, main_red: bool = False) -> str | None:
    """FR #4630 / #4833 / #4857: why tip FIX-CI must not be offered (or None).

    * ``cancelled-only`` — tip reds are only cancelled/canceled (bulk cancel wave).
    * ``main-also-red-shared-suite`` — shared suite (test-and-synth) failed on tip
      while main's required checks are also red. Tip FIX is skipped; enqueue one
      main-side FIX instead (FR #4857).
    * ``human-gated-lock`` — only red check is ``lock`` / ``assert-lock``; only
      SimonBarnett can add ``simon-approved-rule-change`` (seats must not forge it).
    """
    state = _normalize_check_detail(detail)
    if not state:
        return None
    # Primary: cancelled / canceled (and completed/cancelled) with no hard failure token.
    head = state.split(":", 1)[0]
    # FR #4639: concurrency skip is the same class as a bulk cancel.
    if head in _CANCEL_CONCLUSIONS or head == "skipped":
        return "cancelled-only"
    # FR #4833: human-gated assert-lock (before shared-suite — lock is never seat FIX).
    if _detail_names_human_gated_lock(state):
        return "human-gated-lock"
    # Secondary: named shared suite + main also red.
    if main_red and _detail_names_shared_suite(state):
        return "main-also-red-shared-suite"
    return None


_ACTIONS_RUN_ID_RE = re.compile(r"/actions/runs/(\d+)")


def cancelled_workflow_run_id(runs: dict | list | None) -> str:
    """Workflow run id for a cancelled or skipped check, from its details URL.

    GitHub pull objects do not carry ``run_id``. Check-runs do, in
    ``details_url`` (``/actions/runs/{id}/job/...``). FR #4639.
    """
    if isinstance(runs, dict):
        items = runs.get("check_runs")
    elif isinstance(runs, list):
        items = runs
    else:
        return ""
    if not isinstance(items, list):
        return ""
    for item in items:
        if not isinstance(item, dict):
            continue
        conclusion = str(item.get("conclusion") or "").lower()
        if conclusion not in ("cancelled", "canceled", "skipped"):
            continue
        for field in ("details_url", "html_url"):
            match = _ACTIONS_RUN_ID_RE.search(str(item.get(field) or ""))
            if match:
                return match.group(1)
    return ""


def rollup_check_runs(
    runs: dict | list | None,
    *,
    ignore_coderabbit: bool = False,
) -> str:
    """Roll check-runs into success | failure | cancelled | pending | none.

    FR #4630: when every fail-like conclusion is cancelled/canceled, return
    ``cancelled`` (not ``failure``) so FIX-CI can refuse bulk-cancel waves.
    When the only hard failure is the shared suite, annotate
    ``failure:test-and-synth`` so enqueue can skip while main is also red.
    FR #4833: when the only hard failure is ``lock`` / ``assert-lock``, annotate
    ``failure:lock`` so enqueue parks needs-human instead of FIX-CI.
    FR #5865: when ``ignore_coderabbit`` is True (gate cleared / off / absent),
    CodeRabbit checks are non-blocking so a pending/neutral CR does not leave
    the PR UNSTABLE for merge-on-green.
    """
    if isinstance(runs, dict):
        items = runs.get("check_runs")
    elif isinstance(runs, list):
        items = runs
    else:
        items = None
    if not isinstance(items, list) or not items:
        return "none"
    statuses: list[str] = []
    hard: list[str] = []  # check names (or bare conclusion) for non-cancel fails
    saw_cancel = False
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if ignore_coderabbit:
            try:
                import fuel_chain

                if fuel_chain.is_coderabbit_check_name(name):
                    continue
            except Exception:
                if "coderabbit" in name.lower():
                    continue
        statuses.append(str(item.get("status") or "").lower())
        conclusion = str(item.get("conclusion") or "").lower()
        if conclusion in _CANCEL_CONCLUSIONS:
            saw_cancel = True
            continue
        if conclusion in _FAIL_CONCLUSIONS:
            hard.append(name or conclusion)
    if not statuses:
        return "none"
    if any(s != "completed" for s in statuses):
        return "pending"
    if hard:
        names = [n for n in hard if n and n not in _FAIL_CONCLUSIONS]
        if names and all(_detail_names_human_gated_lock(n) for n in names):
            return "failure:lock"
        if names and all(_detail_names_shared_suite(n) for n in names):
            return "failure:test-and-synth"
        return "failure"
    if saw_cancel:
        return "cancelled"
    return "success"


def checks_from_status_and_runs(
    status: dict | None,
    runs: dict | list | None,
    *,
    ignore_coderabbit: bool = True,
) -> str:
    """Classic status when it has entries; otherwise the check-run rollup.

    FR #5865: CodeRabbit is never a required check. Default ignore so a
    pending/neutral CodeRabbit rollup does not block merge-on-green.
    """
    if combined_status_is_empty(status):
        return rollup_check_runs(runs, ignore_coderabbit=ignore_coderabbit)
    return str((status or {}).get("state") or "none").strip().lower()


def _norm_sha(sha: str) -> str:
    return (sha or "").strip().lower()


def shas_match(a: str, b: str) -> bool:
    """True when full SHAs equal or one is a matching short prefix of the other."""
    x, y = _norm_sha(a), _norm_sha(b)
    if not x or not y:
        return False
    if x == y:
        return True
    shorter, longer = (x, y) if len(x) <= len(y) else (y, x)
    return len(shorter) >= 7 and longer.startswith(shorter)


def parse_pass_sha_from_text(text: str) -> str | None:
    """Extract the PASSed head SHA from an MRB PASS / merge-on-green comment."""
    if not text:
        return None
    m = PASS_SHA_RE.search(text)
    if m:
        return _norm_sha(m.group(1))
    return None


def parse_pass_sha_from_comments(comments: list[dict] | None) -> str | None:
    """Prefer the newest comment that names an MRB PASS / merge-on-green SHA."""
    ordered = sorted(list(comments or []), key=mrb_merge_gate._created, reverse=True)
    for c in ordered:
        sha = parse_pass_sha_from_text(mrb_merge_gate._body(c))
        if sha:
            return sha
    return None


def newest_mrb_board(comments: list[dict] | None) -> tuple[str, str] | None:
    """Newest explicit ``MRB FAIL @ sha`` or ``MRB PASS @ sha`` comment.

    Returns ``("FAIL"|"PASS", sha)`` or None. A merge-on-green line is not a board.
    """
    ordered = sorted(list(comments or []), key=mrb_merge_gate._created, reverse=True)
    for c in ordered:
        text = mrb_merge_gate._body(c)
        fail = FAIL_SHA_RE.search(text or "")
        if fail:
            return ("FAIL", _norm_sha(fail.group(1)))
        ok = PASS_BOARD_RE.search(text or "")
        if ok:
            return ("PASS", _norm_sha(ok.group(1)))
    return None



def harvest_fail_disposition_board(comments: list[dict] | None) -> bool:
    """True when comments show FAIL-supersede / CLOSED / MOVED light triage."""
    for c in comments or []:
        if isinstance(c, dict):
            body = str(c.get("body") or c.get("bodyText") or "")
        else:
            body = str(c or "")
        if HARVEST_FAIL_DISPOSITION_RE.search(body):
            return True
    return False


def skip_mrb_fail_fix_for_harvest(
    *,
    title: str = "",
    labels: tuple[str, ...] | list[str] = (),
    closed: bool = False,
    merged: bool = False,
    comments: list[dict] | None = None,
) -> bool:
    """FR #4800 / #5720: skip FIX for harvest-lesson tips closed (or disposition-boarded).

    Product MRB FAIL @ sha still queues FIX (FR #4718). Open harvest tips with a
    real ``MRB FAIL @ sha`` board (no CLOSED/FAIL-supersede disposition) still
    queue FIX so a fix PR can land.

    FR #5720: the same carve-out applies to conflict-FIX (#4636/#4679/#5581) so a
    closed FAIL-supersede harvest tip never gets ``FIX conflict`` on DONE/resync.
    """
    if merged:
        return False
    if not gitclaim.is_harvest_lesson_pr(title=title or "", labels=labels or ()):
        return False
    if closed:
        return True
    return harvest_fail_disposition_board(comments)


def linked_fail_fix_open(prs: list | None, num: str) -> bool:
    """True when another open PR is an mrb-N-fix / fix(mrb-N) for this pull."""
    want = f"#{str(num).lstrip('#')}"
    for pr in prs or []:
        if not isinstance(pr, dict):
            continue
        if str(pr.get("number") or "").lstrip("#") == str(num).lstrip("#"):
            continue
        if pr.get("draft") is True:
            continue
        state = str(pr.get("state") or "open").strip().lower()
        if state and state != "open":
            continue
        parent = gitclaim.mrb_fix_parent_pr_id(str(pr.get("title") or ""))
        if parent == want:
            return True
    return False


def mrb_fail_board_at_head(
    pr: dict,
    head_sha: str,
    ledger_rec: dict | None = None,
) -> tuple[str, str]:
    """``(sha, nick)`` when the newest board is FAIL at ``head_sha``.

    Comments on the PR win. With no comment list, a ledger stamp for that SHA
    is enough (the DONE handler wrote it). A newer PASS board returns empty.
    """
    head = _norm_sha(head_sha)
    if not head:
        return "", ""
    comments = pr.get("comments") if isinstance(pr, dict) else None
    if isinstance(comments, list):
        verdict = newest_mrb_board(comments)
        if not verdict or verdict[0] != "FAIL" or not shas_match(verdict[1], head):
            return "", ""
        nick = ""
        if isinstance(ledger_rec, dict):
            nick = str(ledger_rec.get("nick") or "")
        return verdict[1], nick
    if isinstance(ledger_rec, dict) and shas_match(str(ledger_rec.get("sha") or ""), head):
        return _norm_sha(str(ledger_rec.get("sha") or "")), str(ledger_rec.get("nick") or "")
    return "", ""


def decide_merge_on_green(
    *,
    pass_sha: str,
    current_sha: str,
    checks: str,
    hold_reason: str | None = None,
    merged: bool = False,
    closed: bool = False,
) -> Decision:
    """Pure FR #3948 / FR #4543 decision.

    ``checks`` is one of: success | failure | pending | none
    (``none`` = no required/reported checks --- treat like success when SHA matches).

    FR #4543: closed (unmerged) PRs leave the ledger so sweeps stop re-fetching them.
    """
    if merged:
        return "drop_merged"
    if closed:
        return "drop_closed"
    if hold_reason:
        return "skip_hold"
    if not pass_sha or not current_sha:
        return "wait"
    if not shas_match(pass_sha, current_sha):
        return "requeue_sha"
    state = (checks or "").strip().lower()
    head = state.split(":", 1)[0] if state else ""
    # FR #4833: lock/assert-lock waits for Simon's label — keep pending (skip_hold),
    # never park→FIX-CI. Seats cannot clear this check.
    if fix_ci_skip_reason(state) == "human-gated-lock":
        return "skip_hold"
    # FR #4630: annotated rollups (failure:test-and-synth) still requeue_ci;
    # enqueue_fix_ci may then skip.
    if head in ("failure", "error", "action_required", "timed_out", "cancelled", "canceled"):
        return "requeue_ci"
    if head in ("pending", "expected", "queued", "in_progress", "waiting", "requested"):
        return "wait"
    if head in ("success", "neutral", "skipped", "none", ""):
        return "merge"
    # Unknown check vocabulary: wait rather than merge.
    return "wait"


def ledger_path(home: Path) -> Path:
    """Fleet-root ledger (sibling of queue.json).

    FR #4522: Jeeves ``--home`` is the config dir (``~/.jeeves``); the live
    merge-on-green ledger and queue live under ``fleet_digest_home`` /
    ``BOB_DIGEST_HOME`` (``~/.bobiverse``). Writing beside config home made
    resync miss every ``pass_sha`` and re-queue CI-waiting MRBs.
    """
    return gitclaim._root(Path(home)) / LEDGER_NAME


def _legacy_config_ledger_path(home: Path) -> Path:
    """Pre-FR #4522 path: ``Path(home)/merge-on-green.json`` when home != fleet root."""
    return Path(home) / LEDGER_NAME


def _empty_ledger() -> dict[str, Any]:
    return {
        "version": 1,
        "pending": [],
        CI_FAILED_KEY: {},
        CI_FIX_KEY: {},
        CI_RERUN_KEY: {},
        CONFLICT_KEY: {},
        CONFLICT_FIX_KEY: {},
    }


def load_ledger(home: Path) -> dict[str, Any]:
    path = ledger_path(home)
    if not path.is_file():
        # FR #4522: fall back to a leftover config-home ledger once.
        legacy = _legacy_config_ledger_path(home)
        try:
            if legacy.is_file() and legacy.resolve() != path.resolve():
                path = legacy
            else:
                return _empty_ledger()
        except OSError:
            return _empty_ledger()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return _empty_ledger()
    if not isinstance(doc, dict):
        return _empty_ledger()
    pending = doc.get("pending")
    if not isinstance(pending, list):
        doc["pending"] = []
    if not isinstance(doc.get(CI_FAILED_KEY), dict):
        doc[CI_FAILED_KEY] = {}
    if not isinstance(doc.get(CI_FIX_KEY), dict):
        doc[CI_FIX_KEY] = {}
    if not isinstance(doc.get(CI_RERUN_KEY), dict):
        doc[CI_RERUN_KEY] = {}
    if not isinstance(doc.get(CONFLICT_KEY), dict):
        doc[CONFLICT_KEY] = {}
    if not isinstance(doc.get(CONFLICT_FIX_KEY), dict):
        doc[CONFLICT_FIX_KEY] = {}
    return doc


def failure_signature(
    repo: str,
    *,
    detail: str = "",
    pass_sha: str = "",
    pr: str = "",
    main_red: bool | None = None,
) -> str:
    """FIX-CI fingerprint for dedupe (FR #4585 / FR #4596).

    Collapse N PASSed tips onto one FIX **only when main itself is red** on the
    same check (``main_red=True`` -> ``repo|state``). When main is green (or
    unknown), each PR is its own FIX (``repo|#N|state``) so seats can fold main
    in parallel instead of draining one tip per hourly resync.
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    state = (detail or "failure").strip().lower() or "failure"
    state = re.sub(r"\s+", " ", state)[:120]
    if main_red is True:
        return f"{repo_c}|{state}"
    num = str(pr or "").lstrip("#")
    if num:
        return f"{repo_c}|#{num}|{state}"
    return f"{repo_c}|{state}"


def main_branch_checks_red(
    repo: str,
    *,
    token: str | None = None,
    fetch_default_sha: Callable[..., str] | None = None,
    fetch_checks: Callable[..., str] | None = None,
) -> bool:
    """True when the repo default branch's required checks roll up to failure (FR #4596).

    Injectable fetchers keep tests offline. Unknown / empty checks are **not** red
    (prefer per-PR FIX over collapsing the whole fleet onto one job).
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    if not repo_c:
        return False
    try:
        if fetch_default_sha is not None:
            sha = str(fetch_default_sha(repo_c) or "").strip()
        else:
            tok = _gh_token(token)
            if not tok:
                return False
            meta = _gh_json(
                f"https://api.github.com/repos/{repo_c}",
                token=tok,
            )
            default = str((meta or {}).get("default_branch") or "main").strip() or "main"
            ref = _gh_json(
                f"https://api.github.com/repos/{repo_c}/git/ref/heads/{default}",
                token=tok,
            )
            sha = str(((ref or {}).get("object") or {}).get("sha") or "").strip()
        if not sha:
            return False
        if fetch_checks is not None:
            state = str(fetch_checks(repo_c, sha) or "").strip().lower()
        else:
            tok = _gh_token(token)
            if not tok:
                return False
            status = _gh_json(
                f"https://api.github.com/repos/{repo_c}/commits/{sha}/status",
                token=tok,
            )
            runs = None
            if combined_status_is_empty(status if isinstance(status, dict) else None):
                runs = _gh_json(
                    f"https://api.github.com/repos/{repo_c}/commits/{sha}/check-runs",
                    token=tok,
                )
            state = checks_from_status_and_runs(
                status if isinstance(status, dict) else None,
                runs,
            )
        head = state.split(":", 1)[0] if state else ""
        return head in (
            "failure",
            "error",
            "action_required",
            "timed_out",
            "cancelled",
            "canceled",
        )
    except Exception:  # noqa: BLE001
        return False


def main_branch_head_sha(
    repo: str,
    *,
    token: str | None = None,
    fetch_default_sha: Callable[..., str] | None = None,
) -> str:
    """Default-branch tip SHA, or empty when unknown (FR #4857)."""
    repo_c = gitclaim.canonical_queue_repo(repo)
    if not repo_c:
        return ""
    try:
        if fetch_default_sha is not None:
            return _norm_sha(str(fetch_default_sha(repo_c) or ""))
        tok = _gh_token(token)
        if not tok:
            return ""
        meta = _gh_json(
            f"https://api.github.com/repos/{repo_c}",
            token=tok,
        )
        default = str((meta or {}).get("default_branch") or "main").strip() or "main"
        ref = _gh_json(
            f"https://api.github.com/repos/{repo_c}/git/ref/heads/{default}",
            token=tok,
        )
        return _norm_sha(str(((ref or {}).get("object") or {}).get("sha") or ""))
    except Exception:  # noqa: BLE001
        return ""


def enqueue_main_red_shared_suite_fix(
    home: Path,
    *,
    repo: str,
    detail: str = "",
    main_sha: str = "",
    check_url: str = "",
    failed_tail: str = "",
    tip_pr: str = "",
    now_epoch: float | None = None,
    token: str | None = None,
    fetch_default_sha: Callable[..., str] | None = None,
) -> str:
    """Queue one FIX for a red default branch shared suite (FR #4857).

    Deduped per ``main-red|<repo>|<main sha>|<check>``. Returns
    ``added`` | ``duplicate`` | ``skipped``. Tip PASSed PRs stay skipped.
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    if not repo_c:
        return "skipped"
    sha = _norm_sha(main_sha)
    if not sha:
        sha = main_branch_head_sha(
            repo_c, token=token, fetch_default_sha=fetch_default_sha
        )
    if not sha:
        return "skipped"
    check = shared_suite_check_name(detail)
    sig = main_red_fix_signature(repo_c, sha, check)
    tnow = float(now_epoch if now_epoch is not None else time.time())
    doc = load_ledger(home)
    offered = doc.get(CI_FIX_KEY)
    if not isinstance(offered, dict):
        offered = {}
        doc[CI_FIX_KEY] = offered
    prev = offered.get(sig)
    if isinstance(prev, dict) and shas_match(str(prev.get("pass_sha") or ""), sha):
        if fix_signature_is_live(home, repo_c, sig, "main"):
            return "duplicate"
        # Orphaned ledger stamp: clear and re-offer.
        offered.pop(sig, None)
        save_ledger(home, doc)
    pull_url = (check_url or "").strip() or f"https://github.com/{repo_c}/commit/{sha}"
    title = f"FIX main red {check} @ {sha[:12]} (shared suite; FR #4857)"
    body = (
        f"FR #4857 main-side FIX: default branch is red on shared suite `{check}` "
        f"while PASSed tips were skipped (`main-also-red-shared-suite`). "
        f"Signature `{sig}`. Fix main (open a PR from current main), do not burn "
        f"N tip FIX jobs for the same suite failure."
    )
    if tip_pr:
        body += f" Trigger tip PR #{str(tip_pr).lstrip('#')}."
    if check_url:
        body += f" Failing job: {check_url}."
    if failed_tail:
        # Never paste secrets; keep a short ASCII tail for the seat.
        tail = re.sub(r"\s+", " ", str(failed_tail).strip())[:400]
        body += f" Failed-test tail: {tail}"
    claim = gitclaim.GitClaim(
        repo=repo_c,
        task="FIX",
        id="#main",
        event="check_suite",
        action="completed",
        line=pull_url,
        title=title,
        body=body,
        labels=("via-intake", "fix-ci", "main-red"),
    )
    with gitclaim._lock(home):
        try:
            qdoc = gitclaim._load_queue_unlocked(home)
        except (OSError, ValueError):
            qdoc = gitclaim._empty_queue()
        # Drop stale main-red FIX rows for this repo (older main SHA).
        kept_ua: list = []
        for row in list(qdoc.get("unaccepted") or []):
            if (
                is_main_red_fix_row(row)
                and gitclaim.canonical_queue_repo(str(row.get("repo") or "")) == repo_c
                and not shas_match(str(row.get("pass_sha") or ""), sha)
            ):
                continue
            kept_ua.append(row)
        qdoc["unaccepted"] = kept_ua
        for row in list(qdoc.get("unaccepted") or []) + list(qdoc.get("accepted") or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "FIX":
                continue
            if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            row_body = str(row.get("body") or "") + " " + str(row.get("title") or "")
            row_sig = str(row.get("fail_signature") or "")
            if row_sig == sig or sig in row_body or (
                is_main_red_fix_row(row)
                and shas_match(str(row.get("pass_sha") or ""), sha)
            ):
                offered[sig] = {
                    "repo": repo_c,
                    "pr": "main",
                    "pass_sha": sha,
                    "signature": sig,
                    "offered_epoch": tnow,
                    "url": str(row.get("url") or pull_url),
                    "main_red": True,
                }
                save_ledger(home, doc)
                return "duplicate"
        changed = gitclaim._append_unaccepted(
            qdoc,
            claim,
            url=pull_url,
            body=body,
            title=claim.title,
            pass_sha=sha,
            fail_signature=sig,
            main_red_fix="1",
        )
        try:
            gitclaim._write_queue(gitclaim.queue_path(home), qdoc)
        except OSError:
            return "skipped"
    if changed == "added":
        offered[sig] = {
            "repo": repo_c,
            "pr": "main",
            "pass_sha": sha,
            "signature": sig,
            "offered_epoch": tnow,
            "url": pull_url,
            "main_red": True,
        }
        save_ledger(home, doc)
        return "added"
    if changed == "duplicate":
        offered[sig] = {
            "repo": repo_c,
            "pr": "main",
            "pass_sha": sha,
            "signature": sig,
            "offered_epoch": tnow,
            "url": pull_url,
            "main_red": True,
        }
        save_ledger(home, doc)
        return "duplicate"
    return "skipped"


def park_ci_failed(
    doc: dict[str, Any],
    row: dict[str, Any],
    *,
    detail: str = "",
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Record a CI-failed PASS row outside ``pending`` (FR #4566 follow-up)."""
    repo_c = gitclaim.canonical_queue_repo(str(row.get("repo") or ""))
    num = str(row.get("pr") or "").lstrip("#")
    key = _row_key(repo_c, num)
    failed_epoch = float(now_epoch if now_epoch is not None else time.time())
    rec = {
        "key": key,
        "repo": repo_c,
        "pr": num,
        "pass_sha": str(row.get("pass_sha") or ""),
        "url": str(row.get("url") or f"https://github.com/{repo_c}/pull/{num}"),
        "nick": str(row.get("nick") or ""),
        "failed_ts": _utc(),
        "failed_epoch": failed_epoch,
        # FR #4706 / #4566: do not re-GET every chair tick; check_run bypasses this.
        "next_refresh_epoch": failed_epoch + float(CI_FAILED_REFRESH_S),
        "detail": detail or "required check failed",
    }
    parked = doc.get(CI_FAILED_KEY)
    if not isinstance(parked, dict):
        parked = {}
        doc[CI_FAILED_KEY] = parked
    parked[key] = rec
    return rec


def enqueue_fix_ci(
    home: Path,
    *,
    repo: str,
    pr: str,
    pass_sha: str,
    url: str = "",
    detail: str = "",
    check_run_id: str = "",
    now_epoch: float | None = None,
    main_red: bool | None = None,
    token: str | None = None,
    main_red_fn: Callable[..., bool] | None = None,
    mergeable: Any = "",
    merge_state: str = "",
    main_sha: str = "",
    check_url: str = "",
    failed_tail: str = "",
    fetch_default_sha: Callable[..., str] | None = None,
) -> str:
    """Offer a FIX job for a PASSed+auto-merge PR with a red required check (FR #4585/#4596).

    When ``main_red`` (or ``main_red_fn`` / live main check) is True, dedupe by
    shared ``repo|state`` so one FIX covers a main breakage. When main is green
    (or unknown), each PR is its own FIX. Returns ``added`` | ``duplicate`` | ``skipped``.

    FR #4630 / #4857: tip cancelled-only -> ``skipped``. Shared suite red while
    main is also red -> tip ``skipped_main_added`` / ``skipped_main_duplicate``
    (one main-side FIX is queued / already present).

    FR #4833: returns ``needs_human`` when the only red check is ``lock`` /
    ``assert-lock`` (Simon must add ``simon-approved-rule-change``).

    FR #4669: a FIX that is already DONE on this same head SHA is not a permanent
    duplicate. Main green -> one update-branch, then a re-offer. DIRTY -> conflict
    FIX. After ``FIX_CI_RECOVER_MAX`` re-offers, stamp ``needs_human``.
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    sha = _norm_sha(pass_sha)
    if not repo_c or not num or not sha:
        return "skipped"
    if main_red is None:
        if main_red_fn is not None:
            try:
                main_red = bool(main_red_fn(repo_c))
            except Exception:  # noqa: BLE001
                main_red = False
        else:
            main_red = main_branch_checks_red(repo_c, token=token)
    skip = fix_ci_skip_reason(detail, main_red=bool(main_red))
    if skip == "human-gated-lock":
        return park_human_gated_lock(
            home,
            repo=repo_c,
            pr=num,
            sha=sha,
            url=url or f"https://github.com/{repo_c}/pull/{num}",
            detail=detail,
        )
    if skip == "main-also-red-shared-suite":
        main_result = enqueue_main_red_shared_suite_fix(
            home,
            repo=repo_c,
            detail=detail,
            main_sha=main_sha,
            check_url=check_url,
            failed_tail=failed_tail,
            tip_pr=num,
            now_epoch=now_epoch,
            token=token,
            fetch_default_sha=fetch_default_sha,
        )
        if main_result == "added":
            return "skipped_main_added"
        if main_result == "duplicate":
            return "skipped_main_duplicate"
        return "skipped"
    if skip:
        return "skipped"
    sig = failure_signature(
        repo_c, detail=detail, pass_sha=sha, pr=num, main_red=bool(main_red)
    )
    tnow = float(now_epoch if now_epoch is not None else time.time())
    reoffer_n = 0
    reoffer_seats = ""
    reoffer_branch = ""
    doc = load_ledger(home)
    offered = doc.get(CI_FIX_KEY)
    if not isinstance(offered, dict):
        offered = {}
        doc[CI_FIX_KEY] = offered
    prev = offered.get(sig)
    if isinstance(prev, dict):
        prev_sha = _norm_sha(str(prev.get("pass_sha") or ""))
        prev_run = str(prev.get("check_run_id") or "")
        # Same signature + same SHA (+ same run when known) -> no second FIX.
        if prev_sha and shas_match(prev_sha, sha):
            if not check_run_id or not prev_run or prev_run == str(check_run_id):
                # FR #4639: a pruned FIX row with no DONE must not block the next offer.
                # FR #4669: a DONE row on this same SHA must re-run or re-offer.
                if not ci_fix_signature_orphaned(home, repo_c, sig, num):
                    if fix_signature_is_live(home, repo_c, sig, num):
                        return "duplicate"
                    if fix_pr_is_done(home, repo_c, num):
                        recovered = recover_done_fix_ci(
                            home,
                            repo=repo_c,
                            pr=num,
                            sha=sha,
                            sig=sig,
                            prev=prev,
                            main_red=bool(main_red),
                            mergeable=mergeable,
                            merge_state=merge_state,
                            token=token,
                            url=url or f"https://github.com/{repo_c}/pull/{num}",
                            detail=detail,
                            now_epoch=tnow,
                        )
                        if recovered != "reoffer":
                            return recovered
                        reoffer_n = int(prev.get("recover_n") or 0)
                        reoffer_seats = str(prev.get("giveup_seats") or "")
                        reoffer_branch = str(prev.get("branch_update") or "")
                        doc = load_ledger(home)
                        offered = doc.get(CI_FIX_KEY)
                        if not isinstance(offered, dict):
                            offered = {}
                            doc[CI_FIX_KEY] = offered
                    else:
                        return "duplicate"
                else:
                    offered.pop(sig, None)
                    save_ledger(home, doc)
    pull_url = url or f"https://github.com/{repo_c}/pull/{num}"
    if main_red:
        guidance = (
            f"Prefer fixing the shared failure on main when many tips share this "
            f"signature ({sig}); otherwise fix CI on this PR branch and push."
        )
        title = f"FIX CI after MRB PASS (red check; shared sig {sig})"
    else:
        guidance = (
            f"Main required checks are green — fix CI on this PR branch "
            f"(signature {sig}), fold main if needed, and push; do not wait for "
            f"a shared main FIX."
        )
        title = f"FIX CI after MRB PASS (red check; per-PR sig {sig})"
    body = (
        f"FR #4596 FIX CI: PASSed MRB with auto-merge on but a required check failed "
        f"({detail or 'failure'}). Head SHA {sha}. {guidance} "
        f"Do not re-open MRB while the head SHA is unchanged."
    )
    if check_run_id:
        body += f" check_run_id={check_run_id}."
    claim = gitclaim.GitClaim(
        repo=repo_c,
        task="FIX",
        id=f"#{num}",
        event="pull_request",
        action="synchronize",
        line=pull_url,
        title=title,
        body=body,
        labels=("via-intake", "fix-ci"),
    )
    with gitclaim._lock(home):
        try:
            qdoc = gitclaim._load_queue_unlocked(home)
        except (OSError, ValueError):
            qdoc = gitclaim._empty_queue()
        # Dedupe against any FIX already queued for this repo with the same signature
        # stamped on the row (body/title) or the same PR id.
        for row in list(qdoc.get("unaccepted") or []) + list(qdoc.get("accepted") or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "FIX":
                continue
            if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            row_body = str(row.get("body") or "") + " " + str(row.get("title") or "")
            if sig in row_body or gitclaim._same(row, repo_c, "FIX", f"#{num}"):
                offered[sig] = {
                    "repo": repo_c,
                    "pr": str(row.get("id") or num).lstrip("#"),
                    "pass_sha": sha,
                    "check_run_id": str(check_run_id or ""),
                    "signature": sig,
                    "offered_epoch": tnow,
                    "url": str(row.get("url") or pull_url),
                }
                save_ledger(home, doc)
                return "duplicate"
        extra_giveup = {}
        if reoffer_seats:
            extra_giveup["giveup_seats"] = reoffer_seats
        changed = gitclaim._append_unaccepted(
            qdoc,
            claim,
            url=pull_url,
            body=body,
            title=claim.title,
            pass_sha=sha,
            fail_signature=sig,
            check_run_id=str(check_run_id or ""),
            **extra_giveup,
        )
        try:
            gitclaim._write_queue(gitclaim.queue_path(home), qdoc)
        except OSError:
            return "skipped"
    if changed == "added":
        offered[sig] = {
            "repo": repo_c,
            "pr": num,
            "pass_sha": sha,
            "check_run_id": str(check_run_id or ""),
            "signature": sig,
            "offered_epoch": tnow,
            "url": pull_url,
            "recover_n": int(reoffer_n or 0),
        }
        if reoffer_branch:
            offered[sig]["branch_update"] = reoffer_branch
        save_ledger(home, doc)
        return "added"
    if changed == "duplicate":
        offered[sig] = {
            "repo": repo_c,
            "pr": num,
            "pass_sha": sha,
            "check_run_id": str(check_run_id or ""),
            "signature": sig,
            "offered_epoch": tnow,
            "url": pull_url,
        }
        save_ledger(home, doc)
        return "duplicate"
    return "skipped"


def ci_fix_signature_orphaned(home: Path, repo: str, sig: str, pr: str) -> bool:
    """FR #4639: ledger ``ci_fix`` row whose FIX queue row was pruned and not DONE."""
    try:
        q = gitclaim.load_queue(home)
    except (OSError, ValueError):
        return False
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    ident = f"#{num}"
    for bucket in ("unaccepted", "accepted"):
        for row in q.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "FIX":
                continue
            if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            blob = str(row.get("body") or "") + " " + str(row.get("title") or "")
            row_id = str(row.get("id") or "").lstrip("#")
            if sig in blob or row_id == num or gitclaim._same(row, repo_c, "FIX", ident):
                return False
    for row in q.get("done") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("task") or "").upper() != "FIX":
            continue
        if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
            continue
        if str(row.get("id") or "").lstrip("#") == num:
            return False
    return True


def _fix_rows(home: Path, repo: str, pr: str, *buckets: str) -> list[dict]:
    """FIX queue rows for this PR in the named buckets."""
    try:
        q = gitclaim.load_queue(home)
    except (OSError, ValueError):
        return []
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    ident = f"#{num}"
    found: list[dict] = []
    for bucket in buckets:
        for row in q.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "FIX":
                continue
            if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            row_id = str(row.get("id") or "").lstrip("#")
            if row_id == num or gitclaim._same(row, repo_c, "FIX", ident):
                found.append(row)
    return found


def fix_signature_is_live(home: Path, repo: str, sig: str, pr: str) -> bool:
    """True when an unaccepted or accepted FIX still carries this signature or PR."""
    try:
        q = gitclaim.load_queue(home)
    except (OSError, ValueError):
        return False
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    ident = f"#{num}"
    for bucket in ("unaccepted", "accepted"):
        for row in q.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "FIX":
                continue
            if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            blob = str(row.get("body") or "") + " " + str(row.get("title") or "")
            row_id = str(row.get("id") or "").lstrip("#")
            if sig in blob or row_id == num or gitclaim._same(row, repo_c, "FIX", ident):
                return True
    return False


def fix_pr_is_done(home: Path, repo: str, pr: str) -> bool:
    """True when a FIX for this PR sits in ``done`` and is not still queued."""
    if fix_signature_is_live(home, repo, "\0", pr):
        return False
    return bool(_fix_rows(home, repo, pr, "done"))


def done_fix_giveup_seats(home: Path, repo: str, pr: str) -> str:
    """Comma list of seats that already DONE this FIX, so the re-offer skips them."""
    seats: list[str] = []
    seen: set[str] = set()
    for row in _fix_rows(home, repo, pr, "done"):
        for key in ("done_by", "nick", "accepted_by"):
            nick = gitclaim.canonical_worker_nick(str(row.get(key) or "")) or ""
            if not nick:
                continue
            low = nick.lower()
            if low in seen:
                continue
            seen.add(low)
            seats.append(nick)
    return ",".join(seats)


def park_human_gated_lock(
    home: Path,
    *,
    repo: str,
    pr: str,
    sha: str,
    url: str = "",
    detail: str = "",
) -> str:
    """FR #4833: park lock/assert-lock as needs_human — never offerable FIX-CI.

    Uses a FIX row (resync keeps non-FR/MRB kinds) stamped ``needs_human`` so
    digest shows the park and auto-offer / !assign FIX refuse it. Returns
    ``needs_human`` (row present) or ``skipped`` on I/O failure.
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    pull_url = url or f"https://github.com/{repo_c}/pull/{num}"
    title = f"needs-human: add simon-approved-rule-change ({num}@{sha[:12]})"
    body = (
        f"FR #4833: required check lock/assert-lock failed "
        f"({detail or 'failure:lock'}). Only SimonBarnett may add label "
        f"simon-approved-rule-change; seats must never forge it. "
        f"Head SHA {sha}. Do not offer FIX-CI or re-queue MRB while the head "
        f"SHA is unchanged."
    )
    claim = gitclaim.GitClaim(
        repo=repo_c,
        task="FIX",
        id=f"#{num}",
        event="pull_request",
        action="synchronize",
        line=pull_url,
        title=title,
        body=body,
        labels=("via-intake", "fix-ci"),
    )
    with gitclaim._lock(home):
        try:
            qdoc = gitclaim._load_queue_unlocked(home)
        except (OSError, ValueError):
            qdoc = gitclaim._empty_queue()
        stamped = False
        for row in list(qdoc.get("unaccepted") or []) + list(qdoc.get("accepted") or []):
            if not isinstance(row, dict):
                continue
            if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            if str(row.get("id") or "").lstrip("#") != num:
                continue
            task = str(row.get("task") or "").upper()
            if task not in ("MRB", "FIX"):
                continue
            row["needs_human"] = True
            if task == "FIX":
                row["title"] = title
                row["body"] = body
            row["note"] = HUMAN_GATED_LOCK_REASON
            stamped = True
        if not stamped:
            changed = gitclaim._append_unaccepted(
                qdoc,
                claim,
                url=pull_url,
                body=body,
                title=title,
                pass_sha=sha,
                needs_human="true",
                note=HUMAN_GATED_LOCK_REASON,
            )
            if changed in ("added", "duplicate", "noop"):
                for row in qdoc.get("unaccepted") or []:
                    if isinstance(row, dict) and gitclaim._same(
                        row, repo_c, "FIX", f"#{num}"
                    ):
                        row["needs_human"] = True
                        row["note"] = HUMAN_GATED_LOCK_REASON
                        stamped = True
        try:
            gitclaim._write_queue(gitclaim.queue_path(home), qdoc)
        except OSError:
            return "skipped"
    return "needs_human" if stamped else "skipped"


def _stamp_fix_needs_human(
    home: Path,
    *,
    repo: str,
    pr: str,
    sha: str,
    sig: str,
    url: str,
    detail: str,
    giveup_seats: str,
) -> str:
    """Leave one visible needs_human FIX when re-offers are exhausted (FR #4669)."""
    if fix_signature_is_live(home, repo, sig, pr):
        return "needs_human"
    pull_url = url or f"https://github.com/{repo}/pull/{pr}"
    title = f"FIX CI after MRB PASS needs human ({pr}@{sha[:12]})"
    body = (
        f"FR #4669: FIX finished without a new head SHA and CI is still red "
        f"({detail or 'failure'}). Re-offer budget is spent. Head SHA {sha}."
    )
    claim = gitclaim.GitClaim(
        repo=repo,
        task="FIX",
        id=f"#{pr}",
        event="pull_request",
        action="synchronize",
        line=pull_url,
        title=title,
        body=body,
        labels=("via-intake", "fix-ci"),
    )
    with gitclaim._lock(home):
        try:
            qdoc = gitclaim._load_queue_unlocked(home)
        except (OSError, ValueError):
            qdoc = gitclaim._empty_queue()
        changed = gitclaim._append_unaccepted(
            qdoc,
            claim,
            url=pull_url,
            body=body,
            title=title,
            pass_sha=sha,
            fail_signature=sig,
            needs_human="true",
            giveup_seats=giveup_seats,
        )
        if changed == "added":
            for row in qdoc.get("unaccepted") or []:
                if isinstance(row, dict) and gitclaim._same(row, repo, "FIX", f"#{pr}"):
                    row["needs_human"] = True
        try:
            gitclaim._write_queue(gitclaim.queue_path(home), qdoc)
        except OSError:
            return "skipped"
    return "needs_human"


def recover_done_fix_ci(
    home: Path,
    *,
    repo: str,
    pr: str,
    sha: str,
    sig: str,
    prev: dict,
    main_red: bool,
    mergeable: Any = "",
    merge_state: str = "",
    token: str | None = None,
    url: str = "",
    detail: str = "",
    now_epoch: float | None = None,
) -> str:
    """FR #4669: DONE FIX, same head, CI still red. Never a permanent duplicate.

    Returns ``updated-branch`` | ``pending`` | ``capped`` | ``needs_human`` |
    ``added`` | ``duplicate`` | ``reoffer``. ``reoffer`` means the caller should
    enqueue a fresh FIX (ledger entry already cleared). An update-branch HTTP
    error (FR #4672) is stored as ``branch_update=rejected`` and falls through
    to re-offer or ``needs_human`` instead of raising.
    """
    dirty = merge_attempt_conflict_reason(mergeable=mergeable, merge_state=merge_state)
    seats = done_fix_giveup_seats(home, repo, pr)
    prev["giveup_seats"] = seats
    if dirty:
        return offer_dirty_conflict_fix(
            home,
            repo=repo,
            pr=pr,
            sha=sha,
            url=url,
            reason=dirty,
        )
    retries = int(prev.get("recover_n") or 0)
    if not main_red and not str(prev.get("branch_update") or ""):
        try:
            result = rerun_cancelled_passed(
                home,
                repo=repo,
                pr=pr,
                pass_sha=sha,
                behind=True,
                token=token,
                now_epoch=now_epoch,
            )
        except RuntimeError:
            # FR #4672: update-branch HTTP 422 (already up to date) must be recorded
            # so the next resync does not PUT again. Fall through to re-offer.
            result = "rejected"
        doc = load_ledger(home)
        offered = doc.get(CI_FIX_KEY)
        if not isinstance(offered, dict):
            offered = {}
            doc[CI_FIX_KEY] = offered
        kept = dict(prev)
        kept["branch_update"] = result
        offered[sig] = kept
        save_ledger(home, doc)
        prev["branch_update"] = result
        if result in ("updated-branch", "pending", "capped"):
            return result
    if retries >= FIX_CI_RECOVER_MAX:
        return _stamp_fix_needs_human(
            home,
            repo=repo,
            pr=pr,
            sha=sha,
            sig=sig,
            url=url,
            detail=detail,
            giveup_seats=seats,
        )
    prev["recover_n"] = retries + 1
    doc = load_ledger(home)
    offered = doc.get(CI_FIX_KEY)
    if isinstance(offered, dict):
        offered.pop(sig, None)
        doc[CI_FIX_KEY] = offered
        save_ledger(home, doc)
    return "reoffer"


def offer_dirty_conflict_fix(
    home: Path,
    *,
    repo: str,
    pr: str,
    sha: str,
    url: str = "",
    reason: str = "conflicting",
    pr_state: dict[str, Any] | None = None,
) -> str:
    """Offer one conflict FIX for a DIRTY/CONFLICTING PR (FR #4669 / #4636 / #4679).

    A finished FIX on this SHA is re-offered. A still-queued FIX stays ``duplicate``.
    After ``FIX_CI_RECOVER_MAX`` re-offers, stamp ``needs_human``.

    FR #5720: harvest-lesson closed / FAIL-supersede dispositions return ``skipped``
    (same carve-out as FR #4800 for mrb-fail FIX).
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    sig = f"conflict|{repo_c}|{num}|{_norm_sha(sha)}"
    result = enqueue_conflict_fix(
        home,
        repo=repo_c,
        pr=num,
        pass_sha=sha,
        url=url,
        reason=reason,
        pr_state=pr_state,
    )
    if result != "duplicate":
        return result
    if fix_signature_is_live(home, repo_c, sig, num):
        return "duplicate"
    doc = load_ledger(home)
    offered = doc.get(CONFLICT_FIX_KEY)
    prev = offered.get(sig) if isinstance(offered, dict) else None
    retries = int((prev or {}).get("recover_n") or 0) if isinstance(prev, dict) else 0
    if retries >= FIX_CI_RECOVER_MAX:
        return _stamp_fix_needs_human(
            home,
            repo=repo_c,
            pr=num,
            sha=sha,
            sig=sig,
            url=url,
            detail=reason or "conflicting",
            giveup_seats=done_fix_giveup_seats(home, repo_c, num),
        )
    if isinstance(offered, dict):
        offered.pop(sig, None)
        doc[CONFLICT_FIX_KEY] = offered
        save_ledger(home, doc)
    result = enqueue_conflict_fix(
        home,
        repo=repo_c,
        pr=num,
        pass_sha=sha,
        url=url,
        reason=reason,
        pr_state=pr_state,
    )
    if result == "added":
        doc = load_ledger(home)
        offered = doc.get(CONFLICT_FIX_KEY)
        if isinstance(offered, dict) and isinstance(offered.get(sig), dict):
            offered[sig]["recover_n"] = retries + 1
            save_ledger(home, doc)
    return result


def enqueue_mrb_fail_fix(
    home: Path,
    *,
    repo: str,
    pr: str,
    sha: str,
    url: str = "",
    nick: str = "",
    pr_state: dict[str, Any] | None = None,
) -> str:
    """Queue one FIX to implement the MRB FAIL board on this PR+SHA (FR #4718).

    Same SHA returns ``duplicate``. FIX is offerable to any seat, including the
    seat that posted the FAIL. That seat must not be offered the MRB again.

    FR #4800: harvest-lesson tips that are closed unmerged (or carry a
    FAIL-supersede / CLOSED / MOVED disposition board) return ``skipped``.
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    tip = _norm_sha(sha)
    if not repo_c or not num or not tip:
        return "skipped"
    state = pr_state
    if state is None:
        try:
            state = fetch_pr_state(repo_c, num)
        except Exception:  # noqa: BLE001
            state = None
    if isinstance(state, dict) and skip_mrb_fail_fix_for_harvest(
        title=str(state.get("title") or ""),
        labels=tuple(state.get("labels") or ()),
        closed=bool(state.get("closed")),
        merged=bool(state.get("merged")),
        comments=state.get("comments") if isinstance(state.get("comments"), list) else None,
    ):
        return "skipped"
    sig = f"mrb-fail|{repo_c}|{num}|{tip}"
    doc = load_ledger(home)
    offered = doc.get(MRB_FAIL_FIX_KEY)
    if not isinstance(offered, dict):
        offered = {}
        doc[MRB_FAIL_FIX_KEY] = offered
    prev = offered.get(sig)
    if isinstance(prev, dict) and shas_match(str(prev.get("pass_sha") or ""), tip):
        return "duplicate"
    pull_url = url or f"https://github.com/{repo_c}/pull/{num}"
    who = (gitclaim.canonical_worker_nick(nick) or str(nick or "")).strip()
    title = f"FIX MRB FAIL board ({num}@{tip[:12]})"
    body = (
        f"FR #4718: newest MRB board is FAIL at head SHA {tip}. "
        f"Implement that board on this branch and push. One job per PR+SHA. "
        f"Signature {sig}."
    )
    claim = gitclaim.GitClaim(
        repo=repo_c,
        task="FIX",
        id=f"#{num}",
        event="pull_request",
        action="synchronize",
        line=pull_url,
        title=title,
        body=body,
        labels=("via-intake", "fix-mrb-fail"),
    )
    with gitclaim._lock(home):
        try:
            qdoc = gitclaim._load_queue_unlocked(home)
        except (OSError, ValueError):
            qdoc = gitclaim._empty_queue()
        for row in list(qdoc.get("unaccepted") or []) + list(qdoc.get("accepted") or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "FIX":
                continue
            if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            blob = str(row.get("body") or "") + " " + str(row.get("title") or "")
            if sig in blob:
                offered[sig] = {
                    "repo": repo_c,
                    "pr": num,
                    "pass_sha": tip,
                    "signature": sig,
                    "url": pull_url,
                    "nick": who,
                }
                save_ledger(home, doc)
                return "duplicate"
        changed = gitclaim._append_unaccepted(
            qdoc,
            claim,
            url=pull_url,
            body=body,
            title=claim.title,
            pass_sha=tip,
            fail_signature=sig,
            mrb_fail_by=who,
        )
        try:
            gitclaim._write_queue(gitclaim.queue_path(home), qdoc)
        except OSError:
            return "skipped"
    if changed in ("added", "duplicate"):
        offered[sig] = {
            "repo": repo_c,
            "pr": num,
            "pass_sha": tip,
            "signature": sig,
            "url": pull_url,
            "nick": who,
        }
        save_ledger(home, doc)
        if who:
            gitclaim.stamp_mrb_fail(home, repo_c, f"#{num}", tip, who)
        return changed if changed in ("added", "duplicate") else "skipped"
    return "skipped"


def head_sha_for_mrb_fail(repo: str, num: str) -> str:
    """Live head SHA for a DONE MRB FAIL. Tests replace this."""
    state = fetch_pr_state(repo, str(num).lstrip("#"))
    if not isinstance(state, dict):
        return ""
    return _norm_sha(str(state.get("sha") or ""))


def enqueue_from_mrb_fail_done(
    home: Path,
    *,
    repo: str,
    pr_url: str,
    nick: str,
    sha: str = "",
) -> str:
    """DONE MRB FAIL queues a FIX for the current head (FR #4718).

    FR #4800: harvest-lesson closed / FAIL-supersede dispositions skip FIX
    (seats should DONE PASS for those tips; this is the chair backstop).
    """
    parsed = gitclaim.parse_github_pull_url(pr_url or "")
    if parsed:
        repo_c, ident = parsed
    else:
        repo_c = gitclaim.canonical_queue_repo(repo)
        ident = ""
    num = str(ident).lstrip("#")
    if not repo_c or not num.isdigit():
        return "skipped"
    state: dict[str, Any] | None = None
    try:
        state = fetch_pr_state(repo_c, num)
    except Exception:  # noqa: BLE001
        state = None
    if isinstance(state, dict) and skip_mrb_fail_fix_for_harvest(
        title=str(state.get("title") or ""),
        labels=tuple(state.get("labels") or ()),
        closed=bool(state.get("closed")),
        merged=bool(state.get("merged")),
        comments=state.get("comments") if isinstance(state.get("comments"), list) else None,
    ):
        return "skipped"
    tip = _norm_sha(sha)
    if not tip and isinstance(state, dict):
        tip = _norm_sha(str(state.get("sha") or ""))
    if not tip:
        try:
            tip = head_sha_for_mrb_fail(repo_c, num)
        except Exception:  # noqa: BLE001
            return "skipped"
    if not tip:
        return "skipped"
    gitclaim.stamp_mrb_fail(home, repo_c, f"#{num}", tip, nick)
    return enqueue_mrb_fail_fix(
        home,
        repo=repo_c,
        pr=num,
        sha=tip,
        url=pr_url or f"https://github.com/{repo_c}/pull/{num}",
        nick=nick,
        pr_state=state,
    )


def _rerun_pending_count(doc: dict[str, Any]) -> int:
    rows = doc.get(CI_RERUN_KEY)
    if not isinstance(rows, dict):
        return 0
    return sum(
        1
        for v in rows.values()
        if isinstance(v, dict) and str(v.get("state") or "") == "pending"
    )


def rerun_cancelled_passed(
    home: Path,
    *,
    repo: str,
    pr: str,
    pass_sha: str,
    run_id: str = "",
    behind: bool = False,
    token: str | None = None,
    now_epoch: float | None = None,
    post_fn: Callable[..., Any] | None = None,
) -> str:
    """FR #4639: re-run a cancelled required check, or update-branch when behind.

    Returns ``reran`` | ``updated-branch`` | ``pending`` | ``capped`` | ``skipped``.
    A second call while the recorded run is still pending does not POST again.
    At most ``CI_RERUN_CAP`` pending re-runs (runner capacity).
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    sha = _norm_sha(pass_sha)
    if not repo_c or not num or not sha:
        return "skipped"
    doc = load_ledger(home)
    rows = doc.get(CI_RERUN_KEY)
    if not isinstance(rows, dict):
        rows = {}
        doc[CI_RERUN_KEY] = rows
    key = _row_key(repo_c, num)
    prev = rows.get(key)
    if (
        isinstance(prev, dict)
        and shas_match(str(prev.get("pass_sha") or ""), sha)
        and str(prev.get("state") or "") == "pending"
    ):
        return "pending"
    if _rerun_pending_count(doc) >= CI_RERUN_CAP:
        return "capped"
    run = str(run_id or "").strip()
    if behind:
        url = f"https://api.github.com/repos/{repo_c}/pulls/{num}/update-branch"
        method = "PUT"
        kind = "updated-branch"
    elif run:
        url = f"https://api.github.com/repos/{repo_c}/actions/runs/{run}/rerun"
        method = "POST"
        kind = "reran"
    else:
        return "skipped"
    if post_fn is not None:
        post_fn(url, method)
    else:
        tok = _gh_token(token)
        if not tok:
            return "skipped"
        _gh_json(url, token=tok, method=method, body={})
    rows[key] = {
        "pass_sha": sha,
        "run_id": run,
        "state": "pending",
        "kind": kind,
        "epoch": float(now_epoch if now_epoch is not None else time.time()),
    }
    save_ledger(home, doc)
    return kind


def prune_ci_failed(doc: dict[str, Any], *, now_epoch: float, ttl_s: float = CI_FAILED_TTL_S) -> int:
    parked = doc.get(CI_FAILED_KEY)
    if not isinstance(parked, dict):
        doc[CI_FAILED_KEY] = {}
        return 0
    stale = []
    for k, v in parked.items():
        try:
            age = now_epoch - float((v or {}).get("failed_epoch") or 0.0)
        except (TypeError, ValueError, AttributeError):
            age = ttl_s + 1
        if age > ttl_s:
            stale.append(k)
    for k in stale:
        parked.pop(k, None)
    return len(stale)


def ci_failed_pass_sha(doc: dict[str, Any], repo: str, pr: str) -> str:
    parked = doc.get(CI_FAILED_KEY)
    if not isinstance(parked, dict):
        return ""
    rec = parked.get(_row_key(repo, pr))
    return str((rec or {}).get("pass_sha") or "") if isinstance(rec, dict) else ""


def pr_is_ci_fail_tracked(home: Path, repo: str, pr: str) -> bool:
    """True when ``repo#pr`` is parked under the CI-failed ledger (FR #4706)."""
    doc = load_ledger(home)
    parked = doc.get(CI_FAILED_KEY)
    if not isinstance(parked, dict):
        return False
    rec = parked.get(_row_key(gitclaim.canonical_queue_repo(repo), pr))
    return isinstance(rec, dict)


def _checks_are_failed(checks: str) -> bool:
    state = (checks or "").strip().lower()
    head = state.split(":", 1)[0] if state else ""
    return head in (
        "failure",
        "failed",
        "error",
        "action_required",
        "timed_out",
        "cancelled",
        "canceled",
    )


def refresh_ci_failed_tips(
    home: Path,
    *,
    fetch_pr: Callable[..., dict[str, Any]] | None = None,
    main_red: bool | None = None,
    token: str | None = None,
    now_epoch: float | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """FR #4706: re-offer FIX when a parked CI-failed tip fails again (new head SHA).

    Same-SHA failures stay deduped via ``enqueue_fix_ci``. Closed/merged tips leave
    the park list. Pending/green tips are left alone until the next sweep.
    """
    fetch_pr = fetch_pr or (lambda repo, pr: fetch_pr_state(repo, pr, token=token))
    tnow = float(now_epoch if now_epoch is not None else time.time())
    out: dict[str, Any] = {
        "seen": 0,
        "offered": 0,
        "deduped": 0,
        "skipped": 0,
        "errors": 0,
    }
    doc = load_ledger(home)
    parked = doc.get(CI_FAILED_KEY)
    if not isinstance(parked, dict) or not parked:
        return out
    main_red_cache: dict[str, bool] = {}
    items = [(k, dict(v)) for k, v in list(parked.items()) if isinstance(v, dict)]
    for key, rec in items:
        out["seen"] += 1
        repo = str(rec.get("repo") or "")
        pr = str(rec.get("pr") or "")
        if not repo or not pr:
            out["skipped"] += 1
            continue
        if not force:
            nxt = rec.get("next_refresh_epoch")
            if nxt is not None:
                try:
                    if float(nxt) > tnow:
                        out["skipped"] += 1
                        continue
                except (TypeError, ValueError):
                    pass
        try:
            pr_state = fetch_pr(repo, pr)
        except Exception:  # noqa: BLE001
            out["errors"] += 1
            continue
        # Schedule next poll regardless of outcome (FR #4566 API quiet).
        live_parked = doc.get(CI_FAILED_KEY)
        if isinstance(live_parked, dict) and isinstance(live_parked.get(key), dict):
            live_parked[key]["next_refresh_epoch"] = tnow + float(CI_FAILED_REFRESH_S)
            live_parked[key]["last_refresh_epoch"] = tnow
            save_ledger(home, doc)
        if bool(pr_state.get("merged")) or bool(pr_state.get("closed")):
            parked.pop(key, None)
            save_ledger(home, doc)
            out["skipped"] += 1
            continue
        detail = str(pr_state.get("checks") or "failure")
        if not _checks_are_failed(detail):
            out["skipped"] += 1
            continue
        tip_sha = _norm_sha(str(pr_state.get("sha") or ""))
        if not tip_sha:
            out["skipped"] += 1
            continue
        repo_c = gitclaim.canonical_queue_repo(repo)
        if main_red is not None:
            mr = bool(main_red)
        else:
            if repo_c not in main_red_cache:
                main_red_cache[repo_c] = main_branch_checks_red(repo_c, token=token)
            mr = main_red_cache[repo_c]
        try:
            result = enqueue_fix_ci(
                home,
                repo=repo_c,
                pr=pr,
                pass_sha=tip_sha,
                url=str(pr_state.get("html_url") or rec.get("url") or ""),
                detail=detail,
                now_epoch=tnow,
                main_red=mr,
                token=token,
                mergeable=pr_state.get("mergeable"),
                merge_state=str(
                    pr_state.get("merge_state_status")
                    or pr_state.get("mergeable_state")
                    or ""
                ),
            )
        except Exception:  # noqa: BLE001
            out["errors"] += 1
            continue
        if result == "added":
            out["offered"] += 1
            doc = load_ledger(home)
            park_ci_failed(
                doc,
                {
                    "repo": repo_c,
                    "pr": pr,
                    "pass_sha": tip_sha,
                    "url": str(pr_state.get("html_url") or rec.get("url") or ""),
                    "nick": str(rec.get("nick") or ""),
                },
                detail=detail,
                now_epoch=tnow,
            )
            save_ledger(home, doc)
        elif result == "duplicate":
            out["deduped"] += 1
        else:
            out["skipped"] += 1
    return out


def handle_check_run_event(
    home: Path,
    payload: dict[str, Any],
    *,
    main_red: bool | None = None,
    token: str | None = None,
) -> str:
    """FR #4706: check_run failure for a parked CI-failed PR -> FIX for that head SHA.

    Returns ``added`` | ``duplicate`` | ``skipped``. Unknown / untracked PRs skip.
    """
    if not isinstance(payload, dict):
        return "skipped"
    cr = payload.get("check_run")
    if not isinstance(cr, dict):
        return "skipped"
    status = str(cr.get("status") or "").strip().lower()
    conclusion = str(cr.get("conclusion") or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    if status and status != "completed":
        return "skipped"
    if action and action not in ("completed", "rerequested", ""):
        # Still allow completed payloads that omit / use other action strings.
        if status != "completed":
            return "skipped"
    if conclusion not in _FAIL_CONCLUSIONS and conclusion not in (
        "failure",
        "timed_out",
        "action_required",
    ):
        return "skipped"
    repository = payload.get("repository")
    repo = ""
    if isinstance(repository, dict):
        repo = str(repository.get("full_name") or "").strip()
    if not repo:
        return "skipped"
    prs = cr.get("pull_requests")
    if not isinstance(prs, list) or not prs:
        return "skipped"
    head_sha = _norm_sha(str(cr.get("head_sha") or ""))
    if not head_sha:
        return "skipped"
    check_run_id = str(cr.get("id") or "")
    name = str(cr.get("name") or "").strip()
    detail = f"{conclusion}:{name}" if name else (conclusion or "failure")
    last = "skipped"
    tracked = False
    for pr_obj in prs:
        if not isinstance(pr_obj, dict):
            continue
        num = pr_obj.get("number")
        if num is None:
            continue
        pr = str(num)
        if not pr_is_ci_fail_tracked(home, repo, pr):
            continue
        tracked = True
        result = enqueue_fix_ci(
            home,
            repo=repo,
            pr=pr,
            pass_sha=head_sha,
            url=f"https://github.com/{repo}/pull/{pr}",
            detail=detail,
            check_run_id=check_run_id,
            main_red=main_red,
            token=token,
        )
        if result == "added":
            doc = load_ledger(home)
            park_ci_failed(
                doc,
                {
                    "repo": gitclaim.canonical_queue_repo(repo),
                    "pr": pr,
                    "pass_sha": head_sha,
                    "url": f"https://github.com/{repo}/pull/{pr}",
                },
                detail=detail,
            )
            save_ledger(home, doc)
            return "added"
        last = result
    if not tracked:
        return "skipped"
    return last


def merge_attempt_conflict_reason(
    *,
    http_error: str = "",
    mergeable: Any = "",
    merge_state: str = "",
) -> str | None:
    """FR #4636: why this merge attempt must stop for the current head SHA.

    HTTP 405 from ``PUT /merges``, GraphQL ``mergeable: CONFLICTING``, or
    ``mergeStateStatus`` / REST ``mergeable_state`` of DIRTY.
    """
    if re.search(r"\b405\b", str(http_error or "")):
        return "http-405"
    if str(mergeable or "").strip().upper() == "CONFLICTING":
        return "conflicting"
    if str(merge_state or "").strip().upper() in ("DIRTY", "CONFLICTING"):
        return "conflicting"
    return None


def park_conflict(
    doc: dict[str, Any],
    row: dict[str, Any],
    *,
    reason: str,
    head_sha: str = "",
) -> dict[str, Any]:
    """Remember a conflicting PASS row so merge-on-green does not retry that SHA."""
    repo_c = gitclaim.canonical_queue_repo(str(row.get("repo") or ""))
    num = str(row.get("pr") or "").lstrip("#")
    key = _row_key(repo_c, num)
    sha = _norm_sha(head_sha or str(row.get("pass_sha") or ""))
    rec = {
        "key": key,
        "repo": repo_c,
        "pr": num,
        "pass_sha": sha,
        "url": str(row.get("url") or f"https://github.com/{repo_c}/pull/{num}"),
        "nick": str(row.get("nick") or ""),
        "reason": reason or "conflicting",
        "blocked_ts": _utc(),
    }
    parked = doc.get(CONFLICT_KEY)
    if not isinstance(parked, dict):
        parked = {}
        doc[CONFLICT_KEY] = parked
    parked[key] = rec
    return rec


def conflict_blocked_pass_sha(doc: dict[str, Any], repo: str, pr: str) -> str:
    parked = doc.get(CONFLICT_KEY)
    if not isinstance(parked, dict):
        return ""
    rec = parked.get(_row_key(repo, pr))
    return str((rec or {}).get("pass_sha") or "") if isinstance(rec, dict) else ""


def enqueue_conflict_fix(
    home: Path,
    *,
    repo: str,
    pr: str,
    pass_sha: str,
    url: str = "",
    reason: str = "",
    pr_state: dict[str, Any] | None = None,
) -> str:
    """Queue one FIX to merge main and resolve conflicts for this PR+SHA (FR #4636).

    Same SHA returns ``duplicate``. A later SHA is a new job once any earlier FIX
    row for this PR has left the queue. FIX stays offerable to any seat: the
    author block applies to MRB/UAT, not to FIX.

    FR #5720: harvest-lesson tips closed unmerged (or FAIL-supersede / CLOSED /
    MOVED disposition-boarded) return ``skipped`` — never ``FIX conflict``.
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    sha = _norm_sha(pass_sha)
    if not repo_c or not num or not sha:
        return "skipped"
    state = pr_state
    if state is None:
        try:
            state = fetch_pr_state(repo_c, num)
        except Exception:  # noqa: BLE001
            state = None
    if isinstance(state, dict) and skip_mrb_fail_fix_for_harvest(
        title=str(state.get("title") or ""),
        labels=tuple(state.get("labels") or ()),
        closed=bool(state.get("closed")),
        merged=bool(state.get("merged")),
        comments=state.get("comments") if isinstance(state.get("comments"), list) else None,
    ):
        return "skipped"
    sig = f"conflict|{repo_c}|{num}|{sha}"
    doc = load_ledger(home)
    offered = doc.get(CONFLICT_FIX_KEY)
    if not isinstance(offered, dict):
        offered = {}
        doc[CONFLICT_FIX_KEY] = offered
    prev = offered.get(sig)
    if isinstance(prev, dict) and shas_match(str(prev.get("pass_sha") or ""), sha):
        return "duplicate"
    pull_url = url or f"https://github.com/{repo_c}/pull/{num}"
    title = f"FIX conflict ({reason or 'conflicting'}; {num}@{sha[:12]})"
    body = (
        f"FR #4636/#4679 conflict-fix: PR is {reason or 'conflicting'} "
        f"for head SHA {sha}. Merge origin/main into this branch, resolve the "
        f"conflicts, and push. One job per PR+SHA. Offer to any seat (FIX is not "
        f"author-blocked). Signature {sig}."
    )
    claim = gitclaim.GitClaim(
        repo=repo_c,
        task="FIX",
        id=f"#{num}",
        event="pull_request",
        action="synchronize",
        line=pull_url,
        title=title,
        body=body,
        labels=("via-intake", "fix-conflict"),
    )
    with gitclaim._lock(home):
        try:
            qdoc = gitclaim._load_queue_unlocked(home)
        except (OSError, ValueError):
            qdoc = gitclaim._empty_queue()
        for row in list(qdoc.get("unaccepted") or []) + list(qdoc.get("accepted") or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "FIX":
                continue
            if gitclaim.canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            blob = str(row.get("body") or "") + " " + str(row.get("title") or "")
            if sig in blob:
                offered[sig] = {"repo": repo_c, "pr": num, "pass_sha": sha, "signature": sig, "url": pull_url}
                save_ledger(home, doc)
                return "duplicate"
        changed = gitclaim._append_unaccepted(
            qdoc,
            claim,
            url=pull_url,
            body=body,
            title=claim.title,
            pass_sha=sha,
            fail_signature=sig,
        )
        try:
            gitclaim._write_queue(gitclaim.queue_path(home), qdoc)
        except OSError:
            return "skipped"
    if changed in ("added", "duplicate"):
        offered[sig] = {"repo": repo_c, "pr": num, "pass_sha": sha, "signature": sig, "url": pull_url}
        save_ledger(home, doc)
        return changed if changed in ("added", "duplicate") else "skipped"
    return "skipped"


def rearm_conflict_blocked(home: Path, *, repo: str, pr: str, head_sha: str) -> str:
    """Drop a conflict block when the head SHA changes and resume merge-on-green.

    Returns ``blocked`` (same SHA), ``rearmed`` (pending row restored on the new
    SHA), or ``""`` when this PR is not conflict-blocked.
    """
    new = _norm_sha(head_sha)
    doc = load_ledger(home)
    parked = doc.get(CONFLICT_KEY)
    if not isinstance(parked, dict):
        return ""
    key = _row_key(repo, pr)
    rec = parked.get(key)
    if not isinstance(rec, dict):
        return ""
    old = _norm_sha(str(rec.get("pass_sha") or ""))
    if not new or shas_match(old, new):
        return "blocked"
    parked.pop(key, None)
    doc[CONFLICT_KEY] = parked
    save_ledger(home, doc)
    enqueue(
        home,
        repo=str(rec.get("repo") or repo),
        pr=str(rec.get("pr") or pr),
        pass_sha=new,
        url=str(rec.get("url") or ""),
        nick=str(rec.get("nick") or ""),
    )
    return "rearmed"


def save_ledger(home: Path, doc: dict[str, Any]) -> None:
    path = ledger_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _row_key(repo: str, pr: str) -> str:
    return f"{gitclaim.canonical_queue_repo(repo)}#{str(pr).lstrip('#')}"


def enqueue(
    home: Path,
    *,
    repo: str,
    pr: str,
    pass_sha: str,
    url: str = "",
    nick: str = "",
    hold_reason: str | None = None,
) -> dict[str, Any]:
    """Record or refresh a merge-on-green pending row. Held PRs are recorded as skipped."""
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    sha = _norm_sha(pass_sha)
    if not repo_c or not num or not sha:
        raise ValueError("repo, pr and pass_sha are required")
    key = _row_key(repo_c, num)
    doc = load_ledger(home)
    pending = [p for p in (doc.get("pending") or []) if isinstance(p, dict)]
    row = {
        "key": key,
        "repo": repo_c,
        "pr": num,
        "pass_sha": sha,
        "url": url
        or f"https://github.com/{repo_c}/pull/{num}",
        "nick": nick,
        "enqueued_ts": _utc(),
        "status": "skip_hold" if hold_reason else "pending",
        "hold_reason": hold_reason or "",
    }
    out: list[dict] = []
    replaced = False
    for old in pending:
        if str(old.get("key") or "") == key:
            out.append(row)
            replaced = True
        else:
            out.append(old)
    if not replaced:
        out.append(row)
    doc["pending"] = out
    parked = doc.get(CI_FAILED_KEY)
    if isinstance(parked, dict):
        parked.pop(key, None)
    save_ledger(home, doc)
    return row


def drop(home: Path, *, repo: str, pr: str) -> bool:
    key = _row_key(repo, pr)
    doc = load_ledger(home)
    before = list(doc.get("pending") or [])
    after = [p for p in before if isinstance(p, dict) and str(p.get("key") or "") != key]
    if len(after) == len(before):
        return False
    doc["pending"] = after
    save_ledger(home, doc)
    return True


_last_rate_remaining: int | None = None


def get_rate_remaining() -> int | None:
    """Last X-RateLimit-Remaining seen by merge-on-green GitHub calls (FR #4543)."""
    return _last_rate_remaining


def _note_rate_headers(hdrs) -> None:
    global _last_rate_remaining
    if hdrs is None:
        return
    try:
        get = hdrs.get
    except Exception:  # noqa: BLE001
        return
    rem = get("X-RateLimit-Remaining") or get("x-ratelimit-remaining")
    if rem is None:
        return
    try:
        _last_rate_remaining = int(str(rem).strip())
    except ValueError:
        pass


def _gh_token(token: str | None = None) -> str:
    if token is not None:
        return token.strip()
    return (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()


def _gh_json(url: str, *, token: str, method: str = "GET", body: dict | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-mrb-merge-on-green",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            _note_rate_headers(getattr(resp, "headers", None))
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        _note_rate_headers(getattr(e, "headers", None))
        raise RuntimeError(f"GitHub HTTP {e.code} for {url}") from e


def fetch_pr_state(repo: str, pr: str, *, token: str | None = None) -> dict[str, Any]:
    """Return head sha, merged flag, labels, and rollup check state for the PR tip."""
    tok = _gh_token(token)
    if not tok:
        raise RuntimeError("GH_TOKEN/GITHUB_TOKEN required for merge-on-green")
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    pr_doc = _gh_json(f"https://api.github.com/repos/{repo_c}/pulls/{num}", token=tok)
    head = pr_doc.get("head") if isinstance(pr_doc.get("head"), dict) else {}
    sha = _norm_sha(str(head.get("sha") or ""))
    merged = bool(pr_doc.get("merged"))
    state = str(pr_doc.get("state") or "")
    labels: list[str] = []
    for lab in pr_doc.get("labels") or []:
        if isinstance(lab, dict) and lab.get("name"):
            labels.append(str(lab["name"]))
    title = str(pr_doc.get("title") or "")
    body = str(pr_doc.get("body") or "")
    checks = "none"
    if sha:
        status = None
        try:
            status = _gh_json(
                f"https://api.github.com/repos/{repo_c}/commits/{sha}/status",
                token=tok,
            )
        except RuntimeError:
            checks = "pending"
        else:
            # FR #4566: pending + 0 statuses is Actions-only, not an open check.
            if combined_status_is_empty(status):
                try:
                    runs = _gh_json(
                        f"https://api.github.com/repos/{repo_c}/commits/{sha}/check-runs",
                        token=tok,
                    )
                    # FR #5865: CodeRabbit never blocks merge-on-green.
                    checks = rollup_check_runs(runs, ignore_coderabbit=True)
                except RuntimeError:
                    checks = "pending"
            else:
                checks = str(status.get("state") or "none").lower()
    return {
        "repo": repo_c,
        "pr": num,
        "sha": sha,
        "merged": merged or state == "closed" and bool(pr_doc.get("merged_at")),
        "closed": state == "closed",
        "labels": labels,
        "title": title,
        "body": body,
        "checks": checks,
        "html_url": str(pr_doc.get("html_url") or ""),
        "mergeable": pr_doc.get("mergeable") if pr_doc.get("mergeable") is not None else "",
        "merge_state_status": str(
            pr_doc.get("mergeable_state") or pr_doc.get("mergeStateStatus") or ""
        ),
    }


def merge_pull(
    repo: str,
    pr: str,
    *,
    pass_sha: str,
    token: str | None = None,
    merge_method: str = "merge",
) -> dict[str, Any]:
    """PUT /merges for the PR when the tip still matches ``pass_sha``."""
    tok = _gh_token(token)
    if not tok:
        raise RuntimeError("GH_TOKEN/GITHUB_TOKEN required to merge")
    repo_c = gitclaim.canonical_queue_repo(repo)
    num = str(pr).lstrip("#")
    return _gh_json(
        f"https://api.github.com/repos/{repo_c}/pulls/{num}/merge",
        token=tok,
        method="PUT",
        body={
            "merge_method": merge_method,
            "sha": _norm_sha(pass_sha),
        },
    )


def requeue_mrb(home: Path, *, repo: str, pr: str, url: str = "", reason: str = "") -> None:
    """Clear premature mrb_done and put the PR back on the unaccepted MRB queue.

    FR #4929: also pop stale MRB PASS/FAIL from ``done[]`` so purge cannot drop
    the fresh row when ``pr_exists`` is absent.
    """
    repo_c = gitclaim.canonical_queue_repo(repo)
    pull = url or f"https://github.com/{repo_c}/pull/{str(pr).lstrip('#')}"
    with gitclaim._lock(home):
        try:
            doc = gitclaim._load_queue_unlocked(home)
        except (OSError, ValueError):
            doc = gitclaim._empty_queue()
        gitclaim.ensure_mrb_requeued_after_head_move(
            doc,
            home,
            repo=repo_c,
            pr=pr,
            url=pull,
            reason=reason or "merge-on-green",
        )
        try:
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
        except OSError:
            pass


def evaluate_pending_row(
    row: dict[str, Any],
    *,
    pr_state: dict[str, Any],
    comments: list[dict] | None = None,
) -> tuple[Decision, str]:
    """Combine live PR state + hold/gate with the pure decision."""
    hold = gitclaim.pr_hold_reason(
        title=str(pr_state.get("title") or ""),
        body=str(pr_state.get("body") or ""),
        labels=tuple(str(x) for x in (pr_state.get("labels") or [])),
    )
    if not hold and comments is not None:
        hold = mrb_merge_gate.find_active_owner_hold(comments)
    ok_gate, gate_reason = mrb_merge_gate.evaluate_merge_gate(comments)
    if hold:
        return "skip_hold", hold
    if not ok_gate and "hold" in (gate_reason or "").lower():
        return "skip_hold", gate_reason
    checks = str(pr_state.get("checks") or "none")
    decision = decide_merge_on_green(
        pass_sha=str(row.get("pass_sha") or ""),
        current_sha=str(pr_state.get("sha") or ""),
        checks=checks,
        hold_reason=None,
        merged=bool(pr_state.get("merged")),
        closed=bool(pr_state.get("closed")),
    )
    if decision == "merge" and not ok_gate:
        # Still waiting for PASS board scrape, or other gate refuse that is not hold.
        if "pass" in (gate_reason or "").lower() or "board" in (gate_reason or "").lower():
            return "wait", gate_reason
        return "wait", gate_reason or "merge gate refused"
    # FR #4833: surface the human-label reason when lock parked the tip.
    if decision == "skip_hold" and fix_ci_skip_reason(checks) == "human-gated-lock":
        return "skip_hold", HUMAN_GATED_LOCK_REASON
    return decision, ""


def _stop_conflict_retry(
    home: Path,
    doc: dict[str, Any],
    row: dict[str, Any],
    *,
    reason: str,
    head_sha: str,
    summary: dict[str, Any],
    log: Callable[[str], None],
) -> None:
    """Park the SHA and queue at most one conflict-fix job (FR #4636)."""
    park_conflict(doc, row, reason=reason, head_sha=head_sha)
    save_ledger(home, doc)
    result = "skipped"
    try:
        result = enqueue_conflict_fix(
            home,
            repo=str(row.get("repo") or ""),
            pr=str(row.get("pr") or ""),
            pass_sha=head_sha or str(row.get("pass_sha") or ""),
            url=str(row.get("url") or ""),
            reason=reason,
        )
    except Exception as exc:  # noqa: BLE001
        summary["errors"] = int(summary.get("errors") or 0) + 1
        log(f"WARN merge-on-green conflict-fix enqueue failed: {exc}")
    fresh = load_ledger(home)
    if isinstance(fresh.get(CONFLICT_KEY), dict):
        doc[CONFLICT_KEY] = fresh[CONFLICT_KEY]
    if isinstance(fresh.get(CONFLICT_FIX_KEY), dict):
        doc[CONFLICT_FIX_KEY] = fresh[CONFLICT_FIX_KEY]
    summary["conflict_parked"] = int(summary.get("conflict_parked") or 0) + 1
    summary["dropped"] = int(summary.get("dropped") or 0) + 1
    if result == "added":
        summary["fix_offered"] = int(summary.get("fix_offered") or 0) + 1
    log(
        f"INFO merge-on-green stop conflict {row.get('repo')}#{row.get('pr')} "
        f"@{str(head_sha)[:12]} reason={reason} fix={result}"
    )


def process_pending(
    home: Path,
    *,
    fetch_pr: Callable[..., dict[str, Any]] | None = None,
    fetch_comments: Callable[..., list[dict]] | None = None,
    merge_fn: Callable[..., dict[str, Any]] | None = None,
    token: str | None = None,
    log: Callable[[str], None] | None = None,
    rate_remaining: Callable[[], int | None] | None = None,
    min_rate_remaining: int = DEFAULT_MIN_RATE_REMAINING,
    now: Callable[[], float] | None = None,
    max_wait_s: int = MAX_WAIT_S,
    backoff_base_s: int = BACKOFF_BASE_S,
    backoff_cap_s: int = BACKOFF_CAP_S,
) -> dict[str, Any]:
    """Advance every merge-on-green pending row once. Pure side effects via injectables.

    FR #4543: when ``rate_remaining()`` is below ``min_rate_remaining``, back off
    without fetching so ``pr_exists`` / offers / ``!resync`` keep budget. Closed or
    merged PRs are dropped after one PR GET and never fetch comments.
    """
    _log = log or (lambda _m: None)
    fetch_pr = fetch_pr or (lambda repo, pr: fetch_pr_state(repo, pr, token=token))
    fetch_comments = fetch_comments or (
        lambda repo, pr: mrb_merge_gate.fetch_issue_comments(repo, pr, token=token)
    )
    merge_fn = merge_fn or (
        lambda repo, pr, pass_sha: merge_pull(repo, pr, pass_sha=pass_sha, token=token)
    )

    doc = load_ledger(home)
    pending = [p for p in (doc.get("pending") or []) if isinstance(p, dict)]
    keep: list[dict] = []
    summary: dict[str, Any] = {
        "seen": len(pending),
        "merged": 0,
        "wait": 0,
        "requeued": 0,
        "fix_offered": 0,
        "fix_skip_main_red": 0,
        "skipped_hold": 0,
        "dropped": 0,
        "errors": 0,
        "backed_off": False,
        "deferred": 0,
        "ci_failed": 0,
        "conflict_parked": 0,
        "actions": [],
    }
    now_fn = now or time.time
    try:
        tnow = float(now_fn())
    except (TypeError, ValueError):
        tnow = time.time()
    # FR #4596: one main-branch check probe per repo per sweep.
    main_red_cache: dict[str, bool] = {}

    if rate_remaining is not None:
        try:
            rem = rate_remaining()
        except Exception:  # noqa: BLE001
            rem = None
        if rem is not None and int(rem) < int(min_rate_remaining):
            summary["backed_off"] = True
            summary["rate_remaining"] = int(rem)
            _log(
                f"INFO merge-on-green back-off rate_remaining={rem} "
                f"min={min_rate_remaining} pending={len(pending)}"
            )
            return summary

    for row in pending:
        repo = str(row.get("repo") or "")
        pr = str(row.get("pr") or "")
        if not repo or not pr:
            summary["dropped"] += 1
            continue
        first_wait = row.get("first_wait_epoch")
        if first_wait is not None:
            try:
                waited = tnow - float(first_wait)
            except (TypeError, ValueError):
                waited = 0.0
            if waited >= float(max_wait_s):
                summary["requeued"] += 1
                try:
                    requeue_mrb(
                        home,
                        repo=repo,
                        pr=pr,
                        url=str(row.get("url") or ""),
                        reason="wait_cap",
                    )
                except Exception as exc:  # noqa: BLE001
                    summary["errors"] += 1
                    row = dict(row)
                    row["last_error"] = f"requeue {type(exc).__name__}: {exc}"
                    keep.append(row)
                    continue
                summary["actions"].append(
                    {"repo": repo, "pr": pr, "decision": "requeue_ci", "detail": "wait_cap"}
                )
                _log(f"INFO merge-on-green requeue {repo}#{pr} reason=wait_cap")
                continue
        nxt = row.get("next_fetch_epoch")
        if nxt is not None:
            try:
                if float(nxt) > tnow:
                    summary["wait"] += 1
                    summary["deferred"] += 1
                    keep.append(dict(row))
                    continue
            except (TypeError, ValueError):
                pass
        try:
            pr_state = fetch_pr(repo, pr)
            # FR #4543: closed/merged leave the ledger; do not spend a comments GET.
            if bool(pr_state.get("merged")) or bool(pr_state.get("closed")):
                decision = "drop_merged" if pr_state.get("merged") else "drop_closed"
                detail = "merged" if pr_state.get("merged") else "closed"
                action = {"repo": repo, "pr": pr, "decision": decision, "detail": detail}
                summary["actions"].append(action)
                summary["dropped"] += 1
                _log(f"INFO merge-on-green drop {repo}#{pr}: {detail}")
                continue
            comments = fetch_comments(repo, pr)
            decision, detail = evaluate_pending_row(row, pr_state=pr_state, comments=comments)
        except Exception as exc:  # noqa: BLE001
            summary["errors"] += 1
            row = dict(row)
            row["last_error"] = f"{type(exc).__name__}: {exc}"
            row["last_ts"] = _utc()
            keep.append(row)
            _log(f"WARN merge-on-green {repo}#{pr}: {type(exc).__name__}: {exc}")
            continue

        action = {"repo": repo, "pr": pr, "decision": decision, "detail": detail}
        summary["actions"].append(action)
        row = dict(row)
        row["last_decision"] = decision
        row["last_ts"] = _utc()
        if detail:
            row["last_detail"] = detail

        # FR #4714: a keep-both fold moves the head and posts a new PASS before
        # this sweep. requeue_sha would clear mrb_done and then resync drops the
        # MRB (already PASSed at head) while also dropping pending, so a later
        # DIRTY tip never reaches the conflict-FIX path.
        if decision == "requeue_sha":
            current = _norm_sha(str(pr_state.get("sha") or ""))
            board = _norm_sha(parse_pass_sha_from_comments(comments) or "")
            if current and board and shas_match(board, current):
                row["pass_sha"] = current
                decision = decide_merge_on_green(
                    pass_sha=current,
                    current_sha=current,
                    checks=str(pr_state.get("checks") or "none"),
                    merged=bool(pr_state.get("merged")),
                    closed=bool(pr_state.get("closed")),
                )
                row["last_decision"] = decision
                action["decision"] = decision
                action["detail"] = "pass_at_head"
                _log(
                    f"INFO merge-on-green retarget {repo}#{pr} "
                    f"@{current[:12]} follow={decision}"
                )

        if decision == "merge":
            conflict = merge_attempt_conflict_reason(
                mergeable=pr_state.get("mergeable"),
                merge_state=str(
                    pr_state.get("merge_state_status")
                    or pr_state.get("mergeable_state")
                    or ""
                ),
            )
            if conflict:
                _stop_conflict_retry(
                    home,
                    doc,
                    row,
                    reason=conflict,
                    head_sha=str(pr_state.get("sha") or row.get("pass_sha") or ""),
                    summary=summary,
                    log=_log,
                )
                continue
            try:
                merge_fn(repo, pr, str(row.get("pass_sha") or ""))
                summary["merged"] += 1
                _log(f"INFO merge-on-green merged {repo}#{pr} @{row.get('pass_sha')}")
                continue  # drop from pending
            except Exception as exc:  # noqa: BLE001
                conflict = merge_attempt_conflict_reason(http_error=str(exc))
                if conflict:
                    _stop_conflict_retry(
                        home,
                        doc,
                        row,
                        reason=conflict,
                        head_sha=str(pr_state.get("sha") or row.get("pass_sha") or ""),
                        summary=summary,
                        log=_log,
                    )
                    continue
                summary["errors"] += 1
                row["last_error"] = f"{type(exc).__name__}: {exc}"
                keep.append(row)
                _log(f"WARN merge-on-green merge failed {repo}#{pr}: {exc}")
                continue

        if decision in ("drop_merged", "drop_closed"):
            summary["dropped"] += 1
            continue

        if decision == "skip_hold":
            summary["skipped_hold"] += 1
            row["status"] = "skip_hold"
            row["hold_reason"] = detail or row.get("hold_reason") or "hold"
            keep.append(row)
            # FR #4833: park a visible needs_human FIX so seats do not burn turns.
            if HUMAN_GATED_LOCK_REASON in str(row.get("hold_reason") or ""):
                try:
                    park_human_gated_lock(
                        home,
                        repo=repo,
                        pr=pr,
                        sha=str(row.get("pass_sha") or pr_state.get("sha") or ""),
                        url=str(row.get("url") or pr_state.get("html_url") or ""),
                        detail=str(pr_state.get("checks") or "failure:lock"),
                    )
                except Exception as exc:  # noqa: BLE001
                    _log(
                        f"WARN merge-on-green lock needs_human park failed "
                        f"{repo}#{pr}: {exc}"
                    )
            _log(f"INFO merge-on-green skip hold {repo}#{pr}: {row['hold_reason']}")
            continue

        if decision == "requeue_ci":
            # FR #4566 follow-up: stop polling; keep the PASS SHA so resync does
            # not turn it back into an MRB while the head is unchanged.
            # FR #4585: offer one FIX (deduped by failure signature) instead of
            # leaving the queue empty while PASSed+auto-merge tips sit red forever.
            detail = str(pr_state.get("checks") or "failure")
            park_ci_failed(doc, row, detail=detail, now_epoch=tnow)
            summary["ci_failed"] += 1
            summary["dropped"] += 1
            fix_result = "skipped"
            try:
                repo_c = gitclaim.canonical_queue_repo(repo)
                if repo_c not in main_red_cache:
                    main_red_cache[repo_c] = main_branch_checks_red(
                        repo_c, token=token
                    )
                fix_result = enqueue_fix_ci(
                    home,
                    repo=repo,
                    pr=pr,
                    pass_sha=str(row.get("pass_sha") or ""),
                    url=str(row.get("url") or pr_state.get("html_url") or ""),
                    detail=detail,
                    now_epoch=tnow,
                    main_red=main_red_cache[repo_c],
                    token=token,
                )
                if fix_result == "added":
                    summary["fix_offered"] = int(summary.get("fix_offered") or 0) + 1
                elif fix_result == "skipped_main_added":
                    summary["fix_offered"] = int(summary.get("fix_offered") or 0) + 1
                    summary["fix_skip_main_red"] = (
                        int(summary.get("fix_skip_main_red") or 0) + 1
                    )
                elif fix_result == "skipped_main_duplicate":
                    summary["fix_skip_main_red"] = (
                        int(summary.get("fix_skip_main_red") or 0) + 1
                    )
            except Exception as exc:  # noqa: BLE001
                summary["errors"] += 1
                _log(f"WARN merge-on-green FIX enqueue failed {repo}#{pr}: {exc}")
            _log(
                f"INFO merge-on-green drop ci-failed {repo}#{pr} "
                f"@{str(row.get('pass_sha') or '')[:12]} checks={detail} fix={fix_result}"
            )
            continue

        if decision == "requeue_sha":
            summary["requeued"] += 1
            try:
                requeue_mrb(
                    home,
                    repo=repo,
                    pr=pr,
                    url=str(row.get("url") or pr_state.get("html_url") or ""),
                    reason=decision,
                )
            except Exception as exc:  # noqa: BLE001
                summary["errors"] += 1
                row["last_error"] = f"requeue {type(exc).__name__}: {exc}"
                keep.append(row)
                continue
            _log(f"INFO merge-on-green requeue {repo}#{pr} reason={decision}")
            continue  # drop pending after requeue

        # wait — back off so a still-pending row is not fetched every sweep (FR #4566).
        summary["wait"] += 1
        row["status"] = "pending"
        polls = int(row.get("wait_polls") or 0) + 1
        row["wait_polls"] = polls
        if row.get("first_wait_epoch") is None:
            row["first_wait_epoch"] = tnow
        shift = min(polls - 1, 4)
        delay = min(int(backoff_base_s) * (2**shift), int(backoff_cap_s))
        row["next_fetch_epoch"] = tnow + delay
        keep.append(row)

    doc["pending"] = keep
    prune_ci_failed(doc, now_epoch=tnow)
    save_ledger(home, doc)
    # FR #4706: parked tips leave pending; still refresh when head advances + fails.
    summary.setdefault("ci_failed_refresh_offered", 0)
    summary.setdefault("ci_failed_refresh_deduped", 0)
    try:
        refresh = refresh_ci_failed_tips(
            home,
            fetch_pr=fetch_pr,
            token=token,
            now_epoch=tnow,
        )
        summary["ci_failed_refresh_offered"] = int(refresh.get("offered") or 0)
        summary["ci_failed_refresh_deduped"] = int(refresh.get("deduped") or 0)
        if summary["ci_failed_refresh_offered"]:
            summary["fix_offered"] = int(summary.get("fix_offered") or 0) + int(
                summary["ci_failed_refresh_offered"]
            )
            _log(
                f"INFO merge-on-green ci_failed refresh offered="
                f"{summary['ci_failed_refresh_offered']} "
                f"deduped={summary['ci_failed_refresh_deduped']}"
            )
    except Exception as exc:  # noqa: BLE001
        summary["errors"] += 1
        _log(f"WARN merge-on-green ci_failed refresh: {type(exc).__name__}: {exc}")
    return summary


def enqueue_from_done(
    home: Path,
    *,
    repo: str,
    pr_url: str,
    result: str,
    nick: str = "",
    fetch_pr: Callable[..., dict[str, Any]] | None = None,
    fetch_comments: Callable[..., list[dict]] | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    """On DONE MRB PASS, stamp merge-on-green with the PASSed head SHA.

    SHA preference: PR tip from GitHub, else newest PASS/@sha comment.
    """
    if str(result or "").strip().upper() != "PASS":
        return None
    parsed = gitclaim.parse_github_pull_url(pr_url or "")
    if not parsed:
        m = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_url or "", re.I)
        if not m:
            return None
        pr_repo, pr_num = m.group(1), m.group(2)
    else:
        pr_repo, pr_num = parsed[0], str(parsed[1]).lstrip("#")

    hold = None
    sha = ""
    try:
        fetch_pr = fetch_pr or (lambda r, p: fetch_pr_state(r, p, token=token))
        st = fetch_pr(pr_repo, pr_num)
        sha = _norm_sha(str(st.get("sha") or ""))
        hold = gitclaim.pr_hold_reason(
            title=str(st.get("title") or ""),
            body=str(st.get("body") or ""),
            labels=tuple(str(x) for x in (st.get("labels") or [])),
        )
    except Exception:  # noqa: BLE001
        st = {}
    if not sha:
        try:
            fetch_comments = fetch_comments or (
                lambda r, p: mrb_merge_gate.fetch_issue_comments(r, p, token=token)
            )
            sha = parse_pass_sha_from_comments(fetch_comments(pr_repo, pr_num)) or ""
        except Exception:  # noqa: BLE001
            sha = ""
    if not sha:
        return None
    url = pr_url or str(st.get("html_url") or "")
    # FR #5581: CONFLICTING/DIRTY at DONE time → queue conflict FIX at once and
    # do not leave a merge-pending row that sits while the seat stays "doing".
    conflict = merge_attempt_conflict_reason(
        mergeable=st.get("mergeable") if isinstance(st, dict) else "",
        merge_state=str(
            (st.get("merge_state_status") if isinstance(st, dict) else None)
            or (st.get("mergeable_state") if isinstance(st, dict) else None)
            or ""
        ),
    )
    if conflict:
        st_dict = st if isinstance(st, dict) else {}
        # FR #5720: closed harvest FAIL-supersede must not enqueue FIX conflict
        # (FR #4800 carve-out for the DONE CONFLICTING path / FR #5581).
        if skip_mrb_fail_fix_for_harvest(
            title=str(st_dict.get("title") or ""),
            labels=tuple(st_dict.get("labels") or ()),
            closed=bool(st_dict.get("closed")),
            merged=bool(st_dict.get("merged")),
            comments=(
                st_dict.get("comments")
                if isinstance(st_dict.get("comments"), list)
                else None
            ),
        ):
            return {
                "key": _row_key(pr_repo, pr_num),
                "repo": gitclaim.canonical_queue_repo(pr_repo),
                "pr": str(pr_num).lstrip("#"),
                "pass_sha": sha,
                "url": url,
                "nick": nick,
                "status": "skipped_harvest_disposition",
                "conflict_reason": conflict,
                "conflict_fix": "skipped",
            }
        fix = offer_dirty_conflict_fix(
            home,
            repo=pr_repo,
            pr=pr_num,
            sha=sha,
            url=url,
            reason=conflict,
            pr_state=st_dict or None,
        )
        # Park so resync/process_pending do not re-try merge on this SHA.
        doc = load_ledger(home)
        park_conflict(
            doc,
            {
                "repo": gitclaim.canonical_queue_repo(pr_repo),
                "pr": str(pr_num).lstrip("#"),
                "pass_sha": sha,
                "url": url,
                "nick": nick,
            },
            reason=conflict,
            head_sha=sha,
        )
        # Drop any prior pending merge row for this PR.
        key = _row_key(pr_repo, pr_num)
        pending = [
            p
            for p in (doc.get("pending") or [])
            if isinstance(p, dict) and str(p.get("key") or "") != key
        ]
        doc["pending"] = pending
        save_ledger(home, doc)
        return {
            "key": key,
            "repo": gitclaim.canonical_queue_repo(pr_repo),
            "pr": str(pr_num).lstrip("#"),
            "pass_sha": sha,
            "url": url,
            "nick": nick,
            "status": "conflict",
            "conflict_reason": conflict,
            "conflict_fix": fix,
        }
    return enqueue(
        home,
        repo=pr_repo,
        pr=pr_num,
        pass_sha=sha,
        url=url,
        nick=nick,
        hold_reason=hold,
    )
