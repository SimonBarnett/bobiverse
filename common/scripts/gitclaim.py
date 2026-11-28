#!/usr/bin/env python3
"""GIT job queue owned by the digest webhook. No model calls.

POST /bob/v1/git appends claimable work. GET /bob/v1/report lists
queue.unaccepted and queue.accepted. (claim_top is local to Jeeves; not a network op)
pops the oldest unaccepted row and stamps it accepted in one step.

Jeeves does that POST when a shop worker sends !BORED, then announces
``{repo} {task} {id}``. !ACCEPT does not claim. FILE v1 ACCEPT is unrelated.

On-disk queue.json is the listener's crash mirror of that webhook list.
It is not a second source of truth.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import contextlib
import copy
import threading
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import bobreport
import repo_alias

# FR #628: the per-seat "wait" NAK after DONE/GIVEUP is off by default (0 = never NAK a seat that
# has work offerable). Set BOB_BORED_IDLE_S to restore a gate. Seat busy/cooldown rules still apply.
try:
    IDLE_S = max(0.0, float(os.environ.get("BOB_BORED_IDLE_S", "0")))
except ValueError:
    IDLE_S = 0.0
# FR #628: under repo-level focus a UAT row only counts as real work for this long after its merge.
UAT_MAX_AGE_S = 48 * 3600.0
# t856u: an FR a seat already DONE (its PR waits for MRB/merge) is not re-offered for this long.
FR_DONE_HOLD_S = 24 * 3600.0
# FR #1323: DONE MRB (PASS/FAIL) must not be re-offered after done[] rotates or resync races.
MRB_DONE_HOLD_S = 7 * 24 * 3600.0
QUEUE_NAME = "queue.json"
LEGACY_UNACCEPTED = "git-unaccepted.json"
LEGACY_ACCEPTED = "git-accepted.jsonl"
ACTIVITY_NAME = "git-worker-activity.json"
LAST_BORED_NAME = "last-bored.json"
LOCK_NAME = "git-claim.lock"
PENDING_NAME = "git-claim-pending.jsonl"
ACCEPTED_CAP = 200
# FR #1811: lock wait was 5s and dropped webhook rows under contention; default 30s (env override).
try:
    LOCK_WAIT_S = max(1.0, float(os.environ.get("BOB_GITCLAIM_LOCK_S", "30")))
except ValueError:
    LOCK_WAIT_S = 30.0
# FR #1811: keep done[] smaller so queue.json rewrite stays cheap under lock.
DONE_CAP = 100
WRITE_REPLACE_RETRIES = 8

# Task vocabulary. The GIT allowlist below is unchanged: only PR and MRB
# are produced from GitHub events. BUILD, FIX, and UAT are valid kinds if a
# row is already on the queue; this map does not emit them.
TASK_KINDS = frozenset({"FR", "PR", "BUILD", "MRB", "FIX", "UAT"})
# Issues are FR (not PR). PR open/ready -> MRB. Legacy PR rows still valid.
CLAIM_ACTIONS: dict[tuple[str, str], str] = {
    ("issues", "opened"): "FR",
    ("issues", "reopened"): "FR",
    ("pull_request", "opened"): "MRB",
    ("pull_request", "ready_for_review"): "MRB",
}
# t826u: `Closes #N` and the full `Closes owner/repo#N` form (what the worker FR skill mandates in every FR PR body).
# FR #6460: do NOT treat `Refs` as a closer. Refs is citation-only (docs/mrb pins, parents,
# follow-ups). Including refs? here dequeued open FRs when a docs/mrb pin merged (class of #6451 / #6452).
CLOSES_RE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?#(?P<num>\d+)\b"
)

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
# FR #4857: synthetic main-side FIX id `#main` / `#main-red` (shared-suite main red).
ID_RE = re.compile(r"^#(?:\d+|main(?:-red)?)$", re.IGNORECASE)
# FR #785: archived / superseded repos must not be offered or enqueued.
# Keys are lower-case owner/name; values are the live successor for resync discovery.
# Keep in sync with docs/ARCHIVED_REPOS.md (all five archived 2026-10-03).
ARCHIVED_REPO_SUCCESSORS: dict[str, str] = {
    "simonbarnett/gh-jeeves": "SimonBarnett/bobiverse",
    "simonbarnett/agentic_build": "SimonBarnett/bobiverse",
    "simonbarnett/agentic_irc": "SimonBarnett/bobiverse",
    "simonbarnett/agentmonitor": "SimonBarnett/bobiverse",
    "simonbarnett/bob-design-uat": "SimonBarnett/bobiverse",
}
# FR #254: DONE FR URL -> real PR repo/id (cross-repo implement PRs).
PULL_URL_RE = re.compile(
    r"https?://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(?P<num>\d+)",
    re.I,
)
# FR #595 / #247: detect issues-shaped URLs so MRB never treats them as pull targets.
ISSUE_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/(\d+)",
    re.I,
)

NAK_BORED_WAIT = "NAK !BORED wait"
NAK_BORED_BUSY = "NAK !BORED busy"
NO_JOBS = "no jobs"


def format_bored_busy_nak(nick: str, open_job: str = "") -> str:
    """FR #4415: busy NAK names the seat and held/offered job (operators + seat logs).

    Always keeps the ``NAK !BORED busy`` token so worker NAK parsers still match.
    """
    why = str(open_job or "").strip()
    me = (canonical_worker_nick(nick) or nick or "").strip()
    if not why:
        return NAK_BORED_BUSY
    if me:
        return f"{me}: NAK !BORED busy ({why})"
    return f"{NAK_BORED_BUSY} ({why})"
# FR #208 (updated Simon 2026-09-25): one line per job, no flood.
LIST_RATE_S = 30.0
LIST_MAX_LINES = 10  # job lines; + optional 1 summary + 1 more-hint <= ~12 total
LIST_LINE_MAX = 400  # bytes budget; only title is truncated
_LIST_LAST: dict[str, float] = {}

# FR #180: after GIVEUP/NACK, do not re-offer immediately; repeated giveups need a human.
GIVEUP_COOLDOWN_S = 600.0
# FR #8465: NACK busy is a seat-local pause, not a fleet cooldown.
BUSY_NACK_BACKOFF_S = 60.0
GIVEUP_NEEDS_HUMAN_COUNT = 2
SAFE_TO_CLOSE_RE = re.compile(r"(?i)\bsafe\s+to\s+close\b")
HARVEST_TITLE_RE = re.compile(r"(?i)^(harvest|skill)\b")
# FR #2650: intake harvest receipt PRs never become MRB via webhook.
# FR #7118: !assign / !resync still enqueue open non-draft receipts as MRB.
_INTAKE_HARVEST_FOOTER_RE = re.compile(r"(?i)Invoke-BobiverseHarvest|Session summary:")
# FR #5685: Report-*IntakeIssue / GhCliFiler footers without a Lesson body are stubs.
_VIA_INTAKE_ID_FOOTER_RE = re.compile(r"(?i)_via-intake\b")
# FR #6356: require a real Lesson section. Bare LESSON_PR_MRB_INSTRUCTION
# ("MRB (light triage): ...") is prepended to every skill *draft* receipt and must
# not make docs/intake-harvest-only tips offerable as MRB.
# FR #8642: the standard lesson tip body uses a ``Lessons:`` list, not only ``Lesson``.
_INTAKE_SKILL_LESSON_BODY_RE = re.compile(
    r"(?im)^(?:##\s*)?Lessons?\b"
)
_INTAKE_HARVEST_PATH_RE = re.compile(r"(?i)^docs/intake-harvest/")
_QUEUE_ME_STUB_RE = re.compile(r"(?im)^\s*queue\s+me\b")
_HARVEST_RECEIPT_STATUS_RE = re.compile(
    r"(?i)\b(?:GIVEUP|SKIP|self-MRB|twin|DONE|PASS|FAIL)\b|\bduplicate of\b"
)
# FR #628 / FR #2670: chair-spam records (re-offer / drain loops) are never real FR work.
# Bare ``CRITICAL:`` without via-intake / feature-request is still spam (seat loop filings).
# Via-intake / feature-request ``CRITICAL:`` product filings are offerable (deadlock fix #2670).
CRITICAL_SPAM_PREFIX_RE = re.compile(r"(?i)^CRITICAL:")
CRITICAL_SPAM_SHAPE_RE = re.compile(
    r"(?i)\bdrain FR-unaccepted\b|\b\d+(st|nd|rd|th)\+? re-offer\b"
)
# Back-compat for tests/importers that still match the combined name.
CRITICAL_SPAM_TITLE_RE = re.compile(
    r"(?i)^CRITICAL:|\bdrain FR-unaccepted\b|\b\d+(st|nd|rd|th)\+? re-offer\b"
)
# FR #133 / bobiverse#258: evergreen MRB-home boards are not FR jobs.
EVERGREEN_MRB_HOME_TITLE_RE = re.compile(
    r"(?i)\bMRB\s+home\b|\bHostile\s+MRB\s+home\b|\bMRB:\s+\S+.*\bhandoff\b",
)
# FR #2562 / #2677 / #2687: MRB FAIL:/PASS: (or dash) verdict board titles are never FR jobs.
# FR #3299: MOVED owner/repo#N boards are also verdicts (done, not mrb-fail / not re-offered as FR).
# FR #3317: CLOSED not-useful (light harvest triage) is also a done verdict.
MRB_VERDICT_TITLE_RE = re.compile(r"(?i)^MRB\s+(FAIL|PASS|MOVED|CLOSED)\s*[-:]")
# FR #3658 / #3317: intake hold issues titled ``harvest: hold for <owner/repo> - …``
# must never be offered as FR even when the ``owner-missing`` label failed to apply
# (gh_filer retries create without labels when a label is missing on the repo).
# Carve-out from FR #1682 (plain ``harvest:`` promote titles stay offerable).
HARVEST_OWNER_MISSING_HOLD_TITLE_RE = re.compile(
    r"(?i)^harvest:\s*hold\s+for\b"
)
# bobiverse#224 / #765 / #781: FAIL-fix PRs (fix(mrb-N) / mrb-N-fix) are not MRB/UAT targets.
_MRB_FIX_TITLE_RE = re.compile(
    r"(?i)(?:^|\b)(?:fix\s*\(\s*mrb[-_]?(\d+)|mrb[-_]?(\d+)[-_]fix\b)"
)
SKIP_FR_LABELS = frozenset(
    {
        # FR #1682 / #1684 / operator 2026-10-04: skill is offerable (promote PR /
        # consolidate-by-book). Kept out of this set so intake harvests are handed out.
        # Still excluded from repo-UAT blocking via issue_blocks_repo_uat.
        "umbrella",
        "parent-fr",
        # FR #9304: fr-digest epics are go-gate release switches (ACK then GIVEUP),
        # never implement FRs. Offer children (e.g. BOB-G1) instead.
        "fr-digest",
        "mrb-home",
        "mrb_home",
        "evergreen",
        "evergreen-mrb",
        # FR #595: verdict / board labels are not implementable FRs.
        # FR #2562 / #2677: reverse #2464 - mrb-fail / mrb_fail are verdict boards,
        # never offerable FRs (remediation belongs on child product FRs).
        "mrb",
        "mrb-pass",
        "mrb-fail",
        "mrb_pass",
        "mrb_fail",
        # FR #628: held for a human / ionos / release gate.
        "needs-human",
        # needs-mrb1 must NOT be a SKIP_FR label (#1080/#1122/#1174 / PR #1236): that
        # emptied bobiverse offers under focus.strict and dropped rows on resync.
        # Operator 2026-10-04: needs-mrb1 is a hallucination - do not offer-block on it
        # (row_awaits_mrb1 always False). Intake no longer stamps the label.
        "blocked",
        "release-gate",
        # FR #3317: harvest tip held until the intended product repo exists.
        "owner-missing",
    }
)

# FR #9304: line-anchored Kind: fr-digest (label may be missing on a stale queue row).
FR_DIGEST_KIND_BODY_RE = re.compile(
    r"(?im)^\s*(?:\*\*)?Kind\s*:\s*fr-digest(?:\*\*)?\s*$"
)

# FR #9411 / #9402: ops / MONITORING rebuild-install trackers are gate records,
# not shop FR work. Match body cues from walrus/jeeves install trackers (class
# of #9376); do not offer even when hold was cleared for MONITORING.
OPS_MONITOR_TRACKER_BODY_RE = re.compile(
    r"(?is)(?:"
    r"Instructions\s+for\s+Jeeves\s+MONITORING\s+agent"
    r"|GateIssues\s*\("
    r"|Do\s+\*?\*?not\*?\*?\s+`?Closes`?\s+this\s+issue[^\n]{0,80}"
    r"(?:walrus\s+rebuild|rebuild/install\s+tracker|GateIssues)"
    r"|Ops\s+install\s+NOT\s+done"
    r")"
)

# FR #9827: TipForm-restore / online_zero_workers escalate receipts (ops TipForm
# Agents only; not shop FR). Title shapes from #9824 / #9378 / #9103 / #9310.
# Never match product FRs that merely name the detector (#9462).
TIPFORM_RESTORE_ESCALATE_TITLE_RE = re.compile(
    r"(?i)(?:"
    r"\(TipForm\s+restore\)"
    r"|\bonline\s+workers\s*=\s*\[\s*\]\s+while\s+offerable"
    r"|\bonline\s+with\s+zero\s+workers?(?:\s+seats?)?\b"
    r"|\bidle\s+seats?\b.{0,60}\bofferable\s*>\s*0\b.{0,60}\bTipForm-only"
    r")"
)
TIPFORM_RESTORE_ESCALATE_BODY_RE = re.compile(
    r"(?i)(?:"
    r"TipForm-only\s+seat\s+start"
    r"|TipForm-only\s+start;\s*report-only"
    r"|monitor will not Start-BobWorker"
    r"|Operator:\s*TipForm\s+(?:Agents|->)"
    r"|fingerprint\s+stall:online-zero-workers:"
    r")"
)


# Labels safe to detect in free text (title/line only when GitHub labels empty).
# Bare ``mrb`` is labels-only - otherwise titles like "harden MRB/FR routing" (#595)
# would false-positive. ``owner-missing`` is also labels-only (FR #3661 / class of
# #987): remediation PRs that *mention* the hold-label name must stay offerable as
# MRB; real holds are gated by HARVEST_OWNER_MISSING_HOLD_TITLE_RE + the label itself.
# FR #9424: never match ``fr-digest`` via title text - only real labels +
# line-anchored ``Kind: fr-digest`` (product FR/MRB titles often name the feature).
SKIP_FR_LABELS_IN_TEXT = frozenset(
    lab
    for lab in SKIP_FR_LABELS
    if lab
    not in {
        "mrb",
        "needs-human",
        "blocked",
        "release-gate",
        "owner-missing",
        "fr-digest",  # FR #9424: title feature names must not label_text-skip
    }
)

# FR #3928 / #9082: PR merge/offer holds. ``hold`` / ``on-hold`` are issues-only
# (never stamp them on pull requests). PR gate uses do-not-merge / wip labels,
# owner HOLD body stamps, and linked-issue hold (fr_hold_reason) instead.
HOLD_MRB_LABELS = frozenset(
    {
        "do-not-merge",
        "wip",
    }
)
# FR #9082: forbidden on pull_request targets (intake must strip; monitor alarms).
ISSUES_ONLY_HOLD_LABELS = frozenset({"hold", "on-hold"})
# Title-only free hold cues (short titles). Not applied to PR bodies - lesson
# prose such as "do not merge the thinner duplicate" must not count as a hold
# (FR #4545; class of a-search#3627). Body uses line-anchored stamps below.
# FR #9395: bare mid-title "on hold" (e.g. "Create fr-digest on hold before…")
# is product prose, not a gate. Title "on hold" only when leading or "on hold:".
PR_HOLD_TITLE_RE = re.compile(
    r"(?i)(?:^\s*on\s+hold\b|\bon\s+hold\s*:|\bmust\s+not\s+merge\b|\bdo\s+not\s+merge\b|"
    r"\bhold(?:ing)?\s+(?:this\s+)?(?:pr|pull(?:\s+request)?)\b)"
)
# Owner body hold stamp (class of a-search#1334 "On hold (Simon …): must not merge…").
# Line-anchored like FR_HOLD_BODY_RE so free prose does not false-positive.
PR_HOLD_BODY_RE = re.compile(
    r"(?im)^\s*(?:\*\*)?(?:On\s+hold|HOLD)\b(?:\s*\([^)]*\))?(?:\*\*)?\s*:"
)
# Back-compat alias for importers/tests that still name PR_HOLD_TEXT_RE.
PR_HOLD_TEXT_RE = PR_HOLD_TITLE_RE

# FR #4009: issue hold labels - never enqueue/offer FR while present.
# Kept out of SKIP_FR_LABELS so held product FRs still block repo UAT.
HOLD_FR_LABELS = frozenset({"hold", "on-hold"})
# Owner HOLD body stamp (class of bobiverse#3991 "**HOLD (date, Simon):** Do not start…").
# Line-anchored so prose "must hold the previous version" does not false-positive.
FR_HOLD_BODY_RE = re.compile(
    r"(?im)^\s*(?:\*\*)?HOLD\b(?:\s*\([^)]*\))?(?:\*\*)?\s*:"
)

# FR #8741: park-only anti-omnibus FRs must not be offered until a human dispatch stamp.
# Park cues (any one): explicit park-only / do-not-bob-job until human dispatch.
FR_PARK_ONLY_RE = re.compile(
    r"(?is)(?:\bpark-only\b|park:\s*park-only|"
    r"do\s+not\s+bob-job\s+until\s+human\s+dispatch|"
    r"park-only\s+until\s+human\s+dispatch)"
)
# Dispatch clear: body ``(dispatched)`` (BOB pack stamp) or label dispatched / human-dispatch.
FR_DISPATCH_BODY_RE = re.compile(r"(?i)\(\s*dispatched\s*\)")
FR_DISPATCH_LABELS = frozenset({"dispatched", "human-dispatch", "bob-dispatched"})


def strip_issues_only_hold_labels(
    labels: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """FR #9082: drop ``hold`` / ``on-hold`` from a label list destined for a PR."""
    out: list[str] = []
    for x in labels or []:
        s = str(x).strip()
        if not s:
            continue
        if s.lower() in ISSUES_ONLY_HOLD_LABELS:
            continue
        out.append(s)
    return out


def pr_forbidden_hold_labels(
    labels: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """FR #9082: which issues-only hold labels are present on a PR (sorted)."""
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    return sorted(labs & ISSUES_ONLY_HOLD_LABELS)


def pr_hold_reason(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> str | None:
    """FR #3928 / #4545 / #9082: why an open PR must not be offered/merged as MRB.

    ``do-not-merge`` / ``wip`` labels still count. ``hold`` / ``on-hold`` on a PR
    do **not** (issues-only; see ``pr_forbidden_hold_labels`` / monitor). Body
    hold text only matches an owner stamp line (``On hold:`` / ``HOLD:``).
    Title still scans short hold cues (leading ``On hold`` / ``on hold:``,
    do-not-merge); mid-title prose ``on hold`` (VIS-G1) does not count (FR #9395).
    """
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    hit = sorted(labs & HOLD_MRB_LABELS)
    if hit:
        return f"hold label: {hit[0]}"
    title_s = str(title or "")
    m_title = PR_HOLD_TITLE_RE.search(title_s)
    if m_title:
        return f"hold text: {m_title.group(0).strip()}"
    m_body = PR_HOLD_BODY_RE.search(str(body or ""))
    if m_body:
        return f"hold text: {m_body.group(0).strip()}"
    return None


def ops_monitor_tracker_reason(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> str | None:
    """FR #9402: why an issue is an ops/MONITORING gate tracker (None = ordinary FR).

    These trackers must not be ``feature-request`` shop work. Chair skips enqueue/offer;
    operators keep them as hold/ops records (see #9400 Closes rule).
    """
    blob = f"{title or ''}\n{body or ''}"
    if OPS_MONITOR_TRACKER_BODY_RE.search(blob):
        return "ops_monitor_tracker"
    return None


def fr_hold_reason(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> str | None:
    """FR #4009: why an open issue must not be enqueued/offered as FR, else None.

    Label ``hold`` / ``on-hold``, or an owner HOLD body stamp. Does not use
    SKIP_FR_LABELS (held product work still blocks repo UAT until cleared/closed).
    """
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    hit = sorted(labs & HOLD_FR_LABELS)
    if hit:
        return f"hold label: {hit[0]}"
    blob = f"{title or ''}\n{body or ''}"
    m = FR_HOLD_BODY_RE.search(blob)
    if m:
        return f"hold text: {m.group(0).strip()}"
    return None


def row_fr_hold_reason(row: dict) -> str | None:
    """FR #4009: hold gate for a queue FR row; None for non-FR or clear rows."""
    if _canon_task(row) != "FR":
        return None
    labels = row.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    title = str(row.get("title") or "").strip() or str(row.get("line") or "").strip()
    return fr_hold_reason(
        title=title,
        body=str(row.get("body") or ""),
        labels=tuple(str(x) for x in labels),
    )


def fr_park_only_reason(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> str | None:
    """FR #8741: why a park-only anti-omnibus FR must not be offered, else None.

    Park cues in title/body block offer until a human dispatch stamp clears them:
    body ``(dispatched)`` or label ``dispatched`` / ``human-dispatch`` / ``bob-dispatched``.
    """
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    blob = f"{title or ''}\n{body or ''}"
    if labs & FR_DISPATCH_LABELS or FR_DISPATCH_BODY_RE.search(blob):
        return None
    m = FR_PARK_ONLY_RE.search(blob)
    if m:
        return f"park-only: {m.group(0).strip()[:80]}"
    return None


def row_fr_park_only_reason(row: dict) -> str | None:
    """FR #8741: park-only gate for a queue FR row; None for non-FR or clear/dispatched."""
    if _canon_task(row) != "FR":
        return None
    labels = row.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    title = str(row.get("title") or "").strip() or str(row.get("line") or "").strip()
    return fr_park_only_reason(
        title=title,
        body=str(row.get("body") or ""),
        labels=tuple(str(x) for x in labels),
    )


def row_fr_skip_offer_reason(row: dict) -> str | None:
    """FR #4009 + #8741: hold or park-only reason to skip offering an FR row."""
    return row_fr_hold_reason(row) or row_fr_park_only_reason(row)


# BOB-G3 / FR #9108: Digest flag - issues only (never title heuristics alone).
DIGEST_ISSUE_LABELS = frozenset({"digest", "fr-digest"})
# Forbidden on pull_request targets (intake/plan must strip; distinct from hold).
ISSUES_ONLY_DIGEST_LABELS = DIGEST_ISSUE_LABELS
# Line-anchored Kind: fr-digest|digest (plain or bold); prose must not match.
DIGEST_KIND_BODY_RE = re.compile(
    r"(?im)^[^\S\n]*(?:\*{0,2}|`{0,2})Kind(?:\*{0,2}|`{0,2})"
    r"[^\S\n]*:"
    r"(?:\*{0,2}|`{0,2})?"
    r"[^\S\n]*(fr-digest|digest)\b"
)


def strip_issues_only_digest_labels(
    labels: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """BOB-G3 / FR #9108: drop ``digest`` / ``fr-digest`` from a PR label list."""
    out: list[str] = []
    for x in labels or []:
        s = str(x).strip()
        if not s:
            continue
        if s.lower() in ISSUES_ONLY_DIGEST_LABELS:
            continue
        out.append(s)
    return out


def pr_forbidden_digest_labels(
    labels: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """BOB-G3: which issues-only digest labels are present on a PR (sorted)."""
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    return sorted(labs & ISSUES_ONLY_DIGEST_LABELS)


def _row_is_pr_shaped_issue(row: dict) -> bool:
    """True when the row is structurally a pull (event/URL), not an issues FR."""
    if not isinstance(row, dict):
        return True
    event = str(row.get("event") or "").strip().lower()
    if event == "pull_request":
        return True
    raw = str(row.get("url") or "").strip()
    if PULL_URL_RE.search(raw):
        return True
    return False


def digest_issue_reason(row: dict) -> str | None:
    """BOB-G3 / FR #9108: why a queue row is a Digest gate record, else None.

    Issues-only FR rows. Matches label ``digest`` / ``fr-digest`` (string, dict,
    or comma-separated) or a line-anchored ``Kind: digest|fr-digest`` body stamp.
    Never uses the title. MRB / PR-shaped rows are never digests.
    """
    if not isinstance(row, dict) or _canon_task(row) != "FR":
        return None
    if _row_is_pr_shaped_issue(row):
        return None
    labs = _depend_row_label_names(row)
    hit = sorted(labs & DIGEST_ISSUE_LABELS)
    if hit:
        return f"digest label: {hit[0]}"
    body = str(row.get("body") or "")
    m = DIGEST_KIND_BODY_RE.search(body)
    if m:
        return f"digest kind: {m.group(1).strip().lower()}"
    return None


def row_is_digest_issue(row: dict) -> bool:
    """True when ``digest_issue_reason`` matches (BOB-G3)."""
    return digest_issue_reason(row) is not None


def clear_sticky_offer_fields(row: dict) -> None:
    """Drop offered_to / offered_ts / offered_channel / offered_via on one row."""
    if not isinstance(row, dict):
        return
    row.pop("offered_to", None)
    row.pop("offered_ts", None)
    row.pop("offered_channel", None)
    row.pop("offered_via", None)


def clear_held_fr_sticky_offers(doc: dict) -> list[str]:
    """FR #9402 / #9406: clear sticky offered_to on hold-gated FR rows and drop them.

    Hold-labeled ops umbrellas must not pin a seat as ``busy (offered FR ...)`` after
    the issue gains ``hold`` (or an owner HOLD stamp). Digest gate rows stay queued
    (BOB-G3) but still lose sticky offered_* so they cannot block assigns.
    Returns human drop labels for logging.
    """
    dropped: list[str] = []
    if not isinstance(doc, dict):
        return dropped
    keep: list[dict] = []
    for row in list(doc.get("unaccepted") or []):
        if not isinstance(row, dict):
            continue
        if _canon_task(row) != "FR":
            keep.append(row)
            continue
        why = row_fr_hold_reason(row)
        if not why:
            keep.append(row)
            continue
        had_offer = bool(str(row.get("offered_to") or "").strip())
        clear_sticky_offer_fields(row)
        # BOB-G3: digest gate records stay queued even when held.
        if digest_issue_reason(row):
            keep.append(row)
            if had_offer:
                dropped.append(f"{_row_drop_label(row)} fr_hold_clear_offer")
            continue
        dropped.append(f"{_row_drop_label(row)} fr_hold")
    doc["unaccepted"] = keep
    return dropped


def clear_closed_fr_sticky_offers(
    doc: dict, home: Path | None = None, *, log=None
) -> list[str]:
    """FR #9835: clear sticky offered_to / seat-holds on stamped ``state=closed`` FRs.

    Phantom CLOSED (or webhook-stamped) FR rows must not pin a seat as
    ``busy (offered FR ...)`` / ``busy (held ...)`` within the offer-timeout window
    and must not refuse ``!assign`` tip MRBs. Drops the unaccepted row (same as
    ``_purge_closed_fr_unaccepted`` stamped path) and clears matching seat-holds.
    Returns human drop labels for one-shot announce logging.
    """
    dropped: list[str] = []
    if not isinstance(doc, dict):
        return dropped
    keep: list[dict] = []
    for row in list(doc.get("unaccepted") or []):
        if not isinstance(row, dict):
            continue
        if _canon_task(row) != "FR":
            keep.append(row)
            continue
        if str(row.get("state") or "").strip().lower() != "closed":
            keep.append(row)
            continue
        had_offer = bool(str(row.get("offered_to") or "").strip())
        repo = str(row.get("repo") or "").strip()
        ident = str(row.get("id") or "").strip()
        clear_sticky_offer_fields(row)
        if home is not None and repo and ident:
            with contextlib.suppress(Exception):
                _clear_job_seat_holds_unlocked(home, repo, "FR", ident)
                _clear_job_seat_holds_unlocked(home, repo, "PR", ident)
                _clear_job_seat_holds_unlocked(home, repo, "UAT", ident)
        label = f"{_row_drop_label(row)} closed_fr_clear_sticky"
        dropped.append(label)
        _log_queue_purge(
            f"INFO git-claim purge closed-fr-sticky {repo}{ident} "
            f"had_offer={int(had_offer)}",
            log=log,
        )
        # Drop the unaccepted CLOSED phantom so it cannot re-pin.
    doc["unaccepted"] = keep
    return dropped

def clear_offers_for_held_digest_children(
    home: Path | None,
    doc: dict,
    digest_repo: str,
    digest_id: str,
) -> list[str]:
    """FR #9832: when an fr-digest gains ``hold``, clear Depends-on child offers now.

    Clears sticky ``offered_*`` on unaccepted children, soft-releases accepted
    children back to unaccepted, and drops seat holds for those jobs. Returns
    human labels for logging / fleet notice.
    """
    cleared: list[str] = []
    if not isinstance(doc, dict):
        return cleared
    want_repo = _repo_key(digest_repo)
    raw_id = str(digest_id or "").strip().lstrip("#")
    try:
        want_num = int(raw_id) if raw_id else 0
    except ValueError:
        return cleared
    if not want_repo or want_num <= 0:
        return cleared
    want = (want_repo, want_num)

    def _depends_on_digest(row: dict) -> bool:
        return want in _row_depends_on_issue_refs(row)

    for row in list(doc.get("unaccepted") or []):
        if not isinstance(row, dict) or _canon_task(row) != "FR":
            continue
        if not _depends_on_digest(row):
            continue
        had = bool(str(row.get("offered_to") or "").strip())
        clear_sticky_offer_fields(row)
        if home is not None:
            with contextlib.suppress(Exception):
                _clear_job_seat_holds_unlocked(
                    home,
                    str(row.get("repo") or ""),
                    "FR",
                    str(row.get("id") or ""),
                )
        if had:
            cleared.append(f"{_row_drop_label(row)} digest_hold_clear_offer")

    kept_acc: list[dict] = []
    released_rows: list[dict] = []
    for row in list(doc.get("accepted") or []):
        if not isinstance(row, dict):
            continue
        if _canon_task(row) != "FR" or not _depends_on_digest(row):
            kept_acc.append(row)
            continue
        if home is not None:
            with contextlib.suppress(Exception):
                _clear_job_seat_holds_unlocked(
                    home,
                    str(row.get("repo") or ""),
                    "FR",
                    str(row.get("id") or ""),
                )
        retry = _row_to_unaccepted_retry(row)
        clear_sticky_offer_fields(retry)
        released_rows.append(retry)
        cleared.append(f"{_row_drop_label(row)} digest_hold_release_accepted")
    if released_rows:
        doc["accepted"] = kept_acc
        doc["unaccepted"] = list(doc.get("unaccepted") or []) + released_rows
    return cleared

# FR #9848: injectable GitHub label remover for tests (callable(repo, num, label) -> bool).
_FR9848_REMOVE_LABEL = None


def _default_remove_github_issue_label(repo: str, issue_num: int, label: str) -> bool:
    """Best-effort ``gh api -X DELETE repos/.../issues/N/labels/LABEL`` (FR #9848)."""
    import shutil
    import subprocess
    import urllib.parse

    gh = shutil.which("gh")
    if not gh:
        return False
    lab = urllib.parse.quote(str(label or "").strip(), safe="")
    if not lab or int(issue_num) <= 0:
        return False
    try:
        r = subprocess.run(
            [
                gh,
                "api",
                "-X",
                "DELETE",
                f"repos/{repo}/issues/{int(issue_num)}/labels/{lab}",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def strip_hold_from_digest_children(
    home: Path | None,
    doc: dict,
    digest_repo: str,
    digest_id: str,
    *,
    remove_github_label=None,
) -> list[str]:
    """FR #9848: parent digest unhold strips ``hold`` from ordinary Depends-on children.

    Nested digest children keep hold (FR #9860 no auto-unhold). Updates queue labels
    in place and best-effort removes the GitHub label so the next resync stays clear.
    """
    actions: list[str] = []
    if not isinstance(doc, dict):
        return actions
    want_repo = _repo_key(digest_repo)
    raw_id = str(digest_id or "").strip().lstrip("#")
    try:
        want_num = int(raw_id) if raw_id else 0
    except ValueError:
        return actions
    if not want_repo or want_num <= 0:
        return actions
    want = (want_repo, want_num)

    try:
        import fr_digest_gate as _fdg
    except ImportError:
        _fdg = None  # type: ignore[assignment]

    remover = remove_github_label
    if remover is None:
        remover = _FR9848_REMOVE_LABEL
    if remover is None:
        remover = _default_remove_github_issue_label

    def _depends_on_digest(row: dict) -> bool:
        return want in _row_depends_on_issue_refs(row)

    for bucket in ("unaccepted", "accepted"):
        for row in list(doc.get(bucket) or []):
            if not isinstance(row, dict) or _canon_task(row) != "FR":
                continue
            if not _depends_on_digest(row):
                continue
            if _fdg is not None:
                if not _fdg.should_strip_child_hold_on_parent_unhold(row):
                    continue
                new_labs = _fdg.strip_hold_labels(row.get("labels") or [])
            else:
                labs = {
                    str(x).strip().lower()
                    for x in (row.get("labels") or [])
                    if str(x).strip()
                }
                if labs & DIGEST_ISSUE_LABELS:
                    continue
                if "hold" not in labs and "on-hold" not in labs:
                    continue
                new_labs = [
                    str(x)
                    for x in (row.get("labels") or [])
                    if str(x).strip().lower() not in ISSUES_ONLY_HOLD_LABELS
                ]
            old_labs = [str(x) for x in (row.get("labels") or [])]
            old_hold = [
                x
                for x in old_labs
                if str(x).strip().lower() in ISSUES_ONLY_HOLD_LABELS
            ]
            if not old_hold:
                continue
            row["labels"] = new_labs
            child_repo = str(row.get("repo") or digest_repo)
            child_raw = str(row.get("id") or "").strip().lstrip("#")
            try:
                child_num = int(child_raw)
            except ValueError:
                child_num = 0
            for lab in old_hold:
                ok = False
                if callable(remover) and child_num > 0:
                    try:
                        ok = bool(remover(child_repo, child_num, str(lab).strip()))
                    except Exception:
                        ok = False
                actions.append(
                    f"{_row_drop_label(row)} digest_unhold_strip_{lab}"
                    f"{'' if ok else '_queued'}"
                )
            # Ensure hold no longer gates this row locally.
            if home is not None:
                with contextlib.suppress(Exception):
                    _clear_job_seat_holds_unlocked(
                        home,
                        child_repo,
                        "FR",
                        str(row.get("id") or ""),
                    )
    return actions


# FR #8754: skip FR offer while vision/index Depends-on backlog IDs still have open issues.
_DEPENDS_ON_LINE_RE = re.compile(r"(?im)^\s*\*{0,2}Depends-on\*{0,2}\s*:\s*(.+)$")
_BOB_BACKLOG_ID_RE = re.compile(r"\bBOB-(\d+)\b", re.I)
_DEPENDS_ISSUE_REF_RE = re.compile(r"(?:#|/issues/)(\d+)\b")
# FR #9220 / #8807: owner/repo#N (finditer + full-token match).
_QUALIFIED_DEPENDS_ISSUE_RE = re.compile(
    r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b"
)
_VISION_PACK_FILE_RE = re.compile(r"(feature-request-[\w.-]+\.md)", re.I)
_BOB_TITLE_ID_RE = re.compile(r"^\s*BOB-(\d+)\b", re.I)


def linked_issue_hold_reason(
    repo: str,
    *,
    body: str = "",
    refs: tuple[str, ...] | list[str] = (),
    issue_lookup=None,
) -> str | None:
    """FR #9080 / #9243: hold on a Closes-linked issue blocks dirty-FIX / MRB requeue.

    Operator policy (2026-11-22): ``hold`` is issues-only. Dirty-FIX and head-move
    requeue (``ensure_mrb_requeued_after_head_move`` when ``issue_lookup`` is
    passed) must still respect the linked FR/issue hold even when the PR has no
    ``hold`` label. ``issue_lookup=None`` returns None (no network).
    """
    if issue_lookup is None:
        return None
    repo_c = canonical_queue_repo(repo)
    ids: list[str] = []
    seen: set[str] = set()
    for raw in refs or ():
        s = str(raw or "").strip()
        if not s:
            continue
        if s.isdigit():
            s = f"#{s}"
        if not s.startswith("#"):
            continue
        if s not in seen:
            seen.add(s)
            ids.append(s)
    for ident in extract_closes_issue_ids(str(body or ""), repo=repo_c):
        if ident not in seen:
            seen.add(ident)
            ids.append(ident)
    for ident in ids:
        try:
            issue = issue_lookup(repo_c, ident)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(issue, dict):
            continue
        labs = issue.get("labels") or ()
        if isinstance(labs, str):
            labs = [labs]
        names: list[str] = []
        for lab in labs:
            if isinstance(lab, dict):
                name = str(lab.get("name") or "").strip()
            else:
                name = str(lab or "").strip()
            if name:
                names.append(name)
        why = fr_hold_reason(
            title=str(issue.get("title") or ""),
            body=str(issue.get("body") or ""),
            labels=tuple(names),
        )
        if why:
            return f"linked issue {ident} {why}"
    return None



def _bob_docs_root() -> Path | None:
    """Repo ``bob/docs`` next to common/scripts when present (chair install / worktree)."""
    here = Path(__file__).resolve()
    for cand in (here.parents[2] / "bob" / "docs", here.parents[1] / "bob" / "docs"):
        if cand.is_dir():
            return cand
    return None


def parse_depends_on_tokens(text: str) -> list[str]:
    """Normalize Depends-on tokens to ``BOB-N``, ``owner/repo#N``, and ``#N``.

    FR #9220: keep qualified ``owner/repo#N`` (do not also emit bare ``#N`` for the
    same span). Relative ``#N`` stays relative; callers resolve against the FR repo.
    """
    out: list[str] = []
    seen: set[str] = set()
    blob = text or ""
    for m in _BOB_BACKLOG_ID_RE.finditer(blob):
        tok = f"BOB-{int(m.group(1))}"
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    qualified_spans: list[tuple[int, int]] = []
    for m in _QUALIFIED_DEPENDS_ISSUE_RE.finditer(blob):
        tok = f"{m.group(1)}#{int(m.group(2))}"
        qualified_spans.append(m.span())
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    for m in _DEPENDS_ISSUE_REF_RE.finditer(blob):
        if any(s <= m.start() < e for s, e in qualified_spans):
            continue
        tok = f"#{int(m.group(1))}"
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def fr_depends_on_tokens(
    *,
    title: str = "",
    body: str = "",
    docs_root: Path | None = None,
) -> list[str]:
    """FR #8754: Depends-on tokens from issue body/title and linked local vision pack."""
    blob = f"{title or ''}\n{body or ''}"
    tokens: list[str] = []
    seen: set[str] = set()

    def _add(more: list[str]) -> None:
        for t in more:
            if t not in seen:
                seen.add(t)
                tokens.append(t)

    for m in _DEPENDS_ON_LINE_RE.finditer(blob):
        _add(parse_depends_on_tokens(m.group(1)))
    root = docs_root if docs_root is not None else _bob_docs_root()
    if root is not None:
        for m in _VISION_PACK_FILE_RE.finditer(blob):
            path = root / m.group(1)
            if not path.is_file():
                continue
            try:
                pack = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for pm in _DEPENDS_ON_LINE_RE.finditer(pack):
                _add(parse_depends_on_tokens(pm.group(1)))
    return tokens


def _open_fr_bob_and_id_index(
    doc: dict,
) -> tuple[dict[str, list[tuple[str, str]]], set[tuple[str, str]]]:
    """Map ``BOB-N`` to open ``(repo_key, #id)``; set of open ``(repo_key, #id)``.

    FR #9220: index by owner/repo so cross-repo bare ``#N`` collisions do not false-skip.
    BOB-D4 / FR #8808: skip ``state=closed`` rows (same as ``open_fr_issue_keys``) so a
    depend that closed while still ACC/unaccepted no longer blocks offer.
    """
    bobs: dict[str, list[tuple[str, str]]] = {}
    keys: set[tuple[str, str]] = set()
    for bucket in (doc.get("unaccepted") or [], doc.get("accepted") or []):
        for row in bucket:
            if not isinstance(row, dict) or _canon_task(row) != "FR":
                continue
            if str(row.get("state") or "").strip().lower() == "closed":
                continue
            repo = _repo_key(str(row.get("repo") or ""))
            rid = _norm_row_id(str(row.get("id") or ""))
            if not repo or not rid:
                continue
            keys.add((repo, rid))
            title = str(row.get("title") or "").strip()
            tm = _BOB_TITLE_ID_RE.match(title)
            if tm:
                key = f"BOB-{int(tm.group(1))}"
                bobs.setdefault(key, []).append((repo, rid))
    return bobs, keys


# BOB-D3 / FR #8807 + BOB-G1 / FR #8837 (bob_g1_skip_held_digest).
# FR #9455 bob_g1_shared_gate: offer + assign + stuck share depends_gate_reason.
DEPENDS_OPEN_REASON = "depends-open"
DEPENDS_HELD_REASON = "depends-held"


def _depend_row_label_names(row: dict) -> set[str]:
    """Lower-case label names from a queue FR row (BOB-G1 / FR #8837)."""
    names: set[str] = set()
    if not isinstance(row, dict):
        return names
    raw = row.get("labels") or ()
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, (list, tuple)):
        return names
    for item in raw:
        if isinstance(item, str):
            n = item.strip().lower()
        elif isinstance(item, dict):
            n = str(item.get("name") or "").strip().lower()
        else:
            n = ""
        if n:
            names.add(n)
    return names


def _depend_queue_state(doc: dict | None, repo: str, num: int) -> str:
    """Lower-case queue state for a depend, including closed rows. Empty if absent."""
    if not isinstance(doc, dict) or num < 1:
        return ""
    want = (_repo_key(repo), int(num))
    for bucket in (
        doc.get("unaccepted") or [],
        doc.get("accepted") or [],
        doc.get("done") or [],
    ):
        for row in bucket:
            if not isinstance(row, dict):
                continue
            rkey = _repo_key(str(row.get("repo") or ""))
            raw = str(row.get("id") or "").strip().lstrip("#")
            try:
                n = int(raw) if raw else 0
            except ValueError:
                continue
            if (rkey, n) == want:
                return str(row.get("state") or "").strip().lower()
    return ""


def find_open_fr_row(doc: dict | None, repo: str, num: int) -> dict | None:
    """Locate an open FR queue row by ``(repo, number)`` (BOB-G1 digest labels)."""
    if not isinstance(doc, dict) or num < 1:
        return None
    want = (_repo_key(repo), int(num))
    for bucket in (doc.get("unaccepted") or [], doc.get("accepted") or []):
        for row in bucket:
            if not isinstance(row, dict) or _canon_task(row) != "FR":
                continue
            if str(row.get("state") or "").strip().lower() == "closed":
                continue
            rkey = _repo_key(str(row.get("repo") or ""))
            raw = str(row.get("id") or "").strip().lstrip("#")
            try:
                n = int(raw) if raw else 0
            except ValueError:
                continue
            if (rkey, n) == want:
                return row
    return None


def _github_issue_dict_as_fr_row(repo: str, num: int, issue: dict) -> dict:
    """Synthetic FR row from a GitHub issue dict for BOB-G1 digest recognition (FR #9418)."""
    labels = issue.get("labels") or ()
    return {
        "repo": str(repo or "").strip(),
        "task": "FR",
        "id": f"#{int(num)}",
        "state": str(issue.get("state") or "open").strip().lower() or "open",
        "title": str(issue.get("title") or ""),
        "body": str(issue.get("body") or ""),
        "labels": labels,
        "event": "issues",
        "line": f"FR {repo}#{int(num)}",
        "url": str(issue.get("html_url") or f"https://github.com/{repo}/issues/{int(num)}"),
    }


def depends_issue_fetch_checker(fetch_issue=None):
    """Unbudgeted GitHub issue dict fetch for BOB-G1 when digests are not queued (FR #9418).

    Mirrors ``depends_issue_open_checker``: test fakes (no ``.budget``) pass through;
    otherwise default to ``fetch_github_issue_dict`` so !bored budget 0 still resolves
    fr-digest / hold labels for Depends-on refs absent from the local FR queue.
    """
    if fetch_issue is not None and getattr(fetch_issue, "budget", None) is None:
        return fetch_issue
    return lambda repo, num: fetch_github_issue_dict(repo, num)


def _bob_g1_digest_gate_for_pair(
    doc: dict, repo: str, oid: str, *, issue_fetch=None
) -> str | None:
    """BOB-G1 / FR #8837 bob_g1_skip_held_digest (+ BOB-G3 Digest flag).

    Returns ``depends-held`` when the open depend has hold; ``ok-fr-digest`` when
    it is an unheld digest (``digest`` / ``fr-digest`` label or ``Kind:`` stamp;
    caller must not treat OPEN as blocking); None when the row is absent or has
    no digest recognition.

    FR #9418 ``bob_g1_live_digest_absent_queue``: when the digest is not in
    unaccepted/accepted, ``issue_fetch`` (GitHub issue dict) still resolves labels /
    Kind so children are not wrongly blocked as ``depends-open``.

    FR #9858: same held-digest skip for **foreign** ``owner/repo#N`` digests
    (repo B child blocked while repo A digest still has ``hold``).
    """
    raw = str(oid or "").strip().lstrip("#")
    try:
        num = int(raw) if raw else 0
    except ValueError:
        return None
    dep = find_open_fr_row(doc, repo, num)
    if dep is None and issue_fetch is not None:
        try:
            issue = issue_fetch(repo, str(num))
        except Exception:
            issue = None
        if isinstance(issue, dict):
            dep = _github_issue_dict_as_fr_row(repo, num, issue)
    if dep is None:
        return None
    # Closed parents (incl. issue_fetch) never gate children — leftover hold labels
    # on a closed digest must not hide a released child (MRB #9834 / CodeRabbit).
    if str(dep.get("state") or "").strip().lower() == "closed":
        return None
    labs = _depend_row_label_names(dep)
    if "hold" in labs or "on-hold" in labs:
        # Held digest (or any held depend) blocks children.
        return DEPENDS_HELD_REASON
    if row_is_digest_issue(dep):
        return "ok-fr-digest"
    return None


def row_fr_depends_blocked_reason(
    row: dict,
    doc: dict,
    *,
    docs_root: Path | None = None,
    issue_fetch=None,
) -> str | None:
    """FR #8754 / BOB-D7 (FR #8811) / FR #9220 / BOB-G1 (FR #8837): Depends-on gate.

    bob_d7_wire_hold: call this beside every ``fr_hold_reason`` / ``row_fr_hold_reason``
    offer, enqueue, purge, and reconcile site. Distinct from hold / HOLD: stamps.

    FR #9220: relative ``#N`` resolves against the FR's own repo; qualified
    ``owner/repo#N`` looks up that repo only. Does not purge the row - when depends
    leave the queue (or stamp ``state=closed``, BOB-D4 / FR #8808), the FR becomes offerable.

    BOB-G1: hold on depend -> ``depends-held``; unheld digest/fr-digest OK while OPEN.
    FR #9455: pass ``issue_fetch`` so digests absent from the local queue still resolve
    (same as ``row_depends_open_reason`` / ``depends_gate_reason``).
    """
    if _canon_task(row) not in ("FR", "FIX", "MRB"):
        return None
    title = str(row.get("title") or "").strip() or str(row.get("line") or "").strip()
    body = str(row.get("body") or "")
    tokens = fr_depends_on_tokens(title=title, body=body, docs_root=docs_root)
    if not tokens:
        return None
    home_repo = _repo_key(str(row.get("repo") or ""))
    self_id = _norm_row_id(str(row.get("id") or ""))
    self_key = (home_repo, self_id) if home_repo and self_id else None
    bobs, open_keys = _open_fr_bob_and_id_index(doc)
    for tok in tokens:
        if tok.startswith("BOB-"):
            for repo, oid in bobs.get(tok) or []:
                # Vision BOB-* backlog is repo-local for offer gating (FR #9220).
                if home_repo and repo != home_repo:
                    continue
                if self_key is not None and (repo, oid) == self_key:
                    continue
                g1 = _bob_g1_digest_gate_for_pair(
                    doc, repo, oid, issue_fetch=issue_fetch
                )
                if g1 == DEPENDS_HELD_REASON:
                    return f"{DEPENDS_HELD_REASON}: {tok}"
                if g1 == "ok-fr-digest":
                    return f"depends-on open: {tok}"
                if (repo, oid) in open_keys:
                    return (
                        f"depends-on open: {tok} "
                        f"({repo}{oid if oid.startswith('#') else '#' + oid})"
                    )
            continue
        qm = _QUALIFIED_DEPENDS_ISSUE_RE.match(tok)
        if qm:
            pair = (_repo_key(qm.group(1)), _norm_row_id(f"#{int(qm.group(2))}"))
            if self_key is not None and pair == self_key:
                continue
            g1 = _bob_g1_digest_gate_for_pair(
                doc, pair[0], pair[1], issue_fetch=issue_fetch
            )
            if g1 == DEPENDS_HELD_REASON:
                return f"{DEPENDS_HELD_REASON}: {tok}"
            if g1 == "ok-fr-digest":
                return f"depends-on open: {tok}"
            if pair in open_keys:
                return f"depends-on open: {tok}"
            continue
        if tok.startswith("#"):
            if not home_repo:
                continue
            oid = _norm_row_id(tok)
            pair = (home_repo, oid)
            if self_key is not None and pair == self_key:
                continue
            g1 = _bob_g1_digest_gate_for_pair(
                doc, home_repo, oid, issue_fetch=issue_fetch
            )
            if g1 == DEPENDS_HELD_REASON:
                return f"{DEPENDS_HELD_REASON}: {tok}"
            if g1 == "ok-fr-digest":
                return f"depends-on open: {tok}"
            if pair in open_keys:
                return f"depends-on open: {tok}"
    return None


def depends_gate_reason(
    row: dict,
    doc: dict | None = None,
    *,
    open_keys: set[tuple[str, int]] | None = None,
    issue_open=None,
    issue_fetch=None,
    docs_root: Path | None = None,
) -> str | None:
    """FR #9455 ``bob_g1_shared_gate``: one Depends-on reason for offer, assign, stuck.

    FR #9553: also the shared gate for ``!list`` / digest ``offerable_count`` /
    monitor ungated counts (token-free when ``issue_open`` is unset).

    Returns ``depends-held`` / ``depends-open`` / ``depends-unresolved`` / None.
    Prefer this over calling ``row_depends_open_reason`` and
    ``row_fr_depends_blocked_reason`` separately (those two used to disagree when
    digests were absent from the local queue).
    """
    if _canon_task(row) not in ("FR", "FIX", "MRB"):
        return None
    qdoc = doc if isinstance(doc, dict) else {}
    fetch = issue_fetch
    opener = issue_open
    keys = open_keys if open_keys is not None else open_fr_issue_keys(qdoc)
    why = row_depends_open_reason(
        row,
        keys,
        issue_open=opener,
        doc=qdoc,
        issue_fetch=fetch,
    )
    if why:
        return why
    blocked = row_fr_depends_blocked_reason(
        row, qdoc, docs_root=docs_root, issue_fetch=fetch
    )
    if not blocked:
        return None
    if blocked == DEPENDS_HELD_REASON or blocked.startswith(f"{DEPENDS_HELD_REASON}:"):
        return DEPENDS_HELD_REASON
    if blocked == DEPENDS_OPEN_REASON or blocked.startswith("depends-on open"):
        return DEPENDS_OPEN_REASON
    if (
        blocked == DEPENDS_UNRESOLVED_REASON
        or blocked.startswith(f"{DEPENDS_UNRESOLVED_REASON}:")
    ):
        return DEPENDS_UNRESOLVED_REASON
    return DEPENDS_OPEN_REASON


def walk_depends_on_offer_reason(
    row: dict,
    doc: dict | None = None,
    *,
    open_keys: set[tuple[str, int]] | None = None,
    issue_open=None,
    issue_fetch=None,
    docs_root: Path | None = None,
) -> str | None:
    """FR #9857: shared Depends-on walk for !bored / assign / offerable list.

    Alias of `depends_gate_reason` (FR #9455). Resolves relative `#N` against
    the child row repo and qualified `owner/repo#N`. Multi-ref: every hard ref
    must be clear (G1: unheld fr-digest may stay OPEN). Fail-closed when
    `issue_open` raises and a fetch path exists (`depends-unresolved`).
    """
    return depends_gate_reason(
        row,
        doc,
        open_keys=open_keys,
        issue_open=issue_open,
        issue_fetch=issue_fetch,
        docs_root=docs_root,
    )


# BOB-D3 / FR #8807: skip offer when any Depends-on issue ref is OPEN.
# BOB-D5 / FR #8809: fail closed on malformed tokens / lookup Unknown.
# BOB-D1/D2 own the public parse_depends_on / resolver contract; this gate uses a
# private extractor so D3 ships with Depends-on: (none) before those land.
# DEPENDS_OPEN_REASON / DEPENDS_HELD_REASON defined with BOB-G1 block above.
DEPENDS_UNRESOLVED_REASON = "depends-unresolved"
# _QUALIFIED_DEPENDS_ISSUE_RE defined with FR #8754 Depends-on regexes above.
_RELATIVE_DEPENDS_ISSUE_RE = re.compile(r"^#(\d+)$")
_NONE_DEPENDS_VALUE_RE = re.compile(r"^\(none\)$", re.I)
# FR #9434: strip human annotations like ``#9259 (Digest: BOB-TRAY-UI)`` before
# whitespace tokenization so BOB-D5 does not treat ``(Digest:`` as a bad ref.
_DEPENDS_VALUE_ANNOTATION_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")



# FR #9548 / MRB #9551: bare annotation tokens beside a valid #N (Digest:…, see, digest,
# BOB-THEME slugs). True garbage (garbage-token) still fails BOB-D5 even when #N present.
_DEPENDS_ANNOTATION_SOFT_RE = re.compile(
    r"(?i)^(Digest:.*|see|digest|BOB-[A-Z0-9][A-Z0-9_-]*)$"
)


def _is_depends_annotation_soft_token(tok: str) -> bool:
    s = (tok or "").strip()
    return bool(s) and _DEPENDS_ANNOTATION_SOFT_RE.match(s) is not None

def _depends_on_value_tokens(value: str) -> list[str]:
    """Split a Depends-on value into issue-ref tokens; drop ``(...)`` / ``[...]`` notes."""
    cleaned = _DEPENDS_VALUE_ANNOTATION_RE.sub(" ", value or "")
    out: list[str] = []
    for raw in re.split(r"[,;\s]+", cleaned):
        tok = raw.strip().strip("`*")
        if tok:
            out.append(tok)
    return out


def _row_depends_on_issue_refs(row: dict) -> list[tuple[str, int]]:
    """Private BOB-D3 extractor: ``(owner/repo, number)`` from Depends-on stamps.

    Line-anchored, case-insensitive, optional Markdown bold. Accepts ``#N`` and
    ``owner/repo#N`` (comma/whitespace separated). Relative ``#N`` resolves against
    ``row["repo"]``. Repo keys are lower-cased. Empty / ``(none)`` / malformed /
    self-reference yield no refs. Public parser/resolver: BOB-D1 / BOB-D2.
    """
    if not isinstance(row, dict) or _canon_task(row) not in ("FR", "FIX", "MRB"):
        return []
    home_repo = _repo_key(str(row.get("repo") or ""))
    self_num_raw = str(row.get("id") or "").strip().lstrip("#")
    try:
        self_num = int(self_num_raw) if self_num_raw else None
    except ValueError:
        self_num = None
    blob = f"{str(row.get('title') or '')}\n{str(row.get('body') or '')}"
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for m in _DEPENDS_ON_LINE_RE.finditer(blob):
        value = (m.group(1) or "").strip()
        if not value or _NONE_DEPENDS_VALUE_RE.match(value):
            continue
        for tok in _depends_on_value_tokens(value):
            qm = _QUALIFIED_DEPENDS_ISSUE_RE.match(tok)
            if qm:
                pair = (_repo_key(qm.group(1)), int(qm.group(2)))
            else:
                rm = _RELATIVE_DEPENDS_ISSUE_RE.match(tok)
                if not rm:
                    continue
                if not home_repo:
                    continue
                pair = (home_repo, int(rm.group(1)))
            if self_num is not None and pair[0] == home_repo and pair[1] == self_num:
                continue
            if pair in seen:
                continue
            seen.add(pair)
            out.append(pair)
    return out


def _row_depends_on_has_bad_ref(row: dict) -> bool:
    """BOB-D5: True when a Depends-on line has only non-``#N`` / ``owner/repo#N`` tokens.

    ``(none)`` (whole value) and empty lines are fine. Relative ``#N`` without a
    home ``row["repo"]`` counts as unresolved. Self-references are ignored (not bad).
    Parenthetical / bracket annotations after a ref (FR #9434) are stripped first.

    FR #9548 ``bob_g1_depends_annotation_soft``: when a line already has at least one
    valid issue ref, trailing bare annotation tokens (e.g. ``Digest: BOB-TRAY-UI``
    without parentheses, or ``see digest``) are treated as notes - not
    ``depends-unresolved``. A line that is *only* junk still fails closed.
    """
    if not isinstance(row, dict) or _canon_task(row) not in ("FR", "FIX", "MRB"):
        return False
    home_repo = _repo_key(str(row.get("repo") or ""))
    self_num_raw = str(row.get("id") or "").strip().lstrip("#")
    try:
        self_num = int(self_num_raw) if self_num_raw else None
    except ValueError:
        self_num = None
    blob = f"{str(row.get('title') or '')}\n{str(row.get('body') or '')}"
    for m in _DEPENDS_ON_LINE_RE.finditer(blob):
        value = (m.group(1) or "").strip()
        if not value or _NONE_DEPENDS_VALUE_RE.match(value):
            continue
        line_good = False
        line_bad = False
        for tok in _depends_on_value_tokens(value):
            qm = _QUALIFIED_DEPENDS_ISSUE_RE.match(tok)
            if qm:
                pair = (_repo_key(qm.group(1)), int(qm.group(2)))
                if self_num is not None and pair[0] == home_repo and pair[1] == self_num:
                    continue
                line_good = True
                continue
            rm = _RELATIVE_DEPENDS_ISSUE_RE.match(tok)
            if rm:
                if not home_repo:
                    return True
                if self_num is not None and int(rm.group(1)) == self_num:
                    continue
                line_good = True
                continue
            if _is_depends_annotation_soft_token(tok):
                continue
            line_bad = True
        # FR #9548 / MRB #9551: annotation soft-tokens are ignored; any other junk
        # fails closed even when a valid #N is present (BOB-D5 / fr8809).
        # Junk-only (no valid ref) also fails closed.
        if line_bad:
            return True
    return False


def open_fr_issue_keys(doc: dict) -> set[tuple[str, int]]:
    """Open FR ``(lower repo, number)`` keys from unaccepted + accepted (not done)."""
    keys: set[tuple[str, int]] = set()
    if not isinstance(doc, dict):
        return keys
    for bucket in (doc.get("unaccepted") or [], doc.get("accepted") or []):
        for row in bucket:
            if not isinstance(row, dict) or _canon_task(row) != "FR":
                continue
            if str(row.get("state") or "").strip().lower() == "closed":
                continue
            repo = _repo_key(str(row.get("repo") or ""))
            raw = str(row.get("id") or "").strip().lstrip("#")
            if not repo or not raw:
                continue
            try:
                num = int(raw)
            except ValueError:
                continue
            if num < 1:
                continue
            keys.add((repo, num))
    return keys


def depends_issue_open_checker(issue_open=None):
    """Unbudgeted ``issue_open`` for the Depends-on gate (FR #8754 strengthen).

    ``!bored`` keeps ``BORED_GITHUB_CALL_BUDGET=0`` for ordinary lookups. Depends-on
    prerequisites are often still OPEN on GitHub while absent from the local FR
    queue, so this checker must live-check without consuming that budget. Test
    fakes (no ``.budget`` attr) are returned as-is; budgeted wrappers are replaced
    with ``github_issue_open_checker()`` (disk cache still applies).
    """
    if issue_open is not None and getattr(issue_open, "budget", None) is None:
        return issue_open
    try:
        return github_issue_open_checker()
    except Exception:
        return None


def row_depends_open_reason(
    row: dict,
    open_keys: set[tuple[str, int]] | None = None,
    *,
    issue_open=None,
    doc: dict | None = None,
    issue_fetch=None,
) -> str | None:
    """BOB-D3 / BOB-D5 + BOB-G1 digest go-gate.

    - `depends-held` (FR #8837): depend has ``hold`` / ``on-hold``.
    - unheld digest/fr-digest (BOB-G1/G3): OK while OPEN (`ok-fr-digest`).
    - `depends-open` (FR #8807): any ordinary Depends-on issue is positively OPEN.
    - `depends-unresolved` (FR #8809): malformed Depends-on token, or
      `issue_open` raises (`GitHubLookupUnknown` / budget / network).
    - Empty stamp / `(none)` / absent ref with no checker: do not block.
    - BOB-D4 / FR #8808: when every depend is CLOSED (absent from `open_keys` and
      `issue_open` False / unset), returns None so the FR is offerable again.
    - FR #8754: callers should pass ``depends_issue_open_checker(...)`` so OPEN
      GitHub issues block even when they are not local queue keys.
    - FR #9418: when the digest is OPEN on GitHub but absent from the local queue,
      pass ``issue_fetch`` / ``depends_issue_fetch_checker`` so G1 still sees
      fr-digest / hold (else live OPEN wrongly becomes ``depends-open``).
    - FR #9548: trailing bare annotation tokens beside a valid ``#N`` must not
      short-circuit as ``depends-unresolved`` before G1 soft-allow (see
      ``_row_depends_on_has_bad_ref`` / ``bob_g1_depends_annotation_soft``).
    """
    if _canon_task(row) not in ("FR", "FIX", "MRB"):
        return None
    if _row_depends_on_has_bad_ref(row):
        return DEPENDS_UNRESOLVED_REASON
    keys = open_keys if open_keys is not None else set()
    fetch = issue_fetch
    # FR #9665: durable GIVEUP depends_open block bypasses unheld fr-digest soft-allow
    # until those refs are CLOSED (auto-cleared here when checkers say closed).
    block_refs = clear_closed_depends_open_block(
        row, open_keys=keys if open_keys is not None else None, issue_open=issue_open
    )
    if block_refs:
        home = str(row.get("repo") or "").strip()
        for repo, num in block_refs:
            repo_s = str(repo or home or "").strip()
            if (repo_s, int(num)) in keys or (repo_s.lower(), int(num)) in {
                (r.lower(), n) for r, n in keys
            }:
                return DEPENDS_OPEN_REASON
            if issue_open is None:
                # No live checker: keep blocking while depends_open is non-empty.
                return DEPENDS_OPEN_REASON
            try:
                if bool(issue_open(repo_s, str(num))):
                    return DEPENDS_OPEN_REASON
            except Exception:
                return DEPENDS_UNRESOLVED_REASON
    refs = _row_depends_on_issue_refs(row)
    if not refs:
        return None
    unknown = False
    for repo, num in refs:
        g1 = _bob_g1_digest_gate_for_pair(
            doc if isinstance(doc, dict) else {}, repo, str(num), issue_fetch=fetch
        )
        if g1 == DEPENDS_HELD_REASON:
            return DEPENDS_HELD_REASON
        if g1 == "ok-fr-digest":
            # FR #10059: an unheld OPEN digest still blocks dispatch.
            return DEPENDS_OPEN_REASON
        dep = find_open_fr_row(doc, repo, num) if doc is not None else None
        if dep is not None:
            labs = _depend_row_label_names(dep)
            if "hold" in labs or "on-hold" in labs:
                return DEPENDS_HELD_REASON
            if row_is_digest_issue(dep):
                return DEPENDS_OPEN_REASON
        if (repo, num) in keys:
            return DEPENDS_OPEN_REASON
        if _depend_queue_state(doc if isinstance(doc, dict) else {}, repo, num) == "closed":
            continue
        if issue_open is None:
            # FR #10059: no live checker and not a positive CLOSED is unknown.
            # Keep scanning so a later ref that is positively OPEN still wins.
            unknown = True
            continue
        try:
            if bool(issue_open(repo, str(num))):
                # Live OPEN and not a G1 digest => ordinary depends-open (BOB-D3).
                # Callers (offer/assign) must pass issue_fetch via
                # depends_issue_fetch_checker so unqueued digests resolve without
                # a surprise live GET inside unit tests.
                return DEPENDS_OPEN_REASON
        except Exception:
            # Unknown / budget / network: fail closed (BOB-D5 / FR #8809).
            unknown = True
            continue
    if unknown:
        return DEPENDS_UNRESOLVED_REASON
    return None



@dataclass(frozen=True)
class GitClaim:
    repo: str
    task: str
    id: str
    event: str
    action: str
    line: str
    refs: tuple[str, ...] = ()  # linked issue ids e.g. ("#19",) when PR supersedes FR
    merged: bool | None = None  # pull_request closed: True if merged
    title: str = ""
    body: str = ""
    labels: tuple[str, ...] = ()
    state: str = ""
    # Lesson PRs: refs are citations, not implementation links; author = opener seat.
    harvest_lesson: bool = False
    opened_by: str = ""
    # FR #4851: webhook sender (issues closed) for shop CANCEL "closed by <user>".
    actor: str = ""
    # FR #6340: clean docs/mrb pin whose original is already merged/closed.
    docs_mrb_orphan: bool = False
    # FR #8475: orphan or main-base fix(mrb-N) is an ordinary MRB. Stacked
    # parent-branch fixes stay unstamped so purge still drops them (FR #2375).
    mrb_fix_offer: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root(home: Path) -> Path:
    return bobreport.fleet_digest_home(Path(home))


@contextmanager
def _scoped_digest_home(home: Path | None):
    """Temporarily point ``BOB_DIGEST_HOME`` at ``home`` for token lookup, then restore.

    FR #2540: ``os.environ.setdefault("BOB_DIGEST_HOME", …)`` leaked the first caller's
    home for the rest of the process. ``fleet_digest_home`` / ``queue_path`` then redirected
    every later test or seat onto that home (GET /bob/v1/report after FR #2458 was enough).
    """
    if home is None:
        yield
        return
    key = "BOB_DIGEST_HOME"
    prev = os.environ.get(key)
    os.environ[key] = str(home)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


def queue_path(home: Path) -> Path:
    return _root(home) / QUEUE_NAME


def activity_path(home: Path) -> Path:
    return _root(home) / ACTIVITY_NAME


def format_claimed(job: dict) -> str:
    """Shop line for the single claimed row. Webhook field order, no !TASK."""
    return f"{job.get('repo') or ''} {job.get('task') or ''} {job.get('id') or ''}".strip()


def is_bored_command(body: str) -> bool:
    return (body or "").strip().lower() == "!bored"


_WORKER_READY_RE = re.compile(
    r"(?i)^(?:[\w][\w.-]*\s+)?worker\s+ready\b"
)


def is_worker_ready_line(body: str) -> bool:
    """FR #9882: shop ``worker ready`` (optionally prefixed with nick) — primary offer cue.

    ``!bored`` remains a fallback when the chair missed ready/DONE.
    """
    text = (body or "").strip()
    if not text:
        return False
    return bool(_WORKER_READY_RE.match(text))


def shop_line_resets_bored_clock(body: str) -> bool:
    """FR #5203: ACK/DONE/NACK/GIVEUP mean the seat is not waiting to !bored."""
    text = (body or "").strip()
    if not text:
        return False
    return bool(re.match(r"(?i)^(?:@?\S+[:,]\s*)?(?:ACK|DONE|NACK|GIVEUP)\b", text))


def last_bored_path(home: Path) -> Path:
    return _root(home) / LAST_BORED_NAME


def load_last_bored(home: Path) -> dict[str, float]:
    """FR #5166: last !bored unix time per canonical seat nick."""
    p = last_bored_path(home)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in raw.items():
        nick = (canonical_worker_nick(str(key)) or str(key or "")).strip()
        if not nick:
            continue
        try:
            out[nick] = float(val)
            out[nick.lower()] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def record_last_bored(home: Path, nick: str, now: float | None = None) -> str | None:
    """Stamp ``nick`` as having said !bored. Returns canonical nick or None."""
    me = (canonical_worker_nick(nick) or (nick or "").strip())
    if not me:
        return None
    import time as _time

    ts = _time.time() if now is None else float(now)
    doc = load_last_bored(home)
    # drop lowercase aliases before write
    clean = {k: v for k, v in doc.items() if k and k == (canonical_worker_nick(k) or k)}
    clean[me] = ts
    last_bored_path(home).write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
    return me


def merge_last_bored(*homes: Path) -> dict[str, float]:
    """Union last-bored maps; later higher timestamp wins (FR #5166)."""
    out: dict[str, float] = {}
    for home in homes:
        if home is None:
            continue
        for key, val in load_last_bored(home).items():
            prev = out.get(key)
            if prev is None or float(val) > float(prev):
                out[key] = float(val)
    return out


def is_accept_command(body: str) -> bool:
    parts = (body or "").strip().split(None, 1)
    return bool(parts) and parts[0].lower() == "!accept"


def is_list_command(body: str) -> bool:
    """True for !list and optional filters: !list fr|mrb|uat|repo."""
    parts = (body or "").strip().split()
    return bool(parts) and parts[0].lower() == "!list"


def is_help_command(body: str) -> bool:
    """True for !help and !help <cmd> (FR #224 / gh-Jeeves #27)."""
    parts = (body or "").strip().split()
    return bool(parts) and parts[0].lower() == "!help"


_HELP_LAST: dict[str, float] = {}
HELP_RATE_S = 30.0

# Chair-visible commands (registry-lite; keep in sync with docs)
_HELP_INDEX = (
    ("!help [cmd]", "list commands or detail one (PM only)", "all"),
    ("!list [all|<repo>]", "unaccepted queue, one PM line per job", "all"),
    ("!status", "version/uptime/queue counts (when enabled)", "all"),
    ("!resync", "rebuild queue from GitHub now", "simon,bob-*"),
)


def reset_help_rate() -> None:
    _HELP_LAST.clear()


def help_rate_ok(nick: str, now: float) -> bool:
    key = (nick or "").strip().lower()
    if not key:
        return False
    last = _HELP_LAST.get(key)
    if last is not None and (float(now) - last) < HELP_RATE_S:
        return False
    _HELP_LAST[key] = float(now)
    return True


def help_rate_notice(nick: str, now: float) -> str:
    key = (nick or "").strip().lower()
    last = _HELP_LAST.get(key)
    if last is None:
        return "(help rate)"
    left = HELP_RATE_S - (float(now) - last)
    return f"(help sent; wait {int(max(0.0, left))}s)"


def format_help_lines(body: str, *, asker: str = "") -> list[str]:
    """PM lines for !help / !help <cmd>. One line per command; detail <=5 lines."""
    parts = (body or "").strip().split()
    arg = parts[1].lower().lstrip("!") if len(parts) > 1 else None
    asker_l = (asker or "").strip().lower()
    is_priv = asker_l == "simon" or asker_l.startswith("bob-")

    if arg:
        for syntax, summary, who in _HELP_INDEX:
            name = syntax.split()[0].lstrip("!").lower()
            if name != arg and not syntax.lower().startswith(f"!{arg}"):
                continue
            if who != "all" and not is_priv:
                return ["unknown command; try !help"]
            lines = [
                f"syntax: {syntax}",
                f"what: {summary}",
                f"who: {who}",
                f"example: {syntax.split()[0]}",
                "note: ACK/DONE/!bored are shop wire in #{machine}; Jeeves assigns (gh-Jeeves#106)",
            ]
            return lines[:5]
        return ["unknown command; try !help"]

    out: list[str] = []
    for syntax, summary, who in _HELP_INDEX:
        if who != "all" and not is_priv:
            continue
        out.append(f"{syntax} - {summary} [{who}]")
    out.append(
        "note: ACK/DONE/NACK/!bored in #{machine}; bob-* ear does not OFFER (Jeeves assigns)"
    )
    return out


def parse_list_command(body: str) -> tuple[str | None, str | None, bool]:
    """Return (task_filter, repo_filter, list_all)."""
    parts = (body or "").strip().split()
    if not parts or parts[0].lower() != "!list":
        return None, None, False
    task_f: str | None = None
    repo_f: str | None = None
    list_all = False
    for p in parts[1:]:
        up = p.upper()
        low = p.lower()
        if low in ("all", "full"):
            list_all = True
            continue
        if up in TASK_KINDS or up in ("FR", "MRB", "UAT", "PR", "FIX", "BUILD"):
            task_f = up
        elif REPO_RE.fullmatch(p) or ("/" in p and len(p) < 120):
            repo_f = p
    return task_f, repo_f, list_all


def reset_list_rate() -> None:
    _LIST_LAST.clear()


def list_rate_ok(nick: str, now: float) -> bool:
    """True if nick may receive a full list; stamps last time when True."""
    key = (nick or "").strip().lower()
    if not key:
        return False
    last = _LIST_LAST.get(key)
    if last is not None and (float(now) - last) < LIST_RATE_S:
        return False
    _LIST_LAST[key] = float(now)
    return True


def list_rate_remaining_s(nick: str, now: float) -> float:
    key = (nick or "").strip().lower()
    last = _LIST_LAST.get(key)
    if last is None:
        return 0.0
    left = LIST_RATE_S - (float(now) - last)
    return max(0.0, left)


def list_rate_notice(nick: str, now: float) -> str:
    left = list_rate_remaining_s(nick, now)
    ago = LIST_RATE_S - left
    if ago < 0:
        ago = 0.0
    return f"(list sent {int(ago)}s ago)"


def _job_title(row: dict) -> str:
    if str(row.get("title") or "").strip():
        return str(row.get("title")).strip()
    line = str(row.get("line") or "")
    # GIT issues repo opened #N title by user ΓÇö title is mid tokens
    if " by " in line:
        mid = line.rsplit(" by ", 1)[0]
        parts = mid.split()
        # drop GIT event repo action #id
        if len(parts) >= 5 and parts[0] == "GIT":
            return " ".join(parts[5:]).strip()
    return ""


def _job_age(row: dict, *, now: float | None = None) -> str:
    """Compact age from ts/accepted_ts (e.g. 5m, 2h, 1d)."""
    import time as _time

    raw = str(row.get("ts") or row.get("accepted_ts") or "").strip()
    if not raw:
        return "?"
    try:
        # 2026-09-25T12:00:00Z
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        from datetime import datetime

        dt = datetime.fromisoformat(raw)
        ts = dt.timestamp()
    except ValueError:
        return "?"
    now_f = _time.time() if now is None else float(now)
    sec = max(0, int(now_f - ts))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 86400:
        return f"{sec // 3600}h"
    return f"{sec // 86400}d"


def format_list_line(
    index: int,
    row: dict,
    *,
    line_max: int = LIST_LINE_MAX,
    now: float | None = None,
) -> str:
    """One PM line: ``#1 FR owner/repo#n 2h title`` (title truncated only)."""
    import focus_ignore as _fi_list

    task = str(row.get("task") or "?")
    repo = str(row.get("repo") or "?")
    ident = str(row.get("id") or "?")
    age = _job_age(row, now=now)
    title = _job_title(row)
    # Fixed prefix must never be truncated away.
    mark = "[critical] " if _fi_list.row_is_priority_critical(row) else ""
    if digest_issue_reason(row):
        mark = f"{mark}[digest] "
    head = f"#{index} {mark}{task} {repo}{ident} {age}"
    budget = max(8, int(line_max) - len(head.encode("utf-8")) - 1)
    if title:
        t_bytes = title.encode("utf-8")
        if len(t_bytes) > budget:
            # truncate on UTF-8 boundaries
            cut = title
            while cut and len(cut.encode("utf-8")) > budget - 1:
                cut = cut[:-1]
            title = cut + "ΓÇª"
        line = f"{head} {title}"
    else:
        line = head
    # hard cap (should already fit)
    while len(line.encode("utf-8")) > line_max and len(line) > 1:
        line = line[:-2] + "ΓÇª"
    return line


def format_unaccepted_list(
    home: Path,
    *,
    task_filter: str | None = None,
    repo_filter: str | None = None,
    list_all: bool = False,
    max_lines: int = LIST_MAX_LINES,
    line_max: int = LIST_LINE_MAX,
    now: float | None = None,
) -> list[str]:
    """PM lines for !list: optional one summary + one line per job + optional more.

    Updated FR #208: no header spam; default max 10 jobs; `N unaccepted (showing M)`.
    FR #9553: omit Depends-on gated FRs (`depends_gate_reason`) so !list matches
    digest `offerable_count` / !assign; `!stuck` still surfaces those rows.
    """
    try:
        doc = load_queue(home)
    except Exception:
        doc = {
            "v": 1,
            "unaccepted": list(load_unaccepted(home)),
            "accepted": [],
            "done": [],
        }
    if not isinstance(doc, dict):
        doc = {"v": 1, "unaccepted": [], "accepted": [], "done": []}
    rows = ordered_unaccepted(home, list(doc.get("unaccepted") or []))
    if task_filter:
        tf = task_filter.upper()
        rows = [r for r in rows if str(r.get("task") or "").upper() == tf]
    if repo_filter:
        rf = repo_filter.lower()
        rows = [r for r in rows if str(r.get("repo") or "").lower() == rf]
    try:
        open_keys = open_fr_issue_keys(doc)
    except Exception:
        open_keys = set()
    # FR #9821 / #9553: same issue_fetch as offer/assign so held digests absent
    # from the local queue still gate !list (token-free when digests are queued).
    _list_fetch = depends_issue_fetch_checker()
    rows = [
        r
        for r in rows
        if not (
            isinstance(r, dict)
            and _canon_task(r) == "FR"
            and depends_gate_reason(
                r, doc, open_keys=open_keys, issue_fetch=_list_fetch
            )
        )
    ]
    if not rows:
        return ["queue empty"]
    total = len(rows)
    cap = max(1, int(max_lines))
    if list_all:
        cap = max(cap, total)
    show = rows[:cap]
    out: list[str] = []
    if total > len(show):
        out.append(f"{total} unaccepted (showing {len(show)})")
    elif total > 1:
        out.append(f"{total} unaccepted (showing {len(show)})")
    # single job: no summary spam - just the job line
    for i, row in enumerate(show, start=1):
        out.append(format_list_line(i, row, line_max=line_max, now=now))
    more = total - len(show)
    if more > 0:
        out.append(f"+{more} more; !list all")
    return out




def parse_accept(body: str) -> tuple[str, str, str] | None:
    """Legacy line shape. Claiming ignores it. Not FILE v1 ACCEPT."""
    parts = (body or "").strip().split()
    if len(parts) != 4 or parts[0].lower() != "!accept":
        return None
    repo, task, ident = parts[1], parts[2], parts[3]
    if task not in TASK_KINDS or not REPO_RE.fullmatch(repo) or not ID_RE.fullmatch(ident):
        return None
    return repo, task, ident


def parse_git_announce(line: str) -> GitClaim | None:
    """Parse a Jeeves `GIT ΓÇª` line. None for ping, push, and other noise."""
    text = (line or "").strip()
    if not text.startswith(bobreport.GIT_ANNOUNCE_PREFIX):
        return None
    parts = text.split()
    if len(parts) < 5:
        return None
    event = parts[1].lower()
    repo = parts[2]
    action = parts[3].lower()
    ident = parts[4]
    task = CLAIM_ACTIONS.get((event, action))
    if task is None or not REPO_RE.fullmatch(repo) or not ID_RE.fullmatch(ident):
        return None
    return GitClaim(repo=repo, task=task, id=ident, event=event, action=action, line=text)


def _payload_repo(payload: dict) -> str:
    repo = payload.get("repository")
    if isinstance(repo, dict):
        return str(repo.get("full_name") or "").strip()
    return ""


def _payload_number(event: str, payload: dict) -> str | None:
    key = "pull_request" if event == "pull_request" else "issue" if event == "issues" else ""
    ent = payload.get(key) if key else None
    if not isinstance(ent, dict):
        return None
    num = ent.get("number")
    if isinstance(num, bool) or num is None:
        return None
    try:
        n = int(num)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    return f"#{n}"



def _repo_key(repo: str) -> str:
    """FR #3817 / #7121: case-folded canonical owner/name for queue identity."""
    return repo_alias.canonicalize_repo(str(repo or "").strip()).lower()


def _prefer_repo_casing(a: str, b: str) -> str:
    """Prefer GitHub-style casing (any uppercase) over an all-lowercase twin (FR #3817)."""
    left = str(a or "").strip()
    right = str(b or "").strip()
    if not left:
        return right
    if not right:
        return left
    if _repo_key(left) != _repo_key(right):
        return left
    if repo_alias.repos_equivalent(left, repo_alias.PRIORITY_MCP_CANONICAL):
        return repo_alias.PRIORITY_MCP_CANONICAL
    if left != left.lower() and right == right.lower():
        return left
    if right != right.lower() and left == left.lower():
        return right
    return left


def _job_key(repo: str, task: str, ident: str) -> tuple[str, str, str]:
    """FR #3817: case-insensitive repo + task + normalised id."""
    return (_repo_key(repo), str(task or "").upper(), _norm_row_id(ident))


def canonical_queue_repo(repo: str) -> str:
    """FR #785: map archived/legacy repos to their live successor (identity otherwise).

    FR #3817: comparisons use ``_repo_key`` (case-insensitive); this helper still
    returns the successor spelling (or the input spelling) for storage.
    """
    key = (repo or "").strip()
    if not key:
        return key
    mapped = repo_alias.canonicalize_repo(key)
    if mapped != key:
        return mapped
    return ARCHIVED_REPO_SUCCESSORS.get(key.lower(), key)


def repo_archived_for_queue(repo: str, *, payload: dict | None = None) -> bool:
    """FR #785: True when the repo is a known archived source or the payload marks it archived."""
    key = (repo or "").strip()
    if key and key.lower() in ARCHIVED_REPO_SUCCESSORS:
        return True
    if isinstance(payload, dict):
        blob = payload.get("repository")
        if isinstance(blob, dict) and blob.get("archived"):
            return True
    return False


def extract_closes_issue_ids(*texts: str, repo: str = "") -> tuple[str, ...]:
    """Issue ids referenced via Closes/Fixes/Resolves #n or ``Closes owner/repo#n`` (deterministic).

    FR #6460: ``Refs`` / ``Ref`` are intentionally excluded (citation only; they must not
    dequeue or supersede an open FR). With ``repo`` given, a link that names ANOTHER repo
    is ignored (it closes an issue elsewhere, not a row of this repo's queue).
    """
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for m in CLOSES_RE.finditer(text or ""):
            named = (m.group("repo") or "").lower()
            if repo and named and named != repo.lower():
                continue
            ident = f"#{int(m.group('num'))}"
            if ident not in seen:
                seen.add(ident)
                found.append(ident)
    return tuple(found)


def _pr_blob(payload: dict) -> dict:
    pr = payload.get("pull_request")
    return pr if isinstance(pr, dict) else {}


def _issue_blob(payload: dict) -> dict:
    issue = payload.get("issue")
    return issue if isinstance(issue, dict) else {}


def _label_names(labels) -> tuple[str, ...]:
    out: list[str] = []
    for lab in labels or []:
        if isinstance(lab, dict):
            name = str(lab.get("name") or "").strip()
        else:
            name = str(lab or "").strip()
        if name:
            out.append(name)
    return tuple(out)


def is_harvest_lesson_pr(
    *,
    title: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> bool:
    """True for a ``harvest-lesson`` / ``lesson(<book>):`` skill-book PR (FR #2705)."""
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    if "harvest-lesson" in labs:
        return True
    return bool(re.match(r"(?i)^lesson\s*\(", (title or "").strip()))


def is_docs_mrb_pin_pr(
    *,
    title: str = "",
    head_ref: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> bool:
    """True for a ``docs/mrb-*`` hostile pin PR (FR #4917 / #5500).

    FR #6936: GitHub titles are often ``docs(mrb-N):`` (parens) while the branch
    is ``docs/mrb-N``. Either shape is a pin.
    """
    del labels  # reserved; pins are branch/title shaped
    if re.match(r"(?i)^docs/mrb-", (head_ref or "").strip()):
        return True
    t = (title or "").strip()
    return bool(re.match(r"(?i)^docs[/()]mrb-\d+", t))


_DOCS_MRB_PARENT_RE = re.compile(r"(?i)^docs[/()]mrb-(\d+)\b")


def docs_mrb_pin_parent_pr_id(*, title: str = "", head_ref: str = "") -> str:
    """Parent PR id ``#N`` from ``docs/mrb-N`` head/title, or empty (FR #6340)."""
    for blob in ((head_ref or "").strip(), (title or "").strip()):
        m = _DOCS_MRB_PARENT_RE.match(blob)
        if m:
            return f"#{m.group(1)}"
    return ""


def is_lesson_or_pin_pr(
    *,
    title: str = "",
    labels: tuple[str, ...] | list[str] = (),
    head_ref: str = "",
) -> bool:
    """True for harvest-lesson tips or docs/mrb pin PRs (FR #4917)."""
    if is_harvest_lesson_pr(title=title, labels=labels):
        return True
    if is_docs_mrb_pin_pr(title=title, head_ref=head_ref, labels=labels):
        return True
    return bool(re.match(r"(?i)^intake/", (head_ref or "").strip()))


# FR #4968: intake harvest PR bodies (ver=20261020-fr4917) include the light-triage
# instruction paragraph with "board CLOSED not-useful". That must not mark a normal
# product lesson as lesson-of-lesson (webhook path stored the full body; resync
# stored empty body and therefore offered).
_INTAKE_LIGHT_TRIAGE_BOILERPLATE_RE = re.compile(
    r"(?is)MRB\s*\(\s*light\s+triage\s*\):.*?"
    r"(?=\n\s*\n|\nTarget\s+skill\s+book:|\n---|\Z)"
)


def strip_intake_light_triage_boilerplate(body: str = "") -> str:
    """Remove the standard intake light-triage instruction block (FR #4968)."""
    return _INTAKE_LIGHT_TRIAGE_BOILERPLATE_RE.sub("\n", body or "")


def is_lesson_of_lesson_pr(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    head_ref: str = "",
) -> bool:
    """True when a tip is meta about another lesson/pin job (FR #4917).

    Jeeves must not queue MRB for these; seats must not open a further docs/mrb pin.
    Product playbooks that merely mention fill-madeira / soft-deploy stay False.

    FR #4968: strip the intake light-triage boilerplate before matching so the
    template's ``CLOSED not-useful`` instruction does not false-positive.
    """
    if not is_lesson_or_pin_pr(title=title, labels=labels, head_ref=head_ref):
        return False
    body_n = strip_intake_light_triage_boilerplate(body)
    blob = f"{title or ''}\n{body_n}"
    # Pin of a pin / pin whose parent tip is itself a pin or lesson-of-lesson.
    if is_docs_mrb_pin_pr(title=title, head_ref=head_ref, labels=labels):
        if re.search(r"(?i)Refs\s+\S+#\d+|Refs\s+https://github\.com/\S+/pull/\d+", blob):
            if re.search(
                r"(?i)harvest[- ]lesson|docs/mrb-\d+|lesson\s*\(|CLOSED[- ]duplicate|"
                r"FAIL[- ]supersede|light[- ]triage|pin harvest",
                blob,
            ):
                # First-level pin of a product lesson still Refs the promote PR;
                # only treat as chain when the tip text is about reviewing/closing tips.
                if re.search(
                    r"(?i)CLOSED[- ]duplicate|FAIL[- ]supersede|process[- ]loop|"
                    r"light[- ]triage|lesson[- ]of[- ]lesson|reassign|"
                    r"restating\s+mrb\d+|twin of\s*#\d+",
                    blob,
                ):
                    return True
        return False
    # harvest-lesson tip about MRB/FIX/close of another tip or pin.
    return bool(
        re.search(
            r"(?i)CLOSED[- ]duplicate|FAIL[- ]supersede|CLOSED\s+not[- ]useful|"
            r"CLOSED\s+harvest\s+tip|process[- ]loop|tip[- ]?loop|"
            r"light[- ]triage.{0,80}(?:PASS|CLOSED|FAIL)|"
            r"harvest[- ]lesson\s+MRB|docs/mrb-\d+.{0,80}(?:FIX|MRB|CONFLICTING)|"
            r"\bFIX\b.{0,120}docs/mrb|\bFIX\b.{0,120}\bmrb\d{3,}\b|"
            r"MRB\s+reassign|do not invent a second tip|"
            r"restating\s+mrb\d+|needle[- ]drift tip twin",
            blob,
        )
    )


_LESSON_OPENER_SEAT_RE = re.compile(
    r"(?i)\b(?P<key>seat|agent)=`?(?P<nick>[A-Za-z0-9_.+-]+)`?"
)


def lesson_pr_opener_seat(body: str = "") -> str:
    """Seat nick that opened a lesson PR, from the intake provenance footer (``seat=`` / ``agent=``).

    A lesson PR's author is whoever opened it. The seats that implemented an FR the
    lesson merely cites are not its authors. Returns '' when no seat nick is named
    (operator / audit PRs, ``agent=`Invoke-BobiverseHarvest``` without ``seat=``).

    FR #8095: prefer ``seat=`` over ``agent=``; accept canonical ``<machine>-<pid>``
    via ``canonical_worker_nick`` even when the machine is not yet in seat_machine_ids.
    """
    seat_hit = ""
    agent_hit = ""
    for m in _LESSON_OPENER_SEAT_RE.finditer(body or ""):
        nick = (m.group("nick") or "").strip()
        if not nick:
            continue
        canon = canonical_worker_nick(nick)
        if not canon:
            continue
        key = (m.group("key") or "").lower()
        if key == "seat" and not seat_hit:
            seat_hit = canon
        elif key == "agent" and not agent_hit:
            agent_hit = canon
    return seat_hit or agent_hit


def _heal_lesson_mrb_row(row: dict, opener: str) -> None:
    """Lesson MRB row: drop cited-FR refs and any author stamp that is not the opener."""
    row.pop("refs", None)
    for k in ("author_seat", "implementer_seat", "author_nick", "author", "author_seats"):
        row.pop(k, None)
    if opener:
        row["author_seat"] = opener
        row["implementer_seat"] = opener



def _intake_pr_changed_paths(blob) -> list[str]:
    """Best-effort changed paths from a PR/issue dict (FR #6356).

    Accepts ``changed_files`` as a list of path strings or GitHub file objects
    with ``filename`` / ``path``. Empty when unknown (body heuristics still apply).
    """
    if not isinstance(blob, dict):
        return []
    raw = blob.get("changed_files")
    if raw is None:
        raw = blob.get("files")
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            name = str(item.get("filename") or item.get("path") or "").strip()
            if name:
                out.append(name)
    return out


def fetch_pr_changed_paths(repo: str, num: int, *, fetch_json=None) -> list[str]:
    """GET /repos/{repo}/pulls/{num}/files filenames (FR #6359).

    Used when webhook/list payloads omit ``changed_files``. Soft-fail to [] on
    errors so body heuristics still apply. ``fetch_json`` is the test seam.
    """
    repo_s = str(repo or "").strip()
    try:
        n = int(str(num).lstrip("#"))
    except (TypeError, ValueError):
        return []
    if not repo_s or n <= 0:
        return []
    url = f"https://api.github.com/repos/{repo_s}/pulls/{n}/files?per_page=100"
    getter = fetch_json
    if getter is None:
        token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
        if not token:
            return []

        def _default(u: str):
            req = urllib.request.Request(
                u,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "bobiverse-gitclaim",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read()
                return json.loads(
                    raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
                )

        getter = _default
    try:
        data = getter(url)
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        data = data.get("files") or data.get("items") or []
    if not isinstance(data, (list, tuple)):
        return []
    return _intake_pr_changed_paths({"files": list(data)})


def resolve_intake_pr_changed_paths(
    blob,
    *,
    repo: str = "",
    number=None,
    fetch_json=None,
) -> list[str]:
    """Prefer paths on *blob*; else fetch when repo+number known (FR #6359)."""
    paths = _intake_pr_changed_paths(blob)
    if paths:
        return paths
    if not repo or number is None:
        return []
    return fetch_pr_changed_paths(repo, number, fetch_json=fetch_json)


def is_intake_harvest_only_paths(paths=None) -> bool:
    """True when every changed path is under docs/intake-harvest/ (FR #6356).

    GhCliFiler create_draft_pr with empty files writes only
    ``docs/intake-harvest/<branch>.md``. Real skill-book / harvest-lesson tips
    also touch ``.grok/skills/**`` or other docs.
    """
    items = [
        str(p).replace("\\", "/").lstrip("./")
        for p in (paths or [])
        if str(p).strip()
    ]
    if not items:
        return False
    return all(_INTAKE_HARVEST_PATH_RE.match(p) for p in items)


def is_intake_harvest_receipt_pr(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    files=None,
) -> bool:
    """True when a pull is an intake harvest/skill receipt, not shop MRB work (FR #2650).

    Matches GhCliFiler drafts: ``harvest:`` / ``skill`` title plus ``via-intake``+``skill``
    labels, ``Invoke-BobiverseHarvest`` / ``Session summary:`` footer, or a receipt
    status word (DONE/PASS/FAIL/GIVEUP/SKIP/twin/…). Real worker promote PRs lack
    ``via-intake`` and receipt-status titles.

    FR #2705: ``harvest-lesson`` / ``lesson(<book>):`` skill-book PRs that touch
    ``.grok/skills/**`` (or other non-intake-harvest paths) are offerable MRB work.

    FR #5685: ``via-intake``+``skill`` tips with a ``_via-intake`` / queue-me stub body and
    no ``Lesson`` section are receipts (e.g. docs/intake-harvest only), even when the
    title is not ``harvest:`` / ``skill``.

    FR #6356 / #6359: bare ``MRB (light triage)`` boilerplate is not a Lesson body.
    Tips whose changed files are only under ``docs/intake-harvest/`` are receipts even
    with a ``Lesson`` heading, ``lesson(...)`` title, or ``harvest-lesson`` label
    (bobiverse#6358).
    """
    title_s = (title or "").strip()
    body_s = body or ""
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    # FR #6356 / #6359: docs/intake-harvest-only tips are receipts even when titled
    # lesson(...) or labelled harvest-lesson (GhCliFiler empty-files drafts).
    # Path check must run before the FR #2705 lesson-title exemption.
    if is_intake_harvest_only_paths(files):
        return True
    if "harvest-lesson" in labs:
        return False
    if re.match(r"(?i)^lesson\s*\(", title_s):
        return False
    harvestish = bool(HARVEST_TITLE_RE.match(title_s))
    via_intake_skill = "via-intake" in labs and "skill" in labs
    if via_intake_skill and (harvestish or _INTAKE_HARVEST_FOOTER_RE.search(body_s)):
        return True
    if harvestish and _INTAKE_HARVEST_FOOTER_RE.search(body_s):
        return True
    if harvestish and _HARVEST_RECEIPT_STATUS_RE.search(title_s):
        return True
    # FR #5685 / #6356: stub (queue me / bare via-intake footer) without a Lesson section.
    if via_intake_skill and not _INTAKE_SKILL_LESSON_BODY_RE.search(body_s):
        if _VIA_INTAKE_ID_FOOTER_RE.search(body_s) or _QUEUE_ME_STUB_RE.search(body_s):
            return True
    return False


def is_offerable_intake_skill_lesson_pr(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    files=None,
) -> bool:
    """FR #5506 / #5685 / #6356: real via-intake+skill lesson (not a GhCliFiler receipt).

    Drafts with a ``Lesson`` / ``## Lesson`` section are shop MRB work. Receipt
    titles or ``Invoke-BobiverseHarvest`` / ``Session summary:`` footers stay skipped.

    FR #5685 / #6356: a non-harvest title alone is not enough --- require a ``Lesson``
    section in the body. Bare ``MRB (light triage)`` boilerplate (prepended to every
    skill draft) and docs/intake-harvest-only tips (agentic_fomprep#144 / #377) are
    never offered as MRB.
    """
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    if "via-intake" not in labs or "skill" not in labs:
        return False
    # FR #6359: belt-and-braces even if receipt exemptions change order.
    if is_intake_harvest_only_paths(files):
        return False
    if is_intake_harvest_receipt_pr(title=title, body=body, labels=labels, files=files):
        return False
    title_s = (title or "").strip()
    if _HARVEST_RECEIPT_STATUS_RE.search(title_s):
        return False
    body_s = body or ""
    return bool(_INTAKE_SKILL_LESSON_BODY_RE.search(body_s))


_DRAFT_SKILL_BOOK_RE = re.compile(
    r"(?i)target skill book:\s*`?([A-Za-z0-9_.-]+)`?"
)


def is_draft_skill_leaflet(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    files=None,
) -> bool:
    """FR #8477: draft via-intake+skill leaflet that should be marked ready.

    A receipt title (DONE/PASS/FAIL/GIVEUP/SKIP) stays a draft. A real leaflet
    has a Lesson section, or a skill/harvest title plus a non-stub body, and
    does not only touch docs/intake-harvest/.
    """
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    if "via-intake" not in labs or "skill" not in labs:
        return False
    if is_intake_harvest_only_paths(files):
        return False
    title_s = (title or "").strip()
    if _HARVEST_RECEIPT_STATUS_RE.search(title_s):
        return False
    body_s = body or ""
    if _INTAKE_SKILL_LESSON_BODY_RE.search(body_s):
        return True
    if not HARVEST_TITLE_RE.match(title_s):
        return False
    if not body_s.strip() or _QUEUE_ME_STUB_RE.search(body_s):
        return False
    return True


def lesson_title_for_draft_skill(title: str, body: str = "") -> str:
    """Retitle a skill: leaflet to lesson(<book>): so FR #2705 can offer it."""
    title_s = (title or "").strip()
    if re.match(r"(?i)^lesson\s*\(", title_s):
        return title_s[:240]
    found = _DRAFT_SKILL_BOOK_RE.search(body or "")
    book = found.group(1) if found else "skill"
    rest = re.sub(r"(?i)^(skill|harvest)\s*:\s*", "", title_s).strip() or title_s or "skill leaflet"
    return f"lesson({book}): {rest}"[:240]


def promoted_draft_skill_view(pr: dict) -> dict:
    """Local view of a leaflet after ready_for_review (draft false, lesson title)."""
    out = dict(pr)
    out["draft"] = False
    out["title"] = lesson_title_for_draft_skill(
        str(pr.get("title") or ""), str(pr.get("body") or "")
    )
    return out


def github_promote_draft_skill_leaflet(repo: str, pr: dict, *, token: str) -> dict | None:
    """Mark a draft skill leaflet ready and retitle it (FR #8477).

    Returns the undrafted view, or None when GitHub refuses. Never logs the token.
    Operator fallback: gh pr ready, and a lesson(<book>): title.
    """
    import urllib.request

    if not token or not isinstance(pr, dict):
        return None
    num = pr.get("number")
    node = str(pr.get("node_id") or "")
    if not isinstance(num, int) or not node:
        return None
    new_title = lesson_title_for_draft_skill(
        str(pr.get("title") or ""), str(pr.get("body") or "")
    )
    hdrs = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "bobiverse-jeeves",
        "Content-Type": "application/json",
    }
    try:
        patch = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/pulls/{num}",
            data=json.dumps({"title": new_title}).encode("utf-8"),
            headers=hdrs,
            method="PATCH",
        )
        with urllib.request.urlopen(patch, timeout=30):
            pass
        query = (
            "mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id})"
            "{pullRequest{isDraft}}}"
        )
        gql = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query, "variables": {"id": node}}).encode("utf-8"),
            headers=hdrs,
            method="POST",
        )
        with urllib.request.urlopen(gql, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        pr_node = ((raw.get("data") or {}).get("markPullRequestReadyForReview") or {}).get(
            "pullRequest"
        ) or {}
        if pr_node.get("isDraft") is True or raw.get("errors"):
            return None
    except Exception:  # noqa: BLE001
        return None
    return promoted_draft_skill_view(pr)


# FR #5847: Copilot Coding Agent FR implement PRs (often draft) must enter the MRB
# queue and supersede the FR so stuck-sweep does not release accepted_holder_gone.
COPILOT_FR_HEAD_RE = re.compile(r"(?i)^copilot/fr-(\d+)(?:-|$)")


def is_copilot_agent_login(login: str = "") -> bool:
    """True for Copilot Coding Agent / app logins (FR #5847)."""
    s = str(login or "").strip().lower()
    if not s:
        return False
    if "copilot-swe-agent" in s:
        return True
    return s in ("copilot", "app/copilot-swe-agent", "copilot-swe-agent[bot]")


def copilot_fr_head_issue(head_ref: str = "") -> str:
    """Issue id from head ``copilot/fr-<N>-*``, else empty (FR #5847)."""
    m = COPILOT_FR_HEAD_RE.match(str(head_ref or "").strip())
    if not m:
        return ""
    return f"#{int(m.group(1))}"


def is_copilot_fr_implement_pr(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    head_ref: str = "",
    user_login: str = "",
    repo: str = "",
) -> bool:
    """Draft-offerable Copilot FR implement PR (FR #5847).

    Matches head ``copilot/fr-<N>-*``, or Copilot agent author with
    Closes/Fixes/Resolves naming an issue. Not docs pins.
    """
    del labels  # call-site parity with other PR classifiers
    if is_docs_mrb_pin_pr(title=title, head_ref=head_ref, labels=()):
        return False
    if copilot_fr_head_issue(head_ref):
        return True
    if is_copilot_agent_login(user_login) and extract_closes_issue_ids(
        title, body, repo=repo
    ):
        return True
    return False


def copilot_fr_pr_covers_issue(
    *,
    issue_id: str,
    title: str = "",
    body: str = "",
    head_ref: str = "",
    user_login: str = "",
    repo: str = "",
) -> bool:
    """True when a Copilot PR covers this FR issue id (FR #5847)."""
    want = _norm_row_id(issue_id)
    if not want:
        return False
    head_iss = copilot_fr_head_issue(head_ref)
    if head_iss and head_iss == want:
        return True
    if not is_copilot_agent_login(user_login) and not head_iss:
        return False
    return want in extract_closes_issue_ids(title, body, repo=repo)


def ops_monitor_tracker_reason(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> str | None:
    """FR #9411 / #9402: why an issue is an ops/MONITORING gate tracker (None = ordinary FR).

    These trackers must not be ``feature-request`` shop work. Chair skips enqueue/offer
    even when ``hold`` was cleared so MONITORING can finish (class of #9376 / #9411).
    """
    blob = f"{title or ''}\n{body or ''}"
    if OPS_MONITOR_TRACKER_BODY_RE.search(blob):
        return "ops_monitor_tracker"
    return None



def tipform_restore_escalate_reason(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> str | None:
    """FR #9827: TipForm-restore / online_zero_workers escalate receipt (None = ordinary FR).

    Ops TipForm Agents-only filings (class of #9824 / #9378 / #9103). Never skip
    stamped `feature-request` product work (e.g. #9462). `stall:online-zero-workers:`
    titles remain `stall_receipt` via the earlier `^stall:` check.
    """
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    if "feature-request" in labs:
        return None
    title_s = (title or "").strip()
    if TIPFORM_RESTORE_ESCALATE_TITLE_RE.search(title_s):
        return "tipform_restore_escalate"
    if "via-intake" in labs and TIPFORM_RESTORE_ESCALATE_BODY_RE.search(body or ""):
        return "tipform_restore_escalate"
    return None


def issue_skip_fr_reason(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    state: str = "",
    scan_label_text: bool = True,
) -> str | None:
    """FR #180 / #258: why an issue must not become (or stay) an assignable FR row; None = ok.

    ``scan_label_text`` (default True): when labels are empty, scan the title for
    legacy board-label tokens. FR #9424: callers pass False for MRB/FIX PR rows so
    titles that mention ``fr-digest`` (feature names) are not ``label_text`` skips.
    """
    if (state or "").strip().lower() == "closed":
        return "closed"
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    hit = labs & SKIP_FR_LABELS
    # FR #2562 / #2677: reverse #2464 - do not drop bare `mrb` when mrb-fail is present.
    if hit:
        return f"label:{sorted(hit)[0]}"
    title_s = (title or "").strip()
    # FR #8376: stall detector receipts (stall:all-gave-up:… and sibling stall:*)
    # are not shop FR work. They must not be offered or stamped needs_human.
    if re.match(r"(?i)^stall:", title_s):
        return "stall_receipt"
    # FR #9038: bob-worker files these when the agent CLI exits non-zero
    # (report_agent_cli_nonzero_exit). They are detector receipts of FR #7593,
    # already handled by GIVEUP + seat restart. Do not offer them as FR work.
    if title_s == "bug: agent CLI nonzero exit (FR #7593)":
        return "cli_exit_receipt"
    # FR #3658 / #3317: owner-missing hold titles (even with empty labels).
    if HARVEST_OWNER_MISSING_HOLD_TITLE_RE.search(title_s):
        return "owner_missing_hold_title"
    # FR #1682 / #1684: harvest:/skill: titles are offerable promote jobs (workers
    # consolidate by skill book then open a harvest/* PR). Do not SKIP_FR them -
    # except the hold-title carve-out above.
    # FR #628 / #2670: drain / Nth re-offer shapes are always spam.
    if CRITICAL_SPAM_SHAPE_RE.search(title_s):
        return "critical_spam_title"
    # FR #2670: via-intake / feature-request CRITICAL: is real work (must queue +
    # block UAT). Bare CRITICAL: without those labels stays SKIP_FR (seat spam).
    if CRITICAL_SPAM_PREFIX_RE.search(title_s):
        if "via-intake" not in labs and "feature-request" not in labs:
            return "critical_spam_title"
    # FR #2562 / #2677: MRB FAIL:/PASS: verdict board titles are never FR jobs.
    if MRB_VERDICT_TITLE_RE.search(title_s):
        return "mrb_verdict_title"
    blob = f"{title_s}\n{body or ''}"
    if SAFE_TO_CLOSE_RE.search(blob):
        return "safe_to_close"
    # FR #2480: exact fomprep MRB-home board signature in body (not generic "MRB home" prose).
    if _MRB_HOME_BOARD_BODY_RE.search(body or ""):
        return "mrb_home_board_body"
    # bobiverse#258 / FR #133 / FR #987: evergreen MRB-home boards by title shape only
    # (label mrb-home/evergreen already returned above). Do not scan the body ΓÇö real FRs
    # that mention "MRB home" in prose must stay assignable.
    if EVERGREEN_MRB_HOME_TITLE_RE.search(title_s):
        return "evergreen_mrb_home"
    # FR #595 / MRB #603 / FR #987: legacy queue rows may only put board labels in
    # title/line text (empty labels). Never run this scan when GitHub/labels are present
    # (false-positive on titles like "skip for stale mrb-home rows" / bodies saying
    # "evergreen"). Title/line only ΓÇö never the body.
    if not labs and scan_label_text:
        title_l = title_s.lower()
        text_hits = []
        for lab in sorted(SKIP_FR_LABELS_IN_TEXT, key=len, reverse=True):
            if re.search(rf"(?<![a-z0-9]){re.escape(lab)}(?![a-z0-9])", title_l):
                text_hits.append(lab)
        if text_hits:
            return f"label_text:{text_hits[0]}"
    # FR #1812: via-intake+skill "PR opened" / pull URL summaries are receipts of an
    # already-open harvest PR - do not enqueue as FR work (workers would re-implement).
    if "via-intake" in labs and "skill" in labs:
        if re.search(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+", blob, re.I):
            return "harvest_pr_summary"
        if re.search(r"(?i)\bPR\s+opened\b", title_s):
            return "harvest_pr_summary"
    # FR #9304: Kind: fr-digest body stamp (go-gate epic) even without the label.
    if FR_DIGEST_KIND_BODY_RE.search(body or ""):
        return "fr_digest_kind"
    # FR #9411 / #9402: ops / MONITORING rebuild-install trackers are not shop FR work.
    ops = ops_monitor_tracker_reason(title=title_s, body=body or "", labels=tuple(labs))
    if ops:
        return ops
    # FR #9827: TipForm-restore / online_zero_workers escalate receipts (no feature-request).
    tip = tipform_restore_escalate_reason(
        title=title_s, body=body or "", labels=tuple(labs)
    )
    if tip:
        return tip
    return None


def row_skip_fr_reason(row: dict) -> str | None:
    labels = row.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    repo = _repo_key(row.get("repo") or "")
    ident = _norm_row_id(row.get("id"))
    if repo and ident and (repo, ident) in _NEEDS_HUMAN_ISSUE_PINS:
        return "needs_human_hold"
    if repo and ident and (repo, ident) in _SKIP_FR_ISSUE_PINS:
        return "hard_pin_umbrella"
    # Queue rows often store the issue title in ``line`` (offer/list); fall back so
    # mrb-home / harvest title skips still fire when ``title`` was never stamped.
    title = str(row.get("title") or "").strip() or str(row.get("line") or "").strip()
    task = _canon_task(row)
    # FR #9424: MRB/FIX (and PR-shaped) rows often have labels=[]; never treat a
    # title that mentions fr-digest / board tokens as skip_fr.
    scan_label_text = task == "FR" and not _row_is_pr_shaped_issue(row)
    return issue_skip_fr_reason(
        title=title,
        body=str(row.get("body") or ""),
        labels=tuple(str(x) for x in labels),
        state=str(row.get("state") or ""),
        scan_label_text=scan_label_text,
    )


def _parse_iso_ts(raw: str) -> float | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def row_on_cooldown(row: dict, now: float, nick: str = "", live: set[str] | None = None) -> bool:
    """True when this seat must wait out ``cooldown_until``.

    Global row cooldown after GIVEUP used to block *every* seat for
    ``GIVEUP_COOLDOWN_S``, which left the fleet idle while other live seats
    could have taken the work. Ledger / ``giveup_seats`` already prevent
    re-offer to the giver; other seats skip the global wait.
    Compare seats via ``canonical_worker_nick`` so ``w-io-<pid>`` matches
    ``win-mpre8vi4u6u-<pid>`` stored after GIVEUP.
    FR #5088: ``live`` is accepted for API stability but give-up/cooldown matching
    is exact-seat only (recycled successors are not blocked). ``needs_human`` remains
    the global auto-offer gate (FR #4336).
    """
    until = _parse_iso_ts(str(row.get("cooldown_until") or ""))
    if until is None or float(now) >= until:
        return False
    me = (nick or "").strip()
    if not me:
        return True
    seats = giveup_seat_set(row)
    if seats and not nick_in_giveup_seats(row, me, live=live):
        return False
    return True


# FR #8628: one auto-offer after an agent CLI crash, then needs_human holds again.
_CLI_EXIT_RETRY_REASON = "agent-cli-nonzero-exit"


def cli_exit_fresh_seat_retry(row: dict, nick: str = "", now: float | None = None) -> bool:
    """True when this nick may take one auto-offer past needs_human (FR #8628).

    Only ``giveup_reason=agent-cli-nonzero-exit``, after cooldown, for a nick
    that is not already in ``giveup_seats``, and only before
    ``cli_exit_retry_used`` is stamped on the offer. Empty nick stays blocked
    so global scans still see needs_human. ``!assign`` is unchanged.
    """
    if not isinstance(row, dict):
        return False
    me = (nick or "").strip()
    if not me:
        return False
    if row.get("cli_exit_retry_used"):
        return False
    if str(row.get("giveup_reason") or "").strip() != _CLI_EXIT_RETRY_REASON:
        return False
    flag = row.get("needs_human")
    if isinstance(flag, bool):
        on = flag
    else:
        on = str(flag or "").strip().lower() in ("1", "true", "yes")
    if not on:
        return False
    when = time.time() if now is None else float(now)
    until = _parse_iso_ts(str(row.get("cooldown_until") or ""))
    if until is not None and when < until:
        return False
    if nick_in_giveup_seats(row, me):
        return False
    return True


def stamp_cli_exit_retry_used(row: dict) -> None:
    """Mark the one FR #8628 auto-offer as spent once the row is offered."""
    if not isinstance(row, dict):
        return
    if row.get("cli_exit_retry_used"):
        return
    if str(row.get("giveup_reason") or "").strip() != _CLI_EXIT_RETRY_REASON:
        return
    if not row.get("needs_human"):
        return
    row["cli_exit_retry_used"] = True


def row_needs_human(row: dict, nick: str = "") -> bool:
    """True when auto-offer paths must not hand out this row (FR #4336).

    Once `needs_human` is stamped, **every** seat is blocked for `!bored`,
    done-offer, idle feed, and seat-reconcile revive. Only an explicit chair
    `!assign` may hand the row out (`assign_row` skips this gate).

    FR #8628: a fresh nick (not in giveup_seats) may pass once after cooldown
    when giveup_reason is agent-cli-nonzero-exit. The offer stamps
    cli_exit_retry_used so the next fresh nick is blocked again.

    Early per-seat GIVEUP still uses `giveup_seats` / `row_gave_up_by` /
    cooldown before the needs_human stamp (FR #1236). FR #3277's "other seats
    may still take a needs_human row" behaviour is superseded by FR #4336 after
    live re-offer loops of recycled nicks past giveup_seats.

    FR #4711: an owner ``issue_comment`` after ``giveup_ts`` clears the stamp
    via ``clear_needs_human_from_owner_issue_comment`` so the next ``!bored``
    can offer again. Seat GIVEUP-shaped comments do not clear.
    """
    if not _needs_human_flag(row):
        return False
    # FR #8634: a stale holder_bored / other infra-soft stamp must not black out
    # auto-offer. Those reasons never should have set needs_human (FR #8375).
    # Seats already in giveup_seats stay out via row_gave_up_by. A fresh nick
    # can take the row without waiting for the monitor heal.
    if is_infra_soft_giveup_reason(str(row.get("giveup_reason") or "")):
        return False
    if cli_exit_fresh_seat_retry(row, nick):
        return False
    return True


def _needs_human_flag(row: dict) -> bool:
    """Raw needs_human bit, ignoring FR #8628 / #8634 offer exceptions."""
    if not isinstance(row, dict):
        return False
    v = row.get("needs_human")
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes")


# FR #4711: seat wire / board comments must not clear needs_human (same GitHub
# login as the repo owner when seats use fleet gh tokens).
_SEAT_ISSUE_COMMENT_RE = re.compile(
    r"(?im)^\s*(GIVEUP|NACK|ACK|DONE)\b"
    r"|^\s*##\s*MRB\s+board\b"
    r"|\breason\s*=\s*needs_human\b"
    r"|\bself[-_]?MRB\b",
)


def comment_looks_like_seat_wire(body: str) -> bool:
    """True when a GitHub issue comment is seat GIVEUP/ACK/DONE/MRB-board shaped."""
    return bool(_SEAT_ISSUE_COMMENT_RE.search(body or ""))


def comment_is_repo_owner(payload: dict, comment: dict) -> bool:
    """True when the comment author is the repository owner (login or OWNER assoc)."""
    if not isinstance(payload, dict) or not isinstance(comment, dict):
        return False
    assoc = str(comment.get("author_association") or "").strip().upper()
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    login = str((user or {}).get("login") or "").strip().lower()
    repo = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    owner = (repo or {}).get("owner") if isinstance((repo or {}).get("owner"), dict) else {}
    owner_login = str((owner or {}).get("login") or "").strip().lower()
    if owner_login and login and login == owner_login:
        return True
    return assoc == "OWNER"


def stamp_coderabbit_from_webhook(home: Path, event: str, payload: dict) -> dict:
    """FR #6434: stamp MRB queue rows from CodeRabbit webhook surfaces.

    Handles ``pull_request_review`` (ready/failed/skipped), ``issue_comment``
    (skip walkthrough), and ``check_run`` (CodeRabbit completed check).
    Returns ``{stamped, repo, id, reason}`` (empty stamped when nothing matched).
    """
    out: dict = {"stamped": "", "repo": "", "id": "", "reason": ""}
    if not isinstance(payload, dict):
        return out
    ev = (event or "").strip().lower()
    if ev not in ("pull_request_review", "issue_comment", "check_run"):
        return out
    try:
        import fuel_chain
    except Exception:
        return out
    if not fuel_chain.stage_enabled("coderabbit"):
        return out

    repo = ""
    with contextlib.suppress(Exception):
        repo = str(_payload_repo(payload) or "").strip()
    if not repo:
        rep = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
        repo = str(rep.get("full_name") or "").strip()
    if not repo or not REPO_RE.fullmatch(repo):
        return out

    num = 0
    head = ""
    reviews: list = []
    comments: list = []
    checks: list = []

    if ev == "pull_request_review":
        # FR #7467: dismissed reviews must not stamp ready/light.
        action = str(payload.get("action") or "").strip().lower()
        if action == "dismissed":
            out["reason"] = "dismissed"
            print("INFO coderabbit stamp skip reason=dismissed", flush=True)
            return out
        review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
        pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
        try:
            num = int(pr.get("number") or 0)
        except (TypeError, ValueError):
            num = 0
        head = str(((pr.get("head") or {}) if isinstance(pr.get("head"), dict) else {}).get("sha") or "")
        head = head or str(review.get("commit_id") or "")
        if review:
            reviews = [review]
    elif ev == "issue_comment":
        if str(payload.get("action") or "").strip().lower() not in ("created", "edited"):
            return out
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        if not isinstance(issue.get("pull_request"), dict):
            return out
        try:
            num = int(issue.get("number") or 0)
        except (TypeError, ValueError):
            num = 0
        comment = payload.get("comment") if isinstance(payload.get("comment"), dict) else {}
        if comment:
            comments = [comment]
    elif ev == "check_run":
        cr = payload.get("check_run") if isinstance(payload.get("check_run"), dict) else {}
        name = str(cr.get("name") or "")
        if not fuel_chain.is_coderabbit_check_name(name):
            return out
        status = str(cr.get("status") or "").strip().lower()
        if status not in ("", "completed"):
            return out
        head = str(cr.get("head_sha") or "")
        prs = cr.get("pull_requests") if isinstance(cr.get("pull_requests"), list) else []
        if prs and isinstance(prs[0], dict):
            try:
                num = int(prs[0].get("number") or 0)
            except (TypeError, ValueError):
                num = 0
        checks = [cr]

    if num <= 0:
        return out
    ident = f"#{num}"
    out["repo"] = repo
    out["id"] = ident

    state = fuel_chain.coderabbit_state_from_surfaces(
        reviews=reviews, checks=checks, comments=comments, head_sha=head
    )
    stamp = ""
    if state.get("skipped"):
        why = str(state.get("skip_why") or "skipped").strip() or "skipped"
        stamp = why if why.startswith("skipped") else f"skipped:{why}"
    elif state.get("failed"):
        stamp = "failed"
    elif state.get("ready"):
        stamp = "ready"
    else:
        return out

    import time as _time

    now_f = _time.time()
    stamped_any = False
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, ValueError):
                return out
            for bucket in ("unaccepted", "accepted"):
                rows = list(doc.get(bucket) or [])
                for idx, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("repo") or "") != repo:
                        continue
                    if _norm_row_id(row.get("id")) != _norm_row_id(ident):
                        continue
                    if _canon_task(row) != "MRB":
                        continue
                    if head:
                        row["head_sha"] = head
                        row["coderabbit_head_sha"] = head.lower()
                    row["coderabbit"] = stamp
                    row["coderabbit_reason"] = stamp if stamp != "ready" else "ready:webhook"
                    paths = row.get("changed_files") or row.get("files") or row.get("paths")
                    row["review"] = fuel_chain.review_mode_for(stamp, paths if isinstance(paths, (list, tuple)) else None)
                    if "coderabbit_wait_since" not in row:
                        row["coderabbit_wait_since"] = float(now_f)
                    rows[idx] = row
                    stamped_any = True
                doc[bucket] = rows
            if stamped_any:
                _write_queue(queue_path(home), doc)
    except Exception:
        return out
    if stamped_any:
        out["stamped"] = stamp
        out["reason"] = stamp
        with contextlib.suppress(Exception):
            _log_queue_purge(f"INFO coderabbit stamp={stamp} {repo}{ident} via={ev}")
    return out


def clear_needs_human_from_owner_issue_comment(
    home: Path, event: str, payload: dict
) -> bool:
    """FR #4711: clear needs_human when the repo owner comments after giveup_ts.

    Returns True when at least one queue row was cleared. Seat-shaped comments
    (GIVEUP/ACK/DONE/MRB board) never clear. Only ``issue_comment`` + ``created``.
    """
    ev = (event or "").strip().lower()
    if ev != "issue_comment":
        return False
    if not isinstance(payload, dict):
        return False
    action = str(payload.get("action") or "").strip().lower()
    if action != "created":
        return False
    comment = payload.get("comment") if isinstance(payload.get("comment"), dict) else None
    issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else None
    if not comment or not issue:
        return False
    if not comment_is_repo_owner(payload, comment):
        return False
    body = str(comment.get("body") or "")
    if comment_looks_like_seat_wire(body):
        return False
    repo = _payload_repo(payload)
    if not repo or not REPO_RE.fullmatch(repo):
        return False
    try:
        num = int(issue.get("number"))
    except (TypeError, ValueError):
        return False
    ident = f"#{num}"
    comment_ts = _parse_iso_ts(str(comment.get("created_at") or ""))
    cleared_any = False
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, ValueError):
                return False
            for row in list(doc.get("unaccepted") or []):
                if not isinstance(row, dict):
                    continue
                if str(row.get("repo") or "") != repo:
                    continue
                if _norm_row_id(row.get("id")) != _norm_row_id(ident):
                    continue
                if not row_needs_human(row, ""):
                    continue
                giveup_ts = _parse_iso_ts(str(row.get("giveup_ts") or ""))
                if giveup_ts is not None and comment_ts is not None and comment_ts <= giveup_ts:
                    continue
                row.pop("needs_human", None)
                row.pop("cli_exit_retry_used", None)
                row["giveup_count"] = 0
                row.pop("giveup_seats", None)
                row.pop("giveup_agent_kinds", None)
                row["hard_ceiling_count"] = 0
                row.pop("cooldown_until", None)
                # Keep giveup_ts as history; offer gates no longer use it once cleared.
                cleared_any = True
                print(
                    f"needs_human cleared {repo}#{num} by=owner-comment",
                    flush=True,
                )
            if cleared_any:
                try:
                    _write_queue(queue_path(home), doc)
                except OSError:
                    return False
    except (TimeoutError, OSError):
        return False
    return cleared_any


def row_awaits_mrb1(row: dict) -> bool:
    """Legacy FR #1363 offer gate - always False (operator 2026-10-04).

    ``needs-mrb1`` was an intake hallucination that stranded ungated work while
    open-issue counts climbed. Kept as a named helper so call sites/tests stay
    stable; label presence must not block ``!bored`` / ``!assign`` offers.
    """
    return False


def issue_blocks_repo_uat(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    state: str = "",
) -> bool:
    """True when an open issue must hold repo-level UAT back (t853u / FR #1416).

    ``needs-mrb1`` must not prevent repo UAT (#1416) and must not block offers
    (operator 2026-10-04: label is a hallucination). Kept as a non-blocking
    open-issue class for UAT clearance only.

    FR #1682 / #1684: skill / harvest: / skill: receipts are offerable
    promote jobs but must not hold repo UAT (honesty-box backlog is not product work).

    FR #2971: ``feature-request`` (incl. via-intake product FRs) always blocks UAT.
    Do not treat a prose title that merely starts with the word ``Harvest`` /
    ``Skill`` as a harvest receipt - require ``harvest:`` / ``skill:`` (colon) or
    the ``skill`` label. Live miss: #2970 title ``Harvest re-promotes…`` left the
    repo "clear" and UAT #0 was offered.
    """
    if issue_skip_fr_reason(title=title, body=body, labels=labels, state=state):
        return False
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    if "needs-mrb1" in labs:
        return False
    # Ordinary product FRs - including via-intake - block UAT even if the title
    # starts with the word Harvest/Skill (FR #2971).
    if "feature-request" in labs:
        return True
    if "skill" in labs:
        return False
    title_s = (title or "").strip()
    # Receipt titles only: "harvest: …" / "skill: …", not "Harvest re-promotes…".
    if re.match(r"(?i)^(harvest|skill)\s*:", title_s):
        return False
    if HARVEST_TITLE_RE.match(title_s) and "via-intake" not in labs:
        return False
    return True


# FR #587: machine-affinity for seats that cannot do the work (WP0 live / chair-outbox).
# FR #628 / #732: also accept bare ``machine:<id>`` (legacy pin label).
_REQUIRE_MACHINE_LABEL_RE = re.compile(
    r"(?i)^(?:needs|require[_-]?machine|machine)[-_:=]([a-z0-9][a-z0-9_.-]*)$"
)
# Tokens that match needs-<x> but are human/process gates, not fleet machine ids.
# needs-mrb1 was wrongly stamped require_machine=mrb1 and stranded the offer queue (#1080).
_REQUIRE_MACHINE_NON_MACHINE = frozenset(
    {
        "mrb1",
        "mrb",
        "human",
        "vision",
        "blocked",
        "release",
        "release-gate",
        "gate",
    }
)
# FR #8653 / #9680: Ergo and the Jeeves chair host used to be ionos, then walrus.
# Never bake the live hostname into source - resolve from BOB_CHAIR_MACHINE
# (bob_recycle.CHAIR_ENV) or JEEVES_CHAIR_HOST (jeeves_chair_host). Legacy
# labels/cues ``needs-walrus`` / ``needs-ionos`` / ``require_machine: walrus|ionos``
# remain aliases that fold onto the configured live host.
_LEGACY_CHAIR_HOST_ALIASES = frozenset({"ionos", "bob-ionos", "walrus"})


def live_chair_host() -> str:
    """Resolved Ergo / Jeeves chair machine id (FR #9680).

    Prefer ``BOB_CHAIR_MACHINE``, then ``JEEVES_CHAIR_HOST``, then
    ``jeeves_chair_host.DEFAULT_CHAIR_HOST``. Tests inject via monkeypatch.
    """
    import bob_recycle
    import jeeves_chair_host as jch

    raw = (os.environ.get(bob_recycle.CHAIR_ENV) or "").strip()
    if raw:
        return bobreport.normalize_machine_id(raw) or jch.normalize_host(raw)
    return jch.configured_chair_host()


def fold_chair_host(mid: str) -> str:
    """Map a retired/alias chair-host id onto the configured live chair.

    Other fleet machine ids stay put. Legacy ``ionos`` / ``walrus`` always fold
    to ``live_chair_host()`` so a future chair rename only needs env/config.
    """
    m = (mid or "").strip().lower()
    if not m:
        return m
    live = live_chair_host()
    if m == live:
        return live
    if m in _LEGACY_CHAIR_HOST_ALIASES:
        return live
    return m


# Explicit cue -> fleet machine id (normalized lowercase).
# FR #1508: title/label cues vs body cues. Bare machine names / require_machine=
# in an issue body often appear as evidence about *other* pins and must not
# re-pin the filing itself (#1507 class).
# FR #1824 / #1843: a *dedicated body line* ``require_machine: ionos`` (or ``=``)
# is an intentional pin - honor it. Inline evidence prose still must not pin.
_REQUIRE_MACHINE_TITLE_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    # FR #6407: ce-priority-dev1 title cues retired (seat gone; Si 2026-11-10).
    (re.compile(r"(?i)\brequire_machine\s*=\s*(?:ionos|walrus)\b"), "walrus"),
    # FR #5030 / #4422-class: "without/missing require_machine=redqueen" offer-gap
    # meta titles must not self-pin the filing to redqueen.
    (re.compile(
        r"(?i)(?<!without\s)(?<!missing\s)\brequire_machine\s*=\s*redqueen\b"
    ), "redqueen"),
    # FR #4422: "missing needs-ionos stamp" meta-FRs must not self-pin to ionos.
    (re.compile(r"(?i)(?<!missing\s)\bneeds-(?:ionos|walrus)\b"), "walrus"),
    (re.compile(r"(?i)(?<!missing\s)(?<!without\s)\bneeds-redqueen\b"), "redqueen"),
    # FR #5030: a-search hasresults monitor / redeploy titles (not bare "redqueen")
    (re.compile(r"(?i)\ba-hasresults-monitor\b"), "redqueen"),
    (re.compile(r"(?i)\bRegister-HasresultsMonitorService\b"), "redqueen"),
    (re.compile(r"(?i)\bchair[- ]outbox\b"), "walrus"),
    # FR #1550: monitor idle+ungated / ircJeeves StartPending filings are chair-host ops
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,60}\bstartpending\b"), "walrus"),
    (re.compile(r"(?i)\bstartpending\b.{0,60}\b(?:irc)?jeeves\b"), "walrus"),
    (re.compile(r"(?i)\bidle seats?\b.{0,120}\bungated offerable\b"), "walrus"),
    (re.compile(r"(?i)\bungated offerable\b.{0,120}\bidle seats?\b"), "walrus"),
    # FR #1899: title-level intake/BobCallback 502 ops filings
    (re.compile(r"(?i)\bintake\b.{0,40}\b(?:BobCallback|ARR)\b.{0,40}\b502\b"), "walrus"),
    (re.compile(r"(?i)\b(?:BobCallback|ARR)\b.{0,40}\bintake\b.{0,40}\b502\b"), "walrus"),
    (re.compile(r"(?i)\bintake\b.{0,60}\b502\b.{0,40}\b(?:Bad Gateway|harvest)"), "walrus"),
    # FR #2451: release pack titles that say install/smoke on ionos
    (re.compile(r"(?i)\binstall(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos\b"), "walrus"),
    # FR #3129: Sync/compose ircJeeves on ionos (allowlist / intake 403 class of #3122)
    (re.compile(r"(?i)\bionos\b.{0,80}\b(?:sync(?:/compose)?|compose)\b.{0,80}\b(?:irc)?jeeves\b"), "walrus"),
    (re.compile(r"(?i)\b(?:sync(?:/compose)?|compose)\b.{0,80}\b(?:irc)?jeeves\b.{0,40}\bionos\b"), "walrus"),
    (re.compile(r"(?i)\bSync-BobiverseFromRepo\b.{0,80}\b(?:irc)?jeeves\b"), "walrus"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,80}\bSync-BobiverseFromRepo\b"), "walrus"),
    # FR #4343: ionos !build / Jeeves install lag / hotpatch|ff-update of chair install tree
    # Note: !build has no word-boundary before '!' (punctuation); do not use \b!build.
    (re.compile(r"(?i)\bionos\b.{0,100}!build\b"), "walrus"),
    (re.compile(r"(?i)!build\b.{0,100}\bionos\b"), "walrus"),
    (re.compile(r"(?i)\bionos\b.{0,80}\b(?:irc)?jeeves\b.{0,80}\binstall\b"), "walrus"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,60}\binstall\b.{0,80}\blags?\s+main\b"), "walrus"),
    (re.compile(r"(?i)\b(?:hotpatch|ff-update|ff[- ]only)\b.{0,120}\b(?:ionos\s+)?(?:irc)?jeeves\b.{0,80}\binstall\b"), "walrus"),
)
# FR #9679: bobiverse-only chair-host title/body cues that still pin after FR #9637.
# Does NOT restore bare ``require_machine: walrus`` body paste (idle starve). Prefer
# GitHub ``needs-walrus`` labels; these catch CAST IRON walrus-action children filed
# with a ``chair-host:`` title / Ergo / BOB_CHAIR_MACHINE stamp and no label yet.
_REQUIRE_MACHINE_BOBIVERSE_CHAIR_HOST_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)^chair-host\s*:"), "walrus"),
    (re.compile(r"(?i)\bchair-host\s*:\s*install\b"), "walrus"),
    (re.compile(r"(?i)\bErgo(?:/|\s+)chair\b.{0,60}\b(?:server|host|install|heal|from\s+config)\b"), "walrus"),
    (re.compile(r"(?i)\b(?:server|host)\s+from\s+config\b.{0,80}\bBOB_CHAIR_MACHINE\b"), "walrus"),
    (re.compile(r"(?i)\bBOB_CHAIR_MACHINE\b.{0,80}\b(?:chair|Ergo|needs-walrus)\b"), "walrus"),
    (re.compile(r"(?i)\bneeds-walrus\s+alias\b"), "walrus"),
)

# FR #1824 / #4512: dedicated pin lines (MULTILINE). Kept for _body_for_queue preserve
# and non-bobiverse helpers. FR #9637: bobiverse infer_require_machine ignores these
# (labels / hard pins / !pin only) so monitor body paste cannot starve idle seats.
_REQUIRE_MACHINE_DEDICATED_PIN_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*(?:ionos|walrus)\b"), "walrus"),
    # FR #6407: dedicated ce-priority-dev1 / ce-priority-dev pin lines retired.
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*flamingo\b"), "flamingo"),
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*marchhare\b"), "marchhare"),
    # FR #5030: dedicated body pin (was missing; body line alone did not stamp)
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*redqueen\b"), "redqueen"),
)
_REQUIRE_MACHINE_BODY_SOFT_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    # FR #6407: WP0 / AllowedComputer / PRIORITY_WP0_INSTANCE DEV1 soft cues retired.
    # FR #852: recycle/recompose live ircJeeves / prune chair queue on ionos
    (re.compile(r"(?i)\b(?:recycle|recompose)\b.{0,60}\b(?:irc)?jeeves\b"), "walrus"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,60}\b(?:recycle|recompose|recycled)\b"), "walrus"),
    # FR #3129: Sync/compose (or Sync-BobiverseFromRepo) ircJeeves on ionos.
    # Do not bare-match Sync-BobiverseFromRepo alone (bob/airc Sync on any fleet box).
    (re.compile(r"(?i)\b(?:sync(?:/compose)?|compose)\b.{0,80}\b(?:irc)?jeeves\b"), "walrus"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,80}\b(?:sync(?:/compose)?|compose)\b"), "walrus"),
    (re.compile(r"(?i)\bSync-BobiverseFromRepo\b.{0,80}\b(?:irc)?jeeves\b"), "walrus"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,80}\bSync-BobiverseFromRepo\b"), "walrus"),
    (re.compile(r"(?i)\bOn\s+ionos\s*:\s*Sync-BobiverseFromRepo\b"), "walrus"),
    (re.compile(r"(?i)\bprune\b.{0,80}\bqueue\.json\b"), "walrus"),
    (re.compile(r"(?i)\bqueue\.json\b.{0,80}\b(?:prune|on\s+ionos)\b"), "walrus"),
    # FR #1363: BobCallback principal / SYSTEM vs Admin .bobiverse lives on the chair host
    (re.compile(r"(?i)\bBobCallback\b.{0,120}\bSYSTEM\b"), "walrus"),
    (re.compile(r"(?i)\bSYSTEM\b.{0,120}\bBobCallback\b"), "walrus"),
    (re.compile(r"(?i)\bBobCallback\b.{0,160}\.bobiverse\b"), "walrus"),
    (re.compile(r"(?i)\bBobCallback\b.{0,80}\bprincipal\b"), "walrus"),
    # FR #1550 / #1559: monitor check evidence / missing shop OFFER after StartPending.
    # Bare Invoke-JeevesMonitorCheck alone is too broad (docs/skills); require ops context.
    (re.compile(
        r"(?i)\bInvoke-JeevesMonitorCheck\b.{0,200}\b(?:idle_seats|StartPending|offerable|no shop OFFER)\b"
    ), "walrus"),
    (re.compile(
        r"(?i)\b(?:idle_seats|StartPending|offerable|no shop OFFER)\b.{0,200}\bInvoke-JeevesMonitorCheck\b"
    ), "walrus"),
    (re.compile(r"(?i)\bno shop OFFER\b"), "walrus"),
    (re.compile(r"(?i)\bchair[- ]outbox\b.{0,100}\b(?:OFFER|!bored|GIT announce)"), "walrus"),
    # FR #1899: intake/ARR/BobCallback 502 ops live on the Ergo/chair host (not flamingo)
    (re.compile(r"(?i)\b(?:intake|/bob/v1/intake)\b.{0,140}\b(?:502|Bad Gateway)\b"), "walrus"),
    (re.compile(r"(?i)\b(?:502|Bad Gateway)\b.{0,140}\b(?:intake|/bob/v1/intake|BobCallback|harvest-outbox)\b"), "walrus"),
    # FR #3610: outage/ops wording only - bare :7700 or LISTEN in design prose
    # (e.g. Hours webhook FR #3450 "BobCallback (default 127.0.0.1:7700)") must not pin.
    (re.compile(
        r"(?i)\bBobCallback\b.{0,160}\b(?:502|Bad Gateway|DOWN|not[- ]listening|no LISTEN|restart|recycle)\b"
    ), "walrus"),
    (re.compile(
        r"(?i)\b(?:502|Bad Gateway|DOWN|not[- ]listening|no LISTEN|restart|recycle)\b.{0,160}\bBobCallback\b"
    ), "walrus"),
    (re.compile(r"(?i)\b(?:ARR|reverse[- ]proxy)\b.{0,140}\b(?:intake|BobCallback|/bob/v1)\b"), "walrus"),
    (re.compile(r"(?i)\b(?:intake|BobCallback|/bob/v1)\b.{0,140}\b(?:ARR|reverse[- ]proxy)\b"), "walrus"),
    (re.compile(r"(?i)\bharvest-outbox\b.{0,100}\b(?:502|Bad Gateway|KEPT)\b"), "walrus"),
    # FR #2451: release pack FRs that install/smoke on ionos (not bare release-out)
    (re.compile(r"(?i)\binstall(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos\b"), "walrus"),
    (re.compile(r"(?i)\bsmoke\s+on\s+ionos\b"), "walrus"),
    # FR #2512: Pack-Airc / Pack-BobiverseRelease -Product airc near Assert or ionos install/smoke
    (re.compile(
        r"(?i)\bPack-Airc\b.{0,220}\b(?:Assert-ReleaseAssets|install(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos)\b"
    ), "walrus"),
    (re.compile(
        r"(?i)\bPack-BobiverseRelease\b.{0,160}\b-Product\s+airc\b.{0,160}\b(?:Assert-ReleaseAssets|install(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos)\b"
    ), "walrus"),
    # FR #4343: hotpatch / ff-update of the ionos Jeeves install tree (chair host only)
    (re.compile(r"(?i)\b(?:hotpatch|ff-update|ff[- ]only)\b.{0,160}\bionos\s+(?:irc)?jeeves\s+install\b"), "walrus"),
    (re.compile(r"(?i)\bionos\s+(?:irc)?jeeves\s+install(?:\s+tree)?\b.{0,120}\b(?:hotpatch|ff-update)\b"), "walrus"),
    (re.compile(r"(?i)\bC:\\ai\\jeeves\\scripts\\run_bobiverse_build\.py\b"), "walrus"),
    (re.compile(r"(?i)\b(?:hotpatch|ff-update)\b.{0,120}\bC:\\ai\\jeeves\b"), "walrus"),
    # FR #5030: a-search redeploy / monitor / CloudWatch / SQL-log ops on redqueen
    # (do not bare-match "redqueen" alone --- host layout docs must stay unpinned).
    (re.compile(r"(?i)\ba-hasresults-monitor\b"), "redqueen"),
    (re.compile(r"(?i)\bRegister-HasresultsMonitorService\b"), "redqueen"),
    (re.compile(
        r"(?i)\bredeploy\b.{0,160}\b(?:live\s+workers?|walrus)\b.{0,160}\ba-search\b"
    ), "redqueen"),
    (re.compile(
        r"(?i)\ba-search\b.{0,160}\bredeploy\b.{0,160}\b(?:live\s+workers?|walrus)\b"
    ), "redqueen"),
    (re.compile(
        r"(?i)\bFilterLogEvents\b.{0,160}\b(?:a-search|provider-\w+-live|a-sqlsearch|walrus)\b"
    ), "redqueen"),
    (re.compile(
        r"(?i)\b(?:a-search|provider-\w+-live|a-sqlsearch|walrus)\b.{0,160}\bFilterLogEvents\b"
    ), "redqueen"),
    (re.compile(
        r"(?i)\b(?:a-sqlsearch|walrus)\b.{0,80}\b(?:drain\s+)?logs?\b"
    ), "redqueen"),
)
_REQUIRE_MACHINE_BODY_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    _REQUIRE_MACHINE_DEDICATED_PIN_CUES + _REQUIRE_MACHINE_BODY_SOFT_CUES
)
# Back-compat for tests importing the combined name.
_REQUIRE_MACHINE_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    _REQUIRE_MACHINE_TITLE_CUES + _REQUIRE_MACHINE_BODY_CUES
)

# FR #4512: Simon - bobiverse work is not reliant on ionos; text cues never pin this repo.
_BOBIVERSE_REPO_L = "simonbarnett/bobiverse"

# Hard pins for known WP0 / machine-gated issues (FR #1093): survive empty title/body on stale rows.
_REQUIRE_MACHINE_ISSUE_PINS: dict[tuple[str, str], str] = {
    # FR #6407: agentic_fomprep#56 and ce-priority#16 DEV1 hard pins retired.
    # FR #2312 / #1714: ionos orphan workers-map / nak-busy - body pin is past the
    # historic body[:500] truncate window; hard pin so marchhare never gets the offer.
    ("simonbarnett/bobiverse", "#1714"): "walrus",
    # FR #2512 / #2511: airc MSI re-pack + install/smoke on ionos (mis-offered to marchhare
    # while frozen jeeves lagged #2451 cues). Hard pin survives empty/stale queue body.
    ("simonbarnett/bobiverse", "#2511"): "walrus",
    # FR #2525 / #2522: maintenance butler FR pin past truncate + backtick line.
    ("simonbarnett/bobiverse", "#2522"): "walrus",
    # FR #3129 / #3122: ionos Sync/compose ircJeeves for intake allowlist (mis-offered to marchhare).
    ("simonbarnett/bobiverse", "#3122"): "walrus",
    # FR #5030 / a-search#5221: hasresults redeploy + monitor + CloudWatch + SQL logs
    # (mis-offered to flamingo; soft cues + dedicated redqueen pin land in same FR).
    ("simonbarnett/a-search", "#5221"): "redqueen",
    # FR #6229 / #6144: live MarchHare source->digest->tray gate (mis-offered to redqueen
    # while covering merges already on main; bobiverse soft cues never pin per FR #4512).
    ("simonbarnett/bobiverse", "#6144"): "marchhare",
    # FR #9543 / #9526: host-heal TipForm on marchhare - body pin added after enqueue;
    # hard pin until living residual closes (issues.edited refresh is the durable path).
    ("simonbarnett/bobiverse", "#9526"): "marchhare",
    # FR #4599: do NOT hard-pin bobiverse #4340 to ionos (Simon: bobiverse work never
    # pinned to ionos). See _REQUIRE_MACHINE_ISSUE_UNPINS.
}

# FR #4427: ce-priority Day Works living/umbrella FRs and UAT need CE-PRIORITY-DEV1
# (CredMan / instances.json). Repo-gated so bobiverse chair filings about the pin
# do not re-pin themselves.
# FR #4745: do NOT match bare ``dayworks`` / ``WP3`` / ``WP4`` alone --- parked
# spec FRs and harvest-lesson tips that only mention those words were stranded
# on offline DEV1. Keep living/umbrella + Gates C-G (live gate work).
_CE_PRIORITY_DAYWORKS_REPOS = frozenset(
    {
        "simonbarnett/ce-priority",
        "simonbarnett/ce-dayworks",
    }
)
_CE_PRIORITY_DAYWORKS_TASK_RE = re.compile(
    r"(?i)\bliving\s+(?:fr|umbrella)\b|\btracking\s+umbrella\b"
    # Live gate range C-G only (not "Gates D-G" listed as out-of-scope on parked specs).
    r"|\bGates?\s*C\s*-\s*G\b"
    r"|\bGate\s+[C-G]\b"
)

# FR #4422: hard unpins - survive title/body cues that wrongly re-pin (bobiverse must
# not be stranded on ionos for meta "missing needs-ionos" filings).
# FR #4427: chair meta filing title contains require_machine=ce-priority-dev1 as evidence.
# FR #4599: #4340 descriptive "ionos !build ..." title must stay offerable to any seat
# (hard unpin wins over sticky stamp + soft cues; same class as #4343 / #4512).
_REQUIRE_MACHINE_ISSUE_UNPINS: set[tuple[str, str]] = {
    ("simonbarnett/bobiverse", "#4343"),
    ("simonbarnett/bobiverse", "#4340"),
    ("simonbarnett/bobiverse", "#4427"),
}

# FR #6407: CE-PRIORITY-DEV1 seat retired; never stamp/infer this machine again.
_RETIRED_REQUIRE_MACHINES: frozenset[str] = frozenset(
    {"ce-priority-dev1", "ce-priority-dev", "dev1"}
)


def _is_operator_require_machine(row: dict) -> bool:
    """FR #6592: True when !pin/!unpin stamped require_machine_operator on the row."""
    v = row.get("require_machine_operator")
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_retired_require_machine(mid: str) -> bool:
    """True when mid is the retired CE-PRIORITY-DEV1 seat (FR #6407)."""
    raw = str(mid or "").strip().lower()
    if not raw:
        return False
    if raw in _RETIRED_REQUIRE_MACHINES:
        return True
    try:
        folded = bobreport.fold_machine_id(bobreport.normalize_machine_id(raw) or raw)
    except Exception:
        folded = raw
    return bool(folded) and folded in _RETIRED_REQUIRE_MACHINES


def _rewrite_retired_require_machine_rows(doc: dict) -> int:
    """Rewrite stamped ce-priority-dev1 -> any on load/resync (FR #6407). Returns count."""
    n = 0
    for bucket in ("unaccepted", "accepted"):
        for row in doc.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            stamped = str(row.get("require_machine") or "").strip().lower()
            if not stamped or stamped in {"*", "any", "none", "-"}:
                continue
            if _is_retired_require_machine(stamped):
                row["require_machine"] = "any"
                n += 1
    return n


# FR #2480 / #2471 / #2472: agentic_fomprep evergreen umbrella / MRB-home boards.
# Labels mrb-home/umbrella/parent-fr should SKIP_FR (#271), but stale queue rows
# enqueued before labels (or when API label payloads were empty) kept being offered.
# Hard-pin by (repo, #N) so resync/offer always prune.
# FR #2562 / #2677: reverse #2521 - re-pin #11 (MRB FAIL verdict board). Remediation
# belongs on child FRs (#9/#10), never on the verdict board itself.
# FR #6027: living WCF/tabula live proof (#6026) has no fleet host and no WSDL yet.
# Hard-hold so !bored cannot offer it to flamingo (or any shop) until a human
# captures the Priority WCF contract and unpins. Not an umbrella SKIP_FR.
_NEEDS_HUMAN_ISSUE_PINS: set[tuple[str, str]] = {
    ("simonbarnett/bobiverse", "#6026"),
}

_SKIP_FR_ISSUE_PINS: set[tuple[str, str]] = {
    ("simonbarnett/priority-mcp", "#3"),
    ("simonbarnett/priority-mcp", "#7"),
    ("simonbarnett/priority-mcp", "#8"),
    ("simonbarnett/priority-mcp", "#9"),
    ("simonbarnett/priority-mcp", "#11"),
    ("simonbarnett/priority-mcp", "#20"),
}

# Exact board phrase used by fomprep MRB-home intake issues (body). Title-only
# evergreen regex (#987) deliberately ignores body "MRB home" prose; this phrase
# is the parked-board signature and is safe to skip.
_MRB_HOME_BOARD_BODY_RE = re.compile(
    r"(?i)This issue is the MRB home for (?:that|this) feature request"
)

# Queue rows keep a short body for size; trailing dedicated require_machine pins must
# survive (FR #2312 - #1714 pin sat after char 500 and was dropped on enqueue).
QUEUE_BODY_LIMIT = 500
_REQUIRE_MACHINE_PIN_LINE_RE = re.compile(
    # FR #2525: allow markdown wrappers + trailing notes, e.g.
    # `` `require_machine: ionos` (hotpatch verify) ``
    r"(?im)^[ \t]*[`*]*require_machine\s*[:=]\s*([a-z0-9][a-z0-9_.-]*)\b[`*]*"
)


def _body_for_queue(body: str, *, limit: int | None = None) -> str:
    """Store issue/PR body for queue rows without dropping require_machine pin lines.

    FR #8619: when truncating a self-review-deadlock stall body, keep a compact
    `stall_idle: nick1, nick2` pin so offer/assign still blocks idle authors
    after QUEUE_BODY_LIMIT cuts the Evidence JSON.

    BOB-G3 / FR #9108: also preserve a ``Kind: digest|fr-digest`` line so Digest
    recognition survives the 500-char window (label remains the primary signal).
    """
    text = str(body or "")
    lim = QUEUE_BODY_LIMIT if limit is None else int(limit)
    if lim < 1:
        lim = QUEUE_BODY_LIMIT
    if len(text) <= lim:
        return text
    pins: list[str] = []
    for m in _REQUIRE_MACHINE_PIN_LINE_RE.finditer(text):
        mid = (m.group(1) or "").strip().lower()
        if not mid:
            continue
        line = f"require_machine: {mid}"
        if line not in pins:
            pins.append(line)
    for m in DIGEST_KIND_BODY_RE.finditer(text):
        kind = (m.group(1) or "").strip().lower()
        if not kind:
            continue
        line = f"Kind: {kind}"
        if line not in pins:
            pins.append(line)
    if "self-review-deadlock" in text:
        m_idle = re.search(r'"idle"\s*:\s*\[(.*?)\]', text, re.S)
        if m_idle:
            nicks = re.findall(r'"([^"]+)"', m_idle.group(1))
            if nicks:
                pin = "stall_idle: " + ", ".join(nicks)
                if pin not in pins:
                    pins.append(pin)
    head = text[:lim].rstrip()
    if not pins:
        return head
    # Prefer pins that are not already intact inside the head window.
    missing = [p for p in pins if p not in head]
    if not missing:
        return head
    return head + "\n" + "\n".join(missing)


def infer_require_machine(
    *,
    title: str = "",
    body: str = "",
    labels=(),
    line: str = "",
    repo: str = "",
    ident: str = "",
) -> str:
    """Return a fleet machine id the job must run on, or '' (FR #587).

    Labels ``needs-<machine>`` / ``require_machine:<machine>`` win first, then
    title/body/line cues (dedicated body ``require_machine:``/``=`` pin lines; needs-ionos / chair-outbox /
    recycle|recompose|Sync/compose Jeeves / Sync-BobiverseFromRepo near Jeeves / prune queue.json / install(+smoke) on ionos -> ionos;
    FR #5030 a-hasresults-monitor / redeploy live workers|walrus / FilterLogEvents near a-search -> redqueen;
    FR #6229 hard-pin bobiverse#6144 -> marchhare (live MarchHare E2E);
    FR #587 / #852 / #2451 / #3129 / #4427 / #5030 / #6229).

    FR #4512 / #9637: for ``SimonBarnett/bobiverse``, soft title/body text cues and
    dedicated ``require_machine:`` body lines do not pin (monitor paste starved idle
    seats). Only ``needs-<machine>`` / ``require_machine:<machine>`` labels, hard
    issue pins/unpins, operator ``!pin``, and FR #9679 narrow chair-host cues
    (``chair-host:`` / Ergo+BOB_CHAIR_MACHINE / needs-walrus alias).
    """
    labs = labels or ()
    if isinstance(labs, str):
        labs = [labs]
    repo_l = str(repo or "").strip().lower()
    id_l = str(ident or "").strip()
    if id_l and not id_l.startswith("#"):
        id_l = f"#{id_l}"
    if (repo_l, id_l) in _REQUIRE_MACHINE_ISSUE_UNPINS:
        return ""
    pin = _REQUIRE_MACHINE_ISSUE_PINS.get((repo_l, id_l))
    if pin:
        if _is_retired_require_machine(pin):
            return ""
        return pin
    for lab in labs:
        s = str(lab or "").strip()
        m = _REQUIRE_MACHINE_LABEL_RE.match(s)
        if m:
            mid = bobreport.normalize_machine_id(m.group(1)) or m.group(1).strip().lower()
            if mid and mid not in _REQUIRE_MACHINE_NON_MACHINE:
                if _is_retired_require_machine(mid):
                    return ""
                return fold_chair_host(mid)
        # bare needs-ionos style already covered by cue regex below via label join
    body_blob = str(body or "")
    title_blob = "\n".join(
        [
            str(title or ""),
            str(line or ""),
            " ".join(str(x) for x in labs),
        ]
    )
    # FR #4512 / #9637: bobiverse - no soft/dedicated paste pins; FR #9679 chair-host ok.
    if repo_l == _BOBIVERSE_REPO_L:
        for rx, mid in _REQUIRE_MACHINE_BOBIVERSE_CHAIR_HOST_CUES:
            blob = title_blob + "\n" + body_blob
            if rx.search(blob):
                if _is_retired_require_machine(mid):
                    return ""
                return fold_chair_host(mid)
        return ""
    # Title + labels + assign line: bare machine / require_machine= cues (FR #1508).
    for rx, mid in _REQUIRE_MACHINE_TITLE_CUES:
        if rx.search(title_blob):
            if _is_retired_require_machine(mid):
                return ""
            # FR #9680: cue maps may still name legacy aliases (walrus/ionos);
            # stamp the configured live chair host.
            return fold_chair_host(mid)
    # Body: only strong WP0 / ionos-ops cues (not bare machine name mentions).
    for rx, mid in _REQUIRE_MACHINE_BODY_CUES:
        if rx.search(body_blob) or rx.search(title_blob):
            if _is_retired_require_machine(mid):
                return ""
            return fold_chair_host(mid)
    # FR #4745: harvest-lesson / lesson(<book>) tips never inherit Day Works / UAT
    # auto-pin (docs/skill-only MRB). Explicit needs-<machine> labels and dedicated
    # require_machine lines already returned above.
    if is_harvest_lesson_pr(title=str(title or ""), labels=labs):
        return ""
    # FR #6407: Day Works / UAT auto-pin to ce-priority-dev1 retired (seat gone).
    # Keep the repo/task helpers for docs and older tests that import them.
    if repo_l in _CE_PRIORITY_DAYWORKS_REPOS:
        pass
    return ""


def row_require_machine(row: dict) -> str:
    """Machine id required for this queue row, if any (FR #587 / #1093)."""
    repo_l = str(row.get("repo") or "").strip().lower()
    id_l = f"#{str(row.get('id') or '').strip().lstrip('#')}"
    # FR #4422 hard unpin before hard pins / stamped machine.
    if (repo_l, id_l) in _REQUIRE_MACHINE_ISSUE_UNPINS:
        return ""
    labels = row.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    label_tuple = tuple(str(x) for x in labels)
    # Hard issue pins + needs-<machine> labels win over unpin tokens (any/none).
    # FR #1093: hard pin must not leak after monitor any-clear.
    # FR #9664: label needs-walrus must still gate offer when !unpin left rm=any
    # (else non-walrus seats ACK then GIVEUP require_machine=walrus in a loop).
    hard_or_label = infer_require_machine(
        title="",
        body="",
        labels=label_tuple,
        line="",
        repo=str(row.get("repo") or ""),
        ident=str(row.get("id") or ""),
    )
    if hard_or_label:
        return hard_or_label
    stamped = str(row.get("require_machine") or "").strip().lower()
    # Operator/monitor unpin: "*" / "any" / "none" means do not re-infer from title/body
    # (titles that mention require_machine=ce-priority-dev1 were re-pinning forever).
    # Labels already applied above (FR #9664).
    if stamped in {"*", "any", "none", "-"}:
        return ""
    if stamped and _is_retired_require_machine(stamped):
        return ""
    # FR #4512: bobiverse never trusts a persisted text-cue stamp - re-infer
    # (labels / dedicated pin / hard pin only). Stale ionos stamps clear.
    # FR #4745: harvest-lesson rows re-infer too (sticky Day Works DEV1 must not stick).
    # FR #6592: operator !pin/!unpin stamps (require_machine_operator) survive re-infer.
    title_s = str(row.get("title") or "")
    if repo_l == _BOBIVERSE_REPO_L or is_harvest_lesson_pr(title=title_s, labels=labels):
        if _is_operator_require_machine(row):
            if stamped in {"*", "any", "none", "-"}:
                return ""
            if stamped:
                mid = bobreport.normalize_machine_id(stamped) or stamped
                if mid and mid not in _REQUIRE_MACHINE_NON_MACHINE and not _is_retired_require_machine(mid):
                    return mid
        return infer_require_machine(
            title=title_s,
            body=str(row.get("body") or ""),
            labels=label_tuple,
            line=str(row.get("line") or ""),
            repo=str(row.get("repo") or ""),
            ident=str(row.get("id") or ""),
        )
    if stamped:
        mid = bobreport.normalize_machine_id(stamped) or stamped
        # Ignore corrupt stamps like mrb1 from needs-mrb1 (#1080).
        if mid and mid not in _REQUIRE_MACHINE_NON_MACHINE:
            return mid
    return infer_require_machine(
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        labels=label_tuple,
        line=str(row.get("line") or ""),
        repo=str(row.get("repo") or ""),
        ident=str(row.get("id") or ""),
    )


def seat_matches_require_machine(nick: str, required: str) -> bool:
    """True when nick's machine matches ``required`` (or required is empty)."""
    req = (required or "").strip().lower()
    if not req:
        return True
    req = fold_chair_host(req)
    req_mid = bobreport.fold_machine_id(bobreport.normalize_machine_id(req) or req)
    # FR #8768: use _seat_machine_id so cold digest / missing roster still parses
    # canonical ``<machine>-<pid>`` nicks (parse_seat_nick alone returns None).
    seat_mid = _seat_machine_id(nick)
    if not seat_mid:
        return False
    # FR #8697: fold legacy chair-host seat ids (ionos) before DIGEST_ID_FOLD so
    # ionos-<pid> seats match walrus pins after the #8653 cutover.
    seat_mid = bobreport.fold_machine_id(fold_chair_host(seat_mid))
    return bool(seat_mid) and seat_mid == req_mid


_REQUIRE_MACHINE_GIVEUP_RE = re.compile(
    r"(?i)\brequire_machine\s*=\s*([a-z0-9][a-z0-9_.-]*)\b"
)


def parse_require_machine_giveup_reason(reason: str) -> str:
    """FR #8768: machine id from a honor-path GIVEUP reason, or ''."""
    m = _REQUIRE_MACHINE_GIVEUP_RE.search(str(reason or ""))
    if not m:
        return ""
    mid = fold_chair_host((m.group(1) or "").strip().lower())
    mid = bobreport.fold_machine_id(bobreport.normalize_machine_id(mid) or mid)
    if not mid or mid in _REQUIRE_MACHINE_NON_MACHINE or _is_retired_require_machine(mid):
        return ""
    return mid


def apply_require_machine_giveup_stamp(row: dict, reason: str) -> str:
    """FR #8768: stamp require_machine from GIVEUP reason so wrong shops stay gated.

    Returns the stamped machine id, or '' when the reason is not a machine pin.
    Operator flag survives bobiverse FR #4512 re-infer (same as ops !pin).
    """
    if not isinstance(row, dict):
        return ""
    mid = parse_require_machine_giveup_reason(reason)
    if not mid:
        return ""
    row["require_machine"] = mid
    row["require_machine_operator"] = True
    return mid


# FR #9554 bob_host_heal_tipform_auto_pin: tipform / tray-not-logged-in / engine.alive
# host-heal GIVEUP churn must pin require_machine (not needs_human) after >=2 outcomes.
_HOST_HEAL_TIPFORM_REASON_RE = re.compile(
    r"(?i)\b(?:tipform|tray-not-logged-in|tray not logged|nobody logged in with"
    r"|bob tray running|engine\.alive|host-heal|host heal|start-bobfleetray"
    r"|start-bobtray|interactive tipform|reload/?restart engine)\b"
)
_HOST_HEAL_TIPFORM_ROW_RE = re.compile(
    r"(?i)\b(?:tipform|tray-not-logged-in|nobody logged in with the bob tray"
    r"|engine\.alive|host tray|host-heal|start-bobfleetray|start-bobtray"
    r"|interactive tipform|bob-tray / ear|workers=0)\b"
)
_HOST_HEAL_FLEET_MACHINES = frozenset(
    {"marchhare", "flamingo", "redqueen", "walrus", "ionos"}
)
_HOST_HEAL_TITLE_MACHINE_RE = re.compile(
    r"(?im)^\s*([a-z0-9][a-z0-9_.-]*)\s*:"
)
_HOST_HEAL_HOST_LINE_RE = re.compile(
    r"(?im)^\s*Host\s*:\s*([a-z0-9][a-z0-9_.-]*)\b"
)


def is_host_heal_tipform_reason(reason: str) -> bool:
    """True when a GIVEUP/NACK reason is tipform / tray / engine.alive host-heal (FR #9554)."""
    text = str(reason or "").strip()
    if not text:
        return False
    return bool(_HOST_HEAL_TIPFORM_REASON_RE.search(text))


def row_is_host_heal_tipform(row: dict) -> bool:
    """True when the queue row title/body looks like tipform/tray host-heal (FR #9554)."""
    if not isinstance(row, dict) or _canon_task(row) != "FR":
        return False
    blob = f"{row.get('title') or ''}\n{row.get('body') or ''}\n{row.get('line') or ''}"
    return bool(_HOST_HEAL_TIPFORM_ROW_RE.search(blob))


def _normalize_host_heal_machine(raw: str) -> str:
    mid = fold_chair_host(
        bobreport.fold_machine_id(bobreport.normalize_machine_id(raw) or raw)
    )
    mid = str(mid or "").strip().lower()
    if not mid or mid in _REQUIRE_MACHINE_NON_MACHINE or _is_retired_require_machine(mid):
        return ""
    if mid not in _HOST_HEAL_FLEET_MACHINES and mid not in {
        bobreport.fold_machine_id(x) for x in _HOST_HEAL_FLEET_MACHINES
    }:
        # Still allow any non-retired fleet id from an explicit pin/reason.
        if not re.match(r"^[a-z0-9][a-z0-9_.-]*$", mid):
            return ""
    return mid


def infer_host_heal_machine(row: dict, reason: str = "") -> str:
    """Machine id for tipform host-heal auto-pin, or '' (FR #9554).

    Prefer GIVEUP ``require_machine=`` reason, then dedicated body pin / needs-
    label, then ``Host:`` / leading ``<machine>:`` title for host-heal rows.
    """
    if not isinstance(row, dict):
        return ""
    mid = parse_require_machine_giveup_reason(reason)
    if mid:
        return _normalize_host_heal_machine(mid)
    stamped = str(row.get("require_machine") or "").strip().lower()
    if stamped and stamped not in {"*", "any", "none", "-"}:
        got = _normalize_host_heal_machine(stamped)
        if got:
            return got
    # Dedicated body line + needs-<mid> labels (works on bobiverse under FR #4512).
    got = infer_require_machine(
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        labels=row.get("labels") or (),
        line=str(row.get("line") or ""),
        repo=str(row.get("repo") or ""),
        ident=str(row.get("id") or ""),
    )
    if got:
        return _normalize_host_heal_machine(got)
    body = str(row.get("body") or "")
    m = _HOST_HEAL_HOST_LINE_RE.search(body)
    if m:
        got = _normalize_host_heal_machine(m.group(1))
        if got:
            return got
    title = str(row.get("title") or "")
    m = _HOST_HEAL_TITLE_MACHINE_RE.match(title)
    if m:
        got = _normalize_host_heal_machine(m.group(1))
        if got:
            return got
    # Bare fleet machine token in title for host-heal rows only.
    if row_is_host_heal_tipform(row) or is_host_heal_tipform_reason(reason):
        blob = f"{title}\n{body}".lower()
        for cand in sorted(_HOST_HEAL_FLEET_MACHINES, key=len, reverse=True):
            if re.search(rf"\b{re.escape(cand)}\b", blob):
                got = _normalize_host_heal_machine(cand)
                if got:
                    return got
    return ""


def _ensure_host_heal_pin_body_and_label(row: dict, mid: str) -> None:
    """Append ``require_machine:`` body line + ``needs-<mid>`` queue label (FR #9554)."""
    mid = str(mid or "").strip().lower()
    if not mid:
        return
    body = str(row.get("body") or "")
    pin_line = f"require_machine: {mid}"
    if not _REQUIRE_MACHINE_PIN_LINE_RE.search(body):
        body = (body.rstrip() + "\n\n" + pin_line + "\n") if body.strip() else pin_line + "\n"
        row["body"] = _body_for_queue(body)
    elif pin_line.lower() not in body.lower():
        # Wrong machine line present - append the host-heal pin (operator path wins later).
        row["body"] = _body_for_queue(body.rstrip() + "\n" + pin_line + "\n")
    labs = row.get("labels")
    if isinstance(labs, str):
        labs = [labs]
    elif not isinstance(labs, list):
        labs = list(labs or [])
    need = f"needs-{mid}"
    labs_l = {str(x).strip().lower() for x in labs}
    if need not in labs_l:
        labs.append(need)
        row["labels"] = labs


def apply_host_heal_require_machine_stamp(
    row: dict,
    reason: str = "",
    *,
    nick: str = "",
) -> str:
    """FR #9554: after >=2 tipform/host-heal outcomes, pin require_machine (no needs_human).

    Counts infra-soft outcomes (holder_bored) when the *row* is host-heal class.
    Returns the stamped machine id, or '' when not yet at threshold / no machine.
    """
    if not isinstance(row, dict) or _canon_task(row) != "FR":
        return ""
    class_hit = is_host_heal_tipform_reason(reason) or row_is_host_heal_tipform(row)
    if not class_hit:
        return ""
    mid = infer_host_heal_machine(row, reason=reason)
    if not mid:
        return ""
    try:
        hh = int(row.get("host_heal_giveup_count") or 0)
    except (TypeError, ValueError):
        hh = 0
    hh += 1
    row["host_heal_giveup_count"] = hh
    try:
        gc = int(row.get("giveup_count") or 0)
    except (TypeError, ValueError):
        gc = 0
    threshold = int(GIVEUP_NEEDS_HUMAN_COUNT)
    if hh < threshold and gc < threshold:
        return ""
    row["require_machine"] = mid
    row["require_machine_operator"] = True
    row["require_machine_host_heal"] = True
    _ensure_host_heal_pin_body_and_label(row, mid)
    # Divert: host console / infra - never park as needs_human for this class.
    row.pop("needs_human", None)
    if nick:
        row["host_heal_pin_by"] = str(nick).strip()[:80]
    return mid


def clear_host_heal_require_machine_on_ack(row: dict, nick: str) -> bool:
    """FR #9554: clear auto host-heal pin when the pinned machine's seat ACKs.

    Operator ``!pin`` (no host-heal flag) is left alone; ``!unpin`` remains the
    human clear path for those.
    """
    if not isinstance(row, dict):
        return False
    flag = row.get("require_machine_host_heal")
    if isinstance(flag, bool):
        if not flag:
            return False
    elif str(flag or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    mid = str(row.get("require_machine") or "").strip().lower()
    if not mid or mid in {"*", "any", "none", "-"}:
        row.pop("require_machine_host_heal", None)
        return False
    if not seat_matches_require_machine(nick, mid):
        return False
    row["require_machine"] = "any"
    row.pop("require_machine_host_heal", None)
    # Keep operator flag so FR #4512 does not re-soft-pin from title text; any = unpinned.
    row["require_machine_operator"] = True
    return True


# FR #9469 / #9665: GIVEUP blocked:depends-on / blocked-on / depends_unresolved /
# depends_open with a parseable issue ref must stamp Depends-on: + durable block.
_BLOCKED_DEPENDS_CUE_RE = re.compile(
    r"(?i)\b(?:blocked\s*:\s*depends-on|blocked-on|depends[_-]unresolved|"
    r"depends[_-]?open)\b"
)
_BLOCKED_DEPENDS_QUAL_RE = re.compile(
    r"(?i)\b(?:blocked\s*:\s*depends-on|blocked-on|depends[_-]unresolved|"
    r"depends[_-]?open)\b"
    r"[^\n]*?\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b"
)
_BLOCKED_DEPENDS_REL_RE = re.compile(
    r"(?i)\b(?:blocked\s*:\s*depends-on|blocked-on|depends[_-]unresolved|"
    r"depends[_-]?open)\b"
    r"[^\n]*?#(\d+)\b"
)
# FR #9665: also ``depends_open:#N`` / ``depends_open=#N`` (structured reason).
_DEPENDS_OPEN_EQ_QUAL_RE = re.compile(
    r"(?i)\bdepends[_-]?open\s*[:=]\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b"
)
_DEPENDS_OPEN_EQ_REL_RE = re.compile(
    r"(?i)\bdepends[_-]?open\s*[:=]\s*#?(\d+)\b"
)


def parse_blocked_depends_giveup_refs(
    reason: str,
    *,
    home_repo: str = "",
) -> list[tuple[str, int]]:
    """FR #9469 / #9665: ``(repo, number)`` refs from a blocked Depends-on GIVEUP reason.

    Accepts ``blocked:depends-on #N``, ``depends_unresolved``, and structured
    ``depends_open:#N`` / ``reason=depends_open:#N`` (FR #9665).
    """
    text = str(reason or "").strip()
    if not text:
        return []
    home = str(home_repo or "").strip()
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    def _add(repo: str, num: int) -> None:
        repo_s = str(repo or home or "").strip()
        if not repo_s or num <= 0:
            return
        key = (repo_s.lower(), int(num))
        if key in seen:
            return
        seen.add(key)
        out.append((repo_s, int(num)))

    for m in _DEPENDS_OPEN_EQ_QUAL_RE.finditer(text):
        _add(m.group(1), int(m.group(2)))
    for m in _DEPENDS_OPEN_EQ_REL_RE.finditer(text):
        _add(home, int(m.group(1)))
    if _BLOCKED_DEPENDS_CUE_RE.search(text):
        for m in _BLOCKED_DEPENDS_QUAL_RE.finditer(text):
            _add(m.group(1), int(m.group(2)))
        # Prefer qualified owner/repo#N when present (same as FR #9469).
        if not out:
            for m in _BLOCKED_DEPENDS_REL_RE.finditer(text):
                _add(home, int(m.group(1)))
    return out


def _load_common_depends_on():
    """FR #9540: load ``common/scripts/depends_on.py`` by path (never monitor shadow).

    Tip ``build-jeeves`` collects monitor tests that ``sys.path.insert(0, tools/monitor)``.
    A bare ``import depends_on`` then binds ``jeeves/tools/monitor/depends_on.py`` (no
    ``merge_depends_on_body``) and reds FR #9469. Always load the sibling of this file.
    """
    import importlib.util
    import sys as _sys

    name = "bobiverse_common_depends_on"
    cached = _sys.modules.get(name)
    if cached is not None and hasattr(cached, "merge_depends_on_body"):
        return cached
    path = Path(__file__).resolve().with_name("depends_on.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load common depends_on from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _sys.modules[name] = mod
    return mod


def _normalize_depends_open_block(raw) -> list[tuple[str, int]]:
    """Parse ``row['depends_open']`` into ``(repo, number)`` tuples (FR #9665)."""
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    if raw is None:
        return out
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    for item in items:
        repo = ""
        num = 0
        if isinstance(item, dict):
            repo = str(item.get("repo") or "").strip()
            try:
                num = int(str(item.get("id") or item.get("number") or "").lstrip("#"))
            except ValueError:
                num = 0
        else:
            s = str(item or "").strip()
            m = re.match(
                r"(?i)^(?:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#|#)?(\d+)$", s
            )
            if m:
                repo = str(m.group(1) or "").strip()
                num = int(m.group(2))
        if num <= 0:
            continue
        key = (repo.lower(), num)
        if key in seen:
            continue
        seen.add(key)
        out.append((repo, num))
    return out


def _serialize_depends_open_block(
    refs: list[tuple[str, int]], *, home_repo: str = ""
) -> list[str]:
    """Stable queue tokens for ``depends_open`` (FR #9665)."""
    home = str(home_repo or "").strip()
    out: list[str] = []
    for repo, num in refs:
        repo_s = str(repo or home or "").strip()
        if not repo_s:
            out.append(f"#{int(num)}")
        elif home and repo_s.lower() == home.lower():
            out.append(f"#{int(num)}")
        else:
            out.append(f"{repo_s}#{int(num)}")
    return out


def merge_depends_open_block(
    row: dict, refs: list[tuple[str, int]]
) -> list[tuple[str, int]]:
    """Union ``refs`` into ``row['depends_open']``; return the full block list (FR #9665)."""
    if not isinstance(row, dict) or not refs:
        return _normalize_depends_open_block(row.get("depends_open") if isinstance(row, dict) else None)
    home = str(row.get("repo") or "").strip()
    merged = _normalize_depends_open_block(row.get("depends_open"))
    seen = {(r.lower(), n) for r, n in merged}
    for repo, num in refs:
        repo_s = str(repo or home or "").strip()
        key = (repo_s.lower(), int(num))
        if key in seen:
            continue
        seen.add(key)
        merged.append((repo_s, int(num)))
    row["depends_open"] = _serialize_depends_open_block(merged, home_repo=home)
    return merged


def clear_closed_depends_open_block(
    row: dict,
    *,
    open_keys: set[tuple[str, int]] | None = None,
    issue_open=None,
) -> list[tuple[str, int]]:
    """Drop CLOSED refs from ``depends_open``; return remaining open block (FR #9665)."""
    if not isinstance(row, dict):
        return []
    home = str(row.get("repo") or "").strip()
    cur = _normalize_depends_open_block(row.get("depends_open"))
    if not cur:
        row.pop("depends_open", None)
        return []
    keys = open_keys if open_keys is not None else set()
    keep: list[tuple[str, int]] = []
    for repo, num in cur:
        repo_s = str(repo or home or "").strip()
        still_open = (repo_s.lower(), int(num)) in {
            (r.lower(), n) for r, n in keys
        } or (repo_s, int(num)) in keys
        if not still_open and issue_open is not None:
            try:
                still_open = bool(issue_open(repo_s, str(num)))
            except Exception:
                # Unknown: keep the block (fail closed).
                still_open = True
        elif not still_open and issue_open is None and open_keys is None:
            # No checker: keep until a checker says CLOSED.
            still_open = True
        if still_open:
            keep.append((repo_s, int(num)))
    if keep:
        row["depends_open"] = _serialize_depends_open_block(keep, home_repo=home)
    else:
        row.pop("depends_open", None)
    return keep


def apply_depends_on_giveup_stamp(
    row: dict,
    reason: str,
    *,
    patch_github: bool = True,
    filer=None,
) -> list[tuple[str, int]]:
    """FR #9469 / #9665: stamp Depends-on body + durable ``depends_open`` block.

    Updates ``row["body"]`` with a plain ``Depends-on:`` line (unions existing)
    and ``row["depends_open"]`` so offer/assign skip until those issues CLOSE
    (bypasses unheld fr-digest soft-allow - FR #9665). When ``patch_github`` is
    true, PATCHes the issue body via ``gh``. Returns refs stamped from the reason.
    """
    if not isinstance(row, dict):
        return []
    home = str(row.get("repo") or "").strip()
    refs = parse_blocked_depends_giveup_refs(reason, home_repo=home)
    if not refs:
        return []
    merge_depends_open_block(row, refs)
    try:
        _dep = _load_common_depends_on()
    except Exception:
        return refs
    body = str(row.get("body") or "")
    new_body, changed = _dep.merge_depends_on_body(body, refs, repo=home)
    if changed:
        row["body"] = _body_for_queue(new_body) if new_body else new_body
    if patch_github and home:
        num = str(row.get("id") or "").strip().lstrip("#")
        if num.isdigit():
            try:
                api = filer
                if api is None:
                    import gh_filer

                    api = gh_filer.default_filer()
                # Prefer live GitHub body so we union remote Depends-on too.
                remote = ""
                with contextlib.suppress(Exception):
                    issue = fetch_github_issue_dict(home, num)
                    if isinstance(issue, dict):
                        remote = str(issue.get("body") or "")
                base = remote if remote.strip() else str(row.get("body") or body)
                patched, did = _dep.merge_depends_on_body(base, refs, repo=home)
                if did or (patched and patched != remote):
                    api.edit_issue_body(home, int(num), patched)
                    row["body"] = _body_for_queue(patched)
            except Exception:
                pass
    return refs


def row_blocked_for_machine(row: dict, nick: str) -> bool:
    """True when this seat must not be offered the row (FR #587 require_machine)."""
    req = row_require_machine(row)
    if not req:
        return False
    return not seat_matches_require_machine(nick, req)


def parse_github_pull_url(url: str) -> tuple[str, str] | None:
    """Return (owner/repo, #N) for a GitHub pull URL, else None (FR #254)."""
    m = PULL_URL_RE.search(str(url or ""))
    if not m:
        return None
    return m.group("repo"), f"#{m.group('num')}"


def fr_issue_key(repo: str, ident: str) -> str:
    """Canonical SimonBarnett/bobiverse#224 key for supersede checks."""
    r = str(repo or "").strip()
    i = str(ident or "").strip()
    if i and not i.startswith("#"):
        i = f"#{i}"
    return f"{r}{i}"


def normalize_row_refs(raw) -> list[str]:
    """FR #9475: always ``list[str]`` of ``#N``; heal comma-strings and char-split lists.

    Synchronize / enqueue historically wrote ``extra["refs"]=",".join(...)`` then
    ``row[k]=v``, leaving a string. ``tuple(str(x) for x in prior_refs)`` then
    iterates characters (``"#9270"`` -> ``["#","9",...]``), poisoning ledger
    link keys and false self-MRB / no_eligible_reviewer stamps.
    """
    if raw is None or raw == "":
        return []
    parts: list[str] = []
    if isinstance(raw, str):
        parts = [p.strip() for p in re.split(r"[,\s;]+", raw) if p.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw if str(x).strip() != ""]
        if items and all(len(x) == 1 for x in items):
            joined = "".join(items)
            parts = [p.strip() for p in re.split(r"[,\s;]+", joined) if p.strip()]
        else:
            parts = items
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        s = str(p or "").strip()
        if not s:
            continue
        num = s[1:].strip() if s.startswith("#") else s
        if not num.isdigit():
            continue
        tok = f"#{num}"
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def _refs_need_heal(raw) -> bool:
    """True when stored refs are a comma-string or a char-split list (FR #9475)."""
    if isinstance(raw, str):
        return bool(raw.strip())
    if isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw if str(x).strip() != ""]
        return bool(items) and all(len(x) == 1 for x in items)
    return False


def _row_refs(row: dict) -> list[str]:
    return normalize_row_refs(row.get("refs") if isinstance(row, dict) else None)


def fr_superseded_by_mrb(doc: dict, repo: str, ident: str) -> bool:
    """True when an unaccepted/accepted MRB supersedes this FR (FR #254)."""
    key = fr_issue_key(repo, ident)
    ident_s = str(ident or "").strip()
    if ident_s and not ident_s.startswith("#"):
        ident_s = f"#{ident_s}"
    for bucket in ("unaccepted", "accepted"):
        for row in doc.get(bucket) or []:
            if str(row.get("task") or "").upper() != "MRB":
                continue
            if str(row.get("supersedes") or "").strip() == key:
                return True
            if str(row.get("repo") or "") == str(repo or "") and ident_s in _row_refs(row):
                return True
    return False


def fr_superseded_by_done_pr(
    doc: dict,
    repo: str,
    ident: str,
    *,
    open_pulls: dict[str, set[str]] | None = None,
    fetched_repos: set[str] | None = None,
) -> bool:
    """DONE FR with /pull/ URL keeps the issue superseded while that PR is open (FR #254).

    If the PR repo was not fetched, stay superseded (avoid re-offer when implement PR is cross-repo).
    If the PR repo was fetched and the PR is no longer open, do not block.
    FR #4373: without live ``open_pulls``, terminal DONE results (PASS/MERGED/CLOSED/FAIL)
    must not block reopen - only an ambiguous active implement (no terminal result) does.
    """
    ident_s = str(ident or "").strip()
    if ident_s and not ident_s.startswith("#"):
        ident_s = f"#{ident_s}"
    _terminal = frozenset({"PASS", "MERGED", "CLOSED", "DONE", "FAIL"})
    for row in doc.get("done") or []:
        if str(row.get("task") or "").upper() != "FR":
            continue
        if not _same(row, repo, "FR", ident_s):
            continue
        parsed = parse_github_pull_url(str(row.get("url") or ""))
        if not parsed:
            continue
        pr_repo, pr_id = parsed
        if fetched_repos is not None and pr_repo not in fetched_repos:
            return True
        if open_pulls is not None:
            return pr_id in open_pulls.get(pr_repo, set())
        result = str(row.get("result") or "").strip().upper()
        if result in _terminal:
            continue
        return True
    return False


def _append_row_history(row: dict, note: str, *, cap: int = 20) -> None:
    """Append a short history line onto a queue row (FR #4373 reopen notes)."""
    text = str(note or "").strip()
    if not text or not isinstance(row, dict):
        return
    hist = row.get("history")
    if not isinstance(hist, list):
        hist = []
    hist.append(text)
    row["history"] = hist[-cap:]


def _done_has_fr(doc: dict, repo: str, ident: str) -> bool:
    """True when ``done`` already holds this FR (FR #4656)."""
    done = doc.get("done")
    if not isinstance(done, list):
        return False
    return any(isinstance(row, dict) and _same(row, repo, "FR", ident) for row in done)


def closed_unmerged_ref_skip_reason(doc: dict, repo: str, ident: str) -> str | None:
    """FR #4656: why a closed-unmerged PR ref must not be requeued.

    Requeue only when the ref is an open issue (not a pull) that already sits in
    ``done`` (FR #4373). Otherwise return a one-line skip reason.
    """
    num = str(ident or "").strip().lstrip("#")
    shown = f"#{num}" if num else str(ident or "")
    if not num.isdigit():
        return f"requeue skip ref {shown}: not an issue number"
    if not _done_has_fr(doc, repo, ident):
        return f"requeue skip ref {shown}: not in done"
    is_pull = github_is_pull_checker()
    issue_open = github_issue_open_checker()
    if is_pull is None or issue_open is None:
        return f"requeue skip ref {shown}: lookup unavailable"
    try:
        if bool(is_pull(repo, num)):
            return f"requeue skip ref {shown}: pull request"
        if not bool(issue_open(repo, num)):
            return f"requeue skip ref {shown}: issue closed"
    except GitHubLookupUnknown:
        return f"requeue skip ref {shown}: lookup unknown"
    except Exception:
        return f"requeue skip ref {shown}: lookup unknown"
    return None


def pop_done_fr_rows(doc: dict, repo: str, ident: str) -> list[dict]:
    """Remove matching FR rows from ``done`` (FR #4373 reopen / resync)."""
    done = doc.get("done")
    if not isinstance(done, list):
        return []
    kept: list[dict] = []
    removed: list[dict] = []
    for row in done:
        if isinstance(row, dict) and _same(row, repo, "FR", ident):
            removed.append(row)
        elif isinstance(row, dict):
            kept.append(row)
    if removed:
        doc["done"] = kept
    return removed


def pop_done_mrb_rows(doc: dict, repo: str, ident: str) -> list[dict]:
    """Remove matching MRB rows from ``done`` (FR #4929 head-move requeue).

    A prior PASS/FAIL in ``done[]`` makes ``mrb_already_done`` true when purge
    runs without ``pr_exists``, which drops a fresh synchronize MRB before
    DONE FIX can land. Popping the stale done row lets the new head stay queued.
    """
    done = doc.get("done")
    if not isinstance(done, list):
        return []
    kept: list[dict] = []
    removed: list[dict] = []
    for row in done:
        if isinstance(row, dict) and _same(row, repo, "MRB", ident):
            removed.append(row)
        elif isinstance(row, dict):
            kept.append(row)
    if removed:
        doc["done"] = kept
    return removed


def _queue_row_for(doc: dict, repo: str, task: str, ident: str) -> dict | None:
    """First matching row in unaccepted / accepted / done (FR #9080 requeue refresh)."""
    repo_c = canonical_queue_repo(repo)
    for bucket in ("unaccepted", "accepted", "done"):
        for row in doc.get(bucket) or []:
            if isinstance(row, dict) and _same(row, repo_c, task, ident):
                return row
    return None


def ensure_mrb_requeued_after_head_move(
    doc: dict,
    home: Path | None,
    *,
    repo: str,
    pr: str,
    url: str = "",
    reason: str = "",
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    refs: tuple[str, ...] | list[str] = (),
    pr_snapshot: dict | None = None,
    fetch_pr=None,
    issue_lookup=None,
) -> str:
    """FR #4929 / #9080 / #9243: clear stale mrb_done / done[] MRB and ensure an unaccepted MRB row.

    Used when a FIX push (synchronize) or DONE FIX lands after a prior MRB PASS
    so the new head is offerable without waiting for ``!resync``.
    Returns ``added`` | ``duplicate`` | ``skipped`` | ``noop``.

    FR #9080: refresh title / body / labels / refs from ``pr_snapshot``, optional
    ``fetch_pr``, or a prior queue row before append. Never stamp empty labels that
    hide a GitHub ``hold``. When ``pr_hold_reason`` hits, purge the unaccepted twin
    and return ``skipped``.

    FR #9243: also honour ``linked_issue_hold_reason`` when ``issue_lookup`` is
    provided (same injectable shape as ``enqueue_conflict_fix``). Do **not**
    invent a default network fetch here - callers under the queue lock must pass
    a prefetched lookup or omit it (omit = no linked check, lock-safe). Lookup
    failures inside ``linked_issue_hold_reason`` continue per-issue (fail-open).
    An accepted MRB row is left alone; only the unaccepted twin is purged.
    """
    repo_c = canonical_queue_repo(repo)
    num = str(pr or "").strip().lstrip("#")
    if not repo_c or not num.isdigit():
        return "skipped"
    ident = f"#{num}"
    pull = str(url or "").strip()
    if not PULL_URL_RE.search(pull):
        pull = f"https://github.com/{repo_c}/pull/{num}"
    if home is not None:
        with contextlib.suppress(Exception):
            clear_mrb_done(home, repo_c, ident)
    pop_done_mrb_rows(doc, repo_c, ident)
    why = str(reason or "head-move").strip() or "head-move"

    snap: dict = {}
    if isinstance(pr_snapshot, dict):
        snap = pr_snapshot
    elif fetch_pr is False:
        snap = {}
    else:
        getter = fetch_pr
        if getter is None:
            try:
                import mrb_merge_on_green as _mog

                getter = lambda r, n: _mog.fetch_pr_state(r, n)  # noqa: E731
            except Exception:  # noqa: BLE001
                getter = None
        if getter is not None:
            with contextlib.suppress(Exception):
                got = getter(repo_c, num)
                if isinstance(got, dict):
                    snap = got

    prior = _queue_row_for(doc, repo_c, "MRB", ident)
    title_s = (
        str(title or "").strip()
        or str(snap.get("title") or "").strip()
        or str((prior or {}).get("title") or "").strip()
    )
    body_s = (
        str(body or "")
        or str(snap.get("body") or "")
        or str((prior or {}).get("body") or "")
    )
    labels_t: tuple[str, ...] = tuple(str(x) for x in (labels or ()) if str(x).strip())
    if not labels_t:
        labels_t = _label_names(snap.get("labels"))
    if not labels_t and prior is not None:
        pl = prior.get("labels") or ()
        if isinstance(pl, str):
            pl = [pl]
        labels_t = tuple(str(x) for x in pl if str(x).strip())
    refs_t: tuple[str, ...] = tuple(normalize_row_refs(refs or ()))
    if not refs_t and prior is not None and prior.get("refs"):
        # FR #9475: never iterate a refs string by character.
        refs_t = tuple(normalize_row_refs(prior.get("refs")))
    if not refs_t:
        refs_t = extract_closes_issue_ids(body_s, repo=repo_c)
    if not title_s:
        title_s = f"requeue after {why} (FR #4929)"

    hold = pr_hold_reason(title=title_s, body=body_s, labels=labels_t)
    # FR #9243: linked FR/issue hold (issues-only labels / HOLD: body) blocks
    # head-move requeue the same way dirty-FIX does - only when lookup is passed.
    if not hold and issue_lookup is not None:
        hold = linked_issue_hold_reason(
            repo_c,
            body=body_s,
            refs=refs_t,
            issue_lookup=issue_lookup,
        )
    if hold:
        doc["unaccepted"] = [
            r
            for r in (doc.get("unaccepted") or [])
            if not (isinstance(r, dict) and _same(r, repo_c, "MRB", ident))
        ]
        return "skipped"

    claim = GitClaim(
        repo=repo_c,
        task="MRB",
        id=ident,
        event="pull_request",
        action="synchronize",
        line=pull,
        title=title_s,
        body=body_s,
        labels=labels_t,
        refs=refs_t,
    )
    return _append_unaccepted(doc, claim, url=pull)


def prepare_reopened_fr_row(
    row: dict,
    claim: GitClaim,
    *,
    via: str,
    actor: str = "",
    prior_done: dict | None = None,
) -> None:
    """Stamp reopen history, labels, and clear machine pins (FR #4373).

    Requeued work is never pinned to a machine (bobiverse must never stick on ionos).
    """
    labels = list(claim.labels) if claim.labels else list((prior_done or {}).get("labels") or [])
    if labels:
        row["labels"] = labels
    if claim.title:
        row["title"] = claim.title
    if claim.body:
        row["body"] = _body_for_queue(claim.body)
    if claim.state:
        row["state"] = str(claim.state).strip().lower()
    # Drop seat / machine pins from the finished attempt.
    for key in (
        "require_machine",
        "require_machine_operator",  # FR #6592
        "require_machine_host_heal",  # FR #9554
        "host_heal_giveup_count",
        "host_heal_pin_by",
        "offered_to",
        "offered_ts",
        "offered_via",
        "nick",
        "accepted_by",
        "accepted_ts",
        "channel",
        "needs_human",
    ):
        row.pop(key, None)
    who = (actor or claim.opened_by or "").strip() or "unknown"
    when = _utc_now()
    via_s = (via or "unknown").strip().lower() or "unknown"
    _append_row_history(
        row,
        f"reopened via={via_s} by={who} at={when}",
    )


def clear_fr_done_stamp(home: Path, repo: str, ident) -> bool:
    """Drop the ``fr_done`` hold for ``repo#id`` (FR #4695).

    Called when a real reopen requeues the FR so seats can take it without
    waiting for ``!resync``. Returns True when a stamp was present and removed.
    """
    key = _lkey(repo, ident)
    cleared = {"v": False}

    def _fn(doc: dict) -> None:
        fd = doc.setdefault("fr_done", {})
        if key in fd:
            fd.pop(key, None)
            cleared["v"] = True

    try:
        _ledger_update(home, _fn)
    except OSError:
        return False
    if cleared["v"]:
        num = str(ident or "").strip().lstrip("#")
        print(f"INFO reopen cleared fr_done {repo}#{num}", flush=True)
    return cleared["v"]


def requeue_reopened_issue(
    doc: dict,
    claim: GitClaim,
    *,
    via: str,
    actor: str = "",
    home: Path | None = None,
) -> str:
    """Move an open/reopened FR out of ``done`` into ``unaccepted`` (FR #4373).

    FR #4695: when ``home`` is set and the row is requeued, clear ``fr_done`` in
    the same step so ``_ledger_blocks`` no longer reports
    ``FR already delivered (PR pending merge)`` until a manual ``!resync``.

    Returns added|updated|duplicate|noop|skipped.
    """
    if claim.task != "FR":
        return "noop"
    # FR #6208: refuse before mutating done/accepted so ignore does not wipe history.
    if home is not None:
        import focus_ignore as _fi_ignore

        if _fi_ignore.is_ignored(home, claim.repo):
            return "skipped"
    removed = pop_done_fr_rows(doc, claim.repo, claim.id)
    # Accepted FR for a reopened issue must not stay claimed.
    before_acc = len(doc.get("accepted") or [])
    doc["accepted"] = [
        r
        for r in (doc.get("accepted") or [])
        if not (isinstance(r, dict) and _same(r, claim.repo, "FR", claim.id))
    ]
    _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"UAT", "PR"})
    prior = removed[0] if removed else None
    changed = _append_unaccepted(doc, claim, home=home)
    if changed == "skipped":
        return "skipped"
    # Find the live unaccepted row and stamp reopen metadata.
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict) or not _same(row, claim.repo, "FR", claim.id):
            continue
        prepare_reopened_fr_row(
            row,
            claim,
            via=via,
            actor=actor,
            prior_done=prior,
        )
        break
    if removed or before_acc != len(doc.get("accepted") or []):
        if changed in ("noop", "duplicate"):
            changed = "updated"
    if home is not None and changed in ("added", "updated", "duplicate"):
        clear_fr_done_stamp(home, claim.repo, claim.id)
    return changed

def fr_superseded_by_open_closes_pr(
    repo: str,
    ident: str,
    open_closes: dict[str, set[str]] | None,
) -> bool:
    """True when an open PR's Closes/Fixes/Resolves covers this issue (FR #4589).

    Includes draft, harvest-receipt, and ci-wait pulls that resync skips as MRB:
    the issue is waiting on CI/review, not on a new implement turn.
    """
    if not open_closes:
        return False
    ident_s = _norm_row_id(ident)
    if not ident_s:
        return False
    repo_s = str(repo or "").strip()
    nums = open_closes.get(repo_s)
    if nums is None:
        rk = _repo_key(repo_s)
        for name, nset in open_closes.items():
            if _repo_key(name) == rk:
                nums = nset
                break
    return bool(nums) and ident_s in nums


def fr_is_superseded(
    doc: dict,
    repo: str,
    ident: str,
    *,
    open_pulls: dict[str, set[str]] | None = None,
    fetched_repos: set[str] | None = None,
    open_closes: dict[str, set[str]] | None = None,
) -> bool:
    """FR must not be (re)queued/offered while MRB supersedes it or implement PR is open."""
    if fr_superseded_by_mrb(doc, repo, ident):
        return True
    if fr_superseded_by_open_closes_pr(repo, ident, open_closes):
        return True
    return fr_superseded_by_done_pr(
        doc, repo, ident, open_pulls=open_pulls, fetched_repos=fetched_repos
    )



def claim_from_payload(
    event: str,
    payload: dict,
    *,
    line: str = "",
    docs_mrb_parent_open=None,
    mrb_fix_parent_open=None,
) -> GitClaim | None:
    """Build a claim from the GitHub webhook body. None if not a queue-driving event.

    issues opened/reopened/edited -> FR (edited refreshes body/require_machine - FR #9543;
    skipped for skill/harvest/safe-to-close/umbrella/closed - FR #180)
    pull_request opened/ready_for_review -> MRB (with refs to linked issues)
    pull_request closed -> MRB row used for supersede (merged flag set)
    issues closed -> FR/UAT removal via apply_queue_event (task FR id)
    issues/pull_request labeled|unlabeled -> update matching row labels; re-eval FR skip (FR #3275).
    FR #4955: pull_request labeled on a lesson(book): tip backfills MRB if opened missed.
    """
    if not isinstance(payload, dict):
        return None
    ev = (event or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    repo = _payload_repo(payload)
    if not repo or not REPO_RE.fullmatch(repo):
        return None
    src = (line or "").strip()
    # FR #785: never enqueue new work from an archived repo (closed still flows for prune).
    enqueue_action = action in ("opened", "reopened", "ready_for_review", "edited")
    if enqueue_action and repo_archived_for_queue(repo, payload=payload):
        return None

    # FR #9543: include edited so a late ``require_machine:`` body pin refreshes
    # the queued FR (class of #9526 - pin stamped after enqueue, chair kept offering
    # non-pin shops until the next full resync).
    if ev == "issues" and action in ("opened", "reopened", "edited"):
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        issue = _issue_blob(payload)
        # FR #838 / #846: issue payloads for pulls include ``pull_request`` - never FR.
        if issue.get("pull_request"):
            return None
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        labels = _label_names(issue.get("labels"))
        state = str(issue.get("state") or "open")
        # FR #180 / #2340: closed issues must never become FR rows (opened/reopened
        # with state=closed, or backfill synthesising opened for a closed issue).
        # edited on a closed issue is a no-op claim (apply path ignores / closed wins).
        if action != "edited" and issue_skip_fr_reason(
            title=title, body=body, labels=labels, state=state
        ):
            # FR #9821 / MRB #9834: open fr-digest gate records must still claim so
            # _append_unaccepted can enqueue them (skip_fr alone must not drop).
            _probe = {
                "task": "FR",
                "title": title,
                "body": body,
                "labels": list(labels),
            }
            if str(state).strip().lower() == "closed" or not digest_issue_reason(_probe):
                return None
        if action == "edited" and str(state).strip().lower() == "closed":
            return None
        return GitClaim(
            repo=repo,
            task="FR",
            id=ident,
            event=ev,
            action=action,
            line=src,
            title=title,
            body=body,
            labels=labels,
            state=state,
        )

    if ev == "issues" and action == "closed":
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        issue = _issue_blob(payload)
        sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
        actor = str(sender.get("login") or "").strip()
        # FR #4624: carry state=closed so apply stamps ACC rows (budget-0 offer
        # cannot live-check; released ACC must not re-enter unaccepted unstamped).
        # FR #4851: actor drives shop CANCEL "closed by <user>".
        return GitClaim(
            repo=repo,
            task="FR",
            id=ident,
            event=ev,
            action=action,
            line=src,
            title=str(issue.get("title") or ""),
            body=str(issue.get("body") or ""),
            labels=_label_names(issue.get("labels")),
            state="closed",
            actor=actor,
        )

    # FR #3275: labeled/unlabeled mutate queue labels in place (zero REST).
    if ev in ("issues", "pull_request") and action in ("labeled", "unlabeled"):
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        blob = _issue_blob(payload) if ev == "issues" else _pr_blob(payload)
        if ev == "issues" and blob.get("pull_request"):
            return None
        title = str(blob.get("title") or "")
        body = str(blob.get("body") or "")
        labels = _label_names(blob.get("labels"))
        state = str(blob.get("state") or "open")
        task = "FR" if ev == "issues" else "MRB"
        # FR #4955: lesson(book) tips may open before harvest-lesson is applied.
        # Stamp harvest_lesson so labeled can backfill a missed opened MRB.
        # Drafts never invent a row. Product titles with a stray label do not.
        lesson = False
        opener = ""
        if ev == "pull_request":
            lesson = bool(
                is_harvest_lesson_pr(title=title, labels=labels)
                and re.match(r"(?i)^lesson\s*\(", title.strip())
                and blob.get("draft") is not True
            )
            if lesson:
                opener = lesson_pr_opener_seat(body)
        return GitClaim(
            repo=repo,
            task=task,
            id=ident,
            event=ev,
            action=action,
            line=src or title,
            title=title,
            body=body,
            labels=labels,
            state=state,
            harvest_lesson=lesson,
            opened_by=opener,
        )

    # FR #924: include synchronize so author_seat backfill runs on push without waiting for edited.
    if ev == "pull_request" and action in ("opened", "ready_for_review", "edited", "synchronize"):
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        pr = _pr_blob(payload)
        title = str(pr.get("title") or "")
        body = str(pr.get("body") or "")
        labels = _label_names(pr.get("labels"))
        # FR #2650 / #2604: draft PRs never become MRB (resync already skips drafts).
        # FR #5506: draft via-intake+skill lesson PRs are offerable (not receipts).
        # MRB #2651: also edited/synchronize - _apply_claim_to_doc appends unaccepted for those.
        _paths = resolve_intake_pr_changed_paths(pr, repo=repo, number=ident)
        if action in ("opened", "ready_for_review", "edited", "synchronize") and pr.get("draft") is True:
            _head_early = pr.get("head") if isinstance(pr.get("head"), dict) else {}
            _user = pr.get("user") if isinstance(pr.get("user"), dict) else {}
            if not (
                is_offerable_intake_skill_lesson_pr(
                    title=title, body=body, labels=labels, files=_paths
                )
                or is_copilot_fr_implement_pr(
                    title=title,
                    body=body,
                    labels=labels,
                    head_ref=str(_head_early.get("ref") or ""),
                    user_login=str(_user.get("login") or ""),
                    repo=repo,
                )
            ):
                return None
        # FR #2650 / MRB #2651: intake harvest receipt PRs never become MRB via webhook
        # (opened/ready_for_review/edited/synchronize all call _append_unaccepted).
        if action in ("opened", "ready_for_review", "edited", "synchronize") and is_intake_harvest_receipt_pr(
            title=title, body=body, labels=labels, files=_paths
        ):
            return None
        # FR #5500 / #6340: docs/mrb-* pin PRs skip webhook MRB while the original
        # is still open. When the parent is already merged/closed, claim one MRB.
        _head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
        _docs_mrb_orphan_claim = False
        if action in ("opened", "ready_for_review", "edited", "synchronize") and is_docs_mrb_pin_pr(
            title=title,
            head_ref=str(_head.get("ref") or ""),
            labels=labels,
        ):
            parent = docs_mrb_pin_parent_pr_id(
                title=title, head_ref=str(_head.get("ref") or "")
            )
            parent_open = True
            if parent and docs_mrb_parent_open is not None:
                try:
                    parent_open = bool(docs_mrb_parent_open(repo, parent))
                except Exception:  # noqa: BLE001
                    parent_open = True
            if parent_open or not parent:
                return None
            if is_lesson_of_lesson_pr(
                title=title,
                body=body,
                labels=labels,
                head_ref=str(_head.get("ref") or ""),
            ):
                return None
            _docs_mrb_orphan_claim = True
        # bobiverse#224 / #781: stacked fix(mrb-N) on the parent branch is not a
        # second MRB. FR #8475: main/master base, or a parent that is not open,
        # is an ordinary MRB (same rule as resync).
        _mrb_fix_offer_claim = False
        if action in ("opened", "ready_for_review") and is_mrb_fix_pr_title(title):
            parent_fix = mrb_fix_parent_pr_id(title)
            parent_open = True
            if parent_fix and mrb_fix_parent_open is not None:
                try:
                    parent_open = bool(mrb_fix_parent_open(repo, parent_fix))
                except Exception:  # noqa: BLE001
                    parent_open = True
            allow_fix = mrb_fix_targets_default_branch(pr) or (
                bool(parent_fix) and not parent_open
            )
            if not allow_fix:
                return None
            _mrb_fix_offer_claim = True
        # Lesson PRs cite FRs; they do not implement them. No refs, so the cited FR's
        # implementer is not stamped as author and the FR row is not superseded.
        lesson = is_harvest_lesson_pr(title=title, labels=labels)
        refs = () if lesson else extract_closes_issue_ids(title, body, src, repo=repo)
        _head_ref = str(_head.get("ref") or "")
        _u = pr.get("user") if isinstance(pr.get("user"), dict) else {}
        _ulogin = str(_u.get("login") or "")
        # FR #5847: head copilot/fr-<N>-* links the FR even when body omits Closes.
        if not lesson:
            head_iss = copilot_fr_head_issue(_head_ref)
            if head_iss and head_iss not in refs:
                refs = tuple(list(refs) + [head_iss])
        if lesson:
            opener = lesson_pr_opener_seat(body)
        elif is_copilot_fr_implement_pr(
            title=title,
            body=body,
            labels=labels,
            head_ref=_head_ref,
            user_login=_ulogin,
            repo=repo,
        ):
            opener = "copilot"
        else:
            opener = ""
        task = "MRB" if action in ("opened", "ready_for_review") else "MRB"
        orphan_line = src
        if _docs_mrb_orphan_claim:
            hint = (
                f"docs_mrb_orphan parent={parent} "
                "(missing required check -> FAIL or re-run; no pin-of-pin)"
            )
            orphan_line = f"{src} | {hint}" if src else hint
        return GitClaim(
            repo=repo,
            task=task,
            id=ident,
            event=ev,
            action=action,
            line=orphan_line,
            refs=refs,
            title=title,
            body=body,
            labels=labels,
            harvest_lesson=lesson,
            opened_by=opener,
            docs_mrb_orphan=_docs_mrb_orphan_claim,
            mrb_fix_offer=_mrb_fix_offer_claim,
        )

    if ev == "pull_request" and action == "closed":
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        pr = _pr_blob(payload)
        title = str(pr.get("title") or "")
        body = str(pr.get("body") or "")
        labels = _label_names(pr.get("labels"))
        # Lesson PRs cite FRs: closing one (merged or not) must not touch or re-open them.
        # Never self-reference: the chair line "... closed #N ..." is not a link to FR #N.
        if is_harvest_lesson_pr(title=title, labels=labels):
            refs = ()
        else:
            refs = tuple(
                r for r in extract_closes_issue_ids(title, body, src, repo=repo) if r != ident
            )
        merged = bool(pr.get("merged"))
        return GitClaim(
            repo=repo,
            task="MRB",
            id=ident,
            event=ev,
            action=action,
            line=src or title,
            refs=refs,
            merged=merged,
            title=title,
            body=body,
        )

    # legacy allowlist map for anything else
    task = CLAIM_ACTIONS.get((ev, action))
    if task is None:
        return None
    ident = _payload_number(ev, payload)
    if ident is None:
        return None
    return GitClaim(repo=repo, task=task, id=ident, event=ev, action=action, line=src)


def _clear_unaccepted_offer_pins_for_job(
    home: Path | None,
    doc: dict,
    repo: str,
    task: str,
    ident: str,
) -> int:
    """FR #9402: clear offered_to (+ seat-holds) on matching unaccepted rows.

    Returns how many rows had an offer pin cleared. Caller still removes/drops
    the row when hold/skip applies.
    """
    cleared = 0
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if not _same(row, repo, task, ident):
            continue
        had = bool(str(row.get("offered_to") or "").strip())
        for k in ("offered_to", "offered_ts", "offered_channel", "offered_via"):
            row.pop(k, None)
        if had:
            cleared += 1
    if home is not None:
        with contextlib.suppress(Exception):
            _clear_job_seat_holds_unlocked(home, repo, task, ident)
    return cleared


def _remove_unaccepted(doc: dict, repo: str, task: str, ident: str) -> int:
    before = len(doc["unaccepted"])
    doc["unaccepted"] = [
        r for r in doc["unaccepted"] if not _same(r, repo, task, ident)
    ]
    return before - len(doc["unaccepted"])


def _remove_unaccepted_tasks(doc: dict, repo: str, ident: str, tasks: set[str]) -> int:
    before = len(doc["unaccepted"])
    want_id = _norm_row_id(ident)
    want_repo = _repo_key(repo)
    want_tasks = {str(t).upper() for t in tasks}
    doc["unaccepted"] = [
        r
        for r in doc["unaccepted"]
        if not (
            _repo_key(r.get("repo")) == want_repo
            and _norm_row_id(r.get("id")) == want_id
            and str(r.get("task") or "").upper() in want_tasks
        )
    ]
    return before - len(doc["unaccepted"])


def _prune_stale_requeue_duplicate(doc: dict, claim: GitClaim) -> None:
    """FR #4827: drop a second seat's accepted FR when the stale-released seat's PR lands.

    A done row with ``reconcile`` STALE_BUSY / LOST_DONE_RESTART is the original seat.
    The accepted row for the same FR held by anyone else is the duplicate. That row
    moves to done and a stand-down note is queued for the chair to say in the shop.
    """
    if claim.harvest_lesson or not claim.refs:
        return
    notes = doc.get("stand_down")
    if not isinstance(notes, list):
        notes = []
        doc["stand_down"] = notes
    repo = str(claim.repo or "")
    pr_n = str(claim.id or "").lstrip("#")
    pr_url = f"https://github.com/{repo}/pull/{pr_n}" if repo and pr_n else ""
    acc = [r for r in (doc.get("accepted") or []) if isinstance(r, dict)]
    drop_ids: set[int] = set()
    for ref in claim.refs:
        want = _norm_row_id(ref)
        original = ""
        for row in doc.get("done") or []:
            if not isinstance(row, dict):
                continue
            if _repo_key(str(row.get("repo") or "")) != _repo_key(repo):
                continue
            if str(row.get("task") or "").upper() != "FR":
                continue
            if _norm_row_id(row.get("id")) != want:
                continue
            reason = str(row.get("reconcile") or row.get("result") or "").strip()
            if reason not in ("STALE_BUSY", "LOST_DONE_RESTART"):
                continue
            nick = str(row.get("nick") or row.get("accepted_by") or "").strip()
            if nick:
                original = nick
                break
        if not original:
            continue
        for row in acc:
            if id(row) in drop_ids:
                continue
            if _repo_key(str(row.get("repo") or "")) != _repo_key(repo):
                continue
            if str(row.get("task") or "").upper() != "FR":
                continue
            if _norm_row_id(row.get("id")) != want:
                continue
            holder = str(row.get("nick") or row.get("accepted_by") or "").strip()
            if not holder or holder.lower() == original.lower():
                continue
            fin = dict(row)
            fin["result"] = "DUPLICATE_STALE"
            fin["reconcile"] = "DUPLICATE_STALE"
            fin["done_ts"] = _utc_now()
            doc.setdefault("done", []).append(fin)
            drop_ids.add(id(row))
            chan = worker_shop_channel(holder) or ""
            text = f"stand down FR {repo}{want} original seat {original} opened {pr_url}".strip()
            notes.append(
                {"nick": holder, "channel": chan, "text": text, "repo": repo, "id": want}
            )
    if drop_ids:
        doc["accepted"] = [r for r in acc if id(r) not in drop_ids]
        done = doc.get("done") or []
        if len(done) > DONE_CAP:
            doc["done"] = done[-DONE_CAP:]
    if len(notes) > 20:
        doc["stand_down"] = notes[-20:]


def drain_stand_down(home: Path) -> list[dict]:
    """Pop FR #4827 stand-down notes written by ``_prune_stale_requeue_duplicate``."""
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            notes = [n for n in (doc.get("stand_down") or []) if isinstance(n, dict)]
            if not notes:
                return []
            doc["stand_down"] = []
            _write_queue(queue_path(home), doc)
            return notes
    except (TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return []


def fr_implementer_seat_from_doc(doc: dict, repo: str, refs, pr_id: str = "") -> str:
    """FR #593 / #227: seat nick that implemented linked FR(s), if known.

    Looks at accepted/done FR rows matching ``repo`` + ``refs`` (``#N``), then
    unaccepted FR rows (rare). Used when a PR-opened webhook creates an MRB
    without going through DONE FR (which already stamps author_seat).

    FR #4854: when ``pr_id`` is set, prefer an FR whose result/url is that pull,
    and never return a seat from an FR whose result is a different pull (Refs noise).
    """
    ref_set = set()
    if isinstance(refs, str):
        refs = [refs]
    for r in refs or ():
        s = str(r or "").strip()
        if not s:
            continue
        if not s.startswith("#"):
            s = f"#{s.lstrip('#')}"
        ref_set.add(s)
    if not ref_set or not repo:
        return ""
    want_pr = _norm_row_id(pr_id) if pr_id else ""

    def _seat_of(row: dict) -> str:
        nick = str(
            row.get("nick")
            or row.get("done_by")
            or row.get("implementer_seat")
            or row.get("author_seat")
            or ""
        ).strip()
        if nick and bobreport.parse_seat_nick(nick):
            return canonical_worker_nick(nick) or nick
        return ""

    def _result_pr(row: dict) -> str:
        url = str(row.get("url") or row.get("result") or "")
        parsed = parse_github_pull_url(url)
        if not parsed:
            return ""
        if _repo_key(parsed[0]) != _repo_key(repo):
            return ""
        return _norm_row_id(parsed[1])

    # Pass 1 (FR #4854): FR whose result is this PR.
    if want_pr:
        for bucket in ("accepted", "done", "unaccepted"):
            for row in doc.get(bucket) or []:
                if str(row.get("repo") or "") != repo:
                    continue
                if str(row.get("task") or "").upper() != "FR":
                    continue
                if str(row.get("id") or "") not in ref_set:
                    continue
                if _result_pr(row) != want_pr:
                    continue
                seat = _seat_of(row)
                if seat:
                    return seat

    # Pass 2: linked FR without a conflicting different-PR result.
    for bucket in ("accepted", "done", "unaccepted"):
        for row in doc.get(bucket) or []:
            if str(row.get("repo") or "") != repo:
                continue
            if str(row.get("task") or "").upper() != "FR":
                continue
            if str(row.get("id") or "") not in ref_set:
                continue
            other = _result_pr(row)
            if want_pr and other and other != want_pr:
                continue
            seat = _seat_of(row)
            if seat:
                return seat
    return ""


# FR #2623: citing DONE FR must not overwrite the true implementer on an existing MRB row.
_IMPLEMENTER_KEEP_KEYS = frozenset(
    {"author_seat", "implementer_seat", "author_nick", "author"}
)


def resolve_done_fr_implementer_seat(
    doc: dict,
    *,
    pr_repo: str,
    pr_id: str,
    issue_repo: str,
    issue_id: str,
    done_nick: str,
) -> str:
    """Seat to stamp as MRB implementer after a DONE FR with a pull URL (FR #2623).

    Prefer (1) an existing MRB row stamp for the pull, then (2) the earliest prior
    DONE FR that already pointed at the same pull (or same issue+pull). A re-offered
    FR whose DONE only cites another seat's open PR must keep that earlier
    implementer - never the citing seat.
    """
    want_pr = _norm_row_id(pr_id)
    for bucket in ("unaccepted", "accepted", "done"):
        for row in doc.get(bucket) or []:
            if str(row.get("task") or "").upper() != "MRB":
                continue
            if str(row.get("repo") or "") != str(pr_repo or ""):
                continue
            if _norm_row_id(row.get("id")) != want_pr:
                continue
            seat = str(
                row.get("implementer_seat")
                or row.get("author_seat")
                or row.get("author_nick")
                or ""
            ).strip()
            if seat and bobreport.parse_seat_nick(seat):
                return canonical_worker_nick(seat) or seat

    pull_num = str(pr_id or "").lstrip("#")
    pull_needle = f"/pull/{pull_num}"
    issue_norm = _norm_row_id(issue_id)
    for row in doc.get("done") or []:
        if str(row.get("task") or "").upper() != "FR":
            continue
        url = str(row.get("url") or row.get("result") or "")
        if pull_needle not in url:
            continue
        parsed = parse_github_pull_url(url)
        same_pull = bool(parsed and parsed[0] == pr_repo and _norm_row_id(parsed[1]) == want_pr)
        if not same_pull and pr_repo.lower() not in url.lower():
            continue
        same_issue = (
            str(row.get("repo") or "") == str(issue_repo or "")
            and _norm_row_id(row.get("id")) == issue_norm
        )
        if not (same_pull or same_issue):
            continue
        seat = str(row.get("nick") or row.get("done_by") or "").strip()
        if seat and bobreport.parse_seat_nick(seat):
            return canonical_worker_nick(seat) or seat

    nick = str(done_nick or "").strip()
    if nick and bobreport.parse_seat_nick(nick):
        return canonical_worker_nick(nick) or nick
    return nick


def _append_unaccepted(doc: dict, claim: GitClaim, home: Path | None = None, **extra: str) -> str:
    # FR #6208: never enqueue (or refresh) rows for a persistently ignored repo.
    if home is not None:
        import focus_ignore as _fi_ignore

        if _fi_ignore.is_ignored(home, claim.repo):
            store_repo = canonical_queue_repo(claim.repo)
            doc["unaccepted"] = [
                r
                for r in (doc.get("unaccepted") or [])
                if not (
                    isinstance(r, dict)
                    and _fi_ignore.repo_match(store_repo, str(r.get("repo") or ""))
                )
            ]
            return "skipped"
    # FR #9821 / BOB-G3: digest gate rows must enter unaccepted even when
    # label:fr-digest is SKIP_FR or the digest carries hold - otherwise the
    # token-free Depends-on held-digest gate cannot see them (class of #9803).
    _digest_probe = {
        "task": "FR",
        "title": claim.title,
        "body": claim.body,
        "labels": list(claim.labels),
    }
    _is_digest_gate = claim.task == "FR" and bool(digest_issue_reason(_digest_probe))
    if claim.task == "FR":
        _skip_fr = issue_skip_fr_reason(
            title=claim.title, body=claim.body, labels=claim.labels, state=claim.state
        )
        if _skip_fr and not _is_digest_gate:
            # FR #9402: ops/monitor trackers drop any twin + clear offered_to.
            # Other skip_fr reasons keep prior behaviour (return skipped; digests
            # and needs-human paths are handled by prune / label mutation).
            if _skip_fr in ("ops_monitor_tracker", "tipform_restore_escalate"):
                store_repo = canonical_queue_repo(claim.repo)
                _clear_unaccepted_offer_pins_for_job(
                    home, doc, store_repo, claim.task, claim.id
                )
                doc["unaccepted"] = [
                    r
                    for r in (doc.get("unaccepted") or [])
                    if not (
                        isinstance(r, dict)
                        and _same(r, store_repo, claim.task, claim.id)
                    )
                ]
            return "skipped"
    if claim.task == "FR" and fr_is_superseded(doc, claim.repo, claim.id):
        return "skipped"  # FR #254: MRB / open implement PR supersedes FR
    # FR #4009: never enqueue FR for issues on hold (label or owner HOLD body stamp).
    # Drop any already-queued twin so webhook edited / resync clears the offer path.
    # FR #9402: also clear offered_to / seat-holds so the pin cannot block !assign.
    # BOB-G3 / FR #9821: held digests stay as gate records (enqueue, do not drop).
    if claim.task == "FR" and fr_hold_reason(
        title=claim.title, body=claim.body, labels=claim.labels
    ):
        if _is_digest_gate:
            pass  # fall through to append/refresh below
        else:
            store_repo = canonical_queue_repo(claim.repo)
            _clear_unaccepted_offer_pins_for_job(
                home, doc, store_repo, claim.task, claim.id
            )
            doc["unaccepted"] = [
                r
                for r in (doc.get("unaccepted") or [])
                if not (isinstance(r, dict) and _same(r, store_repo, claim.task, claim.id))
            ]
            return "skipped"
    # FR #8741: never enqueue park-only anti-omnibus FRs until human dispatch stamp.
    if claim.task == "FR" and fr_park_only_reason(
        title=claim.title, body=claim.body, labels=claim.labels
    ):
        store_repo = canonical_queue_repo(claim.repo)
        doc["unaccepted"] = [
            r
            for r in (doc.get("unaccepted") or [])
            if not (isinstance(r, dict) and _same(r, store_repo, claim.task, claim.id))
        ]
        return "skipped"
    # FR #3928 / #9080: never enqueue MRB for PRs on hold; purge any twin already queued
    # (done-fix requeue used to stamp labels=() and leave a held tip offerable).
    if claim.task == "MRB" and pr_hold_reason(
        title=claim.title, body=claim.body, labels=claim.labels
    ):
        store_repo = canonical_queue_repo(claim.repo)
        doc["unaccepted"] = [
            r
            for r in (doc.get("unaccepted") or [])
            if not (isinstance(r, dict) and _same(r, store_repo, claim.task, claim.id))
        ]
        return "skipped"
    store_repo = canonical_queue_repo(claim.repo)
    if _already(doc, store_repo, claim.task, claim.id):
        # refresh refs/line on existing unaccepted row (case-insensitive match, FR #3817)
        for row in doc["unaccepted"]:
            if _same(row, store_repo, claim.task, claim.id):
                row["repo"] = _prefer_repo_casing(str(row.get("repo") or ""), store_repo)
                # Do not wipe a useful GIT announce line with an empty resync/webhook line.
                new_line = str(claim.line or "")
                old_line = str(row.get("line") or "")
                if new_line.strip() or not old_line.strip():
                    row["line"] = claim.line
                row["event"] = claim.event
                row["action"] = claim.action
                if claim.refs:
                    row["refs"] = normalize_row_refs(claim.refs)
                if claim.title:
                    row["title"] = claim.title
                # FR #9543 / #2312: refresh body so late require_machine pin lines land.
                if claim.body:
                    row["body"] = _body_for_queue(claim.body)
                if claim.action in ("labeled", "unlabeled") or claim.labels:
                    row["labels"] = list(claim.labels)
                if claim.state:
                    row["state"] = str(claim.state).strip().lower()
                for k, v in extra.items():
                    if not v:
                        continue
                    # FR #2623: keep the true implementer when a citing DONE refreshes the MRB.
                    if k in _IMPLEMENTER_KEEP_KEYS and str(row.get(k) or "").strip():
                        continue
                    # FR #9475: never persist refs as a comma-joined string.
                    if k == "refs":
                        row["refs"] = normalize_row_refs(v)
                        continue
                    row[k] = v
                if claim.docs_mrb_orphan:
                    row["docs_mrb_orphan"] = "1"
                if claim.mrb_fix_offer:
                    row["mrb_fix_offer"] = "1"
                _stamp_require_machine(row, claim)
                return "duplicate"
        return "duplicate"
    seq = 1
    for row in doc["unaccepted"]:
        try:
            seq = max(seq, int(row.get("seq") or 0) + 1)
        except (TypeError, ValueError):
            continue
    row = {
        "repo": store_repo,
        "task": claim.task,
        "id": claim.id,
        "ts": _utc_now(),
        "line": claim.line,
        "event": claim.event,
        "action": claim.action,
        "seq": seq,
    }
    if claim.refs:
        row["refs"] = normalize_row_refs(claim.refs)
    if claim.title:
        row["title"] = claim.title
    if claim.body:
        row["body"] = _body_for_queue(claim.body)
    if claim.labels:
        row["labels"] = list(claim.labels)
    # FR #2340: persist issue state so closed rows can be purged/skipped offline.
    if claim.state:
        row["state"] = str(claim.state).strip().lower()
    if claim.docs_mrb_orphan:
        row["docs_mrb_orphan"] = "1"
    if claim.mrb_fix_offer:
        row["mrb_fix_offer"] = "1"
    for k, v in extra.items():
        if not v:
            continue
        # FR #9475: never persist refs as a comma-joined string (or raw split crumbs).
        if k == "refs":
            row["refs"] = normalize_row_refs(v)
            continue
        row[k] = v
    _stamp_require_machine(row, claim)
    doc["unaccepted"].append(row)
    return "added"


def _stamp_require_machine(row: dict, claim: GitClaim | None = None) -> None:
    """FR #587 / #1093: persist require_machine on enqueue/refresh when cues match.

    Hard issue pins always overwrite empty/unpin tokens. A real machine stamp is kept.
    Operator unpin (``any`` / ``none`` / ``*`` / ``-``) must survive title/body cues that
    merely *mention* ``require_machine=ce-priority-dev1`` as evidence (e.g. #1116) -
    otherwise monitor clears are wiped on the next offer/resync stamp.
    FR #9664: ``needs-<machine>`` labels still overwrite operator/monitor ``any``
    (label is the GitHub pin; bare any must not re-open wrong shops).
    """
    title = str((claim.title if claim else "") or row.get("title") or "")
    body = str((claim.body if claim else "") or row.get("body") or "")
    line = str((claim.line if claim else "") or row.get("line") or "")
    labels = list(claim.labels) if claim and claim.labels else (row.get("labels") or [])
    if isinstance(labels, str):
        labels = [labels]
    repo = str((claim.repo if claim else "") or row.get("repo") or "")
    ident = str((claim.id if claim else "") or row.get("id") or "")
    repo_l = repo.strip().lower()
    id_l = f"#{str(ident or '').strip().lstrip('#')}"
    hard = _REQUIRE_MACHINE_ISSUE_PINS.get((repo_l, id_l), "")
    # FR #4422: hard unpin wins over stamped ionos and title/body re-infer.
    if (repo_l, id_l) in _REQUIRE_MACHINE_ISSUE_UNPINS:
        row["require_machine"] = "any"
        return
    raw_stamp = str(row.get("require_machine") or "").strip().lower()
    stamped = fold_chair_host(raw_stamp)
    # FR #9680: rewrite legacy ionos/walrus stamps onto the configured live host.
    if stamped and (raw_stamp in _LEGACY_CHAIR_HOST_ALIASES or stamped != raw_stamp):
        row["require_machine"] = stamped
    if stamped and _is_retired_require_machine(stamped):
        stamped = "any"
        row["require_machine"] = "any"
    if stamped in {"*", "any", "none", "-"}:
        if hard and not _is_retired_require_machine(hard):
            row["require_machine"] = hard
            return
        # FR #9664: labels win over any (do not re-infer soft title/body cues).
        label_pin = infer_require_machine(
            title="", body="", labels=labels, line="", repo=repo, ident=ident
        )
        if label_pin and not _is_retired_require_machine(label_pin):
            row["require_machine"] = label_pin
        return
    req = infer_require_machine(
        title=title, body=body, labels=labels, line=line, repo=repo, ident=ident
    )
    harvest_lesson = bool(
        (claim and claim.harvest_lesson)
        or is_harvest_lesson_pr(title=title, labels=labels)
    )
    # FR #4512: bobiverse - clear stale text-cue stamps when inference is empty.
    # FR #4745: harvest-lesson rows clear sticky DEV1 (or other) stamps the same way.
    # FR #6592: operator !pin/!unpin stamps survive; do not wipe them to any.
    # FR #9664: needs-* labels still overwrite operator any (handled above).
    if req and _is_retired_require_machine(req):
        req = ""
    if repo_l == _BOBIVERSE_REPO_L or harvest_lesson:
        if _is_operator_require_machine(row):
            if hard and not _is_retired_require_machine(hard):
                row["require_machine"] = hard
                return
            # Label pin may still win when stamp drifted back to any mid-path.
            cur = fold_chair_host(str(row.get("require_machine") or "").strip().lower())
            if cur in {"*", "any", "none", "-", ""}:
                label_pin = infer_require_machine(
                    title="", body="", labels=labels, line="", repo=repo, ident=ident
                )
                if label_pin and not _is_retired_require_machine(label_pin):
                    row["require_machine"] = label_pin
            return
        if req:
            row["require_machine"] = req
        elif stamped and stamped not in {"*", "any", "none", "-"}:
            row["require_machine"] = "any"
        return
    if stamped:
        mid = bobreport.normalize_machine_id(stamped) or stamped
        if mid and mid not in _REQUIRE_MACHINE_NON_MACHINE and not _is_retired_require_machine(mid):
            return
    if req:
        row["require_machine"] = req


def _apply_label_mutation(doc: dict, claim: GitClaim, home: Path | None = None) -> str:
    """FR #3275: labeled/unlabeled update labels on matching rows; re-eval FR skip locally."""
    # FR #6208: ignored repos must not gain new unaccepted rows from label events.
    if home is not None:
        import focus_ignore as _fi_ignore

        if _fi_ignore.is_ignored(home, claim.repo):
            n = _remove_unaccepted(doc, claim.repo, claim.task, claim.id)
            return "removed" if n else "noop"
    updated = False
    found_unaccepted = False
    # FR #9848: detect digest hold removal before labels mutate in place.
    # FR #9832: detect newly applied digest hold before labels mutate in place.
    was_held_digest = False
    for bucket in ("unaccepted", "accepted"):
        for row in doc.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            if not _same(row, claim.repo, claim.task, claim.id):
                continue
            if bucket == "unaccepted":
                found_unaccepted = True
            if claim.task == "FR" and digest_issue_reason(row):
                labs_prev = {
                    str(x).strip().lower()
                    for x in (row.get("labels") or [])
                    if str(x).strip()
                }
                if "hold" in labs_prev or "on-hold" in labs_prev:
                    was_held_digest = True
            row["labels"] = list(claim.labels)
            row["action"] = claim.action
            row["event"] = claim.event
            if claim.title:
                row["title"] = claim.title
            if claim.body:
                row["body"] = _body_for_queue(claim.body)
            if claim.state:
                row["state"] = str(claim.state).strip().lower()
            _stamp_require_machine(row, claim)
            updated = True

    if claim.task == "FR":
        skip = issue_skip_fr_reason(
            title=claim.title, body=claim.body, labels=claim.labels, state=claim.state
        )
        # BOB-G3 / FR #9821: digest gate records stay queued even when held /
        # fr-digest SKIP_FR. If the digest was never enqueued (old skip path),
        # backfill it so Depends-on children see hold without GitHub fetch.
        _digest_probe = {
            "task": "FR",
            "title": claim.title,
            "body": claim.body,
            "labels": list(claim.labels),
        }
        if digest_issue_reason(_digest_probe):
            labs_now = {
                str(x).strip().lower() for x in (claim.labels or []) if str(x).strip()
            }
            now_held = "hold" in labs_now or "on-hold" in labs_now
            # FR #9832: hold newly applied -> clear child offers/accepted pins now.
            if (
                now_held
                and not was_held_digest
                and str(claim.action or "").strip().lower() in ("labeled", "edited")
            ):
                cleared = clear_offers_for_held_digest_children(
                    home, doc, claim.repo, claim.id
                )
                if cleared:
                    updated = True
                    notes = doc.get("stand_down")
                    if not isinstance(notes, list):
                        notes = []
                        doc["stand_down"] = notes
                    notes.append(
                        {
                            "channel": "#bobiverse",
                            "text": (
                                f"hold {claim.repo}#{str(claim.id).lstrip('#')}: "
                                f"cleared {len(cleared)} Depends-on child offer(s) "
                                "(FR #9832)"
                            ),
                        }
                    )
                    if len(notes) > 20:
                        doc["stand_down"] = notes[-20:]
            # FR #9848: parent digest unhold -> strip hold from ordinary children.
            if (
                was_held_digest
                and not now_held
                and str(claim.action or "").strip().lower()
                in ("unlabeled", "edited", "labeled")
            ):
                stripped = strip_hold_from_digest_children(
                    home, doc, claim.repo, claim.id
                )
                if stripped:
                    updated = True
                    notes = doc.get("stand_down")
                    if not isinstance(notes, list):
                        notes = []
                        doc["stand_down"] = notes
                    notes.append(
                        {
                            "channel": "#bobiverse",
                            "text": (
                                f"unhold {claim.repo}#{str(claim.id).lstrip('#')}: "
                                f"stripped hold from {len(stripped)} Depends-on "
                                f"child(ren) (FR #9848)"
                            ),
                        }
                    )
                    if len(notes) > 20:
                        doc["stand_down"] = notes[-20:]
            if (
                not found_unaccepted
                and not repo_archived_for_queue(claim.repo)
            ):
                ch = _append_unaccepted(doc, claim, home=home)
                if ch == "added":
                    return "added"
                if ch == "duplicate":
                    return "updated"
                if ch == "skipped":
                    return "noop"
            return "updated" if updated else "noop"
        # FR #9402: hold (and skip/ops-tracker) must drop the unaccepted row and
        # clear offered_to / seat-holds - label mutation used to stamp hold in
        # place and leave the ghost pin (class of #9376 / flamingo busy refuse).
        # Keep fr_hold_reason beside _remove_unaccepted so FR #8811 wire pin
        # classifies this as hold-drop-only (not an offer site).
        hold = fr_hold_reason(
            title=claim.title, body=claim.body, labels=claim.labels
        )
        if skip or hold:
            cleared = _clear_unaccepted_offer_pins_for_job(
                home, doc, claim.repo, "FR", claim.id
            )
            n = _remove_unaccepted(doc, claim.repo, "FR", claim.id)
            if n or cleared:
                return "removed"
            return "updated" if updated else "noop"
        if not found_unaccepted and not repo_archived_for_queue(claim.repo):
            ch = _append_unaccepted(doc, claim, home=home)
            if ch == "skipped":
                return "noop"
            if ch == "added":
                return "added"
            return "updated" if updated or ch == "duplicate" else "noop"
        return "updated" if updated else "noop"

    # MRB: mutate existing rows. FR #4955: if opened missed the queue, a later
    # labeled event on a lesson(book): tip (not draft) backfills the MRB row.
    # Product PRs and stray harvest-lesson labels still do not invent a row.
    if (
        not found_unaccepted
        and claim.harvest_lesson
        and str(claim.state or "open").strip().lower() == "open"
        and not repo_archived_for_queue(claim.repo)
    ):
        extra: dict[str, str] = {
            "url": f"https://github.com/{claim.repo}/pull/{str(claim.id).lstrip('#')}",
        }
        # FR #8095: stamp filing seat on labeled backfill (opened may have missed
        # harvest-lesson; without author_seat the tip self-offers to the harvester).
        opener = str(claim.opened_by or "").strip() or lesson_pr_opener_seat(claim.body)
        if opener:
            extra["author_seat"] = opener
            extra["implementer_seat"] = opener
        ch = _append_unaccepted(doc, claim, home=home, **extra)
        if ch == "skipped":
            return "noop"
        for r in doc.get("unaccepted") or []:
            if _same(r, claim.repo, "MRB", claim.id):
                _heal_lesson_mrb_row(r, opener)
                break
        if ch == "added":
            return "added"
        return "updated" if updated or ch == "duplicate" else "noop"
    return "updated" if updated else "noop"


def _apply_claim_to_doc(doc: dict, claim: GitClaim, home: Path | None = None) -> str:
    """Mutate queue doc for one claim. Returns added|removed|updated|duplicate|noop|error.

    ``home`` (FR #4695) lets reopen requeue clear the seat-ledger ``fr_done`` stamp.
    """
    if claim.task not in TASK_KINDS and claim.action not in (
        "closed",
        "edited",
        "labeled",
        "unlabeled",
    ):
        return "error"
    ev, action = claim.event, claim.action
    changed = "noop"

    if ev in ("issues", "pull_request") and action in ("labeled", "unlabeled"):
        return _apply_label_mutation(doc, claim, home=home)

    if ev == "issues" and action in ("opened", "reopened"):
        _opened_digest = bool(
            digest_issue_reason(
                {
                    "task": "FR",
                    "title": claim.title,
                    "body": claim.body,
                    "labels": list(claim.labels),
                }
            )
        )
        if issue_skip_fr_reason(
            title=claim.title, body=claim.body, labels=claim.labels, state=claim.state
        ) and not _opened_digest:
            changed = "noop"
        elif action == "reopened":
            # FR #4373: leave done, clear pins, stamp history, re-enter unaccepted.
            # FR #4695: also clear fr_done so seats are not held until !resync.
            # FR #6208: ignored repos stay out of unaccepted.
            if home is not None:
                import focus_ignore as _fi_ignore

                if _fi_ignore.is_ignored(home, claim.repo):
                    return "noop"
            changed = requeue_reopened_issue(
                doc,
                claim,
                via="webhook",
                actor=str(claim.opened_by or ""),
                home=home,
            )
            if changed == "skipped":
                changed = "noop"
        else:
            _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"UAT", "PR"})
            changed = _append_unaccepted(doc, claim, home=home)
            if changed == "skipped":
                changed = "noop"
    elif ev == "issues" and action == "closed":
        n = _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"FR", "PR"})
        before = len(doc["unaccepted"])
        doc["unaccepted"] = [
            r for r in doc["unaccepted"]
            if not (r.get("repo") == claim.repo and r.get("id") == claim.id and r.get("task") == "UAT"
                    and r.get("action") != "uat")
        ]
        n += before - len(doc["unaccepted"])
        # FR #4624: stamp accepted FR/PR rows state=closed (seat keeps ACC until DONE;
        # if the seat departs, release must not resurrect an unstamped offerable FR).
        # FR #4851: nick-held ACC also gets cancel_pending + one shop CANCEL; digest
        # stays doing until the seat NACKs (do not clear_seat_doing here).
        stamped = 0
        actor = str(getattr(claim, "actor", "") or "").strip()
        for row in doc.get("accepted") or []:
            if not isinstance(row, dict):
                continue
            task_u = str(row.get("task") or "").upper()
            if task_u not in ("FR", "PR"):
                continue
            if not _same(row, claim.repo, task_u, claim.id):
                continue
            row["state"] = "closed"
            if actor:
                row["closed_by"] = actor
            if _seat_holder_nick(row):
                row["cancel_pending"] = True
                if home is not None:
                    with contextlib.suppress(Exception):
                        enqueue_seat_cancel(home, row, actor=actor)
            stamped += 1
        if n:
            changed = "removed"
        elif stamped:
            changed = "updated"
        else:
            changed = "noop"

    elif ev == "pull_request" and action in (
        "opened",
        "ready_for_review",
        "edited",
        "synchronize",
    ):
        # FR #6208: persistent !ignore blocks late synchronize / reopen enqueue.
        if home is not None:
            import focus_ignore as _fi_ignore

            if _fi_ignore.is_ignored(home, claim.repo):
                n_drop = 0
                for task_u in ("MRB", "FIX", "PR", "UAT"):
                    n_drop += _remove_unaccepted(doc, claim.repo, task_u, claim.id)
                return "removed" if n_drop else "noop"
        # FR #4827: original seat's PR closes the FR the ack-stale requeue handed to someone else.
        _prune_stale_requeue_duplicate(doc, claim)
        if claim.harvest_lesson:
            implementer = claim.opened_by  # lesson PR author = opener, never a cited FR's implementer
        else:
            # FR #4854: pass pr_id so Refs to a different result PR cannot stamp author_seat.
            implementer = fr_implementer_seat_from_doc(
                doc, claim.repo, claim.refs, pr_id=claim.id
            )
        for ref in claim.refs:
            _remove_unaccepted_tasks(doc, claim.repo, ref, {"FR", "PR", "UAT"})
        extra: dict[str, str] = {}
        if claim.refs:
            extra["refs"] = ",".join(claim.refs)
        extra["url"] = (
            f"https://github.com/{claim.repo}/pull/{str(claim.id).lstrip('#')}"
        )
        if implementer:
            extra["author_seat"] = implementer
            extra["implementer_seat"] = implementer
        if claim.docs_mrb_orphan:
            extra["docs_mrb_orphan"] = "1"
        if claim.mrb_fix_offer:
            extra["mrb_fix_offer"] = "1"
        # FR #4929: synchronize after a prior MRB PASS must clear done[] / mrb_done
        # before append; otherwise purge drops the new row while FIX is still ACC.
        if action == "synchronize":
            ensure_mrb_requeued_after_head_move(
                doc,
                home,
                repo=claim.repo,
                pr=claim.id,
                url=extra["url"],
                reason="synchronize",
            )
            # Refresh stamps on the row ensure just (re)queued.
            for r in doc["unaccepted"]:
                if not _same(r, claim.repo, "MRB", claim.id):
                    continue
                if claim.title:
                    r["title"] = claim.title
                if claim.body:
                    r["body"] = _body_for_queue(claim.body)
                if claim.refs:
                    r["refs"] = normalize_row_refs(claim.refs)
                for k, v in extra.items():
                    if not v:
                        continue
                    if k in _IMPLEMENTER_KEEP_KEYS and str(r.get(k) or "").strip():
                        continue
                    # FR #9475: never persist refs as a comma-joined string.
                    if k == "refs":
                        r["refs"] = normalize_row_refs(v)
                        continue
                    r[k] = v
                if claim.harvest_lesson:
                    _heal_lesson_mrb_row(r, claim.opened_by)
            # FR #4604: live FIX nicks become author_seats on the requeued MRB.
            for row in doc.get("accepted") or []:
                if not isinstance(row, dict):
                    continue
                if str(row.get("task") or "").upper() != "FIX":
                    continue
                if not _same(row, claim.repo, "FIX", claim.id):
                    continue
                nick = str(row.get("nick") or row.get("accepted_by") or "").strip()
                if nick:
                    stamp_fix_seats_on_mrb_rows(doc, claim.repo, claim.id, nick)
            changed = "updated"
        else:
            changed = _append_unaccepted(doc, claim, home=home, **extra)
            for r in doc["unaccepted"]:
                if not _same(r, claim.repo, "MRB", claim.id):
                    continue
                if not PULL_URL_RE.search(str(r.get("url") or "")):
                    r["url"] = extra["url"]
                if claim.harvest_lesson:
                    _heal_lesson_mrb_row(r, claim.opened_by)
                elif implementer and not row_author_seats(r):
                    r["author_seat"] = implementer
                    r["implementer_seat"] = implementer

    elif ev == "pull_request" and action == "closed":
        _remove_unaccepted(doc, claim.repo, "MRB", claim.id)
        # FR #4682: FIX rows target the same PR id; drop them with the pull.
        _remove_unaccepted(doc, claim.repo, "FIX", claim.id)
        _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"UAT", "PR"})
        if claim.merged:
            # FR #2375: move any accepted MRB for this PR into done (lost webhook race /
            # self-authored fix PR must not stay ACC and re-offer after merge).
            # FR #4682: same for accepted FIX (seat stuck NAK busy after merge).
            kept_acc: list[dict] = []
            done = doc.setdefault("done", [])
            for row in doc.get("accepted") or []:
                if not isinstance(row, dict):
                    continue
                task_u = str(row.get("task") or "").upper()
                if (
                    str(row.get("repo") or "") == claim.repo
                    and task_u in ("MRB", "FIX")
                    and str(row.get("id") or "") == claim.id
                ):
                    fin = dict(row)
                    fin["result"] = "MERGED"
                    fin["merged"] = True
                    fin["done_ts"] = _utc_now()
                    fin["state"] = "closed"
                    done.append(fin)
                    continue
                kept_acc.append(row)
            doc["accepted"] = kept_acc
            if len(done) > DONE_CAP:
                doc["done"] = done[-DONE_CAP:]
            for ref in claim.refs:
                _remove_unaccepted_tasks(doc, claim.repo, ref, {"FR", "PR", "MRB", "UAT"})
            if is_mrb_fix_pr_title(str(claim.title or claim.line or "")):
                _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"UAT", "MRB", "FR", "PR"})
            changed = "updated"
        else:
            # FR #2650: closed-unmerged must move ACC MRB to done as CLOSED (not leave
            # it for _purge_dead_mrb_accepted to stamp MERGED).
            # FR #4682: same for accepted FIX.
            kept_acc_cu: list[dict] = []
            done_cu = doc.setdefault("done", [])
            moved_cu = False
            for row in doc.get("accepted") or []:
                if not isinstance(row, dict):
                    continue
                task_u = str(row.get("task") or "").upper()
                if (
                    str(row.get("repo") or "") == claim.repo
                    and task_u in ("MRB", "FIX")
                    and str(row.get("id") or "") == claim.id
                ):
                    fin = dict(row)
                    fin["result"] = "CLOSED"
                    fin["merged"] = False
                    fin["done_ts"] = _utc_now()
                    fin["state"] = "closed"
                    done_cu.append(fin)
                    moved_cu = True
                    continue
                kept_acc_cu.append(row)
            if moved_cu:
                doc["accepted"] = kept_acc_cu
                if len(done_cu) > DONE_CAP:
                    doc["done"] = done_cu[-DONE_CAP:]
            for ref in claim.refs:
                # FR #4656: Refs often name another PR or a closed issue. Requeue only
                # an open issue that was already in done (FR #4373).
                skip = closed_unmerged_ref_skip_reason(doc, claim.repo, ref)
                if skip:
                    print(skip, flush=True)
                    continue
                fr = GitClaim(
                    repo=claim.repo,
                    task="FR",
                    id=ref,
                    event="issues",
                    action="reopened",
                    line=claim.line,
                )
                # FR #4695: clear fr_done when closed-unmerged PR requeues the issue.
                requeue_reopened_issue(doc, fr, via="webhook", actor="", home=home)
            changed = "updated"
    else:
        changed = _append_unaccepted(doc, claim, home=home)
    return changed


def apply_queue_event(home: Path, claim: GitClaim) -> str:
    """Apply one deterministic queue transition.

    Returns added|removed|updated|duplicate|noop|error|error:queue-*.
    FR #1811: distinguish lock/read/write failures, spool on failure, skip noop rewrite,
    drain pending under the same lock.
    """
    claim = replace(claim, repo=canonical_queue_repo(claim.repo))
    if claim.task not in TASK_KINDS and claim.action not in ("closed", "edited"):
        return "error"
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                _spool_pending(home, claim)
                return "error:queue-read"

            dirty = False
            # FR #6502: keep drained claims so a later write failure can re-spool them
            # (rename-aside pop already removed them from the pending file).
            drained: list[GitClaim] = list(_pop_all_pending(home))
            for pending in drained:
                ch = _apply_claim_to_doc(doc, pending, home=home)
                if ch == "error":
                    _spool_pending(home, pending)
                elif ch != "noop":
                    dirty = True

            changed = _apply_claim_to_doc(doc, claim, home=home)
            if changed == "error":
                # Persist any drained pending already merged into doc, then spool the
                # failing claim so it is not dropped (FR #1811 / #6502).
                if dirty:
                    try:
                        _write_queue(queue_path(home), doc)
                    except OSError:
                        for p in drained:
                            _spool_pending(home, p)
                _spool_pending(home, claim)
                return "error"
            if changed != "noop":
                dirty = True

            if not dirty:
                return changed
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                for p in drained:
                    _spool_pending(home, p)
                _spool_pending(home, claim)
                return "error:queue-write"
            # FR #2375 / #1323: ledger hold so MERGED PRs cannot re-offer if unaccepted leaks back.
            # FR #2650: also hold closed-unmerged (ACC moved to CLOSED) so harvest receipts
            # cannot bounce back onto the offer queue after FAIL-superseded close.
            if claim.event == "pull_request" and claim.action == "closed":
                with contextlib.suppress(Exception):
                    stamp_mrb_done(home, claim.repo, claim.id)
                # FR #4415: drop seat holds for the closed PR so idle seats are not
                # stuck busy (held ...) after the queue row is removed.
                # FR #4682: FIX holds too (same PR id).
                with contextlib.suppress(Exception):
                    for _t in ("MRB", "FIX", "UAT", "PR", "FR"):
                        _clear_job_seat_holds_unlocked(home, claim.repo, _t, claim.id)
                # FR #4682 / #1430: idle digest seats still showing FIX/MRB on this PR.
                ident = str(claim.id or "").lstrip("#")
                if ident:
                    with contextlib.suppress(Exception):
                        for row in (doc.get("done") or []):
                            if not isinstance(row, dict):
                                continue
                            if str(row.get("repo") or "") != claim.repo:
                                continue
                            if str(row.get("id") or "").lstrip("#") != ident:
                                continue
                            if str(row.get("task") or "").upper() not in ("MRB", "FIX"):
                                continue
                            seat = str(
                                row.get("nick")
                                or row.get("accepted_by")
                                or row.get("offered_to")
                                or ""
                            ).strip()
                            if seat:
                                bobreport.clear_seat_doing(
                                    home, seat, only_if_work_contains=ident
                                )
            elif claim.event == "issues" and claim.action == "closed":
                # FR #4415: same for closed issues (FR/PR rows dropped).
                with contextlib.suppress(Exception):
                    for _t in ("FR", "PR", "UAT"):
                        _clear_job_seat_holds_unlocked(home, claim.repo, _t, claim.id)
                # FR #4624: ledger fr_done so a leaked unaccepted row cannot survive
                # resync while the issue stays closed (mirrors stamp_mrb_done on PR close).
                with contextlib.suppress(Exception):
                    def _fd(led: dict) -> None:
                        led.setdefault("fr_done", {})[
                            _lkey(claim.repo, claim.id)
                        ] = _utc_now()

                    _ledger_update(home, _fd)
                # FR #9552: last-child close of an unheld fr-digest (ticket-closure peer).
                with contextlib.suppress(Exception):
                    import fr_digest_auto_close as _fac

                    _fac.on_issue_closed(
                        str(claim.repo or ""),
                        str(claim.id or "").lstrip("#"),
                        str(getattr(claim, "body", "") or ""),
                    )
            return changed
    except TimeoutError:
        _spool_pending(home, claim)
        return "error:queue-lock-timeout"
    except OSError:
        _spool_pending(home, claim)
        return "error:queue-write"



def canonical_worker_nick(nick: str) -> str | None:
    """Always ``<machine>-<pid>`` for legacy ``w-<short>-<pid>`` or real seat nicks (#39 gap 1).

    Must NOT return the short ``w-io-<pid>`` form: ledger ``giveup`` keys and row
    ``giveup_seats`` store ``<machine>-<pid>``. Returning the short form made
    ``w-io-*`` / ``w-mh-*`` !bored seats bypass GIVEUP / needs_human / ledger
    blocks and re-offer needs-mrb1 FRs forever while full-form seats got empty.
    """
    seat = bobreport.parse_seat_nick(nick)
    if seat:
        return f"{seat[0]}-{seat[1]}"
    legacy = bobreport.parse_worker_nick(nick)
    if legacy:
        return f"{legacy[0]}-{legacy[1]}"
    # Fallback when machine is not yet in seat_machine_ids() (cold digest / tests):
    # still accept already-canonical ``<machine>-<pid>`` (MRB #1278).
    n = (nick or "").strip().lower()
    if n and not n.startswith("bob-") and not n.startswith("w-"):
        m = re.match(r"^([a-z0-9][a-z0-9_.-]*)-(\d+)$", n)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return None


def giveup_seat_set(row: dict) -> set[str]:
    """Canonical lowercase seat nicks from ``row['giveup_seats']`` (comma list)."""
    out: set[str] = set()
    for raw in str(row.get("giveup_seats") or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        out.add((canonical_worker_nick(raw) or raw).strip().lower())
    return out


def drop_nick_from_giveup_seats(row: dict, nick: str) -> None:
    """Remove one seat from giveup_seats. FR #8344: ACK means they took the work.

    A busy NACK or unanswered-offer stamp can list a seat that later accepts.
    Leaving them in giveup_seats makes all-gave-up fire while they still hold the row.
    """
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me or not isinstance(row, dict):
        return
    kept: list[str] = []
    seen: set[str] = set()
    for raw in str(row.get("giveup_seats") or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        canon = (canonical_worker_nick(raw) or raw).strip()
        key = canon.lower()
        if not key or key == me or key in seen:
            continue
        seen.add(key)
        kept.append(canon)
    if kept:
        row["giveup_seats"] = ",".join(kept)
    else:
        row.pop("giveup_seats", None)


def _seat_machine_id(nick: str) -> str:
    """Folded machine id from a seat nick, or empty."""
    p = bobreport.parse_seat_nick(nick) or bobreport.parse_worker_nick(nick)
    if not p:
        c = canonical_worker_nick(nick)
        p = bobreport.parse_seat_nick(c) if c else None
    if not p:
        # FR #8768: cold digest roster - peel ``<machine>-<pid>`` without parse_seat_nick.
        c = (canonical_worker_nick(nick) or nick or "").strip().lower()
        m = re.match(r"^([a-z0-9][a-z0-9_.-]*)-(\d+)$", c)
        if not m:
            return ""
        try:
            return bobreport.fold_machine_id(m.group(1))
        except Exception:
            return m.group(1)
    try:
        return bobreport.fold_machine_id(p[0])
    except Exception:
        return str(p[0] or "").strip().lower()


def _live_nick_set(live: set[str] | None) -> set[str]:
    out: set[str] = set()
    for n in live or ():
        c = (canonical_worker_nick(str(n)) or str(n)).strip().lower()
        if c:
            out.add(c)
    return out


def nick_inherits_dead_seat(
    nick: str,
    stored: str,
    live: set[str] | None,
) -> bool:
    """True when `nick` succeeds a recycled `stored` seat on the same machine.

    Used for **UAT** dead-author inherit (FR #4336) and related author stamps.
    Give-up / cooldown matching is exact-seat only (FR #5088) and does not call
    this helper. When `stored` is not live and `nick` is the **sole** live seat
    on that machine, treat as recycle successor. Sibling live seats on the same
    machine do not inherit (FR #2604 / #4604).
    """
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    st = (canonical_worker_nick(stored) or stored or "").strip().lower()
    if not me or not st or me == st:
        return False
    live_l = _live_nick_set(live)
    if not live_l:
        return False
    if st in live_l:
        return False
    me_mid = _seat_machine_id(me)
    st_mid = _seat_machine_id(st)
    if not (me_mid and st_mid and me_mid == st_mid):
        return False
    peers = {n for n in live_l if _seat_machine_id(n) == me_mid}
    return peers == {me}


def nick_in_giveup_seats(
    row: dict,
    nick: str,
    live: set[str] | None = None,
) -> bool:
    """True when `nick` (any form) is listed in the row's giveup_seats.

    FR #5088: exact-seat match only (canonical nick / short form). ``live`` is
    accepted for call-site compatibility but does **not** inherit a dead
    predecessor's give-up to a recycled same-machine nick --- that blocked
    ``!bored`` after seat recycle while ``!assign`` (no live) still offered.
    ``needs_human`` stays global for auto-offer (FR #4336). UAT dead-author
    inherit remains in ``review_blocked_for_author`` via ``nick_inherits_dead_seat``.
    """
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    seats = giveup_seat_set(row)
    if not seats:
        return False
    if me in seats:
        return True
    if (nick or "").strip().lower() in {
        x.strip().lower() for x in str(row.get("giveup_seats") or "").split(",") if x.strip()
    }:
        return True
    # FR #5088: do not call nick_inherits_dead_seat here (live ignored for give-up).
    _ = live
    return False



def _channel(target: str) -> str:
    return bobreport.normalize_channel(target).lower()


def worker_shop_channel(nick: str) -> str | None:
    parsed = bobreport.parse_seat_nick(nick)
    if not parsed:
        return None
    try:
        return bobreport.shop_channel(parsed[0]).lower()
    except ValueError:
        return None


def _worker_list_busy_work(ent: dict, nick: str) -> str:
    """Non-empty work string when worker_list still shows offered/doing for nick."""
    n = (nick or "").strip().lower()
    if not n or not isinstance(ent, dict):
        return ""
    for row in ent.get("worker_list") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("nick") or "").strip().lower() != n:
            continue
        state = str(row.get("state") or "").strip().lower()
        # Digest rows use ``work``; tolerate ``working_on`` aliases (FR #5889).
        work = str(row.get("work") or row.get("working_on") or "").strip()
        # FR #4454: state=offered is Jeeves's own pending offer, not seat work.
        if state == "offered":
            continue
        # FR #8137: waiting (rebase/merge) still counts as busy work for tray/digest.
        if state in ("doing", "busy", "accepted", "waiting") or work:
            return work or state
    return ""


def worker_working_on(home: Path, nick: str) -> str:
    """Digest working_on for this worker pid. Empty if the worker is absent.

    FR #1714: when ``worker_list`` is already idle but the legacy pid ``workers``
    map still has ``working_on`` / ``running``, heal the map (and machine roll)
    so ``!bored`` does not nak-busy forever after a lost DONE.
    """
    parsed = bobreport.parse_seat_nick(nick)
    if not parsed:
        return ""
    mid, pid = parsed
    doc = bobreport.load_digest(_root(home))
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    ent = machines.get(mid) if isinstance(machines.get(mid), dict) else {}
    if not isinstance(ent, dict):
        return ""
    list_busy = _worker_list_busy_work(ent, nick)
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    row = workers.get(str(pid))
    map_wo = ""
    if isinstance(row, dict):
        map_wo = str(row.get("working_on") or "").strip()
        map_state = str(row.get("state") or "").strip().lower()
        if not map_wo and map_state in ("running", "doing", "offered", "busy"):
            map_wo = map_state
    if map_wo and not list_busy:
        # FR #3867: map still names an unaccepted queue row → lost ACK across restart;
        # keep the evidence (do not FR #1714-clear) so reconcile can promote to accepted.
        with contextlib.suppress(Exception):
            if unaccepted_matches_digest_work(home, map_wo):
                return map_wo
        # Split brain: list idle, map busy → clear map (CAST IRON: do not clear when list busy).
        needle = ""
        m = _MRB_DOING_RX.search(map_wo)
        if m:
            needle = str(int(m.group(2)))
        with contextlib.suppress(Exception):
            bobreport.clear_seat_doing(
                home, nick, only_if_work_contains=needle or map_wo[:40]
            )
        return ""
    if list_busy:
        # Prefer real work text; state-only busy still counts (FR #5889 skip).
        if list_busy not in ("doing", "offered", "busy", "accepted"):
            return list_busy
        return map_wo or list_busy
    return map_wo


def pending_path(home: Path) -> Path:
    return _root(home) / PENDING_NAME


def _claim_to_pending_dict(claim: GitClaim) -> dict:
    return {
        "repo": claim.repo,
        "task": claim.task,
        "id": claim.id,
        "event": claim.event,
        "action": claim.action,
        "line": claim.line,
        "refs": list(claim.refs or ()),
        "merged": claim.merged,
        "title": claim.title,
        "body": claim.body,
        "labels": list(claim.labels or ()),
        "state": claim.state,
    }


def _claim_from_pending_dict(d: dict) -> GitClaim | None:
    if not isinstance(d, dict):
        return None
    repo = str(d.get("repo") or "").strip()
    task = str(d.get("task") or "").strip()
    ident = str(d.get("id") or "").strip()
    if not repo or not ident:
        return None
    refs = d.get("refs") or ()
    if isinstance(refs, str):
        refs = [x for x in refs.split(",") if x]
    labels = d.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    merged = d.get("merged")
    if merged is not None and not isinstance(merged, bool):
        merged = None
    return GitClaim(
        repo=repo,
        task=task or "FR",
        id=ident,
        event=str(d.get("event") or ""),
        action=str(d.get("action") or ""),
        line=str(d.get("line") or ""),
        refs=tuple(str(x) for x in refs),
        merged=merged,
        title=str(d.get("title") or ""),
        body=str(d.get("body") or ""),
        labels=tuple(str(x) for x in labels),
        state=str(d.get("state") or ""),
    )


_spool_seq = 0
_spool_seq_lock = threading.Lock()


def _next_spool_token() -> str:
    """Process-unique sidecar token. time_ns repeats under a tight Windows loop."""
    global _spool_seq
    with _spool_seq_lock:
        _spool_seq += 1
        n = _spool_seq
    return f"{os.getpid()}-{n}-{threading.get_ident()}"


def _spool_pending(home: Path, claim: GitClaim) -> None:
    """Durable spool so lock/write failures do not drop webhook claims (FR #1811).

    FR #6502: write a unique sidecar file per claim. Concurrent TimeoutError
    paths used to append the same ``pending`` file without a lock; interleaved
    JSON lines were skipped on drain and rows vanished. Sidecars are drained by
    ``_pop_all_pending`` alongside any legacy shared pending file.
    """
    path = pending_path(home)
    line = json.dumps(_claim_to_pending_dict(claim), separators=(",", ":")) + "\n"
    payload = line.encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    # FR #7942: publish the side name only after the bytes are closed. A pop
    # that lists ``.side-*`` during os.open/write used to read an empty file
    # and unlink it. time.time_ns() also repeats on Windows, so a later
    # os.replace reused the same side name and erased an unread claim.
    for attempt in range(40):
        token = _next_spool_token()
        partial = path.with_name(f"{path.name}.partial-{token}")
        side = path.with_name(f"{path.name}.side-{token}")
        fd: int | None = None
        try:
            fd = os.open(str(partial), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, payload)
            os.close(fd)
            fd = None
            os.replace(str(partial), str(side))
            return
        except FileExistsError:
            continue
        except OSError:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            time.sleep(0.01 * (attempt + 1))
    raise OSError("pending sidecar was not published")


def _pending_sidecar_paths(home: Path) -> list[Path]:
    """FR #6502: recover `.side-*` files left when append spool failed under AV."""
    root = pending_path(home).parent
    name = pending_path(home).name
    if not root.is_dir():
        return []
    out: list[Path] = []
    try:
        for p in root.iterdir():
            if p.name.startswith(name + ".side-") and p.is_file():
                out.append(p)
    except OSError:
        return []
    return sorted(out)


def _pop_all_pending(home: Path) -> list[GitClaim]:
    """Drain the durable pending spool under the queue lock (FR #1811 / #6502).

    Atomically renames ``pending`` aside before reading so concurrent
    ``_spool_pending`` appends (TimeoutError path, outside the lock) land on a
    fresh file and are not deleted by unlink-after-read.
    """
    path = pending_path(home)
    out: list[GitClaim] = []
    drain: Path | None = None
    if path.exists():
        drain = path.with_name(f"{path.name}.drain-{os.getpid()}-{time.time_ns()}")
        try:
            os.replace(str(path), str(drain))
        except FileNotFoundError:
            drain = None
        except OSError:
            # Fallback: best-effort read+unlink (pre-#6502 behaviour).
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                raw = ""
            try:
                path.unlink()
            except OSError:
                pass
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                c = _claim_from_pending_dict(d)
                if c is not None:
                    out.append(c)
            drain = None
    if drain is not None:
        try:
            raw = drain.read_text(encoding="utf-8")
        except OSError:
            # Put the unread drain back so the next holder can retry.
            try:
                os.replace(str(drain), str(path))
            except OSError:
                pass
            raw = ""
            drain = None
        else:
            try:
                drain.unlink()
            except OSError:
                pass
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                c = _claim_from_pending_dict(d)
                if c is not None:
                    out.append(c)
    # FR #6502 / #7942: drain published sidecars. Leave an empty or torn
    # file in place so a writer that has not closed yet is not unlinked.
    for side in _pending_sidecar_paths(home):
        try:
            raw = side.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if not lines:
            continue
        parsed: list[GitClaim] = []
        torn = False
        for line in lines:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                torn = True
                break
            c = _claim_from_pending_dict(d)
            if c is not None:
                parsed.append(c)
        if torn:
            continue
        try:
            side.unlink()
        except OSError:
            pass
        out.extend(parsed)
    return out


def _lock_wait_budget(timeout: float | None) -> float:
    """Seconds to wait for the disk git-claim lock.

    FR #9534: under pytest (no explicit ``BOB_GITCLAIM_LOCK_S``) default to 2s so a
    nested re-lock fails fast instead of burning ``--timeout=180`` per test.
    """
    if timeout is not None:
        return max(0.0, float(timeout))
    if os.environ.get("PYTEST_CURRENT_TEST") and "BOB_GITCLAIM_LOCK_S" not in os.environ:
        return 2.0
    return float(LOCK_WAIT_S)


@contextmanager
def _lock(home: Path, *, timeout: float | None = None):
    # FR #1993: same-process chair+HTTP share an RLock (no 30s disk wait between threads).
    # FR #2729: ``timeout`` (seconds) bounds the wait; TimeoutError when the lock is busy.
    try:
        import jeeves_locks

        inproc = jeeves_locks.inproc_queue_lock()
    except Exception:  # noqa: BLE001
        inproc = None
    if inproc is not None:
        if timeout is None:
            with inproc:
                yield
            return
        if not inproc.acquire(timeout=max(0.0, float(timeout))):
            raise TimeoutError("git-claim lock busy")
        try:
            yield
        finally:
            inproc.release()
        return
    root = _root(home)
    root.mkdir(parents=True, exist_ok=True)
    path = root / LOCK_NAME
    wait_s = _lock_wait_budget(timeout)
    deadline = time.time() + wait_s
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > max(30.0, LOCK_WAIT_S):
                    path.unlink()
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError("git-claim lock")
            time.sleep(0.02)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            path.unlink()
        except OSError:
            pass


def _empty_queue() -> dict:
    return {"v": 1, "unaccepted": [], "accepted": [], "done": []}


def _coerce_row(row: dict) -> dict | None:
    repo = repo_alias.canonicalize_repo(str(row.get("repo") or "").strip())
    task = str(row.get("task") or "").strip()
    ident = str(row.get("id") or "").strip()
    if not repo or task not in TASK_KINDS or not ID_RE.fullmatch(ident):
        return None
    out = {
        "repo": repo,
        "task": task,
        "id": ident,
        "ts": str(row.get("ts") or ""),
        "line": str(row.get("line") or ""),
        "event": str(row.get("event") or ""),
        "action": str(row.get("action") or ""),
    }
    try:
        out["seq"] = int(row.get("seq") or 0)
    except (TypeError, ValueError):
        out["seq"] = 0
    # author_seat/url: written by gh-Jeeves-style producers; needed by the MRB author rule and wire url (#39).
    # FR #265: implementer_seat + mrb_author_seat survive reload for UAT dual-seat block.
    # FR #180: title/labels/cooldown/needs_human must survive reload so offer/prune keep working.
    # accepted_by: ACC ownership for stale-busy heal (#2369 / MRB #2371) and ACC CLOSED purge (#2361).
    for key in ("nick", "worker",  # FR #6770: stored worker must survive reload (distinct from nick)
                "channel", "accepted_ts", "accepted_by", "offered_to", "offered_ts", "offered_channel",
                "offered_via",  # FR #2811: giveup-push sticky window
                "author_seat", "author_nick", "author", "implementer_seat", "mrb_author_seat", "mrb_fix_author_seat",
                "author_seats", "url", "title", "body", "state",
                "giveup_seats", "giveup_reason", "giveup_agent_kinds", "require_machine", "cooldown_until", "giveup_ts", "supersedes", "result", "done_ts", "done_by",
                "reconcile",  # FR #3742: LOST_DONE_RESTART vs STALE_BUSY audit
                "prior_holder",  # FR #4564: do not re-offer a lost DONE to the seat that held it
                # FR #4706 / #4585: FIX CI head SHA + failure signature must survive reload
                # FR #4718: seat that FAILed this MRB head must not be offered it again
                # FR #4857: main-side FIX stamp survives reload (belt with id/fail_signature)
                "pass_sha", "fail_signature", "check_run_id", "mrb_fail_by", "main_red_fix",
                # FR #8137: DONE MRB PASS awaiting merge/rebase provenance on done[]
                "awaiting", "mrb_pass_nick",
                # FR #6340: clean orphan docs/mrb pin offerable as one MRB
                "docs_mrb_orphan",
                # FR #8475: orphan / main-base fix(mrb-N) must survive reload
                "mrb_fix_offer"):
        if row.get(key):
            out[key] = str(row.get(key))
    # FR #7334: least-commit pick and the 5-minute stuck clock must survive reload.
    # FR #7338: per-seat commit counts for the fewest-commits recycle pick.
    counts = row.get("author_commit_counts")
    if isinstance(counts, dict):
        clean_counts = {}
        for key, val in counts.items():
            nick = str(key or "").strip()
            if not nick:
                continue
            try:
                clean_counts[nick] = int(val)
            except (TypeError, ValueError):
                continue
        if clean_counts:
            out["author_commit_counts"] = clean_counts
    # FR #9475: heal poisoned refs before copying no_eligible_* stamps.
    refs_raw = row.get("refs")
    refs_healed = False
    if refs_raw:
        refs_healed = _refs_need_heal(refs_raw)
        normalized = normalize_row_refs(refs_raw)
        if normalized:
            out["refs"] = normalized
    try:
        since = float(row.get("no_eligible_since") or 0)
    except (TypeError, ValueError):
        since = 0.0
    # Clear no_eligible_* when refs heal so false self-MRB deadlocks can recover.
    if not refs_healed:
        if since > 0:
            out["no_eligible_since"] = since
        # FR #7574: one no_eligible_reviewer report must survive queue reload.
        if row.get("no_eligible_reported"):
            out["no_eligible_reported"] = True
    if row.get("labels"):
        labs = row.get("labels")
        if isinstance(labs, list):
            out["labels"] = [str(x) for x in labs]
        else:
            out["labels"] = [str(labs)]
    # FR #4373: reopen notes (webhook / resync) must survive queue reload.
    if row.get("history"):
        hist = row.get("history")
        if isinstance(hist, list):
            out["history"] = [str(x) for x in hist if str(x).strip()][-20:]
        else:
            text = str(hist).strip()
            if text:
                out["history"] = [text]
    try:
        if row.get("giveup_count") is not None:
            out["giveup_count"] = int(row.get("giveup_count") or 0)
        if row.get("hard_ceiling_count") is not None:
            try:
                out["hard_ceiling_count"] = int(row.get("hard_ceiling_count") or 0)
            except (TypeError, ValueError):
                out["hard_ceiling_count"] = 0
    except (TypeError, ValueError):
        pass
    # FR #2309: sticky no-ACK rebroadcast counter + skip list must survive reload.
    try:
        if row.get("offered_count") is not None:
            out["offered_count"] = int(row.get("offered_count") or 0)
    except (TypeError, ValueError):
        pass
    if row.get("sticky_skip_seats"):
        skips = row.get("sticky_skip_seats")
        if isinstance(skips, list):
            out["sticky_skip_seats"] = [str(x) for x in skips if str(x).strip()]
        else:
            out["sticky_skip_seats"] = [str(skips)]
    # FR #9665: durable GIVEUP depends_open block must survive queue reload.
    dep_open = row.get("depends_open")
    if dep_open:
        if isinstance(dep_open, list):
            cleaned = [str(x).strip() for x in dep_open if str(x).strip()]
        else:
            cleaned = [str(dep_open).strip()] if str(dep_open).strip() else []
        if cleaned:
            out["depends_open"] = cleaned
    # FR #7966: per-seat unanswered-offer outcomes survive reload for the digest.
    if row.get("offer_refused_by"):
        refused = row.get("offer_refused_by")
        if isinstance(refused, list):
            out["offer_refused_by"] = [str(x) for x in refused if str(x).strip()]
        else:
            out["offer_refused_by"] = [str(refused)]
    outcomes = row.get("offer_outcomes")
    if isinstance(outcomes, list):
        clean_out = []
        for item in outcomes[-20:]:
            if not isinstance(item, dict):
                continue
            seat = str(item.get("seat") or "").strip()
            outcome = str(item.get("outcome") or "").strip()
            if not seat or not outcome:
                continue
            clean_out.append({
                "seat": seat,
                "outcome": outcome,
                "reason": str(item.get("reason") or "")[:200],
                "ts": str(item.get("ts") or ""),
            })
        if clean_out:
            out["offer_outcomes"] = clean_out
    unanswered = row.get("offer_unanswered")
    if isinstance(unanswered, dict):
        clean_un: dict[str, int] = {}
        for key, val in unanswered.items():
            nick = str(key or "").strip().lower()
            if not nick:
                continue
            try:
                clean_un[nick] = int(val)
            except (TypeError, ValueError):
                continue
        if clean_un:
            out["offer_unanswered"] = clean_un
    # FR #8924: refusal waves and the one escalation survive reload.
    try:
        waves = int(row.get("offer_refusal_waves") or 0)
    except (TypeError, ValueError):
        waves = 0
    if waves:
        out["offer_refusal_waves"] = waves
    escalated = str(row.get("offer_escalate_reason") or "").strip()
    if escalated:
        out["offer_escalate_reason"] = escalated
    # FR #8428: last seat that timed out. Idle push tries a different seat first.
    last_to = (canonical_worker_nick(str(row.get("offer_last_timeout_seat") or "")) or "").strip()
    if last_to:
        out["offer_last_timeout_seat"] = last_to
    # FR #8017: per-seat pre-ACK deterministic NACK cooldown must survive reload.
    nack_until = row.get("deterministic_nack_until")
    if isinstance(nack_until, dict):
        clean_nack: dict[str, str] = {}
        for key, val in nack_until.items():
            nick = (canonical_worker_nick(str(key)) or str(key) or "").strip()
            iso = str(val or "").strip()
            if nick and iso and _parse_iso_ts(iso) is not None:
                clean_nack[nick] = iso
        if clean_nack:
            out["deterministic_nack_until"] = clean_nack
    if row.get("repo_uat"):
        out["repo_uat"] = True
    if row.get("merged_prs"):
        mp = row.get("merged_prs")
        out["merged_prs"] = [str(x) for x in mp] if isinstance(mp, list) else [str(mp)]
    # Persist the raw stamp. Offer exceptions (FR #8628 / #8634) must not
    # drop it on reload or the infra-soft heal cannot see it.
    if _needs_human_flag(row):
        out["needs_human"] = True
    # FR #6592: operator !pin/!unpin flag must survive queue reload.
    if _is_operator_require_machine(row):
        out["require_machine_operator"] = "1"
    # FR #9554: tipform host-heal auto-pin flag + counter must survive reload.
    hh_flag = row.get("require_machine_host_heal")
    if isinstance(hh_flag, bool):
        if hh_flag:
            out["require_machine_host_heal"] = "1"
    elif str(hh_flag or "").strip().lower() in {"1", "true", "yes", "on"}:
        out["require_machine_host_heal"] = "1"
    try:
        if row.get("host_heal_giveup_count") is not None:
            out["host_heal_giveup_count"] = int(row.get("host_heal_giveup_count") or 0)
    except (TypeError, ValueError):
        pass
    if row.get("host_heal_pin_by"):
        out["host_heal_pin_by"] = str(row.get("host_heal_pin_by"))[:80]
    # FR #2939: one-shot announce when every live seat is self-UAT for repo UAT #0.
    if row.get("self_uat_escalated"):
        out["self_uat_escalated"] = True
    # FR #3400: orphan-ACK release marker (retry + prior ACK void note) must survive reload.
    if row.get("retry"):
        out["retry"] = True
    if row.get("note"):
        out["note"] = str(row.get("note"))
    # FR #4851: closed-mid-ACK cancel flags must survive reload until seat NACK.
    if row.get("cancel_pending"):
        out["cancel_pending"] = True
    if row.get("cancel_notified"):
        out["cancel_notified"] = True
    if row.get("closed_by"):
        out["closed_by"] = str(row.get("closed_by"))
    if row.get("cancel_reason"):
        out["cancel_reason"] = str(row.get("cancel_reason"))[:200]
    # FR #5317 / #5865 / #6434: CodeRabbit wait stamps must survive queue reload.
    if row.get("coderabbit"):
        out["coderabbit"] = str(row.get("coderabbit"))
    if row.get("review"):
        out["review"] = str(row.get("review"))
    if row.get("coderabbit_reason"):
        out["coderabbit_reason"] = str(row.get("coderabbit_reason"))[:200]
    if row.get("coderabbit_head_sha"):
        out["coderabbit_head_sha"] = str(row.get("coderabbit_head_sha"))
    # FR #6211 / #5865: current PR tip SHA must survive reload so CodeRabbit
    # new-head reset (stale ready on older SHA) still holds on !assign / !bored.
    if row.get("head_sha"):
        out["head_sha"] = str(row.get("head_sha"))
    if row.get("changed_files") is not None:
        out["changed_files"] = row.get("changed_files")
    try:
        raw_cr = row.get("coderabbit_wait_since")
        if raw_cr is not None and str(raw_cr).strip() != "":
            out["coderabbit_wait_since"] = float(raw_cr)
    except (TypeError, ValueError):
        pass
    return out


def is_repo_uat(row: dict) -> bool:
    """t853u / FR #818 / #821: UAT is per REPO only.

    Requires task=UAT, ``repo_uat``, id ``#0``, and a title/line that is not an
    mrb-*-fix / fix(mrb-N) PR title (poisoned leftover rows).
    """
    if _canon_task(row) != "UAT":
        return False
    if not bool(row.get("repo_uat")):
        return False
    ident = str(row.get("id") or "").strip().lstrip("#")
    if ident != "0":
        return False
    titleish = " ".join([str(row.get("line") or ""), str(row.get("title") or "")])
    if is_mrb_fix_pr_title(titleish):
        return False
    return True


def repo_has_uat_release_to_build(repo: str, *, home: Path | None = None) -> bool:
    """FR #9382: UAT #0 only for repos whose PASS path builds/publishes a release."""
    try:
        import uat_release

        return bool(uat_release.repo_has_release_to_build(repo, home=home))
    except Exception:
        return False


def uat_no_release_to_build_reason(row: dict, *, home: Path | None = None) -> str | None:
    """Return ``no-release-to-build`` when this UAT row must not be offered/assigned."""
    if _canon_task(row) != "UAT":
        return None
    if not is_repo_uat(row):
        return None
    repo = str(row.get("repo") or "").strip()
    if repo_has_uat_release_to_build(repo, home=home):
        return None
    try:
        import uat_release

        return str(uat_release.NO_RELEASE_TO_BUILD)
    except Exception:
        return "no-release-to-build"


def _mrb_fix_offer_stamped(row: dict) -> bool:
    """True when resync/webhook marked this fix(mrb-N) as an ordinary MRB (FR #8475)."""
    return str(row.get("mrb_fix_offer") or "").strip().lower() in ("1", "true", "yes")


def is_mrb_fix_pr_title(title: str) -> bool:
    """True for titles like ``fix(mrb-105):ΓÇª`` or ``mrb-105-fix:ΓÇª`` (bobiverse#224 / #781)."""
    return bool(_MRB_FIX_TITLE_RE.search(str(title or "")))


def mrb_fix_parent_pr_id(title: str) -> str:
    """PR id ``#N`` from ``fix(mrb-N)`` / ``mrb-N-fix``, or empty (FR #4665)."""
    m = _MRB_FIX_TITLE_RE.search(str(title or ""))
    if not m:
        return ""
    num = next((g for g in m.groups() if g), "")
    return f"#{num}" if num else ""


def pr_base_ref(pr: dict | None) -> str:
    """Lowercased base branch name from a GitHub pull payload, or empty."""
    if not isinstance(pr, dict):
        return ""
    base = pr.get("base")
    if not isinstance(base, dict):
        return ""
    return str(base.get("ref") or "").strip().lower()


def pr_head_ref(pr: dict | None) -> str:
    """Lowercased head branch name from a GitHub pull payload, or empty."""
    if not isinstance(pr, dict):
        return ""
    head = pr.get("head")
    if not isinstance(head, dict):
        return ""
    return str(head.get("ref") or "").strip().lower()


def mrb_fix_targets_default_branch(pr: dict | None) -> bool:
    """True when the fix PR targets ``main`` / ``master`` (FR #4994).

    Missing base is treated as non-default so stacked FR #4665 skips stay safe
    when fixtures omit ``base``.
    """
    ref = pr_base_ref(pr)
    return ref in ("main", "master")


def mrb_fix_targets_feature_branch(
    pr: dict | None,
    parent_id: str,
    parent_pr: dict | None = None,
) -> bool:
    """True when the fix PR base is the open parent's feature branch (FR #8298).

    Match ``fr-<parent_pr_number>`` or the parent's head ref. Live evidence
    (``fix(mrb-8239)`` #8260): parent PR #8239 head is ``fr-8234`` (issue
    branch), so the fix base is ``fr-8234``, not ``fr-8239``. Other non-default
    bases stay stacked skips (FR #4665).
    """
    ref = pr_base_ref(pr)
    num = str(parent_id or "").lstrip("#").strip()
    if not ref or not num.isdigit():
        return False
    if ref in ("main", "master"):
        return False
    if ref == f"fr-{num}":
        return True
    if parent_pr is None:
        return False
    parent_head = pr_head_ref(parent_pr)
    return bool(parent_head) and parent_head not in ("main", "master") and ref == parent_head


def pr_base_is_explicit_non_default(pr: dict | None) -> bool:
    """True when the pull names a base that is not ``main`` / ``master`` (FR #8333).

    Empty/missing base is False so older fixtures and thin payloads that omit
    ``base`` keep prior resync behaviour (FR #4665 orphan queue). An explicit
    ``fr-*`` / stacked tip base is True --- those PRs cannot land on the default
    branch until retargeted or recreated (class of bobiverse#8320 / #8331).
    """
    ref = pr_base_ref(pr)
    return bool(ref) and ref not in ("main", "master")


def list_open_prs_explicit_non_default_base(prs) -> list[dict]:
    """Cheap hygiene rows: open pulls whose ``base.ref`` is not the default branch.

    Used by github-resync warn lines and the open_pr_stale_base monitor (FR #8333).
    """
    out: list[dict] = []
    if not isinstance(prs, list):
        return out
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        if pr.get("draft") is True:
            continue
        if not pr_base_is_explicit_non_default(pr):
            continue
        num = pr.get("number")
        out.append(
            {
                "number": num,
                "base": pr_base_ref(pr),
                "title": str(pr.get("title") or "")[:160],
                "html_url": str(pr.get("html_url") or ""),
            }
        )
    return out


def open_pr_expects_mrb_or_fix_row(
    pr: dict | None,
    *,
    fix_keeper: dict | None = None,
) -> bool:
    """True when an open pull should hold an MRB (or FIX) queue row (FR #8377).

    Mirrors the resync classification so the open_pr_mrb_missing monitor does not
    flag pulls that are intentionally not standalone MRB work: drafts, intake
    harvest receipts, stacked ``fix(mrb-N)`` tips, ``docs/mrb-*`` pins, and
    lesson-of-lesson / pin-of-pin tips.

    FR #8475: a ``fix(mrb-N)`` whose base is ``main`` or ``master`` is expected
    MRB work (orphan parent, or the FR #4994 main-base keeper). Stacked fixes
    with a missing or non-default base stay ignored. Pass ``fix_keeper`` (parent
    id -> lowest PR number) to ignore a twin that resync will not queue.
    """
    if not isinstance(pr, dict):
        return False
    if pr.get("draft") is True:
        return False
    title = str(pr.get("title") or "")
    body = str(pr.get("body") or "")
    labels = tuple(_label_names(pr.get("labels")))
    head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
    head_ref = str(head.get("ref") or "")
    if is_mrb_fix_pr_title(title):
        if not mrb_fix_targets_default_branch(pr):
            return False
        parent = mrb_fix_parent_pr_id(title)
        num = pr.get("number")
        if (
            fix_keeper
            and parent
            and parent in fix_keeper
            and isinstance(num, int)
            and num != fix_keeper[parent]
        ):
            return False
        return True
    if is_docs_mrb_pin_pr(title=title, head_ref=head_ref, labels=labels):
        return False
    if is_intake_harvest_receipt_pr(title=title, body=body, labels=labels):
        return False
    if is_lesson_of_lesson_pr(
        title=title, body=body, labels=labels, head_ref=head_ref
    ):
        return False
    return True


def _queue_rows_cover_mrb_fix(
    rows: list[dict], repo: str, ident: str, num: int
) -> bool:
    """True when any unaccepted/accepted row is an MRB or FIX for ``repo#num``.

    FR #8377: an open PR is covered when a matching MRB row exists, or a FIX row
    handles it (ci-fail / conflict / dirty fold). MRB rows carry a ``/pull/N`` URL
    (FR #595), so a URL match is the fallback when the id shape differs.
    """
    repo_c = canonical_queue_repo(repo).lower() if repo else ""
    want = _norm_row_id(ident)
    pull_tail = f"/pull/{num}"
    for r in rows:
        if not isinstance(r, dict):
            continue
        if str(r.get("task") or "").upper() not in ("MRB", "FIX"):
            continue
        r_repo = canonical_queue_repo(str(r.get("repo") or "")).lower()
        if repo_c and r_repo and r_repo != repo_c:
            continue
        r_id = _norm_row_id(str(r.get("id") or ""))
        if r_id and r_id == want:
            return True
        if pull_tail in str(r.get("url") or ""):
            return True
    return False


def list_open_prs_missing_mrb(
    prs, queue_doc=None, *, repo: str = ""
) -> list[dict]:
    """Open non-draft non-receipt PRs with no MRB/FIX queue row (FR #8377).

    Shared by the ``open_pr_mrb_missing`` monitor (and future resync self-checks):
    a product PR that GitHub still lists as open but the queue neither holds nor
    is reviewing as MRB/FIX is stranded - seats can never be offered the hostile
    review for a green, mergeable PR (class of bobiverse#8353).
    """
    out: list[dict] = []
    if not isinstance(prs, list):
        return out
    rows: list[dict] = []
    if isinstance(queue_doc, dict):
        for bucket in ("unaccepted", "accepted"):
            v = queue_doc.get(bucket)
            if isinstance(v, list):
                rows.extend(r for r in v if isinstance(r, dict))
            elif isinstance(v, dict):
                rows.extend(r for r in v.values() if isinstance(r, dict))
    open_nums = {
        int(p["number"])
        for p in prs
        if isinstance(p, dict) and isinstance(p.get("number"), int)
    }
    fix_keeper: dict[str, int] = {}
    for p in prs:
        if not isinstance(p, dict) or not isinstance(p.get("number"), int):
            continue
        if p.get("draft") is True:
            continue
        title_p = str(p.get("title") or "")
        if not is_mrb_fix_pr_title(title_p) or not mrb_fix_targets_default_branch(p):
            continue
        parent_p = mrb_fix_parent_pr_id(title_p)
        if not parent_p:
            continue
        try:
            parent_num = int(str(parent_p).lstrip("#"))
        except ValueError:
            parent_num = -1
        if parent_num not in open_nums:
            continue
        n_p = int(p["number"])
        prev = fix_keeper.get(parent_p)
        if prev is None or n_p < prev:
            fix_keeper[parent_p] = n_p
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        if not open_pr_expects_mrb_or_fix_row(pr, fix_keeper=fix_keeper):
            continue
        num = pr.get("number")
        if not isinstance(num, int):
            continue
        base = pr.get("base") if isinstance(pr.get("base"), dict) else {}
        base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else {}
        pr_repo = repo or str(base_repo.get("full_name") or "")
        ident = f"#{num}"
        if _queue_rows_cover_mrb_fix(rows, pr_repo, ident, num):
            continue
        out.append(
            {
                "repo": pr_repo,
                "number": num,
                "id": ident,
                "title": str(pr.get("title") or "")[:160],
                "html_url": str(pr.get("html_url") or ""),
            }
        )
    return out


def heal_open_prs_missing_mrb(
    home: Path,
    pulls,
    *,
    repo: str = "",
    dry_run: bool = False,
) -> dict:
    """FR #9635: enqueue MRB for open expected PRs missing from the queue.

    Mirrors ``resync_from_github`` open-PR classification via
    ``list_open_prs_missing_mrb`` / ``claim_from_github_issue``. Includes
    ``lesson(...)`` / harvest-lesson tips (same as !resync / !assign; webhook
    still skips pure intake receipts per FR #2650).

    Returns ``{ok, added, duplicate, skipped, refused, missing_before,
    missing_after, details, dry_run}``.
    """
    pulls_l = [p for p in (pulls if isinstance(pulls, list) else []) if isinstance(p, dict)]
    by_num: dict[tuple[str, int], dict] = {}
    for pr in pulls_l:
        num = pr.get("number")
        if not isinstance(num, int):
            continue
        base = pr.get("base") if isinstance(pr.get("base"), dict) else {}
        base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else {}
        pr_repo = (
            canonical_queue_repo(str(base_repo.get("full_name") or repo or ""))
            or str(repo or "").strip()
        )
        if not pr_repo:
            continue
        by_num[(_repo_key(pr_repo), int(num))] = pr

    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            missing = list_open_prs_missing_mrb(pulls_l, doc, repo=repo)
            details: list[dict] = []
            added = duplicate = skipped = refused = 0
            if dry_run:
                return {
                    "ok": True,
                    "added": 0,
                    "duplicate": 0,
                    "skipped": 0,
                    "refused": 0,
                    "missing_before": len(missing),
                    "missing_after": len(missing),
                    "details": [
                        {
                            "repo": m.get("repo"),
                            "number": m.get("number"),
                            "planned": "enqueue_mrb",
                        }
                        for m in missing
                    ],
                    "dry_run": True,
                }
            for m in missing:
                pr_repo = canonical_queue_repo(str(m.get("repo") or repo or "")) or ""
                num = m.get("number")
                if not pr_repo or not isinstance(num, int):
                    refused += 1
                    details.append({"repo": pr_repo, "number": num, "result": "refused:bad_key"})
                    continue
                pr = by_num.get((_repo_key(pr_repo), int(num)))
                if pr is None:
                    refused += 1
                    details.append(
                        {"repo": pr_repo, "number": num, "result": "refused:pr_not_in_list"}
                    )
                    continue
                # claim_from_github_issue treats /pull/ URLs (and pull_request blobs) as MRB.
                issue = dict(pr)
                if "html_url" not in issue or "/pull/" not in str(issue.get("html_url") or ""):
                    issue["html_url"] = (
                        str(pr.get("html_url") or "")
                        or f"https://github.com/{pr_repo}/pull/{num}"
                    )
                if "state" not in issue:
                    issue["state"] = "open"
                claim = claim_from_github_issue(pr_repo, issue)
                if claim is None or claim.task != "MRB":
                    refused += 1
                    details.append(
                        {
                            "repo": pr_repo,
                            "number": num,
                            "result": "refused:not_mrb_claim",
                        }
                    )
                    continue
                url = str(pr.get("html_url") or issue.get("html_url") or "")
                result = _append_unaccepted(doc, claim, home=home, url=url)
                if result == "added":
                    added += 1
                elif result == "duplicate":
                    duplicate += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    refused += 1
                details.append(
                    {"repo": pr_repo, "number": num, "result": result or "refused"}
                )
            if added or duplicate:
                _write_queue(queue_path(home), doc)
            missing_after = list_open_prs_missing_mrb(pulls_l, doc, repo=repo)
            return {
                "ok": True,
                "added": added,
                "duplicate": duplicate,
                "skipped": skipped,
                "refused": refused,
                "missing_before": len(missing),
                "missing_after": len(missing_after),
                "details": details,
                "dry_run": False,
            }
    except (TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
            "added": 0,
            "duplicate": 0,
            "skipped": 0,
            "refused": 0,
            "missing_before": 0,
            "missing_after": -1,
            "details": [],
            "dry_run": bool(dry_run),
        }


def _read_legacy_unaccepted(path: Path) -> list[dict]:
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    items = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for row in items:
        if isinstance(row, dict):
            coerced = _coerce_row(row)
            if coerced:
                out.append(coerced)
    return out


def _read_legacy_accepted(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            coerced = _coerce_row(row)
            if coerced:
                rows.append(coerced)
    return rows


def _queue_needs_repo_alias_backup(doc: dict) -> bool:
    for bucket in ("unaccepted", "accepted", "done"):
        rows = doc.get(bucket)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw = str(row.get("repo") or "").strip()
            if raw and repo_alias.canonicalize_repo(raw) != raw:
                return True
    return False


def _read_queue_file(path: Path) -> dict:
    raw_text = path.read_text(encoding="utf-8")
    doc = json.loads(raw_text)
    if not isinstance(doc, dict):
        raise ValueError("queue")
    unaccepted = doc.get("unaccepted")
    accepted = doc.get("accepted")
    done = doc.get("done")
    if not isinstance(unaccepted, list) or not isinstance(accepted, list):
        raise ValueError("queue lists")
    if not isinstance(done, list):
        done = []
    if _queue_needs_repo_alias_backup(doc):
        bak = path.with_name(path.name + ".bak-fr7121")
        if not bak.exists():
            bak.write_text(raw_text, encoding="utf-8")
    out = {
        "v": 1,
        "unaccepted": [row for row in (_coerce_row(r) for r in unaccepted if isinstance(r, dict)) if row],
        "accepted": [row for row in (_coerce_row(r) for r in accepted if isinstance(r, dict)) if row],
        # FR #254: keep DONE rows (url/result) so FR stays superseded while implement PR is open.
        "done": [row for row in (_coerce_row(r) for r in done if isinstance(r, dict)) if row][-DONE_CAP:],
    }
    # FR #4827: stand-down notes must survive a queue reload until the chair says them.
    notes = doc.get("stand_down")
    if isinstance(notes, list):
        out["stand_down"] = [n for n in notes if isinstance(n, dict)]
    # FR #6407: rewrite retired ce-priority-dev1 stamps to any on every load.
    out["_retired_pin_rewrites"] = _rewrite_retired_require_machine_rows(out)
    # FR #7121: persist canonical repo names after alias rewrite.
    out["_repo_alias_rewrites"] = 1 if _queue_needs_repo_alias_backup(doc) else 0
    return out


def _write_queue(path: Path, doc: dict) -> None:
    """Atomic replace with PermissionError retries (Windows AV/reader contention, FR #1811)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # prune done under lock so rewrites stay smaller
    done = doc.get("done")
    if isinstance(done, list) and len(done) > DONE_CAP:
        doc["done"] = done[-DONE_CAP:]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    last_exc: Exception | None = None
    for attempt in range(WRITE_REPLACE_RETRIES):
        try:
            os.replace(str(tmp), str(path))
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
        except OSError as exc:
            # Some Windows paths surface sharing violations as WinError 32/5 via OSError
            if getattr(exc, "winerror", None) in (5, 32) or isinstance(exc, PermissionError):
                last_exc = exc
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise OSError("queue replace failed")


def _load_queue_unlocked(home: Path) -> dict:
    path = queue_path(home)
    if path.exists():
        doc = _read_queue_file(path)
        n = int(doc.pop("_retired_pin_rewrites", 0) or 0)
        n += int(doc.pop("_repo_alias_rewrites", 0) or 0)
        if n:
            try:
                _write_queue(path, doc)
            except OSError:
                pass
        return doc
    root = _root(home)
    legacy_u = _read_legacy_unaccepted(root / LEGACY_UNACCEPTED)
    legacy_a = _read_legacy_accepted(root / LEGACY_ACCEPTED)
    if legacy_u or legacy_a:
        doc = {"v": 1, "unaccepted": legacy_u, "accepted": legacy_a[-ACCEPTED_CAP:], "done": []}
        _write_queue(path, doc)
        return doc
    return _empty_queue()


def load_queue(home: Path) -> dict:
    """Webhook mirror. Empty lists when nothing has been queued."""
    try:
        with _lock(home):
            return _load_queue_unlocked(home)
    except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
        return _empty_queue()


def _norm_row_id(ident: str | None) -> str:
    """Canonical ``#N`` id for queue row matching (FR #2458)."""
    s = str(ident or "").strip()
    if not s:
        return ""
    if s.startswith("#"):
        return s
    if s.isdigit():
        return f"#{s}"
    return s


def _row_drop_label(row: dict) -> str:
    """Short ``TASK repo#N`` label for resync/prune drop logs (FR #2899)."""
    task = str(row.get("task") or "?").upper() or "?"
    repo = str(row.get("repo") or "?").strip() or "?"
    ident = _norm_row_id(row.get("id")) or "#?"
    return f"{task} {repo}{ident}"


def _mrb_row_has_pull_provenance(row: dict) -> bool:
    """True when an MRB row looks like a real pull (FR #2927).

    Bare ``task=MRB`` + ``repo`` + ``#N`` queue junk (no URL / event / lesson labels)
    must stay unhealable so prune can drop it (FR #595). Harvest-lesson / webhook
    pull rows may omit ``url`` briefly - those get a synthesized ``/pull/N``.
    """
    if not isinstance(row, dict):
        return False
    if PULL_URL_RE.search(str(row.get("url") or "")):
        return True
    event = str(row.get("event") or "").strip().lower()
    if event in ("pull_request", "pull_request_target"):
        return True
    labels = {
        str(x).strip().lower()
        for x in (row.get("labels") or ())
        if str(x).strip()
    }
    if "harvest-lesson" in labels:
        return True
    title = str(row.get("title") or "").strip()
    if title.lower().startswith("lesson("):
        return True
    return False


def _heal_mrb_pull_url(row: dict, *, force: bool = False) -> bool:
    """Synthesize ``/pull/N`` URL when repo+#N are known (FR #2604 / #2899 / #2927).

    ``force=True`` is for resync paths that already know the id is an open pull.
    """
    if not isinstance(row, dict) or _canon_task(row) != "MRB":
        return False
    if PULL_URL_RE.search(str(row.get("url") or "")):
        return True
    # FR #2927: never invent a pull URL for fake/bare MRB rows (keeps FR #595 prune).
    if not force and not _mrb_row_has_pull_provenance(row):
        return False
    repo = str(row.get("repo") or "").strip()
    ident = _norm_row_id(row.get("id"))
    if not repo or not ident:
        return False
    if force and not str(row.get("event") or "").strip():
        row["event"] = "pull_request"
    row["url"] = f"https://github.com/{repo}/pull/{ident.lstrip('#')}"
    return bool(PULL_URL_RE.search(str(row.get("url") or "")))


def _same(row: dict, repo: str, task: str, ident: str) -> bool:
    """True when row matches repo/task/id. Repo compare is case-insensitive (FR #3817)."""
    return (
        _repo_key(row.get("repo")) == _repo_key(repo)
        and str(row.get("task") or "").upper() == str(task or "").upper()
        and _norm_row_id(row.get("id")) == _norm_row_id(ident)
    )


def _already(doc: dict, repo: str, task: str, ident: str) -> bool:
    return any(_same(row, repo, task, ident) for row in doc["unaccepted"]) or any(
        _same(row, repo, task, ident) for row in doc["accepted"]
    )


def collapse_case_variant_twins(doc: dict) -> int:
    """FR #3817: merge unaccepted/accepted rows that differ only by repo-name casing.

    Prefers mixed-case ``owner/name`` (GitHub ``full_name``) and a non-empty ``line``.
    Returns how many duplicate rows were dropped.
    """
    dropped = 0
    for bucket in ("unaccepted", "accepted"):
        rows = [r for r in (doc.get(bucket) or []) if isinstance(r, dict)]
        if len(rows) < 2:
            continue
        best: dict[tuple[str, str, str], dict] = {}
        order: list[tuple[str, str, str]] = []
        for row in rows:
            key = _job_key(row.get("repo"), row.get("task"), row.get("id"))
            prev = best.get(key)
            if prev is None:
                best[key] = row
                order.append(key)
                continue
            dropped += 1
            prev["repo"] = _prefer_repo_casing(
                str(prev.get("repo") or ""), str(row.get("repo") or "")
            )
            if str(row.get("line") or "").strip() and not str(prev.get("line") or "").strip():
                prev["line"] = row.get("line")
            for field in (
                "title",
                "body",
                "labels",
                "event",
                "action",
                "url",
                "require_machine",
                "state",
                "refs",
            ):
                if row.get(field) and not prev.get(field):
                    prev[field] = row.get(field)
            try:
                a = int(prev.get("seq") or 0)
                b = int(row.get("seq") or 0)
                if b and (not a or b < a):
                    prev["seq"] = b
            except (TypeError, ValueError):
                pass
            best[key] = prev
        doc[bucket] = [best[k] for k in order]
    return dropped


def enqueue_unaccepted(home: Path, claim: GitClaim) -> str:
    """Apply deterministic queue transition for this claim (FR #207 supersede table).

    FR #1811: pass through error:queue-* so BobCallback can announce specific errs;
    still maps success codes to legacy added|duplicate.
    FR #2803: after a real queue add/update, push offers to seats idle after ``nothing queued``.
    """
    if claim.task not in TASK_KINDS:
        return "error"
    result = apply_queue_event(home, claim)
    if result.startswith("error"):
        return result
    if result in ("added", "updated", "removed", "duplicate", "noop"):
        out = "added"
        if result == "added":
            out = "added"
        elif result == "duplicate":
            out = "duplicate"
        else:
            out = "added" if result in ("updated", "removed") else "duplicate"
        if out == "added" and result in ("added", "updated"):
            with contextlib.suppress(Exception):
                push_idle_offers_via_chair_outbox(home)
            if str(claim.task or "").upper() == "MRB":
                with contextlib.suppress(Exception):
                    counter = github_pr_seat_commit_counter(home=home)
                    if counter is not None:
                        stamp_mrb_author_commit_counts(
                            home,
                            [{
                                "task": "MRB",
                                "repo": claim.repo,
                                "id": claim.id,
                                "url": "",
                            }],
                            counter,
                            limit=1,
                        )
        return out
    return "error"


def load_unaccepted(home: Path) -> list[dict]:
    return list(load_queue(home).get("unaccepted") or [])


def load_accepted(home: Path) -> list[dict]:
    return list(load_queue(home).get("accepted") or [])


def _sort_key(row: dict) -> tuple:
    """FR #3205 fallback / claim_top key: MRB < UAT < FIX < FR, then lowest number, then repo.

    Prefer ``focus_ignore.offer_sort_key`` / ``ordered_unaccepted`` when a home is available.
    """
    import focus_ignore as _fi

    task = str(row.get("task") or "").strip().upper()
    return (
        _fi._TASK_ORDER.get(task, 4),
        _fi.row_offer_number(row),
        str(row.get("repo") or "").lower(),
        str(row.get("id") or ""),
    )


OFFER_PRECOMPUTE_FILE = "offer-precompute.json"


def offer_precompute_path(home: Path) -> Path:
    return bobreport.fleet_digest_home(Path(home)) / OFFER_PRECOMPUTE_FILE


def _offer_row_fingerprint(rows: list[dict]) -> str:
    parts = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        parts.append(
            f"{r.get('repo')}|{r.get('task')}|{str(r.get('id') or '').lstrip('#')}"
        )
    return "|".join(sorted(parts))


def rebuild_offer_precompute(home: Path, rows: list[dict] | None = None) -> list[dict]:
    """FR #3205: rebuild ordered candidate list from local queue + focus (no GitHub).

    Written under the digest home so !bored can walk a pre-validated order with
    zero live GitHub calls when the fingerprint still matches.
    """
    import focus_ignore as _fi

    src = list(rows) if rows is not None else list(load_unaccepted(home))
    ordered = _fi.sort_unaccepted_rows(home, src)
    payload = {
        "v": 1,
        "ts": _utc_now(),
        "fingerprint": _offer_row_fingerprint(src),
        "order": [
            {
                "repo": str(r.get("repo") or ""),
                "task": str(r.get("task") or ""),
                "id": str(r.get("id") or ""),
            }
            for r in ordered
            if isinstance(r, dict)
        ],
    }
    path = offer_precompute_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=0) + "\n", encoding="utf-8")
    tmp.replace(path)
    return ordered


def load_offer_precompute(home: Path) -> dict | None:
    path = offer_precompute_path(home)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def offer_precompute_fresh(home: Path, rows: list[dict] | None = None) -> bool:
    """True when on-disk precompute matches the current unaccepted fingerprint."""
    doc = load_offer_precompute(home)
    if not doc:
        return False
    src = list(rows) if rows is not None else list(load_unaccepted(home))
    return str(doc.get("fingerprint") or "") == _offer_row_fingerprint(src)


def claim_top(home: Path, nick: str, channel: str) -> tuple[str, dict | None]:
    """Atomically move the oldest unaccepted row to accepted.

    Returns (\"ok\", job), (\"empty\", None), or (\"error\", None).
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            if not doc["unaccepted"]:
                return "empty", None
            doc["unaccepted"].sort(key=_sort_key)
            job = dict(doc["unaccepted"].pop(0))
            job["nick"] = (nick or "").strip()
            job["channel"] = bobreport.normalize_channel(channel) if channel else ""
            job["accepted_ts"] = _utc_now()
            doc["accepted"].append(job)
            if len(doc["accepted"]) > ACCEPTED_CAP:
                doc["accepted"] = doc["accepted"][-ACCEPTED_CAP:]
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def _read_activity(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    seen = doc.get("seen") if isinstance(doc, dict) else None
    if not isinstance(seen, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in seen.items():
        try:
            out[str(key)] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _write_activity(path: Path, seen: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"v": 1, "seen": seen}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def note_worker_activity(home: Path, nick: str, now: float) -> None:
    canon = canonical_worker_nick(nick)
    if not canon:
        return
    try:
        with _lock(home):
            path = activity_path(home)
            try:
                seen = _read_activity(path)
            except (OSError, json.JSONDecodeError):
                seen = {}
            seen[canon] = float(now)
            _write_activity(path, seen)
    except (TimeoutError, OSError, json.JSONDecodeError):
        return


def last_worker_activity(home: Path, nick: str) -> float | None:
    canon = canonical_worker_nick(nick)
    if not canon:
        return None
    try:
        with _lock(home):
            seen = _read_activity(activity_path(home))
    except (OSError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
    val = seen.get(canon)
    return float(val) if val is not None else None



OFFER_TIMEOUT_S = 90.0
# FR #2811 / FR #3893: giveup/done-push offers stay sticky through harvest_hold_s so a held assign is not stolen.
GIVEUP_OFFER_EXTRA_S = 90.0
# FR #2309: max same-nick rebroadcasts without ACK before clearing the pin.
OFFER_STICKY_MAX = 3
# FR #7966: unanswered offers to one seat (timeout, no ACK/NACK/GIVEUP) stop at this count.
OFFER_UNANSWERED_MAX = 3
# FR #8924: one cooldown expiry may clear an offer-timeout refusal. The next
# expiry escalates once and leaves the seat refused.
OFFER_REFUSAL_EXPIRE_MAX = 1
# Sticky via values that get the extended offer window (harvest hold / seat turn end).
_RELEASE_OFFER_VIA = frozenset({"giveup", "done", "nack"})


def offer_timeout_s(row: dict | None) -> float:
    """Sticky offer window; giveup/done-pushed rows get OFFER_TIMEOUT_S + GIVEUP_OFFER_EXTRA_S (FR #2811 / #3893)."""
    base = float(OFFER_TIMEOUT_S)
    via = ""
    if isinstance(row, dict):
        via = str(row.get("offered_via") or "").strip().lower()
    if via in _RELEASE_OFFER_VIA:
        return base + float(GIVEUP_OFFER_EXTRA_S)
    return base


def _seat_nick_eq(a: str, b: str) -> bool:
    left = (canonical_worker_nick(a) or a or "").strip().lower()
    right = (canonical_worker_nick(b) or b or "").strip().lower()
    return bool(left) and left == right


def seat_blocked_for_self_review_stall(
    row: dict, nick: str, doc: dict | None = None
) -> bool:
    """FR #8264 / #8293: do not offer a self-review stall FR to its author seat.

    Block when the evidence ``idle`` list names this seat, or when this seat is
    the author of a waiting pull named in the stall title. A queue row whose
    body was truncated still blocks the author.
    """
    if not isinstance(row, dict):
        return False
    task = _canon_task(row)
    if task == "MRB":
        return False
    blob = " ".join(
        str(row.get(k) or "") for k in ("title", "body", "line")
    )
    if "self-review-deadlock" not in blob:
        return False
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    m = re.search(r'"idle"\s*:\s*\[(.*?)\]', blob, re.S)
    if m:
        for raw in re.findall(r'"([^"]+)"', m.group(1)):
            if _seat_nick_eq(raw, me):
                return True
    # FR #8619: compact pin kept when queue body truncate drops Evidence JSON.
    for raw in re.findall(r"(?im)^stall_idle:\s*(.+)$", blob):
        for nick in re.split(r"[,\s]+", raw.strip()):
            if nick and _seat_nick_eq(nick, me):
                return True
    if re.search(r"(?i)\bidle\b[^]]{0,500}\b" + re.escape(me) + r"\b", blob):
        return True
    if not isinstance(doc, dict):
        return False
    title = str(row.get("title") or "")
    waiting = re.findall(
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)", title
    )
    if not waiting:
        return False
    want = {(repo.lower(), num) for repo, num in waiting}
    buckets = []
    for key in ("unaccepted", "accepted", "done"):
        buckets.extend(doc.get(key) or [])
    for other in buckets:
        if not isinstance(other, dict):
            continue
        repo = str(other.get("repo") or "").strip().lower()
        ident = str(other.get("id") or "").lstrip("#")
        if (repo, ident) not in want:
            continue
        for field in ("author_seat", "implementer_seat", "author_nick"):
            if _seat_nick_eq(str(other.get(field) or ""), me):
                return True
    return False


def seat_offer_refused(row: dict, nick: str) -> bool:
    """True when this seat already used its unanswered-offer budget (FR #7966)."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me or not isinstance(row, dict):
        return False
    for raw in row.get("offer_refused_by") or []:
        other = (canonical_worker_nick(str(raw)) or str(raw) or "").strip().lower()
        if other and other == me:
            return True
    return False


def live_seat_can_take_unanswered(
    row: dict,
    live: set[str] | None,
    home: Path | None = None,
    doc: dict | None = None,
) -> bool:
    """True when some live seat is not refused and has not given up (FR #7966).

    no_eligible_since means nobody live can take the row. A sibling seat that
    is still eligible must not look stalled. FR #8153: also skip seats blocked
    for no-clone on this repo when *home* is provided.
    FR #8295: pass the queue doc so a self-review stall blocks its author
    even when the row body has no idle list.
    """
    if not isinstance(row, dict):
        return False
    expire_offer_timeout_refusals(row, time.time())
    repo = str(row.get("repo") or "")
    for raw in live or ():
        nick = str(raw or "").strip()
        if not nick:
            continue
        if seat_offer_refused(row, nick) or row_gave_up_by(row, nick):
            continue
        if seat_blocked_for_self_review_stall(row, nick, doc):
            continue
        if seat_on_deterministic_nack_cooldown(row, nick, time.time()):
            continue
        if home is not None and seat_blocked_for_no_clone_repo(home, nick, repo):
            continue
        return True
    return False


def note_offer_outcome(row: dict, seat: str, outcome: str, reason: str = "") -> None:
    """Append one per-seat offer result (timeout / nack / giveup) for the digest (FR #7966)."""
    canon = (canonical_worker_nick(seat) or seat or "").strip()
    if not canon or not isinstance(row, dict):
        return
    outcomes = row.get("offer_outcomes")
    if not isinstance(outcomes, list):
        outcomes = []
    outcomes.append({
        "seat": canon,
        "outcome": str(outcome or "").strip() or "timeout",
        "reason": str(reason or "")[:200],
        "ts": _utc_now(),
    })
    row["offer_outcomes"] = outcomes[-20:]


def seat_submit_verify_in_flight(home: Path, nick: str) -> bool:
    """FR #8442: a live seat pasting/submit-verify is not an offer-timeout."""
    want = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not want:
        return False
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return False
    for ent in (doc.get("machines") or {}).values():
        if not isinstance(ent, dict):
            continue
        rows = bobreport._coerce_worker_list(ent.get("worker_list"))
        for row in rows:
            if not isinstance(row, dict):
                continue
            got = (canonical_worker_nick(str(row.get("nick") or "")) or "").strip().lower()
            phase = str(row.get("progress_phase") or "").strip().lower()
            if got == want and phase == "submit-verify":
                return True
    return False


def offer_timeout_reason(home: Path, nick: str) -> str:
    """Why a live seat missed ACK (FR #8924). Idle with no job is idle-no-ack."""
    want = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not want:
        return "offer-timeout"
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return "offer-timeout:idle-no-ack"
    for ent in (doc.get("machines") or {}).values():
        if not isinstance(ent, dict):
            continue
        for wrow in bobreport._coerce_worker_list(ent.get("worker_list")):
            if not isinstance(wrow, dict):
                continue
            got = (canonical_worker_nick(str(wrow.get("nick") or "")) or "").strip().lower()
            if got != want:
                continue
            state = str(wrow.get("state") or "").strip().lower()
            jobs = wrow.get("jobs")
            work = str(wrow.get("work") or "").strip()
            if isinstance(jobs, list) and jobs:
                return "offer-timeout:busy-jobs"
            if work:
                return "offer-timeout:busy-jobs"
            if state and state != "idle":
                return "offer-timeout:state-" + state[:40]
            return "offer-timeout:idle-no-ack"
    return "offer-timeout:idle-no-ack"


def expire_offer_timeout_refusals(row: dict, now_f: float) -> bool:
    """Clear an offer-timeout refusal after cooldown (FR #8924).

    One wave may be re-offered. A later expiry stamps offer-timeout-cap and
    leaves the seat refused. Real giveup_reason rows keep giveup_seats.
    """
    if not isinstance(row, dict):
        return False
    until = _parse_iso_ts(str(row.get("cooldown_until") or ""))
    if until is None or float(now_f) < until:
        return False
    refused = [str(x).strip() for x in (row.get("offer_refused_by") or []) if str(x).strip()]
    if not refused:
        return False
    latest: dict[str, str] = {}
    for item in row.get("offer_outcomes") or []:
        if not isinstance(item, dict):
            continue
        seat = str(item.get("seat") or "").strip().lower()
        if seat:
            latest[seat] = str(item.get("reason") or "")
    timeout_seats = []
    for seat in refused:
        key = (canonical_worker_nick(seat) or seat).strip().lower()
        reason = latest.get(key) or latest.get(seat.lower()) or ""
        if reason.startswith("offer-timeout") and "cap" not in reason:
            timeout_seats.append(seat)
    if not timeout_seats:
        return False
    try:
        waves = int(row.get("offer_refusal_waves") or 0)
    except (TypeError, ValueError):
        waves = 0
    if waves >= int(OFFER_REFUSAL_EXPIRE_MAX):
        if not str(row.get("offer_escalate_reason") or "").strip():
            row["offer_escalate_reason"] = "offer-timeout-cap"
            note_offer_outcome(row, timeout_seats[0], "escalate", "offer-timeout-cap")
            return True
        return False
    drop = {(canonical_worker_nick(s) or s).strip().lower() for s in timeout_seats}
    row["offer_refused_by"] = [
        s for s in refused
        if (canonical_worker_nick(s) or s).strip().lower() not in drop
    ]
    real = str(row.get("giveup_reason") or "").strip()
    if not real or real.startswith("offer-timeout"):
        kept = []
        for raw in str(row.get("giveup_seats") or "").split(","):
            seat = raw.strip()
            if not seat:
                continue
            if (canonical_worker_nick(seat) or seat).strip().lower() in drop:
                continue
            kept.append(seat)
        if kept:
            row["giveup_seats"] = ",".join(kept)
        else:
            row.pop("giveup_seats", None)
    counts = row.get("offer_unanswered")
    if isinstance(counts, dict):
        for key in list(counts):
            if str(key).strip().lower() in drop:
                counts.pop(key, None)
        row["offer_unanswered"] = counts
    row.pop("cooldown_until", None)
    row["offer_refusal_waves"] = waves + 1
    note_offer_outcome(row, timeout_seats[0], "expire", "offer-timeout-expired")
    return True


def note_unanswered_offer(row: dict, seat: str, now_f: float, reason: str = "offer-timeout") -> None:
    """Count a timed-out offer. After OFFER_UNANSWERED_MAX, refuse that seat (FR #7966).

    Sets cooldown_until and offer_refused_by. Also appends giveup_seats so
    row_on_cooldown blocks only that seat. Does not increment giveup_count
    and does not stamp needs_human. FR #8924 records why the seat missed ACK.
    """
    canon = (canonical_worker_nick(seat) or seat or "").strip()
    if not canon or not isinstance(row, dict):
        return
    why = str(reason or "offer-timeout").strip() or "offer-timeout"
    note_offer_outcome(row, canon, "timeout", why)
    key = canon.lower()
    counts = row.get("offer_unanswered")
    if not isinstance(counts, dict):
        counts = {}
    try:
        n = int(counts.get(key) or 0) + 1
    except (TypeError, ValueError):
        n = 1
    counts[key] = n
    row["offer_unanswered"] = counts
    # FR #8428: one timeout must not pin the next idle push to this nick.
    row["offer_last_timeout_seat"] = canon
    if n < int(OFFER_UNANSWERED_MAX):
        return
    refused = [str(x).strip() for x in (row.get("offer_refused_by") or []) if str(x).strip()]
    if canon.lower() not in {(canonical_worker_nick(x) or x).strip().lower() for x in refused}:
        refused.append(canon)
    row["offer_refused_by"] = refused
    seats = [s.strip() for s in str(row.get("giveup_seats") or "").split(",") if s.strip()]
    if canon.lower() not in {(canonical_worker_nick(x) or x).strip().lower() for x in seats}:
        seats.append(canon)
    if seats:
        row["giveup_seats"] = ",".join(seats)
    from datetime import timedelta as _td

    until = datetime.fromtimestamp(float(now_f), tz=timezone.utc) + _td(
        seconds=float(GIVEUP_COOLDOWN_S)
    )
    row["cooldown_until"] = until.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ordered_unaccepted(home: Path, rows: list[dict] | None = None) -> list[dict]:
    """Unaccepted rows in assignment order (#39 gap 2): ignored dropped, strict-focus filter,
    priority/critical first (FR #7204), then item rank > repo priority > seq.
    Same order feeds !list and !bored."""
    import focus_ignore

    if rows is None:
        rows = load_unaccepted(home)
    return focus_ignore.sort_unaccepted_rows(home, list(rows))


def _canon_task(row: dict) -> str:
    task = str(row.get("task") or "FR").upper()
    if task == "PR":
        task = "FR"
    # FR #4585: FIX (and BUILD) must stay distinct on the assign wire.
    return task if task in ("FR", "MRB", "UAT", "FIX", "BUILD") else "FR"


def resolve_assign_url(row: dict) -> str:
    """URL for an assign line (FR #595 / #247).

    FR/UAT may invent ``/issues/{id}`` when url is missing.
    MRB/FIX may only use an existing ``/pull/N`` url, or invent from explicit
    ``pr_id`` / ``pr`` - never from the bare row/issue id alone.
    """
    task = _canon_task(row)
    repo = str(row.get("repo") or "").strip()
    url = str(row.get("url") or "").strip()
    if task in ("MRB", "FIX"):
        if PULL_URL_RE.search(url):
            return url
        # FR #4857: main-side FIX carries an actions/commit URL, not /pull/N.
        if task == "FIX" and (
            str(row.get("main_red_fix") or "") in ("1", "true", "True")
            or str(row.get("id") or "").strip().lstrip("#").lower()
            in ("main", "main-red")
            or str(row.get("fail_signature") or "").startswith("main-red|")
        ):
            return url
        pr = str(row.get("pr_id") or row.get("pr") or "").strip().lstrip("#")
        if not pr and task == "FIX":
            pr = str(row.get("id") or "").strip().lstrip("#")
        if repo and pr and pr.lower() not in ("main", "main-red"):
            return f"https://github.com/{repo}/pull/{pr}"
        return ""
    if url:
        return url
    num = str(row.get("id") or "").strip().lstrip("#")
    if repo and num:
        return f"https://github.com/{repo}/issues/{num}"
    return ""


def row_url(row: dict) -> str:
    """Backward-compatible alias for ``resolve_assign_url``."""
    return resolve_assign_url(row)


def mrb_ledger_done_hold(home: Path, repo: str, ident: str) -> bool:
    """FR #1323: True when ledger ``mrb_done`` still holds this MRB row_key."""
    try:
        led = ledger_load(home)
    except OSError:
        return False
    done_ts = _parse_iso_ts(str((led.get("mrb_done") or {}).get(_lkey(repo, ident)) or ""))
    return done_ts is not None and (time.time() - done_ts) < MRB_DONE_HOLD_S


def stamp_mrb_done(home: Path, repo: str, ident: str) -> None:
    """Record DONE MRB so re-offers stay blocked after ``done[]`` trim (FR #1323)."""

    def _upd(doc: dict) -> None:
        doc.setdefault("mrb_done", {})[_lkey(repo, ident)] = _utc_now()

    try:
        _ledger_update(home, _upd)
    except OSError:
        pass


def stamp_mrb_fail(home: Path, repo: str, ident: str, sha: str, nick: str) -> None:
    """Remember which seat FAILed this head so resync does not re-offer MRB (FR #4718)."""

    def _upd(doc: dict) -> None:
        doc.setdefault("mrb_fail", {})[_lkey(repo, ident)] = {
            "sha": (sha or "").strip().lower(),
            "nick": (canonical_worker_nick(nick) or str(nick or "")).strip(),
            "at": _utc_now(),
        }

    try:
        _ledger_update(home, _upd)
    except OSError:
        pass


def mrb_fail_record(home: Path, repo: str, ident: str) -> dict | None:
    """Ledger stamp for a FAIL board, or None."""
    try:
        led = ledger_load(home)
    except OSError:
        return None
    rec = (led.get("mrb_fail") or {}).get(_lkey(repo, ident))
    return rec if isinstance(rec, dict) else None


def mrb_fail_same_head_for_seat(row: dict, nick: str) -> bool:
    """True when this seat already FAILed the MRB and must not be offered it again."""
    if _canon_task(row) != "MRB":
        return False
    raw = str(row.get("mrb_fail_by") or "").strip()
    who = (canonical_worker_nick(raw) or raw).strip()
    me = (canonical_worker_nick(nick) or str(nick or "")).strip()
    if not who or not me:
        return False
    return who.lower() == me.lower()


def clear_mrb_done(home: Path, repo: str, ident: str) -> None:
    """Drop a stale ``mrb_done`` stamp (FR #1585: premature DONE while PR still open)."""

    def _upd(doc: dict) -> None:
        md = doc.get("mrb_done")
        if isinstance(md, dict):
            md.pop(_lkey(repo, ident), None)

    try:
        _ledger_update(home, _upd)
    except OSError:
        pass


def _mrb_review_finished(
    doc: dict | None, home: Path | None, repo: str, ident: str
) -> bool:
    """FR #8278: True when a real MRB verdict or merge-on-green PASS is on record.

    DONE PASS/FAIL/MERGED/CLOSED in ``done[]``, or a merge-on-green PASS SHA, means
    the review finished. That must block re-offer even while the pull is still
    open (ci-wait / ``allow_auto_merge=false`` customer repos). Premature DONE
    that only stamped ``mrb_done`` without a verdict still yields to GitHub open
    (FR #1585).
    """
    want = _norm_row_id(ident)
    if not want or not str(repo or "").strip():
        return False
    repo_raw = str(repo or "").strip()
    repo_c = canonical_queue_repo(repo_raw) or repo_raw
    if isinstance(doc, dict):
        for r in doc.get("done") or []:
            if not isinstance(r, dict):
                continue
            if str(r.get("task") or "").upper() != "MRB":
                continue
            r_repo = str(r.get("repo") or "").strip()
            if not r_repo:
                continue
            if (canonical_queue_repo(r_repo) or r_repo) != repo_c and r_repo != repo_raw:
                continue
            if _norm_row_id(r.get("id")) != want:
                continue
            result = str(r.get("result") or "").strip().upper()
            if result in ("PASS", "FAIL", "MERGED", "CLOSED"):
                return True
    if home is not None:
        try:
            num = int(str(ident).lstrip("#"))
        except (TypeError, ValueError):
            num = 0
        if num:
            with contextlib.suppress(Exception):
                if str(_merge_on_green_pass_sha(home, repo_raw, num) or "").strip():
                    return True
    return False


def mrb_already_done(
    doc: dict, row: dict, *, home: Path | None = None, pr_exists=None
) -> bool:
    """FR #740 / #1323: True when ``done`` or ledger ``mrb_done`` covers this MRB.

    After DONE PASS/FAIL the row must not be re-offered (even if a duplicate
    lingered in ``unaccepted``, ``done[]`` rotated, or GitHub still returns HTTP 200).

    FR #1585: when ``pr_exists`` confirms the pull is still **open**, a premature
    DONE / ledger stamp must not block or purge - GitHub open wins over the stamp.

    FR #8278: a recorded PASS/FAIL/MERGED (or merge-on-green PASS) blocks re-offer
    even while the pull is still open, so customer ``allow_auto_merge=false``
    merge-on-green waits cannot clear the hold and bounce the same head back onto
    ``!bored``.
    """
    if _canon_task(row) != "MRB":
        return False
    repo = str(row.get("repo") or "").strip()
    ident = str(row.get("id") or "").strip()
    if not repo or not ident:
        return False
    want = ident if ident.startswith("#") else f"#{ident.lstrip('#')}"
    # Finished review wins over GitHub-open (ci-wait). Check before pr_exists.
    if _mrb_review_finished(doc, home, repo, want):
        # FR #9885: open clean mergeable tip stays offerable until merged (FR #4661
        # still blocks the seat that PASSed).
        if _mrb_pass_awaiting_merge(doc, row, home=home, pr_exists=pr_exists):
            return False
        return True
    if pr_exists is not None:
        try:
            if bool(pr_exists(repo, want.lstrip("#"))):
                return False
        except Exception:
            pass
    for r in doc.get("done") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("task") or "").upper() != "MRB":
            continue
        if str(r.get("repo") or "").strip() != repo:
            continue
        rid = str(r.get("id") or "").strip()
        if rid == want or rid.lstrip("#") == want.lstrip("#"):
            return True
    if home is not None and mrb_ledger_done_hold(home, repo, want):
        return True
    return False


def mrb_row_should_survive_resync(
    row: dict,
    *,
    want: set,
    fetched: set,
) -> bool:
    """FR #1323: MERGED/closed MRB must drop even when ``offered_to`` is set.

    Previously resync kept MRB rows with ``offered_to`` that were no longer in the
    open-pull want set - those phantoms got re-offered after DONE PASS.
    FR #3817: ``want`` / ``fetched`` membership is case-insensitive on repo.
    """
    if not isinstance(row, dict):
        return False
    repo = str(row.get("repo") or "")
    task = str(row.get("task") or "").upper()
    ident = _norm_row_id(row.get("id"))
    fetched_keys = {_repo_key(x) for x in (fetched or ())}
    if _repo_key(repo) not in fetched_keys:
        return True
    if task not in ("FR", "MRB"):
        return True
    # want may be legacy (repo, task, id) or FR #3817 _job_key tuples.
    if _job_key(repo, task, ident) in want or (repo, task, ident) in want:
        return True
    return False


def _mrb_row_merge_state(row: dict) -> tuple[Any, str]:
    """Mergeable + merge_state fields stamped on queue rows (resync / precompute)."""
    mergeable = row.get("mergeable")
    merge_state = str(
        row.get("mergeable_state")
        or row.get("merge_state_status")
        or row.get("mergeStateStatus")
        or ""
    )
    return mergeable, merge_state


def _mrb_row_merge_conflict_reason(row: dict) -> str | None:
    """FR #9885: DIRTY/CONFLICTING open PRs are FIX-first, not MRB."""
    try:
        import mrb_merge_on_green as _mog
    except ImportError:
        return None
    mergeable, merge_state = _mrb_row_merge_state(row)
    return _mog.merge_attempt_conflict_reason(
        mergeable=mergeable, merge_state=merge_state
    )


def _mrb_pass_verdict_on_record(
    doc: dict | None, home: Path | None, repo: str, ident: str
) -> bool:
    """True when a PASS verdict (not mere FAIL) is on record for this MRB."""
    want = _norm_row_id(ident)
    if not want or not str(repo or "").strip():
        return False
    repo_raw = str(repo or "").strip()
    repo_c = canonical_queue_repo(repo_raw) or repo_raw
    if isinstance(doc, dict):
        for r in doc.get("done") or []:
            if not isinstance(r, dict):
                continue
            if str(r.get("task") or "").upper() != "MRB":
                continue
            r_repo = str(r.get("repo") or "").strip()
            if not r_repo:
                continue
            if (canonical_queue_repo(r_repo) or r_repo) != repo_c and r_repo != repo_raw:
                continue
            if _norm_row_id(r.get("id")) != want:
                continue
            result = str(r.get("result") or "").strip().upper()
            if result == "PASS":
                return True
    if home is not None:
        try:
            num = int(str(ident).lstrip("#"))
        except (TypeError, ValueError):
            num = 0
        if num:
            with contextlib.suppress(Exception):
                if str(_merge_on_green_pass_sha(home, repo_raw, num) or "").strip():
                    return True
    return False


def _mrb_pass_awaiting_merge(
    doc: dict,
    row: dict,
    *,
    home: Path | None = None,
    pr_exists=None,
) -> bool:
    """FR #9885: PASS on an open clean MERGEABLE tip MRB stays offerable until merge."""
    if _canon_task(row) != "MRB":
        return False
    repo = str(row.get("repo") or "").strip()
    ident = _norm_row_id(str(row.get("id") or ""))
    if not repo or not ident:
        return False
    if not _mrb_pass_verdict_on_record(doc, home, repo, ident):
        return False
    if row.get("draft") in (True, "true", "1", 1):
        return False
    if _mrb_row_merge_conflict_reason(row):
        return False
    if row.get("merged") in (True, "true", "1", 1):
        return False
    if str(row.get("state") or "").strip().lower() == "closed":
        return False
    if pr_exists is not None:
        try:
            if not bool(pr_exists(repo, ident.lstrip("#"))):
                return False
        except Exception:
            pass
    return True


def mrb_row_not_offerable_reason(
    row: dict,
    *,
    pr_exists=None,
) -> str | None:
    """Why an MRB row is not offerable, or None when it is (FR #4968).

    Used by purge logging so ``purge_dead_mrb`` names repo/PR and reason instead of
    a bare ``dropped purge_dead_mrb xN`` count.
    """
    if _canon_task(row) != "MRB":
        return None
    if row.get("merged") in (True, "true", "1", 1):
        return "merged"
    if str(row.get("state") or "").strip().lower() == "closed":
        return "state=closed"
    if row.get("draft") in (True, "true", "1", 1):
        return "draft"
    conflict = _mrb_row_merge_conflict_reason(row)
    if conflict:
        return f"merge-{conflict}"
    titleish = " ".join([str(row.get("title") or ""), str(row.get("line") or "")])
    if is_mrb_fix_pr_title(titleish) and not _mrb_fix_offer_stamped(row):
        # FR #2375: stacked parent-branch fixes are not MRB.
        # FR #8475: orphan / main-base rows are stamped mrb_fix_offer and stay.
        return "fix_pr_title"
    labs = row.get("labels") or ()
    if isinstance(labs, str):
        labs = [labs]
    labs_t = tuple(str(x) for x in labs)
    # FR #5500 / #6340: docs/mrb-* and pin-of-pin are skipped at auto enqueue
    # (resync/webhook) only. Once a row is queued --- orphan stamp, or explicit
    # !assign --- offer must not refuse with docs_mrb_pin / lesson_of_lesson.
    # Purge still drops lesson_of_lesson via mrb_row_purge_dead_reason (FR #4968).
    hold = pr_hold_reason(
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        labels=labs_t,
    )
    if hold:
        return f"hold:{hold}"
    # Structural / live URL checks stay in mrb_row_offerable (shared tail).
    return None


def _mrb_row_head_ref(row: dict) -> str:
    """Best-effort head ref from a queue row (string or nested head dict)."""
    head = row.get("head")
    if isinstance(head, dict):
        return str(head.get("ref") or head.get("name") or "")
    return str(
        head
        or row.get("head_ref")
        or row.get("headRefName")
        or row.get("branch")
        or ""
    )


def mrb_row_purge_dead_reason(
    row: dict,
    *,
    pr_exists=None,
) -> str | None:
    """Why ``purge_dead_mrb`` should drop an unaccepted MRB row, or None to keep.

    Includes every ``mrb_row_not_offerable_reason`` plus ``lesson_of_lesson``
    (FR #4917 / #4968). Offer path (FR #6340) must not refuse lesson_of_lesson
    once queued, but leaked meta tips still need queue hygiene.
    """
    why = mrb_row_not_offerable_reason(row, pr_exists=pr_exists)
    if why is not None:
        return why
    if _canon_task(row) != "MRB":
        return None
    labs = row.get("labels") or ()
    if isinstance(labs, str):
        labs = [labs]
    labs_t = tuple(str(x) for x in labs)
    if is_lesson_of_lesson_pr(
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        labels=labs_t,
        head_ref=_mrb_row_head_ref(row),
    ):
        return "lesson_of_lesson"
    return None


def mrb_row_offerable(
    row: dict,
    *,
    pr_exists=None,
) -> bool:
    """True when an MRB row has a resolvable pull URL (and optional live PR check).

    FR #595 / #247: never offer MRB without a real ``/pull/N`` (or explicit pr_id).
    FR #740 / #738: ``pr_exists`` must mean the pull is still **open** (merged/closed -> False).
    FR #2375: ``fix(mrb-N)`` / ``mrb-N-fix`` titles are never MRB targets (enqueue already
    skips them; reject at offer too if a row leaked in).
    FR #3928: hold label / ``on hold`` / ``must not merge`` body text → not offerable.
    FR #6340: offer must not refuse docs_mrb_pin / lesson_of_lesson once queued
    (auto enqueue still skips; purge drops lesson_of_lesson via
    ``mrb_row_purge_dead_reason`` - FR #4968 / #4917).
    FR #4968: intake light-triage boilerplate is stripped before lesson-of-lesson match.
    """
    early = mrb_row_not_offerable_reason(row, pr_exists=pr_exists)
    if early is not None:
        return False
    if _canon_task(row) != "MRB":
        return True
    raw = str(row.get("url") or "").strip()
    if ISSUE_URL_RE.search(raw) and not PULL_URL_RE.search(raw):
        return False
    url = resolve_assign_url(row)
    if not url or not PULL_URL_RE.search(url):
        return False
    m = PULL_URL_RE.search(url)
    if not m:
        return False
    repo, num = m.group("repo"), m.group("num")
    # FR #595: pull URL must target the row's repository (no cross-repo bait-and-switch).
    row_repo = str(row.get("repo") or "").strip().lower()
    if row_repo and repo.lower() != row_repo:
        return False
    if pr_exists is None:
        return True
    try:
        return bool(pr_exists(repo, num))
    except GitHubLookupUnknown:
        # FR #3188 / MRB #3207: unknown (rate limit, 5xx, !bored budget) is not "gone".
        # The structural same-repo pull URL check above already passed - still offer.
        return True
    except Exception:
        # Fail closed for MRB: do not offer a possibly-fake pull URL.
        return False


# FR #846 / #838: conventional-commit Fixes PR titles are never FR issues
# when the row type is otherwise unclear. FR #4257: skip this heuristic when
# the row URL is /issues/N or the event is ``issues``.
_PR_SHAPED_FR_TITLE_RE = re.compile(
    r"(?i)^(fix|docs|chore|feat|refactor|test|build|ci|perf|style)(?:\([^)]*\))?:",
)


def fr_row_offerable(row: dict, *, pr_exists=None, is_pull=None, issue_open=None) -> bool:
    """True when an FR row may be offered (FR #846 / #1313 / #2340 / #4257).

    Rejects FR rows that are actually pull requests:
    * URL is ``/pull/N``
    * event is ``pull_request``
    * optional ``is_pull(repo, num)`` is true for **any** PR state (open/merged/closed)
      - covers ``/issues/N`` URLs that still resolve to a PR page (#833 / #1313)
    * ``pr_exists`` kept as a deprecated alias for ``is_pull`` (do **not** pass the
      open-only ``github_pr_exists_checker`` here - MERGED PRs would stay offerable)
    * title looks like a conventional Fixes/docs PR **only when** the row is not
      already identified as a real issue (``/issues/N`` URL or ``issues`` event)
      - FR #4257: genuine issues titled ``CI:`` / ``fix:`` / ``docs:`` must stay offerable

    FR #2340: also rejects when the issue is CLOSED:
    * row ``state`` is ``closed`` (stamped on enqueue)
    * optional ``issue_open(repo, num)`` returns False (live GitHub open-state check)

    Non-FR rows return True.
    """
    if _canon_task(row) != "FR":
        return True
    event = str(row.get("event") or "").strip().lower()
    if event == "pull_request":
        return False
    raw = str(row.get("url") or "").strip()
    if PULL_URL_RE.search(raw):
        return False
    # BOB-G3 digests stay structurally offerable (real issues) so purge/heal paths
    # do not drop them; offer/assign skip via digest_issue_reason instead.
    # FR #4257: skip title heuristic when the row is clearly an issues row.
    clearly_issue = bool(ISSUE_URL_RE.search(raw) and not PULL_URL_RE.search(raw)) or (
        event == "issues"
    )
    title = str(row.get("title") or "").strip() or str(row.get("line") or "").strip()
    if not clearly_issue and _PR_SHAPED_FR_TITLE_RE.match(title):
        return False
    if str(row.get("state") or "").strip().lower() == "closed":
        return False
    checker = is_pull if is_pull is not None else pr_exists
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    if checker is not None and repo and num:
        try:
            if bool(checker(repo, num)):
                return False
        except Exception:
            pass
    if issue_open is not None and repo and num:
        try:
            if not bool(issue_open(repo, num)):
                return False
        except Exception:
            pass
    return True


# FR #2729: process-wide pr_exists verdict cache for the GET /bob/v1/report purge.
PR_EXISTS_CACHE_TTL_S = 60.0
_CACHE_MISS = object()


class TTLCache:
    """Thread-safe dict-like store whose entries expire after ``ttl_s`` seconds (FR #2729).

    Supports ``get`` / ``in`` / ``[]`` like the plain dict callers already pass as
    ``cache=``; its own small mutex is never the queue lock.
    """

    def __init__(self, ttl_s: float = PR_EXISTS_CACHE_TTL_S, *, clock=time.monotonic) -> None:
        self.ttl_s = float(ttl_s)
        self._clock = clock
        self._data: dict = {}
        self._mu = threading.Lock()

    def get(self, key, default=None):
        with self._mu:
            ent = self._data.get(key)
            if ent is None:
                return default
            if self._clock() - ent[0] > self.ttl_s:
                self._data.pop(key, None)
                return default
            return ent[1]

    def __contains__(self, key) -> bool:
        return self.get(key, _CACHE_MISS) is not _CACHE_MISS

    def __getitem__(self, key):
        val = self.get(key, _CACHE_MISS)
        if val is _CACHE_MISS:
            raise KeyError(key)
        return val

    def __setitem__(self, key, value) -> None:
        with self._mu:
            self._data[key] = (self._clock(), value)

    def clear(self) -> None:
        with self._mu:
            self._data.clear()

    def __len__(self) -> int:
        with self._mu:
            return len(self._data)


PR_EXISTS_SHARED_CACHE = TTLCache(PR_EXISTS_CACHE_TTL_S)
# FR #4574: after HTTP 403 or rate_remaining=0, skip pr_exists until reset.
_PR_EXISTS_BACKOFF_UNTIL = 0.0
_PR_EXISTS_NETWORK_CALLS = 0


def pr_exists_now() -> float:
    return time.time()


def pr_exists_backoff_active() -> bool:
    return pr_exists_now() < float(_PR_EXISTS_BACKOFF_UNTIL)


def clear_pr_exists_backoff() -> None:
    global _PR_EXISTS_BACKOFF_UNTIL, _PR_EXISTS_NETWORK_CALLS
    _PR_EXISTS_BACKOFF_UNTIL = 0.0
    _PR_EXISTS_NETWORK_CALLS = 0


def note_pr_exists_rate(hdrs, *, code: int | None = None) -> str | None:
    """Back off until X-RateLimit-Reset when the core limit is gone (FR #4574)."""
    global _PR_EXISTS_BACKOFF_UNTIL
    rem = _rate_remaining_from_headers(hdrs)
    reset_raw = ""
    retry_raw = ""
    if hdrs is not None:
        try:
            get = getattr(hdrs, "get", None)
            if callable(get):
                reset_raw = str(get("X-RateLimit-Reset") or get("x-ratelimit-reset") or "").strip()
                retry_raw = str(get("Retry-After") or get("retry-after") or "").strip()
        except Exception:
            reset_raw = ""
            retry_raw = ""
    rem_i = None
    if rem is not None and str(rem).strip() != "":
        try:
            rem_i = int(str(rem).strip())
        except ValueError:
            rem_i = None
    if rem_i == 0 or code == 403:
        until = pr_exists_now() + 60.0
        if reset_raw:
            try:
                parsed = float(reset_raw)
                if parsed > pr_exists_now():
                    until = parsed
            except ValueError:
                pass
        if retry_raw:
            try:
                until = max(until, pr_exists_now() + float(retry_raw))
            except ValueError:
                pass
        _PR_EXISTS_BACKOFF_UNTIL = max(float(_PR_EXISTS_BACKOFF_UNTIL), until)
        # FR #9865: core rate death also pauses unbudgeted issue_open probes.
        _arm_issue_open_backoff_until(until, rem=rem, log_warn=False)
        print(
            "WARN git-claim pr_exists backoff "
            f"until={int(_PR_EXISTS_BACKOFF_UNTIL)} "
            f"rate_remaining={rem if rem is not None else '-'} "
            f"calls={_PR_EXISTS_NETWORK_CALLS} "
            f"bored_budget={BORED_GITHUB_CALL_BUDGET}",
            flush=True,
        )
    return rem


# FR #3188: shared TTL across !bored so two seats do not re-GET the same rows every cycle.
ISSUE_OPEN_SHARED_CACHE = TTLCache(PR_EXISTS_CACHE_TTL_S)
IS_PULL_SHARED_CACHE = TTLCache(PR_EXISTS_CACHE_TTL_S)

# FR #9865: after HTTP 403 or rate_remaining=0, skip issue_open until reset.
_ISSUE_OPEN_BACKOFF_UNTIL = 0.0
_ISSUE_OPEN_NETWORK_CALLS = 0
_ISSUE_OPEN_BACKOFF_LOGGED = False


def issue_open_now() -> float:
    return time.time()


def issue_open_backoff_active() -> bool:
    if issue_open_now() < float(_ISSUE_OPEN_BACKOFF_UNTIL):
        return True
    # Share pr_exists core-rate pause so one 403 stops both probe kinds.
    return pr_exists_backoff_active()


def clear_issue_open_backoff() -> None:
    global _ISSUE_OPEN_BACKOFF_UNTIL, _ISSUE_OPEN_NETWORK_CALLS, _ISSUE_OPEN_BACKOFF_LOGGED
    _ISSUE_OPEN_BACKOFF_UNTIL = 0.0
    _ISSUE_OPEN_NETWORK_CALLS = 0
    _ISSUE_OPEN_BACKOFF_LOGGED = False


def _arm_issue_open_backoff_until(
    until: float, *, rem: str | None = None, log_warn: bool = True
) -> None:
    """Extend the global issue_open pause; WARN at most once per arming (FR #9865)."""
    global _ISSUE_OPEN_BACKOFF_UNTIL, _ISSUE_OPEN_BACKOFF_LOGGED
    prev = float(_ISSUE_OPEN_BACKOFF_UNTIL)
    _ISSUE_OPEN_BACKOFF_UNTIL = max(prev, float(until))
    if not log_warn:
        return
    if _ISSUE_OPEN_BACKOFF_LOGGED and prev >= issue_open_now():
        return
    _ISSUE_OPEN_BACKOFF_LOGGED = True
    print(
        "WARN git-claim issue_open backoff "
        f"until={int(_ISSUE_OPEN_BACKOFF_UNTIL)} "
        f"rate_remaining={rem if rem is not None else '-'} "
        f"calls={_ISSUE_OPEN_NETWORK_CALLS}",
        flush=True,
    )


def note_issue_open_rate(hdrs, *, code: int | None = None) -> str | None:
    """Back off until X-RateLimit-Reset / Retry-After when core limit is gone (FR #9865)."""
    rem = _rate_remaining_from_headers(hdrs)
    reset_raw = ""
    retry_raw = ""
    if hdrs is not None:
        try:
            get = getattr(hdrs, "get", None)
            if callable(get):
                reset_raw = str(get("X-RateLimit-Reset") or get("x-ratelimit-reset") or "").strip()
                retry_raw = str(get("Retry-After") or get("retry-after") or "").strip()
        except Exception:
            reset_raw = ""
            retry_raw = ""
    rem_i = None
    if rem is not None and str(rem).strip() != "":
        try:
            rem_i = int(str(rem).strip())
        except ValueError:
            rem_i = None
    if rem_i == 0 or code == 403:
        until = issue_open_now() + 60.0
        if reset_raw:
            try:
                parsed = float(reset_raw)
                if parsed > issue_open_now():
                    until = parsed
            except ValueError:
                pass
        if retry_raw:
            try:
                until = max(until, issue_open_now() + float(retry_raw))
            except ValueError:
                pass
        _arm_issue_open_backoff_until(until, rem=rem, log_warn=True)
        # Keep pr_exists paused too while core remaining is zero.
        global _PR_EXISTS_BACKOFF_UNTIL
        _PR_EXISTS_BACKOFF_UNTIL = max(float(_PR_EXISTS_BACKOFF_UNTIL), until)
    return rem


def _issue_open_backoff_from_api_budget(home: Path | None) -> bool:
    """If durable GithubApiBudget already has rate_remaining=0 (or core floor), arm pause (FR #9865)."""
    try:
        import github_api_budget as gab
    except Exception:
        return False
    root: Path | None = None
    if home is not None:
        root = Path(home)
    else:
        env_home = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
        if env_home:
            root = Path(env_home)
    if root is None or not root.is_dir():
        return False
    try:
        bud = gab.GithubApiBudget(root, log=lambda _s: None)
        bud.clear_rate_limit_if_reset()
        rem = bud.rate_remaining
        if rem is None:
            return False
        rem_i = int(rem)
        # rate_remaining=0 always pauses; core floor pause when budget already in backoff.
        if rem_i != 0 and not (bud.in_backoff() and rem_i < int(bud.floor)):
            return False
        until = issue_open_now() + 60.0
        if bud.rate_reset is not None:
            try:
                rst = float(bud.rate_reset)
                if rst > issue_open_now():
                    until = rst
            except (TypeError, ValueError):
                pass
        _arm_issue_open_backoff_until(until, rem=str(rem_i), log_warn=True)
        return True
    except Exception:
        return False

# FR #3188: at most one live GitHub lookup while picking the next !bored offer.
# FR #3212: !bored is local-state only - zero live GitHub calls on the IRC offer path.
BORED_GITHUB_CALL_BUDGET = 0


class GitHubLookupUnknown(Exception):
    """GitHub state is unknown (non-404 error, timeout, budget). Never treat as closed."""


def _log_github_lookup_failure(
    kind: str,
    repo: str,
    num: str,
    *,
    code: int | None = None,
    rate_remaining: str | None = None,
    exc: BaseException | None = None,
    log=None,
) -> None:
    """Log lookup failure without token (FR #3188 / #3158 item 2)."""
    bits = [f"WARN git-claim {kind} unknown {repo}#{num}"]
    if code is not None:
        bits.append(f"http={code}")
    if rate_remaining is not None and str(rate_remaining).strip() != "":
        bits.append(f"rate_remaining={rate_remaining}")
    if exc is not None:
        bits.append(type(exc).__name__)
    msg = " ".join(bits)
    if log is not None:
        try:
            log(msg)
            return
        except Exception:
            pass
    print(msg, flush=True)


def _rate_remaining_from_headers(hdrs) -> str | None:
    if hdrs is None:
        return None
    try:
        get = getattr(hdrs, "get", None)
        if callable(get):
            return get("X-RateLimit-Remaining") or get("x-ratelimit-remaining")
    except Exception:
        return None
    return None


def _cache_peek(store, key):
    """Cache-only lookup for a checker store (TTLCache or plain dict); never network."""
    try:
        if hasattr(store, "get"):
            return store.get(key, _CACHE_MISS)
        return store[key] if key in store else _CACHE_MISS
    except Exception:
        return _CACHE_MISS


def _budgeted_github(fn, budget: "_GithubCallBudget", kind: str | None = None):
    """Wrap a checker so only real GitHub calls consume the shared !bored budget (FR #3188).

    Fix for MRB #3207 FAIL: cache hits (checker ``peek``) are free, and repeat calls for the
    same row in one pass share one verdict, so ``mrb_already_done`` + ``mrb_row_offerable``
    cost one lookup, not two. Any checker failure surfaces as ``GitHubLookupUnknown``.
    """
    if fn is None:
        return None
    label = kind or getattr(fn, "__name__", "check")

    def _check(repo: str, num: str):
        return budget.call(fn, repo, num, kind=label)

    _check.budget = budget
    return _check


class _GithubCallBudget:
    """Shared network-call counter for one offer_focus_top / offer_top pass (FR #3188)."""

    def __init__(self, limit: int = BORED_GITHUB_CALL_BUDGET) -> None:
        self.limit = int(limit)
        self.used = 0  # real (network) checker calls only
        self._memo: dict = {}

    def call(self, fn, repo: str, num: str, *, kind: str = "check"):
        key = (kind, id(fn), str(repo or "").strip().lower(), str(num or "").strip().lstrip("#"))
        if key in self._memo:
            ok, val = self._memo[key]
            if ok:
                return val
            raise val
        peek = getattr(fn, "peek", None)
        if callable(peek):
            try:
                hit = peek(repo, num)
            except Exception:
                hit = _CACHE_MISS
            if hit is not _CACHE_MISS:
                self._memo[key] = (True, hit)
                return hit
        if self.used >= self.limit:
            raise GitHubLookupUnknown(
                f"bored github call budget exhausted ({self.limit})"
            )
        self.used += 1
        try:
            val = fn(repo, num)
        except GitHubLookupUnknown as e:
            self._memo[key] = (False, e)
            raise
        except Exception as e:
            err = GitHubLookupUnknown(f"{kind} {repo}#{num} {type(e).__name__}")
            err.__cause__ = e
            self._memo[key] = (False, err)
            raise err from e
        self._memo[key] = (True, val)
        return val


def _live_verdict(check, row: dict) -> bool | None:
    """True/False from a (budgeted) checker for this row; None when unknown (FR #3188)."""
    if check is None:
        return None
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    if not repo or not num:
        return None
    try:
        return bool(check(repo, num))
    except Exception:
        return None


def _drop_unaccepted_row(
    doc: dict,
    row: dict,
    *,
    kind: str,
    reason: str,
    log=None,
    home: Path | None = None,
) -> int:
    """Remove one definitively-dead unaccepted row and log why (FR #3188 / MRB #3207).

    FR #9402: when ``home`` is set, also clear offered_to seat-holds for the job.
    """
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    task = _canon_task(row)
    if home is not None:
        _clear_unaccepted_offer_pins_for_job(home, doc, repo, task, num)
    before = len(doc.get("unaccepted") or [])
    doc["unaccepted"] = [
        r
        for r in (doc.get("unaccepted") or [])
        if not (
            isinstance(r, dict)
            and str(r.get("repo") or "").strip() == repo
            and str(r.get("id") or "").strip().lstrip("#") == num
            and _canon_task(r) == task
        )
    ]
    dropped = before - len(doc["unaccepted"])
    if dropped:
        _log_queue_purge(f"INFO git-claim purge {kind} {repo}#{num} reason={reason}", log=log)
    return dropped


def github_pr_exists_checker(
    *,
    home: Path | None = None,
    cache: dict | None = None,
):
    """Return ``pr_exists(repo, num)`` -> True only for an **open** pull (FR #595 / #740).

    Merged or closed PRs still return HTTP 200 from GitHub; those must be False so
    seats are not re-offered MRB after DONE PASS/FAIL. Returns None when offline /
    no token (structural URL checks in ``mrb_row_offerable`` still apply).

    FR #3188: HTTP 404/410 -> False (gone). Any other failure raises
    ``GitHubLookupUnknown`` (never False) so purge paths cannot wipe the queue.
    """
    try:
        import gh_filer
    except Exception:
        return None
    # Prefer digest-home token when present (chair / LocalSystem); do not leak env (FR #2540).
    with _scoped_digest_home(home):
        src = gh_filer.ensure_gh_token_env()
    if src == "none":
        return None
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return None
    store: dict = cache if cache is not None else PR_EXISTS_SHARED_CACHE

    def _check(repo: str, num: str) -> bool:
        key = f"{repo}#{num}"
        hit = store.get(key, _CACHE_MISS)  # FR #2729: one lookup (TTL entry may expire between two)
        if hit is not _CACHE_MISS:
            return hit
        if pr_exists_backoff_active():
            raise GitHubLookupUnknown(
                f"pr_exists {repo}#{num} backoff rate_remaining=0"
            )
        api = f"https://api.github.com/repos/{repo}/pulls/{num}"
        req = urllib.request.Request(
            api,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "bobiverse-gitclaim",
            },
            method="GET",
        )
        try:
            global _PR_EXISTS_NETWORK_CALLS
            _PR_EXISTS_NETWORK_CALLS += 1
            with urllib.request.urlopen(req, timeout=8) as resp:
                note_pr_exists_rate(getattr(resp, "headers", None))
                if 200 <= int(getattr(resp, "status", 200) or 200) < 300:
                    raw = resp.read()
                    try:
                        body = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
                    except (TypeError, ValueError, UnicodeDecodeError):
                        body = {}
                    # FR #740 / #738: only open pulls are offerable MRB targets.
                    ok = str((body or {}).get("state") or "").lower() == "open"
                    store[key] = ok
                    return ok
                raise GitHubLookupUnknown(
                    f"pr_exists {repo}#{num} http={getattr(resp, 'status', '?')}"
                )
        except urllib.error.HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            note_pr_exists_rate(getattr(e, "headers", None), code=code)
            if code in (404, 410):
                store[key] = False
                return False
            _log_github_lookup_failure(
                "pr_exists",
                repo,
                num,
                code=code,
                rate_remaining=_rate_remaining_from_headers(getattr(e, "headers", None)),
                exc=e,
            )
            raise GitHubLookupUnknown(f"pr_exists {repo}#{num} http={code}") from e
        except GitHubLookupUnknown:
            raise
        except Exception as e:
            _log_github_lookup_failure("pr_exists", repo, num, exc=e)
            raise GitHubLookupUnknown(f"pr_exists {repo}#{num} {type(e).__name__}") from e

    _check.peek = lambda repo, num: _cache_peek(store, f"{repo}#{num}")
    return _check


def github_is_pull_checker(
    *,
    home: Path | None = None,
    cache: dict | None = None,
):
    """Return ``is_pull(repo, num)`` -> True when the number is a pull in **any** state (FR #1313).

    Unlike ``github_pr_exists_checker`` (open-only for MRB), MERGED/CLOSED pulls still
    return True so they are never offered as FR. Returns None when offline / no token.

    FR #3188: 404/410 -> False. Other failures raise ``GitHubLookupUnknown``.
    """
    try:
        import gh_filer
    except Exception:
        return None
    with _scoped_digest_home(home):
        src = gh_filer.ensure_gh_token_env()
    if src == "none":
        return None
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return None
    store: dict = cache if cache is not None else IS_PULL_SHARED_CACHE

    def _check(repo: str, num: str) -> bool:
        key = f"is_pull:{repo}#{num}"
        hit = store.get(key, _CACHE_MISS) if hasattr(store, "get") else (
            store[key] if key in store else _CACHE_MISS
        )
        if hit is not _CACHE_MISS:
            return hit
        if key in store and not hasattr(store, "get"):
            return store[key]
        api = f"https://api.github.com/repos/{repo}/pulls/{num}"
        req = urllib.request.Request(
            api,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "bobiverse-gitclaim",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                ok = 200 <= int(getattr(resp, "status", 200) or 200) < 300
                store[key] = ok
                return ok
        except urllib.error.HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            if code in (404, 410):
                store[key] = False
                return False
            _log_github_lookup_failure(
                "is_pull",
                repo,
                num,
                code=code,
                rate_remaining=_rate_remaining_from_headers(getattr(e, "headers", None)),
                exc=e,
            )
            raise GitHubLookupUnknown(f"is_pull {repo}#{num} http={code}") from e
        except GitHubLookupUnknown:
            raise
        except Exception as e:
            _log_github_lookup_failure("is_pull", repo, num, exc=e)
            raise GitHubLookupUnknown(f"is_pull {repo}#{num} {type(e).__name__}") from e

    _check.peek = lambda repo, num: _cache_peek(store, f"is_pull:{repo}#{num}")
    return _check


def github_issue_open_checker(
    *,
    home: Path | None = None,
    cache: dict | None = None,
):
    """Return ``issue_open(repo, num)`` -> True only for an **open** issue (FR #2340).

    Closed issues and 404/410 return False so seats are not offered dead FR work.
    Pull-request numbers that still appear under ``/issues/N`` also return False
    when ``state`` is not open (``is_pull`` remains the primary PR gate). Returns
    None when offline / no token (structural / stamped-state checks still apply).

    FR #3188: non-404 failures raise ``GitHubLookupUnknown`` - never False - so a
    rate-limit / 5xx / timeout cannot purge the whole unaccepted queue.

    FR #9865: when core ``rate_remaining=0`` (or ApiBudget already at the floor),
    pause all issue_open probes until reset / Retry-After — one WARN, no 403 storm.
    """
    try:
        import gh_filer
    except Exception:
        return None
    with _scoped_digest_home(home):
        src = gh_filer.ensure_gh_token_env()
    if src == "none":
        return None
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return None
    store: dict = cache if cache is not None else ISSUE_OPEN_SHARED_CACHE

    def _check(repo: str, num: str) -> bool:
        key = f"issue_open:{repo}#{num}"
        if hasattr(store, "get"):
            hit = store.get(key, _CACHE_MISS)
            if hit is not _CACHE_MISS:
                return hit
        elif key in store:
            return store[key]
        if not issue_open_backoff_active():
            _issue_open_backoff_from_api_budget(home)
        if issue_open_backoff_active():
            raise GitHubLookupUnknown(
                f"issue_open {repo}#{num} backoff rate_remaining=0"
            )
        api = f"https://api.github.com/repos/{repo}/issues/{num}"
        req = urllib.request.Request(
            api,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "bobiverse-gitclaim",
            },
            method="GET",
        )
        try:
            global _ISSUE_OPEN_NETWORK_CALLS
            _ISSUE_OPEN_NETWORK_CALLS += 1
            with urllib.request.urlopen(req, timeout=8) as resp:
                note_issue_open_rate(getattr(resp, "headers", None))
                if 200 <= int(getattr(resp, "status", 200) or 200) < 300:
                    raw = resp.read()
                    try:
                        body = json.loads(
                            raw.decode("utf-8")
                            if isinstance(raw, (bytes, bytearray))
                            else raw
                        )
                    except (TypeError, ValueError, UnicodeDecodeError):
                        body = {}
                    ok = str((body or {}).get("state") or "").lower() == "open"
                    store[key] = ok
                    return ok
                raise GitHubLookupUnknown(
                    f"issue_open {repo}#{num} http={getattr(resp, 'status', '?')}"
                )
        except urllib.error.HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            rem = note_issue_open_rate(getattr(e, "headers", None), code=code)
            if code in (404, 410):
                store[key] = False
                return False
            # FR #9865: rate-limit arm already emitted one backoff WARN — skip storm.
            if issue_open_backoff_active() and (code == 403 or rem == "0"):
                raise GitHubLookupUnknown(
                    f"issue_open {repo}#{num} http={code}"
                ) from e
            _log_github_lookup_failure(
                "issue_open",
                repo,
                num,
                code=code,
                rate_remaining=rem,
                exc=e,
            )
            raise GitHubLookupUnknown(f"issue_open {repo}#{num} http={code}") from e
        except GitHubLookupUnknown:
            raise
        except Exception as e:
            _log_github_lookup_failure("issue_open", repo, num, exc=e)
            raise GitHubLookupUnknown(f"issue_open {repo}#{num} {type(e).__name__}") from e

    _check.peek = lambda repo, num: _cache_peek(store, f"issue_open:{repo}#{num}")
    return _check


def _purge_fr_that_are_pulls(doc: dict, *, is_pull=None, issue_open=None) -> int:
    """Drop unaccepted FR rows whose id is a GitHub pull (any state) - FR #1313 / #2340."""
    before = len(doc.get("unaccepted") or [])
    kept: list[dict] = []
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if _canon_task(row) == "FR" and not fr_row_offerable(
            row, is_pull=is_pull, issue_open=issue_open
        ):
            continue
        kept.append(row)
    doc["unaccepted"] = kept
    return before - len(kept)


def _fr_issue_is_closed(row: dict, *, issue_open=None) -> bool:
    """True when an FR row's GitHub issue is CLOSED (stamped and/or live check)."""
    if _canon_task(row) != "FR":
        return False
    if str(row.get("state") or "").strip().lower() == "closed":
        return True
    if issue_open is None:
        return False
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    if not repo or not num:
        return False
    try:
        return not bool(issue_open(repo, num))
    except Exception:
        return False


def _log_queue_purge(msg: str, *, log=None) -> None:
    """Log a queue purge with reason (FR #3188 / FR #2899 parity)."""
    line = str(msg)
    if log is not None:
        try:
            log(line)
            return
        except Exception:
            pass
    print(line, flush=True)


def _purge_closed_fr_unaccepted(
    doc: dict, *, issue_open=None, home: Path | None = None, log=None
) -> int:
    """Drop unaccepted FR rows whose GitHub issue is CLOSED (FR #2340 / #9835).

    Mirrors ``_purge_dead_mrb_unaccepted`` for FR: stamped ``state=closed`` and/or
    live ``issue_open(repo, num) is False`` remove the row before offer.

    FR #3188: ``issue_open`` raising / unknown must not purge (see ``_fr_issue_is_closed``).
    Every drop is logged with a reason so a wipe cannot happen silently.

    FR #9835: when ``home`` is set, also clear FR/PR/UAT seat-holds for the dropped
    id so a residual ``via=offer`` pin cannot busy the seat after the row is gone.
    """
    before = len(doc.get("unaccepted") or [])
    kept: list[dict] = []
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if _fr_issue_is_closed(row, issue_open=issue_open):
            repo = str(row.get("repo") or "").strip()
            ident = str(row.get("id") or "").strip()
            stamped = str(row.get("state") or "").strip().lower() == "closed"
            why = "stamped-state=closed" if stamped else "issue_open=False"
            _log_queue_purge(
                f"INFO git-claim purge closed-fr {repo}{ident} reason={why}",
                log=log,
            )
            if home is not None and repo and ident:
                with contextlib.suppress(Exception):
                    _clear_job_seat_holds_unlocked(home, repo, "FR", ident)
                    _clear_job_seat_holds_unlocked(home, repo, "PR", ident)
                    _clear_job_seat_holds_unlocked(home, repo, "UAT", ident)
            continue
        kept.append(row)
    doc["unaccepted"] = kept
    return before - len(kept)


def _purge_closed_fr_accepted(doc: dict, *, issue_open=None, home: Path | None = None) -> int:
    """Move orphan accepted FR rows whose GitHub issue is CLOSED into done (FR #2361).

    Unaccepted CLOSED purge (#2348 / FR #2340) left ACC rows (e.g. #2340 on
    marchhare) stuck forever. Mirrors ``_purge_dead_mrb_accepted`` for FR.

    FR #4851: nick-held ACC (nick / accepted_by / offered_to) stays in accepted with
    ``cancel_pending`` until the seat NACKs. Do **not** ``clear_seat_doing`` for those
    rows - digest idle while the seat still holds ACK is the #4851 defect class.
    Orphan ACC (no seat holder) still moves to done CLOSED as before.
    """
    before = len(doc.get("accepted") or [])
    kept: list[dict] = []
    done = doc.setdefault("done", [])
    for row in doc.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        if _fr_issue_is_closed(row, issue_open=issue_open):
            seat = _seat_holder_nick(row)
            if seat:
                row["state"] = "closed"
                row["cancel_pending"] = True
                if home is not None:
                    with contextlib.suppress(Exception):
                        enqueue_seat_cancel(home, row)
                kept.append(row)
                continue
            fin = dict(row)
            fin["result"] = "CLOSED"
            fin["done_ts"] = _utc_now()
            fin["state"] = "closed"
            done.append(fin)
            continue
        kept.append(row)
    doc["accepted"] = kept
    return before - len(kept)


def _purge_dead_mrb_unaccepted(
    doc: dict,
    *,
    pr_exists=None,
    home: Path | None = None,
    open_pulls: dict | None = None,
    fetched_repos: set | None = None,
    log=None,
) -> int:
    """Drop unaccepted MRB rows that are already done or no longer an open pull (FR #740 / #1323 / #2458).

    FR #1585: when ``pr_exists`` says the pull is still open, keep the row and clear
    a stale ledger ``mrb_done`` stamp so the next offline scan cannot re-kill it.

    FR #2458: when ``open_pulls`` + ``fetched_repos`` are provided (resync), drop MRB
    rows whose id is absent from that repo's open-pull set (merged/closed webhook miss).

    FR #4968: every drop logs ``repo`` + ``#id`` + reason (not only a bare count).
    """
    before = len(doc.get("unaccepted") or [])
    kept: list[dict] = []
    fetched = {str(x) for x in (fetched_repos or ())}
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if _canon_task(row) == "MRB":
            # FR #4574: needs_human rows are not offerable. Do not spend pr_exists on them.
            row_pr = None if row_needs_human(row, "") else pr_exists
            repo = str(row.get("repo") or "").strip()
            ident = _norm_row_id(str(row.get("id") or ""))
            label = f"{repo}{ident}" if repo or ident else "?"
            if mrb_already_done(doc, row, home=home, pr_exists=row_pr):
                _log_queue_purge(
                    f"INFO git-claim purge_dead_mrb {label} reason=already_done",
                    log=log,
                )
                continue
            # FR #4968: purge uses mrb_row_purge_dead_reason so lesson_of_lesson
            # still drops (offer path deliberately omits that refuse - FR #6340).
            why = mrb_row_purge_dead_reason(row, pr_exists=row_pr)
            if why is not None or not mrb_row_offerable(row, pr_exists=row_pr):
                if why is None:
                    why = "not_offerable"
                _log_queue_purge(
                    f"INFO git-claim purge_dead_mrb {label} reason={why}",
                    log=log,
                )
                continue
            if (
                open_pulls is not None
                and repo
                and repo in fetched
                and ident
                and ident not in (open_pulls.get(repo) or set())
            ):
                _log_queue_purge(
                    f"INFO git-claim purge_dead_mrb {label} reason=not_in_open_pulls",
                    log=log,
                )
                continue
            if home is not None and row_pr is not None:
                if repo and ident and mrb_ledger_done_hold(home, repo, ident):
                    # FR #8278: keep the stamp when DONE PASS / merge-on-green PASS
                    # is on record (ci-wait). Premature DONE without a verdict still
                    # clears under FR #1585 when GitHub says open.
                    if not _mrb_review_finished(doc, home, repo, ident):
                        with contextlib.suppress(Exception):
                            if bool(row_pr(repo, ident.lstrip("#"))):
                                clear_mrb_done(home, repo, ident)
        kept.append(row)
    doc["unaccepted"] = kept
    return before - len(kept)


# FR #2729: at most one purge at a time; concurrent report GETs skip instead of queueing.
_PURGE_INFLIGHT = threading.Lock()


def _mrb_verdict_key(repo, num) -> tuple[str, str]:
    return (str(repo or "").strip().lower(), str(num or "").strip().lstrip("#"))


def _mrb_row_verdict_key(row: dict) -> tuple[str, str]:
    return _mrb_verdict_key(row.get("repo"), row.get("id"))


def _is_mrb_row(row) -> bool:
    return isinstance(row, dict) and _canon_task(row) == "MRB"


def purge_dead_mrb_rows(
    home: Path, *, pr_exists=None, lock_timeout: float | None = None
) -> int:
    """FR #2458: drop dead unaccepted/accepted MRB rows; persist if changed.

    FR #2729: never call GitHub (``pr_exists``) while holding the queue lock.

    1. Under the lock, snapshot the queue.
    2. Outside the lock, ask ``pr_exists`` about every MRB row in the snapshot
       (judged on a scratch copy; no ledger/digest side effects).
    3. Re-lock, reload the queue and run the usual purge against those cached
       verdicts only. MRB rows that appeared after the snapshot are left alone.

    ``lock_timeout`` (seconds) bounds each lock wait; when the lock is busy the
    purge is skipped (returns 0). Only one purge runs at a time; a concurrent
    caller returns 0 at once.
    """
    if not _PURGE_INFLIGHT.acquire(blocking=False):
        return 0
    try:
        try:
            with _lock(home, timeout=lock_timeout):
                snap = copy.deepcopy(_load_queue_unlocked(home))
        except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
            return 0
        if not any(
            (_is_mrb_row(r) or _is_fix_row(r))
            for b in ("unaccepted", "accepted")
            for r in (snap.get(b) or [])
        ):
            return 0

        verdicts: dict[tuple[str, str], bool] = {}
        memo = None
        if pr_exists is not None:

            def _record(repo, num):
                key = _mrb_verdict_key(repo, num)
                if key in verdicts:
                    return verdicts[key]
                ok = bool(pr_exists(repo, num))  # network: outside the queue lock
                verdicts[key] = ok
                return ok

            scratch = copy.deepcopy(snap)
            with contextlib.suppress(Exception):
                _purge_dead_mrb_unaccepted(scratch, pr_exists=_record, home=None)
            with contextlib.suppress(Exception):
                _purge_dead_mrb_accepted(scratch, pr_exists=_record, home=None)
            with contextlib.suppress(Exception):
                _purge_dead_fix_unaccepted(scratch, pr_exists=_record)
            with contextlib.suppress(Exception):
                _purge_dead_fix_accepted(scratch, pr_exists=_record, home=None)

            def memo(repo, num):  # noqa: F811 - cached verdicts only, never network
                return verdicts.get(_mrb_verdict_key(repo, num), True)

        try:
            with _lock(home, timeout=lock_timeout):
                doc = _load_queue_unlocked(home)
                held: dict[str, list] = {}
                for b in ("unaccepted", "accepted"):
                    rows = list(doc.get(b) or [])
                    held[b] = rows
                    if memo is not None:
                        doc[b] = [
                            r
                            for r in rows
                            if not (
                                (_is_mrb_row(r) or _is_fix_row(r))
                                and _mrb_row_verdict_key(r) not in verdicts
                            )
                        ]
                n = _purge_dead_mrb_unaccepted(doc, pr_exists=memo, home=home)
                n += _purge_dead_mrb_accepted(doc, pr_exists=memo, home=home)
                n += _purge_dead_fix_unaccepted(doc, pr_exists=memo)
                n += _purge_dead_fix_accepted(doc, pr_exists=memo, home=home)
                if memo is not None:
                    for b in ("unaccepted", "accepted"):
                        kept = {id(r) for r in doc.get(b) or []}
                        doc[b] = [
                            r
                            for r in held[b]
                            if id(r) in kept
                            or (
                                (_is_mrb_row(r) or _is_fix_row(r))
                                and _mrb_row_verdict_key(r) not in verdicts
                            )
                        ]
                if n:
                    _write_queue(queue_path(home), doc)
                return n
        except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
            return 0
    finally:
        _PURGE_INFLIGHT.release()



def _mrb_is_dead(doc: dict, row: dict, *, pr_exists=None, home: Path | None = None) -> bool:
    """True when an MRB row should leave the live queues (merged/closed/already-done)."""
    if _canon_task(row) != "MRB":
        return False
    row_pr = None if row_needs_human(row, "") else pr_exists
    if mrb_already_done(doc, row, home=home, pr_exists=row_pr):
        return True
    return not mrb_row_offerable(row, pr_exists=row_pr)



_MRB_DOING_RX = re.compile(
    r"(?i)\bMRB\b(?:\s+(?:SimonBarnett/)?([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?))?\s*#\s*(\d+)"
)

# Digest / tray work text (shop_listen.short_work): ``a-search FR #1018``.
# Also task-first ``FR SimonBarnett/a-search#1018`` and bare ``FR #1018``.
_DIGEST_WORK_RXES = (
    re.compile(
        r"(?i)\b(?P<repo>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)\s+"
        r"(?P<task>FR|MRB|UAT)\s*#\s*(?P<num>\d+)"
    ),
    re.compile(
        r"(?i)\b(?P<task>FR|MRB|UAT)\s+"
        r"(?P<repo>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)\s*#\s*(?P<num>\d+)"
    ),
    re.compile(r"(?i)\b(?P<task>FR|MRB|UAT)\s*#\s*(?P<num>\d+)"),
)


def parse_digest_work(work: str) -> dict | None:
    """Parse digest ``working_on`` / worker_list work into task/id/repo hints (FR #3867)."""
    text = str(work or "").strip()
    if not text:
        return None
    for rx in _DIGEST_WORK_RXES:
        m = rx.search(text)
        if not m:
            continue
        gd = m.groupdict()
        task = str(gd.get("task") or "").strip().upper()
        num = str(gd.get("num") or "").strip()
        if not task or not num:
            continue
        repo_raw = str(gd.get("repo") or "").strip()
        out: dict = {"task": task, "id": f"#{int(num)}", "repo_short": "", "repo": ""}
        if repo_raw:
            if "/" in repo_raw:
                out["repo"] = repo_raw
                out["repo_short"] = repo_raw.rsplit("/", 1)[-1]
            else:
                out["repo_short"] = repo_raw
                out["repo"] = f"SimonBarnett/{repo_raw}"
        return out
    return None


def row_matches_digest_work(row: dict, work: str) -> bool:
    """True when a queue row is the job named by digest work text (FR #3867)."""
    if not isinstance(row, dict):
        return False
    parsed = parse_digest_work(work)
    if not parsed:
        return False
    if str(row.get("task") or "").strip().upper() != parsed["task"]:
        return False
    rid = str(row.get("id") or "").strip().lstrip("#")
    if rid != str(parsed["id"]).lstrip("#"):
        return False
    repo = str(row.get("repo") or "").strip()
    full = str(parsed.get("repo") or "").strip()
    short = str(parsed.get("repo_short") or "").strip()
    if full and "/" in full:
        return repo.lower() == full.lower() or repo.lower().endswith("/" + full.rsplit("/", 1)[-1].lower())
    if short:
        return repo.lower() == short.lower() or repo.lower().endswith("/" + short.lower())
    # Bare ``FR #N``: task+id only (caller should prefer unique matches).
    return True


def unaccepted_matches_digest_work(home: Path, work: str) -> bool:
    """True when any unaccepted queue row matches digest work text (FR #3867)."""
    if not parse_digest_work(work):
        return False
    try:
        doc = load_queue(home)
    except Exception:  # noqa: BLE001
        return False
    for row in doc.get("unaccepted") or []:
        if row_matches_digest_work(row, work):
            return True
    return False


def _orphan_mrb_repo_num(
    work: str, *, default_repo: str = "SimonBarnett/bobiverse"
) -> tuple[str, str] | None:
    m = _MRB_DOING_RX.search(str(work or ""))
    if not m:
        return None
    repo_part = (m.group(1) or "").strip()
    num = str(int(m.group(2)))
    if repo_part and "/" in repo_part:
        repo = repo_part
    elif repo_part:
        repo = f"SimonBarnett/{repo_part}"
    else:
        repo = default_repo
    return repo, num


def clear_orphan_digest_mrb_doing(
    home: Path,
    *,
    pr_exists=None,
    default_repo: str = "SimonBarnett/bobiverse",
) -> int:
    """Idle seats whose digest still says doing MRB #N after the PR is dead (FR #1508).

    FR #1430 clears doing when an *accepted* MERGED row is purged. When the ACC
    row is already gone (DONE lost / webhook race), seats stay nak-busy forever.
    Call from !bored / offer paths with the live `pr_exists` checker.

    FR #1714: also scan pid-keyed ``workers`` map (and machine ``working_on``) -
    ``worker_list`` can already be idle while the map keeps ``running`` + working_on.
    """
    if pr_exists is None or home is None:
        return 0
    import bobreport

    doc = bobreport.load_digest(home)
    machines = doc.get("machines") if isinstance(doc, dict) else None
    if not isinstance(machines, dict):
        return 0
    cleared = 0
    seen_nicks: set[str] = set()

    def _try_clear(nick: str, num: str, repo: str) -> None:
        nonlocal cleared
        n = (nick or "").strip()
        if not n or n.lower() in seen_nicks:
            return
        try:
            still_open = bool(pr_exists(repo, num))
        except Exception:
            return
        if still_open:
            return
        with contextlib.suppress(Exception):
            out = bobreport.clear_seat_doing(home, n, only_if_work_contains=num)
            if getattr(out, "ok", False):
                cleared += 1
                seen_nicks.add(n.lower())

    for mid, ent in list(machines.items()):
        if not isinstance(ent, dict):
            continue
        rows = list(ent.get("worker_list") or [])
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("state") or "").lower() != "doing":
                continue
            parsed = _orphan_mrb_repo_num(str(row.get("work") or ""), default_repo=default_repo)
            if not parsed:
                continue
            repo, num = parsed
            _try_clear(str(row.get("nick") or "").strip(), num, repo)
        # FR #1714: workers map + machine-level working_on even when list is idle.
        workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
        for pid_s, w in list(workers.items()):
            if not isinstance(w, dict):
                continue
            wo = str(w.get("working_on") or "").strip()
            if not wo:
                continue
            parsed = _orphan_mrb_repo_num(wo, default_repo=default_repo)
            if not parsed:
                continue
            repo, num = parsed
            nick = str(w.get("nick") or "").strip()
            if not nick:
                nick = f"{mid}-{pid_s}"
            _try_clear(nick, num, repo)
        mach_wo = str(ent.get("working_on") or "").strip()
        if mach_wo:
            parsed = _orphan_mrb_repo_num(mach_wo, default_repo=default_repo)
            if parsed:
                repo, num = parsed
                # Prefer a concrete seat nick from workers/list still holding that PR.
                nick = ""
                for row in rows:
                    if isinstance(row, dict) and num in str(row.get("work") or ""):
                        nick = str(row.get("nick") or "").strip()
                        if nick:
                            break
                if not nick:
                    for pid_s, w in list(workers.items()):
                        if isinstance(w, dict) and num in str(w.get("working_on") or ""):
                            nick = str(w.get("nick") or f"{mid}-{pid_s}").strip()
                            if nick:
                                break
                if nick:
                    _try_clear(nick, num, repo)
    return cleared


def _purge_dead_mrb_accepted(
    doc: dict,
    *,
    pr_exists=None,
    pr_merged=None,
    home: Path | None = None,
) -> int:
    """Move accepted MRB rows whose PR is already merged/closed into done.

    Without this, seats stay ``doing`` on MERGED PRs (#1171/#1236 class) and
    never !bored for new work - looks like an empty offer queue to monitors.

    FR #2650: when ``pr_merged`` says the pull was not merged (closed unmerged),
    stamp ``result=CLOSED`` instead of ``MERGED`` so queue.json matches GitHub.
    When ``pr_merged`` is omitted, keep the historical MERGED stamp for dead rows
    (open-only ``pr_exists`` cannot distinguish merged vs closed-unmerged).
    """
    before = len(doc.get("accepted") or [])
    kept: list[dict] = []
    done = doc.setdefault("done", [])
    for row in doc.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        if _mrb_is_dead(doc, row, pr_exists=pr_exists, home=home):
            fin = dict(row)
            repo = str(fin.get("repo") or "").strip()
            num = str(fin.get("id") or "").strip().lstrip("#")
            merged_known = None
            if pr_merged is not None and repo and num:
                try:
                    merged_known = bool(pr_merged(repo, num))
                except Exception:
                    merged_known = None
            if merged_known is False:
                fin["result"] = "CLOSED"
                fin["merged"] = False
            else:
                fin["result"] = "MERGED"
                if merged_known is True:
                    fin["merged"] = True
            fin["done_ts"] = _utc_now()
            done.append(fin)
            if home is not None:
                stamp_mrb_done(home, str(fin.get("repo") or ""), str(fin.get("id") or ""))
                # FR #1430: ACC purge must idle the seat in digest or !bored stays nak busy.
                seat = str(
                    fin.get("nick")
                    or fin.get("accepted_by")
                    or fin.get("offered_to")
                    or ""
                ).strip()
                ident = str(fin.get("id") or "").lstrip("#")
                if seat:
                    with contextlib.suppress(Exception):
                        bobreport.clear_seat_doing(
                            home, seat, only_if_work_contains=ident or "MRB"
                        )
            continue
        kept.append(row)
    doc["accepted"] = kept
    return before - len(kept)


def _is_fix_row(row) -> bool:
    return isinstance(row, dict) and _canon_task(row) == "FIX"


def _fix_row_pr_num(row: dict) -> str:
    return _norm_row_id(str(row.get("id") or ""))


def _is_main_red_fix_row_local(row: dict) -> bool:
    """Mirror mrb_merge_on_green.is_main_red_fix_row without a hard import cycle."""
    if str(row.get("task") or "").upper() != "FIX":
        return False
    if str(row.get("main_red_fix") or "") in ("1", "true", "True"):
        return True
    if str(row.get("id") or "").strip().lstrip("#").lower() in ("main", "main-red"):
        return True
    return str(row.get("fail_signature") or "").startswith("main-red|")


def _fix_is_dead(
    row: dict,
    *,
    pr_exists=None,
    open_pulls: dict | None = None,
    fetched_repos: set | None = None,
    main_red_by_repo: dict | None = None,
    main_sha_by_repo: dict | None = None,
) -> bool:
    """True when a FIX row's pull is gone (merged/closed) or stamped closed (FR #4682).

    FR #4911: main-red FIX rows retire when main is green again or the signature
    SHA is no longer the default-branch head (never via open_pulls alone).
    """
    if not _is_fix_row(row):
        return False
    if row.get("merged") in (True, "true", "1", 1):
        return True
    if str(row.get("state") or "").strip().lower() == "closed":
        return True
    # FR #4857 / #4911: main-side FIX has no open PR number.
    if _is_main_red_fix_row_local(row):
        repo = canonical_queue_repo(str(row.get("repo") or "")) or str(
            row.get("repo") or ""
        ).strip()
        try:
            import mrb_merge_on_green as _mog

            mr = None
            if isinstance(main_red_by_repo, dict) and repo in main_red_by_repo:
                mr = bool(main_red_by_repo[repo])
            head = ""
            if isinstance(main_sha_by_repo, dict) and repo in main_sha_by_repo:
                head = str(main_sha_by_repo.get(repo) or "")
            if _mog.main_red_fix_obsolete(row, main_red=mr, main_sha=head):
                return True
        except Exception:
            pass
        return False
    repo = str(row.get("repo") or "").strip()
    ident = _fix_row_pr_num(row)
    if not repo or not ident:
        return False
    # FR #7653: match repo case the same way MRB purge does (FR #3817). A
    # merged PR left off the open-pull set must still drop the FIX row.
    fetched_keys = {_repo_key(x) for x in (fetched_repos or ())}
    repo_key = _repo_key(repo)
    if open_pulls is not None and repo_key in fetched_keys:
        open_ids: set[str] = set()
        for name, nums in open_pulls.items():
            if _repo_key(str(name)) == repo_key:
                open_ids.update(nums or ())
        return ident not in open_ids
    if pr_exists is None:
        return False
    try:
        return not bool(pr_exists(repo, ident.lstrip("#")))
    except Exception:
        return False


def _finish_dead_fix_row(
    row: dict,
    *,
    pr_merged=None,
    home: Path | None = None,
) -> dict:
    """Stamp a dead FIX into a done row and idle its seat (FR #4682 / #4911)."""
    fin = dict(row)
    repo = str(fin.get("repo") or "").strip()
    num = str(fin.get("id") or "").strip().lstrip("#")
    if _is_main_red_fix_row_local(fin):
        # FR #4911: main-side FIX retired because main is green / SHA moved.
        fin["result"] = "MAIN_GREEN"
        fin["reconcile"] = "FR4911_MAIN_GREEN"
        fin["merged"] = False
        fin["done_ts"] = _utc_now()
        fin["state"] = "closed"
        for k in (
            "nick",
            "accepted_ts",
            "accepted_by",
            "offered_to",
            "offered_ts",
            "offered_channel",
            "channel",
        ):
            fin.pop(k, None)
        if home is not None:
            seat = str(
                row.get("nick")
                or row.get("accepted_by")
                or row.get("offered_to")
                or ""
            ).strip()
            if seat:
                with contextlib.suppress(Exception):
                    bobreport.clear_seat_doing(
                        home, seat, only_if_work_contains="main"
                    )
                with contextlib.suppress(Exception):
                    clear_seat_hold(
                        home, seat, repo=repo, task="FIX", ident=str(fin.get("id") or ""),
                        clear_pins=True,
                    )
        return fin
    merged_known = None
    if pr_merged is not None and repo and num:
        try:
            merged_known = bool(pr_merged(repo, num))
        except Exception:
            merged_known = None
    if merged_known is False:
        fin["result"] = "CLOSED"
        fin["merged"] = False
    else:
        fin["result"] = "MERGED"
        if merged_known is True:
            fin["merged"] = True
    fin["done_ts"] = _utc_now()
    fin["state"] = "closed"
    if home is not None:
        seat = str(
            fin.get("nick")
            or fin.get("accepted_by")
            or fin.get("offered_to")
            or ""
        ).strip()
        if seat and num:
            with contextlib.suppress(Exception):
                bobreport.clear_seat_doing(
                    home, seat, only_if_work_contains=num
                )
    return fin


def _purge_dead_fix_unaccepted(
    doc: dict,
    *,
    pr_exists=None,
    open_pulls: dict | None = None,
    fetched_repos: set | None = None,
    main_red_by_repo: dict | None = None,
    main_sha_by_repo: dict | None = None,
) -> int:
    """Drop unaccepted FIX rows whose pull is no longer open (FR #4682 / #4911)."""
    before = len(doc.get("unaccepted") or [])
    kept: list[dict] = []
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if _fix_is_dead(
            row,
            pr_exists=pr_exists,
            open_pulls=open_pulls,
            fetched_repos=fetched_repos,
            main_red_by_repo=main_red_by_repo,
            main_sha_by_repo=main_sha_by_repo,
        ):
            continue
        kept.append(row)
    doc["unaccepted"] = kept
    return before - len(kept)


def _purge_dead_fix_accepted(
    doc: dict,
    *,
    pr_exists=None,
    pr_merged=None,
    home: Path | None = None,
    open_pulls: dict | None = None,
    fetched_repos: set | None = None,
    main_red_by_repo: dict | None = None,
    main_sha_by_repo: dict | None = None,
) -> int:
    """Move accepted FIX rows whose PR is merged/closed into done (FR #4682).

    Without this, seats stay ``doing`` on a merged FIX tip and every ``!bored``
    returns ``nak busy`` (class of a-search#3871 / flamingo-33384).
    FR #4911: also finish main-red FIX when main is green / signature SHA moved.
    """
    before = len(doc.get("accepted") or [])
    kept: list[dict] = []
    done = doc.setdefault("done", [])
    for row in doc.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        if _fix_is_dead(
            row,
            pr_exists=pr_exists,
            open_pulls=open_pulls,
            fetched_repos=fetched_repos,
            main_red_by_repo=main_red_by_repo,
            main_sha_by_repo=main_sha_by_repo,
        ):
            done.append(
                _finish_dead_fix_row(row, pr_merged=pr_merged, home=home)
            )
            continue
        kept.append(row)
    doc["accepted"] = kept
    if len(done) > DONE_CAP:
        doc["done"] = done[-DONE_CAP:]
    return before - len(kept)


def format_assign_line(nick: str, row: dict) -> str:
    """Wire line the seats and Watch-AgentHealth parse: ``<nick>: FR|MRB|UAT owner/repo#N url``."""
    num = str(row.get("id") or "").strip().lstrip("#")
    line = f"{nick}: {_canon_task(row)} {row.get('repo') or ''}#{num} {resolve_assign_url(row)}"
    try:
        import fuel_chain

        extra = fuel_chain.assign_suffix(row)
    except Exception:
        extra = ""
    if extra:
        line = f"{line} {extra}"
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", line)).strip()


def format_cancel_line(nick: str, row: dict, *, actor: str = "") -> str:
    """FR #4851 shop stop: ``<nick>: CANCEL FR owner/repo#N (closed by <user>)``."""
    num = str(row.get("id") or "").strip().lstrip("#")
    who = (actor or str(row.get("closed_by") or "")).strip()
    base = f"{nick}: CANCEL {_canon_task(row)} {row.get('repo') or ''}#{num}"
    if who:
        base = f"{base} (closed by {who})"
    else:
        base = f"{base} (closed)"
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", base)).strip()


def _seat_holder_nick(row: dict) -> str:
    """Nick holding an ACC row (nick, accepted_by, or offered_to)."""
    return str(
        row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
    ).strip()


def enqueue_seat_cancel(
    home: Path | None,
    row: dict,
    *,
    actor: str = "",
) -> bool:
    """Enqueue one shop CANCEL for a nick-held ACC row (FR #4851). Idempotent via cancel_notified."""
    if home is None or not isinstance(row, dict):
        return False
    if row.get("cancel_notified"):
        return False
    seat = _seat_holder_nick(row)
    if not seat:
        return False
    channel = str(row.get("channel") or row.get("offered_channel") or "").strip()
    if not channel:
        channel = worker_shop_channel(seat) or ""
    if not channel:
        return False
    if actor:
        row["closed_by"] = str(actor).strip()
    line = format_cancel_line(seat, row, actor=actor)
    ok = bool(bobreport.enqueue_chair_fleet_privmsg(home, line, channel))
    if ok:
        row["cancel_notified"] = True
        row["cancel_pending"] = True
        row["state"] = "closed"
    return ok


def summarize_empty_offer(home: Path, nick: str = "") -> dict:
    """Operator counts when !bored yields empty under focus (FR #1993 WP2 / FR #2309).

    Returns unaccepted / out_of_focus / require_machine / offerable estimates plus
    per-nick gate counts: self_mrb, self_uat, ledger, sticky_offered.
    ``offerable`` is rows that pass focus (when strict) and are not blocked for ``nick``
    by machine / self-MRB / self-UAT / ledger / sticky pin to another seat.
    """
    out = {
        "unaccepted": 0,
        "out_of_focus": 0,
        "require_machine": 0,
        "offerable": 0,
        "strict": False,
        "self_mrb": 0,
        "self_uat": 0,
        "ledger": 0,
        "sticky_offered": 0,
        # FR #5939: which stamp blocked the seat (aggregate across rows).
        "stamp_implementer": 0,
        "stamp_fix": 0,
        "stamp_giveup": 0,
        # FR #6211: CodeRabbit current-head hold (not opaque blocked_other).
        "coderabbit_hold": 0,
        "coderabbit_hold_row": "",
        # FR #7182: per-job skip reasons for an idle seat (focus, ledger, pin, ...).
        "skips": [],
    }
    try:
        path = queue_path(home)
        raw = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
        rows = [r for r in (raw.get("unaccepted") or []) if isinstance(r, dict)]
    except Exception:
        return out
    out["unaccepted"] = len(rows)
    open_dep_keys_summary = open_fr_issue_keys(raw if isinstance(raw, dict) else {})
    me = (canonical_worker_nick(nick) or nick or "").strip()
    live = live_seat_nicks(home) if me else set()
    free = free_seat_nicks(home, live) if me else set()
    ledger = ledger_load(home) if me else {}
    import time as _time

    now_f = _time.time()
    try:
        import focus_ignore

        strict = bool(focus_ignore.is_strict(home))
        out["strict"] = strict
        focused: set[str] = set()
        if strict:
            try:
                fdoc = focus_ignore.load_focus(home)
                focused |= {str(k) for k in (fdoc.get("repos") or {}).keys()}
                for meta in (fdoc.get("items") or {}).values():
                    if isinstance(meta, dict) and meta.get("repo"):
                        focused.add(str(meta["repo"]))
            except Exception:
                focused = set()
        offerable = 0
        out_of_focus = 0
        req_machine = 0
        self_mrb = 0
        self_uat = 0
        ledger_n = 0
        sticky_n = 0
        stamp_implementer = 0
        stamp_fix = 0
        stamp_giveup = 0
        coderabbit_hold = 0
        coderabbit_hold_row = ""
        skip_log: list[dict] = []

        def _job_key(row: dict) -> str:
            task = str(row.get("task") or "FR").strip().upper() or "FR"
            repo_s = str(row.get("repo") or "").strip()
            ident = str(row.get("id") or "").strip()
            if ident and not ident.startswith("#"):
                ident = "#" + ident
            return f"{task} {repo_s}{ident}".strip()

        def _record_empty_skip(row: dict, reason: str) -> None:
            skip_log.append({"key": _job_key(row), "reason": str(reason)})

        for r in rows:
            repo = str(r.get("repo") or "")
            if strict and focused:
                in_focus = any(
                    focus_ignore.repo_match(repo, fr) or focus_ignore.repo_match(fr, repo)
                    for fr in focused
                )
                if not in_focus:
                    out_of_focus += 1
                    _record_empty_skip(r, "focus")
                    continue
            row = dict(r)
            _stamp_require_machine(row)
            # FR #8768: gate on row_require_machine (re-infer), not only the stamp
            # field - bobiverse body pins must block wrong shops in why-empty too.
            rm = row_require_machine(row)
            if rm:
                if not me or row_blocked_for_machine(row, me):
                    req_machine += 1
                    _record_empty_skip(r, "pin")
                    continue
            to = str(row.get("offered_to") or "").strip()
            sticky_pin = False
            if to:
                try:
                    age = now_f - datetime.fromisoformat(
                        str(row.get("offered_ts") or "").replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    age = 0.0
                if age < OFFER_TIMEOUT_S:
                    sticky_n += 1
                    sticky_pin = True
            if me:
                cand = enrich_review_author_fields(
                    raw if isinstance(raw, dict) else {}, row
                )
                if is_repo_uat(cand):
                    with contextlib.suppress(Exception):
                        maybe_escalate_repo_uat_all_self_uat(
                            home, cand, live=live, ledger=ledger
                        )
                if review_blocked_for_author(cand, me, live, ledger=ledger, free=free):
                    # Repo UAT exact-author / sibling stamp counts as self_uat (FR #2939);
                    # MRB exact-author stays self_mrb.
                    if is_repo_uat(cand) or _canon_task(cand) == "UAT":
                        self_uat += 1
                        _record_empty_skip(r, "self-uat")
                    else:
                        self_mrb += 1
                        _record_empty_skip(r, "self-mrb")
                        kind = classify_mrb_author_stamp(cand, me)
                        if kind == "implementer":
                            stamp_implementer += 1
                        elif kind == "fix":
                            stamp_fix += 1
                    continue
                why = ledger_blocks(ledger, cand, me, live)
                if why:
                    if is_repo_uat(cand) and ledger_why_is_self_uat(why):
                        self_uat += 1
                        _record_empty_skip(r, "self-uat")
                    else:
                        ledger_n += 1
                        _record_empty_skip(r, "ledger")
                    continue
                if row_gave_up_by(cand, me, live=live):
                    stamp_giveup += 1
                    ledger_n += 1
                    _record_empty_skip(r, "giveup")
                    continue
                if row_needs_human(cand, me):
                    ledger_n += 1
                    _record_empty_skip(r, "needs-human")
                    continue
                skips = {
                    (canonical_worker_nick(x) or str(x)).strip().lower()
                    for x in (cand.get("sticky_skip_seats") or [])
                    if str(x).strip()
                }
                if me.lower() in skips:
                    _record_empty_skip(r, "cooldown")
                    continue
            else:
                cand = row
            # FR #6211: count CodeRabbit holds separately (stamped pending within wait;
            # no live HTTP; cleared stamps ready/failed/timeout/absent/off are not holds).
            if _canon_task(cand) == "MRB":
                try:
                    import fuel_chain

                    if fuel_chain.stage_enabled("coderabbit"):
                        st = str(cand.get("coderabbit") or "").strip().lower()
                        if st in ("", "pending"):
                            try:
                                since = float(cand.get("coderabbit_wait_since") or now_f)
                                age = float(now_f) - since
                            except (TypeError, ValueError):
                                age = 0.0
                            if age < float(fuel_chain.wait_seconds()):
                                coderabbit_hold += 1
                                if not coderabbit_hold_row:
                                    rid = str(cand.get("id") or "").strip().lstrip("#")
                                    coderabbit_hold_row = (
                                        f"{repo}#{rid}" if rid else repo
                                    )
                                _record_empty_skip(r, "coderabbit")
                                continue
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"WARN summarize_empty_offer coderabbit hold: {type(exc).__name__}",
                        flush=True,
                    )
            if sticky_pin:
                to_c = (canonical_worker_nick(to) or to).strip().lower()
                me_l = me.lower()
                if me and to_c and to_c != me_l:
                    _record_empty_skip(r, "sticky")
                    continue  # pinned to someone else
            # BOB-D3 / BOB-D5 + BOB-G1: depends-open / depends-unresolved / depends-held.
            # Local open_keys only (no live GitHub) - empty-offer honesty must stay
            # token-free. Stuck/report paths pass issue_fetch (FR #9434 / #9418).
            if _canon_task(cand) == "FR":
                dep_why = row_depends_open_reason(
                    cand, open_dep_keys_summary, doc=raw if isinstance(raw, dict) else None
                )
                if dep_why:
                    _record_empty_skip(r, dep_why)
                    continue
            offerable += 1
        out["skips"] = skip_log
        out["out_of_focus"] = out_of_focus
        out["require_machine"] = req_machine
        out["offerable"] = offerable
        out["self_mrb"] = self_mrb
        out["self_uat"] = self_uat
        out["ledger"] = ledger_n
        out["sticky_offered"] = sticky_n
        out["stamp_implementer"] = stamp_implementer
        out["stamp_fix"] = stamp_fix
        out["stamp_giveup"] = stamp_giveup
        out["coderabbit_hold"] = coderabbit_hold
        out["coderabbit_hold_row"] = coderabbit_hold_row
    except Exception:
        # Fail closed for quiet-idle nudge / empty-offer honesty (MRB #5921).
        out["offerable"] = 0
    return out



def clamp_empty_reply_stats(stats: dict | None) -> dict:
    """FR #2333: empty bored reply must never claim N>0 offerable for this seat.

    `summarize_empty_offer` can still count a row the live `offer_focus_top` path
    skipped (cooldown, awaits_mrb1, sticky_skip edge, PR checker, …). When the shop
    already returned empty for this nick, fold leftover offerable into `blocked_other`.
    """
    out = dict(stats or {})
    try:
        off = int(out.get("offerable") or 0)
    except (TypeError, ValueError):
        off = 0
    if off > 0:
        try:
            prev = int(out.get("blocked_other") or 0)
        except (TypeError, ValueError):
            prev = 0
        out["blocked_other"] = prev + off
        out["offerable"] = 0
    return out


def format_nothing_queued(nick: str, stats: dict | None = None) -> str:
    """Shop empty reply to a !bored seat: ONE short line, never a summary list.

    ``stats`` is accepted for backward compatibility and ignored: the focus/gate breakdown
    (FR #1993 WP2 / FR #2309 / FR #2333) goes to the chair log via ``format_empty_offer_detail``,
    not the channel. Simon: Jeeves MUST hand out work - empty reply stays short.
    """
    return f"{nick}: nothing queued"


# FR #2803: seats told "nothing queued" - push the next offerable row without waiting for !bored.
IDLE_AFTER_EMPTY_MAX_AGE_S = 900.0  # 15 minutes
IDLE_PUSH_MIN_INTERVAL_S = 5.0


def idle_after_empty_path(home: Path) -> Path:
    return _root(home) / "idle-after-empty.json"


def _load_idle_after_empty(home: Path) -> dict:
    path = idle_after_empty_path(home)
    if not path.exists():
        return {"v": 1, "seats": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {"v": 1, "seats": {}}
    if not isinstance(doc, dict):
        return {"v": 1, "seats": {}}
    seats = doc.get("seats")
    if not isinstance(seats, dict):
        seats = {}
    return {"v": 1, "seats": seats}


def _write_idle_after_empty(home: Path, doc: dict) -> None:
    path = idle_after_empty_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({"v": 1, "seats": doc.get("seats") or {}}, indent=0, sort_keys=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(raw + "\n", encoding="utf-8")
    tmp.replace(path)


def _idle_after_empty_ts(value) -> float | None:
    """Positive finite float from a stored idle timestamp, else ``None`` (FR #6360)."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out) or out <= 0:
        return None
    return out


def note_idle_after_empty(
    home: Path, nick: str, channel: str, *, now: float | None = None
) -> None:
    """Record that Jeeves told this seat ``nothing queued`` (FR #2803).

    FR #6360: a repeat ``!bored`` keeps the seat's original ``told_at`` (its place in the
    idle-offer line) while it stays in a continuous idle period; ``last_seen`` is refreshed
    and drives expiry. A stale prior row starts a new period.
    """
    import time as _time

    me = (canonical_worker_nick(nick) or nick or "").strip()
    if not me:
        return
    shop = bobreport.normalize_channel(channel) if channel else (worker_shop_channel(me) or "")
    if not shop:
        return
    now_f = _time.time() if now is None else float(now)
    try:
        with _lock(home):
            doc = _load_idle_after_empty(home)
            seats = doc.setdefault("seats", {})
            prev = seats.get(me) if isinstance(seats.get(me), dict) else {}
            prev_told = _idle_after_empty_ts(prev.get("told_at"))
            prev_seen = _idle_after_empty_ts(prev.get("last_seen"))
            ref = prev_seen if prev_seen is not None else prev_told
            if (
                prev_told is not None
                and ref is not None
                and (now_f - ref) <= IDLE_AFTER_EMPTY_MAX_AGE_S
            ):
                told_at = prev_told
            else:
                told_at = float(now_f)
            seats[me] = {
                "nick": me,
                "channel": shop,
                "told_at": told_at,
                "last_seen": float(now_f),
                "last_push_at": _idle_after_empty_ts(prev.get("last_push_at")) or 0.0,
            }
            _write_idle_after_empty(home, doc)
    except (TimeoutError, OSError):
        return


def clear_idle_after_empty(home: Path, nick: str) -> None:
    """Drop an idle-after-empty entry (offered / ACK / leave / busy)."""
    me = (canonical_worker_nick(nick) or nick or "").strip()
    if not me:
        return
    me_l = me.lower()
    try:
        with _lock(home):
            doc = _load_idle_after_empty(home)
            seats = doc.get("seats") or {}
            drop = [
                k
                for k in list(seats.keys())
                if (canonical_worker_nick(k) or k).strip().lower() == me_l
            ]
            if not drop:
                return
            for k in drop:
                seats.pop(k, None)
            _write_idle_after_empty(home, doc)
    except (TimeoutError, OSError):
        return


def list_idle_after_empty(
    home: Path, *, now: float | None = None, live: set[str] | None = None
) -> list[dict]:
    """Idle seats oldest-first; prune expired and seats missing from the digest."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    live_set = set(live) if live is not None else live_seat_nicks(home)
    live_l = {
        (canonical_worker_nick(x) or x).strip().lower() for x in live_set if str(x).strip()
    }
    try:
        with _lock(home):
            doc = _load_idle_after_empty(home)
            seats = doc.get("seats") or {}
            keep: dict = {}
            rows: list[dict] = []
            for key, ent in list(seats.items()):
                if not isinstance(ent, dict):
                    continue
                nick = str(ent.get("nick") or key or "").strip()
                nick_c = (canonical_worker_nick(nick) or nick).strip()
                if not nick_c:
                    continue
                try:
                    told = float(ent.get("told_at") or 0.0)
                except (TypeError, ValueError):
                    told = 0.0
                # FR #6360: expire on the latest "nothing queued" (``last_seen``); legacy
                # rows without it fall back to ``told_at``.
                last_seen = _idle_after_empty_ts(ent.get("last_seen"))
                if last_seen is None:
                    last_seen = told
                if told <= 0 or (now_f - last_seen) > IDLE_AFTER_EMPTY_MAX_AGE_S:
                    continue
                # If digest has any live seats, drop entries that are gone.
                if live_l and nick_c.lower() not in live_l:
                    continue
                chan = bobreport.normalize_channel(str(ent.get("channel") or "")) or (
                    worker_shop_channel(nick_c) or ""
                )
                if not chan:
                    continue
                try:
                    last_push = float(ent.get("last_push_at") or 0.0)
                except (TypeError, ValueError):
                    last_push = 0.0
                row = {
                    "nick": nick_c,
                    "channel": chan,
                    "told_at": told,
                    "last_seen": last_seen,
                    "last_push_at": last_push,
                }
                keep[nick_c] = row
                rows.append(row)
            if keep != seats:
                doc["seats"] = keep
                _write_idle_after_empty(home, doc)
    except (TimeoutError, OSError):
        return []
    rows.sort(key=lambda r: (float(r.get("told_at") or 0.0), str(r.get("nick") or "")))
    return rows


def sort_idle_seats_cheapest_first(
    idle_rows: list,
    fields_by_nick: dict | None = None,
    *,
    home: Path | None = None,
) -> list:
    """FR #7084 / MRB #7089: prefer min cost_tier among idle seats (stable nick tie-break)."""
    rows = list(idle_rows or [])
    cache = dict(fields_by_nick or {})

    def _key(ent: dict) -> tuple:
        nick = str((ent or {}).get("nick") or "").strip()
        fields = cache.get(nick)
        if fields is None and home is not None:
            try:
                fields = _seat_digest_model_fields(home, nick)
            except Exception:
                fields = {}
            cache[nick] = fields or {}
        fields = fields or {}
        try:
            import worker_start_model as wsm

            rank = wsm._tier_rank(str(fields.get("cost_tier") or wsm.DEFAULT_JOB_TIER))
        except Exception:
            rank = 0
        try:
            told = float((ent or {}).get("told_at") or 0.0)
        except (TypeError, ValueError):
            told = 0.0
        return (rank, told, nick.lower())

    rows.sort(key=_key)
    return rows


def prefer_cross_machine_mrb_reviewers(
    idle_rows: list,
    *,
    home: Path | None = None,
    unaccepted: list | None = None,
) -> list:
    """FR #9478: among same cost order, prefer idle seats cross-machine to MRB authors.

    When the unaccepted MRB backlog is mostly authored on machine A and idle
    includes machine B, offer B first so flamingo-authored MRBs reach redqueen
    before same-machine siblings (until soft free= policy allows siblings).
    """
    rows = list(idle_rows or [])
    if len(rows) < 2:
        return rows
    author_mids: set[str] = set()
    try:
        rows_q = unaccepted
        if rows_q is None and home is not None:
            rows_q = load_unaccepted(home)
        for row in rows_q or []:
            if not isinstance(row, dict):
                continue
            if _canon_task(row) != "MRB":
                continue
            for a in row_author_seats(row):
                p = bobreport.parse_seat_nick(a)
                if p:
                    author_mids.add(bobreport.fold_machine_id(p[0]))
    except Exception:
        author_mids = set()
    if not author_mids:
        return rows
    # Stable partition: keep cheapest-first order inside each group.
    cross: list = []
    same: list = []
    for ent in rows:
        nick = str((ent or {}).get("nick") or "").strip()
        p = bobreport.parse_seat_nick(nick) if nick else None
        mid = bobreport.fold_machine_id(p[0]) if p else ""
        if mid and mid in author_mids:
            same.append(ent)
        else:
            cross.append(ent)
    return cross + same if cross else rows

def digest_idle_ready_seats(
    home: Path, *, now: float | None = None, live: set[str] | None = None
) -> list[dict]:
    """Digest ``worker_list`` idle/ready seats with a shop channel (FR #7182).

    Complements ``list_idle_after_empty``: a seat that posted ``worker ready`` / is
    idle on the digest must be offerable even if Jeeves never said ``nothing queued``.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    live_set = set(live) if live is not None else live_seat_nicks(home, now=now_f)
    live_l = {
        (canonical_worker_nick(x) or x).strip().lower() for x in live_set if str(x).strip()
    }
    out: list[dict] = []
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return out
    for _mid, ent in (doc.get("machines") or {}).items():
        if not isinstance(ent, dict):
            continue
        for row in bobreport._coerce_worker_list(ent.get("worker_list")):
            nick = str(row.get("nick") or "").strip()
            nick_c = (canonical_worker_nick(nick) or nick).strip()
            if not nick_c or nick_c.lower() not in live_l:
                continue
            state = str(row.get("state") or "idle").strip().lower()
            if state not in ("idle", "ready", ""):
                continue
            if worker_working_on(home, nick_c):
                continue
            chan = worker_shop_channel(nick_c) or ""
            if not chan:
                continue
            out.append(
                {
                    "nick": nick_c,
                    "channel": chan,
                    "told_at": now_f,
                    "last_push_at": 0.0,
                    "via": "digest-idle",
                }
            )
    return out


def offer_to_idle_seats(
    home: Path,
    *,
    say,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
    live: set[str] | None = None,
    log=None,
) -> int:
    """Push ``offer_focus_top`` to tracked idle seats (oldest first). No empty chatter (FR #2803).

    ``say(channel, text)`` delivers the assign line (IRC or chair-outbox). Returns offers sent.
    FR #2899: optional ``log(msg)`` records every successful offer (parity with bored offered).
    FR #7182: also offer to digest-idle ready seats (not only nothing-queued).
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    # Idle digest + a leftover accepted row is a stall. Release it before the
    # free-seat filter, which treats any accepted nick as busy.
    for idle_nick in digest_idle_ready_seats(home, now=now_f, live=live):
        nick_i = str(idle_nick.get("nick") or "").strip()
        if nick_i:
            with contextlib.suppress(Exception):
                release_stale_busy(home, nick_i, now_f, log=log)
    idle_rows = list_idle_after_empty(home, now=now_f, live=live)
    seen = {
        str(ent.get("nick") or "").strip().lower()
        for ent in idle_rows
        if str(ent.get("nick") or "").strip()
    }
    for extra in digest_idle_ready_seats(home, now=now_f, live=live):
        nick_l = str(extra.get("nick") or "").strip().lower()
        if nick_l and nick_l not in seen:
            idle_rows.append(extra)
            seen.add(nick_l)
    if not idle_rows:
        return 0
    try:
        idle_rows = sort_idle_seats_cheapest_first(idle_rows, home=home)
    except Exception:
        pass
    # FR #9478: among cheapest peers, prefer cross-machine reviewers for MRB backlog.
    try:
        idle_rows = prefer_cross_machine_mrb_reviewers(idle_rows, home=home)
    except Exception:
        pass
    # FR #8428: after an offer-timeout, try a different live idle seat before
    # the nick that just went silent.
    timeout_nicks: set[str] = set()
    try:
        for queued in load_unaccepted(home):
            last = str(queued.get("offer_last_timeout_seat") or "").strip().lower()
            if last:
                timeout_nicks.add(last)
    except Exception:
        timeout_nicks = set()
    if timeout_nicks:
        others = []
        same = []
        for ent in idle_rows:
            nick_l = str(ent.get("nick") or "").strip().lower()
            if nick_l in timeout_nicks:
                same.append(ent)
            else:
                others.append(ent)
        if others:
            idle_rows = others + same
    sent = 0
    for ent in idle_rows:
        nick = str(ent.get("nick") or "").strip()
        channel = str(ent.get("channel") or "").strip()
        if not nick or not channel:
            continue
        try:
            last_push = float(ent.get("last_push_at") or 0.0)
        except (TypeError, ValueError):
            last_push = 0.0
        if last_push and (now_f - last_push) < IDLE_PUSH_MIN_INTERVAL_S:
            continue
        # Busy / wrong-shop seats: do not push; clear if genuinely busy.
        if worker_working_on(home, nick):
            clear_idle_after_empty(home, nick)
            continue
        gate = bored_gate(home, nick, channel, now_f)
        if gate == "busy":
            clear_idle_after_empty(home, nick)
            continue
        if gate == "ignore":
            clear_idle_after_empty(home, nick)
            continue
        # gate == wait: recent activity throttle - skip this tick, keep idle entry.
        if gate == "wait":
            continue
        status, job = offer_focus_top(
            home,
            nick,
            channel,
            now=now_f,
            pr_exists=pr_exists,
            is_pull=is_pull,
            issue_open=issue_open,
        )
        if status == "ok" and isinstance(job, dict):
            line = format_assign_line(nick, job)
            delivered = False
            try:
                ret = say(channel, line)
                # Chair-outbox enqueue returns False on OSError/secret skip; treat as fail.
                delivered = ret is not False
            except Exception:
                delivered = False
            if not delivered:
                # Keep idle entry; stamp rate limit so we retry after IDLE_PUSH_MIN_INTERVAL_S.
                # FR #2819 / #4089 / #6521: also unwind offered_to (and seat hold) so the
                # failed chair-outbox enqueue does not leave bored_gate busy under FR #3192
                # and clear_idle_after_empty on the next push tick.
                with contextlib.suppress(Exception):
                    clear_seat_offer(home, nick, job)
                with contextlib.suppress(Exception):
                    clear_seat_hold(
                        home,
                        nick,
                        repo=str(job.get("repo") or ""),
                        task=str(job.get("task") or ""),
                        ident=str(job.get("id") or ""),
                    )
                try:
                    with _lock(home):
                        doc = _load_idle_after_empty(home)
                        seats = doc.get("seats") or {}
                        cur = seats.get(nick) if isinstance(seats.get(nick), dict) else None
                        if cur is None:
                            for k, v in list(seats.items()):
                                if (canonical_worker_nick(k) or k).strip().lower() == nick.lower():
                                    cur = v if isinstance(v, dict) else None
                                    nick = k
                                    break
                        if isinstance(cur, dict):
                            cur["last_push_at"] = now_f
                            seats[nick] = cur
                            _write_idle_after_empty(home, doc)
                except (TimeoutError, OSError):
                    pass
                continue
            clear_idle_after_empty(home, nick)
            if callable(log):
                with contextlib.suppress(Exception):
                    log(f"INFO git-claim idle offered {line} nick={nick}")
            sent += 1
            continue
        # Nothing offerable for this seat: stay idle, stamp rate limit, no channel chatter.
        try:
            with _lock(home):
                doc = _load_idle_after_empty(home)
                seats = doc.get("seats") or {}
                cur = seats.get(nick) if isinstance(seats.get(nick), dict) else None
                if cur is None:
                    for k, v in list(seats.items()):
                        if (canonical_worker_nick(k) or k).strip().lower() == nick.lower():
                            cur = v if isinstance(v, dict) else None
                            nick = k
                            break
                if isinstance(cur, dict):
                    cur["last_push_at"] = now_f
                    seats[nick] = cur
                    _write_idle_after_empty(home, doc)
        except (TimeoutError, OSError):
            pass
    return sent


def push_idle_offers_via_chair_outbox(
    home: Path,
    *,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
    log=None,
) -> int:
    """Enqueue shop assign PRIVMSGs on chair-outbox for idle seats (webhook / enqueue path).

    FR #2899 / MRB #2900: when ``log`` is omitted, default to stdout ``INFO git-claim idle
    offered …`` so enqueue/webhook idle pushes match bored-offer logging without each
    caller wiring a callback.
    """

    def _say(channel: str, text: str) -> bool:
        return bool(bobreport.enqueue_chair_fleet_privmsg(home, text, channel))

    def _default_log(msg: str) -> None:
        print(str(msg), flush=True)

    return offer_to_idle_seats(
        home,
        say=_say,
        now=now,
        pr_exists=pr_exists,
        is_pull=is_pull,
        issue_open=issue_open,
        log=_default_log if log is None else log,
    )


def offer_after_release(
    home: Path,
    nick: str,
    channel: str,
    *,
    say,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
    offered_via: str = "giveup",
) -> tuple[int, dict | None]:
    """FR #2811 / FR #3893: after GIVEUP/NACK/DONE, push the next eligible job (no empty chatter).

    Uses the same ``offer_focus_top`` gates as ``!bored``. Returns ``(1, job)`` if delivered.
    ``offered_via`` stamps sticky window (``giveup`` / ``done`` / ``nack``).
    FR #8051: done-offer never delivers an MRB this seat implemented (belt-and-suspenders
    after enrich); clear the pin and return empty instead of a self-MRB assign.
    """
    via = str(offered_via or "giveup").strip().lower() or "giveup"
    # FR #4181: out-of-fuel seats stay quiet (no giveup/done push) until !bored clears.
    if seat_is_out_of_fuel(home, nick, now):
        return 0, None
    if seat_fuel_pause_reason(home, nick, now):
        return 0, None
    # FR #4089: never push to a seat that still has an open job (accepted / offered / held).
    if seat_open_job(home, nick, now):
        return 0, None
    status, job = offer_focus_top(
        home,
        nick,
        channel,
        now=now,
        pr_exists=pr_exists,
        is_pull=is_pull,
        issue_open=issue_open,
        offered_via=via,
    )
    if status != "ok" or not isinstance(job, dict):
        return 0, None
    # FR #8051: never done-offer an MRB to its implementer (stamp race / missing author).
    if via == "done" and _canon_task(job) == "MRB":
        try:
            doc = load_queue(home)
            live = live_seat_nicks(home, now=now)
            free = free_seat_nicks(home, live, doc=doc)
            cand = enrich_review_author_fields(doc, job)
            if review_blocked_for_author(cand, nick, live, ledger=ledger_load(home), free=free):
                with contextlib.suppress(Exception):
                    clear_seat_offer(home, nick, job)
                with contextlib.suppress(Exception):
                    clear_seat_hold(
                        home,
                        nick,
                        repo=str(job.get("repo") or ""),
                        task=str(job.get("task") or ""),
                        ident=str(job.get("id") or ""),
                    )
                return 0, None
        except Exception:
            pass
    line = format_assign_line(nick, job)
    delivered = False
    try:
        ret = say(channel, line)
        delivered = ret is not False
    except Exception:
        delivered = False
    if not delivered:
        # FR #4089: undelivered push must not leave the seat blocked by its own pin/hold.
        with contextlib.suppress(Exception):
            clear_seat_offer(home, nick, job)
        with contextlib.suppress(Exception):
            clear_seat_hold(
                home, nick, repo=str(job.get("repo") or ""), task=str(job.get("task") or ""),
                ident=str(job.get("id") or ""),
            )
        return 0, None
    with contextlib.suppress(Exception):
        clear_idle_after_empty(home, nick)
    return 1, job


def offer_after_giveup(
    home: Path,
    nick: str,
    channel: str,
    *,
    say,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
) -> tuple[int, dict | None]:
    """FR #2811: after GIVEUP/NACK, push the next eligible job to that seat (no empty chatter)."""
    return offer_after_release(
        home,
        nick,
        channel,
        say=say,
        now=now,
        pr_exists=pr_exists,
        is_pull=is_pull,
        issue_open=issue_open,
        offered_via="giveup",
    )


def offer_after_done(
    home: Path,
    nick: str,
    channel: str,
    *,
    say,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
) -> tuple[int, dict | None]:
    """FR #3893: after DONE, push the next eligible job to that seat (no empty chatter)."""
    return offer_after_release(
        home,
        nick,
        channel,
        say=say,
        now=now,
        pr_exists=pr_exists,
        is_pull=is_pull,
        issue_open=issue_open,
        offered_via="done",
    )


def format_empty_offer_detail(nick: str, stats: dict | None = None) -> str:
    """Operator/log line for an empty offer: focus + per-nick gate breakdown (FR #1993 WP2 / #2309 / #2333)."""
    if not stats:
        return f"{nick}: nothing queued"
    try:
        unaccepted = int(stats.get("unaccepted") or 0)
        out_of_focus = int(stats.get("out_of_focus") or 0)
        req = int(stats.get("require_machine") or 0)
        offerable = int(stats.get("offerable") or 0)
        self_mrb = int(stats.get("self_mrb") or 0)
        self_uat = int(stats.get("self_uat") or 0)
        ledger = int(stats.get("ledger") or 0)
        sticky = int(stats.get("sticky_offered") or 0)
        blocked_other = int(stats.get("blocked_other") or 0)
        stamp_implementer = int(stats.get("stamp_implementer") or 0)
        stamp_fix = int(stats.get("stamp_fix") or 0)
        stamp_giveup = int(stats.get("stamp_giveup") or 0)
        coderabbit_hold = int(stats.get("coderabbit_hold") or 0)
        coderabbit_hold_row = str(stats.get("coderabbit_hold_row") or "").strip()
    except (TypeError, ValueError):
        return f"{nick}: nothing queued"
    if unaccepted <= 0:
        return f"{nick}: nothing queued"
    extra = []
    if self_mrb:
        stamp_bits = []
        if stamp_implementer:
            stamp_bits.append(f"implementer={stamp_implementer}")
        if stamp_fix:
            stamp_bits.append(f"fix={stamp_fix}")
        if stamp_bits:
            extra.append(f"self_mrb={self_mrb} ({', '.join(stamp_bits)})")
        else:
            extra.append(f"self_mrb={self_mrb}")
    if self_uat:
        extra.append(f"self_uat={self_uat}")
    if stamp_giveup:
        extra.append(f"giveup={stamp_giveup}")
    if ledger:
        extra.append(f"ledger={ledger}")
    if sticky:
        extra.append(f"sticky={sticky}")
    if coderabbit_hold:
        # FR #6211: concrete hold, not opaque blocked_other.
        if coderabbit_hold_row:
            extra.append(f"coderabbit_hold={coderabbit_hold} row={coderabbit_hold_row}")
        else:
            extra.append(f"coderabbit_hold={coderabbit_hold}")
    if blocked_other:
        extra.append(f"blocked_other={blocked_other}")
    skip_bits = []
    for item in (stats.get("skips") or [])[:8]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if key and reason:
            skip_bits.append(f"{key}:{reason}")
    if skip_bits:
        extra.append("skips=" + ";".join(skip_bits))
    base = (
        f"{nick}: {offerable} offerable for you under focus "
        f"({unaccepted} unaccepted, {out_of_focus} out-of-focus, "
        f"{req} require_machine"
    )
    if extra:
        return base + ", " + ", ".join(extra) + ")"
    return base + ")"


# FR #4211: legacy pid-keyed ``workers`` without a fresh heartbeat are ghosts.
LIVE_LEGACY_WORKER_STALE_S = 900.0


def _local_digest_machine_ids() -> set[str]:
    """Folded machine ids for this host (BOB_MACHINE_ID / COMPUTERNAME)."""
    raw = (
        os.environ.get("BOB_MACHINE_ID")
        or os.environ.get("COMPUTERNAME")
        or os.environ.get("HOSTNAME")
        or ""
    ).strip()
    if not raw:
        return set()
    mid = bobreport.fold_machine_id(bobreport.normalize_machine_id(raw) or raw)
    if not mid:
        return set()
    out = {mid}
    # Alias fold: win-mpre8vi4u6u <-> ionos style.
    for alias, canon in getattr(bobreport, "DIGEST_ID_FOLD", {}).items():
        if bobreport.fold_machine_id(canon) == mid or bobreport.fold_machine_id(alias) == mid:
            out.add(bobreport.fold_machine_id(alias))
            out.add(bobreport.fold_machine_id(canon))
    return {x for x in out if x}


def _legacy_worker_live_nick(
    mid: str,
    pid_s: str,
    w: dict,
    *,
    now: float,
    local_ids: set[str],
) -> str | None:
    """Return canonical seat nick when a legacy ``workers`` entry counts as live (FR #4211).

    Local machine: require the OS pid to be alive.
    Remote / unknown: require a heartbeat ``updated`` within ``LIVE_LEGACY_WORKER_STALE_S``.
    Missing heartbeat on a non-local machine is treated as a ghost.
    """
    mid_f = bobreport.fold_machine_id(mid)
    nick_raw = str(w.get("nick") or "").strip()
    nick = canonical_worker_nick(nick_raw) if nick_raw else None
    if not nick:
        try:
            nick = f"{mid_f}-{int(pid_s)}"
        except ValueError:
            return None
    nick = canonical_worker_nick(nick) or nick

    is_local = bool(local_ids) and mid_f in local_ids
    if is_local:
        try:
            pid_i = int(pid_s)
        except ValueError:
            return None
        try:
            if not bobreport._pid_alive(pid_i):
                return None
        except Exception:
            return None
        return nick

    updated = (
        w.get("updated")
        or w.get("last_seen")
        or w.get("lastSeen")
        or w.get("seen_at")
        or ""
    )
    ts = bobreport._parse_worker_updated_ts(updated)
    if ts is None:
        return None
    if (float(now) - float(ts)) > float(LIVE_LEGACY_WORKER_STALE_S):
        return None
    return nick


def live_seat_nicks(home: Path, *, now: float | None = None) -> set[str]:
    """Seat nicks present in the digest for MRB/UAT author rules (FR #1401 / #4211).

    Prefer canonical ``worker_list`` (tray / shop feed). Legacy pid-keyed
    ``workers`` often keeps ghost seats that never ``!bored``; counting them as
    live used to strand repo-UAT eligibility math (FR #1401) and UAT sibling
    gates (FR #4211). Fall back to ``workers`` only when ``worker_list`` is empty,
    and then only for entries that are locally alive or freshly heartbeated.
    Tests must not rely on COMPUTERNAME/BOB_MACHINE_ID or live OS pids (FR #7098
    SYSTEM ircBob): fixture ``worker_list`` plus a heartbeat ``updated``.

    FR #9310: skip machines with ``workers_stale`` (FR #8513 last-good restore).
    Restored ghosts must not receive auto-offers after the live list emptied
    (offer-to-ghost class: marchhare-8112 while ``workers=[]``).
    """
    import time as _time

    out: set[str] = set()
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return out
    now_f = float(_time.time() if now is None else now)
    local_ids = _local_digest_machine_ids()
    for mid, ent in (doc.get("machines") or {}).items():
        if not isinstance(ent, dict):
            continue
        # FR #9310: last-good paint / restore is TipForm-only - not offerable.
        if ent.get("workers_stale"):
            continue
        rows = bobreport._coerce_worker_list(ent.get("worker_list"))
        if rows:
            for r in rows:
                nick = str(r.get("nick") or "").strip()
                if not nick:
                    continue
                out.add(canonical_worker_nick(nick) or nick)
            continue
        workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
        for pid, w in workers.items():
            if not str(pid).isdigit():
                continue
            if not isinstance(w, dict):
                w = {}
            nick = _legacy_worker_live_nick(
                str(mid), str(pid), w, now=now_f, local_ids=local_ids
            )
            if nick:
                out.add(nick)
    return out



def free_seat_nicks(
    home: Path, live: set[str] | None = None, *, doc: dict | None = None
) -> set[str]:
    """FR #2487: live seats that are idle/free (no digest working_on; not in accepted).

    FR #9534: pass ``doc`` when the caller already holds ``_lock`` so we never
    re-enter ``load_queue`` (disk ``git-claim.lock`` is non-reentrant; nested wait
    spins until timeout and hung tip ``build-jeeves`` under pytest-timeout).
    """
    seats = set(live) if live is not None else live_seat_nicks(home)
    busy: set[str] = set()
    try:
        q = doc if doc is not None else load_queue(home)
        for r in q.get("accepted") or []:
            n = canonical_worker_nick(str(r.get("nick") or "")) or str(r.get("nick") or "").strip()
            if n:
                busy.add(n.lower())
    except Exception:
        pass
    out: set[str] = set()
    for n in seats:
        n_c = canonical_worker_nick(n) or (n or "").strip()
        if not n_c:
            continue
        if n_c.lower() in busy:
            continue
        if worker_working_on(home, n_c):
            continue
        out.add(n_c)
    return out


def _reserved_heal_seat_nick(raw: str) -> str:
    """FR #9489: operator interim author heal nicks that must stick through enrich.

    Prefer ``<roster-machine>-<dead-pid>`` (e.g. ``marchhare-99999``) on fleets
    whose Jeeves still requires ``parse_seat_nick``. ``ghost-<n>`` (n>=1) is the
    reserved non-roster heal nick for tip builds with structural canon.
    """
    n = (raw or "").strip().lower()
    if n == "copilot":
        return "copilot"
    m = re.match(r"^ghost-(\d+)$", n)
    if m and int(m.group(1)) > 0:
        return n
    return ""


def _canon_seat_nick(raw: str) -> str:
    v = str(raw or "").strip()
    if not v:
        return ""
    # FR #5170 / #9489: Copilot + reserved ghost-N heal nicks (not machine-pid).
    reserved = _reserved_heal_seat_nick(v)
    if reserved:
        return reserved
    # FR #8095 / MRB #1278: use canonical_worker_nick structural fallback so a
    # stamped ``<machine>-<pid>`` still counts when seat_machine_ids is cold.
    cw = canonical_worker_nick(v) or ""
    # FR #9489: do not treat ghost-0 / non-reserved ghost-* as a sticky heal.
    if cw.lower().startswith("ghost-"):
        return _reserved_heal_seat_nick(cw)
    return cw


def row_author_seats(row: dict) -> list[str]:
    """All seat nicks that must not self-review / self-UAT this row (FR #227 / #265).

    Collects ``implementer_seat``, ``mrb_author_seat``, legacy ``author_seat`` /
    ``author_nick`` / ``author``, and optional ``author_seats`` (comma list).
    """
    found: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        nick = _canon_seat_nick(raw)
        if not nick:
            return
        key = nick.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(nick)

    for k in ("implementer_seat", "mrb_author_seat", "mrb_fix_author_seat", "author_seat", "author_nick", "author"):
        _add(str(row.get(k) or ""))
    multi = row.get("author_seats")
    if isinstance(multi, (list, tuple)):
        for item in multi:
            _add(str(item or ""))
    elif multi:
        for part in str(multi).replace(";", ",").split(","):
            _add(part)
    return found


def fix_ci_seats_from_doc(doc: dict, repo: str, pr_id: str) -> list[str]:
    """Seats that accepted or DONE a FIX for ``repo#pr`` (FR #4604 / FR #5923).

    Used so a FIX seat that pushed CI fixes cannot be offered the re-queued MRB.

    FR #5923: do not treat a DONE/accepted FR that only cites ``/pull/N``
    (result/url) as authorship. Cite-only FR seats stay eligible to MRB; only
    real commit authors / implementer stamps and FIX seats are blocked.
    """
    want = _norm_row_id(pr_id)
    if not want or not repo:
        return []
    pull_num = str(want).lstrip("#")
    pull_needle = f"/pull/{pull_num}"
    found: list[str] = []
    seen: set[str] = set()
    for bucket in ("accepted", "done"):
        for row in doc.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            task = str(row.get("task") or "").upper()
            if task != "FIX":
                continue
            url = str(row.get("url") or row.get("result") or "")
            same_id = (
                str(row.get("repo") or "") == repo
                and _norm_row_id(row.get("id")) == want
            )
            same_pull = False
            if pull_needle in url:
                parsed = parse_github_pull_url(url)
                if parsed and parsed[0] == repo and _norm_row_id(parsed[1]) == want:
                    same_pull = True
                elif repo.lower() in url.lower():
                    same_pull = True
            if not (same_id or same_pull):
                continue
            seat = str(
                row.get("nick") or row.get("done_by") or row.get("author_seat") or ""
            ).strip()
            if not seat or not bobreport.parse_seat_nick(seat):
                continue
            nick = _canon_seat_nick(seat) or seat
            key = nick.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(nick)
    return found


def append_author_seat(row: dict, seat: str) -> bool:
    """Append ``seat`` to ``author_seats`` on ``row``. Returns True when changed."""
    nick = _canon_seat_nick(seat)
    if not nick:
        return False
    existing = row_author_seats(row)
    if any(x.lower() == nick.lower() for x in existing):
        return False
    multi = row.get("author_seats")
    parts: list[str] = []
    if isinstance(multi, (list, tuple)):
        parts = [str(x).strip() for x in multi if str(x or "").strip()]
    elif multi:
        parts = [p.strip() for p in str(multi).replace(";", ",").split(",") if p.strip()]
    parts.append(nick)
    row["author_seats"] = ",".join(parts)
    return True


def stamp_fix_seats_on_mrb_rows(doc: dict, repo: str, pr_id: str, seat: str) -> int:
    """Append FIX seat to ``author_seats`` on every MRB row for ``repo#pr`` (FR #4604)."""
    nick = _canon_seat_nick(seat)
    if not nick or not repo:
        return 0
    want = _norm_row_id(pr_id)
    n = 0
    for bucket in ("unaccepted", "accepted", "done"):
        for row in doc.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "MRB":
                continue
            if str(row.get("repo") or "") != repo:
                continue
            if _norm_row_id(row.get("id")) != want:
                continue
            if append_author_seat(row, nick):
                n += 1
    return n


def classify_mrb_author_stamp(row: dict, nick: str) -> str:
    """FR #5939: which author stamp blocks ``nick`` on this MRB ("" / implementer / fix).

    ``implementer`` = single-value implementer/author stamps.
    ``fix`` = ``mrb_fix_author_seat`` or multi ``author_seats`` (FIX enrich only after scrub).
    """
    if _canon_task(row) != "MRB":
        return ""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return ""
    for k in ("implementer_seat", "mrb_author_seat", "author_seat", "author_nick", "author"):
        raw = _canon_seat_nick(str(row.get(k) or ""))
        if raw and raw.lower() == me:
            return "implementer"
    fix_raw = _canon_seat_nick(str(row.get("mrb_fix_author_seat") or ""))
    if fix_raw and fix_raw.lower() == me:
        return "fix"
    for seat in row_author_seats(row):
        if seat.lower() == me:
            # Multi author_seats / leftover when single stamps missed -> FIX enrich path.
            return "fix"
    return ""


def implementer_seat_from_done_fr_pull(
    doc: dict,
    repo: str,
    pr_id: str,
    *,
    refs=None,
) -> str:
    """FR #8051 / #3277: DONE FR whose result URL is this pull → implementer seat.

    Recovers author exclusion when ``author_seat`` was stripped or never stamped
    (webhook race before DONE FR supersede). Cite-only noise is filtered the same
    way as ``mrb_author_extra_from_doc`` / ``fr_implementer_seat_from_doc``.
    """
    want = _norm_row_id(pr_id)
    if not want or not repo:
        return ""
    pull_num = str(want).lstrip("#")
    # FR #8051 review: `/pull/8044` is a prefix of `/pull/80440`. Require a
    # parsed pull id, or a path boundary when the URL does not parse.
    boundary = re.compile(r"/pull/" + re.escape(pull_num) + r"(?:/|\b|$)")
    for row in doc.get("done") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("task") or "").upper() != "FR":
            continue
        url = str(row.get("url") or row.get("result") or "")
        parsed = parse_github_pull_url(url)
        if parsed:
            if not (
                _repo_key(parsed[0]) == _repo_key(repo)
                and _norm_row_id(parsed[1]) == want
            ):
                continue
        else:
            if repo.lower() not in url.lower() or not boundary.search(url):
                continue
        seat = str(row.get("nick") or row.get("done_by") or "").strip()
        if seat and bobreport.parse_seat_nick(seat):
            return canonical_worker_nick(seat) or seat
    return fr_implementer_seat_from_doc(doc, repo, refs or (), pr_id=want)


def enrich_mrb_author_fields(doc: dict, row: dict) -> dict:
    """FR #4604 / #5923 / #5939 / #8051 / #9489: merge FIX seats; recover implementer; drop stale author_seats.

    Survives missing stamps on synchronize-enqueued MRB rows by reading queue truth.
    Cite-only FR DONE results are ignored (FR #5923).
    FR #5939: orphan ``author_seats`` entries (false self-mrb give-ups, pre-#5925
    cite-only) are dropped; verified roles are single-value stamps + FIX from doc.
    FR #8051: when ``author_seat`` / ``implementer_seat`` are missing, backfill from
    a DONE FR whose result is this pull so done-offer cannot self-MRB.
    FR #8095: harvest-lesson tips also recover the filing seat from the body footer.
    FR #9489: operator interim heal stamps (``ghost-N`` or ``<roster>-<dead-pid>``)
    stay sticky --- do not overwrite with the recovered DONE-FR implementer.
    """
    if _canon_task(row) != "MRB":
        return row
    out = dict(row)
    # Drop stale multi author_seats; rebuild from FIX queue truth only.
    out.pop("author_seats", None)
    raw_impl = str(
        out.get("implementer_seat") or out.get("author_seat") or out.get("author_nick") or ""
    ).strip()
    canon_impl = _canon_seat_nick(raw_impl)
    # FR #9489: reserved heal nick sticks even when parse_seat_nick is None.
    if not canon_impl:
        canon_impl = _reserved_heal_seat_nick(raw_impl)
        if canon_impl:
            out["author_seat"] = canon_impl
            out["implementer_seat"] = canon_impl
    has_impl = bool(canon_impl)
    if not has_impl:
        impl = implementer_seat_from_done_fr_pull(
            doc,
            str(out.get("repo") or ""),
            str(out.get("id") or ""),
            refs=out.get("refs"),
        )
        if not impl and is_harvest_lesson_pr(
            title=str(out.get("title") or ""),
            labels=out.get("labels") or (),
        ):
            # FR #8095: recover filing seat from tip body when enqueue missed the stamp.
            impl = lesson_pr_opener_seat(str(out.get("body") or ""))
        if impl:
            out["author_seat"] = impl
            out["implementer_seat"] = impl
    for seat in fix_ci_seats_from_doc(doc, str(out.get("repo") or ""), str(out.get("id") or "")):
        append_author_seat(out, seat)
    return out


def enrich_review_author_fields(doc: dict, row: dict) -> dict:
    """Offer-time author enrichment for MRB (FIX seats) and UAT (related MRB)."""
    task = _canon_task(row)
    if task == "UAT":
        return enrich_uat_author_fields(doc, row)
    if task == "MRB":
        return enrich_mrb_author_fields(doc, row)
    return row


def nick_is_row_author(row: dict, nick: str, *, live: set[str] | None = None) -> bool:
    """True when ``nick`` matches any of ``row_author_seats`` (canonical seat form).

    FR #4336 / #4604: when ``live`` is provided, also matches a same-machine recycle
    of a dead author seat via ``nick_inherits_dead_seat``.
    """
    authors = row_author_seats(row)
    if not authors or not (nick or "").strip():
        return False
    if nick_in_giveup_seats({"giveup_seats": ",".join(authors)}, nick, live=live):
        return True
    if live is None:
        return False
    for author in authors:
        if nick_inherits_dead_seat(nick, author, live):
            return True
    return False


def mrb_author_extra_from_doc(doc: dict, claim: "GitClaim") -> dict[str, str]:
    """FR #3277: author/implementer stamps for an MRB claim from queue truth.

    Used by DONE FR enqueue, PR webhook, and resync re-add so a missing
    ``author_seat`` cannot leave the PR offerable to its own implementer.
    FR #4854: opener is the DONE FR whose result is this PR URL, never a Refs
    issue that produced a different PR.
    """
    if str(getattr(claim, "task", "") or "").upper() != "MRB":
        return {}
    if getattr(claim, "harvest_lesson", False):
        opener = str(getattr(claim, "opened_by", "") or "").strip()
        if opener and bobreport.parse_seat_nick(opener):
            seat = canonical_worker_nick(opener) or opener
            return {"author_seat": seat, "implementer_seat": seat}
        return {}
    # FR #4854: prefer DONE FR whose result is this PR, then refs that do not
    # point at a different result PR (Refs noise must not stamp author_seat).
    implementer = ""
    pull_num = str(claim.id or "").lstrip("#")
    pull_needle = f"/pull/{pull_num}"
    for row in doc.get("done") or []:
        if str(row.get("task") or "").upper() != "FR":
            continue
        url = str(row.get("url") or row.get("result") or "")
        if pull_needle not in url:
            continue
        parsed = parse_github_pull_url(url)
        if parsed and parsed[0] == claim.repo and _norm_row_id(parsed[1]) == _norm_row_id(claim.id):
            seat = str(row.get("nick") or row.get("done_by") or "").strip()
            if seat and bobreport.parse_seat_nick(seat):
                implementer = canonical_worker_nick(seat) or seat
                break
        if claim.repo.lower() in url.lower():
            seat = str(row.get("nick") or row.get("done_by") or "").strip()
            if seat and bobreport.parse_seat_nick(seat):
                implementer = canonical_worker_nick(seat) or seat
                break
    if not implementer:
        implementer = fr_implementer_seat_from_doc(
            doc, claim.repo, claim.refs, pr_id=claim.id
        )
    out: dict[str, str] = {}
    if implementer:
        out["author_seat"] = implementer
        out["implementer_seat"] = implementer
    # FR #4604: FIX (CI) seats that pushed to this PR are also self-review blocked.
    fix_seats = fix_ci_seats_from_doc(doc, claim.repo, str(claim.id or ""))
    if fix_seats:
        out["author_seats"] = ",".join(fix_seats)
        if not out.get("author_seat"):
            out["author_seat"] = fix_seats[0]
    return out


def _row_author_seat(row: dict) -> str:
    """Primary blocked seat (legacy single-value API; prefer ``row_author_seats``)."""
    seats = row_author_seats(row)
    return seats[0] if seats else ""


def uat_block_extras_from_mrb_row(mrb_row: dict, *, mrb_nick: str = "") -> dict:
    """Build UAT stamp fields from an MRB accepted/done row (FR #265).

    ``implementer_seat`` = FR implementer (MRB ``implementer_seat`` or legacy ``author_seat``).
    ``mrb_author_seat`` = MRB reviewer nick.
    ``author_seat`` = MRB reviewer (FR #227 back-compat primary).
    """
    implementer = _canon_seat_nick(
        str(
            mrb_row.get("implementer_seat")
            or mrb_row.get("author_seat")
            or mrb_row.get("author_nick")
            or ""
        )
    )
    mrb_author = _canon_seat_nick(
        mrb_nick
        or str(mrb_row.get("nick") or mrb_row.get("done_by") or mrb_row.get("mrb_author_seat") or "")
    )
    # Prefer implementer from author_seat only when it is not the same as the MRB nick
    # (DONE FR stamps author_seat=implementer; accepted MRB nick is the reviewer).
    if implementer and mrb_author and implementer.lower() == mrb_author.lower():
        # Same seat did both: still stamp once via author_seat.
        return {"author_seat": mrb_author, "mrb_author_seat": mrb_author, "implementer_seat": mrb_author}
    out: dict[str, str] = {}
    if mrb_author:
        out["author_seat"] = mrb_author
        out["mrb_author_seat"] = mrb_author
    if implementer:
        out["implementer_seat"] = implementer
        if not out.get("author_seat"):
            out["author_seat"] = implementer
    return out



# FR #618: UAT of a PR number often lacks stamps (DONE MRB stamps the Closes issue id).
MRB_PARENT_RE = re.compile(r"(?i)\bmrb-(\d+)\b")


def _row_refs_list(row: dict) -> list[str]:
    return normalize_row_refs(row.get("refs") if isinstance(row, dict) else None)


def related_mrb_rows(doc: dict, uat_row: dict) -> list[dict]:
    """Find MRB accepted/done rows related to a UAT row (FR #618)."""
    repo = str(uat_row.get("repo") or "")
    uid = str(uat_row.get("id") or "")
    urefs = set(_row_refs_list(uat_row))
    # fix(mrb-603) / mrb-619-nits in line/title/id
    blob = f"{uat_row.get('line') or ''}\n{uat_row.get('title') or ''}\n{uid}"
    for m in MRB_PARENT_RE.finditer(blob):
        urefs.add(f"#{m.group(1)}")
    found: list[dict] = []
    for bucket in ("accepted", "done"):
        for row in doc.get(bucket) or []:
            if str(row.get("repo") or "") != repo:
                continue
            if str(row.get("task") or "").upper() != "MRB":
                continue
            mid = str(row.get("id") or "")
            mrefs = set(_row_refs_list(row))
            if mid == uid or uid in mrefs or mid in urefs or (urefs & mrefs):
                found.append(row)
    return found


def enrich_uat_author_fields(doc: dict, row: dict) -> dict:
    """Copy UAT row with author stamps filled from related MRB rows when missing (FR #618).

    Used for repo-level UAT ``#0`` (t853u) when stamps are missing after DONE MRB
    stamped a Closes issue id or after resync dropped them. Without enrichment,
    ``review_blocked_for_author`` can miss the MRB reviewer / fix / implementer seats.
    Per-PR UAT is never offered (``is_repo_uat`` gate runs before enrich).
    """
    if _canon_task(row) != "UAT":
        return row
    out = dict(row)
    extras: dict[str, str] = {}
    for mrb in related_mrb_rows(doc, out):
        piece = uat_block_extras_from_mrb_row(
            mrb, mrb_nick=str(mrb.get("nick") or mrb.get("done_by") or "")
        )
        for k, v in piece.items():
            # First related MRB wins (accepted before done); do not let a later row clobber.
            if v and not out.get(k) and not extras.get(k):
                extras[k] = v
        # mrb-*-fix / nits author is typically the MRB reviewer; stamp explicitly when
        # this UAT targets a fix/nits PR related to that MRB.
        fix_nick = _canon_seat_nick(str(mrb.get("nick") or mrb.get("done_by") or ""))
        if fix_nick and not out.get("mrb_fix_author_seat") and not extras.get("mrb_fix_author_seat"):
            blob = f"{out.get('line') or ''}\n{out.get('title') or ''}\n{out.get('id') or ''}".lower()
            mid = str(mrb.get("id") or "").lstrip("#")
            if mid and (f"mrb-{mid}" in blob or "nits" in blob or "fix(mrb" in blob):
                extras["mrb_fix_author_seat"] = fix_nick
    out.update(extras)
    return out


def mrb_blocked_for_author(row: dict, nick: str, live: set[str], ledger: dict | None = None, *, free: set[str] | None = None) -> bool:
    """Alias for `review_blocked_for_author` (MRB exact-seat; UAT sibling rules).

    FR #2604 / #4606 / #9574: MRB blocks exact author/FIX nick only. Cross-PID
    same-machine shop seats may review. UAT still uses sibling / recycle rules
    (FR #1407 / #4336).
    """
    return review_blocked_for_author(row, nick, live, ledger=ledger, free=free)


def review_blocked_for_author(
    row: dict,
    nick: str,
    live: set[str],
    ledger: dict | None = None,
    *,
    free: set[str] | None = None,
) -> bool:
    """Shared MRB+UAT author block (FR #39 / #227 / #265 / #1407 / #2604 / #4606 / #9574).

    Blocks when ``nick`` matches any of ``row_author_seats`` (exact seat).

    For **MRB** (FR #2604 / #4606 / #9574): **exact-seat only**. Cross-PID
    siblings on the same machine (e.g. flamingo-17160 vs author flamingo-17068)
    are allowed even when another machine has free seats. Soft machine-id
    sibling block (FR #9401 / #9478 / #9480) false-refused ``!assign`` / offer
    on same-machine shop seats. MRB never inherits a dead author nick via
    ``nick_inherits_dead_seat`` (FR #4606).

    For **UAT**: also blocks a sibling on the same machine while another machine
    has a *viable free* live seat (FR #1407 / #2487), and a recycled sole
    successor of a dead author (FR #4336).

    Viable other-machine seats for UAT (FR #1407): not already in ``giveup_seats``,
    and for repo-level UAT when ``ledger`` is provided, not themselves
    FR-implementer blocked (``_ledger_blocks``). Giveup / fellow-implementer seats
    must not strand siblings of the stamped author after self-UAT GIVEUP loops.

    FR #2487: when ``free`` is provided, UAT sibling viability requires the
    other-machine seat to be idle/free right now (in ``free``). When ``free`` is
    None, all ``live`` seats are treated as free (unit-test / legacy default).
    """
    task = _canon_task(row)
    if task not in ("MRB", "UAT"):
        return False
    authors = row_author_seats(row)
    if not authors:
        return False
    me = canonical_worker_nick(nick) or nick
    me_l = me.lower()
    me_p = bobreport.parse_seat_nick(me)
    me_mid = bobreport.fold_machine_id(me_p[0]) if me_p else ""
    repo_uat = is_repo_uat(row)
    free_set = live if free is None else free
    free_l = {
        (canonical_worker_nick(x) or x or "").strip().lower()
        for x in free_set
        if str(x or "").strip()
    }
    def _seat_gave_up_uat(n_c: str) -> bool:
        if row_gave_up_by(row, n_c, live=live):
            return True
        if ledger is not None and repo_uat:
            other_why = _ledger_blocks(ledger, row, n_c)
            if other_why and "gave up" in other_why:
                return True
        return False

    for author in authors:
        author_l = author.lower()
        # Exact author seat: never self-MRB / self-UAT (FR #628).
        # FR #2939: do not lift exact author when others GIVEUP'd - that escape
        # disagreed with the worker self-UAT skill and stranded UAT after refuse.
        # Escalate via maybe_escalate_repo_uat_all_self_uat instead.
        if author_l == me_l:
            return True
        author_p = bobreport.parse_seat_nick(author)
        author_mid = (
            bobreport.fold_machine_id(author_p[0]) if author_p else ""
        )
        # FR #9574 / #2604 / #4606: MRB is exact-seat only (no machine-id sibling
        # block). Cross-PID shop seats on the author machine may review. Giveup
        # inheritance stays in nick_in_giveup_seats; FIX seats use exact nick
        # stamp (FR #4604). Dead-seat inherit stays UAT-only.
        if task == "MRB":
            continue
        # UAT (FR #4336): recycled sole successor inherits dead author exclusion.
        if nick_inherits_dead_seat(me, author, live):
            return True
        # UAT sibling seat on the same machine: block when another machine has a viable live seat.
        if author_p and me_p:
            if author_mid == me_mid:
                for n in live:
                    n_c = (canonical_worker_nick(n) or n or "").strip()
                    if not n_c or _seat_gave_up_uat(n_c):
                        continue
                    p = bobreport.parse_seat_nick(n_c)
                    if not p or bobreport.fold_machine_id(p[0]) == author_mid:
                        continue
                    # FR #2339: pinned-out other-machine seats are not viable - do not
                    # strand the author-machine sibling when require_machine forbids them.
                    if row_blocked_for_machine(row, n_c):
                        continue
                    # FR #2487: busy other-machine seats are not viable for sibling block.
                    if n_c.lower() not in free_l:
                        continue
                    if ledger is not None and repo_uat:
                        other_why = _ledger_blocks(ledger, row, n_c)
                        if other_why and "implemented" in other_why:
                            continue
                    return True
    return False


def row_machine_mismatch(row: dict, nick: str) -> bool:
    """FR #628 / #732: machine pin via stamp, ``machine:<id>`` label, or title/body cues.

    Delegates to ``row_blocked_for_machine`` / ``row_require_machine`` so ``!assign``
    (``assign_row``) re-infers WP0/ionos cues the same way ``offer_focus_top`` does ΓÇö
    legacy rows that never got ``_stamp_require_machine`` must not be force-assigned
    to the wrong machine.
    """
    return row_blocked_for_machine(row, nick)


def row_gave_up_by(row: dict, nick: str, live: set[str] | None = None) -> bool:
    return nick_in_giveup_seats(row, nick, live=live)


# ---------------------------------------------------------------------------
# FR #4089 (hotpatch): one open job per seat.
# A seat that holds an accepted (not-yet-DONE) row, an unaccepted row offered to it,
# or a remembered offer (seat-holds.json, survives the 90/180 s row offer window
# until the row is re-offered elsewhere - FR #4260) is never offered or pushed
# another job. Rows still time back to the queue for OTHER seats as before.
# Cleared by: DONE/NACK/GIVEUP for that job (all seats holding the job key -
# FR #4260), ACK (accepted row takes over), re-offer to another nick (FR #4260),
# seat QUIT/PART, the seat leaving the live worker list, or SEAT_HOLD_MAX_S.
# ---------------------------------------------------------------------------
SEAT_HOLDS_NAME = "seat-holds.json"
SEAT_HOLD_MAX_S = 3600.0  # same as BUSY_STALE_S (stale-job reaper)

# FR #4181: after GIVEUP reason=out-of-fuel, do not giveup-offer / !bored-offer that
# nick until the seat signals fuel is back (fresh !bored clears the mark).
SEAT_OUT_OF_FUEL_NAME = "seat-out-of-fuel.json"
SEAT_OUT_OF_FUEL_MAX_S = 7 * 24 * 3600.0  # weekly Grok period ceiling


def _seat_key(nick: str) -> str:
    return (canonical_worker_nick(nick or "") or nick or "").strip().lower()


# FR #7837: pause offers while a fresh digest pool is exactly 0% until its reset.
FUEL_PAUSE_REASON = "pool-0-until-reset"
# FR #8592: Go week window exhausted/limited while rolling may still show remaining.
OPENCODE_WEEK_LIMITED_REASON = "opencode-week-limited"
FUEL_FRESH_MAX_S = 120.0


def _fuel_clock(now: float | None) -> float:
    import time as _time

    return _time.time() if now is None else float(now)


def _fuel_epoch(raw: object) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _pool_reading_fresh(pool: dict, now_f: float) -> bool:
    fresh = pool.get("fresh")
    if fresh is True:
        return True
    if fresh is False:
        return False
    fetched = _fuel_epoch(pool.get("fetched_at"))
    if fetched is None:
        return False
    age = now_f - fetched
    return 0.0 <= age <= FUEL_FRESH_MAX_S


def _pool_remaining_exact_zero(pool: dict) -> bool:
    for key in ("remaining", "remaining_pct"):
        if key not in pool or pool.get(key) is None:
            continue
        try:
            return float(pool.get(key)) == 0.0
        except (TypeError, ValueError):
            return False
    return False


def _pool_future_reset(pool: dict, now_f: float) -> str:
    for key in ("period_end", "reset_at", "quota_reset_date"):
        raw = pool.get(key)
        ts = _fuel_epoch(raw)
        if ts is not None and ts > now_f:
            return str(raw).strip()
    return ""


def _opencode_free_pool_from_machine(ent: dict) -> dict | None:
    """Build a pauseable free-pool reading from digest pcent (FR #8028)."""
    if not isinstance(ent, dict):
        return None
    pcent = ent.get("pcent") if isinstance(ent.get("pcent"), dict) else {}
    rem = pcent.get("opencode-free")
    if rem is None:
        rem = pcent.get("opencode_free")
    if rem is None:
        nested = ent.get("opencode") if isinstance(ent.get("opencode"), dict) else {}
        rem = nested.get("opencode-free", nested.get("free", nested.get("remaining")))
    if rem is None:
        return None
    try:
        rem_f = float(rem)
    except (TypeError, ValueError):
        return None
    reset = (
        ent.get("opencode_free_reset_at")
        or ent.get("opencode_free_reset")
        or ent.get("free_reset_at")
        or (ent.get("opencode") or {}).get("free_reset_at")
        or (ent.get("opencode") or {}).get("period_end")
        or (ent.get("opencode") or {}).get("reset_at")
    )
    fetched = ent.get("fetched_at") or (ent.get("opencode") or {}).get("fetched_at")
    pool = {
        "remaining_pct": rem_f,
        "remaining": rem_f,
        "fresh": True,
        "fetched_at": fetched or "1970-01-01T00:00:00Z",
    }
    if reset:
        pool["period_end"] = reset
        pool["reset_at"] = reset
    return pool


def _machine_pool_for_kind(ent: dict, kind: str) -> dict | None:
    k = (kind or "").strip().lower()
    if k in ("grok", "grok-build", "xai"):
        pool = ent.get("xai_weekly") if isinstance(ent.get("xai_weekly"), dict) else ent.get("xai")
    elif k == "cursor":
        pool = ent.get("copilot") if isinstance(ent.get("copilot"), dict) else ent.get("copilot_pool")
    elif k == "opencode":
        pool = ent.get("opencode")
    else:
        return None
    return pool if isinstance(pool, dict) else None


def _raw_digest_machine(home: Path, mid: str) -> dict:
    path = bobreport.digest_path(_root(home))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    ent = (doc.get("machines") or {}).get(mid) if isinstance(doc, dict) else None
    return ent if isinstance(ent, dict) else {}


def _stamp_worker_fuel_pause(home: Path, mid: str, pid: str, until: str, reason: str) -> None:
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else None
    ent = machines.get(mid) if isinstance(machines, dict) else None
    if not isinstance(ent, dict):
        return
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else None
    if not isinstance(workers, dict):
        return
    row = workers.get(str(pid))
    if not isinstance(row, dict):
        return
    changed = False
    if reason and until:
        if str(row.get("fuel_paused_until") or "") != until or str(row.get("fuel_pause_reason") or "") != reason:
            row["fuel_paused_until"] = until
            row["fuel_pause_reason"] = reason
            changed = True
    elif row.get("fuel_paused_until") or row.get("fuel_pause_reason"):
        row.pop("fuel_paused_until", None)
        row.pop("fuel_pause_reason", None)
        changed = True
    if changed:
        try:
            bobreport.save_digest(_root(home), doc)
        except OSError:
            return



def _opencode_go_windows_from_digest(home: Path) -> dict:
    """Fleet/machine Go window map (rolling/week/month) from digest (FR #8592)."""
    path = bobreport.digest_path(_root(home))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(doc, dict):
        return {}
    for root_key in ("fleet_pools", "opencode"):
        root = doc.get(root_key)
        if not isinstance(root, dict):
            continue
        if root_key == "fleet_pools":
            go = root.get("opencode-go") or root.get("opencode_go") or root.get("opencode")
            if isinstance(go, dict):
                win = go.get("windows")
                if isinstance(win, dict) and win:
                    return win
        else:
            win = root.get("windows")
            if isinstance(win, dict) and win:
                return win
    return {}


def _go_window_is_limited(win: object) -> bool:
    """True when a Go CAP window is exhausted/limited (FR #8592)."""
    if not isinstance(win, dict):
        return False
    if win.get("limited") is True:
        return True
    status = str(win.get("status") or "").strip().lower()
    if status in ("exhausted", "limited", "capped"):
        return True
    try:
        rem = win.get("remaining_pct")
        if rem is not None and float(rem) <= 0.0:
            return True
        used = win.get("used_pct")
        if used is not None and float(used) >= 100.0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _opencode_week_limited_pause(
    home: Path,
    nick: str,
    kind: str,
    now_f: float,
) -> tuple[str, str]:
    """Return (reason, until) when Go week is limited for a paid OpenCode seat.

    Free OpenCode seats stay on the free-pool pause path (FR #8028). Rolling /
    month remain soft notes only - week.limited alone gates new offers (FR #8592).
    """
    k = (kind or "").strip().lower()
    me = (canonical_worker_nick(nick) or nick or "").strip()
    if k != "opencode":
        # Also catch paid go models mistyped under another kind.
        fields = _seat_digest_model_fields(home, me)
        model = _start_model_from_fields(fields).lower()
        if not (model.startswith("opencode-go/") or "/opencode-go/" in model):
            return "", ""
    if seat_is_free_fuel(home, me):
        return "", ""
    windows = _opencode_go_windows_from_digest(home)
    week = windows.get("week") if isinstance(windows, dict) else None
    if not _go_window_is_limited(week):
        return "", ""
    until = ""
    if isinstance(week, dict):
        for key in ("resets_at", "reset_at", "period_end", "quota_reset_date"):
            raw = str(week.get(key) or "").strip()
            ts = _fuel_epoch(raw)
            if raw and ts is not None and ts > now_f:
                until = raw
                break
        if not until:
            until = _pool_future_reset(week, now_f)
    return OPENCODE_WEEK_LIMITED_REASON, until


def seat_fuel_pause_reason(home: Path, nick: str, now: float | None = None) -> str:
    """FR #7837: ``pool-0-until-reset`` when a fresh pool is 0% before its reset.

    Unknown agent kinds do not pause. A stale or ``fresh is False`` 0% does not
    pause. The worker row is stamped (or cleared) so the digest shows the pause.

    FR #8028: when the free pool is still exact 0 but the machine reset field
    was stripped by a digest coerce, keep an existing future worker stamp so
    ``offer_focus_top`` does not self-clear the pause on its second check.
    """
    now_f = _fuel_clock(now)
    me = (canonical_worker_nick(nick) or nick or "").strip()
    parsed = bobreport.parse_seat_nick(me)
    if not parsed:
        return ""
    mid, pid = parsed
    kind = seat_agent_kind(home, me)
    ent = _raw_digest_machine(home, mid)
    pool = _machine_pool_for_kind(ent, kind)
    # FR #8028: free OpenCode seats pause on opencode-free=0, not the Go meter.
    if kind == "opencode" and seat_is_free_fuel(home, me):
        free_pool = _opencode_free_pool_from_machine(ent)
        if free_pool is not None:
            pool = free_pool
    until = ""
    reason = ""
    # FR #8592: paid OpenCode / opencode-go - skip new offers when week limited
    # even if rolling remaining_pct > 0 (machine pool alone would not pause).
    week_reason, week_until = _opencode_week_limited_pause(home, me, kind, now_f)
    if week_reason:
        until = week_until or until
        reason = week_reason
        _stamp_worker_fuel_pause(home, mid, pid, until, reason)
        return reason
    if pool and _pool_reading_fresh(pool, now_f) and _pool_remaining_exact_zero(pool):
        until = _pool_future_reset(pool, now_f)
        if not until:
            # Keep a live worker stamp when reset was lost on digest rewrite.
            workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
            row = workers.get(str(pid)) if isinstance(workers.get(str(pid)), dict) else {}
            stamped = str((row or {}).get("fuel_paused_until") or "").strip()
            stamped_reason = str((row or {}).get("fuel_pause_reason") or "").strip()
            stamped_ts = _fuel_epoch(stamped)
            if (
                stamped
                and stamped_ts is not None
                and stamped_ts > now_f
                and stamped_reason == FUEL_PAUSE_REASON
            ):
                until = stamped
        if until:
            reason = FUEL_PAUSE_REASON
    _stamp_worker_fuel_pause(home, mid, pid, until, reason)
    return reason



def is_hard_ceiling_reason(reason: str) -> bool:
    """True when a GIVEUP reason is an OpenCode hard-ceiling kill (FR #8008)."""
    text = (reason or "").strip().lower()
    if not text:
        return False
    return "hard ceiling" in text or text.replace("_", "-").startswith("hard-ceiling")


def is_stop_closed_giveup_reason(reason: str) -> bool:
    """True for a GIVEUP because the issue was already closed (FR #8645).

    The seat can be recycled. This must not stamp needs_human or block a fresh seat.
    """
    token = _deterministic_nack_token(reason)
    return token == "process-exit:stop-closed" or token.startswith("process-exit:stop-closed")


def is_infra_soft_giveup_reason(reason: str) -> bool:
    """True when a NACK/GIVEUP is infra or a soft seat fault (FR #8375).

    These must not increment giveup_count or stamp needs_human. A fresh seat
    must stay offerable. Covers hard-ceiling, worktree-create-failed (and the
    other FR #6240 pre-ACK classes), holder_bored, offer-timeout, and
    process-exit:stop-closed (FR #8645).
    Product GIVEUPs stay on the FR #180 threshold.
    """
    if is_stop_closed_giveup_reason(reason):
        return True
    if is_hard_ceiling_reason(reason):
        return True
    if is_deterministic_nack_reason(reason) or is_worktree_head_mismatch_reason(reason):
        return True
    token = _deterministic_nack_token(reason)
    if not token:
        return False
    if token == "busy" or token.startswith("busy-"):
        return True
    return token in ("holder-bored", "offer-timeout") or token.startswith(
        ("holder-bored", "offer-timeout")
    )


def is_busy_nack_reason(reason: str) -> bool:
    """True for ``NACK … busy`` (FR #8465).

    Seat-local short backoff only. Must not set queue ``cooldown_until``.
    """
    token = _deterministic_nack_token(reason)
    return token == "busy" or token.startswith("busy-")


def is_already_finished_nack_reason(reason: str) -> bool:
    """True for ``NACK … already finished`` (FR #9339).

    Seat may claim a job is finished; chair must confirm a verdict on the
    **current** head SHA (or closed/merged PR) before treating it as terminal.
    """
    token = _deterministic_nack_token(reason)
    if token == "already-finished" or token.startswith("already-finished"):
        return True
    text = (reason or "").strip().lower().replace("_", " ")
    return "already finished" in text


def mrb_verdict_covers_current_head(
    row: dict,
    doc: dict | None = None,
    *,
    home: Path | None = None,
) -> bool:
    """FR #9339: True when a recorded MRB verdict covers this row's current head.

    Terminal when: row/PR looks closed or merged, or a done[] PASS/FAIL SHA
    matches ``row['head_sha']``. Missing head_sha with no matching done SHA is
    **not** terminal (re-offer; do not needs_human on already-finished NACK).
    """
    if not isinstance(row, dict):
        return False
    if _canon_task(row) != "MRB":
        return False
    state = str(row.get("state") or "").strip().lower()
    if state in ("closed", "merged"):
        return True
    result = str(row.get("result") or "").strip().upper()
    if result in ("MERGED", "CLOSED"):
        return True
    head = _sha_from_queue_row(row)
    repo = str(row.get("repo") or "").strip()
    ident = _norm_row_id(str(row.get("id") or ""))
    if not repo or not ident:
        return False
    # Prefer done[] SHA for this PR (any nick).
    done_sha = ""
    if isinstance(doc, dict):
        repo_c = canonical_queue_repo(repo)
        for r in doc.get("done") or []:
            if not isinstance(r, dict):
                continue
            if str(r.get("task") or "").upper() != "MRB":
                continue
            if canonical_queue_repo(str(r.get("repo") or "")) != repo_c:
                continue
            if _norm_row_id(str(r.get("id") or "")) != ident:
                continue
            res = str(r.get("result") or "").strip().upper()
            if res not in ("PASS", "FAIL", "MERGED", "CLOSED"):
                continue
            if res in ("MERGED", "CLOSED"):
                return True
            done_sha = _sha_from_queue_row(r) or done_sha
    if not done_sha and home is not None:
        with contextlib.suppress(Exception):
            num = int(ident.lstrip("#"))
            done_sha = str(_merge_on_green_pass_sha(home, repo, num) or "").strip().lower()
    if not head or not done_sha:
        return False
    try:
        import mrb_merge_on_green as _mog

        return bool(_mog.shas_match(done_sha, head))
    except Exception:
        return done_sha[:7] == head[:7]


def giveup_agent_kinds(row: dict) -> list[str]:
    """Canonical agent kinds blocked after repeated hard-ceiling GIVEUPs (FR #8008)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in str((row or {}).get("giveup_agent_kinds") or "").split(","):
        kind = raw.strip().lower()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        out.append(kind)
    return out


def row_blocked_for_giveup_agent_kind(row: dict, kind: str) -> bool:
    """True when this seat's agent kind is in the row's giveup_agent_kinds (FR #8008)."""
    k = (kind or "").strip().lower()
    if not k:
        return False
    return k in set(giveup_agent_kinds(row))


def append_giveup_agent_kind(row: dict, kind: str) -> None:
    """Append an agent kind to giveup_agent_kinds (deduped, lowercase)."""
    k = (kind or "").strip().lower()
    if not k:
        return
    kinds = giveup_agent_kinds(row)
    if k not in kinds:
        kinds.append(k)
    row["giveup_agent_kinds"] = ",".join(kinds)


def is_out_of_fuel_reason(reason: str) -> bool:
    """True when a GIVEUP/NACK trailing reason is the worker out-of-fuel wire (FR #4181)."""
    text = (reason or "").strip().lower()
    if not text:
        return False
    norm = text.replace("_", "-").replace(" ", "-")
    token = norm.split(",", 1)[0].strip()
    return token == "out-of-fuel" or token.startswith("out-of-fuel-")


def is_worktree_head_mismatch_reason(reason: str) -> bool:
    """True when MRB/FIX worktree create failed head-mismatch (FR #8326).

    Seat/worktree fault: a stale author checkout must not burn giveup_count
    or stamp needs_human. The NACK carries ``want=`` and ``have=`` SHAs.
    """
    token = _deterministic_nack_token(reason)
    if not token:
        return False
    return (
        token == "worktree-create-failed:head-mismatch"
        or token.startswith("worktree-create-failed:head-mismatch")
        or token == "head-mismatch"
        or token.startswith("head-mismatch")
    )


def heal_worktree_head_mismatch_row(row: dict) -> bool:
    """Drop needs_human / giveup stamps left by a head-mismatch NACK (FR #8326)."""
    if not isinstance(row, dict):
        return False
    if not is_worktree_head_mismatch_reason(str(row.get("giveup_reason") or "")):
        return False
    changed = False
    if row.get("needs_human"):
        row.pop("needs_human", None)
        changed = True
    if int(row.get("giveup_count") or 0):
        row["giveup_count"] = 0
        changed = True
    if str(row.get("giveup_seats") or "").strip():
        row.pop("giveup_seats", None)
        changed = True
    if str(row.get("cooldown_until") or "").strip():
        row.pop("cooldown_until", None)
        changed = True
    return changed


def is_skill_dag_down_reason(reason: str) -> bool:
    """True when a GIVEUP reason is skill-dag preflight / MCP down (FR #7963 / #8846).

    Seat fault, not job fault: ``skill_dag_down``, ``skill-dag-down:exit-1``,
    or ``skill-dag-mcp-down`` (FR #8846 fail-closed when MCP + mcp.json CLI both fail).
    """
    text = (reason or "").strip().lower()
    if not text:
        return False
    norm = text.replace("_", "-").replace(" ", "-")
    token = norm.split(",", 1)[0].strip()
    return (
        token == "skill-dag-down"
        or token.startswith("skill-dag-down:")
        or token == "skill-dag-mcp-down"
        or token.startswith("skill-dag-mcp-down:")
    )


def is_console_closed_reason(reason: str) -> bool:
    """True when a GIVEUP reason is console-close / Ctrl (FR #8154).

    Seat fault: ``console-closed`` or ``console-closed wip=<ref>``. Re-offer promptly
    (no long cooldown) and prefer the giving seat's machine so the worktree is reused.
    """
    text = (reason or "").strip().lower()
    if not text:
        return False
    # First whitespace-separated token (keep ``wip=`` as a trailing field).
    head = text.replace("_", "-").split(None, 1)[0].strip()
    head = head.split(",", 1)[0].strip()
    return head == "console-closed" or head.startswith("console-closed")


def console_closed_wip_ref(reason: str) -> str:
    """Extract ``wip=<ref>`` from a console-closed GIVEUP reason, else ``\"\"``."""
    text = (reason or "").strip()
    if not text:
        return ""
    m = re.search(r"(?i)\bwip=([^\s,]+)", text)
    return (m.group(1) if m else "").strip()


def _deterministic_nack_token(reason: str) -> str:
    """Normalised class token from a NACK/GIVEUP reason (FR #8017 / #8153)."""
    text = (reason or "").strip().lower()
    if not text:
        return ""
    head = text.split("(", 1)[0].strip()
    norm = head.replace("_", "-").replace(" ", "-")
    return norm.split(",", 1)[0].strip()


def is_deterministic_nack_reason(reason: str) -> bool:
    """True for stable pre-ACK NACK classes that must cool that seat (FR #8017).

    Covers the FR #6240 OpenCode/worker worktree and job-context family. Transient
    reasons (busy, try later, etc.) stay re-offerable to the same seat.
    """
    token = _deterministic_nack_token(reason)
    if not token:
        return False
    if token in (
        "worktree-create-failed",
        "worktree-absent",
        "job-context-malformed",
        "job-context-ambiguous",
    ):
        return True
    return (
        token.startswith("worktree-create-failed:")
        or token.startswith("worktree-absent:")
        or token.startswith("job-context-malformed:")
        or token.startswith("job-context-ambiguous:")
    )


def is_no_terminal_reply_reason(reason: str) -> bool:
    """True for a seat that went silent after ACK and never finished (FR #8298)."""
    return _deterministic_nack_token(reason) == "no-terminal-reply"


def no_terminal_reply_does_not_block(row: dict, nick: str) -> bool:
    """A lone ``no-terminal-reply`` is not a permanent reviewer refusal (FR #8298).

    The seat never committed. An expiring ``deterministic_nack_until`` stamp may
    still cool that seat. Any other give-up reason stays a permanent block.
    """
    if not isinstance(row, dict):
        return False
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    mine: list[dict] = []
    for raw in row.get("offer_outcomes") or []:
        if not isinstance(raw, dict):
            continue
        other = (canonical_worker_nick(str(raw.get("seat") or "")) or str(raw.get("seat") or "")).strip().lower()
        if other == me:
            mine.append(raw)
    if mine:
        return all(is_no_terminal_reply_reason(str(item.get("reason") or "")) for item in mine)
    # Legacy rows (pre offer_outcomes): the row-level giveup_reason is only this
    # seat's no-terminal-reply when this seat is the sole give-up seat. Otherwise
    # a later no-terminal-reply would wrongly lift another seat's permanent block.
    if not is_no_terminal_reply_reason(str(row.get("giveup_reason") or "")):
        return False
    seats = {
        (canonical_worker_nick(s) or s or "").strip().lower()
        for s in str(row.get("giveup_seats") or "").split(",")
    }
    seats.discard("")
    return seats == {me}


def stamp_seat_nack_cooldown(
    row: dict,
    nick: str,
    now: float | None = None,
    *,
    seconds: float | None = None,
) -> None:
    """Per-seat expiring cooldown on ``row`` (does not write the queue). FR #8298."""
    import time as _time
    from datetime import timedelta as _td

    me = (canonical_worker_nick(nick) or nick or "").strip()
    if not me or not isinstance(row, dict):
        return
    now_f = _time.time() if now is None else float(now)
    span = float(GIVEUP_COOLDOWN_S if seconds is None else seconds)
    until = datetime.fromtimestamp(now_f, tz=timezone.utc) + _td(seconds=span)
    until_s = until.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stamps = row.get("deterministic_nack_until")
    if not isinstance(stamps, dict):
        stamps = {}
    stamps[me] = until_s
    row["deterministic_nack_until"] = stamps


def is_no_clone_nack_reason(reason: str) -> bool:
    """True when the NACK means this seat cannot serve that repo's clone (FR #8153)."""
    token = _deterministic_nack_token(reason)
    if not token:
        return False
    if token in ("no-clone", "worktree-create-failed:no-clone"):
        return True
    return token.startswith("worktree-create-failed:no-clone")


def seat_on_deterministic_nack_cooldown(
    row: dict, nick: str, now: float
) -> bool:
    """True when this seat has an unexpired FR #8017 pre-ACK deterministic NACK."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me or not isinstance(row, dict):
        return False
    stamps = row.get("deterministic_nack_until")
    if not isinstance(stamps, dict):
        return False
    raw = None
    for key, val in stamps.items():
        other = (canonical_worker_nick(str(key)) or str(key) or "").strip().lower()
        if other == me:
            raw = val
            break
    until = _parse_iso_ts(str(raw or ""))
    if until is None:
        return False
    return float(now) < float(until)


def stamp_deterministic_nack_on_unaccepted(
    home: Path,
    *,
    nick: str,
    repo: str,
    task: str,
    ident: str,
    reason: str = "",
    now: float | None = None,
) -> dict | None:
    """Per-seat cooldown on an offered (not yet ACK'd) row after deterministic NACK (FR #8017).

    Pre-ACK NACK returns ``missing`` from ``return_job_to_unaccepted`` because the
    row never entered accepted[]. Without this stamp, ``!bored`` re-offers the
    same job to the same seat immediately. Uses ``deterministic_nack_until`` (not
    permanent ``giveup_seats``) so the seat may retry after ``GIVEUP_COOLDOWN_S``
    or a seat recycle. Does not bump giveup_count / needs_human.
    """
    import time as _time
    from datetime import timedelta as _td

    if not is_deterministic_nack_reason(reason):
        return None
    me = (canonical_worker_nick(nick) or nick or "").strip()
    if not me:
        return None
    now_f = _time.time() if now is None else float(now)
    want_repo = (repo or "").strip()
    want_task = (task or "FR").strip().upper()
    if want_task == "PR":
        want_task = "FR"
    want_id = str(ident or "").strip()
    if want_id and not want_id.startswith("#"):
        want_id = f"#{want_id}"
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, ValueError):
                return None
            found = None
            for row in doc.get("unaccepted") or []:
                if not isinstance(row, dict):
                    continue
                # FR #8153: alias/case-aware match (priority-mcp / agentic_fomprep).
                if not repo_alias.repos_equivalent(str(row.get("repo") or ""), want_repo):
                    continue
                rt = str(row.get("task") or "FR").strip().upper()
                if rt == "PR":
                    rt = "FR"
                if rt != want_task:
                    continue
                rid = str(row.get("id") or "").strip()
                if rid and not rid.startswith("#"):
                    rid = f"#{rid}"
                if rid != want_id:
                    continue
                found = row
                break
            if found is None:
                return None
            until = datetime.fromtimestamp(now_f, tz=timezone.utc) + _td(
                seconds=float(GIVEUP_COOLDOWN_S)
            )
            until_s = until.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            stamps = found.get("deterministic_nack_until")
            if not isinstance(stamps, dict):
                stamps = {}
            # Drop expired entries so the map stays small.
            kept: dict[str, str] = {}
            for key, val in stamps.items():
                ts = _parse_iso_ts(str(val or ""))
                if ts is not None and float(ts) > now_f:
                    canon = (canonical_worker_nick(str(key)) or str(key) or "").strip()
                    if canon:
                        kept[canon] = str(val)
            kept[me] = until_s
            found["deterministic_nack_until"] = kept
            if reason:
                found["giveup_reason"] = str(reason).strip()[:200]
                note_offer_outcome(found, me, "nack", found["giveup_reason"])
            for k in ("offered_to", "offered_ts", "offered_channel", "offered_via"):
                found.pop(k, None)
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return None
            return dict(found)
    except (TimeoutError, OSError):
        return None


def stamp_seat_no_clone_repo(
    home: Path,
    *,
    nick: str,
    repo: str,
    now: float | None = None,
) -> bool:
    """Record that *nick* cannot serve *repo* until re-announce (FR #8153).

    Durable in ``seat-ledger.json`` under ``no_clone_repos`` so every job for
    that repo is skipped for this seat (not only the one NACKed row). Cleared
    on shop JOIN / hello via :func:`clear_seat_no_clone_repos`.
    """
    import time as _time

    me = _canon_ledger_nick(nick)
    repo_k = _repo_key(repo)
    if not me or not repo_k:
        return False
    now_f = _time.time() if now is None else float(now)
    ts = datetime.fromtimestamp(now_f, tz=timezone.utc).replace(microsecond=0)
    ts_s = ts.isoformat().replace("+00:00", "Z")

    def _f(doc: dict) -> None:
        bucket = doc.setdefault("no_clone_repos", {})
        if not isinstance(bucket, dict):
            bucket = {}
            doc["no_clone_repos"] = bucket
        seats = bucket.setdefault(me, {})
        if not isinstance(seats, dict):
            seats = {}
            bucket[me] = seats
        seats[repo_k] = ts_s

    try:
        _ledger_update(home, _f)
        return True
    except OSError:
        return False


def seat_blocked_for_no_clone_repo(home: Path, nick: str, repo: str) -> bool:
    """True when FR #8153 stamped this seat as unable to serve *repo*."""
    me = _canon_ledger_nick(nick)
    repo_k = _repo_key(repo)
    if not me or not repo_k:
        return False
    try:
        doc = ledger_load(home)
    except Exception:
        return False
    bucket = doc.get("no_clone_repos")
    if not isinstance(bucket, dict):
        return False
    seats = bucket.get(me)
    if not isinstance(seats, dict):
        # Also accept canonical nick key variants.
        for key, val in bucket.items():
            other = _canon_ledger_nick(str(key))
            if other == me and isinstance(val, dict):
                seats = val
                break
    if not isinstance(seats, dict):
        return False
    if repo_k in seats:
        return True
    # Alias-aware: compare each blocked key.
    for blocked in seats:
        if repo_alias.repos_equivalent(str(blocked), repo):
            return True
    return False


def clear_seat_no_clone_repos(home: Path, nick: str) -> bool:
    """Clear FR #8153 no-clone repo blocks for *nick* (JOIN / hello re-announce)."""
    me = _canon_ledger_nick(nick)
    if not me:
        return False

    def _f(doc: dict) -> None:
        bucket = doc.get("no_clone_repos")
        if not isinstance(bucket, dict):
            return
        drop = [k for k in list(bucket.keys()) if _canon_ledger_nick(str(k)) == me]
        for k in drop:
            bucket.pop(k, None)

    try:
        _ledger_update(home, _f)
        return True
    except OSError:
        return False


def _seat_out_of_fuel_path(home: Path) -> Path:
    return _root(home) / SEAT_OUT_OF_FUEL_NAME


def _load_seat_out_of_fuel_unlocked(home: Path, now: float | None = None) -> dict:
    import time as _time

    now_f = _time.time() if now is None else float(now)
    path = _seat_out_of_fuel_path(home)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    seats = doc.get("seats") if isinstance(doc, dict) else None
    if not isinstance(seats, dict):
        return {}
    out: dict = {}
    for k, v in seats.items():
        if not isinstance(v, dict):
            continue
        if _offer_age_s({"offered_ts": v.get("ts")}, now_f) >= SEAT_OUT_OF_FUEL_MAX_S:
            continue
        out[str(k).strip().lower()] = v
    return out


def _save_seat_out_of_fuel_unlocked(home: Path, seats: dict) -> None:
    path = _seat_out_of_fuel_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"v": 1, "seats": seats}, indent=2) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))



def _seat_digest_model_fields(home: Path, nick: str) -> dict:
    """FR #7084: start_model / mismatch / cost_tier from digest workers or worker_list."""
    me = (canonical_worker_nick(nick) or nick or "").strip()
    parsed = bobreport.parse_seat_nick(me)
    if not parsed:
        return {}
    mid, pid = parsed
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return {}
    ent = (doc.get("machines") or {}).get(mid) or {}
    if not isinstance(ent, dict):
        return {}
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    w = workers.get(str(pid)) if isinstance(workers.get(str(pid)), dict) else {}
    if w:
        return dict(w)
    for r in bobreport._coerce_worker_list(ent.get("worker_list")):
        if str(r.get("nick") or "").strip().lower() == me.lower():
            return dict(r)
    return {}


def _seat_model_allows_row(home: Path, nick: str, cand: dict) -> bool:
    """FR #7084: unknown digest model does not block; mismatch / too-cheap does.

    FR #7833: an unexpanded ``$model`` (or any ``$`` variable, empty, or missing
    start model) is unknown. It is not a mismatch. The tier uses
    ``configured_model`` when that is a real id. Neither known matches the
    no-model allow. A placeholder is reported once per seat for this process.
    """
    fields = _seat_digest_model_fields(home, nick)
    if not fields:
        return True
    try:
        import worker_start_model as wsm

        cfg = wsm.load_worker_start_config()
        return wsm.seat_model_allows(
            fields,
            str((cand or {}).get("task") or ""),
            cfg,
            nick=canonical_worker_nick(nick) or nick,
        )
    except Exception:
        return True


def seat_agent_kind(home: Path, nick: str) -> str:
    """Digest agent kind for a seat nick (``grok`` / ``cursor`` / ``opencode`` / ...).

    Empty string when unknown. FR #6134: OpenCode seats skip hostile MRB/UAT offers.
    Prefer pid-keyed ``workers`` (merge reports carry ``kind``); fall back to
    ``worker_list`` kind/agent when present.
    """
    me = (canonical_worker_nick(nick) or nick or "").strip()
    parsed = bobreport.parse_seat_nick(me)
    if not parsed:
        return ""
    mid, pid = parsed
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return ""
    ent = (doc.get("machines") or {}).get(mid) or {}
    if not isinstance(ent, dict):
        return ""
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    w = workers.get(str(pid)) if isinstance(workers.get(str(pid)), dict) else {}
    kind = str((w or {}).get("kind") or "").strip().lower()
    if kind:
        return kind
    agent = str((w or {}).get("agent") or "").strip().lower()
    if "opencode" in agent:
        return "opencode"
    for r in bobreport._coerce_worker_list(ent.get("worker_list")):
        if str(r.get("nick") or "").strip().lower() != me.lower():
            continue
        k = str(r.get("kind") or "").strip().lower()
        if k:
            return k
        a = str(r.get("agent") or "").strip().lower()
        if "opencode" in a:
            return "opencode"
    return ""


def seat_skips_hostile_review(kind: str) -> bool:
    """True when this agent kind must not take MRB/UAT (FR #6134 OpenCode trial)."""
    return (kind or "").strip().lower() == "opencode"


def _start_model_from_fields(fields: dict | None) -> str:
    f = fields or {}
    return str(f.get("start_model") or f.get("model") or "").strip()


def opencode_unpaid_model(home: Path) -> str:
    """Model id on the Weights Opencode-Free row (GET /bob/v1/models).

    That saved row is the only unpaid OpenCode model. Missing file or row
    means nothing is unpaid.
    """
    try:
        import models_catalog as mc

        path = mc.catalog_path(_root(home))
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    agents = raw.get("agents") if isinstance(raw, dict) else None
    if not isinstance(agents, list):
        return ""
    for row in agents:
        if not isinstance(row, dict):
            continue
        name = str(row.get("agent") or row.get("row") or "").strip()
        if name != "Opencode-Free":
            continue
        return str(row.get("model") or "").strip()
    return ""


def _seat_kind_always_paid(kind: str) -> bool:
    """Grok and Cursor are never free fuel. Only OpenCode can be unpaid."""
    return (kind or "").strip().lower() in ("grok", "cursor")


def seat_started_on_free_model(home: Path, nick: str) -> bool:
    """True only for an OpenCode seat on the saved unpaid Weights model.

    Grok and Cursor are always paid, even when start_model is empty or the
    id looks free. Any other OpenCode model, including empty and ``$model``,
    is paid.
    """
    if _seat_kind_always_paid(seat_agent_kind(home, nick)):
        return False
    if seat_agent_kind(home, nick) != "opencode":
        return False
    fields = _seat_digest_model_fields(home, nick)
    model = str(fields.get("start_model") or fields.get("model") or "").strip()
    unpaid = opencode_unpaid_model(home)
    return bool(model) and bool(unpaid) and model == unpaid


def idle_free_model_nicks(home: Path, *, now: float | None = None, live: set[str] | None = None) -> set[str]:
    """Idle seats whose start_model is a free model (FR #7926)."""
    found: set[str] = set()
    rows = []
    try:
        rows.extend(digest_idle_ready_seats(home, now=now, live=live))
    except Exception:
        rows = []
    try:
        for extra in list_idle_after_empty(home, now=now, live=live):
            rows.append(extra)
    except Exception:
        pass
    for ent in rows:
        nick = str((ent or {}).get("nick") or "").strip()
        if not nick or worker_working_on(home, nick):
            continue
        if seat_started_on_free_model(home, nick):
            found.add((canonical_worker_nick(nick) or nick).strip().lower())
    return found


def _free_seat_can_take_row(
    home: Path,
    cand: dict,
    nick: str,
    now: float,
    live: set[str],
    ledger: dict | None,
) -> bool:
    """Local eligibility for reserving an FR/FIX for this free seat."""
    if row_on_cooldown(cand, now, nick, live=live):
        return False
    if row_needs_human(cand, nick):
        return False
    if row_machine_mismatch(cand, nick) or row_gave_up_by(cand, nick, live=live):
        return False
    if row_blocked_for_machine(cand, nick):
        return False
    # FR #8008: repeated hard-ceiling GIVEUPs block the whole agent class (e.g. opencode).
    if row_blocked_for_giveup_agent_kind(cand, seat_agent_kind(home, nick)):
        return False
    if not _seat_model_allows_row(home, nick, cand):
        return False
    try:
        if ledger_blocks(ledger, cand, nick, live):
            return False
    except Exception:
        return False
    return True


def fr_reserved_for_idle_free_seat(
    home: Path,
    cand: dict,
    nick: str,
    now: float,
    live: set[str],
    ledger: dict | None,
    free_idle: set[str],
) -> bool:
    """True when a paid seat must leave this FR/FIX for an idle free seat."""
    task = str((cand or {}).get("task") or "").upper()
    if task not in ("FR", "FIX"):
        return False
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if me and me in free_idle:
        return False
    if seat_started_on_free_model(home, nick):
        return False
    for other in free_idle:
        if other == me:
            continue
        if _free_seat_can_take_row(home, cand, other, now, live, ledger):
            return True
    return False


def _row_queue_age_key(row: dict) -> tuple[float, float]:
    """Lower is older. Prefer positive ``seq``, else parse ``ts``."""
    try:
        seq = int((row or {}).get("seq") or 0)
    except (TypeError, ValueError):
        seq = 0
    ts = _parse_iso_ts(str((row or {}).get("ts") or "")) or 0.0
    # Missing seq sorts after stamped seq so age still follows ts when possible.
    return (float(seq) if seq > 0 else 1e12, float(ts))


def mrb_yields_to_older_fr(
    home: Path,
    cand: dict,
    nick: str,
    now: float,
    live: set[str],
    ledger: dict | None,
    free_idle: set[str],
    unaccepted: list | None,
) -> bool:
    """FR #8138: when no free seat is idle, skip a newer MRB if an older FR/FIX waits.

    Amends #7926: free seats still take FR first when up. With only Grok/paid seats,
    do not starve an older waiting FR behind a later MRB in focus order.

    Documented offer rule (FR #8193 / Si 17 Nov):
    - free_idle non-empty: classic MRB-before-FR among seats that can take MRB
      (#3205 / #3265); free seats stay on FR/FIX.
    - free_idle empty (only Grok/paid up): older waiting FR/FIX before a newer MRB
      (#8138).
    - Never yield to an FR that ``fr_is_superseded`` would skip (#254): otherwise
      the superseded FR and its superseding MRB are both skipped into empty.
    """
    if free_idle:
        return False
    task = str((cand or {}).get("task") or "").upper()
    if task != "MRB":
        return False
    # Free-model seats never take MRB; nothing to yield.
    if seat_started_on_free_model(home, nick):
        return False
    cand_age = _row_queue_age_key(cand)
    # FR #8193 / #254: do not yield to an FR this MRB already supersedes (or any
    # FR that offer would skip as superseded) - otherwise both rows are skipped.
    try:
        doc_for_super = {"unaccepted": list(unaccepted or []), "accepted": [], "done": []}
    except Exception:
        doc_for_super = {"unaccepted": list(unaccepted or [])}
    for row in unaccepted or []:
        if not isinstance(row, dict):
            continue
        rt = str(row.get("task") or "").upper()
        if rt not in ("FR", "FIX"):
            continue
        if _row_queue_age_key(row) >= cand_age:
            continue
        if rt == "FR":
            try:
                if fr_is_superseded(
                    doc_for_super,
                    str(row.get("repo") or ""),
                    str(row.get("id") or ""),
                ):
                    continue
            except Exception:
                pass
        # FR #9833 / #9875: do not yield to rows the build-jeeves dispatch lock would skip.
        try:
            import dispatch_lock as _dl

            if _dl.row_blocked_reason(home, row):
                continue
        except Exception:
            pass
        if not _free_seat_can_take_row(home, row, nick, now, live, ledger):
            continue
        # Same machine / self-review gates as the offer path for this seat.
        if row_blocked_for_machine(row, nick):
            continue
        try:
            # FR #9478: pass free= so MRB soft machine-id matches offer_focus_top.
            if review_blocked_for_author(
                row, nick, live, ledger=ledger, free=free_idle
            ):
                continue
        except Exception:
            pass
        return True
    return False


def seat_is_free_fuel(home: Path, nick: str) -> bool:
    """True when this seat must stay on FR/FIX.

    Grok and Cursor are always paid. OpenCode is free only when ``start_model``
    is the Opencode-Free model saved by the Weights form (GET /bob/v1/models).
    """
    return seat_started_on_free_model(home, nick)


def mrb_eligibility_reason(home: Path, nick: str) -> str:
    """One line for the offer log: why this seat may or may not take MRB (FR #7888)."""
    fields = _seat_digest_model_fields(home, nick)
    model = _start_model_from_fields(fields)
    try:
        import worker_start_model as wsm

        klass = wsm.start_model_review_class(model)
    except Exception:
        klass = "unknown"
    shown = model or "missing"
    if len(shown) > 80:
        shown = shown[:80]
    kind = seat_agent_kind(home, nick)
    if _seat_kind_always_paid(kind):
        return f"paid kind {kind}"
    if seat_is_free_fuel(home, nick):
        return f"unpaid opencode model {shown}"
    if klass == "paid":
        return f"paid start_model {shown}"
    return f"mrb-eligible start_model {shown}"


def row_blocked_for_opencode_seat(
    row: dict,
    nick: str,
    home: Path | None = None,
    *,
    kind: str | None = None,
) -> bool:
    """True when this seat must not be offered this MRB/UAT row.

    Grok and Cursor are always paid. OpenCode is blocked only when
    ``start_model`` equals the saved Opencode-Free Weights model.
    Without a digest (``home is None``), kind ``opencode`` still fails safe.
    """
    task = str((row or {}).get("task") or "").upper()
    if task not in ("MRB", "UAT"):
        return False
    if home is not None:
        return seat_is_free_fuel(home, nick)
    k = kind if kind is not None else ""
    return seat_skips_hostile_review(k or "")


def seat_is_out_of_fuel(home: Path, nick: str, now: float | None = None) -> bool:
    """FR #4181: seat marked after GIVEUP out-of-fuel (blocks offers until cleared)."""
    key = _seat_key(nick)
    if not key:
        return False
    try:
        with _lock(home):
            return key in _load_seat_out_of_fuel_unlocked(home, now)
    except (TimeoutError, OSError):
        return False


def note_seat_out_of_fuel(home: Path, nick: str, *, reason: str = "out-of-fuel") -> bool:
    """FR #4181: remember this nick is out of fuel (no giveup-offer / !bored offer)."""
    key = _seat_key(nick)
    if not key:
        return False
    reason_s = str(reason or "out-of-fuel").strip() or "out-of-fuel"
    try:
        import shop_listen as _sl

        reason_s = _sl.truncate_giveup_reason(reason_s) or "out-of-fuel"
    except Exception:  # noqa: BLE001
        reason_s = reason_s[:120]
    try:
        with _lock(home):
            seats = _load_seat_out_of_fuel_unlocked(home)
            seats[key] = {
                "nick": (canonical_worker_nick(nick) or nick or "").strip(),
                "reason": reason_s,
                "ts": _utc_now(),
            }
            _save_seat_out_of_fuel_unlocked(home, seats)
        # FR #8494: paint digest worker_list outside the seat-fuel lock.
        try:
            bobreport.mark_digest_fuel_hold(home, nick, held=True)
        except Exception:
            pass
        return True
    except (TimeoutError, OSError):
        return False


def clear_seat_out_of_fuel(home: Path, nick: str) -> bool:
    """FR #4181: drop the out-of-fuel mark (fresh !bored after fuel returns)."""
    key = _seat_key(nick)
    if not key:
        return False
    try:
        with _lock(home):
            seats = _load_seat_out_of_fuel_unlocked(home)
            if key not in seats:
                return False
            del seats[key]
            _save_seat_out_of_fuel_unlocked(home, seats)
        try:
            bobreport.mark_digest_fuel_hold(home, nick, held=False)
        except Exception:
            pass
        return True
    except (TimeoutError, OSError):
        return False


def worker_list_state(home: Path, nick: str) -> str:
    """Digest worker_list state for nick (empty when absent). FR #8494."""
    parsed = bobreport.parse_seat_nick(nick)
    if not parsed:
        return ""
    mid, _pid = parsed
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return ""
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    ent = machines.get(mid) if isinstance(machines.get(mid), dict) else {}
    if not isinstance(ent, dict):
        return ""
    n = (canonical_worker_nick(nick) or nick or "").strip().lower()
    for row in ent.get("worker_list") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("nick") or "").strip().lower() != n:
            continue
        return str(row.get("state") or "").strip().lower()
    return ""


def _seat_holds_path(home: Path) -> Path:
    return _root(home) / SEAT_HOLDS_NAME


def _load_seat_holds_unlocked(home: Path, now: float | None = None) -> dict:
    import time as _time

    now_f = _time.time() if now is None else float(now)
    path = _seat_holds_path(home)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    holds = doc.get("holds") if isinstance(doc, dict) else None
    if not isinstance(holds, dict):
        return {}
    out: dict = {}
    for k, v in holds.items():
        if not isinstance(v, dict):
            continue
        if _offer_age_s({"offered_ts": v.get("ts")}, now_f) >= SEAT_HOLD_MAX_S:
            continue  # reaper
        out[str(k).strip().lower()] = v
    return out


def _save_seat_holds_unlocked(home: Path, holds: dict) -> None:
    path = _seat_holds_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"v": 1, "holds": holds}, indent=2) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def _note_seat_hold_unlocked(
    home: Path, nick: str, job: dict, *, via: str | None = None
) -> None:
    key = _seat_key(nick)
    if not key or not isinstance(job, dict):
        return
    # Keyword wins when set; else job["via"]; else offer (FR #4415 / FR #4115).
    via_s = str(via if via is not None else (job.get("via") or "offer")).strip().lower() or "offer"
    repo = str(job.get("repo") or "")
    task = str(job.get("task") or "")
    ident = str(job.get("id") or "")
    # FR #9558: one job key → one hold nick. Drop other seats before writing.
    if repo and ident:
        with contextlib.suppress(Exception):
            _clear_job_seat_holds_unlocked(
                home, repo, task, ident, except_nick=nick
            )
    holds = _load_seat_holds_unlocked(home)
    holds[key] = {
        "nick": (canonical_worker_nick(nick) or nick or "").strip(),
        "repo": repo,
        "task": task,
        "id": ident,
        "ts": str(job.get("offered_ts") or _utc_now()),
        # FR #4415: ``offer`` holds void when the queue row is gone; ``ack-missing``
        # (FR #4115) stays busy without a row until DONE/NACK/GIVEUP/QUIT.
        "via": via_s,
    }
    with contextlib.suppress(OSError):
        _save_seat_holds_unlocked(home, holds)
    # FR #4642: an offer after DONE is a real re-offer; ack-missing is not.
    if via_s != "ack-missing":
        with contextlib.suppress(Exception):
            ledger_stamp_seat_job(home, nick, job, "offered")


def note_seat_hold(home: Path, nick: str, job: dict, *, via: str | None = None) -> bool:
    """FR #4089 / FR #4115: remember an open job for this seat (blocks further offers).

    Used when an offer is stamped, and when a seat ACKs a job Jeeves has no queue row
    for (``ACK status=missing``) so the seat is not treated as free after a chair restart.
    ``via``: ``offer`` (default) or ``ack-missing`` (FR #4115 / FR #4415). When omitted,
    ``job["via"]`` is used if present.
    """
    key = _seat_key(nick)
    if not key or not isinstance(job, dict):
        return False
    try:
        with _lock(home):
            _note_seat_hold_unlocked(home, nick, job, via=via)
        return True
    except (TimeoutError, OSError):
        return False


def clear_seat_hold(
    home: Path,
    nick: str,
    *,
    repo: str | None = None,
    task: str | None = None,
    ident: str | None = None,
    clear_pins: bool = False,
) -> bool:
    """FR #4089: drop this seat's remembered offer (and optionally its row pins).

    With repo/task/ident only a matching hold/pin is cleared (task may be omitted to
    match repo+id). Without them every hold/pin for the nick is cleared (QUIT/PART).
    """
    key = _seat_key(nick)
    if not key:
        return False

    def _match(row: dict) -> bool:
        if repo is None and ident is None:
            return True
        if _repo_key(row.get("repo")) != _repo_key(repo or ""):
            return False
        if _norm_row_id(row.get("id")) != _norm_row_id(ident or ""):
            return False
        if task and str(row.get("task") or "").upper() != str(task).upper():
            return False
        return True

    changed = False
    try:
        with _lock(home):
            holds = _load_seat_holds_unlocked(home)
            h = holds.get(key)
            if isinstance(h, dict) and _match(h):
                holds.pop(key, None)
                with contextlib.suppress(OSError):
                    _save_seat_holds_unlocked(home, holds)
                changed = True
            if clear_pins:
                try:
                    doc = _load_queue_unlocked(home)
                except (OSError, json.JSONDecodeError, ValueError):
                    doc = None
                if doc is not None:
                    dirty = False
                    for cand in doc.get("unaccepted") or []:
                        if not isinstance(cand, dict):
                            continue
                        to = str(cand.get("offered_to") or "").strip()
                        if not to or _seat_key(to) != key or not _match(cand):
                            continue
                        for k in ("offered_to", "offered_ts", "offered_channel", "offered_via"):
                            cand.pop(k, None)
                        dirty = True
                    if dirty:
                        with contextlib.suppress(OSError):
                            _write_queue(queue_path(home), doc)
                        changed = True
    except (TimeoutError, OSError):
        return changed
    return changed


def _hold_matches_job(h: dict, repo: str, task: str, ident: str) -> bool:
    if _repo_key(h.get("repo")) != _repo_key(repo or ""):
        return False
    if _norm_row_id(h.get("id")) != _norm_row_id(ident or ""):
        return False
    if task and str(h.get("task") or "").upper() != str(task or "").upper():
        return False
    return True


def _clear_job_seat_holds_unlocked(
    home: Path,
    repo: str,
    task: str,
    ident: str,
    *,
    except_nick: str | None = None,
) -> bool:
    """FR #4260: drop every seat-holds.json entry for this job key (unlocked)."""
    except_key = _seat_key(except_nick) if except_nick else ""
    holds = _load_seat_holds_unlocked(home)
    changed = False
    for nick_key in list(holds.keys()):
        if except_key and nick_key == except_key:
            continue
        h = holds.get(nick_key)
        if isinstance(h, dict) and _hold_matches_job(h, repo, task, ident):
            holds.pop(nick_key, None)
            changed = True
    if changed:
        with contextlib.suppress(OSError):
            _save_seat_holds_unlocked(home, holds)
    return changed


def clear_job_seat_holds(
    home: Path,
    repo: str,
    task: str,
    ident: str,
    *,
    except_nick: str | None = None,
) -> bool:
    """FR #4260: clear all seats' holds for ``repo``+``task``+``id``.

    Used when a row is re-offered to another nick, or when any seat completes
    (DONE/NACK/GIVEUP/ACK) that job so the original no-ACK seat is not stuck
    ``busy (held ...)`` forever.
    """
    if not repo or not ident:
        return False
    try:
        with _lock(home):
            return _clear_job_seat_holds_unlocked(
                home, repo, task or "", ident, except_nick=except_nick
            )
    except (TimeoutError, OSError):
        return False


def _purge_orphan_seat_holds_unlocked(home: Path, doc: dict) -> int:
    """FR #9558: drop offer holds when ACC/offered_to nick is someone else.

    ``ack-missing`` holds stay until DONE/NACK/GIVEUP/QUIT (FR #4115).
    """
    holds = _load_seat_holds_unlocked(home)
    if not holds:
        return 0
    acc_by_job: dict[tuple[str, str, str], str] = {}
    for row in doc.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        repo = str(row.get("repo") or "")
        task = str(row.get("task") or "").upper()
        ident = _norm_row_id(row.get("id"))
        if not repo or not ident:
            continue
        raw = str(
            row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
        ).strip()
        nick = (canonical_worker_nick(raw) or raw).strip().lower()
        if nick:
            acc_by_job[(_repo_key(repo), task, ident)] = nick
    offered_by_job: dict[tuple[str, str, str], str] = {}
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        to = str(row.get("offered_to") or "").strip()
        if not to:
            continue
        repo = str(row.get("repo") or "")
        task = str(row.get("task") or "").upper()
        ident = _norm_row_id(row.get("id"))
        if not repo or not ident:
            continue
        to_c = (canonical_worker_nick(to) or to).strip().lower()
        if to_c:
            offered_by_job[(_repo_key(repo), task, ident)] = to_c
    cleared = 0
    for nick_key, h in list(holds.items()):
        if not isinstance(h, dict):
            continue
        via = str(h.get("via") or "offer").strip().lower() or "offer"
        if via == "ack-missing":
            continue
        repo = str(h.get("repo") or "")
        task = str(h.get("task") or "").upper()
        ident = _norm_row_id(h.get("id"))
        if not repo or not ident:
            continue
        job_key = (_repo_key(repo), task, ident)
        hold_nick = (
            canonical_worker_nick(str(h.get("nick") or nick_key))
            or str(h.get("nick") or nick_key)
        ).strip().lower()
        if not hold_nick:
            continue
        acc_nick = acc_by_job.get(job_key, "")
        offered_nick = offered_by_job.get(job_key, "")
        # ACC moved to another nick, or live offer is on another nick.
        # Keep remembered offer holds when the row still exists without a pin
        # (FR #4089 / #4260); those clear via timeout, DONE, or FR #4415 row-gone.
        if acc_nick and acc_nick != hold_nick:
            holds.pop(nick_key, None)
            cleared += 1
            continue
        if offered_nick and offered_nick != hold_nick:
            holds.pop(nick_key, None)
            cleared += 1
    if cleared:
        with contextlib.suppress(OSError):
            _save_seat_holds_unlocked(home, holds)
    return cleared


def purge_orphan_seat_holds(
    home: Path, *, now: float | None = None, locked_doc: dict | None = None
) -> int:
    """FR #9558: purge offer holds left behind when ACC/offered_to moved.

    Safe to call from ``!stuck`` / ``seat_open_job`` / monitor sweeps.
    """
    if locked_doc is not None:
        return _purge_orphan_seat_holds_unlocked(home, locked_doc)
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return 0
            return _purge_orphan_seat_holds_unlocked(home, doc)
    except (TimeoutError, OSError):
        return 0


def _row_job_finished(row: dict) -> bool:
    """True when a queue row is stamped MERGED/CLOSED (FR #9855)."""
    if not isinstance(row, dict):
        return False
    state = str(row.get("state") or "").strip().lower()
    if state in ("closed", "merged"):
        return True
    result = str(row.get("result") or "").strip().upper()
    if result in ("MERGED", "CLOSED"):
        return True
    if row.get("merged") in (True, "true", "1", 1):
        return True
    return False


def _hold_job_finished(doc: dict, repo: str, task: str, ident: str) -> bool:
    """FR #9855: hold's job is finished when done[] or live row is MERGED/CLOSED."""
    repo_k = _repo_key(repo)
    ident_s = _norm_row_id(ident)
    task_u = str(task or "").upper()
    if not repo_k or not ident_s:
        return False

    def _same(row: dict) -> bool:
        if _repo_key(row.get("repo")) != repo_k:
            return False
        if _norm_row_id(row.get("id")) != ident_s:
            return False
        if task_u and str(row.get("task") or "").upper() not in ("", task_u):
            # Allow FR/PR/UAT alias mismatch only when task omitted on hold.
            rt = str(row.get("task") or "").upper()
            if task_u in ("FR", "PR", "UAT") and rt in ("FR", "PR", "UAT"):
                return True
            if task_u != rt:
                return False
        return True

    for row in list(doc.get("done") or []):
        if isinstance(row, dict) and _same(row):
            # Any done[] match for this job key is finished work.
            return True
    for bucket in (doc.get("unaccepted") or [], doc.get("accepted") or []):
        for row in bucket:
            if isinstance(row, dict) and _same(row) and _row_job_finished(row):
                return True
    return False


def release_stale_via_offer_holds(
    home: Path,
    *,
    now: float | None = None,
    idle: set[str] | None = None,
) -> int:
    """FR #9783 / FR #9855: stuck-sweep clears stale or post-merge via=offer holds.

    FR #9783: after ``offered_to`` ages out (~90s), ``via=offer`` holds can linger
    until ``SEAT_HOLD_MAX_S`` (1h) and leave digest-idle seats ``busy (held …)``
    while stuck-sweep reports ``released=0``. Clear those holds (and matching
    aged pins).

    FR #9855: also clear when report/digest lastSeen is idle with empty
    ``working_on`` *and* the held job is MERGED/CLOSED (or already in done[]),
    even inside the offer-timeout window — post-merge ghost holds that refuse
    ``!assign`` while the digest paints idle. Fresh open offers with a live pin
    stay. ``ack-missing`` stays (FR #4115). Complements
    ``release_sticky_offer_on_bored`` / ``!cleargiveup`` (FR #9633 / #9771).

    Returns the number of seat-holds cleared.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    timeout = float(offer_timeout_s(None))
    idle_l = {
        (canonical_worker_nick(n) or n or "").strip().lower()
        for n in (idle or set())
        if (canonical_worker_nick(n) or n or "").strip()
    }
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                doc = {"unaccepted": [], "accepted": [], "done": []}
            holds = _load_seat_holds_unlocked(home, now_f)
            if not holds:
                return 0
            accepted_nicks = set()
            for row in doc.get("accepted") or []:
                if not isinstance(row, dict):
                    continue
                raw = str(
                    row.get("nick")
                    or row.get("accepted_by")
                    or row.get("offered_to")
                    or ""
                ).strip()
                nick_c = (canonical_worker_nick(raw) or raw).strip().lower()
                if nick_c:
                    accepted_nicks.add(nick_c)
            cleared = 0
            dirty_queue = False
            for nick_key, h in list(holds.items()):
                if not isinstance(h, dict):
                    continue
                via = str(h.get("via") or "offer").strip().lower() or "offer"
                if via == "ack-missing":
                    continue
                hold_nick = (
                    canonical_worker_nick(str(h.get("nick") or nick_key))
                    or str(h.get("nick") or nick_key)
                ).strip().lower()
                if hold_nick and hold_nick in accepted_nicks:
                    continue
                repo_s = str(h.get("repo") or "")
                task_u = str(h.get("task") or "").upper()
                ident_s = _norm_row_id(h.get("id"))
                finished = _hold_job_finished(doc, repo_s, task_u, ident_s)
                age = _offer_age_s({"offered_ts": h.get("ts")}, now_f)
                pin_alive = False
                for cand in doc.get("unaccepted") or []:
                    if not isinstance(cand, dict):
                        continue
                    to = str(cand.get("offered_to") or "").strip()
                    if not to:
                        continue
                    them = (canonical_worker_nick(to) or to).strip().lower()
                    if hold_nick and them != hold_nick:
                        continue
                    if _repo_key(cand.get("repo")) != _repo_key(repo_s):
                        continue
                    if _norm_row_id(cand.get("id")) != ident_s:
                        continue
                    if task_u and str(cand.get("task") or "").upper() != task_u:
                        continue
                    pin_alive = True
                    break
                # FR #9855: idle digest + empty working_on (caller idle set) with
                # pin already gone is a ghost hold even inside offer timeout.
                idle_ghost = bool(
                    hold_nick and hold_nick in idle_l and not pin_alive
                )
                # FR #9855: MERGED/CLOSED (or done[]) clears even inside timeout.
                # FR #9783: otherwise require age past offer timeout.
                if not finished and not idle_ghost and age < timeout:
                    continue
                holds.pop(nick_key, None)
                cleared += 1
                for cand in doc.get("unaccepted") or []:
                    if not isinstance(cand, dict):
                        continue
                    if _repo_key(cand.get("repo")) != _repo_key(repo_s):
                        continue
                    if _norm_row_id(cand.get("id")) != ident_s:
                        continue
                    if task_u and str(cand.get("task") or "").upper() != task_u:
                        continue
                    to = str(cand.get("offered_to") or "").strip()
                    if to:
                        them = (canonical_worker_nick(to) or to).strip().lower()
                        if hold_nick and them != hold_nick:
                            continue
                    elif not finished:
                        continue
                    # Age gate only for the pure stale path; finished clears now.
                    if (
                        not finished
                        and _offer_age_s(cand, now_f) < offer_timeout_s(cand)
                    ):
                        continue
                    clear_sticky_offer_fields(cand)
                    dirty_queue = True
            # FR #9855: strip MERGED/CLOSED offered_to pins, drop matching
            # via=offer holds, and remove finished rows from unaccepted so the
            # idle-offer push cannot re-pin a ghost job (parity with
            # clear_closed_fr_sticky_offers drop).
            keep_unacc: list = []
            for cand in list(doc.get("unaccepted") or []):
                if not isinstance(cand, dict):
                    continue
                if not _row_job_finished(cand):
                    keep_unacc.append(cand)
                    continue
                to = str(cand.get("offered_to") or "").strip()
                repo_c = str(cand.get("repo") or "")
                task_c = str(cand.get("task") or "")
                id_c = str(cand.get("id") or "")
                clear_sticky_offer_fields(cand)
                dirty_queue = True
                for nk, hv in list(holds.items()):
                    if not isinstance(hv, dict):
                        continue
                    via_h = str(hv.get("via") or "offer").strip().lower() or "offer"
                    if via_h == "ack-missing":
                        continue
                    if not _hold_matches_job(hv, repo_c, task_c, id_c):
                        continue
                    hold_n = (
                        canonical_worker_nick(str(hv.get("nick") or nk))
                        or str(hv.get("nick") or nk)
                    ).strip().lower()
                    if hold_n and hold_n in accepted_nicks:
                        continue
                    holds.pop(nk, None)
                    cleared += 1
                # Drop finished row (do not keep for re-offer).
                _log_queue_purge(
                    f"INFO git-claim purge finished-sticky "
                    f"{repo_c}{id_c} task={task_c} had_offer={int(bool(to))} "
                    f"(FR #9855)",
                    log=None,
                )
            if dirty_queue:
                doc["unaccepted"] = keep_unacc
            if cleared:
                with contextlib.suppress(OSError):
                    _save_seat_holds_unlocked(home, holds)
            if dirty_queue:
                with contextlib.suppress(OSError):
                    _write_queue(queue_path(home), doc)
            return cleared
    except (TimeoutError, OSError):
        return 0


def _seat_job_ledger_key(repo: str, task: str, ident: str) -> str:
    return f"{_lkey(repo, ident)}|{str(task or '').upper()}"


def ledger_stamp_seat_job(home: Path, nick: str, job: dict, field: str) -> None:
    """FR #4642: record ``done`` or ``offered`` epoch for this seat and job."""
    me = _canon_ledger_nick(nick)
    if not me or not isinstance(job, dict):
        return
    if field not in ("done", "offered"):
        return
    key = _seat_job_ledger_key(
        str(job.get("repo") or ""), str(job.get("task") or ""), str(job.get("id") or "")
    )
    if key.startswith("#|") or key.startswith("|"):
        return
    stamp = f"{time.time():.6f}"

    def _f(doc: dict) -> None:
        slot = doc.setdefault("seat_job", {}).setdefault(key, {}).setdefault(me, {})
        if not isinstance(slot, dict):
            slot = {}
            doc["seat_job"][key][me] = slot
        slot[field] = stamp

    try:
        _ledger_update(home, _f)
    except OSError:
        pass


def _seat_job_stamp(ledger: dict, nick: str, repo: str, task: str, ident: str, field: str) -> float | None:
    me = _canon_ledger_nick(nick)
    if not me:
        return None
    key = _seat_job_ledger_key(repo, task, ident)
    rec = ((ledger.get("seat_job") or {}).get(key) or {}).get(me) or {}
    if not isinstance(rec, dict):
        return None
    raw = str(rec.get(field) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return _parse_iso_ts(raw)


def seat_done_without_later_offer(
    home: Path, nick: str, repo: str, task: str, ident: str
) -> bool:
    """FR #4642: True when this seat DONE'd the job and it was not re-offered after."""
    led = ledger_load(home)
    done = _seat_job_stamp(led, nick, repo, task, ident, "done")
    if done is None:
        return False
    offered = _seat_job_stamp(led, nick, repo, task, ident, "offered")
    if offered is not None and offered > done:
        return False
    return True


def _sha_from_queue_row(row: dict) -> str:
    """Best-effort head/pass SHA from a queue row (FR #6595)."""
    if not isinstance(row, dict):
        return ""
    for key in ("head_sha", "pass_sha", "sha"):
        raw = str(row.get(key) or "").strip().lower()
        if len(raw) >= 7 and all(c in "0123456789abcdef" for c in raw):
            return raw
    blob = " ".join(
        str(row.get(k) or "") for k in ("url", "line", "body", "title", "result")
    )
    try:
        import mrb_merge_on_green

        parsed = mrb_merge_on_green.parse_pass_sha_from_text(blob) or ""
    except Exception:
        parsed = ""
    return str(parsed).strip().lower()


def _done_mrb_pass_sha_in_doc(
    doc: dict, nick: str, repo: str, ident: str, *, home: Path | None = None
) -> str:
    """PASS SHA for this nick's done[] MRB row, else merge-on-green ledger (FR #6595)."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me or not repo or not ident or not isinstance(doc, dict):
        return ""
    want = _norm_row_id(ident)
    repo_c = canonical_queue_repo(repo)
    for r in doc.get("done") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("task") or "").upper() != "MRB":
            continue
        if canonical_queue_repo(str(r.get("repo") or "")) != repo_c:
            continue
        if _norm_row_id(str(r.get("id") or "")) != want:
            continue
        if str(r.get("result") or "").strip().upper() != "PASS":
            continue
        who = (
            r.get("done_by")
            or r.get("nick")
            or r.get("accepted_by")
            or r.get("offered_to")
            or ""
        )
        who_c = (canonical_worker_nick(str(who)) or str(who)).strip().lower()
        if who_c and who_c == me:
            sha = _sha_from_queue_row(r)
            if sha:
                return sha
            break
    if home is not None:
        try:
            num = int(str(ident).lstrip("#"))
        except (TypeError, ValueError):
            num = 0
        if num:
            try:
                return str(_merge_on_green_pass_sha(home, repo, num) or "").strip().lower()
            except Exception:
                return ""
    return ""


def release_duplicate_done_hold(home: Path, nick: str) -> str:
    """FR #4642 / #4661 / #6565 / #6595: drop an ack-missing/offer hold the seat already finished.

    Returns `TASK repo#id` when a hold was cleared, else `''`.
    A later re-offer (offered stamp after done) keeps the hold.
    Finished when: seat ledger done stamp, or queue `done[]` MRB PASS by this
    nick (FR #6565 - no live GitHub required), or a PASS board on the held MRB pull.
    FR #6595: when clearing, prune unaccepted MRB phantoms only when head SHA is
    missing or matches the PASS SHA; keep a newer-head re-review row.
    """
    key = _seat_key(nick)
    if not key:
        return ""
    try:
        with _lock(home):
            holds = _load_seat_holds_unlocked(home)
            h = holds.get(key)
    except (TimeoutError, OSError):
        return ""
    if not isinstance(h, dict):
        return ""
    repo = str(h.get("repo") or "")
    task = str(h.get("task") or "")
    ident = str(h.get("id") or "")
    if not repo or not ident:
        return ""
    finished = seat_done_without_later_offer(home, nick, repo, task, ident)
    if not finished and str(task or "").upper() == "MRB":
        # FR #4661 / #6565: queue done[] MRB PASS is enough when there is no ledger
        # done stamp and no live GitHub. Only for MRB holds (never clear a FIX hold
        # because an earlier MRB PASS exists for the same pull). Honour FR #4642:
        # when ledger has offered > done, keep the hold (do not override).
        led = ledger_load(home)
        done_ts = _seat_job_stamp(led, nick, repo, task, ident, "done")
        offered_ts = _seat_job_stamp(led, nick, repo, task, ident, "offered")
        later_offer = (
            done_ts is not None
            and offered_ts is not None
            and offered_ts > done_ts
        )
        if not later_offer and nick_done_mrb_pass(home, nick, repo, ident):
            finished = True
    if not finished:
        row = {"repo": repo, "task": task, "id": ident, "url": ""}
        finished = bool(_lost_done_github_result(row))
    if not finished:
        return ""
    clear_seat_hold(home, nick, repo=repo, task=task, ident=ident)
    with contextlib.suppress(Exception):
        bobreport.clear_seat_doing(
            home, nick, only_if_work_contains=str(ident).lstrip("#")
        )
    # FR #4661: drop the phantom unaccepted MRB so LOST_ACK/bored cannot re-offer it.
    if str(task or "").upper() == "MRB":
        try:
            with _lock(home):
                doc = _load_queue_unlocked(home)
                if not _nick_done_mrb_pass_in_doc(doc, nick, repo, ident):
                    pass
                else:
                    # FR #6595: prune same-SHA / unknown-SHA phantoms only; keep a
                    # newer-head unaccepted MRB so tip-push re-review is not deleted.
                    want = _norm_row_id(ident)
                    repo_c = canonical_queue_repo(repo)
                    pass_sha = _done_mrb_pass_sha_in_doc(
                        doc, nick, repo, ident, home=home
                    )
                    kept = []
                    import mrb_merge_on_green as _mog_sha

                    for r in doc.get("unaccepted") or []:
                        if not isinstance(r, dict):
                            continue
                        if (
                            str(r.get("task") or "").upper() == "MRB"
                            and canonical_queue_repo(str(r.get("repo") or "")) == repo_c
                            and _norm_row_id(str(r.get("id") or "")) == want
                        ):
                            row_sha = _sha_from_queue_row(r)
                            if (
                                pass_sha
                                and row_sha
                                and not _mog_sha.shas_match(pass_sha, row_sha)
                            ):
                                kept.append(r)
                            continue
                        kept.append(r)
                    if len(kept) != len(doc.get("unaccepted") or []):
                        doc["unaccepted"] = kept
                        _write_queue(queue_path(home), doc)
        except Exception:
            pass
    return f"{task} {repo}{_norm_row_id(ident)}".strip()


def _is_lost_done_reoffer_to(row: dict, nick: str) -> bool:
    """FR #4564: this seat held the row when a lost DONE was requeued."""
    if not isinstance(row, dict):
        return False
    raw = str(row.get("prior_holder") or "").strip()
    if not raw:
        return False
    holder = (canonical_worker_nick(raw) or raw).strip().lower()
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    return bool(holder) and holder == me


def _lost_done_github_result(row: dict) -> str | None:
    """FR #4564: a PASS board already on the PR means the DONE landed. None if unknown."""
    try:
        import mrb_merge_gate

        repo = str(row.get("repo") or "").strip()
        num = str(row.get("id") or "").lstrip("#").strip()
        if not repo or not num:
            return None
        given = str(row.get("url") or "").strip()
        task = str(row.get("task") or "").upper()
        # FR #7657: the pull URL fallback must not make every FR/FIX id look like a
        # pull. A live MRB PASS on that number (issue id reused as a pull) cleared
        # ack-missing holds and let !bored through (test_ack_missing_hold_still_blocks).
        if task != "MRB" and "/pull/" not in given:
            return None
        url = given or f"https://github.com/{repo}/pull/{num}"
        comments = mrb_merge_gate.fetch_issue_comments(repo, num)
        for c in comments or []:
            body = mrb_merge_gate._body(c)
            if mrb_merge_gate.MRB_PASS_BOARD_RE.search(body) or re.search(
                r"(?i)\bMRB\s+PASS\s*@", body
            ):
                return url
        return None
    except Exception:  # noqa: BLE001
        return None


def _seat_open_job_in(home: Path, doc: dict, nick: str, now: float, live: set | None = None) -> str:
    """Unlocked core of ``seat_open_job`` (caller holds ``_lock`` and loaded ``doc``)."""
    key = _seat_key(nick)
    if not key:
        return ""
    # FR #9402 / #9406: held FR sticky offered_to must not busy the seat.
    clear_held_fr_sticky_offers(doc)
    # FR #9835: stamped CLOSED FR sticky offered_to / holds must not busy the seat.
    clear_closed_fr_sticky_offers(doc, home)
    for row in doc.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        raw = str(row.get("nick") or row.get("accepted_by") or row.get("offered_to") or "").strip()
        if raw and _seat_key(raw) == key:
            # FR #4454: a false LOST_ACK_RESTART with no seat-reported work is not busy.
            if (
                str(row.get("reconcile") or "") == "LOST_ACK_RESTART"
                and not _seat_reports_row(home, nick, row)
            ):
                continue
            return f"accepted {row.get('task')} {row.get('repo')}{_norm_row_id(row.get('id'))}"
    sticky_maxed: list[dict] = []
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        to = str(row.get("offered_to") or "").strip()
        if to and _seat_key(to) == key:
            # FR #4564: an un-ACKed re-offer of the row this seat already finished
            # must not nak !bored as busy.
            if _is_lost_done_reoffer_to(row, nick):
                continue
            try:
                oc = int(row.get("offered_count") or 0)
            except (TypeError, ValueError):
                oc = 0
            if oc >= OFFER_STICKY_MAX:
                # FR #2309 escape: offered OFFER_STICKY_MAX times without ACK -> the
                # sticky-clear path frees it (and this seat) instead of blocking forever.
                sticky_maxed.append(row)
                continue
            # No time window: an offer the seat has not answered still counts.
            return f"offered {row.get('task')} {row.get('repo')}{_norm_row_id(row.get('id'))}"
    holds = _load_seat_holds_unlocked(home, now)
    h = holds.get(key)
    if isinstance(h, dict) and any(
        _same(r, str(h.get("repo") or ""), str(h.get("task") or ""), str(h.get("id") or ""))
        for r in sticky_maxed
    ):
        h = None
    if isinstance(h, dict):
        # FR #4564: a hold for the lost-DONE re-offer is not busy.
        h_repo = str(h.get("repo") or "")
        h_task = str(h.get("task") or "")
        h_id = str(h.get("id") or "")
        for row in doc.get("unaccepted") or []:
            if not isinstance(row, dict) or not _same(row, h_repo, h_task, h_id):
                continue
            if _is_lost_done_reoffer_to(row, nick):
                holds.pop(key, None)
                with contextlib.suppress(OSError):
                    _save_seat_holds_unlocked(home, holds)
                h = None
                break
    if isinstance(h, dict):
        # FR #4260: hold is void when the same job is now offered/accepted by another seat.
        h_repo = str(h.get("repo") or "")
        h_task = str(h.get("task") or "")
        h_id = str(h.get("id") or "")
        for row in doc.get("unaccepted") or []:
            if not isinstance(row, dict):
                continue
            if not _same(row, h_repo, h_task, h_id):
                continue
            to = str(row.get("offered_to") or "").strip()
            if to and _seat_key(to) != key:
                holds.pop(key, None)
                with contextlib.suppress(OSError):
                    _save_seat_holds_unlocked(home, holds)
                h = None
                break
        if isinstance(h, dict):
            for row in doc.get("accepted") or []:
                if not isinstance(row, dict):
                    continue
                if not _same(row, h_repo, h_task, h_id):
                    continue
                raw = str(
                    row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
                ).strip()
                if raw and _seat_key(raw) != key:
                    holds.pop(key, None)
                    with contextlib.suppress(OSError):
                        _save_seat_holds_unlocked(home, holds)
                    h = None
                    break
        # FR #4415: offer-via hold is void when the queue row is gone (closed/merged
        # drop). ack-missing holds (FR #4115) stay until DONE/NACK/GIVEUP/QUIT.
        if isinstance(h, dict):
            via = str(h.get("via") or "offer").strip().lower() or "offer"
            if via != "ack-missing":
                present = False
                for bucket in (doc.get("unaccepted") or [], doc.get("accepted") or []):
                    for row in bucket:
                        if isinstance(row, dict) and _same(row, h_repo, h_task, h_id):
                            present = True
                            break
                    if present:
                        break
                if not present:
                    holds.pop(key, None)
                    with contextlib.suppress(OSError):
                        _save_seat_holds_unlocked(home, holds)
                    h = None
    if isinstance(h, dict):
        live_l = {_seat_key(n) for n in (live or set()) if _seat_key(n)}
        if live_l and key not in live_l:
            return ""  # seat left the shop: hold is void
        return f"held {h.get('task')} {h.get('repo')}{_norm_row_id(h.get('id'))}"
    return ""


def purge_stale_offered_pins(
    home: Path,
    *,
    now: float | None = None,
    live: set[str] | None = None,
    locked_doc: dict | None = None,
    clear_aged_live_holds: bool = True,
) -> int:
    """FR #9402: clear aged/dead ``offered_to`` pins (same rules as ``offer_focus_top``).

    ``!assign`` used ``seat_open_job`` without this purge, so an idle seat past
    ``OFFER_TIMEOUT_S`` still refused busy. Returns how many pins were cleared.
    When ``locked_doc`` is provided the caller already holds ``_lock``.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    try:
        live_set = set(live) if live is not None else live_seat_nicks(home, now=now_f)
    except Exception:  # noqa: BLE001
        live_set = set()
    live_l = {
        (canonical_worker_nick(n) or n or "").strip().lower()
        for n in live_set
        if (canonical_worker_nick(n) or n or "").strip()
    }

    def _purge(doc: dict) -> int:
        cleared = 0
        for cand in doc.get("unaccepted") or []:
            if not isinstance(cand, dict):
                continue
            to = str(cand.get("offered_to") or "").strip()
            if not to:
                continue
            to_c = (canonical_worker_nick(to) or to).strip().lower()
            dead_pin = bool(to_c) and bool(live_l) and to_c not in live_l
            try:
                age = now_f - datetime.fromisoformat(
                    str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                age = offer_timeout_s(cand) + 1
            if (
                not dead_pin
                and age >= offer_timeout_s(cand)
                and to_c in live_l
                and seat_submit_verify_in_flight(home, to)
            ):
                continue
            if dead_pin or age >= offer_timeout_s(cand):
                if not dead_pin:
                    with contextlib.suppress(Exception):
                        note_unanswered_offer(
                            cand, to, now_f, offer_timeout_reason(home, to)
                        )
                else:
                    with contextlib.suppress(Exception):
                        note_offer_outcome(cand, to, "dead-pin", "seat-not-live")
                # FR #9403 / #9565 / #9614: drop seat-holds with the pin (parity with
                # offer_focus_top). Dead pins always clear holds. seat_open_job passes
                # clear_aged_live_holds=True so aged-but-live holds do not leave idle
                # seats busy after offer-timeout:idle-no-ack.
                if clear_aged_live_holds or dead_pin:
                    with contextlib.suppress(Exception):
                        _clear_job_seat_holds_unlocked(
                            home,
                            str(cand.get("repo") or ""),
                            str(cand.get("task") or ""),
                            str(cand.get("id") or ""),
                        )
                cand.pop("offered_to", None)
                cand.pop("offered_ts", None)
                cand.pop("offered_channel", None)
                cand.pop("offered_via", None)
                cleared += 1
        return cleared

    if locked_doc is not None:
        return _purge(locked_doc)
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return 0
            n = _purge(doc)
            if n:
                with contextlib.suppress(OSError):
                    _write_queue(queue_path(home), doc)
            return n
    except (TimeoutError, OSError):
        return 0


def seat_open_job(home: Path, nick: str, now: float | None = None) -> str:
    """FR #4089: describe the seat's open job ('' when free). Accepted row, any-age
    offered_to pin, or a remembered offer in seat-holds.json all count."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    try:
        live = live_seat_nicks(home)
    except Exception:  # noqa: BLE001
        live = set()
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return ""
            # FR #9402 / #9403 / #9565 / #9614: drop aged/dead pins AND their
            # seat-holds before the any-age busy check so !assign matches
            # offer_focus_top timeout behaviour. clear_aged_live_holds must be
            # True here - False left idle seats reporting held FR after purge.
            before_n = len(doc.get("unaccepted") or [])
            before_offers = [
                str(r.get("offered_to") or "")
                for r in (doc.get("unaccepted") or [])
                if isinstance(r, dict)
            ]
            cleared = purge_stale_offered_pins(
                home,
                now=now_f,
                live=live,
                locked_doc=doc,
                clear_aged_live_holds=True,
            )
            # FR #9558: drop offer holds left when ACC/offered_to moved to another nick.
            with contextlib.suppress(Exception):
                purge_orphan_seat_holds(home, now=now_f, locked_doc=doc)
            out = _seat_open_job_in(home, doc, nick, now_f, live)
            after_offers = [
                str(r.get("offered_to") or "")
                for r in (doc.get("unaccepted") or [])
                if isinstance(r, dict)
            ]
            if (
                cleared
                or len(doc.get("unaccepted") or []) != before_n
                or before_offers != after_offers
            ):
                with contextlib.suppress(OSError):
                    _write_queue(queue_path(home), doc)
            return out
    except (TimeoutError, OSError):
        return ""


def offer_focus_top(
    home: Path,
    nick: str,
    channel: str,
    *,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
    fetch_issue=None,
    offered_via: str | None = None,
) -> tuple[str, dict | None]:
    """Focus-ordered offer for !bored (#39 gap 2). Stamps offered_to (ACK accepts it, FR #207).

    "ok" job | "empty" (nothing queued / nothing eligible under strict focus or ignore) | "error".
    A row offered to another seat within OFFER_TIMEOUT_S is skipped.
    FR #3192: a seat that still holds a live ``offered_to`` is not rebroadcast a second job
    (``bored_gate`` busy + early empty return); sticky-max clear (FR #2309) still runs so
    another seat can take a dead pin after ``OFFER_STICKY_MAX`` no-ACK attempts.
    ``pr_exists`` (optional) skips MRB rows whose pull URL 404s (FR #595 / #247).
    ``issue_open`` (optional) purges/skips FR rows whose issue is CLOSED (FR #2340).
    ``fetch_issue`` (optional) BOB-D6 / FR #8810: hydrate empty FR ``body`` before Depends-on
    (test seam; default ``fetch_github_issue_dict`` via ``ensure_fr_queue_body``).

    FR #3188: bulk purge uses stamped/structural checks only (no per-row GitHub fan-out
    on the IRC ``!bored`` path). Live checkers are budgeted to at most one call while
    picking the offered row; unknown lookups never purge.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    # FR #4181: never stamp an offer onto a seat still marked out-of-fuel.
    if seat_is_out_of_fuel(home, nick, now_f):
        return "empty", None
    if seat_fuel_pause_reason(home, nick, now_f):
        return "empty", None
    live = live_seat_nicks(home)
    free = free_seat_nicks(home, live)
    # FR #5163: unlock cross give-up / queue recycleseat for author-only MRB deadlock
    # before the locked offer pick (same !bored can then stamp an offer).
    with contextlib.suppress(Exception):
        heal_mrb_reviewer_deadlock(home, idle=free, live=live, now=now_f)
    me_raw = (nick or "").strip()
    me = (canonical_worker_nick(me_raw) or me_raw).strip()
    ledger = ledger_load(home)
    # FR #7926: computed before the queue lock so digest reads do not nest it.
    free_idle = idle_free_model_nicks(home, now=now_f, live=live)
    # FR #3205 / #3212 / #6581: when an on-disk precompute fingerprint matches the queue,
    # !bored uses zero GitHub calls (local eligibility only). Otherwise use
    # BORED_GITHUB_CALL_BUDGET (production 0 - local-state only; FR #3188's budget-of-one
    # is retired). Resync / webhook / explicit rebuild_offer_precompute refresh the file
    # off the IRC path.
    try:
        with _lock(home):
            try:
                _peek = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                _peek = None
        _rows_peek = list((_peek or {}).get("unaccepted") or []) if _peek else []
    except (TimeoutError, OSError):
        _rows_peek = []
    precompute_ok = offer_precompute_fresh(home, _rows_peek)
    bored_budget = 0 if precompute_ok else BORED_GITHUB_CALL_BUDGET
    budget = _GithubCallBudget(bored_budget)
    # FR #8754: Depends-on live OPEN check is unbudgeted - prereqs are often OPEN on
    # GitHub while absent from the local FR queue; zero !bored budget must not skip them.
    depends_issue_open = depends_issue_open_checker(issue_open)
    # FR #9418: unbudgeted issue dict fetch for G1 when digests are not queued.
    depends_issue_fetch = depends_issue_fetch_checker(fetch_issue)
    # FR #9411: CLOSED FR live check is also unbudgeted - BORED_GITHUB_CALL_BUDGET=0
    # otherwise never fires and CLOSED ops trackers stay offerable (class of #9376).
    fr_closed_issue_open = depends_issue_open_checker(issue_open)
    pr_exists = _budgeted_github(pr_exists, budget, "pr_exists")
    is_pull = _budgeted_github(is_pull, budget, "is_pull")
    issue_open = _budgeted_github(issue_open, budget, "issue_open")
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            # FR #3867: promote unaccepted rows a digest seat is already working (lost ACK
            # across chair restart) before purging offered_to or picking a new offer.
            purged = bool(_reconcile_lost_ack_unlocked(home, doc))
            # FR #9402 / #9406: drop hold-gated FR sticky offers before pick.
            if clear_held_fr_sticky_offers(doc):
                purged = True
            # FR #9835: drop stamped CLOSED FR sticky offers/holds before pick.
            if clear_closed_fr_sticky_offers(doc, home):
                purged = True
            # FR #740 / #738: drop MERGED/CLOSED/already-DONE MRB before picking.
            # Also free seats stuck on accepted MERGED MRBs (#1171/#1236 class).
            # FR #3188: no live pr_exists fan-out here - stamped/ledger only.
            purged = bool(_purge_dead_mrb_unaccepted(doc, pr_exists=None, home=home)) or purged
            purged = bool(_purge_dead_mrb_accepted(doc, pr_exists=None, home=home)) or purged
            # FR #4682: stamped-closed FIX only in the zero-budget path; live check below.
            purged = bool(_purge_dead_fix_unaccepted(doc, pr_exists=None)) or purged
            purged = bool(_purge_dead_fix_accepted(doc, pr_exists=None, home=home)) or purged
            purged = bool(_purge_fr_that_are_pulls(doc)) or purged
            # FR #2340 / #3188: stamped CLOSED only at bulk; live check is budgeted in _eligible.
            purged = bool(_purge_closed_fr_unaccepted(doc, home=home)) or purged
            # FR #2361: accepted list is small (busy seats) - live check OK under the shared budget
            # unless FR #3205 precompute says zero GitHub on this !bored.
            if bored_budget > 0:
                purged = bool(
                    _purge_closed_fr_accepted(doc, issue_open=issue_open, home=home)
                ) or purged
                # FR #4682: live-check accepted/unaccepted FIX under the same budget.
                if pr_exists is not None:
                    purged = bool(
                        _purge_dead_fix_unaccepted(doc, pr_exists=pr_exists)
                    ) or purged
                    purged = bool(
                        _purge_dead_fix_accepted(
                            doc, pr_exists=pr_exists, home=home
                        )
                    ) or purged
            else:
                purged = bool(_purge_closed_fr_accepted(doc, issue_open=None, home=home)) or purged
            # FR #1508: free seats stuck doing MERGED MRB even when ACC row is gone.
            # Budgeted: at most one live call shared with the offer pick (skipped when budget 0).
            if bored_budget > 0 and pr_exists is not None:
                with contextlib.suppress(Exception):
                    if clear_orphan_digest_mrb_doing(home, pr_exists=pr_exists):
                        purged = True
            # Drop stale offered_to so a dead/non-ACKing seat cannot pin the row forever.
            # FR #2899: also clear when offered_to nick is not live (author-seat recycle).
            # FR #2927: only treat as dead-pin when the live set is non-empty. An empty
            # digest (or tests without workers) must keep one-offer-per-job sticky until
            # OFFER_TIMEOUT_S - otherwise every pin looks dead and two seats get #1.
            live_l = {
                (canonical_worker_nick(n) or n or "").strip().lower()
                for n in live
                if (canonical_worker_nick(n) or n or "").strip()
            }
            for cand in doc.get("unaccepted") or []:
                if not isinstance(cand, dict):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                if not to:
                    continue
                to_c = (canonical_worker_nick(to) or to).strip().lower()
                dead_pin = bool(to_c) and bool(live_l) and to_c not in live_l
                try:
                    age = now_f - datetime.fromisoformat(
                        str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    age = offer_timeout_s(cand) + 1
                if (
                    not dead_pin
                    and age >= offer_timeout_s(cand)
                    and to_c in live_l
                    and seat_submit_verify_in_flight(home, to)
                ):
                    # FR #8442: grok paste / submit-verify is still in flight.
                    continue
                if dead_pin or age >= offer_timeout_s(cand):
                    # FR #7966: a silent seat is a recorded refusal, not a fresh offer.
                    if not dead_pin:
                        note_unanswered_offer(cand, to, now_f, offer_timeout_reason(home, to))
                    else:
                        note_offer_outcome(cand, to, "dead-pin", "seat-not-live")
                    with contextlib.suppress(Exception):
                        _clear_job_seat_holds_unlocked(
                            home,
                            str(cand.get("repo") or ""),
                            str(cand.get("task") or ""),
                            str(cand.get("id") or ""),
                        )
                    cand.pop("offered_to", None)
                    cand.pop("offered_ts", None)
                    cand.pop("offered_channel", None)
                    cand.pop("offered_via", None)
                    purged = True
                    # FR #7966: observing the timeout clears the seat hold. The seat
                    # is no longer blocked, and the row can go to this caller or
                    # another seat (FR #4260). Three silences still refuse the seat.

            # FR #4089 (supersedes the FR #3192 time-boxed holding_live check): a seat with
            # an accepted job, any offer pinned to it (no age window) or a remembered offer
            # in seat-holds.json is never offered a second job.
            open_job = _seat_open_job_in(home, doc, me, now_f, live)
            if open_job:
                if purged:
                    try:
                        _write_queue(queue_path(home), doc)
                    except OSError:
                        return "error", None
                return "empty", None

            def _same_seat(a: str, b: str) -> bool:
                ca = (canonical_worker_nick(a) or a or "").strip().lower()
                cb = (canonical_worker_nick(b) or b or "").strip().lower()
                return bool(ca) and ca == cb

            import focus_ignore  # lazy: avoid import cycle; needed before _eligible (FR #6208)

            # BOB-D3 / FR #8807: build once per locked !bored pass (zero-call local keys).
            open_dep_keys = open_fr_issue_keys(doc)

            def _eligible(cand: dict) -> dict | None:
                nonlocal purged
                # FR #6208: belt-and-braces - never offer an ignored repo (incl. fallback walk).
                if focus_ignore.is_ignored(home, str(cand.get("repo") or "")):
                    if _drop_unaccepted_row(doc, cand, kind="ignored", reason="repo-ignored"):
                        purged = True
                    return None
                # FR #9875 / #9833: dispatch-lock belt-and-braces (even if sort filter missed).
                try:
                    import dispatch_lock as _dl

                    if _dl.row_blocked_reason(home, cand):
                        return None
                except Exception:
                    pass
                if row_needs_human(cand, me) or row_on_cooldown(cand, now_f, me, live=live):
                    return None  # FR #180: per-seat GIVEUP cooldown / needs-human
                if row_awaits_mrb1(cand):
                    return None  # legacy hook; row_awaits_mrb1 always False (op 2026-10-04)
                skip_why = row_skip_fr_reason(cand)
                if skip_why:
                    # FR #9411: ops-monitor trackers leave the unaccepted queue (not sticky).
                    if skip_why in ("ops_monitor_tracker", "tipform_restore_escalate"):
                        if _drop_unaccepted_row(
                            doc, cand, kind="ops-monitor", reason=skip_why
                        ):
                            purged = True
                    return None
                # BOB-G3 / FR #9108: Digest gate records stay queued (even when held);
                # never offer as work. Held digests must remain for Depends-on go-gate.
                if digest_issue_reason(cand):
                    return None
                # FR #4009 / #8741: hold or park-only FR - skip offer; purge so it leaves unaccepted.
                # FR #9402: pass home so offered_to seat-holds clear with the drop.
                skip_why = row_fr_skip_offer_reason(cand)
                if skip_why:
                    kind = "fr-park-only" if skip_why.startswith("park-only") else "fr-hold"
                    if _drop_unaccepted_row(
                        doc, cand, kind=kind, reason=skip_why, home=home
                    ):
                        purged = True
                    return None
                # BOB-D6 / FR #8810: empty queue body → fetch issue body before Depends-on parse
                # (fail-when: silent offer with empty body). Persist stamp when filled.
                if _canon_task(cand) == "FR":
                    _body_before = str(cand.get("body") or "")
                    ensure_fr_queue_body(cand, fetch_issue=fetch_issue)
                    if str(cand.get("body") or "") != _body_before:
                        purged = True
                # FR #9455 bob_g1_shared_gate: one Depends-on gate (offer = assign = stuck).
                if depends_gate_reason(
                    cand,
                    doc,
                    open_keys=open_dep_keys,
                    issue_open=depends_issue_open,
                    issue_fetch=depends_issue_fetch,
                ):
                    return None
                if repo_archived_for_queue(str(cand.get("repo") or "")):
                    return None
                if expire_offer_timeout_refusals(cand, now_f):
                    # Cap and clear both mutate the live row. A cap does not
                    # offer, so the empty return must still persist the stamp.
                    purged = True
                if row_machine_mismatch(cand, me) or row_gave_up_by(cand, me, live=live):
                    return None
                # FR #8008: agent-class exclusion after repeated hard-ceiling kills.
                if row_blocked_for_giveup_agent_kind(cand, seat_agent_kind(home, me)):
                    return None
                # FR #7966: three unanswered offers to this seat stop the re-offer loop.
                if seat_offer_refused(cand, me):
                    return None
                # FR #8264: do not hand a self-review stall FR to the idle author.
                if seat_blocked_for_self_review_stall(cand, me, doc):
                    return None
                # FR #8017: pre-ACK deterministic NACK cools this seat for the row.
                if seat_on_deterministic_nack_cooldown(cand, me, now_f):
                    return None
                # FR #8153: no-clone NACK blocks every job for that repo on this seat
                # until JOIN / hello re-announce clears the ledger stamp.
                if seat_blocked_for_no_clone_repo(home, me, str(cand.get("repo") or "")):
                    return None
                # FR #7084: skip model-mismatch seats; skip when actual tier is below job need.
                if not _seat_model_allows_row(home, me, cand):
                    return None
                # FR #4718: do not hand the same MRB head back to the seat that FAILed it.
                if mrb_fail_same_head_for_seat(cand, me):
                    return None
                if _canon_task(cand) == "MRB" and _nick_done_mrb_pass_in_doc(
                    doc, me, str(cand.get("repo") or ""), str(cand.get("id") or "")
                ):
                    return None  # FR #4661: same seat does not re-review after PASS
                if ledger_blocks(ledger, cand, me, live):
                    if is_repo_uat(cand):
                        with contextlib.suppress(Exception):
                            if maybe_escalate_repo_uat_all_self_uat(
                                home,
                                cand,
                                live=live,
                                ledger=ledger,
                                locked_doc=doc,
                            ):
                                purged = True
                    return None
                if str(cand.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc, str(cand.get("repo") or ""), str(cand.get("id") or "")
                ):
                    return None
                # FR #9411 / #2340: unbudgeted live open-check; definitive closed -> purge.
                # (Budgeted issue_open is a no-op when BORED_GITHUB_CALL_BUDGET=0.)
                if _canon_task(cand) == "FR" and _fr_issue_is_closed(
                    cand, issue_open=fr_closed_issue_open
                ):
                    repo = str(cand.get("repo") or "").strip()
                    num = str(cand.get("id") or "").strip().lstrip("#")
                    _log_queue_purge(
                        f"INFO git-claim purge closed-fr {repo}#{num} "
                        f"reason=issue_open=False"
                    )
                    if _drop_unaccepted_row(
                        doc, cand, kind="closed-fr", reason="issue_open=False"
                    ):
                        purged = True
                    return None
                # FR #1313 / MRB #3207: definitive is_pull=True on this FR row -> purge it only.
                if _canon_task(cand) == "FR" and _live_verdict(is_pull, cand) is True:
                    if _drop_unaccepted_row(doc, cand, kind="fr-is-pull", reason="is_pull=True"):
                        purged = True
                    return None
                if not fr_row_offerable(
                    cand,
                    is_pull=is_pull,
                    pr_exists=pr_exists,
                    issue_open=fr_closed_issue_open,
                ):
                    return None
                if str(cand.get("task") or "").upper() == "UAT" and not is_repo_uat(cand):
                    return None
                # FR #9382: CAST IRON - no UAT when the repo has no release to build.
                if uat_no_release_to_build_reason(cand, home=home):
                    if _drop_unaccepted_row(
                        doc, cand, kind="uat-no-release", reason="no-release-to-build"
                    ):
                        purged = True
                    return None
                # FR #740 / MRB #3207: one shared lookup per MRB row; definitive not-open
                # purges this row only; unknown (budget / 403 / 5xx) still offers.
                if _canon_task(cand) == "MRB" and _live_verdict(pr_exists, cand) is False:
                    if _drop_unaccepted_row(doc, cand, kind="dead-mrb", reason="pr_exists=False"):
                        purged = True
                    return None
                if mrb_already_done(doc, cand, home=home, pr_exists=pr_exists):
                    return None
                if not mrb_row_offerable(cand, pr_exists=pr_exists):
                    return None
                # FR #5317: optional CodeRabbit wait (off by default; timeout still offers).
                try:
                    import fuel_chain

                    def _cr_lookup(repo: str, num: str, _row=cand):
                        # FR #5865: state dict so silence->absent and failed stamp.
                        return fuel_chain.lookup_coderabbit_state(
                            repo, num, str(_row.get("head_sha") or "")
                        )

                    cr_check = _budgeted_github(_cr_lookup, budget, "coderabbit")
                    if fuel_chain.apply_mrb_coderabbit_gate(
                        cand, now_f, lookup=cr_check
                    ):
                        # FR #6211: row-specific hold in chair log (shop stays "nothing queued").
                        with contextlib.suppress(Exception):
                            _log_queue_purge(
                                "INFO "
                                + fuel_chain.coderabbit_hold_message(cand, now_f)
                                + " via=bored"
                            )
                        purged = True
                        return None
                except Exception:
                    pass
                to = str(cand.get("offered_to") or "").strip()
                if to and not _same_seat(to, me):
                    try:
                        age = now_f - datetime.fromisoformat(
                            str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                        ).timestamp()
                    except ValueError:
                        age = offer_timeout_s(cand) + 1
                    if age < offer_timeout_s(cand):
                        return None
                skips = {
                    (canonical_worker_nick(x) or str(x)).strip().lower()
                    for x in (cand.get("sticky_skip_seats") or [])
                    if str(x).strip()
                }
                if me.lower() in skips:
                    return None
                # FR #4564: a LOST_DONE_RESTART requeue is not offered back to the seat
                # that held it when the chair restarted.
                if _is_lost_done_reoffer_to(cand, me):
                    return None
                # FR #2309: sticky same-nick pin past OFFER_STICKY_MAX -> clear for other seats.
                if to and _same_seat(to, me):
                    try:
                        oc = int(cand.get("offered_count") or 0)
                    except (TypeError, ValueError):
                        oc = 0
                    if oc >= OFFER_STICKY_MAX:
                        cand.pop("offered_to", None)
                        cand.pop("offered_ts", None)
                        cand.pop("offered_channel", None)
                        skip_list = [
                            str(x).strip()
                            for x in (cand.get("sticky_skip_seats") or [])
                            if str(x).strip()
                        ]
                        if me not in skip_list and me.lower() not in {
                            (canonical_worker_nick(x) or x).strip().lower() for x in skip_list
                        }:
                            skip_list.append(me)
                        cand["sticky_skip_seats"] = skip_list
                        purged = True
                        return None
                cand_eff = enrich_review_author_fields(doc, cand)
                if review_blocked_for_author(cand_eff, me, live, ledger=ledger, free=free):
                    if str(cand.get("task") or "").upper() in ("MRB", "UAT"):
                        with contextlib.suppress(Exception):
                            _log_queue_purge(
                                "INFO mrb-eligibility skip"
                                f" seat={me} task={str(cand.get('task') or '').upper()}"
                                f" id={cand.get('id') or ''} reason=author"
                            )
                    if is_repo_uat(cand):
                        with contextlib.suppress(Exception):
                            if maybe_escalate_repo_uat_all_self_uat(
                                home,
                                cand,
                                live=live,
                                ledger=ledger,
                                locked_doc=doc,
                            ):
                                purged = True
                    return None
                # FR #1093: stamp WP0/issue pins before the machine gate (stale rows).
                _stamp_require_machine(cand_eff)
                if row_blocked_for_machine(cand_eff, me):
                    return None
                # FR #8008: hard-ceiling class exclusion (opencode after repeated ceiling kills).
                if row_blocked_for_giveup_agent_kind(cand_eff, seat_agent_kind(home, me)):
                    return None
                # FR #6134 / #7888: free or unknown start_model stays FR-only.
                # A paid start_model may take MRB/UAT. Log the reason either way.
                if str(cand_eff.get("task") or "").upper() in ("MRB", "UAT"):
                    reason = mrb_eligibility_reason(home, me)
                    if row_blocked_for_opencode_seat(cand_eff, me, home):
                        with contextlib.suppress(Exception):
                            _log_queue_purge(
                                "INFO mrb-eligibility skip"
                                f" seat={me} task={str(cand_eff.get('task') or '').upper()}"
                                f" id={cand_eff.get('id') or ''} reason={reason}"
                            )
                        return None
                    cand_eff["mrb_eligibility"] = reason
                elif row_blocked_for_opencode_seat(cand_eff, me, home):
                    return None
                # FR #7926: an idle eligible free-model seat takes FR/FIX first.
                if fr_reserved_for_idle_free_seat(
                    home, cand_eff, me, now_f, live, ledger, free_idle
                ):
                    return None
                # FR #8138: only-Grok fleet - older FR/FIX before a newer MRB.
                if mrb_yields_to_older_fr(
                    home,
                    cand_eff,
                    me,
                    now_f,
                    live,
                    ledger,
                    free_idle,
                    doc.get("unaccepted") or [],
                ):
                    return None
                return cand_eff

            # Prefer focus order. If that yields nothing, fall back only within focused
            # repos when strict (operator asked to focus bobiverse - do not leak Club-Madeira
            # etc.). When strict is off, fall back to unaccepted minus ignored (FR #6208).
            order = ordered_unaccepted(home, doc["unaccepted"])
            pick = None
            for cand in order:
                pick = _eligible(cand)
                if pick is not None:
                    break
            if pick is None:
                ignored = focus_ignore.ignored_list(home)
                if focus_ignore.is_strict(home):
                    focused = set()
                    try:
                        fdoc = focus_ignore.load_focus(home)
                        focused |= {str(k) for k in (fdoc.get("repos") or {}).keys()}
                        for meta in (fdoc.get("items") or {}).values():
                            if isinstance(meta, dict) and meta.get("repo"):
                                focused.add(str(meta["repo"]))
                    except Exception:
                        focused = set()
                    fallback = [
                        r for r in (doc.get("unaccepted") or [])
                        if isinstance(r, dict)
                        and not any(
                            focus_ignore.repo_match(ig, str(r.get("repo") or ""))
                            for ig in ignored
                        )
                        and (
                            not focused
                            or any(
                                focus_ignore.repo_match(str(r.get("repo") or ""), fr)
                                or focus_ignore.repo_match(fr, str(r.get("repo") or ""))
                                for fr in focused
                            )
                        )
                    ]
                else:
                    fallback = [
                        r for r in (doc.get("unaccepted") or [])
                        if isinstance(r, dict)
                        and not any(
                            focus_ignore.repo_match(ig, str(r.get("repo") or ""))
                            for ig in ignored
                        )
                    ]
                # FR #3205: fallback uses the same kind+number order as focus walk.
                fallback.sort(key=lambda r: focus_ignore.offer_sort_key(home, r))
                for cand in fallback:
                    pick = _eligible(cand)
                    if pick is not None:
                        break
            if pick is None:
                # FR #7966: stamp no_eligible_since only when every live seat is refused.
                for cand in doc.get("unaccepted") or []:
                    if not isinstance(cand, dict):
                        continue
                    if not cand.get("offer_refused_by"):
                        continue
                    if cand.get("offered_to") or live_seat_can_take_unanswered(
                        cand, live, home=home, doc=doc
                    ):
                        if cand.pop("no_eligible_since", None) is not None:
                            purged = True
                        continue
                    try:
                        since = float(cand.get("no_eligible_since") or 0)
                    except (TypeError, ValueError):
                        since = 0.0
                    if since <= 0:
                        cand["no_eligible_since"] = now_f
                        purged = True
                if purged:
                    try:
                        _write_queue(queue_path(home), doc)
                    except OSError:
                        return "error", None
                return "empty", None
            prev_to = ""
            same = False
            job: dict | None = None
            for i, row in enumerate(doc["unaccepted"]):
                if row is pick or _same(row, str(pick.get("repo") or ""), str(pick.get("task") or ""), str(pick.get("id") or "")):
                    # FR #618: persist enriched author stamps (pick may be enrich_uat_author_fields copy).
                    job = dict(pick)
                    # Prefer live queue row fields (pick may be enrich copy without offered_*).
                    prev_to = str(row.get("offered_to") or job.get("offered_to") or "").strip()
                    prev_ts = str(row.get("offered_ts") or job.get("offered_ts") or "").strip()
                    try:
                        prev_count = int(row.get("offered_count") or job.get("offered_count") or 0)
                    except (TypeError, ValueError):
                        prev_count = 0
                    same = bool(prev_to) and _same_seat(prev_to, me)
                    job["offered_to"] = me
                    stamp_cli_exit_retry_used(job)
                    # A live offer means someone is eligible (FR #7966).
                    job.pop("no_eligible_since", None)
                    # FR #8428: a different seat took the row after a timeout.
                    last_timeout = str(job.get("offer_last_timeout_seat") or "").strip()
                    if last_timeout and not _same_seat(last_timeout, me):
                        job.pop("offer_last_timeout_seat", None)
                    # FR #2309: rebroadcast keeps original offered_ts so OFFER_TIMEOUT can free the row.
                    if same and prev_ts:
                        job["offered_ts"] = prev_ts
                    else:
                        job["offered_ts"] = _utc_now()
                    job["offered_count"] = prev_count + 1
                    job["offered_channel"] = bobreport.normalize_channel(channel) if channel else ""
                    via = str(offered_via or "").strip()
                    if via:
                        job["offered_via"] = via
                    elif not same:
                        job.pop("offered_via", None)
                    resolved = resolve_assign_url(job)
                    if resolved:
                        job["url"] = resolved
                    if str(job.get("task") or "").upper() in ("MRB", "UAT"):
                        why = str(job.get("mrb_eligibility") or mrb_eligibility_reason(home, me))
                        job["mrb_eligibility"] = why
                        with contextlib.suppress(Exception):
                            _log_queue_purge(
                                "INFO mrb-eligibility offer"
                                f" seat={me} task={str(job.get('task') or '').upper()}"
                                f" id={job.get('id') or ''} reason={why}"
                            )
                    doc["unaccepted"][i] = job
                    break
            else:
                return "error", None
            if job is None:
                return "error", None
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            # FR #3205: keep precompute fingerprint in sync after stamp so the next
            # !bored can stay on the zero-GitHub path when the set of rows is unchanged.
            with contextlib.suppress(Exception):
                rebuild_offer_precompute(home, list(doc.get("unaccepted") or []))
            # FR #4260: re-offer to a different nick frees the previous seat's hold.
            if prev_to and not same:
                with contextlib.suppress(Exception):
                    _clear_job_seat_holds_unlocked(
                        home,
                        str(job.get("repo") or ""),
                        str(job.get("task") or ""),
                        str(job.get("id") or ""),
                        except_nick=me,
                    )
            with contextlib.suppress(Exception):
                _note_seat_hold_unlocked(home, me, job)  # FR #4089
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def offer_top(
    home: Path,
    nick: str,
    channel: str,
    *,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
    fetch_issue=None,
) -> tuple[str, dict | None]:
    """Peek oldest eligible unaccepted and stamp offered_to without accepting (FR #207 / #180)."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    budget = _GithubCallBudget(BORED_GITHUB_CALL_BUDGET)
    depends_issue_open = depends_issue_open_checker(issue_open)
    # FR #9418: unbudgeted issue dict fetch for G1 when digests are not queued.
    depends_issue_fetch = depends_issue_fetch_checker(fetch_issue)
    # FR #9411: unbudgeted CLOSED FR check (budget 0 would otherwise never fire).
    fr_closed_issue_open = depends_issue_open_checker(issue_open)
    pr_exists = _budgeted_github(pr_exists, budget, "pr_exists")
    is_pull = _budgeted_github(is_pull, budget, "is_pull")
    issue_open = _budgeted_github(issue_open, budget, "issue_open")
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            if not doc["unaccepted"]:
                return "empty", None
            # FR #3188: stamped/structural bulk purge only; live checks are budgeted below.
            purged = bool(_purge_dead_mrb_unaccepted(doc, pr_exists=None, home=home))
            purged = bool(_purge_dead_mrb_accepted(doc, pr_exists=None, home=home)) or purged
            purged = bool(_purge_dead_fix_unaccepted(doc, pr_exists=None)) or purged
            purged = bool(_purge_dead_fix_accepted(doc, pr_exists=None, home=home)) or purged
            purged = bool(_purge_fr_that_are_pulls(doc)) or purged
            open_dep_keys_top = open_fr_issue_keys(doc)
            purged = bool(_purge_closed_fr_unaccepted(doc, home=home)) or purged
            # Accepted list is small - live check under the shared budget (FR #2361).
            purged = bool(
                _purge_closed_fr_accepted(doc, issue_open=issue_open, home=home)
            ) or purged
            # FR #4682: live-check FIX under the same budget.
            if pr_exists is not None:
                purged = bool(_purge_dead_fix_unaccepted(doc, pr_exists=pr_exists)) or purged
                purged = bool(
                    _purge_dead_fix_accepted(doc, pr_exists=pr_exists, home=home)
                ) or purged
            # FR #1508: free seats stuck doing MERGED MRB even when ACC row is gone.
            if pr_exists is not None:
                with contextlib.suppress(Exception):
                    if clear_orphan_digest_mrb_doing(home, pr_exists=pr_exists):
                        purged = True
            doc["unaccepted"].sort(key=_sort_key)
            pick_i = None
            i = 0
            live = live_seat_nicks(home)
            # FR #9534: pass locked doc - free_seat_nicks must not call load_queue under lock.
            free = free_seat_nicks(home, live, doc=doc)  # FR #9478 soft machine-id
            while i < len(doc.get("unaccepted") or []):
                row = doc["unaccepted"][i]
                if (
                    row_needs_human(row, nick or "")
                    or row_on_cooldown(row, now_f, nick or "", live=live)
                    or row_gave_up_by(row, nick or "", live=live)
                    or row_blocked_for_giveup_agent_kind(row, seat_agent_kind(home, nick or ""))
                ):
                    i += 1
                    continue
                # FR #9411: ops-monitor trackers leave the unaccepted queue (parity with
                # offer_focus_top); other skip_fr reasons stay sticky skip.
                skip_why = row_skip_fr_reason(row)
                if skip_why:
                    if skip_why in ("ops_monitor_tracker", "tipform_restore_escalate"):
                        if _drop_unaccepted_row(
                            doc, row, kind="ops-monitor", reason=skip_why
                        ):
                            purged = True
                            continue
                    i += 1
                    continue
                # BOB-G3: held digests stay as gate records (skip only).
                if digest_issue_reason(row):
                    i += 1
                    continue
                # FR #4009 / #8741: hold or park-only FR - skip and purge from unaccepted.
                # FR #9402: pass home so offered_to seat-holds clear with the drop.
                skip_why = row_fr_skip_offer_reason(row)
                if skip_why:
                    kind = "fr-park-only" if skip_why.startswith("park-only") else "fr-hold"
                    if _drop_unaccepted_row(
                        doc, row, kind=kind, reason=skip_why, home=home
                    ):
                        purged = True
                        continue
                    i += 1
                    continue
                # FR #9455 bob_g1_shared_gate: one Depends-on gate for top/bored walk.
                if depends_gate_reason(
                    row,
                    doc,
                    open_keys=open_dep_keys_top,
                    issue_open=depends_issue_open,
                    issue_fetch=depends_issue_fetch,
                ):
                    i += 1
                    continue
                if row_awaits_mrb1(row):
                    i += 1
                    continue  # legacy hook; always False (op 2026-10-04)
                if repo_archived_for_queue(str(row.get("repo") or "")):
                    i += 1
                    continue  # FR #785
                if str(row.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc, str(row.get("repo") or ""), str(row.get("id") or "")
                ):
                    i += 1
                    continue  # FR #254
                # FR #9411: unbudgeted CLOSED check (see offer_focus_top).
                if _canon_task(row) == "FR" and _fr_issue_is_closed(
                    row, issue_open=fr_closed_issue_open
                ):
                    repo = str(row.get("repo") or "").strip()
                    num = str(row.get("id") or "").strip().lstrip("#")
                    _log_queue_purge(
                        f"INFO git-claim purge closed-fr {repo}#{num} "
                        f"reason=issue_open=False"
                    )
                    del doc["unaccepted"][i]
                    purged = True
                    continue
                # FR #1313 / MRB #3207: definitive is_pull=True on this FR row -> purge it only.
                if _canon_task(row) == "FR" and _live_verdict(is_pull, row) is True:
                    if _drop_unaccepted_row(doc, row, kind="fr-is-pull", reason="is_pull=True"):
                        purged = True
                        continue
                    i += 1
                    continue
                if not fr_row_offerable(
                    row,
                    is_pull=is_pull,
                    pr_exists=pr_exists,
                    issue_open=fr_closed_issue_open,
                ):
                    i += 1
                    continue  # FR #846 / #838 / #2340
                # FR #818 / t853u: never offer legacy per-PR UAT (same gate as offer_focus_top).
                if str(row.get("task") or "").upper() == "UAT" and not is_repo_uat(row):
                    i += 1
                    continue
                # FR #9382: CAST IRON - no UAT when the repo has no release to build.
                if uat_no_release_to_build_reason(row, home=home):
                    if _drop_unaccepted_row(
                        doc, row, kind="uat-no-release", reason="no-release-to-build"
                    ):
                        purged = True
                        continue
                    i += 1
                    continue
                # FR #740 / MRB #3207: definitive not-open MRB -> purge this row only.
                if _canon_task(row) == "MRB" and _live_verdict(pr_exists, row) is False:
                    if _drop_unaccepted_row(doc, row, kind="dead-mrb", reason="pr_exists=False"):
                        purged = True
                        continue
                    i += 1
                    continue
                if mrb_already_done(doc, row, home=home, pr_exists=pr_exists):
                    i += 1
                    continue  # FR #740 / #1585
                if not mrb_row_offerable(row, pr_exists=pr_exists):
                    i += 1
                    continue
                try:
                    import fuel_chain

                    def _cr_lookup(repo: str, num: str, _row=row):
                        # FR #5865: state dict so silence->absent and failed stamp.
                        return fuel_chain.lookup_coderabbit_state(
                            repo, num, str(_row.get("head_sha") or "")
                        )

                    cr_check = _budgeted_github(_cr_lookup, budget, "coderabbit")
                    if fuel_chain.apply_mrb_coderabbit_gate(
                        row, now_f, lookup=cr_check
                    ):
                        # Persist wait/pending stamps even while the offer is held.
                        # FR #6211: row-specific hold in chair log.
                        with contextlib.suppress(Exception):
                            _log_queue_purge(
                                "INFO "
                                + fuel_chain.coderabbit_hold_message(row, now_f)
                                + " via=offer_top"
                            )
                        purged = True
                        i += 1
                        continue
                except Exception:
                    pass
                row_eff = enrich_review_author_fields(doc, row)
                led = ledger_load(home)
                if row_blocked_for_machine(row_eff, nick or "") or review_blocked_for_author(
                    row_eff, (nick or "").strip(), live, ledger=led, free=free
                ):
                    i += 1
                    continue
                pick_i = i
                # Persist enrichment onto the queued row when we filled stamps.
                if row_eff is not row:
                    doc["unaccepted"][i] = dict(row_eff)
                break
            if pick_i is None:
                if purged:
                    try:
                        _write_queue(queue_path(home), doc)
                    except OSError:
                        return "error", None
                return "empty", None
            job = dict(doc["unaccepted"][pick_i])
            job["offered_to"] = (nick or "").strip()
            stamp_cli_exit_retry_used(job)
            job["offered_ts"] = _utc_now()
            job["offered_channel"] = bobreport.normalize_channel(channel) if channel else ""
            resolved = resolve_assign_url(job)
            if resolved:
                job["url"] = resolved
            doc["unaccepted"][pick_i] = job
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


# ---------------------------------------------------------------- seat ledger (t852u)
# queue.json rows are rebuilt by GitHub resync (cooldown / giveup / author stamps are lost) and the
# done/accepted history is tiny, so author-seat stamps on rows are unreliable. This ledger is durable,
# outside queue.json, and is the authority for "this seat touched / gave up this work".
LEDGER_NAME = "seat-ledger.json"
_LEDGER_MUTEX = None


def ledger_path(home: Path) -> Path:
    return _root(home) / LEDGER_NAME


def _lkey(repo: str, ident) -> str:
    num = str(ident or "").strip().lstrip("#")
    return f"{_repo_key(repo)}#{num}"


def _ledger_empty() -> dict:
    return {"v": 1, "touch": {}, "giveup": {}, "no_clone_repos": {}}


def ledger_load(home: Path) -> dict:
    try:
        doc = json.loads(ledger_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _ledger_empty()
    if not isinstance(doc, dict):
        return _ledger_empty()
    doc.setdefault("touch", {})
    doc.setdefault("giveup", {})
    doc.setdefault("uat_cycle", {})
    doc.setdefault("fr_done", {})
    doc.setdefault("no_clone_repos", {})
    for bucket in ("touch", "giveup", "uat_cycle", "fr_done", "mrb_done"):
        raw = doc.get(bucket)
        if not isinstance(raw, dict):
            continue
        rewritten: dict = {}
        for k, v in raw.items():
            nk = _lkey(str(k).rsplit("#", 1)[0], str(k).rsplit("#", 1)[-1]) if "#" in str(k) else _repo_key(str(k))
            if nk in rewritten and isinstance(rewritten[nk], dict) and isinstance(v, dict):
                rewritten[nk].update(v)
            else:
                rewritten[nk] = v
        doc[bucket] = rewritten
    # FR #8153: seat -> {repo_key: iso_ts}; do not rewrite keys through _lkey.
    raw_nc = doc.get("no_clone_repos")
    if not isinstance(raw_nc, dict):
        doc["no_clone_repos"] = {}
    else:
        clean_nc: dict = {}
        for seat, repos in raw_nc.items():
            me = _canon_ledger_nick(str(seat))
            if not me or not isinstance(repos, dict):
                continue
            clean_repos: dict[str, str] = {}
            for rk, ts in repos.items():
                key = _repo_key(str(rk))
                iso = str(ts or "").strip()
                if key and iso:
                    clean_repos[key] = iso
            if clean_repos:
                if me in clean_nc and isinstance(clean_nc[me], dict):
                    clean_nc[me].update(clean_repos)
                else:
                    clean_nc[me] = clean_repos
        doc["no_clone_repos"] = clean_nc
    return doc


def ledger_uat_cycle_done(home: Path, repo: str) -> None:
    """A repo-level UAT finished: the next UAT cycle only counts PRs merged after now (t853u)."""
    def _f(doc: dict) -> None:
        doc.setdefault("uat_cycle", {})[(repo or "").strip().lower()] = _utc_now()
    try:
        _ledger_update(home, _f)
    except OSError:
        pass


def _ledger_update(home: Path, fn) -> None:
    import threading

    global _LEDGER_MUTEX
    if _LEDGER_MUTEX is None:
        _LEDGER_MUTEX = threading.Lock()
    with _LEDGER_MUTEX:
        doc = ledger_load(home)
        fn(doc)
        p = ledger_path(home)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)


def _canon_ledger_nick(nick: str) -> str:
    return (canonical_worker_nick(nick) or (nick or "").strip()).lower()


def ledger_touch(home: Path, nick: str, repo: str, task: str, keys: list[str]) -> None:
    """Record that ``nick`` did ``task`` (FR implement / MRB review / UAT) on each ``owner/repo#N`` key."""
    me = _canon_ledger_nick(nick)
    t = (task or "").upper()
    if not me or not t or not keys:
        return

    def _f(doc: dict) -> None:
        for k in keys:
            roles = doc["touch"].setdefault(k, {}).setdefault(me, [])
            if t not in roles:
                roles.append(t)

    try:
        _ledger_update(home, _f)
    except OSError:
        pass


def ledger_giveup(home: Path, nick: str, repo: str, task: str, ident: str, refs=()) -> None:
    """``nick`` gave up (GIVEUP/NACK) this row: never offer it, or its linked PR/issue UAT/MRB, to that seat again."""
    me = _canon_ledger_nick(nick)
    if not me:
        return
    keys = [_lkey(repo, ident)] + [_lkey(repo, r) for r in (refs or ()) if str(r).strip()]

    def _f(doc: dict) -> None:
        for k in keys:
            gu = doc["giveup"].setdefault(k, {})
            tl = gu.setdefault(me, [])
            if (task or "").upper() not in tl:
                tl.append((task or "").upper())

    try:
        _ledger_update(home, _f)
    except OSError:
        pass


def ledger_clear_giveup(
    home: Path,
    repo: str,
    ident: str,
    nick: str | None = None,
    task: str = "FR",
) -> int:
    """FR #2446 operator heal: drop ledger giveup for ``repo#ident`` (one nick or all nicks).

    Returns how many nick entries were cleared for the row key. Does not rewrite
    linked-ref keys (operator clears the living FR/issue key that is stuck).
    """
    key = _lkey(repo, ident)
    task_u = (task or "FR").upper()
    me = _canon_ledger_nick(nick) if nick else ""
    cleared = [0]

    def _f(doc: dict) -> None:
        gu = doc.get("giveup") or {}
        if key not in gu or not isinstance(gu[key], dict):
            return
        bucket = gu[key]
        if me:
            tl = bucket.get(me) or []
            if task_u in tl:
                bucket[me] = [t for t in tl if t != task_u]
                cleared[0] += 1
                if not bucket[me]:
                    bucket.pop(me, None)
        else:
            for n, tl in list(bucket.items()):
                if task_u in (tl or []):
                    bucket[n] = [t for t in (tl or []) if t != task_u]
                    cleared[0] += 1
                    if not bucket[n]:
                        bucket.pop(n, None)
        if not bucket:
            gu.pop(key, None)

    try:
        _ledger_update(home, _f)
    except OSError:
        return 0
    return cleared[0]


_CLEARGIVEUP_CMD = re.compile(
    r"^!cleargiveup\s+(\S+?)#(\d+)(?:\s+(\S+))?\s*$",
    re.IGNORECASE,
)


def parse_cleargiveup_cmd(body: str) -> tuple[str, str, str] | None:
    """``!cleargiveup owner/repo#N [seat]`` -> (repo, '#N', seat-or-empty) (FR #5135)."""
    m = _CLEARGIVEUP_CMD.match((body or "").strip())
    if not m:
        return None
    return m.group(1).strip().strip("{}"), f"#{int(m.group(2))}", (m.group(3) or "").strip()


_UNPIN_CMD = re.compile(
    r"^!unpin\s+(\S+?)#(\d+)\s*$",
    re.IGNORECASE,
)
_PIN_CMD = re.compile(
    r"^!pin\s+(\S+?)#(\d+)\s+([a-z0-9][a-z0-9_.-]*)\s*$",
    re.IGNORECASE,
)


def parse_unpin_cmd(body: str) -> tuple[str, str] | None:
    """``!unpin owner/repo#N`` -> (repo, '#N') (FR #6407)."""
    m = _UNPIN_CMD.match((body or "").strip())
    if not m:
        return None
    return m.group(1).strip().strip("{}"), f"#{int(m.group(2))}"


def parse_pin_cmd(body: str) -> tuple[str, str, str] | None:
    """``!pin owner/repo#N <machine>`` -> (repo, '#N', machine) (FR #6407)."""
    m = _PIN_CMD.match((body or "").strip())
    if not m:
        return None
    mid = (m.group(3) or "").strip().lower()
    if not mid or mid in _REQUIRE_MACHINE_NON_MACHINE or _is_retired_require_machine(mid):
        return None
    return m.group(1).strip().strip("{}"), f"#{int(m.group(2))}", mid


def row_needs_machine_labels(row: dict) -> list[str]:
    """GitHub ``needs-<machine>`` / ``require_machine:<machine>`` labels on a queue row (FR #9708)."""
    labs = row.get("labels") or ()
    if isinstance(labs, str):
        labs = [labs]
    out: list[str] = []
    for lab in labs:
        s = str(lab or "").strip()
        m = _REQUIRE_MACHINE_LABEL_RE.match(s)
        if not m:
            continue
        mid = bobreport.normalize_machine_id(m.group(1)) or m.group(1).strip().lower()
        if mid and mid not in _REQUIRE_MACHINE_NON_MACHINE and not _is_retired_require_machine(mid):
            out.append(s)
    return out


def set_require_machine_job(
    home: Path, repo: str, ident: str, machine: str
) -> dict:
    """FR #6407: set require_machine on matching unaccepted/accepted rows under lock.

    ``machine`` of any/none/*/ - is an operator unpin (survives cue re-inference).
    A real machine id is an operator pin (kept by _stamp_require_machine).
    FR #6592: also stamps ``require_machine_operator=1`` so bobiverse / harvest-lesson
    rows honor the pin under FR #4512 re-infer (bare stamps without the flag still clear).
    Remaining hard ``_REQUIRE_MACHINE_ISSUE_PINS`` still win over operator any
    (documented in jeeves-commands); retired ce-priority-dev1 hard pins are gone.
    FR #9708: ``!unpin`` refuses while the queue row still has ``needs-*`` /
    ``require_machine:*`` labels (CAST IRON: never leave needs-* + rm=any).
    """
    repo_c = canonical_queue_repo((repo or "").strip()) or (repo or "").strip()
    ident_n = _norm_row_id(ident)
    raw = str(machine or "").strip().lower()
    if raw in {"*", "any", "none", "-"}:
        stamp = "any"
    else:
        if _is_retired_require_machine(raw):
            return {
                "ok": False,
                "error": "retired_machine",
                "queue_rows": 0,
                "repo": repo_c,
                "id": ident_n,
                "require_machine": "",
            }
        mid = bobreport.normalize_machine_id(raw) or raw
        if not mid or mid in _REQUIRE_MACHINE_NON_MACHINE:
            return {
                "ok": False,
                "error": "bad_machine",
                "queue_rows": 0,
                "repo": repo_c,
                "id": ident_n,
                "require_machine": "",
            }
        if _is_retired_require_machine(mid):
            return {
                "ok": False,
                "error": "retired_machine",
                "queue_rows": 0,
                "repo": repo_c,
                "id": ident_n,
                "require_machine": "",
            }
        stamp = fold_chair_host(mid)
    rows_n = 0
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            matches: list[dict] = []
            for bucket in ("unaccepted", "accepted"):
                for row in list(doc.get(bucket) or []):
                    if not isinstance(row, dict):
                        continue
                    if _repo_key(str(row.get("repo") or "")) != _repo_key(repo_c):
                        continue
                    if _norm_row_id(row.get("id")) != ident_n:
                        continue
                    matches.append(row)
            if stamp == "any":
                # FR #9708 CAST IRON: remove needs-* before !unpin (never needs-* + any).
                lingering: list[str] = []
                for row in matches:
                    lingering.extend(row_needs_machine_labels(row))
                if lingering:
                    uniq = ",".join(sorted(set(lingering)))
                    return {
                        "ok": False,
                        "error": f"needs_labels:{uniq}",
                        "queue_rows": len(matches),
                        "repo": repo_c,
                        "id": ident_n,
                        "require_machine": "",
                        "needs_labels": sorted(set(lingering)),
                    }
            for row in matches:
                row["require_machine"] = stamp
                # FR #6592: mark operator !pin/!unpin so bobiverse FR #4512 re-infer keeps it.
                row["require_machine_operator"] = "1"
                rows_n += 1
            if rows_n:
                _write_queue(queue_path(home), doc)
    except (TimeoutError, OSError):
        return {
            "ok": False,
            "error": "lock",
            "queue_rows": 0,
            "repo": repo_c,
            "id": ident_n,
            "require_machine": stamp,
        }
    return {
        "ok": True,
        "queue_rows": rows_n,
        "repo": repo_c,
        "id": ident_n,
        "require_machine": stamp,
    }



def ledger_clear_giveup_entry(
    home: Path, repo: str, ident: str, nick: str | None = None
) -> int:
    """FR #5135: drop ``giveup[owner/repo#n]`` for one seat or the whole key."""
    key = _lkey(repo, ident)
    me = _canon_ledger_nick(nick) if nick else ""
    cleared = [0]

    def _f(doc: dict) -> None:
        gu = doc.get("giveup") or {}
        bucket = gu.get(key)
        if not isinstance(bucket, dict):
            return
        if me:
            if me in bucket:
                bucket.pop(me, None)
                cleared[0] += 1
            if not bucket:
                gu.pop(key, None)
        else:
            cleared[0] += len(bucket)
            gu.pop(key, None)

    try:
        _ledger_update(home, _f)
    except OSError:
        return 0
    return cleared[0]


def _strip_giveup_seat_from_row(row: dict, seat: str) -> None:
    want = _canon_ledger_nick(seat)
    kept = [
        x.strip()
        for x in str(row.get("giveup_seats") or "").split(",")
        if x.strip() and _canon_ledger_nick(x) != want
    ]
    if kept:
        row["giveup_seats"] = ",".join(kept)
    else:
        row.pop("giveup_seats", None)


def clear_giveup_job(
    home: Path, repo: str, ident: str, seat: str | None = None
) -> dict:
    """FR #5135 / FR #9771: clear giveup stamps + ledger + matching seat-holds.

    FR #9771: ``!cleargiveup`` with ledger=0 still left ``busy (held …)`` when
    ``seat-holds.json`` kept a via=offer pin for the closed/stuck MRB.
    """
    repo_c = canonical_queue_repo((repo or "").strip()) or (repo or "").strip()
    ident_n = _norm_row_id(ident)
    seat_c = _canon_ledger_nick(seat) if seat else ""
    rows_n = 0
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            for bucket in ("unaccepted", "accepted"):
                for row in list(doc.get(bucket) or []):
                    if not isinstance(row, dict):
                        continue
                    if _repo_key(str(row.get("repo") or "")) != _repo_key(repo_c):
                        continue
                    if _norm_row_id(row.get("id")) != ident_n:
                        continue
                    if seat_c:
                        _strip_giveup_seat_from_row(row, seat_c)
                    else:
                        for k in ("giveup_seats", "cooldown_until", "giveup_ts", "needs_human", "giveup_agent_kinds"):
                            row.pop(k, None)
                        row["giveup_count"] = 0
                        row["hard_ceiling_count"] = 0
                    rows_n += 1
            if rows_n:
                _write_queue(queue_path(home), doc)
    except (TimeoutError, OSError):
        return {"ok": False, "error": "lock", "queue_rows": 0, "ledger": 0}
    ledger_n = ledger_clear_giveup_entry(home, repo_c, ident_n, nick=seat_c or None)
    # FR #9771: drop seat-holds for this job (all seats, or the named seat).
    holds_n = 0
    with contextlib.suppress(Exception):
        if seat_c:
            if clear_seat_hold(
                home, seat_c, repo=repo_c, task="", ident=ident_n, clear_pins=True
            ):
                holds_n = 1
        else:
            if clear_job_seat_holds(home, repo_c, "", ident_n):
                holds_n = 1
    return {
        "ok": True,
        "queue_rows": rows_n,
        "ledger": ledger_n,
        "holds": holds_n,
        "seat": seat_c,
        "repo": repo_c,
        "id": ident_n,
    }


def live_seats_matching_require_machine(live: set[str], required: str) -> list[str]:
    """Live seat nicks that match a ``require_machine`` pin (FR #2446)."""
    req = str(required or "").strip()
    if not req or req.lower() in ("*", "any", "none", "-", ""):
        return []
    out: list[str] = []
    for nick in sorted(live or ()):
        if seat_matches_require_machine(str(nick), req):
            out.append(str(nick))
    return out


def require_machine_all_live_gave_up(
    home: Path, row: dict, live: set[str] | None = None
) -> list[str]:
    """FR #2446: when a living require_machine row is GIVEUP'd by every live seat on that machine.

    Returns the matching live nicks (all gave up) or ``[]`` when the heal/surface
    condition does not apply (no pin, no matching live seats, or at least one
    matching seat has not given up).
    """
    if not isinstance(row, dict):
        return []
    row_eff = dict(row)
    _stamp_require_machine(row_eff)
    req = str(row_eff.get("require_machine") or "").strip()
    if not req or req.lower() in ("*", "any", "none", "-", ""):
        return []
    seats = live if live is not None else live_seat_nicks(home)
    matching = live_seats_matching_require_machine(set(seats or ()), req)
    if not matching:
        return []
    ledger = ledger_load(home)
    task = _canon_task(row_eff)
    blocked: list[str] = []
    for nick in matching:
        why = _ledger_blocks(ledger, row_eff, nick)
        if why and "gave up" in why:
            blocked.append(nick)
            continue
        if row_gave_up_by(row_eff, nick, live=set(seats or ())):
            blocked.append(nick)
            continue
        return []
    return blocked if len(blocked) == len(matching) else []


# FR #2486: Living / Refs-only tracking umbrellas keep operator GIVEUPs - auto-heal
# must not re-offer them after dual pin-machine GIVEUP (e.g. bobiverse#1993).
_LIVING_TRACKING_UMBRELLA_RE = re.compile(
    r"(?i)\bliving\s+fr\b|\brefs[-\s]?only\b|\bkeep\s+appending\b"
)
_LIVING_TRACKING_LABELS = frozenset(
    {"living", "living-fr", "refs-only", "refs_only", "tracking-umbrella", "tracking_umbrella"}
)


def row_skip_pin_ledger_heal_reason(row: dict) -> str | None:
    """FR #2486: why ``heal_require_machine_all_gave_up`` must leave this row alone."""
    labels = {
        str(x).strip().lower().replace("_", "-")
        for x in (row.get("labels") or [])
        if str(x or "").strip()
    }
    if labels & _LIVING_TRACKING_LABELS:
        return "living_tracking_label"
    blob = f"{row.get('title') or ''}\n{row.get('body') or ''}\n{row.get('line') or ''}"
    if _LIVING_TRACKING_UMBRELLA_RE.search(blob):
        return "living_tracking_body"
    return None


# FR #5163: MRB reviewer deadlock (cross give-up / author-only among idle seats).
MRB_REVIEWER_DEADLOCK_COOLDOWN_S = 180.0
MRB_REVIEWER_DEADLOCK_STATE = "mrb-reviewer-deadlock.json"
# FR #5701: recycle a seat that is idle past bored-latency without !bored.
# FR #5756: same 900s per-nick cooldown shared with MRB deadlock !recycleseat IRC.
BORED_LATENCY_HEAL_COOLDOWN_S = 900.0
BORED_LATENCY_HEAL_STATE = "bored-latency-heal.json"
# FR #6774: cap bored-latency !recycleseat per machine slot in a rolling window.
BORED_LATENCY_RECYCLE_WINDOW_S = 3600.0
BORED_LATENCY_RECYCLE_LIMIT = 2
RECYCLESEAT_IRC_COOLDOWN_S = BORED_LATENCY_HEAL_COOLDOWN_S
# FR #5889: outstanding !recycleseat per seat (ACK/NACK/timeout) + seat-keyed gate.
RECYCLESEAT_ACK_WAIT_S = 180.0
RECYCLESEAT_PENDING_STATE = "recycleseat-pending.json"

# FR #6256: bounded idle-seat recovery when author-only MRB deadlock is remediable
# by a fresh same-machine session (exact-seat self_mrb). Shares IRC cooldown with
# bored-latency / recycleseat pending gates.
IDLE_SEAT_RECOVERY_STATE = "idle-seat-recovery.json"
IDLE_SEAT_RECOVERY_MAX_ATTEMPTS = 3
IDLE_SEAT_RECOVERY_COOLDOWN_S = RECYCLESEAT_IRC_COOLDOWN_S
WORKER_STATE_FRESH_S = 600.0


def mrb_reviewer_deadlock_state_path(home: Path) -> Path:
    return _root(home) / MRB_REVIEWER_DEADLOCK_STATE


def _recycleseat_irc_cooldown_ok(
    home: Path,
    nick: str,
    now: float,
    *,
    cooldown_s: float | None = None,
) -> bool:
    """FR #5756 / #5889: shared per-nick cooldown across bored-latency heals."""
    canon = (canonical_worker_nick(nick) or nick or "").strip()
    if not canon:
        return False
    cool = (
        float(cooldown_s)
        if cooldown_s is not None
        else float(RECYCLESEAT_IRC_COOLDOWN_S)
    )
    state = _load_bored_latency_heal_state(home)
    nick_ts = state.get("nicks") if isinstance(state.get("nicks"), dict) else {}
    last = float(nick_ts.get(canon) or nick_ts.get(canon.lower()) or 0)
    if last and (now - last) < cool:
        return False
    return True


def _stamp_recycleseat_irc_cooldown(home: Path, nick: str, now: float) -> None:
    canon = (canonical_worker_nick(nick) or nick or "").strip()
    if not canon:
        return
    state = _load_bored_latency_heal_state(home)
    nick_ts = state.get("nicks") if isinstance(state.get("nicks"), dict) else {}
    nick_ts[canon] = float(now)
    _save_bored_latency_heal_state(home, {"nicks": nick_ts})


def enqueue_recycleseat_shop_only(
    home: Path,
    seat_nick: str,
    *,
    machine: str | None = None,
) -> str | None:
    """FR #5756: PRIVMSG !recycleseat only on the seat shop - never #bobiverse.

    Returns None on success, or a skip reason token (``recycle_skipped:no_machine``).
    """
    parsed = bobreport.parse_seat_nick(seat_nick)
    mid = (machine or (parsed[0] if parsed else "") or "").strip().lstrip("#").lower()
    if not mid:
        return "recycle_skipped:no_machine"
    cmd = f"!recycleseat {seat_nick} {mid}"
    shop = worker_shop_channel(seat_nick) or f"#{mid}"
    bobreport.enqueue_chair_fleet_privmsg(home, cmd, channel=shop)
    return None


def recycleseat_pending_state_path(home: Path) -> Path:
    return _root(home) / RECYCLESEAT_PENDING_STATE


def _load_recycleseat_pending(home: Path) -> dict:
    path = recycleseat_pending_state_path(home)
    if not path.is_file():
        return {"seats": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"seats": {}}
    if not isinstance(raw, dict):
        return {"seats": {}}
    seats = raw.get("seats")
    if not isinstance(seats, dict):
        seats = {}
    return {"seats": seats}


def _save_recycleseat_pending(home: Path, state: dict) -> None:
    path = recycleseat_pending_state_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        clean = {"seats": {}}
        for key, val in (state.get("seats") or {}).items():
            nick = (canonical_worker_nick(str(key)) or str(key or "")).strip()
            if not nick or not isinstance(val, dict):
                continue
            clean["seats"][nick] = {
                "sent_ts": float(val.get("sent_ts") or 0),
                "rid": str(val.get("rid") or ""),
                "awaiting": bool(val.get("awaiting")),
                "ack_ts": float(val["ack_ts"]) if val.get("ack_ts") not in (None, "") else None,
                "nack_ts": float(val["nack_ts"]) if val.get("nack_ts") not in (None, "") else None,
            }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(clean, indent=0) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def note_recycleseat_ack(home: Path, nick: str, *, now: float | None = None) -> None:
    """FR #5889: ear ACK recycleseat clears awaiting for this seat."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    canon = (canonical_worker_nick(nick) or nick or "").strip()
    if not canon:
        return
    state = _load_recycleseat_pending(home)
    seats = state.setdefault("seats", {})
    ent = dict(seats.get(canon) or {})
    ent["awaiting"] = False
    ent["ack_ts"] = now_f
    seats[canon] = ent
    _save_recycleseat_pending(home, state)


def note_recycleseat_nack(home: Path, nick: str, *, now: float | None = None) -> None:
    """FR #5889: ear NACK recycleseat clears awaiting for this seat."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    canon = (canonical_worker_nick(nick) or nick or "").strip()
    if not canon:
        return
    state = _load_recycleseat_pending(home)
    seats = state.setdefault("seats", {})
    ent = dict(seats.get(canon) or {})
    ent["awaiting"] = False
    ent["nack_ts"] = now_f
    seats[canon] = ent
    _save_recycleseat_pending(home, state)


def _mark_recycleseat_sent(
    home: Path, nick: str, *, now: float, rid: str = ""
) -> None:
    canon = (canonical_worker_nick(nick) or nick or "").strip()
    if not canon:
        return
    state = _load_recycleseat_pending(home)
    seats = state.setdefault("seats", {})
    seats[canon] = {
        "sent_ts": float(now),
        "rid": str(rid or ""),
        "awaiting": True,
        "ack_ts": None,
        "nack_ts": None,
    }
    _save_recycleseat_pending(home, state)
    _stamp_recycleseat_irc_cooldown(home, canon, now)


def recycleseat_send_blocked_reason(
    home: Path,
    nick: str,
    *,
    now: float,
    cooldown_s: float | None = None,
) -> str:
    """FR #5889: why !recycleseat must not fire for this seat ('' = ok to send)."""
    canon = (canonical_worker_nick(nick) or nick or "").strip()
    if not canon:
        return "recycle_skipped:no_nick"
    # Busy / working_on seats are never recycled (even if caller passed them as idle).
    try:
        if worker_working_on(home, canon):
            return "recycle_skipped:busy"
    except Exception:
        pass
    cool = (
        float(cooldown_s)
        if cooldown_s is not None
        else float(RECYCLESEAT_IRC_COOLDOWN_S)
    )
    pending = _load_recycleseat_pending(home).get("seats") or {}
    ent = pending.get(canon) or pending.get(canon.lower()) or {}
    if isinstance(ent, dict) and ent.get("awaiting"):
        sent = float(ent.get("sent_ts") or 0)
        if sent and (now - sent) < float(RECYCLESEAT_ACK_WAIT_S):
            return "recycle_skipped:awaiting_ack"
    # Recently ACKed: seat-keyed cooldown from ack_ts (signature changes do not reset).
    ack_ts = ent.get("ack_ts") if isinstance(ent, dict) else None
    if ack_ts not in (None, ""):
        try:
            if (now - float(ack_ts)) < cool:
                return "recycle_skipped:recent_ack"
        except (TypeError, ValueError):
            pass
    if not _recycleseat_irc_cooldown_ok(home, canon, now, cooldown_s=cool):
        return "recycle_skipped:cooldown"
    return ""


def resolve_recycleseat_install_root(home: Path, explicit=None) -> Path:
    """Install root for tray recycleseat queue (FR #5059 / #5163)."""
    if explicit is not None and str(explicit).strip():
        return Path(explicit)
    env = (os.environ.get("BOB_INSTALL_ROOT") or "").strip()
    if env:
        return Path(env)
    h = Path(home)
    for cand in (h, h.parent, h.parent.parent if h.parent != h else h):
        try:
            if (cand / "run").is_dir() or (cand / "scripts").is_dir():
                return cand
        except OSError:
            continue
    return h


def _mrb_idle_block_reason(
    row: dict,
    nick: str,
    live: set[str],
    ledger: dict | None = None,
    *,
    free: set[str] | None = None,
) -> str:
    """Why an idle seat cannot take this MRB ('' = eligible). FR #5163 / #9478."""
    if _canon_task(row) != "MRB":
        return "not-mrb"
    if row_needs_human(row, nick):
        return "needs_human"
    if row_blocked_for_machine(row, nick):
        return "machine"
    if review_blocked_for_author(row, nick, live, ledger=ledger, free=free):
        return "author"
    if seat_on_deterministic_nack_cooldown(row, nick, time.time()):
        return "nack-cooldown"
    if row_gave_up_by(row, nick, live=live) and not no_terminal_reply_does_not_block(row, nick):
        return "giveup"
    if ledger is not None:
        why = ledger_blocks(ledger, row, nick, live)
        if why:
            if "gave up" in why.lower():
                return "giveup"
            return "ledger"
    return ""


def mrb_has_eligible_reviewer(
    home: Path, row: dict, live: set[str], *, ledger: dict | None = None,
    now: float | None = None,
) -> bool:
    """A busy third-party seat can eventually review; Copilot must pass dispatch."""
    import copilot_dispatch

    led = ledger if ledger is not None else ledger_load(home)
    humans = {n for n in live if str(n).strip().lower() != "copilot"}
    return any(
        not _mrb_idle_block_reason(row, nick, humans, led) for nick in humans
    ) or copilot_dispatch.mrb_reviewer_available(home, row, ledger=led, now=now)


def detect_mrb_reviewer_deadlock(
    home: Path,
    *,
    idle: set[str] | None = None,
    live: set[str] | None = None,
    rows: list | None = None,
    ledger: dict | None = None,
    now: float | None = None,
) -> dict | None:
    """Return deadlock info when every idle seat is ineligible for every waiting MRB.

    FR #5163. ``None`` when there is no deadlock (or no idle / no MRB rows).
    """
    seats_live = set(live) if live is not None else live_seat_nicks(home)
    seats_idle = set(idle) if idle is not None else free_seat_nicks(home, seats_live)
    seats_idle = {
        (canonical_worker_nick(n) or n or "").strip()
        for n in seats_idle
        if (canonical_worker_nick(n) or n or "").strip()
    }
    # Virtual seats cannot be recycled or have GIVEUP cleared as cross-seat heal.
    seats_idle = {n for n in seats_idle if n.lower() != "copilot"}
    seats_live = {n for n in seats_live if n.lower() != "copilot"}
    if not seats_idle:
        return None
    if rows is None:
        try:
            path = queue_path(home)
            raw = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
            rows = [r for r in (raw.get("unaccepted") or []) if isinstance(r, dict)]
        except Exception:
            return None
    mrb_rows = [
        r
        for r in rows
        if isinstance(r, dict)
        and _canon_task(r) == "MRB"
        and not row_needs_human(r, "")
    ]
    if not mrb_rows:
        return None
    led = ledger if ledger is not None else ledger_load(home)
    import copilot_dispatch

    if any(
        copilot_dispatch.mrb_reviewer_available(home, row, ledger=led, now=now)
        for row in mrb_rows
    ):
        return None
    for nick in seats_idle:
        for row in mrb_rows:
            if not _mrb_idle_block_reason(row, nick, seats_live, led):
                return None
    # FR #5268 / #5270: cross-giveup clear needs ≥2 idle seats. A sole idle
    # seat that GIVEUP'd the only waiting MRB is not a multi-seat deadlock -
    # clearing its giveup_seats lets offer_after_giveup / !bored re-offer the
    # same job to the same nick (defeats FR #2811 / FR #628).
    clearable: list[tuple[dict, str]] = []
    if len(seats_idle) >= 2:
        for row in mrb_rows:
            authors = {a.lower() for a in row_author_seats(row)}
            for nick in seats_idle:
                if nick.lower() in authors:
                    continue
                if row_gave_up_by(row, nick, live=seats_live):
                    clearable.append((row, nick))
                    continue
                if led:
                    why = ledger_blocks(led, row, nick, seats_live)
                    if why and "gave up" in why.lower():
                        clearable.append((row, nick))
    if clearable:
        kind = "cross_giveup"
    else:
        # author_only recycleseat only when every idle block is author (not
        # giveup/cooldown). Sole-seat GIVEUP must stick until another seat
        # appears or an operator !cleargiveup / !assign (FR #5268 / #5270).
        if not all(
            _mrb_idle_block_reason(row, nick, seats_live, led) == "author"
            for nick in seats_idle
            for row in mrb_rows
        ):
            return None
        kind = "author_only"
    sig_parts = sorted(
        f"{str(r.get('repo') or '')}{_norm_row_id(r.get('id'))}" for r in mrb_rows
    ) + sorted(n.lower() for n in seats_idle)
    return {
        "kind": kind,
        "idle": sorted(seats_idle),
        "live": sorted(seats_live),
        "mrb_ids": sig_parts[: len(mrb_rows)],
        "clearable": clearable,
        "signature": "|".join(sig_parts),
        "rows": mrb_rows,
    }


def _load_mrb_deadlock_state(home: Path) -> dict:
    path = mrb_reviewer_deadlock_state_path(home)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_mrb_deadlock_state(home: Path, state: dict) -> None:
    path = mrb_reviewer_deadlock_state_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=0) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass



def idle_seat_recovery_state_path(home: Path) -> Path:
    return _root(home) / IDLE_SEAT_RECOVERY_STATE


def _load_idle_seat_recovery_state(home: Path) -> dict:
    path = idle_seat_recovery_state_path(home)
    if not path.is_file():
        return {"machines": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"machines": {}}
    if not isinstance(raw, dict):
        return {"machines": {}}
    machines = raw.get("machines")
    if not isinstance(machines, dict):
        machines = {}
    return {"machines": machines}


def _save_idle_seat_recovery_state(home: Path, state: dict) -> None:
    path = idle_seat_recovery_state_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        clean = {"machines": {}}
        for key, val in (state.get("machines") or {}).items():
            mid = bobreport.fold_machine_id(str(key or ""))
            if not mid or not isinstance(val, dict):
                continue
            clean["machines"][mid] = {
                "attempts": int(val.get("attempts") or 0),
                "window_ts": float(val.get("window_ts") or 0),
                "last_ts": float(val.get("last_ts") or 0),
                "last_nick": str(val.get("last_nick") or ""),
                "last_sig": str(val.get("last_sig") or ""),
                "last_result": str(val.get("last_result") or ""),
            }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(clean, indent=0) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _coderabbit_hold_stamp(row: dict, now: float) -> bool:
    """True when the row is stamped as waiting on CodeRabbit (no live API)."""
    if not isinstance(row, dict):
        return False
    st = str(row.get("coderabbit") or "").strip().lower()
    if st in ("pending", "waiting", "hold"):
        return True
    # Stamped wait window without a terminal outcome.
    if st in ("", "off", "ready", "failed", "timeout", "absent"):
        return False
    try:
        since = float(row.get("coderabbit_wait_since") or 0)
    except (TypeError, ValueError):
        since = 0.0
    return bool(since and (float(now) - since) >= 0 and st not in ("ready", "failed", "timeout"))


def worker_evidence_fresh(
    home: Path,
    nick: str,
    now: float,
    *,
    last_activity: dict | None = None,
    max_age_s: float | None = None,
) -> bool:
    """FR #6256: trust per-seat activity, never machine lastSeen alone."""
    max_age = float(WORKER_STATE_FRESH_S if max_age_s is None else max_age_s)
    canon = (canonical_worker_nick(nick) or nick or "").strip()
    if not canon:
        return False
    ts = None
    if isinstance(last_activity, dict):
        for key in (canon, canon.lower(), nick, str(nick).lower()):
            if key in last_activity and last_activity[key] not in (None, ""):
                try:
                    ts = float(last_activity[key])
                    break
                except (TypeError, ValueError):
                    pass
    if ts is None:
        with contextlib.suppress(Exception):
            ts = last_worker_activity(home, canon)
    if ts is None:
        # Digest worker_list updated= is seat evidence; machines[].lastSeen is not.
        with contextlib.suppress(Exception):
            import datetime as _dt

            doc = bobreport.load_digest(_root(home))
            parsed = bobreport.parse_seat_nick(canon)
            if parsed:
                mid, _pid = parsed
                ent = (doc.get("machines") or {}).get(mid) or {}
                for r in bobreport._coerce_worker_list(ent.get("worker_list")):
                    if str(r.get("nick") or "").strip().lower() != canon.lower():
                        continue
                    raw = str(r.get("updated") or "").strip()
                    if not raw:
                        break
                    try:
                        if raw.endswith("Z"):
                            raw = raw[:-1] + "+00:00"
                        ts = _dt.datetime.fromisoformat(raw).timestamp()
                    except Exception:
                        ts = None
                    break
    if ts is None:
        return False
    age = float(now) - float(ts)
    # Future stamps (clock skew / fixture mismatch) are not fresh evidence.
    if age < 0:
        return False
    return age <= max_age


def _seat_accepted_or_offered(home: Path, nick: str, *, accepted: list | None = None) -> bool:
    canon = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not canon:
        return False
    with contextlib.suppress(Exception):
        if worker_working_on(home, nick):
            return True
    rows = accepted
    if rows is None:
        with contextlib.suppress(Exception):
            doc = load_queue(home)
            rows = list(doc.get("accepted") or [])
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        by = (canonical_worker_nick(str(row.get("accepted_by") or "")) or str(row.get("accepted_by") or "")).strip().lower()
        if by and by == canon:
            return True
        offered = (canonical_worker_nick(str(row.get("offered_to") or "")) or str(row.get("offered_to") or "")).strip().lower()
        if offered and offered == canon:
            return True
    return False


def author_only_recovery_blocked_reason(
    home: Path,
    nick: str,
    info: dict,
    now: float,
    *,
    last_activity: dict | None = None,
    accepted: list | None = None,
    cooldown_s: float | None = None,
) -> str:
    """Why FR #6256 must not !recycleseat this author-only idle seat ('' = ok)."""
    canon = (canonical_worker_nick(nick) or nick or "").strip()
    if not canon:
        return "recycle_skipped:no_nick"
    if _seat_accepted_or_offered(home, canon, accepted=accepted):
        return "recycle_skipped:busy"
    # Unlocked read: heal_mrb holds the queue lock; seat_is_out_of_fuel would nest-lock.
    try:
        if _seat_key(canon) in _load_seat_out_of_fuel_unlocked(home, now):
            return "recycle_skipped:out_of_fuel"
    except Exception:
        pass
    kind = ""
    with contextlib.suppress(Exception):
        kind = seat_agent_kind(home, canon)
    if seat_skips_hostile_review(kind):
        return "recycle_skipped:opencode_hostile"
    rows = [r for r in (info.get("rows") or []) if isinstance(r, dict)]
    remediable = [r for r in rows if not _coderabbit_hold_stamp(r, now)]
    if rows and not remediable:
        return "recycle_skipped:coderabbit_only"
    if not worker_evidence_fresh(home, canon, now, last_activity=last_activity):
        return "recycle_skipped:stale_worker"
    cool = float(IDLE_SEAT_RECOVERY_COOLDOWN_S if cooldown_s is None else cooldown_s)
    blocked = recycleseat_send_blocked_reason(home, canon, now=now, cooldown_s=cool)
    if blocked:
        return blocked
    parsed = bobreport.parse_seat_nick(canon)
    mid = bobreport.fold_machine_id(parsed[0]) if parsed else ""
    if not mid:
        return "recycle_skipped:no_machine"
    st = _load_idle_seat_recovery_state(home)
    ent = (st.get("machines") or {}).get(mid) or {}
    attempts = int(ent.get("attempts") or 0)
    window_ts = float(ent.get("window_ts") or 0)
    # Reset attempt window 24h after the first sent in the window (skips must not extend it).
    if window_ts and (float(now) - window_ts) >= 86400.0:
        attempts = 0
    if attempts >= int(IDLE_SEAT_RECOVERY_MAX_ATTEMPTS):
        return "recycle_skipped:attempt_cap"
    return ""


def _pick_author_only_recovery_nick(info: dict) -> str:
    idle = [
        (canonical_worker_nick(n) or n or "").strip()
        for n in (info.get("idle") or [])
        if (canonical_worker_nick(n) or n or "").strip()
    ]
    idle = sorted({n for n in idle if n.lower() != "copilot"}, key=lambda n: n.lower())
    return idle[0] if idle else ""


def _record_idle_seat_recovery(
    home: Path,
    nick: str,
    *,
    now: float,
    signature: str,
    result: str,
) -> None:
    parsed = bobreport.parse_seat_nick(nick)
    mid = bobreport.fold_machine_id(parsed[0]) if parsed else ""
    if not mid:
        return
    st = _load_idle_seat_recovery_state(home)
    machines = st.setdefault("machines", {})
    ent = dict(machines.get(mid) or {})
    window_ts = float(ent.get("window_ts") or 0)
    attempts = int(ent.get("attempts") or 0)
    if window_ts and (float(now) - window_ts) >= 86400.0:
        attempts = 0
        window_ts = 0.0
    if result == "sent":
        attempts += 1
        window_ts = window_ts or float(now)
    ent.update(
        {
            "attempts": attempts,
            "window_ts": window_ts,
            "last_ts": float(now),
            "last_nick": nick,
            "last_sig": str(signature or ""),
            "last_result": str(result or ""),
        }
    )
    machines[mid] = ent
    _save_idle_seat_recovery_state(home, st)


def maybe_recycle_author_only_idle_seat(
    home: Path,
    info: dict,
    *,
    now: float,
    install_root=None,
    last_activity: dict | None = None,
    accepted: list | None = None,
    cooldown_s: float | None = None,
) -> list[str]:
    """FR #6256: one bounded shop !recycleseat when a fresh session can clear self_mrb.

    Keeps author/implementer provenance on the row. Never recycles for
    CodeRabbit-only holds, stale worker evidence, OpenCode hostile-skip,
    busy/out-of-fuel, or past the per-machine attempt cap.
    """
    if not info or info.get("kind") != "author_only":
        return []
    pick = _pick_author_only_recovery_nick(info)
    if not pick:
        return ["idle-recovery recycle_skipped:no_idle"]
    reason = author_only_recovery_blocked_reason(
        home,
        pick,
        info,
        now,
        last_activity=last_activity,
        accepted=accepted,
        cooldown_s=cooldown_s,
    )
    if reason:
        _record_idle_seat_recovery(
            home, pick, now=now, signature=str(info.get("signature") or ""), result=reason
        )
        return [f"idle-recovery {reason} seat={pick}"]
    lines: list[str] = []
    root = resolve_recycleseat_install_root(home, install_root)
    try:
        import recycleseat as _rs

        rid = _rs.write_request(
            _rs.queue_dir(root),
            pick,
            "jeeves",
            "idle-seat-recovery",
            now=now,
        )
        skip = enqueue_recycleseat_shop_only(home, pick)
        if skip:
            _record_idle_seat_recovery(
                home,
                pick,
                now=now,
                signature=str(info.get("signature") or ""),
                result=str(skip),
            )
            lines.append(f"idle-recovery {skip} seat={pick} id={rid}")
            return lines
        _mark_recycleseat_sent(home, pick, now=now, rid=rid)
        _record_idle_seat_recovery(
            home,
            pick,
            now=now,
            signature=str(info.get("signature") or ""),
            result="sent",
        )
        lines.append(f"idle-recovery recycleseat={pick} id={rid}")
    except Exception as exc:  # noqa: BLE001
        _record_idle_seat_recovery(
            home,
            pick,
            now=now,
            signature=str(info.get("signature") or ""),
            result=f"failed:{type(exc).__name__}",
        )
        lines.append(f"idle-recovery recycle_failed:{pick}:{type(exc).__name__}")
    return lines



# FR #7334 / #7574 / #7616: recycle one live eligible idle seat when no eligible
# reviewer has lasted 5 minutes (not "idle author / fewest commits").
NO_ELIGIBLE_RECYCLE_AFTER_S = 300.0


def author_touch_count(row: dict, nick: str) -> int:
    """Commits attributed to ``nick`` on this MRB. Missing counts sort last."""
    counts = row.get("author_commit_counts")
    if not isinstance(counts, dict):
        return 1
    want = (canonical_worker_nick(nick) or nick or "").strip().lower()
    for key, val in counts.items():
        got = (canonical_worker_nick(str(key)) or str(key) or "").strip().lower()
        if got == want:
            try:
                return int(val)
            except (TypeError, ValueError):
                return 1
    return 1


def mrb_offer_nick(
    row: dict,
    candidates,
    live: set[str],
    *,
    free: set[str] | None = None,
) -> str:
    """First candidate that is not an exact author seat (fresh recycled ids qualify).

    FR #9478: optional ``free`` softens same-machine MRB block (busy other-machine
    does not strand siblings). Prefer cross-machine candidates first.
    """
    live_set = set(live or set())
    ordered = list(candidates or [])
    # FR #9478: prefer cross-machine reviewers ahead of same-machine siblings.
    author_mids: set[str] = set()
    for a in row_author_seats(row):
        p = bobreport.parse_seat_nick(a)
        if p:
            author_mids.add(bobreport.fold_machine_id(p[0]))

    def _cross_key(raw: object) -> tuple:
        nick = (canonical_worker_nick(str(raw)) or str(raw) or "").strip()
        p = bobreport.parse_seat_nick(nick) if nick else None
        mid = bobreport.fold_machine_id(p[0]) if p else ""
        same = 1 if mid and mid in author_mids else 0
        return (same, nick.lower())

    try:
        ordered = sorted(ordered, key=_cross_key)
    except Exception:
        pass
    for raw in ordered:
        nick = (canonical_worker_nick(str(raw)) or str(raw) or "").strip()
        if not nick:
            continue
        if review_blocked_for_author(
            row, nick, live_set | {nick}, free=free
        ):
            continue
        return nick
    return ""


def _idle_author_least_commits(row: dict, idle: set[str], accepted: list | None) -> str:
    busy = set()
    for acc in accepted or []:
        if not isinstance(acc, dict):
            continue
        holder = str(acc.get("accepted_by") or acc.get("nick") or "").strip()
        canon = (canonical_worker_nick(holder) or holder).strip().lower()
        if canon:
            busy.add(canon)
    idle_l = {
        (canonical_worker_nick(n) or n or "").strip().lower()
        for n in idle
        if (canonical_worker_nick(n) or n or "").strip()
    }
    cands = []
    for author in row_author_seats(row):
        key = author.lower()
        if key not in idle_l or key in busy:
            continue
        cands.append(author)
    if not cands:
        return ""
    cands.sort(key=lambda n: (author_touch_count(row, n), n.lower()))
    return cands[0]


def _live_eligible_idle_reviewer(
    row: dict,
    idle: set[str],
    live: set[str],
    ledger: dict | None,
) -> str:
    """FR #7574: a live idle seat that would be eligible. Stale, author, and give-up seats are out."""
    live_l = {
        (canonical_worker_nick(n) or n or "").strip().lower()
        for n in (live or set())
        if (canonical_worker_nick(n) or n or "").strip()
    }
    found: list[str] = []
    for raw in idle or set():
        nick = (canonical_worker_nick(str(raw)) or str(raw) or "").strip()
        if not nick or nick.lower() not in live_l:
            continue
        if _mrb_idle_block_reason(row, nick, set(live), ledger):
            continue
        found.append(nick)
    found.sort(key=lambda n: n.lower())
    return found[0] if found else ""


def maybe_recycle_stuck_no_eligible_reviewer(
    home: Path,
    *,
    idle: set[str] | None = None,
    live: set[str] | None = None,
    now: float | None = None,
    accepted: list | None = None,
    install_root=None,
    ledger: dict | None = None,
) -> list[str]:
    """FR #7334 / #7574 / #7616: one !recycleseat for a live eligible idle seat.

    Fires when an offerable MRB has had no eligible reviewer for more than
    five minutes. Pick is ``_live_eligible_idle_reviewer`` (live, idle, not
    author/committer/give-up). Busy seats are never recycled. One #bobiverse
    line names the seat. A later fresh seat id is not an author, so the offer
    path can hand it the MRB.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    seats_live = set(live) if live is not None else live_seat_nicks(home)
    seats_idle = set(idle) if idle is not None else free_seat_nicks(home, seats_live)
    led = ledger if ledger is not None else ledger_load(home)
    lines: list[str] = []
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            changed = False
            target_row = None
            target_nick = ""
            for row in doc.get("unaccepted") or []:
                if not isinstance(row, dict) or _canon_task(row) != "MRB":
                    continue
                if not mrb_row_offerable(row):
                    continue
                if mrb_has_eligible_reviewer(home, row, seats_live, ledger=led, now=now_f):
                    popped = row.pop("no_eligible_since", None) is not None
                    popped = row.pop("no_eligible_reported", None) is not None or popped
                    if popped:
                        changed = True
                    continue
                try:
                    since = float(row.get("no_eligible_since") or 0)
                except (TypeError, ValueError):
                    since = 0.0
                if since <= 0:
                    row["no_eligible_since"] = now_f
                    changed = True
                    continue
                if (now_f - since) < float(NO_ELIGIBLE_RECYCLE_AFTER_S):
                    continue
                pick = _live_eligible_idle_reviewer(row, seats_idle, seats_live, led)
                if not pick:
                    if not row.get("no_eligible_reported"):
                        row["no_eligible_reported"] = True
                        changed = True
                        repo = str(row.get("repo") or "")
                        ident = _norm_row_id(row.get("id"))
                        lines.append(f"no_eligible_reviewer {repo}{ident}")
                    continue
                blocked = recycleseat_send_blocked_reason(home, pick, now=now_f)
                if blocked:
                    continue
                target_row = row
                target_nick = pick
                break
            if changed:
                _write_queue(queue_path(home), doc)
            if not target_row or not target_nick:
                return lines
            root = resolve_recycleseat_install_root(home, install_root)
            import recycleseat as _rs

            rid = _rs.write_request(
                _rs.queue_dir(root),
                target_nick,
                "jeeves",
                "no-eligible-reviewer",
                now=now_f,
            )
            skip = enqueue_recycleseat_shop_only(home, target_nick)
            repo = str(target_row.get("repo") or "")
            ident = _norm_row_id(target_row.get("id"))
            if skip:
                lines.append(f"no-eligible-reviewer {skip} seat={target_nick} id={rid}")
                return lines
            _mark_recycleseat_sent(home, target_nick, now=now_f, rid=rid)
            # Restart the 5-minute clock so stall scans do not recycle every author.
            target_row["no_eligible_since"] = now_f
            _write_queue(queue_path(home), doc)
            notice = (
                f"recycled {target_nick} for no_eligible_reviewer "
                f"{repo}{ident} (live eligible idle seat)"
            )
            bobreport.enqueue_chair_fleet_privmsg(home, notice, channel="#bobiverse")
            lines.append(f"no-eligible-reviewer recycleseat={target_nick} id={rid}")
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return lines
    return lines


def heal_mrb_reviewer_deadlock(
    home: Path,
    *,
    idle: set[str] | None = None,
    live: set[str] | None = None,
    install_root=None,
    now: float | None = None,
    locked_doc: dict | None = None,
    cooldown_s: float | None = None,
    last_activity: dict | None = None,
    accepted: list | None = None,
) -> list[str]:
    """FR #5163 / #6256: resolve idle-seat MRB reviewer deadlock.

    1. Cross give-up: clear give-ups for idle non-author seats so an offer can proceed.
    2. Author-only: flag MRBs (FR #5889). When a fresh same-machine session would
       clear exact-seat self_mrb, also issue one bounded shop-only !recycleseat
       (FR #6256 idle-seat recovery). Never erase author/implementer provenance.

    Returns human-readable heal lines (empty when no action).
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    cool = (
        float(cooldown_s)
        if cooldown_s is not None
        else float(MRB_REVIEWER_DEADLOCK_COOLDOWN_S)
    )
    seats_live = set(live) if live is not None else live_seat_nicks(home)
    seats_idle = set(idle) if idle is not None else free_seat_nicks(home, seats_live)
    ledger = ledger_load(home)

    def _detect(doc_rows):
        return detect_mrb_reviewer_deadlock(
            home,
            idle=seats_idle,
            live=seats_live,
            rows=doc_rows,
            ledger=ledger,
            now=now_f,
        )

    lines: list[str] = []
    cleared_n = 0

    def _apply_clear(doc: dict, info: dict) -> int:
        n = 0
        seen: set[tuple[str, str, str]] = set()
        for row, nick in info.get("clearable") or []:
            repo = str(row.get("repo") or "")
            ident = _norm_row_id(row.get("id"))
            key = (_repo_key(repo), ident, _canon_ledger_nick(nick))
            if key in seen:
                continue
            seen.add(key)
            for r in doc.get("unaccepted") or []:
                if not isinstance(r, dict):
                    continue
                if _repo_key(str(r.get("repo") or "")) != key[0]:
                    continue
                if _norm_row_id(r.get("id")) != ident:
                    continue
                _strip_giveup_seat_from_row(r, nick)
                try:
                    gc = int(r.get("giveup_count") or 0)
                except (TypeError, ValueError):
                    gc = 0
                if gc > 0:
                    r["giveup_count"] = gc - 1
                r.pop("cooldown_until", None)
                n += 1
                with contextlib.suppress(Exception):
                    ledger_clear_giveup(home, repo, ident, nick=nick, task="MRB")
        return n

    def _flag_author_only(doc: dict, info: dict) -> int:
        """FR #5889: author-only deadlock flags MRBs; never !recycleseat."""
        nonlocal lines
        n = 0
        want = {
            (
                _repo_key(str(r.get("repo") or "")),
                _norm_row_id(r.get("id")),
            )
            for r in (info.get("rows") or [])
            if isinstance(r, dict)
        }
        for r in doc.get("unaccepted") or []:
            if not isinstance(r, dict):
                continue
            key = (_repo_key(str(r.get("repo") or "")), _norm_row_id(r.get("id")))
            if key not in want:
                continue
            r["author_only_deadlock"] = True
            r["author_only_deadlock_ts"] = now_f
            n += 1
        if n:
            lines.append(
                f"mrb-reviewer-deadlock author_only flagged={n}"
            )
        else:
            lines.append(
                "mrb-reviewer-deadlock author_only flagged=0"
            )
        return n

    def _stamp(info: dict) -> None:
        _save_mrb_deadlock_state(
            home,
            {
                "signature": info["signature"],
                "ts": now_f,
                "kind": info["kind"],
                "cleared": cleared_n,
            },
        )

    try:
        if locked_doc is not None:
            info = _detect(list(locked_doc.get("unaccepted") or []))
            if not info:
                return []
            st = _load_mrb_deadlock_state(home)
            last_sig = str(st.get("signature") or "")
            last_ts = float(st.get("ts") or 0)
            if last_sig == info["signature"] and (now_f - last_ts) < cool:
                return []
            if info["kind"] == "cross_giveup":
                cleared_n = _apply_clear(locked_doc, info)
                if cleared_n:
                    lines.append(
                        f"mrb-reviewer-deadlock cross_giveup cleared={cleared_n}"
                    )
            else:
                _flag_author_only(locked_doc, info)
                lines.extend(
                    maybe_recycle_author_only_idle_seat(
                        home,
                        info,
                        now=now_f,
                        install_root=install_root,
                        last_activity=last_activity,
                        accepted=accepted
                        if accepted is not None
                        else list(locked_doc.get("accepted") or []),
                        cooldown_s=cool,
                    )
                )
            _stamp(info)
            return lines

        with _lock(home):
            doc = _load_queue_unlocked(home)
            info = _detect(list(doc.get("unaccepted") or []))
            if not info:
                return []
            st = _load_mrb_deadlock_state(home)
            last_sig = str(st.get("signature") or "")
            last_ts = float(st.get("ts") or 0)
            if last_sig == info["signature"] and (now_f - last_ts) < cool:
                return []
            if info["kind"] == "cross_giveup":
                cleared_n = _apply_clear(doc, info)
                if cleared_n:
                    _write_queue(queue_path(home), doc)
                    lines.append(
                        f"mrb-reviewer-deadlock cross_giveup cleared={cleared_n}"
                    )
            else:
                if _flag_author_only(doc, info):
                    _write_queue(queue_path(home), doc)
                lines.extend(
                    maybe_recycle_author_only_idle_seat(
                        home,
                        info,
                        now=now_f,
                        install_root=install_root,
                        last_activity=last_activity,
                        accepted=accepted
                        if accepted is not None
                        else list(doc.get("accepted") or []),
                        cooldown_s=cool,
                    )
                )
            _stamp(info)
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return lines
    return lines


def bored_latency_heal_state_path(home: Path) -> Path:
    return _root(home) / BORED_LATENCY_HEAL_STATE


def _empty_bored_latency_heal_state() -> dict:
    return {"nicks": {}, "recycles": {}, "holds": {}}


def _load_bored_latency_heal_state(home: Path) -> dict:
    empty = _empty_bored_latency_heal_state()
    path = bored_latency_heal_state_path(home)
    if not path.is_file():
        return empty
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return empty
    if not isinstance(raw, dict):
        return empty
    nicks = raw.get("nicks")
    if not isinstance(nicks, dict):
        nicks = {}
    recycles = raw.get("recycles")
    if not isinstance(recycles, dict):
        recycles = {}
    holds = raw.get("holds")
    if not isinstance(holds, dict):
        holds = {}
    return {"nicks": nicks, "recycles": recycles, "holds": holds}


def _save_bored_latency_heal_state(home: Path, state: dict) -> None:
    path = bored_latency_heal_state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    prev = _load_bored_latency_heal_state(home)
    nicks_src = state.get("nicks") if isinstance(state.get("nicks"), dict) else prev.get("nicks")
    rec_src = (
        state.get("recycles") if isinstance(state.get("recycles"), dict) else prev.get("recycles")
    )
    hold_src = state.get("holds") if isinstance(state.get("holds"), dict) else prev.get("holds")
    clean = _empty_bored_latency_heal_state()
    for key, val in (nicks_src or {}).items():
        nick = (canonical_worker_nick(str(key)) or str(key or "")).strip()
        if not nick:
            continue
        try:
            clean["nicks"][nick] = float(val)
        except (TypeError, ValueError):
            continue
    for key, val in (rec_src or {}).items():
        mid = str(key or "").strip().lower()
        if not mid:
            continue
        stamps = []
        for ts in val if isinstance(val, list) else []:
            try:
                stamps.append(float(ts))
            except (TypeError, ValueError):
                continue
        if stamps:
            clean["recycles"][mid] = stamps
    for key, val in (hold_src or {}).items():
        mid = str(key or "").strip().lower()
        if not mid or not isinstance(val, dict):
            continue
        try:
            clean["holds"][mid] = {
                "at": float(val.get("at") or 0),
                "reason": str(val.get("reason") or "recycle-loop"),
                "reported": bool(val.get("reported")),
            }
        except (TypeError, ValueError):
            continue
    path.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")


def _bored_latency_slot_id(nick: str) -> str:
    """Machine slot for recycle-window / hold (FR #6774). PID must not be the key."""
    import stall_detectors as _sd

    return str(_sd._bored_latency_stable_key(nick) or "").strip().lower()


def _prune_bored_latency_recycles(state: dict, now_f: float) -> None:
    window = float(BORED_LATENCY_RECYCLE_WINDOW_S)
    rec = state.get("recycles") if isinstance(state.get("recycles"), dict) else {}
    pruned: dict[str, list[float]] = {}
    for mid, stamps in rec.items():
        keep = [
            float(ts)
            for ts in (stamps if isinstance(stamps, list) else [])
            if (now_f - float(ts)) < window
        ]
        if keep:
            pruned[str(mid)] = keep
    state["recycles"] = pruned


def clear_bored_latency_recycle_holds(
    home: Path, machine: str | None = None
) -> None:
    """FR #6774: drop recycle-loop holds (all, or one machine). Used by !resync."""
    state = _load_bored_latency_heal_state(home)
    holds = state.get("holds") if isinstance(state.get("holds"), dict) else {}
    rec = state.get("recycles") if isinstance(state.get("recycles"), dict) else {}
    if machine:
        mid = str(machine).strip().lower().lstrip("#")
        holds.pop(mid, None)
        rec.pop(mid, None)
    else:
        holds = {}
        rec = {}
    state["holds"] = holds
    state["recycles"] = rec
    _save_bored_latency_heal_state(home, state)


def _clear_bored_latency_holds_on_healthy_seats(
    state: dict,
    *,
    idle: set[str],
    last_bored: dict,
    last_activity: dict,
    now_f: float,
) -> None:
    """Clear hold when a slot !bored on time, or a new seat shows recent activity."""
    import stall_detectors as _sd

    holds = state.get("holds") if isinstance(state.get("holds"), dict) else {}
    if not holds:
        return
    thresh = float(_sd.BORED_LATENCY_S)
    drop: list[str] = []
    for nick in idle:
        mid = _bored_latency_slot_id(nick)
        if not mid or mid not in holds:
            continue
        bored_at = last_bored.get(nick)
        act_at = last_activity.get(nick)
        lag = None
        if bored_at is not None:
            lag = now_f - float(bored_at)
        elif act_at is not None:
            lag = now_f - float(act_at)
        hold_at = float((holds.get(mid) or {}).get("at") or 0)
        if lag is not None and lag < thresh:
            drop.append(mid)
        elif act_at is not None and float(act_at) > hold_at:
            drop.append(mid)
    rec = state.get("recycles") if isinstance(state.get("recycles"), dict) else {}
    for mid in drop:
        holds.pop(mid, None)
        rec.pop(mid, None)
    state["holds"] = holds
    state["recycles"] = rec


def _report_bored_latency_recycle_hold(home: Path, item: dict, now_f: float) -> None:
    """One stall_filer intake per fingerprint (deduped)."""
    import stall_filer as _sf
    import stall_detectors as _sd

    finding = dict(item)
    if not finding.get("fingerprint"):
        finding["fingerprint"] = _sd.fingerprint(
            _sd.BORED_LATENCY_ID, str(finding.get("key") or "")
        )
    title = str(finding.get("title") or "bored-latency recycle-loop")
    finding["title"] = f"{title} (held recycle-loop)"
    ev = dict(finding.get("evidence") or {})
    ev["held"] = "recycle-loop"
    finding["evidence"] = ev
    with contextlib.suppress(Exception):
        _sf.apply_findings([finding], home=home, now=now_f)


def heal_bored_latency(
    home: Path,
    *,
    idle: set[str] | None = None,
    last_bored: dict | None = None,
    last_activity: dict | None = None,
    accepted: list | None = None,
    unaccepted: list | None = None,
    now: float | None = None,
    install_root=None,
    cooldown_s: float | None = None,
) -> list[str]:
    """FR #5701 / #5756: recycle idle seats past bored-latency with no recent !bored.

    Chair-local recycleseat JSON never reaches a remote tray (FR #5220). PRIVMSG
    ``!recycleseat <nick> <machine>`` on the seat shop only (never ``#bobiverse``).
    Rate-limited per nick (shared with MRB deadlock heal).

    FR #6774: at most ``BORED_LATENCY_RECYCLE_LIMIT`` recycles per machine slot
    in ``BORED_LATENCY_RECYCLE_WINDOW_S``. Past that, hold as stalled
    (reason=recycle-loop) and file one stall_filer report. Hold clears on
    on-time !bored, recent activity after the hold, or ``!resync``.

    ``unaccepted`` is the same queue snapshot ``detect_bored_latency`` uses for
    live-offer suppression (PR #5852). Omit it only when the caller has no
    offer rows; an empty list does not load the queue.
    """
    import time as _time

    import stall_detectors as _sd

    now_f = _time.time() if now is None else float(now)
    cool = (
        float(cooldown_s)
        if cooldown_s is not None
        else float(RECYCLESEAT_IRC_COOLDOWN_S)
    )
    seats_idle = set(idle) if idle is not None else free_seat_nicks(home)
    bored_map = dict(last_bored or {})
    act_map = dict(last_activity or {})
    state = _load_bored_latency_heal_state(home)
    _prune_bored_latency_recycles(state, now_f)
    _clear_bored_latency_holds_on_healthy_seats(
        state,
        idle=seats_idle,
        last_bored=bored_map,
        last_activity=act_map,
        now_f=now_f,
    )
    snap = {
        "now": now_f,
        "idle": seats_idle,
        "last_bored": bored_map,
        "last_activity": act_map,
        "accepted": list(accepted or []),
        "unaccepted": list(unaccepted or []),
    }
    findings = _sd.detect_bored_latency(snap)
    nick_ts = state.get("nicks") if isinstance(state.get("nicks"), dict) else {}
    recycles = state.get("recycles") if isinstance(state.get("recycles"), dict) else {}
    holds = state.get("holds") if isinstance(state.get("holds"), dict) else {}
    lines: list[str] = []
    root = resolve_recycleseat_install_root(home, install_root)
    limit = int(BORED_LATENCY_RECYCLE_LIMIT)

    for item in findings:
        nick = str((item.get("evidence") or {}).get("nick") or item.get("key") or "").strip()
        if not nick:
            continue
        canon = (canonical_worker_nick(nick) or nick).strip()
        slot = _bored_latency_slot_id(canon)
        if slot and slot in holds:
            if not (holds[slot] or {}).get("reported"):
                _report_bored_latency_recycle_hold(home, item, now_f)
                holds[slot]["reported"] = True
            lines.append(
                f"bored-latency held seat={canon} machine={slot} reason=recycle-loop"
            )
            continue
        recent = list(recycles.get(slot) or []) if slot else []
        prior = nick_ts.get(canon)
        lag_pre = (item.get("evidence") or {}).get("lag_s")
        if prior:
            # FR #6986: same nick still lagging after a prior recycleseat.
            # Do not change recycle thresholds; log that the recycle had no effect.
            attempts = len(recent) + 1
            lines.append(
                f"bored-latency recycle-no-effect seat={canon} attempts={attempts} lag_s={lag_pre}"
            )
        if slot and len(recent) >= limit:
            holds[slot] = {
                "at": now_f,
                "reason": "recycle-loop",
                "reported": True,
            }
            _report_bored_latency_recycle_hold(home, item, now_f)
            lines.append(
                f"bored-latency held seat={canon} machine={slot} reason=recycle-loop"
            )
            continue
        # FR #5889: seat-keyed pending / ACK wait / busy / recent-ack / cooldown.
        blocked = recycleseat_send_blocked_reason(
            home, canon, now=now_f, cooldown_s=cool
        )
        if blocked:
            lines.append(f"bored-latency {blocked} seat={canon}")
            continue
        try:
            import recycleseat as _rs

            rid = _rs.write_request(
                _rs.queue_dir(root),
                canon,
                "jeeves",
                "bored-latency",
                now=now_f,
            )
            skip = None
            with contextlib.suppress(Exception):
                skip = enqueue_recycleseat_shop_only(home, canon)
            if skip:
                lines.append(f"bored-latency {skip} seat={canon} id={rid}")
                nick_ts[canon] = now_f
                _mark_recycleseat_sent(home, canon, now=now_f, rid=rid)
                continue
            nick_ts[canon] = now_f
            _mark_recycleseat_sent(home, canon, now=now_f, rid=rid)
            if slot:
                recent.append(now_f)
                recycles[slot] = recent
            lag = (item.get("evidence") or {}).get("lag_s")
            lines.append(
                f"bored-latency recycleseat={canon} id={rid} lag_s={lag}"
            )
        except Exception as exc:  # noqa: BLE001
            lines.append(
                f"bored-latency recycle_failed:{canon}:{type(exc).__name__}"
            )

    state["nicks"] = nick_ts
    state["recycles"] = recycles
    state["holds"] = holds
    _save_bored_latency_heal_state(home, state)
    return lines


def heal_require_machine_all_gave_up(
    home: Path, live: set[str] | None = None
) -> list[str]:
    """Clear ledger giveup when every live pin-machine seat gave up a living FR (FR #2446).

    FR #2486: skips Living FR / Refs-only tracking umbrellas so operator GIVEUPs stick.

    Returns human-readable heal lines (repo#id + nick count). Shop IRC stays short;
    callers log these for operators / monitors.
    """
    try:
        path = queue_path(home)
        raw = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
        rows = [r for r in (raw.get("unaccepted") or []) if isinstance(r, dict)]
    except Exception:
        return []
    seats = live if live is not None else live_seat_nicks(home)
    healed: list[str] = []
    for row in rows:
        if row_skip_pin_ledger_heal_reason(row):
            continue
        blocked = require_machine_all_live_gave_up(home, row, seats)
        if not blocked:
            continue
        repo = str(row.get("repo") or "")
        ident = str(row.get("id") or "")
        task = _canon_task(row)
        n = 0
        for nick in blocked:
            n += ledger_clear_giveup(home, repo, ident, nick=nick, task=task)
        if n:
            healed.append(f"{repo}{ident if str(ident).startswith('#') else '#' + str(ident)} cleared={n}")
    return healed


def row_has_false_needs_human(row: dict) -> bool:
    """FR #8427: True when needs_human is set but the give-up was infra-soft.

    FR #8375 made holder_bored (and the other infra/soft seat-churn reasons)
    never increment giveup_count nor stamp needs_human. A row that still carries
    ``needs_human`` with a ``giveup_reason`` from that set is a stale/false stamp
    that starves the offer queue (class of #8391/#8396/#8413).
    """
    if not isinstance(row, dict):
        return False
    if not _needs_human_flag(row):
        return False
    reason = str(row.get("giveup_reason") or "").strip()
    return is_infra_soft_giveup_reason(reason)


def heal_false_needs_human_for_infra_soft(home: Path) -> list[str]:
    """FR #8427: clear needs_human false positives stamped by infra-soft GIVEUPs.

    Clears ``needs_human`` (and the give-up state) on unaccepted/accepted rows
    whose ``giveup_reason`` is holder_bored / offer-timeout / hard-ceiling /
    worktree-create-failed (the FR #8375 infra-soft set). Those reasons must
    never stamp needs_human, so a stamp on such a row is a stale false positive
    that re-offers after the clear.

    Returns repo#id heal lines for monitor/ops logs.
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, ValueError):
                return []
            healed: list[str] = []
            changed = False
            for bucket in ("unaccepted", "accepted"):
                for row in list(doc.get(bucket) or []):
                    if not row_has_false_needs_human(row):
                        continue
                    repo = str(row.get("repo") or "")
                    ident = str(row.get("id") or "")
                    row.pop("needs_human", None)
                    row["giveup_count"] = 0
                    row.pop("giveup_seats", None)
                    row.pop("giveup_agent_kinds", None)
                    row["hard_ceiling_count"] = 0
                    row.pop("cooldown_until", None)
                    changed = True
                    healed.append(
                        f"{repo}{ident if ident.startswith('#') else '#' + ident}"
                    )
            if changed:
                try:
                    _write_queue(queue_path(home), doc)
                except OSError:
                    return []
            return healed
    except (TimeoutError, OSError):
        return []


def _row_link_keys(row: dict) -> list[str]:
    repo = str(row.get("repo") or "")
    refs = normalize_row_refs(row.get("refs") if isinstance(row, dict) else None)
    keys = [_lkey(repo, row.get("id"))]
    for r in refs:
        keys.append(_lkey(repo, r))
    sup = str(row.get("supersedes") or "").strip()
    if "#" in sup:
        keys.append(sup.lower())
    return list(dict.fromkeys(keys))


def _uat_cycle_fr_touch_count(ledger: dict, row: dict, nick: str) -> int:
    """How many link keys of this repo UAT the seat holds role ``FR`` on (FR #1407)."""
    me = _canon_ledger_nick(nick)
    if not me:
        return 0
    tc = ledger.get("touch") or {}
    n = 0
    for k in _row_link_keys(row):
        roles = (tc.get(k) or {}).get(me) or []
        if "FR" in roles:
            n += 1
    return n


def ledger_why_is_self_uat(why: str) -> bool:
    """True when a ledger block reason is self-UAT (authored or MRB'd the cycle)."""
    w = (why or "").lower()
    return ("implemented" in w) or ("reviewed" in w) or ("no self-uat" in w)


def repo_uat_no_eligible_live_seat(
    ledger: dict, row: dict, live
) -> bool:
    """FR #2939: True when every live seat is giveup- or self-UAT-blocked for repo UAT."""
    if not is_repo_uat(row):
        return False
    seats = {s for s in (live or set()) if str(s or "").strip()}
    if not seats:
        return False
    for s in seats:
        if row_gave_up_by(row, s, live=seats):
            continue
        why = _ledger_blocks(ledger, row, s)
        if not why:
            return False
        if "gave up" in why:
            continue
        if ledger_why_is_self_uat(why):
            continue
        # Other ledger block (e.g. FR-done hold) - still not eligible, keep scanning.
        continue
    return True


def stamp_repo_uat_self_uat_escalate(row: dict) -> bool:
    """Stamp needs_human + self_uat_escalated on a queue row (in-memory). True if newly stamped."""
    if not is_repo_uat(row):
        return False
    already = bool(row.get("self_uat_escalated"))
    row["needs_human"] = True
    row["self_uat_escalated"] = True
    return not already


def announce_repo_uat_self_uat_escalate(home: Path, repo: str) -> bool:
    """One-shot #bobiverse announce for stranded repo UAT (FR #2939)."""
    repo_s = (repo or "").strip() or "repo"
    msg = (
        f"UAT {repo_s}#0 stranded: every live seat is self-UAT "
        f"(authored or MRB'd this cycle). Needs a fresh/uninvolved seat or a human."
    )
    try:
        return bool(bobreport.enqueue_chair_fleet_privmsg(home, msg, bobreport.FLEET_CHANNEL))
    except Exception:
        return False


def maybe_escalate_repo_uat_all_self_uat(
    home: Path,
    row: dict,
    *,
    live=None,
    ledger: dict | None = None,
    locked_doc: dict | None = None,
) -> bool:
    """FR #2939: when no live seat can take repo UAT (all self-UAT / giveup), escalate once.

    Stamps ``needs_human`` + ``self_uat_escalated`` on the queue row and announces on
    #bobiverse that UAT needs a fresh/uninvolved seat or a human. Returns True when
    this call performed (or confirmed) the escalation.

    When ``locked_doc`` is provided the caller already holds the queue lock - mutate that
    doc in place and do not re-acquire (file lock is not re-entrant).
    """
    if not is_repo_uat(row):
        return False
    if row.get("self_uat_escalated") and row_needs_human(row, ""):
        return True
    led = ledger if ledger is not None else ledger_load(home)
    seats = set(live) if live is not None else live_seat_nicks(home)
    if not repo_uat_no_eligible_live_seat(led, row, seats):
        return False
    repo = str(row.get("repo") or "").strip() or "repo"
    newly = False

    def _apply(doc: dict) -> bool:
        nonlocal newly
        for r in doc.get("unaccepted") or []:
            if not isinstance(r, dict) or not is_repo_uat(r):
                continue
            if str(r.get("repo") or "").strip().lower() != repo.lower():
                continue
            newly = stamp_repo_uat_self_uat_escalate(r)
            row["needs_human"] = True
            row["self_uat_escalated"] = True
            return True
        # Row not yet in queue (unit test) - stamp the caller copy only.
        newly = stamp_repo_uat_self_uat_escalate(row)
        return newly

    try:
        if locked_doc is not None:
            _apply(locked_doc)
        else:
            with _lock(home):
                doc = _load_queue_unlocked(home)
                if _apply(doc):
                    _write_queue(queue_path(home), doc)
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return False
    if newly:
        announce_repo_uat_self_uat_escalate(home, repo)
    return True


def ledger_blocks(ledger: dict, row: dict, nick: str, live=None) -> str:
    """See ``_ledger_blocks``.

    FR #2939: repo UAT self-UAT (FR or MRB cycle touch) is never escaped. The old
    all-blocked escape (#1407 / #1416) offered a seat that then GIVEUP'd per the
    worker skill. When every live seat is self-UAT / giveup blocked, call
    ``maybe_escalate_repo_uat_all_self_uat`` (offer / empty-offer paths) instead.
    ``live`` remains in the signature for call-site compatibility.
    """
    _ = live  # retained for API compatibility / escalate callers
    return _ledger_blocks(ledger, row, nick)


def _ledger_blocks(ledger: dict, row: dict, nick: str) -> str:
    """Why this seat must not get this row ('' = ok), from the durable ledger.

    * a seat that gave up the row (or its linked PR/issue) in the same MRB/UAT/FR family never gets it again;
    * UAT: blocked for the FR implementer and the MRB reviewer of any linked issue/PR;
    * MRB: blocked for the FR implementer of any linked issue/PR.
    * repo-level UAT (FR #2939): same as UAT - FR *or* MRB cycle touch is self-UAT.
    """
    me = _canon_ledger_nick(nick)
    if not me:
        return ""
    task = _canon_task(row)
    keys = _row_link_keys(row)
    if task == "FR":
        done_ts = _parse_iso_ts(str((ledger.get("fr_done") or {}).get(_lkey(str(row.get("repo") or ""), row.get("id"))) or ""))
        if done_ts is not None and (time.time() - done_ts) < FR_DONE_HOLD_S:
            return "FR already delivered (PR pending merge)"
    gu = ledger.get("giveup") or {}
    own = _lkey(str(row.get("repo") or ""), row.get("id"))
    repo_level = is_repo_uat(row)
    for k in keys:
        tl = (gu.get(k) or {}).get(me) or []
        if k == own and task in tl:
            return f"{nick} already gave up {k}"
        # t860u: a GIVEUP on a LINKED row only blocks the same job kind (a seat that gave up the UAT of a
        # linked issue as "self-UAT" can still review the PR); only the row's own key blocks any kind.
        if not repo_level and task in ("MRB", "UAT") and task in tl:
            return f"{nick} already gave up linked {k}"
    if task in ("MRB", "UAT"):
        # UAT (including repo-level #0): FR implementer OR MRB reviewer (FR #2939).
        # MRB rows: FR implementer only.
        bad = {"FR", "MRB"} if task == "UAT" else {"FR"}
        tc = ledger.get("touch") or {}
        for k in keys:
            roles = (tc.get(k) or {}).get(me) or []
            if bad & set(roles):
                return f"{nick} implemented/reviewed {k} (no self-{task})"
    return ""


def ledger_note_event(home: Path, nick: str, verb: str, task: str, repo: str, ident: str, job: dict | None = None,
                      result: str = "", url: str = "") -> None:
    """Hook for the shop wire: ACK/DONE/NACK/GIVEUP of ``task repo#ident`` by ``nick``."""
    verb_u = (verb or "").upper()
    task_u = (task or "").upper()
    job = job or {}
    keys = _row_link_keys({"repo": repo, "id": ident, "refs": job.get("refs") or [], "supersedes": job.get("supersedes") or ""})
    if verb_u in ("GIVEUP", "NACK"):
        refs = job.get("refs") or []
        if isinstance(refs, str):
            refs = [x for x in re.split(r"[,\s]+", refs) if x]
        ledger_giveup(home, nick, repo, task_u, ident, refs)
        return
    if verb_u == "DONE" and task_u == "UAT" and (job.get("repo_uat") or str(ident) == "#0"):
        ledger_uat_cycle_done(home, repo)
    if verb_u == "DONE" and task_u == "FR":
        def _fd(doc: dict) -> None:   # t856u: FR delivered (PR open elsewhere): do not re-offer the issue while it waits for the merge
            doc.setdefault("fr_done", {})[_lkey(repo, ident)] = _utc_now()
        try:
            _ledger_update(home, _fd)
        except OSError:
            pass
    if verb_u == "DONE" and task_u == "MRB":
        # FR #1323: survive done[] trim / resync races - do not re-offer this MRB.
        stamp_mrb_done(home, repo, ident)
    if verb_u == "DONE":
        # FR #4642: per-seat DONE stamp. A later ACK of the same job is a duplicate
        # unless an offer was stamped after this DONE.
        with contextlib.suppress(Exception):
            ledger_stamp_seat_job(
                home, nick, {"repo": repo, "task": task_u, "id": ident}, "done"
            )
    # t860u: working an FR (ACK/DONE, "DONE existing PR, no duplicate", URL of a PR that already existed) is
    # NOT authorship: it is recorded as the informational role "FRW" and never blocks review. Only the PR's
    # real commit authors (``ledger_refresh_authors`` -> role "FR") and the MRB reviewer block review/UAT.
    if verb_u in ("ACK", "DONE") and task_u in ("FR", "MRB"):
        ledger_touch(home, nick, repo, "FRW" if task_u == "FR" else task_u, keys)
    if verb_u == "DONE" and task_u == "FR":
        parsed = parse_github_pull_url(url or result or "")
        if parsed:
            ledger_touch(home, nick, parsed[0], "FRW", [_lkey(parsed[0], parsed[1])])


def seat_commit_counts_from_payload(data) -> dict[str, int]:
    """Count commits whose git author or committer name is a seat nick (FR #7338).

    One commit counts once per seat even when author and committer are the same nick.
    """
    counts: dict[str, int] = {}
    for commit in data if isinstance(data, list) else []:
        seen: set[str] = set()
        blob = commit.get("commit") if isinstance(commit, dict) else {}
        blob = blob if isinstance(blob, dict) else {}
        for who in (blob.get("author") or {}, blob.get("committer") or {}):
            if not isinstance(who, dict):
                continue
            name = str(who.get("name") or "").strip().lower()
            if not name or name in seen or not bobreport.parse_seat_nick(name):
                continue
            seen.add(name)
            counts[name] = counts.get(name, 0) + 1
    return counts


def _github_pr_commits(token: str, repo: str, num: str):
    api = f"https://api.github.com/repos/{repo}/pulls/{str(num).lstrip('#')}/commits?per_page=100"
    req = urllib.request.Request(api, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": "bobiverse-gitclaim"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return [] if int(getattr(e, "code", 0) or 0) in (404, 410, 422) else None
    except Exception:
        return None
    return data


def _github_token_for_home(home: Path | None) -> str:
    try:
        import gh_filer
    except Exception:
        return ""
    with _scoped_digest_home(home):
        src = gh_filer.ensure_gh_token_env()
    if src == "none":
        return ""
    return (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()


def github_pr_seat_fetcher(*, home: Path | None = None):
    """Return ``fetch(repo, num) -> set[str] | None`` of seat nicks that authored commits on a PR.

    Seats commit as their nick (``marchhare-41928``), so the PR's commit authors are the ground truth for
    "who wrote this" - independent of queue history. ``set()`` = not a PR / no seat commits; ``None`` =
    could not tell (offline / no token / transient error; not cached)."""
    token = _github_token_for_home(home)
    if not token:
        return None

    def _fetch(repo: str, num: str):
        data = _github_pr_commits(token, repo, num)
        if data is None:
            return None
        return set(seat_commit_counts_from_payload(data))

    return _fetch


def github_pr_seat_commit_counter(*, home: Path | None = None):
    """Return ``fetch(repo, num) -> dict[str, int] | None`` of seat commit counts (FR #7338)."""
    token = _github_token_for_home(home)
    if not token:
        return None

    def _fetch(repo: str, num: str):
        data = _github_pr_commits(token, repo, num)
        if data is None:
            return None
        return seat_commit_counts_from_payload(data)

    return _fetch


def stamp_mrb_author_commit_counts(home: Path, rows, fetch, *, limit: int = 8) -> int:
    """Write ``author_commit_counts`` onto MRB rows from a commit-count fetch (FR #7338)."""
    if fetch is None:
        return 0
    updates: dict[tuple[str, str], dict[str, int]] = {}
    done = 0
    for row in rows or []:
        if done >= int(limit):
            break
        if not isinstance(row, dict) or _canon_task(row) != "MRB":
            continue
        repo = str(row.get("repo") or "").strip()
        ident = _norm_row_id(row.get("id"))
        if not repo or not ident:
            continue
        try:
            counts = fetch(repo, ident.lstrip("#"))
        except Exception:
            counts = None
        if counts is None:
            continue
        done += 1
        if isinstance(counts, dict) and counts:
            updates[(_repo_key(repo), ident)] = {str(k): int(v) for k, v in counts.items()}
    if not updates:
        return done
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            changed = False
            for bucket in ("unaccepted", "accepted"):
                for row in doc.get(bucket) or []:
                    if not isinstance(row, dict):
                        continue
                    key = (_repo_key(str(row.get("repo") or "")), _norm_row_id(row.get("id")))
                    if key not in updates:
                        continue
                    row["author_commit_counts"] = updates[key]
                    changed = True
            if changed:
                _write_queue(queue_path(home), doc)
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return done
    return done


def ledger_refresh_authors(home: Path, rows, fetch, *, limit: int = 8, ttl_s: float = 6 * 3600.0) -> int:
    """Stamp the seat ledger with the commit authors of every PR behind the MRB/UAT ``rows`` (bounded).

    The PR key and every linked key of the row get ``FR`` for each seat that committed (so that seat can
    neither review nor UAT it). Results are cached per PR key for ``ttl_s``. Returns lookups done."""
    if fetch is None:
        return 0
    import time as _time

    now_f = _time.time()
    led = ledger_load(home)
    fetched = led.get("fetched") or {}
    todo: list[tuple[str, str, list[str]]] = []
    for row in rows:
        if _canon_task(row) not in ("MRB", "UAT"):
            continue
        repo = str(row.get("repo") or "")
        keys = _row_link_keys(row)
        for k in keys:
            if k in fetched and now_f - float(fetched[k]) < ttl_s:
                continue
            if all(k != t[0] for t in todo):
                # repo-level UAT: a seat that wrote PR A must not look like the author of PR B
                todo.append((k, repo, [k, keys[0]] if is_repo_uat(row) else keys))
    done = 0
    for k, repo, keys in todo[:limit]:
        num = k.rsplit("#", 1)[1]
        try:
            seats = fetch(repo, num)
        except Exception:
            seats = None
        if seats is None:
            continue
        done += 1
        def _f(doc: dict, k=k, seats=seats, keys=keys) -> None:
            doc.setdefault("fetched", {})[k] = _time.time()
            for s in seats:
                for kk in keys:
                    roles = doc["touch"].setdefault(kk, {}).setdefault(s, [])
                    if "FR" not in roles:
                        roles.append("FR")
        try:
            _ledger_update(home, _f)
        except OSError:
            pass
    return done


_ASSIGN_CMD = re.compile(
    r"(?is)^\s*!assign\s+(\S+)\s+(\S+)\s+(FR|MRB|UAT|FIX)\s+#?(\d+)\s*$"
)


def parse_assign_cmd(body: str) -> tuple[str, str, str, str] | None:
    """``!assign <worker-nick> <repo> <FR|MRB|UAT|FIX> <num>`` -> (nick, repo, TASK, '#N') or None (t849u / FR #4652)."""
    m = _ASSIGN_CMD.match(body or "")
    if not m:
        return None
    return m.group(1), m.group(2).strip().strip("{}"), m.group(3).upper(), f"#{int(m.group(4))}"


def _accepted_holder_nick(row: dict) -> str:
    """Seat that owns an accepted row (``nick`` or legacy ``accepted_by``)."""
    raw = str(row.get("nick") or row.get("accepted_by") or "").strip()
    return canonical_worker_nick(raw) or raw


def _row_to_unaccepted_retry(row: dict) -> dict:
    """FR #3400: strip accept/offer stamps and mark prior ACK void for re-offer."""
    out = dict(row)
    for key in (
        "nick",
        "channel",
        "accepted_ts",
        "accepted_by",
        "offered_to",
        "offered_ts",
        "offered_channel",
    ):
        out.pop(key, None)
    out["retry"] = True
    out["note"] = "prior ACK void"
    return out



def clear_live_mrb_hold_for_ci_red(doc: dict, repo: str, ident: str) -> list[str]:
    """FR #9924: drop accepted/offered MRB for repo#id; return holder nicks.

    Accepted rows move to ``done`` with ``result=CI-RED`` (seat freed). Unaccepted
    MRB rows for the same id are removed so CI-red tips are not re-offered as MRB.
    """
    repo_c = canonical_queue_repo(repo)
    want = _norm_row_id(ident)
    if not repo_c or not want or not isinstance(doc, dict):
        return []
    holders: list[str] = []
    done = doc.setdefault("done", [])
    kept_acc: list[dict] = []
    for row in list(doc.get("accepted") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("task") or "").upper() != "MRB":
            kept_acc.append(row)
            continue
        if canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
            kept_acc.append(row)
            continue
        if _norm_row_id(str(row.get("id") or "")) != want:
            kept_acc.append(row)
            continue
        who = _accepted_holder_nick(row) or str(
            row.get("offered_to") or row.get("nick") or ""
        ).strip()
        if who:
            holders.append(who)
        fin = dict(row)
        for key in (
            "nick",
            "channel",
            "accepted_ts",
            "accepted_by",
            "offered_to",
            "offered_ts",
            "offered_channel",
        ):
            fin.pop(key, None)
        fin["result"] = "CI-RED"
        fin["done_ts"] = _utc_now()
        fin["note"] = "FR #9924 required CI red; hold cleared for FIX"
        done.append(fin)
    doc["accepted"] = kept_acc
    kept_un: list[dict] = []
    for row in list(doc.get("unaccepted") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("task") or "").upper() != "MRB":
            kept_un.append(row)
            continue
        if canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
            kept_un.append(row)
            continue
        if _norm_row_id(str(row.get("id") or "")) != want:
            kept_un.append(row)
            continue
        who = str(row.get("offered_to") or row.get("nick") or "").strip()
        if who and who not in holders:
            holders.append(who)
        # Drop the unaccepted MRB entirely (do not re-offer while CI red).
        continue
    doc["unaccepted"] = kept_un
    if len(done) > DONE_CAP:
        doc["done"] = done[-DONE_CAP:]
    return holders


def live_mrb_hold_nicks(doc: dict, repo: str, ident: str) -> list[str]:
    """Nicks holding accepted or offered MRB for repo#id (FR #9924)."""
    repo_c = canonical_queue_repo(repo)
    want = _norm_row_id(ident)
    out: list[str] = []
    if not repo_c or not want or not isinstance(doc, dict):
        return out
    for bucket in ("accepted", "unaccepted"):
        for row in doc.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("task") or "").upper() != "MRB":
                continue
            if canonical_queue_repo(str(row.get("repo") or "")) != repo_c:
                continue
            if _norm_row_id(str(row.get("id") or "")) != want:
                continue
            if bucket == "unaccepted" and not str(row.get("offered_to") or "").strip():
                # Unoffered queued MRB is not a live hold yet.
                if not str(row.get("nick") or "").strip():
                    continue
            who = (
                _accepted_holder_nick(row)
                if bucket == "accepted"
                else str(row.get("offered_to") or row.get("nick") or "").strip()
            )
            if who and who not in out:
                out.append(who)
    return out


def _release_accepted_for_nick_unlocked(doc: dict, nick: str) -> list[dict]:
    """Move accepted rows held by ``nick`` back onto ``unaccepted`` (caller holds lock).

    FR #4624: accepted FR/PR already stamped ``state=closed`` (issues closed webhook)
    go to ``done`` as CLOSED instead - never re-enter unaccepted for re-offer.
    """
    want = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not want:
        return []
    kept: list[dict] = []
    released: list[dict] = []
    done = doc.setdefault("done", [])
    moved_closed = False
    for row in list(doc.get("accepted") or []):
        if not isinstance(row, dict):
            continue
        holder = _accepted_holder_nick(row).lower()
        if holder != want:
            kept.append(row)
            continue
        task_u = str(row.get("task") or "").upper()
        if (
            task_u in ("FR", "PR")
            and str(row.get("state") or "").strip().lower() == "closed"
        ):
            fin = dict(row)
            for key in (
                "nick",
                "channel",
                "accepted_ts",
                "accepted_by",
                "offered_to",
                "offered_ts",
                "offered_channel",
            ):
                fin.pop(key, None)
            fin["result"] = "CLOSED"
            fin["done_ts"] = _utc_now()
            fin["state"] = "closed"
            done.append(fin)
            moved_closed = True
            continue
        released.append(_row_to_unaccepted_retry(row))
    if not released and not moved_closed:
        return []
    doc["accepted"] = kept
    if released:
        doc["unaccepted"] = list(doc.get("unaccepted") or []) + released
    if moved_closed and len(done) > DONE_CAP:
        doc["done"] = done[-DONE_CAP:]
    return released


def drop_ghost_seat_after_names_miss(
    home: Path,
    nick: str,
    *,
    reason: str = "",
) -> dict:
    """FR #9347: after NAMES miss / shop-presence refuse, drop nick from offer roster.

    Ghost seats that stay on ``worker_list`` without JOIN/NAMES keep getting
    auto-offers and ``!assign`` refuses. Remove the nick from the digest
    worker_list (worker-remove), clear ``offered_to`` pins, and release any
    ACC rows. Prefer live shop members on the next offer tick.
    """
    me = (canonical_worker_nick(nick) or nick or "").strip()
    out = {
        "removed": False,
        "released_offers": 0,
        "released_accepted": 0,
        "nick": me,
        "reason": str(reason or "").strip(),
    }
    if not me:
        return out
    me_l = me.lower()
    seat = bobreport.parse_seat_nick(me)
    mid = bobreport.fold_machine_id(seat[0]) if seat else ""
    if mid:
        try:
            import chan_workers

            tracker = chan_workers.WorkerTracker(home)
            code = tracker.post(
                chan_workers.payload_for("worker-remove", mid, me)
            )
            out["removed"] = int(code or 0) in (200, 204)
        except Exception:
            out["removed"] = False
        if not out["removed"]:
            # Fall back: edit digest directly when tracker gate rejects.
            with contextlib.suppress(Exception):
                doc = bobreport.load_digest(_root(home))
                ent = (doc.get("machines") or {}).get(mid)
                if isinstance(ent, dict):
                    rows = list(ent.get("worker_list") or [])
                    keep = [
                        r
                        for r in rows
                        if str((r or {}).get("nick") or "").lower() != me_l
                    ]
                    if len(keep) != len(rows):
                        ent["worker_list"] = bobreport._coerce_worker_list(keep)
                        bobreport.save_digest(_root(home), doc)
                        out["removed"] = True
    # Clear offered_to pins so the row is free for a live seat immediately.
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                doc = None
            if isinstance(doc, dict):
                changed = False
                for row in doc.get("unaccepted") or []:
                    if not isinstance(row, dict):
                        continue
                    to = str(row.get("offered_to") or "").strip()
                    to_c = (canonical_worker_nick(to) or to).strip().lower()
                    if not to_c or to_c != me_l:
                        continue
                    for k in (
                        "offered_to",
                        "offered_ts",
                        "offered_channel",
                        "offered_via",
                    ):
                        row.pop(k, None)
                    out["released_offers"] += 1
                    changed = True
                if changed:
                    with contextlib.suppress(OSError):
                        _write_queue(queue_path(home), doc)
    except (TimeoutError, OSError):
        pass
    released = release_accepted_for_departed_nick(home, me)
    out["released_accepted"] = len(released or [])
    with contextlib.suppress(Exception):
        clear_idle_after_empty(home, me)
    return out


def _nicks_for_recycled_machine(home: Path, machine_id: str) -> list[str]:
    """Collect seat nicks belonging to ``machine_id`` from digest + queue pins."""
    mid = bobreport.fold_machine_id(machine_id) or str(machine_id or "").strip().lower()
    if not mid:
        return []
    found: list[str] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        n = (canonical_worker_nick(str(raw or "")) or str(raw or "")).strip()
        if not n:
            return
        if _seat_machine_id(n) != mid and bobreport.fold_machine_id(
            (_seat_machine_id(n) or "")
        ) != mid:
            # Also accept exact prefix when seat_machine_ids is cold.
            if not n.lower().startswith(mid.lower() + "-"):
                return
        key = n.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(n)

    with contextlib.suppress(Exception):
        doc = bobreport.load_digest(_root(home))
        ent = (doc.get("machines") or {}).get(mid)
        if not isinstance(ent, dict):
            for key, cand in (doc.get("machines") or {}).items():
                if bobreport.fold_machine_id(key) == mid and isinstance(cand, dict):
                    ent = cand
                    break
        if isinstance(ent, dict):
            for row in bobreport._coerce_worker_list(ent.get("worker_list")):
                _add((row or {}).get("nick"))
            workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
            for pid, w in workers.items():
                if not str(pid).isdigit():
                    continue
                if isinstance(w, dict) and str(w.get("nick") or "").strip():
                    _add(w.get("nick"))
                else:
                    _add(f"{mid}-{pid}")
    with contextlib.suppress(Exception):
        q = load_queue(home)
        for row in list(q.get("unaccepted") or []) + list(q.get("accepted") or []):
            if not isinstance(row, dict):
                continue
            _add(row.get("offered_to"))
            _add(row.get("nick"))
            _add(row.get("accepted_by"))
    return found


def clear_queue_after_machine_recycle(
    home: Path,
    machine_id: str,
    *,
    nicks: list[str] | None = None,
) -> dict:
    """FR #9784: free offered/held/accepted rows targeting a recycled machine's seats.

    Soft-release only (no give-up stamp). New seats after restart get fresh offers
    via ``!bored`` / offer_to_idle. Pass ``nicks`` when digest was already wiped.
    """
    mid = bobreport.fold_machine_id(machine_id) or str(machine_id or "").strip().lower()
    out = {
        "machine": mid,
        "cleared_offers": 0,
        "released_accepted": 0,
        "cleared_holds": 0,
        "nicks": [],
    }
    if not mid or mid in {"jeeves", "ircjeeves"}:
        return out
    collected = list(nicks) if nicks is not None else []
    if not collected:
        collected = _nicks_for_recycled_machine(home, mid)
    else:
        # Merge any queue-only pins still targeting this machine.
        extra = _nicks_for_recycled_machine(home, mid)
        seen = {(canonical_worker_nick(n) or n).strip().lower() for n in collected if n}
        for n in extra:
            key = (canonical_worker_nick(n) or n).strip().lower()
            if key and key not in seen:
                collected.append(n)
                seen.add(key)
    nicks = collected
    out["nicks"] = list(nicks)
    nick_l = {(canonical_worker_nick(n) or n).strip().lower() for n in nicks if n}

    def _targets_machine(raw: object) -> bool:
        n = (canonical_worker_nick(str(raw or "")) or str(raw or "")).strip()
        if not n:
            return False
        n_l = n.lower()
        if n_l in nick_l:
            return True
        seat_mid = bobreport.fold_machine_id(_seat_machine_id(n) or "") or _seat_machine_id(n)
        if seat_mid and seat_mid == mid:
            return True
        return n_l.startswith(mid.lower() + "-")

    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                doc = None
            if isinstance(doc, dict):
                changed = False
                for row in doc.get("unaccepted") or []:
                    if not isinstance(row, dict):
                        continue
                    to = str(row.get("offered_to") or "").strip()
                    if not to or not _targets_machine(to):
                        continue
                    for k in (
                        "offered_to",
                        "offered_ts",
                        "offered_channel",
                        "offered_via",
                    ):
                        row.pop(k, None)
                    out["cleared_offers"] += 1
                    changed = True
                    with contextlib.suppress(Exception):
                        _clear_job_seat_holds_unlocked(
                            home,
                            str(row.get("repo") or ""),
                            str(row.get("task") or ""),
                            str(row.get("id") or ""),
                        )
                        out["cleared_holds"] += 1
                # Release accepted rows for recycled nicks (same unlock pass).
                for nick in list(nicks):
                    released = _release_accepted_for_nick_unlocked(doc, nick)
                    if released:
                        out["released_accepted"] += len(released)
                        changed = True
                # Also scan accepted for machine-prefix nick not already listed.
                for row in list(doc.get("accepted") or []):
                    if not isinstance(row, dict):
                        continue
                    holder = str(
                        row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
                    ).strip()
                    if holder and _targets_machine(holder):
                        released = _release_accepted_for_nick_unlocked(doc, holder)
                        if released:
                            out["released_accepted"] += len(released)
                            changed = True
                if changed:
                    with contextlib.suppress(OSError):
                        _write_queue(queue_path(home), doc)
    except (TimeoutError, OSError):
        pass
    for nick in nicks:
        with contextlib.suppress(Exception):
            if clear_seat_hold(home, nick):
                out["cleared_holds"] += 1
        with contextlib.suppress(Exception):
            clear_idle_after_empty(home, nick)
    return out


def clear_after_machine_recycle(home: Path, machine_id: str) -> dict:
    """FR #9784: digest wipe + queue free for one machine (or all roster on fleet)."""
    mid = bobreport.fold_machine_id(machine_id) or str(machine_id or "").strip().lower()
    summary: dict = {"machine": mid, "machines": [], "digest": [], "queue": []}
    targets: list[str] = []
    if mid in {"fleet", "all", ""}:
        with contextlib.suppress(Exception):
            targets = [
                bobreport.fold_machine_id(m) or m
                for m in bobreport.roster_machine_ids(home)
            ]
        if not targets:
            targets = [mid] if mid and mid not in {"fleet", "all", ""} else []
    elif mid in {"jeeves", "ircjeeves"}:
        return summary
    else:
        targets = [mid]
    summary["machines"] = targets
    for t in targets:
        dig = bobreport.clear_machine_workers_after_recycle(home, t)
        summary["digest"].append(dig)
        q = clear_queue_after_machine_recycle(
            home, t, nicks=list(dig.get("nicks") or [])
        )
        summary["queue"].append(q)
    return summary


def release_accepted_for_departed_nick(home: Path, nick: str) -> list[dict]:
    """FR #3400: seat left the shop - return its ACKed rows to unaccepted (prior ACK void).

    Local queue only; no GitHub. Live seats are never passed here (worker-remove / reconcile).

    FR #4624: closed-stamped ACC rows move to done (empty released list) - still persist.
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return []
            acc_before = len(doc.get("accepted") or [])
            released = _release_accepted_for_nick_unlocked(doc, nick)
            if not released and len(doc.get("accepted") or []) == acc_before:
                return []
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return []
            return released
    except (TimeoutError, OSError):
        return []


# BOB-D6 / FR #8810: short TTL for empty-body hydrate (vision UNKNOWN picked 60s).
FR_BODY_FETCH_CACHE_TTL_S = 60.0
FR_BODY_FETCH_SHARED_CACHE = TTLCache(FR_BODY_FETCH_CACHE_TTL_S)


def ensure_fr_queue_body(
    row: dict,
    *,
    fetch_issue=None,
    cache: dict | None = None,
) -> str:
    """BOB-D6 / FR #8810: fetch GitHub issue body when the queue row body is empty.

    Stamps ``row["body"]`` via ``_body_for_queue`` so Depends-on parse sees the stamp.
    Non-FR rows and rows that already have a non-blank body are unchanged (no fetch).
    ``fetch_issue(repo, num)`` is the test seam; default uses ``fetch_github_issue_dict``.
    """
    if not isinstance(row, dict) or _canon_task(row) != "FR":
        return str((row or {}).get("body") or "") if isinstance(row, dict) else ""
    existing = str(row.get("body") or "")
    if existing.strip():
        return existing
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    if not repo or not num:
        return existing
    store: dict = cache if cache is not None else FR_BODY_FETCH_SHARED_CACHE
    key = f"fr_body:{repo}#{num}"
    hit = store.get(key, _CACHE_MISS) if hasattr(store, "get") else _CACHE_MISS
    if hit is not _CACHE_MISS:
        body_hit = str(hit or "")
        if body_hit.strip():
            row["body"] = _body_for_queue(body_hit)
            return str(row.get("body") or "")
        return existing
    getter = fetch_issue or (lambda r, n: fetch_github_issue_dict(r, n))
    issue = None
    try:
        issue = getter(repo, num)
    except Exception:
        issue = None
    fetched = ""
    if isinstance(issue, dict):
        fetched = str(issue.get("body") or "")
    try:
        store[key] = fetched
    except Exception:
        if isinstance(store, dict):
            store[key] = fetched
    if fetched.strip():
        row["body"] = _body_for_queue(fetched)
        return str(row.get("body") or "")
    return existing


def fetch_github_issue_dict(repo: str, num: str, *, token: str = "") -> dict | None:
    """GET ``/repos/{repo}/issues/{num}`` -> issue dict, or None on miss/error (FR #4422)."""
    repo_s = str(repo or "").strip()
    num_s = str(num or "").strip().lstrip("#")
    if not repo_s or not num_s.isdigit():
        return None
    tok = (token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not tok:
        try:
            import gh_filer

            gh_filer.ensure_gh_token_env()
            tok = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
        except Exception:
            tok = ""
    if not tok:
        return None
    api = f"https://api.github.com/repos/{repo_s}/issues/{num_s}"
    req = urllib.request.Request(
        api,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-gitclaim",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            if not (200 <= int(getattr(resp, "status", 200) or 200) < 300):
                return None
            raw = resp.read()
            body = json.loads(
                raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
            )
            return body if isinstance(body, dict) else None
    except Exception:
        return None


def claim_from_github_issue(repo: str, issue: dict) -> GitClaim | None:
    """Build an FR (or MRB) GitClaim from a GitHub issue/PR payload (FR #4422)."""
    if not isinstance(issue, dict):
        return None
    num = issue.get("number")
    if not isinstance(num, int):
        return None
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    labels = _label_names(issue.get("labels"))
    state = str(issue.get("state") or "open").strip().lower()
    if state and state != "open":
        return None
    if issue.get("pull_request") is not None or str(issue.get("html_url") or "").find("/pull/") >= 0:
        # Open PR -> MRB row.
        _paths = resolve_intake_pr_changed_paths(issue, repo=repo, number=num)
        if issue.get("draft") is True and not is_offerable_intake_skill_lesson_pr(
            title=title, body=body, labels=labels, files=_paths
        ):
            return None
        # FR #7118: open non-draft PRs (including intake/ harvest receipts) are
        # offerable MRB via !assign / enqueue. Webhook still skips receipts (FR #2650).
        # FR #6340: explicit !assign / enqueue must reach docs/mrb pins (never
        # refuse with docs_mrb_pin). Auto resync/webhook still skip parent-open
        # and pin-of-pin; stamp docs_mrb_orphan so the row is auditable.
        docs_pin = is_docs_mrb_pin_pr(title=title, labels=labels)
        _mrb_fix_offer_issue = False
        if is_mrb_fix_pr_title(title) and not mrb_fix_targets_default_branch(issue):
            return None
        if is_mrb_fix_pr_title(title):
            _mrb_fix_offer_issue = True
        lesson = is_harvest_lesson_pr(title=title, labels=labels)
        refs = extract_closes_issue_ids(title, body, repo=repo) if not lesson else ()
        orphan_line = ""
        if docs_pin:
            parent = docs_mrb_pin_parent_pr_id(title=title)
            orphan_line = (
                f"docs_mrb_orphan parent={parent or '?'} "
                "(explicit enqueue; missing required check -> FAIL or re-run)"
            )
        return GitClaim(
            repo=canonical_queue_repo(repo),
            task="MRB",
            id=f"#{num}",
            event="pull_request",
            action="opened",
            line=orphan_line,
            title=title,
            body=body,
            labels=labels,
            state=state or "open",
            refs=tuple(refs) if refs else (),
            harvest_lesson=lesson,
            opened_by=lesson_pr_opener_seat(body) if lesson else "",
            docs_mrb_orphan=docs_pin,
            mrb_fix_offer=_mrb_fix_offer_issue,
        )
    _probe = {"task": "FR", "title": title, "body": body, "labels": list(labels or ())}
    if issue_skip_fr_reason(title=title, body=body, labels=labels, state=state or "open") and not digest_issue_reason(_probe):
        return None
    if (_repo_key(repo), _norm_row_id(f"#{num}")) in _SKIP_FR_ISSUE_PINS:
        return None
    if (_repo_key(repo), _norm_row_id(f"#{num}")) in _NEEDS_HUMAN_ISSUE_PINS:
        return None
    return GitClaim(
        repo=canonical_queue_repo(repo),
        task="FR",
        id=f"#{num}",
        event="issues",
        action="opened",
        line="",
        title=title,
        body=body,
        labels=labels,
        state=state or "open",
    )



def _fetch_pr_state_for_assign(repo: str, num: str) -> dict:
    """Pulls API rollup (head SHA + checks). Issues API payloads omit both."""
    import mrb_merge_on_green

    return mrb_merge_on_green.fetch_pr_state(repo, num)


def enqueue_fix_github_item(
    doc: dict,
    repo: str,
    ident: str,
    *,
    fetch_issue=None,
    fetch_pr=None,
    home: Path | None = None,
) -> tuple[str, str]:
    """Enqueue a FIX row for an open red/DIRTY PR when missing (FR #4652 / #4906 !assign FIX).

    ``fetch_issue(repo, num)`` is the test seam (Issues API shape; may include
    ``head.sha`` and ``checks``). The live Issues payload has neither, so a missing
    SHA or check rollup is filled from ``fetch_pr`` (default: pulls API).
    Returns ``("added"|"duplicate"|"refused", detail)``.

    FR #4906: CONFLICTING/DIRTY (or ``conflict_blocked`` ledger for this head SHA)
    is accepted even when required checks are green.
    """
    num = str(ident or "").strip().lstrip("#")
    repo_c = canonical_queue_repo(repo)
    if not repo_c or not num.isdigit():
        return "refused", "repo/id required"
    getter = fetch_issue or (lambda r, n: fetch_github_issue_dict(r, n))
    try:
        issue = getter(repo_c, num)
    except Exception as exc:  # noqa: BLE001
        return "refused", f"github fetch failed: {type(exc).__name__}"
    if not isinstance(issue, dict):
        return "refused", f"{repo_c}#{num}: not found on GitHub or no token"
    state = str(issue.get("state") or "").strip().lower()
    if state and state != "open":
        return "refused", f"{repo_c}#{num}: not open"
    is_pull = (
        issue.get("pull_request") is not None
        or "/pull/" in str(issue.get("html_url") or "")
    )
    if not is_pull:
        return "refused", f"{repo_c}#{num}: not a pull request (FIX needs a PR)"
    if issue.get("draft") is True:
        return "refused", f"{repo_c}#{num}: draft PR"
    head = issue.get("head") if isinstance(issue.get("head"), dict) else {}
    sha = str(head.get("sha") or issue.get("pass_sha") or "").strip()
    checks = issue.get("checks")
    mergeable = issue.get("mergeable")
    merge_state = str(
        issue.get("mergeable_state")
        or issue.get("mergeStateStatus")
        or issue.get("merge_state_status")
        or ""
    )
    need_pr = (
        (not sha)
        or not (isinstance(checks, str) and checks.strip())
        or (mergeable is None and not merge_state.strip())
    )
    if need_pr:
        getter_pr = fetch_pr or _fetch_pr_state_for_assign
        try:
            pr_state = getter_pr(repo_c, num)
        except Exception as exc:  # noqa: BLE001
            return "refused", f"github pr fetch failed: {type(exc).__name__}"
        if not isinstance(pr_state, dict):
            return "refused", f"{repo_c}#{num}: pull state missing"
        if not sha:
            sha = str(pr_state.get("sha") or "").strip()
        if not (isinstance(checks, str) and checks.strip()):
            checks = pr_state.get("checks")
        if mergeable is None and not merge_state.strip():
            mergeable = pr_state.get("mergeable")
            merge_state = str(
                pr_state.get("merge_state_status")
                or pr_state.get("mergeable_state")
                or pr_state.get("mergeStateStatus")
                or ""
            )
    if not sha:
        return "refused", f"{repo_c}#{num}: missing head SHA"
    import mrb_merge_on_green as _mog_fail

    comments = issue.get("comments") if isinstance(issue.get("comments"), list) else []
    verdict = _mog_fail.newest_mrb_board(comments)
    fail_board = bool(
        verdict
        and verdict[0] == "FAIL"
        and _mog_fail.shas_match(verdict[1], sha)
        and not _mog_fail.linked_fail_fix_open(issue.get("open_prs") or [], num)
    )
    checks_failed = isinstance(checks, str) and bool(checks.strip()) and open_pr_mrb_checks_failed(checks)
    dirty_reason = _mog_fail.merge_attempt_conflict_reason(
        mergeable=mergeable, merge_state=merge_state
    )
    if not dirty_reason and home is not None:
        blocked = _mog_fail.conflict_blocked_pass_sha(
            _mog_fail.load_ledger(home), repo_c, num
        )
        if blocked and _mog_fail.shas_match(blocked, sha):
            dirty_reason = "conflict-blocked"
    if not fail_board and not dirty_reason:
        if not (isinstance(checks, str) and checks.strip()):
            return "refused", f"{repo_c}#{num}: PR checks unknown"
        if not checks_failed:
            return (
                "refused",
                f"{repo_c}#{num}: PR checks not failed ({checks.strip()})",
            )
    pull_url = str(issue.get("html_url") or "").strip()
    if not PULL_URL_RE.search(pull_url):
        pull_url = f"https://github.com/{repo_c}/pull/{num}"
    if dirty_reason and not (fail_board and not checks_failed) and not checks_failed:
        # FR #4906: green (or unknown) checks but DIRTY/CONFLICTING / conflict_blocked.
        detail = dirty_reason
        title = f"FIX conflict (!assign; {detail}; PR #{num})"
        body = (
            f"FR #4906/#4636 conflict-fix: operator !assign for open PR that is "
            f"{detail} at head SHA {sha}. Merge origin/main into this branch, "
            f"resolve the conflicts, and push."
        )
        labels = ("via-intake", "fix-conflict")
        sig = f"conflict|{repo_c}|{num}|{_mog_fail._norm_sha(sha)}"
    elif fail_board and not checks_failed:
        detail = "mrb-fail"
        title = f"FIX MRB FAIL board (!assign; PR #{num})"
        body = (
            f"FR #4718 FIX: newest MRB board is FAIL at head SHA {sha}. "
            f"Implement that board on this branch and push."
        )
        labels = ("via-intake", "fix-mrb-fail")
        sig = f"mrb-fail|{repo_c}|{num}|{sha.strip().lower()}"
    else:
        detail = str(checks or "failure").strip() or "failure"
        title = f"FIX CI (!assign; red check; PR #{num})"
        body = (
            f"FR #4652 FIX: operator !assign for open PR with failed required checks "
            f"({detail}). Head SHA {sha}. Fix CI on this PR branch and push."
        )
        labels = ("via-intake", "fix-ci")
        sig = f"assign-fix:{repo_c}#{num}:{sha[:12]}"
    claim = GitClaim(
        repo=repo_c,
        task="FIX",
        id=f"#{num}",
        event="pull_request",
        action="synchronize",
        line=pull_url,
        title=title,
        body=body,
        labels=labels,
    )
    changed = _append_unaccepted(
        doc,
        claim,
        url=pull_url,
        body=body,
        title=title,
        pass_sha=sha,
        fail_signature=sig,
    )
    if changed == "added":
        if dirty_reason and home is not None:
            # Keep conflict_fix ledger in sync so resync does not double-queue.
            try:
                ldoc = _mog_fail.load_ledger(home)
                offered = ldoc.get(_mog_fail.CONFLICT_FIX_KEY)
                if not isinstance(offered, dict):
                    offered = {}
                    ldoc[_mog_fail.CONFLICT_FIX_KEY] = offered
                offered[sig] = {
                    "repo": repo_c,
                    "pr": num,
                    "pass_sha": _mog_fail._norm_sha(sha),
                    "signature": sig,
                    "url": pull_url,
                }
                _mog_fail.save_ledger(home, ldoc)
            except Exception:  # noqa: BLE001
                pass
        return "added", f"enqueued FIX {repo_c}#{num}"
    if changed in ("duplicate", "noop"):
        return "duplicate", f"already queued FIX {repo_c}#{num}"
    return "refused", f"enqueue {changed}"


def enqueue_open_github_item(
    doc: dict,
    repo: str,
    task: str,
    ident: str,
    *,
    fetch_issue=None,
    fetch_pr=None,
    home: Path | None = None,
) -> tuple[str, str]:
    """Enqueue an open GitHub issue/PR into ``doc['unaccepted']`` when missing (FR #4422).

    Returns ``("added"|"duplicate"|"skipped"|"refused", detail)``.
    ``fetch_issue(repo, num)`` is the test seam; default hits the GitHub Issues API.

    FR #4545: ``skipped`` (hold / skip-FR / supersede) is distinct from ``duplicate``
    so !assign does not claim the job is "already queued" when it was never offered.
    """
    task_u = (task or "").upper()
    if task_u == "FIX":
        return enqueue_fix_github_item(
            doc,
            repo,
            ident,
            fetch_issue=fetch_issue,
            fetch_pr=fetch_pr,
            home=home,
        )
    if task_u not in ("FR", "MRB"):
        return "refused", f"{task_u}: only FR/MRB/FIX can be enqueued from GitHub"
    num = str(ident or "").strip().lstrip("#")
    getter = fetch_issue or (lambda r, n: fetch_github_issue_dict(r, n))
    try:
        issue = getter(repo, num)
    except Exception as exc:  # noqa: BLE001
        return "refused", f"github fetch failed: {type(exc).__name__}"
    if not isinstance(issue, dict):
        return "refused", f"{repo}#{num}: not found on GitHub or no token"
    claim = claim_from_github_issue(repo, issue)
    if claim is None:
        is_pr = (
            issue.get("pull_request") is not None
            or str(issue.get("html_url") or "").find("/pull/") >= 0
        )
        if task_u == "MRB" and is_pr and issue.get("draft") is True:
            return "refused", f"{repo}#{num}: draft"
        return "refused", f"{repo}#{num}: not an open offerable {task_u}"
    if claim.task != task_u:
        return "refused", f"{repo}#{num}: GitHub item is {claim.task}, not {task_u}"
    extra: dict = {}
    if claim.task == "MRB":
        extra["url"] = f"https://github.com/{claim.repo}/pull/{num}"
        if claim.refs:
            extra["refs"] = ",".join(claim.refs)
    # FR #6208: honour persistent !ignore on manual / assign enqueue too.
    if home is not None:
        import focus_ignore as _fi_ignore

        if _fi_ignore.is_ignored(home, claim.repo):
            return "skipped", f"ignored {claim.task} {claim.repo}{claim.id}"
    changed = _append_unaccepted(doc, claim, home=home, **extra)
    if changed == "added":
        return "added", f"enqueued {claim.task} {claim.repo}{claim.id}"
    if changed == "duplicate":
        return "duplicate", f"already queued {claim.task} {claim.repo}{claim.id}"
    if changed == "skipped":
        why = ""
        if home is not None:
            import focus_ignore as _fi_ignore

            if _fi_ignore.is_ignored(home, claim.repo):
                why = "repo-ignored"
        if not why and claim.task == "MRB":
            why = pr_hold_reason(
                title=claim.title, body=claim.body, labels=claim.labels
            ) or ""
        elif not why and claim.task == "FR":
            # bob_d7_wire_hold: Depends gate beside hold in skip detail.
            _dep_probe = {
                "task": "FR",
                "repo": claim.repo,
                "id": claim.id,
                "title": claim.title,
                "body": claim.body,
            }
            why = (
                fr_hold_reason(
                    title=claim.title, body=claim.body, labels=claim.labels
                )
                or depends_gate_reason(
                    _dep_probe, doc, issue_fetch=depends_issue_fetch_checker()
                )
                or issue_skip_fr_reason(
                    title=claim.title,
                    body=claim.body,
                    labels=claim.labels,
                    state=claim.state,
                )
                or ""
            )
        detail = f"skipped {claim.task} {claim.repo}{claim.id}"
        if why:
            detail += f" ({why})"
        return "skipped", detail
    if changed == "noop":
        return "duplicate", f"already queued {claim.task} {claim.repo}{claim.id}"
    return "refused", f"enqueue {changed}"



def assign_refusal_outcome_token(reason: str) -> str:
    """Stable grep token for !assign refuse paths (FR #6348)."""
    r = str(reason or "").lower()
    if "accepted by live seat" in r:
        return "accepted_by_seat"
    if "not in the unaccepted queue" in r:
        return "not_queued_skipped"
    if "superseded" in r:
        return "superseded_by_pr"
    if "busy (" in r or ": busy (" in r:
        return "busy"
    if "cooldown" in r:
        return "cooldown"
    return "other"


def format_assign_refusal_log(
    *,
    nick: str,
    worker: str,
    repo: str,
    ident: str,
    task: str,
    reason: object,
    redact_fn=None,
) -> str:
    """Full single-line stdout log for !assign refuse (FR #6348).

    Never truncates. Embedded newlines become spaces. Reason text is redacted
    with ``crash_report.redact`` (or *redact_fn*) before emit.
    """
    raw = str(reason if reason is not None else "")
    nl = chr(10)
    cr = chr(13)
    flat = " ".join(
        part.strip()
        for part in raw.replace(cr + nl, nl).replace(cr, nl).split(nl)
    )
    flat = " ".join(flat.split())
    if redact_fn is None:
        try:
            from crash_report import redact as _redact

            redact_fn = _redact
        except Exception:  # noqa: BLE001
            def _identity(s: str) -> str:
                return s

            redact_fn = _identity
    try:
        flat = str(redact_fn(flat))
    except Exception:  # noqa: BLE001
        pass
    token = assign_refusal_outcome_token(flat)
    ident_s = str(ident or "").strip()
    if ident_s and not ident_s.startswith("#"):
        ident_s = f"#{ident_s}"
    repo_s = str(repo or "").strip()
    task_s = str(task or "").strip().upper() or "?"
    return (
        f"INFO git-assign refused outcome={token} "
        f"nick={nick} worker={worker} {repo_s}{ident_s} {task_s}: {flat}"
    )




def _depends_open_assign_reason(row: dict) -> str:
    """Shop reason for !assign. irc_agent prefixes ``assign: refused - ``."""
    refs = _row_depends_on_issue_refs(row)
    if not refs:
        return "depends-on open"
    repo, num = refs[0]
    home = str(row.get("repo") or "").strip()
    if repo and home and repo.lower() != home.lower():
        return "depends-on open %s#%s" % (repo, num)
    return "depends-on open #%s" % num


def assign_row(
    home: Path,
    nick: str,
    repo: str,
    task: str,
    ident: str,
    *,
    now: float | None = None,
    pr_exists=None, is_pull=None, issue_open=None,
    fetch_issue=None,
    fetch_pr=None,
    coderabbit_lookup=None,
    names_refresh=None,
) -> tuple[str, dict | str]:
    """Chair-driven manual assign (t849u): stamp ``offered_to`` on one named unaccepted row.

    Returns ("ok", job) -> caller posts ``format_assign_line`` in the worker's shop channel as Jeeves
    and the worker's ACK accepts it (``accept_offered``); or ("refused", reason).
    The same eligibility as ``offer_focus_top`` applies: real seat nick, not busy, row queued and
    unaccepted, no self-MRB/UAT, not skip/cooldown/machine-pinned,
    not offered to another seat inside OFFER_TIMEOUT_S, and (FR #6211) the automatic MRB
    CodeRabbit current-head hold. Intentional exceptions: ordinary ``!assign`` may still hand
    out ``needs_human`` FR/MRB rows that auto-offer blocks (FR #4336), and clears this nick's
    prior give-up on the row (queue ``giveup_seats`` + seat ledger) instead of refusing
    ``already gave this row up`` (FR #9634) - same effect as ops ``!cleargiveup … <nick>`` then
    assign.

    FR #3400 / #7186: refuse assign to a nick not in #{machine} membership (JOIN/NAMES/PART),
    never because they have not sent ``!bored``. If the named job is only
    on ``accepted`` under a departed nick, release it (prior ACK void) then offer.
    ``names_refresh(shop)`` (optional) is invoked once before a presence refuse.
    If it returns ``\"wait\"``, this call returns ``(\"waiting\", shop)`` so the chair
    can apply the 353/366 membership update off this stack (FR #7224; no reader deadlock).

    FR #4422 / #4652: when the named open FR/MRB/FIX is missing from the unaccepted queue, fetch it from
    GitHub and enqueue it, then offer (instead of refusing "not in the unaccepted queue").
    ``coderabbit_lookup`` is an optional test/budget checker for ``apply_mrb_coderabbit_gate``.
    """
    import time as _time

    from focus_ignore import repo_match  # lazy: avoids an import cycle at module load

    now_f = _time.time() if now is None else float(now)
    me = canonical_worker_nick(nick) or (nick or "").strip()
    shop = worker_shop_channel(me)
    if shop is None:
        return "refused", f"{nick}: not a worker seat nick (<machine>-<pid>)"
    if worker_working_on(home, me):
        return "refused", f"{me}: busy ({worker_working_on(home, me)[:60]})"
    _open = seat_open_job(home, me, now_f)  # FR #4089
    if _open:
        return "refused", f"{me}: busy ({_open[:60]})"
    task_u = (task or "").upper()
    num = str(ident or "").strip().lstrip("#")
    live = live_seat_nicks(home)
    live_l = {n.lower() for n in live}
    # FR #3400 / #7186: refuse assign to a nick absent from shop membership
    # (worker_list filled by JOIN/NAMES, not !bored). Empty list = unknown
    # presence (tests / cold digest) - do not block. Refresh NAMES once first.
    seat_mid = bobreport.parse_seat_nick(me)
    if seat_mid:
        def _shop_presence():
            try:
                dig = bobreport.load_digest(_root(home))
                ent = (dig.get("machines") or {}).get(seat_mid[0]) or {}
                shop_rows = bobreport._coerce_worker_list(ent.get("worker_list"))
                members_at = str(ent.get("shop_members_ts") or "")
                if not members_at:
                    for r in shop_rows:
                        ts = str((r or {}).get("updated") or "")
                        if ts:
                            members_at = ts
                            break
            except Exception:
                shop_rows, members_at = [], ""
            nicks = {str(r.get("nick") or "").lower() for r in shop_rows}
            return shop_rows, nicks, members_at

        shop_rows, nicks, members_at = _shop_presence()
        if shop_rows and me.lower() not in nicks and callable(names_refresh):
            hint = None
            with contextlib.suppress(Exception):
                hint = names_refresh(shop)
            if str(hint or "").strip().lower() == "wait":
                return "waiting", shop
            shop_rows, nicks, members_at = _shop_presence()
        if shop_rows and me.lower() not in nicks:
            snap = members_at or "unknown"
            return (
                "refused",
                f"{me}: not in the shop channel (not a live seat; members_at={snap})",
            )
    # FR #6134 / #7888: refuse MRB/UAT when start_model is free or unknown.
    # A paid start_model is assignable. OpenCode with no start_model fails safe.
    try:
        if task_u in ("MRB", "UAT") and seat_is_free_fuel(home, me):
            why = mrb_eligibility_reason(home, me)
            return (
                "refused",
                f"{me}: OpenCode or free start_model skips {task_u} ({why}; FR #6134 / #7888)",
            )
    except Exception:
        pass
    free = free_seat_nicks(home, live)
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "refused", "queue unreadable"
            idx = None
            for i, row in enumerate(doc["unaccepted"]):
                if (
                    str(row.get("task") or "").upper() == task_u
                    and str(row.get("id") or "").strip().lstrip("#") == num
                    and repo_match(repo, str(row.get("repo") or ""))
                ):
                    idx = i
                    break
            if idx is None:
                # FR #3400: orphan accepted under a departed seat - release then offer.
                acc_idx = None
                for i, row in enumerate(doc.get("accepted") or []):
                    if (
                        str(row.get("task") or "").upper() == task_u
                        and str(row.get("id") or "").strip().lstrip("#") == num
                        and repo_match(repo, str(row.get("repo") or ""))
                    ):
                        acc_idx = i
                        break
                if acc_idx is None:
                    # FR #4422 / #4652: open issue/PR missing from queue -> enqueue from GitHub, then offer.
                    if task_u in ("FR", "MRB", "FIX"):
                        enq_st, enq_detail = enqueue_open_github_item(
                            doc,
                            repo,
                            task_u,
                            num,
                            fetch_issue=fetch_issue,
                            fetch_pr=fetch_pr,
                            home=home,
                        )
                        if enq_st in ("added", "duplicate"):
                            for i, row in enumerate(doc["unaccepted"]):
                                if (
                                    str(row.get("task") or "").upper() == task_u
                                    and str(row.get("id") or "").strip().lstrip("#") == num
                                    and repo_match(repo, str(row.get("repo") or ""))
                                ):
                                    idx = i
                                    break
                        if idx is None:
                            return (
                                "refused",
                                f"{repo}#{num} {task_u}: not in the unaccepted queue "
                                f"({enq_detail})",
                            )
                    else:
                        return "refused", f"{repo}#{num} {task_u}: not in the unaccepted queue"
                if idx is None and acc_idx is not None:
                    holder = _accepted_holder_nick(doc["accepted"][acc_idx])
                    acc_row = doc["accepted"][acc_idx]
                    same_seat = _seat_key(holder) == _seat_key(me)
                    false_lost = (
                        same_seat
                        and str(acc_row.get("reconcile") or "") == "LOST_ACK_RESTART"
                        and not _seat_reports_row(home, me, acc_row)
                    )
                    if holder.lower() in live_l and not false_lost:
                        return (
                            "refused",
                            f"{repo}#{num} {task_u}: accepted by live seat {holder}",
                        )
                    _release_accepted_for_nick_unlocked(doc, holder)
                    for i, row in enumerate(doc["unaccepted"]):
                        if (
                            str(row.get("task") or "").upper() == task_u
                            and str(row.get("id") or "").strip().lstrip("#") == num
                            and repo_match(repo, str(row.get("repo") or ""))
                        ):
                            idx = i
                            break
                    if idx is None:
                        return "refused", f"{repo}#{num} {task_u}: not in the unaccepted queue"
            cand = doc["unaccepted"][idx]
            # FR #8619 / #8264: never hand a self-review stall FR to its idle author
            # via !assign either (auto-offer already gated in offer_focus_top).
            if seat_blocked_for_self_review_stall(cand, me, doc):
                return (
                    "refused",
                    f"{me}: idle author of self-review-deadlock stall (FR #8264 / #8619)",
                )
            # FR #4652: !assign FIX refuses needs_human (clear reason). FR/MRB still follow FR #4336.
            if task_u == "FIX" and row_needs_human(cand):
                return "refused", "row is needs_human (FIX !assign refused)"
            # FR #4336: auto-offer blocks needs_human globally; explicit !assign may still hand it out.
            # (row_needs_human remains the bored/done-offer/reconcile gate.)
            if row_awaits_mrb1(cand):
                # Unreachable while row_awaits_mrb1 is always False (op 2026-10-04).
                return "refused", "row awaits needs-mrb1 clear (legacy)"
            if row_on_cooldown(cand, now_f, me):
                return "refused", "row is on GIVEUP/NACK cooldown"
            if row_skip_fr_reason(cand):
                return "refused", f"row skipped: {row_skip_fr_reason(cand)}"
            hold_why = row_fr_skip_offer_reason(cand)
            if hold_why:
                prefix = "row park-only" if hold_why.startswith("park-only") else "row on hold"
                return "refused", f"{prefix}: {hold_why}"
            digest_why = digest_issue_reason(cand)
            if digest_why:
                return "refused", f"row is digest gate (not work): {digest_why}"
            # FR #9833 / #9875: !assign obeys build-jeeves dispatch lock (same as !bored / !list).
            try:
                import dispatch_lock as _dl

                lock_why = _dl.row_blocked_reason(home, cand)
                if lock_why:
                    return "refused", f"build-jeeves lock: {lock_why}"
            except Exception:
                pass
            # FR #9455 bob_g1_shared_gate: !assign uses the same helper as offer/stuck.
            live_dep = depends_gate_reason(
                cand,
                doc,
                open_keys=open_fr_issue_keys(doc),
                issue_open=depends_issue_open_checker(issue_open),
                issue_fetch=depends_issue_fetch_checker(fetch_issue),
            )
            if live_dep:
                if live_dep == DEPENDS_OPEN_REASON or str(live_dep).startswith(
                    "depends-on open"
                ):
                    return "refused", _depends_open_assign_reason(cand)
                return "refused", f"row blocked: {live_dep}"
            if repo_archived_for_queue(str(cand.get("repo") or "")):
                return "refused", "repo is archived (FR #785)"
            if row_machine_mismatch(cand, me):
                return "refused", f"row is pinned to another machine than {me}"
            # FR #7084 / FIX #7089: !assign still requires model eligibility (needs_human stays the
            # only manual exception, already gated above for FIX).
            if not _seat_model_allows_row(home, me, cand):
                return "refused", f"{me}: model mismatch or below jobRequiredModelTier (FR #7084)"
            if seat_fuel_pause_reason(home, me, now_f):
                return "refused", f"{me}: fuel paused until reset (FR #7837)"
            # FR #9634: !assign implies clear give-up for this nick+row (queue + ledger),
            # same as ops ``!cleargiveup owner/repo#N <nick>`` then assign. Exact-nick only;
            # recycle inherit remains auto-offer (FR #4336 / #5088). Do not call
            # clear_giveup_job here - it takes the queue lock we already hold.
            if row_gave_up_by(cand, me):
                drop_nick_from_giveup_seats(cand, me)
                with contextlib.suppress(Exception):
                    ledger_clear_giveup_entry(
                        home,
                        str(cand.get("repo") or repo),
                        str(cand.get("id") or num),
                        nick=me,
                    )
            if row_blocked_for_giveup_agent_kind(cand, seat_agent_kind(home, me)):
                return "refused", f"{me}: agent class blocked after hard-ceiling GIVEUPs (FR #8008)"
            if mrb_fail_same_head_for_seat(cand, me):
                return "refused", f"{me} already FAILed this MRB head (FR #4718)"
            why = ledger_blocks(ledger_load(home), cand, me, live)
            if why:
                return "refused", why
            if task_u == "FR" and fr_is_superseded(doc, str(cand.get("repo") or ""), str(cand.get("id") or "")):
                return "refused", "FR superseded by an open PR"
            # FR #9411 / #9827: refuse ops-monitor + TipForm-restore escalate even when hold cleared.
            _assign_skip = row_skip_fr_reason(cand)
            if task_u == "FR" and _assign_skip in (
                "ops_monitor_tracker",
                "tipform_restore_escalate",
            ):
                return (
                    "refused",
                    f"{_assign_skip} (not shop FR; FR #9411/#9827)",
                )
            # FR #9411: unbudgeted closed check when caller omitted issue_open.
            _fr_open = (
                issue_open
                if issue_open is not None
                else depends_issue_open_checker(None)
            )
            if task_u == "FR" and not fr_row_offerable(
                cand, is_pull=is_pull, pr_exists=pr_exists, issue_open=_fr_open
            ):
                return "refused", "row is a pull or CLOSED issue (not an offerable FR; #846/#838/#2340)"
            # FR #818 / t853u: refuse manual assign of legacy per-PR / non-#0 UAT.
            if task_u == "UAT" and not is_repo_uat(cand):
                return "refused", "UAT is per-repo only (id #0 + repo_uat); per-PR UAT forbidden (t853u / FR #818)"
            # FR #9382: CAST IRON - refuse UAT when the repo has no release to build.
            no_rel = uat_no_release_to_build_reason(cand, home=home)
            if no_rel:
                return "refused", no_rel
            # FR #740 / #738 / #1585: refuse already-DONE MRB unless the pull is still open.
            if task_u == "MRB" and mrb_already_done(doc, cand, home=home, pr_exists=pr_exists):
                return "refused", "MRB already DONE for this repo+#id (FR #740)"
            if not mrb_row_offerable(cand, pr_exists=pr_exists):
                return "refused", "MRB has no real open pull URL"
            cand_eff = enrich_review_author_fields(doc, cand)
            if review_blocked_for_author(
                cand_eff, me, live, ledger=ledger_load(home), free=free
            ):
                return "refused", f"{me} authored/implemented this (no self-{task_u})"
            cand = cand_eff
            # FR #6211: honor automatic MRB CodeRabbit hold on ordinary !assign.
            # Persist wait/pending stamps; never stamp offered_to / seat hold on refuse.
            # needs_human remains the intentional manual exception (checked above only for FIX).
            if task_u == "MRB":
                try:
                    import fuel_chain

                    lookup = coderabbit_lookup
                    if lookup is None:

                        def lookup(repo_s: str, num_s: str, _row=cand):
                            return fuel_chain.lookup_coderabbit_state(
                                repo_s, num_s, str(_row.get("head_sha") or "")
                            )

                    if fuel_chain.apply_mrb_coderabbit_gate(
                        cand, now_f, lookup=lookup
                    ):
                        detail = fuel_chain.coderabbit_hold_message(cand, now_f)
                        doc["unaccepted"][idx] = cand
                        try:
                            _write_queue(queue_path(home), doc)
                        except OSError:
                            pass
                        with contextlib.suppress(Exception):
                            _log_queue_purge(f"INFO {detail} via=assign")
                        return "refused", detail
                except Exception as exc:  # noqa: BLE001 - fail-open like offer_focus_top
                    with contextlib.suppress(Exception):
                        _log_queue_purge(
                            f"WARN coderabbit gate error via=assign "
                            f"{repo}#{num}: {type(exc).__name__}"
                        )
            to = str(cand.get("offered_to") or "").strip()
            if to and to.lower() != me.lower():
                try:
                    age = now_f - datetime.fromisoformat(
                        str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    age = OFFER_TIMEOUT_S + 1
                if age < OFFER_TIMEOUT_S:
                    return "refused", f"already offered to {to}"
            prev_to = to
            job = dict(cand)
            job["offered_to"] = me
            stamp_cli_exit_retry_used(job)
            job["offered_ts"] = _utc_now()
            job["offered_channel"] = shop
            resolved = resolve_assign_url(job)
            if resolved:
                job["url"] = resolved
            doc["unaccepted"][idx] = job
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "refused", "queue write failed"
            # FR #4260: !assign to a new nick frees the previous seat's hold for this job.
            if prev_to and _seat_key(prev_to) != _seat_key(me):
                with contextlib.suppress(Exception):
                    _clear_job_seat_holds_unlocked(
                        home,
                        str(job.get("repo") or ""),
                        str(job.get("task") or ""),
                        str(job.get("id") or ""),
                        except_nick=me,
                    )
            with contextlib.suppress(Exception):
                _note_seat_hold_unlocked(home, me, job)  # FR #4089
            return "ok", job
    except (TimeoutError, OSError):
        return "refused", "queue busy"


def parse_worker_ack(body: str) -> bool:
    """True if shop line is an ACK (not FILE v1 ACCEPT)."""
    text = (body or "").strip()
    if not text:
        return False
    # bare ACK or "nick: ACK ..." or "ACK ASSIGN ..."
    low = text.lower()
    if low == "ack":
        return True
    if re.match(r"(?i)^@?\S+[:\s]+ack\b", text):
        return True
    if re.match(r"(?i)^ack\b", text):
        return True
    return False


def accept_offered(home: Path, nick: str, channel: str) -> tuple[str, dict | None]:
    """Move offered unaccepted row for this nick to accepted (ACK in #machine).

    FR #9254: refuse twin accept when this nick already has an accepted row.
    Clear ``offered_to`` on the twin offered row so another seat can take it.
    Returns ``(\"twin\", holding_row)`` when refused for an existing accept.
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            canon = (nick or "").strip()
            me = (canonical_worker_nick(canon) or canon).strip().lower()
            # FR #9254: one accepted row per nick - refuse a second ACK.
            holding: dict | None = None
            for row in doc.get("accepted") or []:
                if not isinstance(row, dict):
                    continue
                raw = str(
                    row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
                ).strip()
                them = (canonical_worker_nick(raw) or raw).strip().lower()
                if them and me and them == me:
                    holding = row
                    break
            idx = None
            for i, row in enumerate(doc["unaccepted"]):
                if str(row.get("offered_to") or "").strip() == canon:
                    ch = str(row.get("offered_channel") or "").lower()
                    want = bobreport.normalize_channel(channel).lower() if channel else ""
                    if ch and want and ch != want:
                        continue
                    idx = i
                    break
            if idx is None:
                return "empty", None
            if holding is not None:
                # Clear offer stamps so the twin is free for another seat.
                twin = doc["unaccepted"][idx]
                twin["offered_to"] = ""
                twin["offered_channel"] = ""
                twin["offered_ts"] = ""
                twin.pop("offered_at", None)
                try:
                    _write_queue(queue_path(home), doc)
                except OSError:
                    return "error", None
                return "twin", holding
            job = dict(doc["unaccepted"].pop(idx))
            job["nick"] = canon
            job["channel"] = bobreport.normalize_channel(channel) if channel else ""
            job["accepted_ts"] = _utc_now()
            # FR #9554: successful ACK from the pinned host clears auto host-heal pin.
            with contextlib.suppress(Exception):
                clear_host_heal_require_machine_on_ack(job, canon)
            doc["accepted"].append(job)
            if len(doc["accepted"]) > ACCEPTED_CAP:
                doc["accepted"] = doc["accepted"][-ACCEPTED_CAP:]
            # FR #9558: ACC moved - drop every seat-hold for this job (incl. prior offer nick).
            with contextlib.suppress(Exception):
                _clear_job_seat_holds_unlocked(
                    home,
                    str(job.get("repo") or ""),
                    str(job.get("task") or ""),
                    str(job.get("id") or ""),
                )
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def prune_unassignable_queue(home: Path) -> dict:
    """FR #180 / #595: drop unaccepted FR verdict/junk rows and MRB rows without a real pull URL.

    Does not call GitHub. Closed-issue drops still come from webhooks + ``resync_from_github``.
    ``needs_human`` rows are kept but never offered (see ``offer_focus_top``).
    FR #2899: heal missing MRB ``/pull/N`` URLs before dropping; return ``dropped_detail``.
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return {"ok": False, "error": "load"}
            before = len(doc["unaccepted"])
            keep = []
            dropped_detail: list[str] = []
            for row in doc["unaccepted"]:
                task = str(row.get("task") or "").upper()
                # BOB-G3 / FR #9821: keep digest gate rows even when fr-digest is
                # SKIP_FR or the digest carries hold (token-free Depends-on gate).
                if task == "FR" and digest_issue_reason(row):
                    keep.append(row)
                    continue
                if task == "FR" and row_skip_fr_reason(row):
                    dropped_detail.append(f"{_row_drop_label(row)} skip_fr")
                    continue
                # FR #4009 / #8741: drop hold or park-only FR rows.
                if task == "FR" and row_fr_skip_offer_reason(row):
                    why = row_fr_skip_offer_reason(row) or ""
                    tag = "fr_park_only" if why.startswith("park-only") else "fr_hold"
                    dropped_detail.append(f"{_row_drop_label(row)} {tag}")
                    continue
                # bob_d7_wire_hold / FR #9455: Depends-on OPEN is offer-skip only - keep.
                if task == "FR" and depends_gate_reason(
                    row, doc, issue_fetch=depends_issue_fetch_checker()
                ):
                    keep.append(row)
                    continue
                # FR #846: drop FR rows whose URL is a pull request.
                if task == "FR" and not fr_row_offerable(row):
                    dropped_detail.append(f"{_row_drop_label(row)} fr_not_offerable")
                    continue
                # FR #785: drop rows whose repo is archived / superseded (e.g. gh-Jeeves).
                if repo_archived_for_queue(str(row.get("repo") or "")):
                    dropped_detail.append(f"{_row_drop_label(row)} archived_repo")
                    continue
                # FR #595 / #2604 / #2899: heal missing pull URL before dropping.
                if task == "MRB":
                    _heal_mrb_pull_url(row)
                    if not mrb_row_offerable(row):
                        dropped_detail.append(f"{_row_drop_label(row)} mrb_not_offerable")
                        continue
                # FR #818 / t853u: drop any UAT that is not the single repo-level #0 row.
                if task == "UAT" and not is_repo_uat(row):
                    dropped_detail.append(f"{_row_drop_label(row)} uat_not_repo_level")
                    continue
                keep.append(row)
            doc["unaccepted"] = keep
            dropped = before - len(keep)
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return {"ok": False, "error": "write"}
            return {
                "ok": True,
                "dropped": dropped,
                "dropped_detail": dropped_detail,
                "unaccepted": len(keep),
            }
    except (TimeoutError, OSError):
        return {"ok": False, "error": "lock"}


_CI_WAIT_PENDING = frozenset(
    {
        "pending",
        "expected",
        "queued",
        "in_progress",
        "waiting",
        "requested",
        "inprogress",
    }
)
_CI_WAIT_FAILURE = frozenset(
    {
        "failure",
        "error",
        "action_required",
        "timed_out",
        "cancelled",
        "canceled",
        "completed/failure",
        "completed/error",
        "completed/timed_out",
        "completed/cancelled",
        "completed/canceled",
        "completed/action_required",
    }
)


def _normalize_ci_checks(checks: str | None) -> str:
    raw = str(checks or "").strip().lower().replace(" ", "")
    if raw.startswith("completed/"):
        return raw.split("/", 1)[-1]
    return raw


def open_pr_mrb_checks_failed(checks: str | None) -> bool:
    """FR #4594: required check already concluded red (not still queued).

    FR #4630: annotated rollups like ``failure:test-and-synth`` still count as failed
    (exit ci-wait); FIX enqueue may then refuse cancelled-only / shared-suite+main-red.
    """
    state = _normalize_ci_checks(checks)
    head = state.split(":", 1)[0] if state else ""
    return head in (
        "failure",
        "error",
        "action_required",
        "timed_out",
        "cancelled",
        "canceled",
    )


def open_pr_mrb_checks_pending(checks: str | None) -> bool:
    """FR #4594: required check still queued / in progress."""
    state = _normalize_ci_checks(checks)
    return state in _CI_WAIT_PENDING



def _nick_done_mrb_pass_in_doc(doc: dict, nick: str, repo: str, ident: str) -> bool:
    """FR #4661 unlocked: True when done[] has MRB PASS for repo#id by this nick."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me or not repo or not ident or not isinstance(doc, dict):
        return False
    want = _norm_row_id(ident)
    repo_c = canonical_queue_repo(repo)
    for r in doc.get("done") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("task") or "").upper() != "MRB":
            continue
        if canonical_queue_repo(str(r.get("repo") or "")) != repo_c:
            continue
        if _norm_row_id(str(r.get("id") or "")) != want:
            continue
        if str(r.get("result") or "").strip().upper() != "PASS":
            continue
        who = (
            r.get("done_by")
            or r.get("nick")
            or r.get("accepted_by")
            or r.get("offered_to")
            or ""
        )
        who_c = (canonical_worker_nick(str(who)) or str(who)).strip().lower()
        if who_c and who_c == me:
            return True
    return False


def nick_done_mrb_pass(home: Path, nick: str, repo: str, ident: str) -> bool:
    """FR #4661: True when this seat DONE MRB PASS for repo#id (still in done[])."""
    try:
        doc = load_queue(home)
    except Exception:
        return False
    return _nick_done_mrb_pass_in_doc(doc, nick, repo, ident)


def done_mrb_pass_sha_for_ci_wait(
    home: Path, repo: str, num: int | str, head_sha: str
) -> str:
    """FR #4661: when merge-on-green ledger missed the PASS SHA, use tip SHA if done[] has PASS.

    Race: DONE stamps done[] then enqueue_from_done fetches GitHub; a concurrent
    !resync can miss the ledger and re-queue the MRB. done[] PASS + auto_merge tip
    still means ci-wait (FR #4466), so treat head_sha as the PASSed SHA.
    """
    sha = str(head_sha or "").strip()
    if not sha or not repo:
        return ""
    want = _norm_row_id(str(num))
    repo_c = canonical_queue_repo(repo)
    try:
        doc = load_queue(home)
    except Exception:
        return ""
    for r in doc.get("done") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("task") or "").upper() != "MRB":
            continue
        if canonical_queue_repo(str(r.get("repo") or "")) != repo_c:
            continue
        if _norm_row_id(str(r.get("id") or "")) != want:
            continue
        if str(r.get("result") or "").strip().upper() != "PASS":
            continue
        return sha
    return ""


def open_pr_mrb_pass_sha_unchanged(pr: dict, pass_sha: str) -> bool:
    """FR #4833: head still matches the PASSed SHA (auto_merge optional).

    Unlike ``open_pr_mrb_ci_wait_candidate``, this does not require auto-merge.
    Repos with ``allow_auto_merge=false`` still record PASS in merge-on-green;
    resync must not re-queue MRB while that head is unchanged.
    """
    if not isinstance(pr, dict):
        return False
    head = pr.get("head")
    sha = str(head.get("sha") or "") if isinstance(head, dict) else ""
    if not pass_sha or not sha:
        return False
    import mrb_merge_on_green

    return mrb_merge_on_green.shas_match(pass_sha, sha)


def open_pr_mrb_ci_wait_candidate(pr: dict, pass_sha: str) -> bool:
    """FR #4466: auto-merge on and head still the PASSed SHA (ignore check conclusion)."""
    if not isinstance(pr, dict):
        return False
    am = pr.get("auto_merge")
    if not isinstance(am, dict) or not am:
        return False
    return open_pr_mrb_pass_sha_unchanged(pr, pass_sha)


def open_pr_mrb_waiting_on_ci(
    pr: dict, pass_sha: str, *, checks: str | None = None
) -> bool:
    """FR #4466 / #4594: auto-merge on PASSed SHA is a CI wait only while checks pending.

    auto-merge off, a missing pass SHA, or a different head SHA returns False.
    Resync still skips MRB when the head matches the PASSed SHA (FR #4833) and
    re-queues when that head has moved. When ``checks`` is a concluded FAILURE (or error),
    returns False so the caller can offer FIX instead of skipping forever (FR #4594).
    When ``checks`` is omitted/unknown, keep the FR #4466 behaviour (wait).
    """
    if not open_pr_mrb_ci_wait_candidate(pr, pass_sha):
        return False
    tip_checks = checks
    if tip_checks is None and isinstance(pr.get("checks"), str):
        tip_checks = pr.get("checks")
    if tip_checks is None:
        return True
    if open_pr_mrb_checks_failed(tip_checks):
        return False
    if open_pr_mrb_checks_pending(tip_checks):
        return True
    # success / none: still waiting for merge-on-green (not a new MRB).
    return True


def _resync_pr_check_state(
    pr: dict,
    repo: str,
    num: int,
    *,
    token: str = "",
) -> str:
    """Resolve rollup check state for a ci-wait candidate (FR #4594).

    Test seam: ``pr['checks']``. Live: ``mrb_merge_on_green.fetch_pr_state``.
    On fetch failure, return ``pending`` so we keep skipping (safe).
    """
    if (
        isinstance(pr, dict)
        and isinstance(pr.get("checks"), str)
        and str(pr.get("checks") or "").strip()
    ):
        return str(pr.get("checks") or "").strip().lower()
    try:
        import mrb_merge_on_green

        st = mrb_merge_on_green.fetch_pr_state(repo, str(num), token=token or None)
        return str((st or {}).get("checks") or "pending").strip().lower() or "pending"
    except Exception:  # noqa: BLE001
        return "pending"


def _merge_on_green_pass_sha(home: Path, repo: str, num: int) -> str:
    """PASSed head SHA recorded when the seat DONE MRB PASS (merge-on-green ledger)."""
    try:
        import mrb_merge_on_green

        # FR #4466 follow-up: the chair passes its config home (~/.jeeves) but the
        # merge-on-green ledger lives beside queue.json in the fleet root (~/.bobiverse).
        doc = mrb_merge_on_green.load_ledger(_root(home))
        if (
            not (doc.get("pending") or [])
            and not (doc.get(mrb_merge_on_green.CI_FAILED_KEY) or {})
            and not (doc.get(mrb_merge_on_green.CONFLICT_KEY) or {})
            and Path(home) != _root(home)
        ):
            doc = mrb_merge_on_green.load_ledger(home)
    except Exception:  # noqa: BLE001
        return ""
    want = str(num)
    repo_l = canonical_queue_repo(repo).lower()
    for row in doc.get("pending") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("pr") or "").lstrip("#") != want:
            continue
        if str(row.get("repo") or "").strip().lower() != repo_l:
            continue
        return str(row.get("pass_sha") or "")
    # FR #4566 follow-up: CI-failed PASS rows leave the poll list but keep their SHA.
    try:
        sha = mrb_merge_on_green.ci_failed_pass_sha(doc, canonical_queue_repo(repo), want)
        if sha:
            return sha
        return mrb_merge_on_green.conflict_blocked_pass_sha(
            doc, canonical_queue_repo(repo), want
        )
    except Exception:  # noqa: BLE001
        return ""


def _tally_fix_ci_result(
    result: str, *, fix_added: int, fix_dup: int, fix_skip_main_red: int
) -> tuple[int, int, int]:
    """Count enqueue_fix_ci outcomes for resync summary (FR #4596 / #4857)."""
    r = str(result or "")
    if r == "added":
        return fix_added + 1, fix_dup, fix_skip_main_red
    if r == "duplicate":
        return fix_added, fix_dup + 1, fix_skip_main_red
    if r == "skipped_main_added":
        return fix_added + 1, fix_dup, fix_skip_main_red + 1
    if r == "skipped_main_duplicate":
        return fix_added, fix_dup, fix_skip_main_red + 1
    return fix_added, fix_dup, fix_skip_main_red


def list_pr_needs_mergeability_enrichment(pr: dict | None) -> bool:
    """True when an open-PR list item lacks mergeable* (FR #4683).

    `GET /repos/{repo}/pulls?state=open` never returns `mergeable` /
    `mergeable_state` / `mergeStateStatus`. The dirty-FIX path must not
    trust those keys until a detail `GET /pulls/N` (or GraphQL) fills them.
    """
    if not isinstance(pr, dict):
        return False
    if "mergeable_state" in pr or "mergeStateStatus" in pr:
        return False
    # FR #6044: a lone ``mergeable`` key (often REST false/null) is not enough;
    # still fetch mergeable_state so dirty pins are not skipped as clean.
    return True


def enrich_pr_mergeability(
    pr: dict,
    *,
    repo: str,
    num: int,
    fetch_json,
) -> bool:
    """FR #4683: copy mergeable* from `GET /repos/{repo}/pulls/{num}` onto `pr`.

    Mutates `pr` in place when enrichment succeeds. Returns True when a detail
    fetch ran and at least one mergeable* key was written. Failures are soft
    (return False) so one bad PR does not abort resync.
    """
    if not list_pr_needs_mergeability_enrichment(pr):
        return False
    if fetch_json is None or not repo or not isinstance(num, int):
        return False
    try:
        detail = fetch_json(f"https://api.github.com/repos/{repo}/pulls/{num}")
    except Exception:  # noqa: BLE001 - budget/404/rate; try again next resync
        return False
    if not isinstance(detail, dict):
        return False
    wrote = False
    if "mergeable" in detail:
        val = detail.get("mergeable")
        # FR #6044 / MRB #6045: do not overwrite mergeable=False with REST null
        # (GitHub still computing). A later mergeable_state=unknown would then
        # look clean and skip the dirty-FIX path.
        if val is not None or "mergeable" not in pr:
            pr["mergeable"] = val
        wrote = True
    if "mergeable_state" in detail:
        pr["mergeable_state"] = detail.get("mergeable_state")
        wrote = True
    if "mergeStateStatus" in detail:
        pr["mergeStateStatus"] = detail.get("mergeStateStatus")
        wrote = True
    return wrote


def resync_from_github(
    home: Path,
    repos: list[str],
    *,
    fetch_json=None,
    token: str = "",
    ignored=(),
    force_refresh: bool = False,
    promote_draft_skill=None,
) -> dict:
    """Rebuild FR/MRB rows from GitHub: open issues without a closing PR -> FR, open PRs -> MRB.

    Merge, not wipe (the chair runs this hourly / on webhook gap - FR #3212):
    * rows of other kinds (UAT/BUILD/PR), still-open FIX, ``accepted`` jobs for open work,
      and rows of repos whose fetch FAILED are kept;
    * a stale FR/MRB/FIX row of a successfully fetched repo (closed/merged/superseded) is dropped
      (FR #4682: accepted FIX must leave ``accepted`` so the seat is not NAK busy);
    * safe-to-close/umbrella/board issues are never (re)added and are pruned from unaccepted (FR #180);
    * skill/harvest receipts ARE added as FR promote jobs (FR #1682 / #1684; operator 2026-10-04);
    * existing rows keep their seq/offer fields; new items are appended; repos in ``ignored`` are skipped.
    * ``NotModified`` / 304 from a budgeted ETag getter leaves that repo's rows untouched (not failed).
    * FR #4959: issues and pulls are fetched independently. A 304 on open issues must not
      skip open pulls (that hid new lesson MRBs behind ``repos=0`` until ``!resync``).
      When both lists 304, the repo is listed in ``unchanged`` (still not ``failed``).
    * ``force_refresh`` skips If-None-Match on budgeted getters (startup / ``!resync``).

    ``token`` (optional) is sent as ``Authorization: Bearer``; it is never logged or returned.
    ``fetch_json(url) -> dict|list`` is the test seam; default is urllib with the token.
    """
    import urllib.request
    import github_api_budget as gab

    def _default_fetch(url: str, force_refresh: bool = False):
        del force_refresh
        hdrs = {"Accept": "application/vnd.github+json", "User-Agent": "bobiverse-jeeves"}
        if token:
            hdrs["Authorization"] = "Bearer " + token
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    getter = fetch_json or _default_fetch

    def _call_getter(url: str, *, force: bool = False):
        """Call ``getter`` with optional force_refresh; tolerate url-only test doubles."""
        use_force = bool(force or force_refresh)
        try:
            return getter(url, force_refresh=use_force)
        except TypeError:
            return getter(url)

    # FR #4969: one topic search per resync; persist beside the queue.
    try:
        import priority_customer as _pc

        _pc.refresh_topic_repos(home, fetch_json=_call_getter)
    except Exception:  # noqa: BLE001 - never block the queue
        pass

    def _fetch_all_pages(
        url_base: str, *, per_page: int = 100, max_pages: int = 20, force: bool = False
    ) -> list:
        """Follow GitHub list pagination (FR #1149 / #1444). One page left 100+ open issues off-queue."""
        out: list = []
        for page in range(1, max_pages + 1):
            sep = "&" if "?" in url_base else "?"
            chunk = _call_getter(
                f"{url_base}{sep}per_page={per_page}&page={page}", force=force
            )
            if not isinstance(chunk, list):
                break
            out.extend(chunk)
            if len(chunk) < per_page:
                break
        return out

    skip = {str(x).strip().lower() for x in (ignored or ()) if str(x).strip()}
    desired: list[GitClaim] = []
    fetched: list[str] = []
    failed: list[str] = []
    unchanged: list[str] = []
    open_pulls_map: dict[str, set[str]] = {}
    open_issue_ids: dict[str, set[str]] = {}  # FR #5267: open issue numbers per fetched repo
    skipped_draft = 0
    skipped_ci = 0
    fix_added = 0  # FR #4596: FIX enqueue adds counted into github-resync ok added=
    fix_dup = 0  # FR #4639: red PASSed PRs deduped as duplicate
    fix_skip_main_red = 0  # FR #4857: tip FIX skipped because main shared suite is red
    main_red_cache: dict[str, bool] = {}  # FR #4596: one main probe per repo per resync
    main_sha_cache: dict[str, str] = {}  # FR #4911: default-branch head for main-red retire
    main_sha_cache: dict[str, str] = {}  # FR #4857: default-branch SHA for main-side FIX
    # FR #2899: open pulls skipped from desired (draft/receipt) - do not "survive" keep.
    skipped_open_pulls: set[tuple[str, str]] = set()
    skipped_open_pull_meta: dict[tuple[str, str], dict] = {}
    # FR #2389: only *merged* closers remove an issue from desired. Open Closes-PRs
    # stay as MRB rows when offerable; the open issue stays desired so fr_done can
    # clear. FR #4589: open Closes (including ci-wait / draft / receipt skips) still
    # supersede FR enqueue via open_closes_map + fr_is_superseded.
    supersede_keys: set[str] = set()  # owner/repo#N closed by merged PR Closes only
    closed_by_merged_pr: set[str] = set()  # #N ids closed by merged PRs (same-repo)
    open_closes_map: dict[str, set[str]] = {}  # repo -> {#N} covered by any open PR Closes
    repo_clear: dict[str, bool] = {}   # t853u: no open non-excluded issue and no open PR
    uat_plan: dict[str, tuple[list[str], list[str]]] = {}   # repo -> (merged PRs this cycle, issues they closed)
    cycles = ledger_load(home).get("uat_cycle") or {}
    for repo in repos:
        if not REPO_RE.fullmatch(repo):
            continue
        if repo.lower() in skip or repo.split("/", 1)[-1].lower() in skip:
            continue
        # FR #785: never resync an archived/superseded source (use successor via discover rewrite).
        if repo_archived_for_queue(repo):
            continue
        issues_url = f"https://api.github.com/repos/{repo}/issues?state=open"
        pulls_url = f"https://api.github.com/repos/{repo}/pulls?state=open"
        issues_nm = False
        pulls_nm = False
        issues: list = []
        prs: list = []
        try:
            issues = _fetch_all_pages(issues_url)
        except gab.NotModified:
            # FR #4959: do not skip pulls - issues 304 alone used to hide new open PRs.
            issues_nm = True
        except Exception:  # noqa: BLE001 - one bad repo (404/403/rate limit) must not wipe its rows
            failed.append(repo)
            continue
        try:
            prs = _fetch_all_pages(pulls_url)
        except gab.NotModified:
            pulls_nm = True
        except Exception:  # noqa: BLE001
            failed.append(repo)
            continue
        if issues_nm and pulls_nm:
            # FR #3212 / #4959: both lists unchanged - keep prior rows; surface as unchanged.
            unchanged.append(repo)
            continue
        # One list changed: force-refresh the 304 side so prune/merge has a full picture
        # (empty [] from a skipped 304 would wrongly drop FR or MRB rows).
        try:
            if issues_nm:
                try:
                    issues = _fetch_all_pages(issues_url, force=True)
                except gab.NotModified:
                    # Budgeted force_refresh never 304s; url-only test doubles might.
                    issues = []
            if pulls_nm:
                try:
                    prs = _fetch_all_pages(pulls_url, force=True)
                except gab.NotModified:
                    prs = []
        except Exception:  # noqa: BLE001
            failed.append(repo)
            continue
        fetched.append(repo)
        if not isinstance(issues, list):
            issues = []
        if not isinstance(prs, list):
            prs = []
        # FR #5267: open issue ids (not pulls) so accepted rows for closed issues can leave.
        issue_ids: set[str] = set()
        for iss in issues:
            if not isinstance(iss, dict) or not isinstance(iss.get("number"), int):
                continue
            if iss.get("pull_request"):
                continue
            issue_ids.add(f"#{int(iss['number'])}")
        open_issue_ids[repo] = issue_ids
        # t853u: repo-level UAT gate. Excluded issues (needs-human, boards/mrb-home, harvest/skill
        # records, CRITICAL spam, safe-to-close, needs-mrb1 - FR #1416) never hold a repo back;
        # every other open issue or any open PR does.
        blocking = [
            i for i in issues
            if isinstance(i, dict) and not i.get("pull_request") and issue_blocks_repo_uat(
                title=str(i.get("title") or ""), body=str(i.get("body") or ""),
                labels=_label_names(i.get("labels")), state=str(i.get("state") or "open"))
        ]
        repo_clear[repo] = not blocking and not [p for p in prs if isinstance(p, dict)]
        if repo_clear[repo]:
            try:
                closed_prs = getter(f"https://api.github.com/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=50")
            except Exception:  # noqa: BLE001
                closed_prs = None
            since = _parse_iso_ts(str(cycles.get(repo.lower()) or "")) or (time.time() - UAT_MAX_AGE_S)
            merged: list[str] = []
            linked: list[str] = []
            for pr in closed_prs if isinstance(closed_prs, list) else []:
                if not isinstance(pr, dict) or not pr.get("merged_at") or not isinstance(pr.get("number"), int):
                    continue
                mts = _parse_iso_ts(str(pr.get("merged_at")))
                if mts is None or mts <= since:
                    continue
                title = str(pr.get("title") or "")
                # bobiverse#765 / #781: mrb-*-fix merges are not UAT cycle inputs.
                if is_mrb_fix_pr_title(title):
                    continue
                merged.append(f"#{pr['number']}")
                for r in extract_closes_issue_ids(title, str(pr.get("body") or ""), repo=repo):
                    if r not in linked:
                        linked.append(r)
            if merged:
                uat_plan[repo] = (merged, linked)
                # FR #2389: merged closers (recent cycle) remove issues from desired.
                for r in linked:
                    closed_by_merged_pr.add(r)
                for iss_id in linked:
                    # extract_closes may return #N; also stamp owner/repo#N supersede keys.
                    n = str(iss_id).lstrip("#")
                    if n.isdigit():
                        supersede_keys.add(f"{repo}#{n}")
        # FR #4665: parent open-ness is the full open-PR set, not PRs seen so far.
        open_pr_ids = {
            f"#{p.get('number')}"
            for p in prs
            if isinstance(p, dict) and isinstance(p.get("number"), int)
        }
        # FR #4994: among open main/master-base mrb-fix PRs for the same parent,
        # only the lowest number is offerable (one-fix-per-failure twin rule).
        main_base_fix_keeper: dict[str, int] = {}
        for p in prs:
            if not isinstance(p, dict) or not isinstance(p.get("number"), int):
                continue
            if p.get("draft") is True:
                continue
            title_p = str(p.get("title") or "")
            if not is_mrb_fix_pr_title(title_p):
                continue
            if not mrb_fix_targets_default_branch(p):
                continue
            parent_p = mrb_fix_parent_pr_id(title_p)
            if not parent_p or parent_p not in open_pr_ids:
                continue
            n_p = int(p["number"])
            prev = main_base_fix_keeper.get(parent_p)
            if prev is None or n_p < prev:
                main_base_fix_keeper[parent_p] = n_p
        for pr in prs:
            if not isinstance(pr, dict):
                continue
            num = pr.get("number")
            if not isinstance(num, int):
                continue
            title = str(pr.get("title") or "")
            body = str(pr.get("body") or "")
            refs = extract_closes_issue_ids(title, body, repo=repo)
            # FR #2389: do NOT add open-PR Closes refs to closed_by_merged_pr / supersede_keys.
            # That left open issues out of desired, so fr_done never cleared (#2380/#2383 class).
            # FR #4589: still record Closes so FR enqueue/prune can see ci-wait / draft covers.
            if refs:
                bucket = open_closes_map.setdefault(repo, set())
                for r in refs:
                    bucket.add(_norm_row_id(r))
            open_pulls_map.setdefault(repo, set()).add(f"#{num}")
            # bobiverse#224 / #781: open mrb-*-fix PRs are not MRB while the parent
            # PR is still open (stacked on the parent branch). FR #4665: once parent N
            # is merged or closed, queue the orphan as an ordinary MRB.
            # FR #4994: when the fix targets main/master while the parent is still
            # open, queue the fix (else FIX-linked parent + skipped fix deadlock).
            # Twin main-base fixes for one parent: only the lowest number queues.
            _mrb_fix_offer_resync = False
            if is_mrb_fix_pr_title(title):
                parent = mrb_fix_parent_pr_id(title)
                if not parent:
                    skipped_open_pulls.add((repo, f"#{num}"))
                    print(
                        f"resync skip mrb-fix PR {repo}#{num} parent ? no parent number",
                        flush=True,
                    )
                    continue
                if parent in open_pr_ids:
                    if mrb_fix_targets_default_branch(pr):
                        keeper = main_base_fix_keeper.get(parent)
                        if keeper is not None and num != keeper:
                            skipped_open_pulls.add((repo, f"#{num}"))
                            print(
                                f"resync skip twin mrb-fix PR {repo}#{num} keeper #{keeper}",
                                flush=True,
                            )
                            continue
                        print(
                            f"resync queue main-base mrb-fix PR {repo}#{num} "
                            f"parent {parent} still open",
                            flush=True,
                        )
                        _mrb_fix_offer_resync = True
                    else:
                        _parent_pr = None
                        _want = str(parent or "").lstrip("#")
                        for _cand in prs:
                            if not isinstance(_cand, dict):
                                continue
                            if str(_cand.get("number") or "") == _want:
                                _parent_pr = _cand
                                break
                        if mrb_fix_targets_feature_branch(pr, parent, _parent_pr):
                            print(
                                f"resync queue feature-base mrb-fix PR {repo}#{num} "
                                f"parent {parent} still open",
                                flush=True,
                            )
                            _mrb_fix_offer_resync = True
                        else:
                            skipped_open_pulls.add((repo, f"#{num}"))
                            print(
                                f"resync skip mrb-fix PR {repo}#{num} parent {parent} still open",
                                flush=True,
                            )
                            continue
                else:
                    # FR #8333: orphan fix on an explicit non-default base (e.g. already
                    # merged fr-* tip) cannot land on main --- skip and warn so a worker
                    # retargets (--base main) or recreates. Missing base still queues
                    # (fixtures / thin payloads; FR #4665).
                    if pr_base_is_explicit_non_default(pr):
                        skipped_open_pulls.add((repo, f"#{num}"))
                        print(
                            f"resync skip orphan mrb-fix PR {repo}#{num} "
                            f"non-default base {pr_base_ref(pr)} "
                            f"(FR #8333: retarget --base main or recreate)",
                            flush=True,
                        )
                        continue
                    print(
                        f"resync queue orphan mrb-fix PR {repo}#{num} parent {parent} not open",
                        flush=True,
                    )
                    _mrb_fix_offer_resync = True
            elif pr_base_is_explicit_non_default(pr):
                # Cheap check FR #8333: any open non-fix PR whose base is not
                # main/master is unlikely to land on the default branch.
                print(
                    f"resync warn non-default base PR {repo}#{num} "
                    f"base={pr_base_ref(pr)} (FR #8333)",
                    flush=True,
                )
            # FR #2604: draft open PRs must not become MRB jobs; still count as open
            # for UAT/repo_clear and FR supersede via open_pulls_map above.
            # FR #5506: draft via-intake+skill lessons backfill as MRB (#4444/#4967).
            # FR #8477: promote a real skill leaflet (ready + lesson title) first.
            # Still-draft leaflets are not offered. DONE/PASS receipts stay drafts.
            if pr.get("draft") is True and is_draft_skill_leaflet(
                title=title,
                body=body,
                labels=_label_names(pr.get("labels")),
                files=resolve_intake_pr_changed_paths(
                    pr, repo=repo, number=num, fetch_json=getter
                ),
            ):
                promoted = None
                try:
                    if promote_draft_skill is not None:
                        promoted = promote_draft_skill(repo, pr)
                    elif token:
                        promoted = github_promote_draft_skill_leaflet(
                            repo, pr, token=token
                        )
                except Exception:  # noqa: BLE001
                    promoted = None
                if isinstance(promoted, dict) and promoted.get("draft") is not True:
                    pr = promoted
                    title = str(pr.get("title") or title)
                    body = str(pr.get("body") or body)
                    print(
                        f"resync promote draft skill PR {repo}#{num}",
                        flush=True,
                    )
            if pr.get("draft") is True:
                pr_labels = _label_names(pr.get("labels"))
                _resync_paths = resolve_intake_pr_changed_paths(
                    pr, repo=repo, number=num, fetch_json=getter
                )
                _resync_head_draft = pr.get("head") if isinstance(pr.get("head"), dict) else {}
                _resync_user = pr.get("user") if isinstance(pr.get("user"), dict) else {}
                if not (
                    is_offerable_intake_skill_lesson_pr(
                        title=title, body=body, labels=pr_labels, files=_resync_paths
                    )
                    or is_copilot_fr_implement_pr(
                        title=title,
                        body=body,
                        labels=pr_labels,
                        head_ref=str(_resync_head_draft.get("ref") or ""),
                        user_login=str(_resync_user.get("login") or ""),
                        repo=repo,
                    )
                ):
                    skipped_draft += 1
                    skipped_open_pulls.add((repo, f"#{num}"))
                    # FR #5847: keep rich catalog fields for stuck-sweep Copilot match.
                    skipped_open_pull_meta.setdefault(
                        (repo, f"#{num}"),
                        {
                            "repo": repo,
                            "id": f"#{num}",
                            "kind": "pr",
                            "task": "MRB",
                            "draft": True,
                            "title": title[:160],
                            "body": (body or "")[:2000],
                            "head_ref": str(_resync_head_draft.get("ref") or ""),
                            "user_login": str(_resync_user.get("login") or ""),
                            "rule": "draft",
                        },
                    )
                    print(
                        f"resync skip draft PR {repo}#{num}",
                        flush=True,
                    )
                    continue
            # FR #7118: non-draft open PRs including intake/ harvest receipts
            # enter the MRB queue on !resync (webhook still skips receipts, FR #2650).
            pr_labels = _label_names(pr.get("labels"))
            # FR #5500: docs/mrb-* pins skip MRB while the original is still open
            # (resync used to store empty title so offer-time could not see pins).
            # FR #6044: DIRTY/CONFLICTING still fall through to FIX.
            # FR #6340: clean orphan (parent already merged/closed) falls through
            # as one MRB with docs_mrb_orphan stamp.
            _resync_head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
            _docs_mrb_orphan_resync = False
            if is_docs_mrb_pin_pr(
                title=title,
                head_ref=str(_resync_head.get("ref") or ""),
                labels=pr_labels,
            ):
                if list_pr_needs_mergeability_enrichment(pr):
                    enrich_pr_mergeability(
                        pr, repo=repo, num=num, fetch_json=getter
                    )
                try:
                    import mrb_merge_on_green as _mog_pin

                    pin_dirty = _mog_pin.merge_attempt_conflict_reason(
                        mergeable=pr.get("mergeable"),
                        merge_state=str(
                            pr.get("mergeable_state")
                            or pr.get("mergeStateStatus")
                            or ""
                        ),
                    )
                except Exception:  # noqa: BLE001
                    pin_dirty = ""
                pin_parent = docs_mrb_pin_parent_pr_id(
                    title=title, head_ref=str(_resync_head.get("ref") or "")
                )
                pin_lesson_of_lesson = is_lesson_of_lesson_pr(
                    title=title,
                    body=body,
                    labels=pr_labels,
                    head_ref=str(_resync_head.get("ref") or ""),
                )
                if pin_dirty:
                    print(
                        f"resync dirty docs/mrb pin PR {repo}#{num} -> FIX",
                        flush=True,
                    )
                elif pin_lesson_of_lesson or not pin_parent or pin_parent in open_pr_ids:
                    skipped_draft += 1
                    skipped_open_pulls.add((repo, f"#{num}"))
                    print(
                        f"resync skip docs/mrb pin PR {repo}#{num}",
                        flush=True,
                    )
                    continue
                else:
                    _docs_mrb_orphan_resync = True
                    print(
                        f"resync orphan docs/mrb pin PR {repo}#{num} "
                        f"parent {pin_parent} -> MRB",
                        flush=True,
                    )
            # FR #4466 / #4594 / #4596: open PR with auto-merge on the PASSed SHA.
            # Still queued/in_progress -> skip ci-wait (not a new MRB).
            # Already concluded FAILURE -> offer FIX (per-PR when main is green;
            # shared sig only when main itself is red). Count FIX adds in added=.
            # Keep Closes coverage via skipped_open_pulls; never re-queue MRB on same SHA.
            head_obj = pr.get("head") if isinstance(pr.get("head"), dict) else {}
            head_sha = str(head_obj.get("sha") or "")
            try:
                import mrb_merge_on_green as _mog_conflict

                conflict_rearm = _mog_conflict.rearm_conflict_blocked(
                    _root(home), repo=repo, pr=str(num), head_sha=head_sha
                )
            except Exception:  # noqa: BLE001
                conflict_rearm = ""
            if conflict_rearm == "rearmed":
                skipped_open_pulls.add((repo, f"#{num}"))
                print(
                    f"resync rearm merge-on-green after conflict {repo}#{num}",
                    flush=True,
                )
                continue
            if conflict_rearm == "blocked":
                # FR #4906: same SHA still blocked - re-offer via offer_dirty
                # (DONE/GIVEUP/NAK with no push clears the dead signature), not bare
                # enqueue_conflict_fix which permanently duplicate-dedupes.
                try:
                    import mrb_merge_on_green as _mog_conflict

                    fix_result = _mog_conflict.offer_dirty_conflict_fix(
                        _root(home),
                        repo=repo,
                        pr=str(num),
                        sha=head_sha,
                        url=str(pr.get("html_url") or ""),
                        reason="conflicting",
                    )
                except Exception as exc:  # noqa: BLE001
                    fix_result = f"error:{type(exc).__name__}"
                fix_added, fix_dup, fix_skip_main_red = _tally_fix_ci_result(
                    fix_result,
                    fix_added=fix_added,
                    fix_dup=fix_dup,
                    fix_skip_main_red=fix_skip_main_red,
                )
                skipped_open_pulls.add((repo, f"#{num}"))
                print(
                    f"resync offer FIX conflict-blocked PR {repo}#{num} "
                    f"result={fix_result}",
                    flush=True,
                )
                continue
            # FR #4683: open-PR list omits mergeable*; enrich from GET /pulls/N
            # before the dirty check (and later mergeable_state readers).
            if list_pr_needs_mergeability_enrichment(pr):
                if enrich_pr_mergeability(pr, repo=repo, num=num, fetch_json=getter):
                    print(
                        f"resync enrich mergeability PR {repo}#{num} "
                        f"mergeable={pr.get('mergeable')!r} "
                        f"state={pr.get('mergeable_state') or pr.get('mergeStateStatus')!r}",
                        flush=True,
                    )
            # FR #4679: any open non-draft DIRTY/CONFLICTING PR with no live job
            # gets one FIX (fold origin/main), even with no MRB PASS and even when
            # auto-merge is off / CI is green or cancelled. Do not leave it as a
            # stranded MRB that seats cannot merge.
            try:
                import mrb_merge_on_green as _mog_dirty

                dirty_reason = _mog_dirty.merge_attempt_conflict_reason(
                    mergeable=pr.get("mergeable"),
                    merge_state=str(
                        pr.get("mergeable_state") or pr.get("mergeStateStatus") or ""
                    ),
                )
            except Exception:  # noqa: BLE001
                dirty_reason = ""
            if dirty_reason and head_sha:
                hold_early = pr_hold_reason(
                    title=str(pr.get("title") or ""),
                    body=str(pr.get("body") or ""),
                    labels=_label_names(pr.get("labels")),
                )
                if hold_early:
                    skipped_open_pulls.add((repo, f"#{num}"))
                    print(
                        f"resync skip FIX dirty PR {repo}#{num} hold={hold_early}",
                        flush=True,
                    )
                    continue
                try:
                    import mrb_merge_on_green as _mog_dirty

                    fix_result = _mog_dirty.offer_dirty_conflict_fix(
                        _root(home),
                        repo=repo,
                        pr=str(num),
                        sha=head_sha,
                        url=str(pr.get("html_url") or ""),
                        reason=dirty_reason,
                    )
                except Exception as exc:  # noqa: BLE001
                    fix_result = f"error:{type(exc).__name__}"
                fix_added, fix_dup, fix_skip_main_red = _tally_fix_ci_result(
                    fix_result,
                    fix_added=fix_added,
                    fix_dup=fix_dup,
                    fix_skip_main_red=fix_skip_main_red,
                )
                skipped_open_pulls.add((repo, f"#{num}"))
                print(
                    f"resync offer FIX dirty PR {repo}#{num} result={fix_result}",
                    flush=True,
                )
                continue
            # FR #9924: accepted/offered MRB + required CI red → clear hold + FIX
            # (same family as DONE MRB FAIL / FR #4718). Soft-only (#9881) skips.
            try:
                check_state_hold = _resync_pr_check_state(pr, repo, num, token=token)
            except Exception:  # noqa: BLE001
                check_state_hold = ""
            try:
                import mrb_merge_on_green as _mog_9924

                trigger_9924 = _mog_9924.ci_failure_triggers_mrb_reset(check_state_hold)
            except Exception:  # noqa: BLE001
                trigger_9924 = False
            if trigger_9924 and head_sha:
                try:
                    qpeek = load_queue(_root(home))
                except Exception:  # noqa: BLE001
                    qpeek = {}
                holders_9924 = live_mrb_hold_nicks(qpeek, repo, f"#{num}")
                if holders_9924:
                    try:
                        import mrb_merge_on_green as _mog_9924

                        fix_result = _mog_9924.reset_live_mrb_hold_on_ci_red(
                            _root(home),
                            repo=repo,
                            pr=str(num),
                            sha=head_sha,
                            url=str(pr.get("html_url") or ""),
                            detail=check_state_hold or "failure",
                        )
                    except Exception as exc:  # noqa: BLE001
                        fix_result = f"error:{type(exc).__name__}"
                    fix_added, fix_dup, fix_skip_main_red = _tally_fix_ci_result(
                        fix_result,
                        fix_added=fix_added,
                        fix_dup=fix_dup,
                        fix_skip_main_red=fix_skip_main_red,
                    )
                    skipped_open_pulls.add((repo, f"#{num}"))
                    print(
                        f"resync FR #9924 CI-red reset MRB→FIX {repo}#{num} "
                        f"holders={','.join(holders_9924)} result={fix_result}",
                        flush=True,
                    )
                    continue
            pass_sha = _merge_on_green_pass_sha(home, repo, num)
            # FR #4661: ledger race --- done[] PASS + auto_merge tip still ci-wait.
            if not pass_sha:
                pass_sha = done_mrb_pass_sha_for_ci_wait(home, repo, num, head_sha)
            if open_pr_mrb_ci_wait_candidate(pr, pass_sha):
                # FR #4669: DIRTY / CONFLICTING auto-merge still needs a fold FIX,
                # even when the last FIX-CI DONE left the head SHA unchanged.
                import mrb_merge_on_green

                conflict_reason = mrb_merge_on_green.merge_attempt_conflict_reason(
                    mergeable=pr.get("mergeable"),
                    merge_state=str(
                        pr.get("mergeable_state") or pr.get("mergeStateStatus") or ""
                    ),
                )
                if conflict_reason:
                    try:
                        import mrb_merge_on_green

                        fix_result = mrb_merge_on_green.offer_dirty_conflict_fix(
                            _root(home),
                            repo=repo,
                            pr=str(num),
                            sha=pass_sha,
                            url=str(pr.get("html_url") or ""),
                            reason=conflict_reason,
                        )
                    except Exception as exc:  # noqa: BLE001
                        fix_result = f"error:{type(exc).__name__}"
                    fix_added, fix_dup, fix_skip_main_red = _tally_fix_ci_result(
                        fix_result,
                        fix_added=fix_added,
                        fix_dup=fix_dup,
                        fix_skip_main_red=fix_skip_main_red,
                    )
                    skipped_open_pulls.add((repo, f"#{num}"))
                    print(
                        f"resync offer FIX conflict PR {repo}#{num} result={fix_result}",
                        flush=True,
                    )
                    continue
                # Candidate (auto-merge + same SHA). Resolve live/injected checks.
                check_state = _resync_pr_check_state(pr, repo, num, token=token)
                if open_pr_mrb_checks_failed(check_state):
                    try:
                        import mrb_merge_on_green

                        cancel_head = (
                            str(check_state or "").strip().lower().split(":", 1)[0]
                        )
                        if cancel_head.startswith("completed/"):
                            cancel_head = cancel_head.split("/", 1)[-1]
                        if cancel_head in ("cancelled", "canceled", "skipped"):
                            run_id = str(
                                pr.get("run_id") or pr.get("check_run_id") or ""
                            )
                            behind = bool(pr.get("behind_main")) or (
                                str(pr.get("mergeable_state") or "").lower() == "behind"
                            )
                            if not run_id and not behind:
                                head_obj = (
                                    pr.get("head")
                                    if isinstance(pr.get("head"), dict)
                                    else {}
                                )
                                tip_sha = str(head_obj.get("sha") or "")
                                if tip_sha:
                                    try:
                                        payload = fetch_json(
                                            "https://api.github.com/repos/"
                                            f"{repo}/commits/{tip_sha}/check-runs"
                                        )
                                        run_id = (
                                            mrb_merge_on_green.cancelled_workflow_run_id(
                                                payload
                                            )
                                        )
                                    except Exception:  # noqa: BLE001
                                        run_id = ""
                            rerun_result = mrb_merge_on_green.rerun_cancelled_passed(
                                _root(home),
                                repo=repo,
                                pr=str(num),
                                pass_sha=pass_sha,
                                run_id=run_id,
                                behind=behind,
                                token=token,
                            )
                            skipped_open_pulls.add((repo, f"#{num}"))
                            print(
                                f"resync rerun cancelled CI {repo}#{num} result={rerun_result}",
                                flush=True,
                            )
                            continue
                        repo_c = canonical_queue_repo(repo)
                        if repo_c not in main_red_cache:
                            main_red_cache[repo_c] = (
                                mrb_merge_on_green.main_branch_checks_red(
                                    repo_c, token=token
                                )
                            )
                        if repo_c not in main_sha_cache:
                            main_sha_cache[repo_c] = (
                                mrb_merge_on_green.main_branch_head_sha(
                                    repo_c, token=token
                                )
                            )
                        fix_result = mrb_merge_on_green.enqueue_fix_ci(
                            _root(home),
                            repo=repo,
                            pr=str(num),
                            pass_sha=pass_sha,
                            url=str(pr.get("html_url") or ""),
                            detail=check_state or "failure",
                            main_red=bool(main_red_cache[repo_c]),
                            main_sha=str(main_sha_cache.get(repo_c) or ""),
                            token=token,
                            mergeable=pr.get("mergeable"),
                            merge_state=str(
                                pr.get("mergeable_state")
                                or pr.get("mergeStateStatus")
                                or ""
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001
                        fix_result = f"error:{type(exc).__name__}"
                    # FR #4596: FIX rows must show in github-resync ok added=.
                    fix_added, fix_dup, fix_skip_main_red = _tally_fix_ci_result(
                        fix_result,
                        fix_added=fix_added,
                        fix_dup=fix_dup,
                        fix_skip_main_red=fix_skip_main_red,
                    )
                    skipped_open_pulls.add((repo, f"#{num}"))
                    print(
                        f"resync offer FIX ci-failed PR {repo}#{num} result={fix_result}",
                        flush=True,
                    )
                    continue
                # pending / success / unknown: still ci-wait (not a new MRB).
                skipped_ci += 1
                skipped_open_pulls.add((repo, f"#{num}"))
                print(
                    f"resync skip ci-wait PR {repo}#{num}",
                    flush=True,
                )
                continue
            # FR #4833: PASS@head without auto_merge (allow_auto_merge=false).
            # Never re-queue MRB. FIX only when checks failed and not human-gated.
            if open_pr_mrb_pass_sha_unchanged(pr, pass_sha):
                check_state = _resync_pr_check_state(pr, repo, num, token=token)
                if open_pr_mrb_checks_failed(check_state):
                    try:
                        import mrb_merge_on_green

                        repo_c = canonical_queue_repo(repo)
                        if repo_c not in main_red_cache:
                            main_red_cache[repo_c] = (
                                mrb_merge_on_green.main_branch_checks_red(
                                    repo_c, token=token
                                )
                            )
                        if repo_c not in main_sha_cache:
                            main_sha_cache[repo_c] = (
                                mrb_merge_on_green.main_branch_head_sha(
                                    repo_c, token=token
                                )
                            )
                        fix_result = mrb_merge_on_green.enqueue_fix_ci(
                            _root(home),
                            repo=repo,
                            pr=str(num),
                            pass_sha=pass_sha,
                            url=str(pr.get("html_url") or ""),
                            detail=check_state or "failure",
                            main_red=bool(main_red_cache[repo_c]),
                            main_sha=str(main_sha_cache.get(repo_c) or ""),
                            token=token,
                            mergeable=pr.get("mergeable"),
                            merge_state=str(
                                pr.get("mergeable_state")
                                or pr.get("mergeStateStatus")
                                or ""
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001
                        fix_result = f"error:{type(exc).__name__}"
                    fix_added, fix_dup, fix_skip_main_red = _tally_fix_ci_result(
                        fix_result,
                        fix_added=fix_added,
                        fix_dup=fix_dup,
                        fix_skip_main_red=fix_skip_main_red,
                    )
                    skipped_open_pulls.add((repo, f"#{num}"))
                    print(
                        f"resync offer FIX pass-sha-unchanged PR {repo}#{num} "
                        f"result={fix_result}",
                        flush=True,
                    )
                    continue
                skipped_ci += 1
                skipped_open_pulls.add((repo, f"#{num}"))
                print(
                    f"resync skip pass-sha-unchanged PR {repo}#{num}",
                    flush=True,
                )
                continue
            # FR #4718: newest MRB board is FAIL at this head and no mrb-N-fix
            # PR is open. Queue FIX (implement the board), never another MRB.
            # FR #8298: the list-pulls payload has no comment bodies. When a
            # fix(mrb-N) sibling is open, load the board so a FAIL still drops
            # the parent even if the reviewer offer was recorded as a nack.
            if not isinstance(pr.get("comments"), list):
                _sib_fix = False
                for _other in prs:
                    if not isinstance(_other, dict):
                        continue
                    if gitclaim_mrb_fix_parent := mrb_fix_parent_pr_id(
                        str(_other.get("title") or "")
                    ):
                        if gitclaim_mrb_fix_parent == f"#{num}":
                            _sib_fix = True
                            break
                if _sib_fix:
                    try:
                        import mrb_merge_gate as _mg_fail

                        _fetched_comments = _mg_fail.fetch_issue_comments(
                            repo, str(num)
                        )
                        if isinstance(_fetched_comments, list):
                            pr["comments"] = _fetched_comments
                    except Exception:  # noqa: BLE001
                        pass
            try:
                import mrb_merge_on_green as _mog_fail

                fail_rec = mrb_fail_record(home, repo, f"#{num}")
                fail_sha, fail_nick = _mog_fail.mrb_fail_board_at_head(
                    pr, head_sha, fail_rec
                )
            except Exception:  # noqa: BLE001
                fail_sha, fail_nick = "", ""
            if fail_sha:
                skipped_open_pulls.add((repo, f"#{num}"))
                linked = False
                try:
                    import mrb_merge_on_green as _mog_fail

                    # FR #4800: harvest disposition boards never enqueue FIX.
                    if _mog_fail.skip_mrb_fail_fix_for_harvest(
                        title=title,
                        labels=pr_labels,
                        closed=False,
                        merged=False,
                        comments=pr.get("comments")
                        if isinstance(pr.get("comments"), list)
                        else None,
                    ):
                        print(
                            f"resync skip FIX harvest-disposition PR {repo}#{num}",
                            flush=True,
                        )
                        continue
                    linked = _mog_fail.linked_fail_fix_open(prs, str(num))
                    fix_result = "linked"
                    if not linked:
                        fix_result = _mog_fail.enqueue_mrb_fail_fix(
                            _root(home),
                            repo=repo,
                            pr=str(num),
                            sha=fail_sha,
                            url=str(pr.get("html_url") or ""),
                            nick=fail_nick,
                            pr_state={
                                "title": title,
                                "labels": list(pr_labels),
                                "closed": False,
                                "merged": False,
                                "comments": pr.get("comments")
                                if isinstance(pr.get("comments"), list)
                                else None,
                                "sha": fail_sha,
                            },
                        )
                except Exception as exc:  # noqa: BLE001
                    fix_result = f"error:{type(exc).__name__}"
                fix_added, fix_dup, fix_skip_main_red = _tally_fix_ci_result(
                    fix_result,
                    fix_added=fix_added,
                    fix_dup=fix_dup,
                    fix_skip_main_red=fix_skip_main_red,
                )
                print(
                    f"resync offer FIX mrb-fail PR {repo}#{num} result={fix_result}",
                    flush=True,
                )
                continue
            lesson = is_harvest_lesson_pr(title=title, labels=pr_labels)
            orphan_line = ""
            if _docs_mrb_orphan_resync:
                orphan_line = (
                    f"docs_mrb_orphan parent={pin_parent} "
                    "(missing required check -> FAIL or re-run; no pin-of-pin)"
                )
            # FR #8298: parent stays visible as blocked on the reviewer's fr-N
            # fix PR, not as no_eligible_reviewer.
            _awaiting_fix = ""
            for _other in prs:
                if not isinstance(_other, dict) or not isinstance(_other.get("number"), int):
                    continue
                if _other.get("draft") is True:
                    continue
                _pt = str(_other.get("title") or "")
                if not is_mrb_fix_pr_title(_pt):
                    continue
                if mrb_fix_parent_pr_id(_pt) != f"#{num}":
                    continue
                if mrb_fix_targets_feature_branch(_other, f"#{num}", pr):
                    _awaiting_fix = f"#{int(_other['number'])}"
                    break
            if _awaiting_fix:
                _fix_line = f"awaiting_fix_pr {_awaiting_fix}"
                orphan_line = f"{orphan_line} {_fix_line}".strip() if orphan_line else _fix_line
            desired.append(
                GitClaim(
                    repo=repo,
                    task="MRB",
                    id=f"#{num}",
                    event="pull_request",
                    action="opened",
                    line=orphan_line,
                    refs=() if lesson else refs,
                    title=title,
                    body=body,
                    labels=pr_labels,
                    harvest_lesson=lesson,
                    opened_by=lesson_pr_opener_seat(body) if lesson else "",
                    docs_mrb_orphan=_docs_mrb_orphan_resync,
                    mrb_fix_offer=_mrb_fix_offer_resync,
                )
            )
        for iss in issues:
            if not isinstance(iss, dict) or iss.get("pull_request"):
                continue
            num = iss.get("number")
            if not isinstance(num, int):
                continue
            ident = f"#{num}"
            if ident in closed_by_merged_pr:
                continue
            if fr_issue_key(repo, ident) in supersede_keys:
                continue  # FR #254 / #2389: merged Closes only
            title = str(iss.get("title") or "")
            body = str(iss.get("body") or "")
            labels = _label_names(iss.get("labels"))
            state = str(iss.get("state") or "open")
            _iss_digest = bool(
                digest_issue_reason(
                    {
                        "task": "FR",
                        "title": title,
                        "body": body,
                        "labels": list(labels),
                    }
                )
            )
            if issue_skip_fr_reason(title=title, body=body, labels=labels, state=state) and not _iss_digest:
                continue
            if (_repo_key(repo), _norm_row_id(ident)) in _SKIP_FR_ISSUE_PINS:
                continue  # FR #2480 hard-pin umbrella
            if (_repo_key(repo), _norm_row_id(ident)) in _NEEDS_HUMAN_ISSUE_PINS:
                continue  # FR #6027 WCF live hold
            desired.append(
                GitClaim(
                    repo=repo,
                    task="FR",
                    id=ident,
                    event="issues",
                    action="opened",
                    line="",
                    title=title,
                    body=body,
                    labels=labels,
                    state=state,
                )
            )

    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            # FR #3817: fold SimonBarnett/x vs simonbarnett/x twins before want/drop logic.
            collapsed_n = collapse_case_variant_twins(doc)
            want = {_job_key(c.repo, c.task, c.id) for c in desired}
            fetched_set = set(fetched)
            fetched_keys = {_repo_key(r) for r in fetched}
            # Case-insensitive open-pull and skipped-pull indexes (FR #3817).
            open_pulls_by_key: dict[str, set[str]] = {}
            for rname, nums in (open_pulls_map or {}).items():
                open_pulls_by_key.setdefault(_repo_key(rname), set()).update(nums or ())
            skipped_pulls_by_key: set[tuple[str, str]] = {
                (_repo_key(r), _norm_row_id(i)) for (r, i) in (skipped_open_pulls or set())
            }

            def _row_fetched(repo_s: str) -> bool:
                return _repo_key(repo_s) in fetched_keys

            def _row_open_pulls(repo_s: str) -> set[str]:
                return open_pulls_by_key.get(_repo_key(repo_s)) or set()

            def _repo_clear_for(repo_s: str) -> bool:
                if repo_s in repo_clear:
                    return bool(repo_clear.get(repo_s, True))
                rk = _repo_key(repo_s)
                for name, clear in repo_clear.items():
                    if _repo_key(name) == rk:
                        return bool(clear)
                return True

            before = len(doc["unaccepted"])
            keep = []
            dropped_detail: list[str] = []
            if collapsed_n:
                dropped_detail.append(f"case_twin_collapse x{collapsed_n}")
            for row in doc["unaccepted"]:
                task_u = str(row.get("task") or "").upper()
                repo_s = str(row.get("repo") or "")
                ident_n = _norm_row_id(row.get("id"))
                job_k = _job_key(repo_s, task_u, ident_n)
                if task_u == "UAT":
                    # FR #818 / t853u: only keep real repo-level UAT (#0 + repo_uat).
                    if not is_repo_uat(row):
                        dropped_detail.append(f"{_row_drop_label(row)} uat_not_repo_level")
                        continue
                    # FR #9382: drop UAT when the repo has no release to build.
                    if uat_no_release_to_build_reason(row, home=home):
                        dropped_detail.append(
                            f"{_row_drop_label(row)} uat_no_release_to_build"
                        )
                        continue
                    if (
                        _row_fetched(repo_s)
                        and not _repo_clear_for(repo_s)
                    ):
                        # FR #2971: drop even when offered_to is set - sticky shop
                        # offers must not survive after a blocking FR opens.
                        dropped_detail.append(f"{_row_drop_label(row)} uat_repo_not_clear")
                        continue  # new issue / PR opened: the repo is no longer clear, UAT waits
                # BOB-G3 / FR #9821: digest gate rows survive skip_fr + hold prune,
                # but closed digests absent from want still fall through to removal
                # (MRB #9834: do not bypass closure reconciliation).
                if task_u == "FR" and digest_issue_reason(row):
                    if not (_row_fetched(repo_s) and job_k not in want):
                        keep.append(row)
                        continue
                if task_u == "FR" and row_skip_fr_reason(row):
                    dropped_detail.append(f"{_row_drop_label(row)} skip_fr")
                    continue  # FR #180 local junk
                if task_u == "FR" and row_fr_skip_offer_reason(row):
                    why = row_fr_skip_offer_reason(row) or ""
                    tag = "fr_park_only" if why.startswith("park-only") else "fr_hold"
                    dropped_detail.append(f"{_row_drop_label(row)} {tag}")
                    continue  # FR #4009 / #8741: hold or park-only
                # bob_d7_wire_hold / FR #9455: Depends-on OPEN is offer-skip only - keep.
                if task_u == "FR" and depends_gate_reason(
                    row, doc, issue_fetch=depends_issue_fetch_checker()
                ):
                    keep.append(row)
                    continue
                if task_u == "FR" and not fr_row_offerable(row):
                    dropped_detail.append(f"{_row_drop_label(row)} fr_not_offerable")
                    continue  # FR #846: /pull/ URL is never an FR
                if task_u == "FR" and fr_is_superseded(
                    doc,
                    repo_s,
                    str(row.get("id") or ""),
                    open_pulls=open_pulls_map,
                    fetched_repos=set(fetched),
                    open_closes=open_closes_map,
                ):
                    dropped_detail.append(f"{_row_drop_label(row)} fr_superseded")
                    continue  # FR #254 / #4589
                # FR #846: drop FR whose id is an open pull number for this repo.
                if task_u == "FR":
                    if ident_n in _row_open_pulls(repo_s):
                        dropped_detail.append(f"{_row_drop_label(row)} fr_is_open_pull")
                        continue
                if (
                    _row_fetched(repo_s)
                    and task_u == "FR"
                    and job_k not in want
                ):
                    # FR #846: do not preserve closed-issue / closed-PR phantoms via offered_to.
                    dropped_detail.append(f"{_row_drop_label(row)} fr_not_in_want")
                    continue
                if (
                    _row_fetched(repo_s)
                    and task_u in ("FR", "MRB")
                    and job_k not in want
                    and not mrb_row_should_survive_resync(
                        row, want=want, fetched=fetched_set
                    )
                ):
                    # FR #2899: still-open pull that missed desired (label race / transient
                    # want miss) must survive - unless this cycle classified it draft/receipt.
                    if (
                        task_u == "MRB"
                        and ident_n in _row_open_pulls(repo_s)
                        and (_repo_key(repo_s), ident_n) not in skipped_pulls_by_key
                    ):
                        _heal_mrb_pull_url(row, force=True)
                        keep.append(row)
                        continue
                    # FR #1323 / #2458: drop MERGED/closed even when offered_to is set
                    dropped_detail.append(f"{_row_drop_label(row)} not_in_want")
                    continue
                # FR #7653: a FIX row for a PR that is no longer open (merged or
                # closed) must not stay offerable. Main-red FIX has no PR number.
                if (
                    task_u == "FIX"
                    and not _is_main_red_fix_row_local(row)
                    and _row_fetched(repo_s)
                    and ident_n
                    and ident_n not in _row_open_pulls(repo_s)
                ):
                    dropped_detail.append(f"{_row_drop_label(row)} fix_pr_not_open")
                    continue
                # FR #1323 / #1585: drop ledger-held MRB only when GitHub no longer wants it.
                # Open pulls in ``want`` must survive keep so offered_to/seq are preserved;
                # stale mrb_done stamps are cleared below when re-enqueueing desired MRBs.
                if (
                    task_u == "MRB"
                    and mrb_ledger_done_hold(home, repo_s, ident_n)
                    and job_k not in want
                    and not (
                        ident_n in _row_open_pulls(repo_s)
                        and (_repo_key(repo_s), ident_n) not in skipped_pulls_by_key
                    )
                ):
                    dropped_detail.append(f"{_row_drop_label(row)} mrb_ledger_done")
                    continue
                keep.append(row)
            dropped = before - len(keep)
            doc["unaccepted"] = keep
            # FR #2458: belt-and-suspenders - drop MRB absent from open pulls for fetched repos
            # (covers id-shape / offered_to edge cases the keep loop may miss).
            # Do not pass home here: without an open-PR checker, ledger mrb_done would
            # re-kill still-open rows (FR #1585). open_pulls alone is the truth for this pass.
            purged_n = _purge_dead_mrb_unaccepted(
                doc,
                open_pulls=open_pulls_map,
                fetched_repos=fetched_set,
            )
            if purged_n:
                dropped += purged_n
                dropped_detail.append(f"purge_dead_mrb x{purged_n}")
            # FR #4682: drop unaccepted FIX and finish accepted FIX when the PR
            # is no longer open (merged/closed webhook miss left the seat NAK busy).
            # FR #4911: also retire main-red FIX when main is green / signature SHA moved.
            # Fill caches for any fetched repo that still has a main-red row.
            try:
                import mrb_merge_on_green as _mog_purge

                for bucket in (doc.get("unaccepted") or []), (doc.get("accepted") or []):
                    for row in bucket:
                        if not isinstance(row, dict) or not _is_main_red_fix_row_local(
                            row
                        ):
                            continue
                        repo_c = canonical_queue_repo(
                            str(row.get("repo") or "")
                        ) or str(row.get("repo") or "").strip()
                        if not repo_c or repo_c not in fetched_set:
                            continue
                        if repo_c not in main_red_cache:
                            with contextlib.suppress(Exception):
                                main_red_cache[repo_c] = bool(
                                    _mog_purge.main_branch_checks_red(
                                        repo_c, token=token
                                    )
                                )
                        if repo_c not in main_sha_cache:
                            with contextlib.suppress(Exception):
                                main_sha_cache[repo_c] = str(
                                    _mog_purge.main_branch_head_sha(
                                        repo_c, token=token
                                    )
                                    or ""
                                )
            except Exception:
                pass
            fix_un_n = _purge_dead_fix_unaccepted(
                doc,
                open_pulls=open_pulls_map,
                fetched_repos=fetched_set,
                main_red_by_repo=main_red_cache,
                main_sha_by_repo=main_sha_cache,
            )
            fix_acc_n = _purge_dead_fix_accepted(
                doc,
                open_pulls=open_pulls_map,
                fetched_repos=fetched_set,
                home=home,
                main_red_by_repo=main_red_cache,
                main_sha_by_repo=main_sha_cache,
            )
            if fix_un_n or fix_acc_n:
                dropped += int(fix_un_n) + int(fix_acc_n)
                dropped_detail.append(
                    f"purge_dead_fix un={fix_un_n} acc={fix_acc_n}"
                )
            added = int(fix_added)  # FR #4596: include FIX adds from the fetch pass
            # FR #4639: keep the duplicate count for the summary (set in the fetch pass).
            fetched_set2 = set(fetched)
            # Premature DONE while GitHub issue/PR still open: pull those rows out of done
            # so resync can re-queue them (FR #1150 / #1444).
            # FR #2617: keep DONE FR rows that carry a /pull/ URL while that implement PR
            # is still open (or its repo was not fetched). Stripping them broke
            # fr_superseded_by_done_pr and let the FR re-enter unaccepted right after DONE.
            # FR #4373: remember stripped open FRs so re-enqueue stamps reopen history and
            # clears machine pins (bobiverse must never stick on ionos after reopen).
            reopened_from_done: dict[tuple[str, str], dict] = {}
            if isinstance(doc.get("done"), list):
                still_open = {(c.repo, c.task, c.id) for c in desired}
                kept_done: list = []
                for r in doc["done"]:
                    if not isinstance(r, dict):
                        continue
                    key = (
                        str(r.get("repo") or ""),
                        str(r.get("task") or ""),
                        str(r.get("id") or ""),
                    )
                    if key not in still_open:
                        kept_done.append(r)
                        continue
                    if str(r.get("task") or "").upper() == "FR":
                        parsed = parse_github_pull_url(str(r.get("url") or ""))
                        if parsed:
                            pr_repo, pr_id = parsed
                            if pr_repo not in fetched_set2:
                                kept_done.append(r)
                                continue
                            if pr_id in (open_pulls_map.get(pr_repo) or set()):
                                kept_done.append(r)
                                continue
                        # Drop premature DONE (issue still open, no open implement PR).
                        reopened_from_done[
                            (_repo_key(str(r.get("repo") or "")), _norm_row_id(r.get("id")))
                        ] = r
                        continue
                    # Drop premature DONE for non-FR (issue/PR still open).
                doc["done"] = kept_done
            ledger_now = ledger_load(home)

            def _fr_done_hold(repo: str, ident: str) -> bool:
                # Ledger fr_done means a seat already DONE'd this FR (PR may be in MRB).
                # Hold only while the FR is *not* in the GitHub want set - if desired still
                # lists it, no open PR Closes it, so suppressing enqueue stranded open
                # issues (e.g. #1201) and Jeeves reported empty while GitHub showed work.
                done_ts = _parse_iso_ts(
                    str((ledger_now.get("fr_done") or {}).get(_lkey(repo, ident)) or "")
                )
                return done_ts is not None and (time.time() - done_ts) < FR_DONE_HOLD_S

            # Drop stale unaccepted FR rows that are still inside the hold *and* not wanted
            # by GitHub (PR open / issue closed). Wanted FRs must stay enqueueable.
            # FR #3817: want_fr keys are case-insensitive on repo.
            want_fr = {
                (_repo_key(c.repo), _norm_row_id(c.id)) for c in desired if c.task == "FR"
            }
            doc["unaccepted"] = [
                r
                for r in doc["unaccepted"]
                if not (
                    isinstance(r, dict)
                    and str(r.get("task") or "").upper() == "FR"
                    and _fr_done_hold(str(r.get("repo") or ""), str(r.get("id") or ""))
                    and (
                        _repo_key(r.get("repo")),
                        _norm_row_id(r.get("id")),
                    )
                    not in want_fr
                )
            ]
            cleared_fr_done: list[str] = []
            cleared_mrb_done: list[str] = []
            for claim in desired:
                # FR #2389 / #1201 / #1482: clear fr_done for every desired open issue even when
                # fr_is_superseded skips re-enqueue (open Closes-PR → MRB). Otherwise the stamp
                # sticks 24h while the issue stays OPEN with no merged closer.
                if claim.task == "FR":
                    fk = _lkey(claim.repo, claim.id)
                    if fk in (ledger_now.get("fr_done") or {}):
                        cleared_fr_done.append(fk)
                if claim.task == "FR" and fr_is_superseded(
                    doc,
                    claim.repo,
                    claim.id,
                    open_pulls=open_pulls_map,
                    fetched_repos=fetched_set2,
                    open_closes=open_closes_map,
                ):
                    continue  # FR #254 / #4589: MRB / open Closes (incl. ci-wait) supersedes FR
                # FR #1585: open PR still on GitHub - clear premature mrb_done so offer
                # purge cannot wipe the row resync just (re)queued.
                # FR #8278: keep the stamp when DONE PASS / merge-on-green PASS exists
                # (customer allow_auto_merge=false ci-wait must not bounce the same head).
                if claim.task == "MRB":
                    mk = _lkey(claim.repo, claim.id)
                    if mk in (ledger_now.get("mrb_done") or {}):
                        if not _mrb_review_finished(doc, home, claim.repo, claim.id):
                            cleared_mrb_done.append(mk)
                mrb_url = (
                    f"https://github.com/{claim.repo}/pull/{claim.id.lstrip('#')}" if claim.task == "MRB" else ""
                )
                prior_done = None
                if claim.task == "FR":
                    prior_done = reopened_from_done.get(
                        (_repo_key(claim.repo), _norm_row_id(claim.id))
                    )
                if any(_same(r, claim.repo, claim.task, claim.id) for r in doc["accepted"] + doc["unaccepted"]):
                    # already queued/claimed: keep its line, seq and offer fields; but an MRB row with no real pull
                    # URL is never offerable (FR #595), so heal it (t855u: resync-made MRB rows were all unofferable)
                    if mrb_url:
                        for r in doc["unaccepted"]:
                            if _same(r, claim.repo, "MRB", claim.id) and not PULL_URL_RE.search(str(r.get("url") or "")):
                                r["url"] = mrb_url
                    # FR #1093: refresh title/body/labels and stamp require_machine on stale rows
                    # (resync used to skip already-queued FRs, so WP0 pins never landed).
                    # FR #3277: heal missing author_seat/implementer_seat from DONE FR / Closes refs.
                    author_extra = mrb_author_extra_from_doc(doc, claim) if claim.task == "MRB" else {}
                    for r in doc["unaccepted"]:
                        if not _same(r, claim.repo, claim.task, claim.id):
                            continue
                        if claim.title:
                            r["title"] = claim.title
                        if claim.body:
                            # FR #9543 / #2312: keep dedicated require_machine pin lines.
                            r["body"] = _body_for_queue(claim.body)
                        if claim.labels:
                            r["labels"] = list(claim.labels)
                        if claim.harvest_lesson:
                            _heal_lesson_mrb_row(r, claim.opened_by)
                        elif author_extra and not row_author_seats(r):
                            for k, v in author_extra.items():
                                if v:
                                    r[k] = v
                        if claim.docs_mrb_orphan:
                            r["docs_mrb_orphan"] = "1"
                        if claim.mrb_fix_offer:
                            r["mrb_fix_offer"] = "1"
                        if prior_done is not None:
                            # FR #4373: reopen via rebuild - clear pins + history note.
                            prepare_reopened_fr_row(
                                r, claim, via="resync", prior_done=prior_done
                            )
                        else:
                            _stamp_require_machine(r, claim)
                    # Clear *stale* needs_human (keep-the-flow) but keep the intentional
                    # FR #180 gate after GIVEUP_NEEDS_HUMAN_COUNT giveups.
                    for r in doc["unaccepted"]:
                        if not _same(r, claim.repo, claim.task, claim.id):
                            continue
                        if not r.get("needs_human"):
                            continue
                        # FR #8326: a head-mismatch giveup is a seat/worktree fault.
                        # Clear the stamp so the MRB can be offered again after the
                        # review-branch create is installed.
                        if heal_worktree_head_mismatch_row(r):
                            continue
                        if int(r.get("giveup_count") or 0) >= GIVEUP_NEEDS_HUMAN_COUNT:
                            continue
                        r.pop("needs_human", None)
                    continue
                extra_add: dict[str, str] = {}
                if mrb_url:
                    extra_add["url"] = mrb_url
                if claim.task == "MRB":
                    extra_add.update(mrb_author_extra_from_doc(doc, claim))
                if claim.docs_mrb_orphan:
                    extra_add["docs_mrb_orphan"] = "1"
                if claim.mrb_fix_offer:
                    extra_add["mrb_fix_offer"] = "1"
                if _append_unaccepted(doc, claim, home=home, **extra_add) == "added":
                    added += 1
                    if prior_done is not None:
                        for r in doc["unaccepted"]:
                            if not _same(r, claim.repo, "FR", claim.id):
                                continue
                            prepare_reopened_fr_row(
                                r, claim, via="resync", prior_done=prior_done
                            )
                            break
            for urepo, (merged, linked) in uat_plan.items():
                # FR #9382: never enqueue UAT #0 for repos with no release to build.
                if not repo_has_uat_release_to_build(urepo, home=home):
                    _log_queue_purge(
                        f"INFO git-claim skip uat {urepo} reason=no-release-to-build"
                    )
                    continue
                if any(
                    str(r.get("repo")) == urepo and str(r.get("task") or "").upper() == "UAT" and r.get("repo_uat")
                    for r in doc["accepted"] + doc["unaccepted"]
                ):
                    continue                      # one repo UAT at a time
                uat = GitClaim(repo=urepo, task="UAT", id="#0", event="repo", action="uat",
                               line=f"UAT {urepo}: all issues closed, all PRs merged ({len(merged)} merged this cycle)",
                               refs=tuple(merged) + tuple(x for x in linked if x not in merged))
                if _append_unaccepted(doc, uat, home=home) == "added":
                    for r in doc["unaccepted"]:
                        if _same(r, urepo, "UAT", "#0"):
                            r["repo_uat"] = True
                            r["merged_prs"] = list(merged)
                            r["url"] = f"https://github.com/{urepo}"
                    added += 1

            def sk(row: dict) -> tuple:
                ident = str(row.get("id") or "#0")
                try:
                    n = int(ident.lstrip("#"))
                except ValueError:
                    n = 0
                return (str(row.get("repo") or ""), n, str(row.get("task") or ""))

            doc["unaccepted"].sort(key=sk)
            for i, row in enumerate(doc["unaccepted"], start=1):
                row["seq"] = i
            # FR #1508: drop focus items for closed issues/PRs so strict focus
            # reflects open ungated work (not a graveyard of closed ranks).
            try:
                import focus_ignore as _fi

                open_keys = set()
                for c in desired:
                    open_keys.add(f"{c.repo}{c.id}".lower())
                for repo, nums in (open_pulls_map or {}).items():
                    for num in nums or ():
                        n = str(num).lstrip("#")
                        open_keys.add(f"{repo}#{n}".lower())
                focus_pruned = _fi.prune_closed_focus_items(home, open_keys)
                # FR #1520: drop owner/repo#N items when that repo is already focused.
                focus_redundant = _fi.prune_redundant_focus_items(home)
            except Exception:
                focus_pruned = 0
                focus_redundant = 0
            # FR #5267: closed issue/PR (or cancel already delivered) leaves accepted,
            # whoever holds it. Stranded nick=copilot rows return to the seat queue.
            try:
                import copilot_dispatch as _cd5267

                _cd5267.settle_stuck_accepted_unlocked(
                    home,
                    doc,
                    now=time.time(),
                    open_issues=open_issue_ids,
                    open_pulls=open_pulls_map,
                    fetched_repos=set(fetched),
                )
            except Exception:  # noqa: BLE001 - queue write must still happen
                pass
            _write_queue(queue_path(home), doc)
            # FR #5510: persist open catalog so stuck-sweep can find untracked/held items offline.
            with contextlib.suppress(Exception):
                import stuck_job_sweep as _sjs5510
                cat = []
                for c in desired:
                    cat.append({
                        "repo": c.repo,
                        "id": c.id,
                        "task": c.task,
                        "kind": "pr" if str(c.task).upper() == "MRB" else "issue",
                        "title": (c.line or "")[:160],
                    })
                for repo, num in sorted(skipped_open_pulls):
                    key = (repo, num if str(num).startswith("#") else f"#{num}")
                    meta = skipped_open_pull_meta.get(key)
                    if isinstance(meta, dict):
                        cat.append(dict(meta))
                    else:
                        cat.append({
                            "repo": repo,
                            "id": num if str(num).startswith("#") else f"#{num}",
                            "kind": "pr",
                            "task": "MRB",
                            "rule": "skipped_resync",
                        })
                _sjs5510.write_open_catalog(home, cat)
            # FR #3205: refresh ordered offer candidates off the IRC thread (resync path).
            with contextlib.suppress(Exception):
                rebuild_offer_precompute(home, list(doc.get("unaccepted") or []))
            if cleared_fr_done or cleared_mrb_done:
                def _clear_stale_done_stamps(led: dict) -> None:
                    if cleared_fr_done:
                        fd = led.setdefault("fr_done", {})
                        for k in cleared_fr_done:
                            fd.pop(k, None)
                    if cleared_mrb_done:
                        md = led.setdefault("mrb_done", {})
                        for k in cleared_mrb_done:
                            md.pop(k, None)

                with contextlib.suppress(OSError):
                    _ledger_update(home, _clear_stale_done_stamps)
            # FR #9552: reconcile open fr-digest issues with no remaining open children.
            fr_digest_closed: list[dict] = []
            with contextlib.suppress(Exception):
                import fr_digest_auto_close as _fac

                for _repo in list(fetched or []):
                    if not isinstance(_repo, str) or "/" not in _repo:
                        continue
                    fr_digest_closed.extend(
                        r
                        for r in (_fac.reconcile_repo(_repo) or [])
                        if isinstance(r, dict) and r.get("action") == "closed"
                    )
            result = {
                "ok": True,
                "unaccepted": len(doc["unaccepted"]),
                "added": added,
                "dropped": dropped,
                "dropped_detail": list(dropped_detail),
                "skipped_draft": int(skipped_draft),
                "skipped_ci": int(skipped_ci),
                "fix_dup": int(fix_dup),
                "fix_skip_main_red": int(fix_skip_main_red),
                "focus_pruned": int(focus_pruned),
                "focus_redundant": int(focus_redundant),
                "repos": list(fetched),
                "failed": list(failed),
                "unchanged": list(unchanged),
            }
            if fr_digest_closed:
                result["fr_digest_auto_close"] = fr_digest_closed
            return result
    except (TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def _unparseable_offer_age_s() -> float:
    """Age for a missing or unparseable ``offered_ts``.

    Older than every sticky offer window, so the row is not a live offer
    (giveup/done/nack is ``OFFER_TIMEOUT_S + GIVEUP_OFFER_EXTRA_S``, and
    ``OFFER_TIMEOUT_S + 1`` still sits inside that window). Younger than the
    seat-hold and out-of-fuel reapers: those marks stay until a parseable
    timestamp ages out. ``float("inf")`` would reap them.
    """
    windows = [offer_timeout_s(None)]
    windows.extend(
        offer_timeout_s({"offered_via": via}) for via in _RELEASE_OFFER_VIA
    )
    return max(windows) + 1.0


def _offer_age_s(row: dict, now: float) -> float:
    """Seconds since ``offered_ts``.

    Missing or unparseable timestamps return :func:`_unparseable_offer_age_s`.
    """
    raw = ""
    if isinstance(row, dict):
        raw = str(row.get("offered_ts") or "").strip()
    if not raw:
        return _unparseable_offer_age_s()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return float(now) - parsed.timestamp()
    except (ValueError, OverflowError, OSError):
        return _unparseable_offer_age_s()


def seat_pending_offer(home: Path, nick: str, now: float | None = None) -> dict | None:
    """FR #3192: live unaccepted row still offered to this nick within ``OFFER_TIMEOUT_S``."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return None
    try:
        doc = load_queue(home)
    except Exception:  # noqa: BLE001
        return None
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        to = str(row.get("offered_to") or "").strip()
        if not to:
            continue
        them = (canonical_worker_nick(to) or to).strip().lower()
        if them != me:
            continue
        # FR #4564: lost-DONE re-offer to the prior holder is not a live pending ACK.
        if _is_lost_done_reoffer_to(row, nick):
            continue
        # FR #4089: same per-row window as offer_focus_top (done/giveup push = 180 s).
        if _offer_age_s(row, now_f) < offer_timeout_s(row):
            return row
    return None


def should_drop_stale_bored(
    home: Path,
    nick: str,
    now: float | None = None,
    *,
    except_job: dict | None = None,
) -> bool:
    """FR #3192: drop a !bored reply when the seat already ACKed or still holds an offer.

    Used after slow GitHub work on the IRC thread so a late offer does not land on a seat
    that accepted (or was assigned) while the offer was being computed.

    ``except_job``: when called *after* ``offer_focus_top`` stamped a new offer, pass that
    job so the just-stamped row does not count as a pre-existing pending offer.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    try:
        for row in load_accepted(home):
            if not isinstance(row, dict):
                continue
            raw = str(
                row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
            ).strip()
            them = (canonical_worker_nick(raw) or raw).strip().lower()
            if them == me:
                return True
    except Exception:  # noqa: BLE001
        return False
    pending = seat_pending_offer(home, nick, now_f)
    if not pending:
        # FR #4089: any-age pin / remembered offer for a different job also drops.
        try:
            with _lock(home):
                doc = _load_queue_unlocked(home)
                holds = _load_seat_holds_unlocked(home, now_f)
        except Exception:  # noqa: BLE001
            return False
        others = [
            r for r in (doc.get("unaccepted") or [])
            if isinstance(r, dict) and _seat_key(str(r.get("offered_to") or "")) == me
        ]
        h = holds.get(me)
        if isinstance(h, dict):
            others.append(h)
        for r in others:
            if except_job is not None and _same(
                r, str(except_job.get("repo") or ""), str(except_job.get("task") or ""),
                str(except_job.get("id") or ""),
            ):
                continue
            return True
        return False
    if except_job is not None and _same(
        pending,
        str(except_job.get("repo") or ""),
        str(except_job.get("task") or ""),
        str(except_job.get("id") or ""),
    ):
        return False
    return True


def clear_seat_offer(
    home: Path,
    nick: str,
    job: dict,
) -> bool:
    """FR #3192: unstamp a just-made offer when the stale-bored drop fires after stamp."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me or not isinstance(job, dict):
        return False
    repo = str(job.get("repo") or "")
    task = str(job.get("task") or "")
    jid = str(job.get("id") or "")
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            changed = False
            for cand in doc.get("unaccepted") or []:
                if not isinstance(cand, dict):
                    continue
                if not _same(cand, repo, task, jid):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                them = (canonical_worker_nick(to) or to).strip().lower()
                if them != me:
                    continue
                cand.pop("offered_to", None)
                cand.pop("offered_ts", None)
                cand.pop("offered_channel", None)
                cand.pop("offered_via", None)
                changed = True
            if changed:
                _write_queue(queue_path(home), doc)
            return changed
    except Exception:  # noqa: BLE001
        return False


def _seat_has_accepted(home: Path, nick: str) -> bool:
    """True when the accepted queue still lists this nick (ACK landed)."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    try:
        for row in load_accepted(home):
            if not isinstance(row, dict):
                continue
            raw = str(
                row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
            ).strip()
            them = (canonical_worker_nick(raw) or raw).strip().lower()
            if them == me:
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _digest_seat_work(home: Path, nick: str) -> str:
    """Seat-reported work. worker_list state=offered is not seat work (FR #4454).

    FR #8525: an idle worker_list / workers row does not keep a stale working_on
    claim. Otherwise LOST_ACK_RESTART UAT #0 NAKs !bored forever while TipForm
    shows idle.
    """
    parsed = bobreport.parse_seat_nick(nick)
    if not parsed:
        return ""
    mid, pid = parsed
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:  # noqa: BLE001
        return ""
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    ent = machines.get(mid) if isinstance(machines.get(mid), dict) else {}
    if not isinstance(ent, dict):
        return ""
    want = (nick or "").strip().lower()
    # Prefer worker_list: idle/offered means no seat-reported claim (FR #8525).
    for row in ent.get("worker_list") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("nick") or "").strip().lower() != want:
            continue
        state = str(row.get("state") or "").strip().lower()
        if state in ("idle", "offered", ""):
            return ""
        if state not in ("doing", "running", "busy"):
            continue
        wo = str(row.get("work") or row.get("working_on") or "").strip()
        if wo and parse_digest_work(wo):
            return wo
        return ""
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    wrow = workers.get(str(pid))
    if isinstance(wrow, dict):
        wstate = str(wrow.get("state") or "").strip().lower()
        if wstate in ("idle", "offered", ""):
            return ""
        if wstate in ("doing", "running", "busy"):
            wo = str(wrow.get("working_on") or "").strip()
            if wo and parse_digest_work(wo):
                return wo
    return ""


def _seat_reports_row(home: Path, nick: str, row: dict) -> bool:
    wo = _digest_seat_work(home, nick)
    return bool(wo and row_matches_digest_work(row, wo))


def release_unacked_lost_ack(home: Path, nick: str, *, log=None) -> bool:
    """FR #4454: !bored demotes a LOST_ACK_RESTART row the seat never reported working.

    Returns True when the row was put back on unaccepted. A real ACK (any other
    reconcile) or seat-reported ``working_on`` stays accepted (FR #3867).

    FR #7598: when the shop wire already recorded an ACK (ledger touch for this
    seat+job), never demote with ``requeue:LOST_ACK_NO_ACK``.
    """
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False

    def _owner(r: dict) -> str:
        raw = str(r.get("nick") or r.get("accepted_by") or r.get("offered_to") or "").strip()
        return (canonical_worker_nick(raw) or raw).strip().lower()

    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            acc = [r for r in (doc.get("accepted") or []) if isinstance(r, dict)]
            mine = [r for r in acc if _owner(r) == me]
            if not mine:
                return False
            if any(str(r.get("reconcile") or "") != "LOST_ACK_RESTART" for r in mine):
                return False
            if any(_seat_reports_row(home, nick, r) for r in mine):
                return False
            # FR #8384: do not keep nak-busy on LOST_ACK_RESTART just because a
            # ledger touch exists. A real ACK clears reconcile (FR #7598) and
            # paints working_on in the same turn, so _seat_reports_row stays put.
            unacc = doc.setdefault("unaccepted", [])
            done = doc.setdefault("done", [])
            demoted: list[dict] = []
            for r in mine:
                fin = dict(r)
                for k in (
                    "nick",
                    "accepted_ts",
                    "accepted_by",
                    "offered_to",
                    "offered_ts",
                    "offered_channel",
                    "offered_via",
                    "channel",
                ):
                    fin.pop(k, None)
                # FR #4661: seat already DONE PASS this MRB --- do not requeue phantom.
                if _nick_done_mrb_pass_in_doc(
                    doc,
                    nick,
                    str(fin.get("repo") or ""),
                    str(fin.get("id") or ""),
                ):
                    fin["reconcile"] = "drop:duplicate-after-done"
                    fin["result"] = str(fin.get("result") or "PASS")
                    fin["done_ts"] = _utc_now()
                    done.append(fin)
                    demoted.append(fin)
                    continue
                fin["reconcile"] = "requeue:LOST_ACK_NO_ACK"
                unacc.append(fin)
                demoted.append(fin)
            doc["accepted"] = [r for r in acc if _owner(r) != me]
            # FR #8525: drop seat-holds for demoted rows so !bored is not why=held.
            try:
                holds = _load_seat_holds_unlocked(home, time.time())
                changed_h = False
                for fin in demoted:
                    for hk, hv in list(holds.items()):
                        if not isinstance(hv, dict):
                            continue
                        if _same(
                            hv,
                            str(fin.get("repo") or ""),
                            str(fin.get("task") or ""),
                            str(fin.get("id") or ""),
                        ):
                            holds.pop(hk, None)
                            changed_h = True
                if changed_h:
                    _save_seat_holds_unlocked(home, holds)
            except Exception:  # noqa: BLE001
                pass
            _write_queue(queue_path(home), doc)
    except Exception:  # noqa: BLE001
        return False
    _log_queue_purge(
        f"INFO seat-reconcile nick={nick} result=requeue:LOST_ACK_NO_ACK reason=LOST_ACK_NO_ACK",
        log=log,
    )
    return True


def _iter_digest_work_claims(home: Path) -> list[tuple[str, str]]:
    """Collect (nick, working_on) claims from digest workers map + doing list (FR #3867)."""
    import bobreport as _br

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        dig = _br.load_digest(_root(home))
    except Exception:  # noqa: BLE001
        return out
    machines = dig.get("machines") if isinstance(dig.get("machines"), dict) else {}
    for mid, ent in list(machines.items()):
        if not isinstance(ent, dict):
            continue
        workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
        for pid_s, w in list(workers.items()):
            if not isinstance(w, dict):
                continue
            # FR #8525: idle/offered workers map rows are not lost-ACK claims.
            wstate = str(w.get("state") or "").strip().lower()
            if wstate and wstate not in ("doing", "running", "busy"):
                continue
            wo = str(w.get("working_on") or "").strip()
            if not wo or not parse_digest_work(wo):
                continue
            nick = str(w.get("nick") or "").strip() or f"{mid}-{pid_s}"
            key = (canonical_worker_nick(nick) or nick).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((nick, wo))
        for row in list(ent.get("worker_list") or []):
            if not isinstance(row, dict):
                continue
            # FR #4454: do not treat Jeeves's own worker_list state=offered as a claim.
            if str(row.get("state") or "").strip().lower() not in ("doing", "running", "busy"):
                continue
            wo = str(row.get("work") or row.get("working_on") or "").strip()
            if not wo or not parse_digest_work(wo):
                continue
            nick = str(row.get("nick") or "").strip()
            if not nick:
                continue
            key = (canonical_worker_nick(nick) or nick).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((nick, wo))
    return out


def _digest_seat_live_heartbeat(home: Path, nick: str, *, window_s: float = 1800.0) -> bool:
    """FR #8235: True when the digest seat has a pid and a fresh last_progress.

    That is a live job process with a current heartbeat. Reconcile must not
    stamp LOST_ACK_RESTART on that seat.
    """
    want = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not want:
        return False
    try:
        import bobreport as _br

        dig = _br.load_digest(_root(home))
    except Exception:  # noqa: BLE001
        return False
    now = time.time()
    machines = dig.get("machines") if isinstance(dig.get("machines"), dict) else {}
    for ent in machines.values():
        if not isinstance(ent, dict):
            continue
        rows = list(ent.get("worker_list") or [])
        workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
        for w in workers.values():
            if isinstance(w, dict):
                rows.append(w)
        for row in rows:
            if not isinstance(row, dict):
                continue
            n = (canonical_worker_nick(str(row.get("nick") or "")) or str(row.get("nick") or "")).strip().lower()
            if n != want:
                continue
            pid = str(row.get("pid") or "").strip()
            if not pid:
                continue
            ts = _parse_iso_ts(str(row.get("last_progress") or ""))
            if ts is None:
                continue
            if (now - float(ts)) <= float(window_s):
                return True
    return False


def _reconcile_lost_ack_unlocked(home: Path, doc: dict, *, log=None) -> int:
    """Promote unaccepted rows claimed by digest working_on into accepted (FR #3867).

    Mutates ``doc`` under the caller's lock. Returns how many rows were promoted.
    """
    claims = _iter_digest_work_claims(home)
    if not claims:
        return 0
    unacc = [r for r in (doc.get("unaccepted") or []) if isinstance(r, dict)]
    if not unacc:
        return 0
    accepted = [r for r in (doc.get("accepted") or []) if isinstance(r, dict)]

    def _already_accepted(row: dict) -> bool:
        for a in accepted:
            if _same(a, str(row.get("repo") or ""), str(row.get("task") or ""), str(row.get("id") or "")):
                return True
        return False

    promoted = 0
    dropped_dup = 0
    keep: list[dict] = []
    for row in unacc:
        matched_nick = ""
        for nick, wo in claims:
            if row_matches_digest_work(row, wo):
                matched_nick = nick
                break
        if not matched_nick:
            keep.append(row)
            continue
        # FR #4336: never revive a needs_human row via LOST_ACK_RESTART.
        # FR #4422: release_stale_busy requeued without closed/merged evidence ---
        # do not bounce the same row straight back to accepted from stale digest work.
        if row_needs_human(row, "") or str(row.get("reconcile") or "").startswith("requeue:"):
            keep.append(row)
            continue
        # Already accepted for this repo/task/id: drop the unaccepted twin so
        # offer_focus_top cannot double-offer (MRB #3871 hostile).
        if _already_accepted(row):
            dropped_dup += 1
            continue
        job = dict(row)
        job["nick"] = (canonical_worker_nick(matched_nick) or matched_nick).strip()
        job["accepted_ts"] = _utc_now()
        # FR #8235: a live process with a current heartbeat is a real accept.
        # Do not stamp LOST_ACK_RESTART (that phantom is what !bored demotes).
        if _digest_seat_live_heartbeat(home, matched_nick):
            job.pop("reconcile", None)
            _log_queue_purge(
                f"INFO seat-reconcile nick={job['nick']} row={job.get('task')} "
                f"{job.get('repo')}{job.get('id')} result=accepted-live-heartbeat "
                f"reason=live-process-heartbeat",
                log=log,
            )
        else:
            job["reconcile"] = "LOST_ACK_RESTART"
            _log_queue_purge(
                f"INFO seat-reconcile nick={job['nick']} row={job.get('task')} "
                f"{job.get('repo')}{job.get('id')} result=LOST_ACK_RESTART reason=LOST_ACK_RESTART",
                log=log,
            )
        # Drop stale offer stamps; ownership is now accepted.
        job.pop("offered_to", None)
        job.pop("offered_ts", None)
        job.pop("offered_channel", None)
        job.pop("offered_via", None)
        accepted.append(job)
        promoted += 1
    if not promoted and not dropped_dup:
        return 0
    if len(accepted) > ACCEPTED_CAP:
        accepted = accepted[-ACCEPTED_CAP:]
    doc["unaccepted"] = keep
    doc["accepted"] = accepted
    # Caller writes when return > 0; count drops so twin-purge alone still persists.
    return promoted + dropped_dup


def reconcile_lost_ack_from_digest(home: Path, *, log=None) -> int:
    """FR #3867: on chair start / before offer, accept unaccepted rows a digest seat is working.

    When an offer lands and the chair restarts before ACK is recorded, the seat may still
    paint ``workers.<pid>.working_on`` while the row stays in ``unaccepted``. Promote those
    rows to ``accepted`` so they are never re-offered to another seat.
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return 0
            n = _reconcile_lost_ack_unlocked(home, doc, log=log)
            if n:
                try:
                    _write_queue(queue_path(home), doc)
                except OSError:
                    return 0
            return n
    except (TimeoutError, OSError):
        return 0


def holder_bored_limit() -> int:
    """FR #7912: consecutive !bored from the holder before the job is released."""
    raw = str(os.environ.get("BOB_HOLDER_BORED_N", "2") or "2").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 2
    return n if n >= 1 else 2


def _holder_bored_path(home: Path) -> Path:
    return Path(home) / "holder-bored.json"


def _load_holder_bored(home: Path) -> dict:
    path = _holder_bored_path(home)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {"seats": {}}
    if not isinstance(doc, dict):
        return {"seats": {}}
    seats = doc.get("seats")
    if not isinstance(seats, dict):
        doc["seats"] = {}
    return doc


def _save_holder_bored(home: Path, doc: dict) -> None:
    path = _holder_bored_path(home)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def reset_holder_bored(home: Path, nick: str) -> None:
    """FR #7912: ACK, DONE, or other progress clears the holder's !bored streak."""
    key = (_seat_key(nick) or "").strip().lower()
    if not key:
        return
    try:
        with _lock(home):
            doc = _load_holder_bored(home)
            seats = doc.setdefault("seats", {})
            if key not in seats:
                return
            seats.pop(key, None)
            _save_holder_bored(home, doc)
    except (TimeoutError, OSError):
        return


def _report_holder_bored(nick: str, job: str) -> None:
    import runtime_failure

    runtime_failure.report_message(
        "jeeves",
        "holder_bored nick=%s job=%s" % (nick, job),
        site="holder-bored",
    )


_HOLDER_OPEN_RX = re.compile(
    r"^(accepted|held)\s+(\S+)\s+(.+)(#\d+)\s*$",
    re.IGNORECASE,
)


def release_sticky_offer_on_bored(
    home: Path, nick: str, now: float | None = None
) -> str:
    """FR #9633 / FR #9771: !bored clears *stale* sticky offer pins and via=offer holds.

    Within ``offer_timeout_s`` the seat stays busy (FR #3192 / #8738 - fresh
    post-DONE / post-GIVEUP pushes must not be wiped by the next !bored). Past
    the timeout, clear ``offered_to`` + matching seat-hold so digest-idle seats
    are not NAK ``busy (offered …)`` forever (issue #9633).

    FR #9771: when the pin is already gone but a ``via=offer`` seat-hold remains
    (hold reaper is ``SEAT_HOLD_MAX_S`` = 1h while offer timeout is ~90s), clear
    that stale hold on !bored so seats are not NAK ``busy (held …)`` after #9633.

    Bare ack-missing ``held …`` seat-holds (FR #4115 / #4415) are never cleared
    here. Does not call ``seat_open_job`` (that would purge first).

    Returns the open-job text that was cleared, else ''.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return ""
    if _seat_has_accepted(home, nick):
        return ""
    # Live pending ACK window: leave the pin alone (FR #8738).
    if seat_pending_offer(home, nick, now_f) is not None:
        return ""
    changed = False
    cleared_job = ""
    repo = task = ident = ""
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            for cand in doc.get("unaccepted") or []:
                if not isinstance(cand, dict):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                if not to:
                    continue
                them = (canonical_worker_nick(to) or to).strip().lower()
                if them != me:
                    continue
                if _offer_age_s(cand, now_f) < offer_timeout_s(cand):
                    continue
                task_u = str(cand.get("task") or "").upper()
                repo_s = str(cand.get("repo") or "")
                ident_s = str(cand.get("id") or "")
                cleared_job = f"offered {task_u} {repo_s}{ident_s}".strip()
                repo, task, ident = repo_s, task_u, ident_s
                clear_sticky_offer_fields(cand)
                changed = True
            if changed:
                with contextlib.suppress(OSError):
                    _write_queue(queue_path(home), doc)
            # FR #9771: stale via=offer hold with no live pin on this nick.
            if not changed:
                key = _seat_key(nick)
                holds = _load_seat_holds_unlocked(home, now_f)
                h = holds.get(key) if key else None
                if isinstance(h, dict):
                    via = str(h.get("via") or "offer").strip().lower() or "offer"
                    if via != "ack-missing":
                        age = _offer_age_s({"offered_ts": h.get("ts")}, now_f)
                        if age >= offer_timeout_s(None):
                            repo_s = str(h.get("repo") or "")
                            task_u = str(h.get("task") or "").upper()
                            ident_s = str(h.get("id") or "")
                            cleared_job = f"held {task_u} {repo_s}{ident_s}".strip()
                            repo, task, ident = repo_s, task_u, ident_s
                            holds.pop(key, None)
                            with contextlib.suppress(OSError):
                                _save_seat_holds_unlocked(home, holds)
                            changed = True
    except (TimeoutError, OSError):
        return ""
    if not changed:
        return ""
    with contextlib.suppress(Exception):
        if repo and task and ident:
            clear_seat_hold(
                home, nick, repo=repo, task=task, ident=ident, clear_pins=True
            )
    with contextlib.suppress(Exception):
        import bobreport

        bobreport.clear_seat_doing(home, nick)
    return cleared_job



def release_holder_on_bored(home: Path, nick: str, now: float | None = None) -> str:
    """FR #7912: N consecutive !bored from the holding seat releases that seat's job.

    Returns the open-job text when this call released it, else ''. A different
    seat's !bored never touches this nick's row. Offered-but-not-accepted pins
    are cleared by ``release_sticky_offer_on_bored`` (FR #9633) before the busy
    gate. ACK/DONE/progress must call ``reset_holder_bored`` or the streak keeps
    counting.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    open_job = seat_open_job(home, nick, now_f)
    match = _HOLDER_OPEN_RX.match(str(open_job or "").strip())
    if not match:
        reset_holder_bored(home, nick)
        return ""
    key = (_seat_key(nick) or "").strip().lower()
    if not key:
        return ""
    limit = holder_bored_limit()
    count = 1
    try:
        with _lock(home):
            doc = _load_holder_bored(home)
            seats = doc.setdefault("seats", {})
            prev = seats.get(key) if isinstance(seats.get(key), dict) else {}
            if str(prev.get("job") or "") == open_job:
                try:
                    count = int(prev.get("count") or 0) + 1
                except (TypeError, ValueError):
                    count = 1
            seats[key] = {"job": open_job, "count": count}
            _save_holder_bored(home, doc)
    except (TimeoutError, OSError):
        return ""
    if count < limit:
        return ""
    _kind, task, repo, ident = match.groups()
    task_u = task.upper()
    try:
        import shop_listen

        shop_listen.return_job_to_unaccepted(
            home,
            repo=repo,
            task=task_u,
            ident=ident,
            now=now_f,
            reason="holder_bored",
            expected_nick=nick,
        )
    except Exception:
        pass
    with contextlib.suppress(Exception):
        clear_seat_hold(home, nick, repo=repo, task=task_u, ident=ident, clear_pins=True)
    with contextlib.suppress(Exception):
        ledger_note_event(home, nick, "GIVEUP", task_u, repo, ident, None)
    with contextlib.suppress(Exception):
        import bobreport

        # FR #8384: placeholder working_on does not contain the issue id, so a
        # needle clear leaves the seat looking busy after the row is released.
        bobreport.clear_seat_doing(home, nick)
    with contextlib.suppress(Exception):
        _report_holder_bored(nick, open_job)
    reset_holder_bored(home, nick)
    return open_job


def bored_gate(
    home: Path,
    nick: str,
    channel: str,
    now: float,
    *,
    session_started: float | None = None,
) -> str:
    """ignore, wait, busy, or ok. wait is checked before busy so retries stay quiet.

    FR #3742: pass ``session_started`` (chair IRC session / process start) so an
    accepted row ACKed before this session is healed on ``!bored`` without waiting
    ``BUSY_STALE_S`` (lost DONE while the chair was down).
    """
    # FR #3867: heal lost-ACK rows from digest before busy/ok decisions.
    with contextlib.suppress(Exception):
        reconcile_lost_ack_from_digest(home)
    shop = worker_shop_channel(nick)
    if shop is None or _channel(channel) != shop:
        return "ignore"
    last = last_worker_activity(home, nick)
    if last is not None and (float(now) - last) < IDLE_S:
        return "wait"
    # FR #4181: out-of-fuel mark blocks !bored offers until clear_seat_out_of_fuel.
    if seat_is_out_of_fuel(home, nick, now):
        return "busy"
    if seat_fuel_pause_reason(home, nick, now):
        return "busy"
    # FR #9633: sticky offered-but-not-ACKed must not NAK !bored forever when the
    # seat is claiming idle - clear the pin so offer_focus_top can re-send.
    with contextlib.suppress(Exception):
        release_sticky_offer_on_bored(home, nick, now)
    # FR #3192: outstanding offered_to (pending ACK / undelivered assign) is busy -
    # never re-offer the same row and never treat it as stale digest doing.
    # (After FR #9633 clear above, a fresh pending offer means another path stamped
    # one mid-gate; still busy.)
    if seat_pending_offer(home, nick, now):
        return "busy"
    # FR #4642: ack-missing hold for a job this seat already DONE'd (no later
    # re-offer) must not nak !bored forever when the follow-up DONE was lost.
    with contextlib.suppress(Exception):
        release_duplicate_done_hold(home, nick)
    # FR #4454 / #8525: demote false LOST_ACK_RESTART before the held-open check.
    # A seat-holds pin for the same UAT #0 used to NAK busy (why=held) forever and
    # skipped release_unacked_lost_ack.
    with contextlib.suppress(Exception):
        if release_unacked_lost_ack(home, nick):
            return "ok"
    # FR #4089: an offer pinned to this seat (any age) or remembered in seat-holds.json
    # keeps it busy; accepted rows still go through release_stale_busy below.
    _open = seat_open_job(home, nick, now)
    if _open and not _open.startswith("accepted "):
        return "busy"
    # FR #3192: accepted row is busy even before digest on_ack paints working_on
    # (stale !bored after slow GH work must NAK-busy, not stamp a second offer).
    if _seat_has_accepted(home, nick):
        if release_stale_busy(home, nick, now, session_started=session_started):
            return "ok"
        return "busy"
    if worker_working_on(home, nick):
        if release_stale_busy(home, nick, now, session_started=session_started):
            return "ok"
        return "busy"
    return "ok"


# A seat only sends !bored when it is idle. If the digest still says "doing" but the seat has
# no accepted queue row, or its accepted row is older than BUSY_STALE_S, the DONE was lost:
# nak-busying it forever stalls the whole fleet (2026-10-05: marchhare seats nak-busy 8h on
# merged MRB #2349 / closed FR #2340 while every open MRB was ionos-authored).
BUSY_STALE_S = 3600.0
# Digest already says idle, but the accepted row is still young. !bored and
# offer_to_idle must not wait out BUSY_STALE_S. 90s covers ACK-to-digest lag.
IDLE_DIGEST_RELEASE_S = 90.0


def _digest_seat_explicit_idle(home: Path, nick: str) -> bool:
    """True only when this nick's digest row says state=idle.

    Missing digest, empty state, or doing/offered is not idle. An explicit idle
    row plus !bored means the accepted job is no longer on the seat.
    """
    parsed = bobreport.parse_seat_nick(nick)
    if not parsed:
        return False
    mid, pid = parsed
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:  # noqa: BLE001
        return False
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    ent = machines.get(mid) if isinstance(machines.get(mid), dict) else {}
    if not isinstance(ent, dict):
        return False
    want = (nick or "").strip().lower()
    for row in ent.get("worker_list") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("nick") or "").strip().lower() != want:
            continue
        return str(row.get("state") or "").strip().lower() == "idle"
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    wrow = workers.get(str(pid))
    if isinstance(wrow, dict):
        return str(wrow.get("state") or "").strip().lower() == "idle"
    return False


def _accepted_row_age_s(row: dict, now: float) -> float:
    """Age of an accepted row from accepted_ts/offered_ts/ts; missing/bad => older than BUSY_STALE_S."""
    ts = str(row.get("accepted_ts") or row.get("offered_ts") or row.get("ts") or "")
    try:
        return float(now) - datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return BUSY_STALE_S + 1.0


def _accepted_ts_epoch(row: dict) -> float | None:
    ts = str(row.get("accepted_ts") or row.get("offered_ts") or row.get("ts") or "")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _digest_work_pull_url(home: Path, nick: str) -> str:
    """Local-only completion hint: digest working_on / worker work containing a pull URL."""
    try:
        work = str(worker_working_on(home, nick) or "")
    except Exception:  # noqa: BLE001
        work = ""
    if not work:
        return ""
    m = re.search(r"https://github\.com/\S+/pull/\d+", work)
    return m.group(0) if m else ""


def release_stale_busy(
    home: Path,
    nick: str,
    now: float,
    *,
    session_started: float | None = None,
    log=None,
) -> bool:
    """Heal a lost-DONE seat on !bored: drop its stale accepted row(s), set it idle. True if healed.

    Stale when:
    * row age >= ``BUSY_STALE_S`` (FR #2369), or
    * digest ``worker_list`` state is exactly ``idle`` and age >= ``IDLE_DIGEST_RELEASE_S``
      (FR #10337 — do not wait out the hour while the seat is already idle), or
    * ``session_started`` is set and the row's accepted_ts is strictly before that
      session (FR #3742 - lost DONE across chair restart / IRC reconnect).

    A seat that ``!bored`` is claiming idle; do not heal a fresh ACK from *this*
    session (accepted_ts >= session_started and age < IDLE_DIGEST_RELEASE_S)
    when the digest does not already say idle. A digest state of doing/offered
    keeps a young row. IDLE_DIGEST requeue does not set prior_holder.
    """
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    # FR #3192: assigned/offered-but-not-ACKed is not stale busy - keep digest doing.
    if seat_pending_offer(home, nick, now):
        return False

    def _owner(r: dict) -> str:
        # Match ACC purge seats (#2361): nick / accepted_by / offered_to.
        raw = str(
            r.get("nick") or r.get("accepted_by") or r.get("offered_to") or ""
        ).strip()
        return (canonical_worker_nick(raw) or raw).strip().lower()

    healed_rows: list[tuple[dict, str]] = []
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            # Re-check pending offer under the lock (race with assign / offer_focus_top).
            for cand in doc.get("unaccepted") or []:
                if not isinstance(cand, dict):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                if not to:
                    continue
                them = (canonical_worker_nick(to) or to).strip().lower()
                if them == me and _offer_age_s(cand, float(now)) < offer_timeout_s(cand):
                    return False
            acc = [r for r in (doc.get("accepted") or []) if isinstance(r, dict)]
            mine = [r for r in acc if _owner(r) == me]
            for r in mine:
                age = _accepted_row_age_s(r, float(now))
                epoch = _accepted_ts_epoch(r)
                pre_session = session_started is not None and (
                    epoch is None or epoch < float(session_started)
                )
                if age >= BUSY_STALE_S:
                    continue  # stale by age
                if pre_session:
                    continue  # stale by FR #3742 session boundary
                if (
                    _digest_seat_explicit_idle(home, nick)
                    and age >= IDLE_DIGEST_RELEASE_S
                ):
                    continue  # digest idle while the chair still holds ACC
                return False  # genuinely recent job in this session: honour busy
            if mine:
                # FR #4422: never mark done without a merged PR or a closed issue.
                # Inventing STALE_BUSY / LOST_DONE_RESTART into done[] while resync is
                # lagging stranded open FRs off the offer queue. Requeue unless the
                # digest already carries a /pull/ URL (lost DONE FR with implement PR).
                pull_hint = _digest_work_pull_url(home, nick)
                done = doc.setdefault("done", [])
                unacc = doc.setdefault("unaccepted", [])
                for r in mine:
                    fin = dict(r)
                    age = _accepted_row_age_s(r, float(now))
                    epoch = _accepted_ts_epoch(r)
                    pre_session = session_started is not None and (
                        epoch is None or epoch < float(session_started)
                    )
                    if age >= BUSY_STALE_S:
                        reason = "STALE_BUSY"
                    elif pre_session:
                        reason = "LOST_DONE_RESTART"
                    elif (
                        _digest_seat_explicit_idle(home, nick)
                        and age >= IDLE_DIGEST_RELEASE_S
                    ):
                        reason = "IDLE_DIGEST"
                    else:
                        reason = "LOST_DONE_RESTART"
                    github_done = ""
                    if reason == "LOST_DONE_RESTART":
                        github_done = str(_lost_done_github_result(fin) or "")
                    if pull_hint or github_done:
                        # Evidence of DONE: digest pull URL, or a PASS board already on GitHub.
                        fin["result"] = pull_hint or github_done
                        fin["done_ts"] = _utc_now()
                        fin["reconcile"] = reason
                        done.append(fin)
                        healed_rows.append((fin, reason))
                        continue
                    # FR #4911: main-red FIX with no /pull/ must not requeue forever when
                    # main is already green (or the signature SHA is no longer HEAD).
                    if _is_main_red_fix_row_local(fin):
                        retire = False
                        try:
                            import mrb_merge_on_green as _mog

                            repo_c = canonical_queue_repo(
                                str(fin.get("repo") or "")
                            ) or str(fin.get("repo") or "").strip()
                            mr = bool(_mog.main_branch_checks_red(repo_c))
                            head = str(_mog.main_branch_head_sha(repo_c) or "")
                            retire = bool(
                                _mog.main_red_fix_obsolete(
                                    fin, main_red=mr, main_sha=head
                                )
                            )
                        except Exception:
                            retire = False
                        if retire:
                            stamped = _finish_dead_fix_row(fin, home=None)
                            stamped["reconcile"] = f"{reason}:FR4911_MAIN_GREEN"
                            done.append(stamped)
                            healed_rows.append((stamped, stamped["reconcile"]))
                            continue
                    # No closed/merged evidence: return to unaccepted so !assign / !bored
                    # can offer again even when github-resync is skipped.
                    # FR #4564: remember who held it so the requeue is not offered back.
                    holder = me
                    for k in (
                        "nick",
                        "accepted_ts",
                        "accepted_by",
                        "offered_to",
                        "offered_ts",
                        "offered_channel",
                        "channel",
                    ):
                        fin.pop(k, None)
                    fin["reconcile"] = f"requeue:{reason}"
                    if reason == "LOST_DONE_RESTART":
                        fin["prior_holder"] = holder
                    unacc.append(fin)
                    healed_rows.append((fin, f"requeue:{reason}"))
                if len(done) > DONE_CAP:
                    doc["done"] = done[-DONE_CAP:]
                doc["accepted"] = [r for r in acc if _owner(r) != me]
                _write_queue(queue_path(home), doc)
    except Exception:  # noqa: BLE001
        return False
    for fin, reason in healed_rows:
        row_id = str(fin.get("id") or "")
        repo = str(fin.get("repo") or "")
        task = str(fin.get("task") or "")
        result = str(fin.get("result") or reason)
        _log_queue_purge(
            f"INFO seat-reconcile nick={nick} row={task} {repo}{row_id} "
            f"result={result} reason={reason}",
            log=log,
        )
    # Digested "doing" with no accepted row (or after drop): clear so !bored can offer.
    try:
        out = bobreport.clear_seat_doing(_root(home), nick)
    except Exception:  # noqa: BLE001
        return False
    return bool(getattr(out, "ok", False))
