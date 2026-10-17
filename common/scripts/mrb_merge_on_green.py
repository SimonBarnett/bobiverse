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

Decision = str  # merge | wait | requeue_sha | requeue_ci | skip_hold | drop_merged | drop_closed

# FR #4543: leave headroom for pr_exists / !resync / offers when the sweep is large.
DEFAULT_MIN_RATE_REMAINING = 100


def _utc() -> str:
    return gitclaim._utc_now()


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
    if state in ("failure", "error", "action_required", "timed_out", "cancelled", "canceled"):
        return "requeue_ci"
    if state in ("pending", "expected", "queued", "in_progress", "waiting", "requested"):
        return "wait"
    if state in ("success", "neutral", "skipped", "none", ""):
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
    return {"version": 1, "pending": []}


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
    return doc


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
        try:
            status = _gh_json(
                f"https://api.github.com/repos/{repo_c}/commits/{sha}/status",
                token=tok,
            )
            checks = str(status.get("state") or "none").lower()
        except RuntimeError:
            checks = "pending"
        # Prefer check-runs rollup when classic status is empty/none.
        if checks in ("none", ""):
            try:
                runs = _gh_json(
                    f"https://api.github.com/repos/{repo_c}/commits/{sha}/check-runs",
                    token=tok,
                )
                items = runs.get("check_runs") if isinstance(runs, dict) else None
                if isinstance(items, list) and items:
                    conclusions = [
                        str(i.get("conclusion") or "").lower()
                        for i in items
                        if isinstance(i, dict)
                    ]
                    statuses = [
                        str(i.get("status") or "").lower()
                        for i in items
                        if isinstance(i, dict)
                    ]
                    if any(s not in ("completed",) for s in statuses):
                        checks = "pending"
                    elif any(c in ("failure", "timed_out", "cancelled", "action_required") for c in conclusions):
                        checks = "failure"
                    else:
                        checks = "success"
            except RuntimeError:
                pass
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
    """Clear premature mrb_done and put the PR back on the unaccepted MRB queue."""
    repo_c = gitclaim.canonical_queue_repo(repo)
    ident = f"#{str(pr).lstrip('#')}"
    gitclaim.clear_mrb_done(home, repo_c, ident)
    claim = gitclaim.GitClaim(
        repo=repo_c,
        task="MRB",
        id=ident,
        event="pull_request",
        action="synchronize",
        line=url or f"https://github.com/{repo_c}/pull/{str(pr).lstrip('#')}",
        title=f"requeue after merge-on-green ({reason or 'retry'})",
        body="",
        labels=(),
    )
    with gitclaim._lock(home):
        try:
            doc = gitclaim._load_queue_unlocked(home)
        except (OSError, ValueError):
            doc = gitclaim._empty_queue()
        gitclaim._append_unaccepted(
            doc,
            claim,
            url=url or claim.line,
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
    decision = decide_merge_on_green(
        pass_sha=str(row.get("pass_sha") or ""),
        current_sha=str(pr_state.get("sha") or ""),
        checks=str(pr_state.get("checks") or "none"),
        hold_reason=None,
        merged=bool(pr_state.get("merged")),
        closed=bool(pr_state.get("closed")),
    )
    if decision == "merge" and not ok_gate:
        # Still waiting for PASS board scrape, or other gate refuse that is not hold.
        if "pass" in (gate_reason or "").lower() or "board" in (gate_reason or "").lower():
            return "wait", gate_reason
        return "wait", gate_reason or "merge gate refused"
    return decision, ""


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
        "skipped_hold": 0,
        "dropped": 0,
        "errors": 0,
        "backed_off": False,
        "actions": [],
    }

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

        if decision == "merge":
            try:
                merge_fn(repo, pr, str(row.get("pass_sha") or ""))
                summary["merged"] += 1
                _log(f"INFO merge-on-green merged {repo}#{pr} @{row.get('pass_sha')}")
                continue  # drop from pending
            except Exception as exc:  # noqa: BLE001
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
            _log(f"INFO merge-on-green skip hold {repo}#{pr}: {row['hold_reason']}")
            continue

        if decision in ("requeue_sha", "requeue_ci"):
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

        # wait
        summary["wait"] += 1
        row["status"] = "pending"
        keep.append(row)

    doc["pending"] = keep
    save_ledger(home, doc)
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
    return enqueue(
        home,
        repo=pr_repo,
        pr=pr_num,
        pass_sha=sha,
        url=pr_url or str(st.get("html_url") or ""),
        nick=nick,
        hold_reason=hold,
    )
