"""FR #5510: deterministic Jeeves stuck-job sweep (no agent, no tokens required for act).

Every 10 minutes (and once on startup) classify open work against the queue:

* ``unaccepted`` — offerable queue row
* ``accepted`` — ACKed row with holder + age
* ``held`` — open on GitHub (or queue) with an exact hold/skip rule
* ``untracked`` — open and offerable but absent from the queue

Stuck actions (never touch needs_human / require_machine / self-MRB author holds;
never merge or close):

* silent or dead-holder ``accepted`` → release (prior ACK void) and re-offer
* ``untracked`` offerable → enqueue
* held past its window → report only

Report: ``stuck-report.json`` + digest ``stuck`` section + ``!stuck`` + one
#bobiverse line when the stuck set fingerprint changes.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Acceptance: silent accepted released/re-offered within 40 min → act at 30 min.
SILENT_ACCEPTED_S = 1800.0
STUCK_SWEEP_S = 600.0
FIRST_STUCK_SWEEP_DELAY_S = 20.0
UNACCEPTED_STARVE_S = 1800.0

REPORT_NAME = "stuck-report.json"
CATALOG_NAME = "open-catalog.json"
ANNOUNCE_FP_NAME = "stuck-announce.fp"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(raw: Any) -> float | None:
    if isinstance(raw, (int, float)):
        v = float(raw)
        if v > 1_000_000_000_000:
            return v / 1000.0
        if v > 1_000_000_000:
            return v
        return None
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _norm_id(ident: Any) -> str:
    s = str(ident or "").strip()
    if not s:
        return ""
    return s if s.startswith("#") else f"#{s.lstrip('#')}"


def _job_key(repo: str, task: str, ident: str) -> str:
    return f"{str(repo).strip().lower()}|{str(task).strip().upper()}|{_norm_id(ident).lower()}"


def report_path(home: Path) -> Path:
    return Path(home) / REPORT_NAME


def catalog_path(home: Path) -> Path:
    return Path(home) / CATALOG_NAME


def announce_fp_path(home: Path) -> Path:
    return Path(home) / ANNOUNCE_FP_NAME


def load_open_catalog(home: Path) -> list[dict]:
    p = catalog_path(home)
    if not p.is_file():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    rows = doc.get("items") if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def write_open_catalog(home: Path, items: list[dict], *, now: float | None = None) -> Path:
    """Persist open-item catalog for the stuck sweep (written by resync / tests)."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    payload = {
        "v": 1,
        "ts": _utc_now() if now is None else datetime.fromtimestamp(
            float(now), tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": list(items or []),
    }
    path = catalog_path(home)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_stuck_report(home: Path) -> dict:
    p = report_path(home)
    if not p.is_file():
        return {"v": 1, "ts": "", "stuck": [], "classified": []}
    try:
        doc = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"v": 1, "ts": "", "stuck": [], "classified": []}
    if not isinstance(doc, dict):
        return {"v": 1, "ts": "", "stuck": [], "classified": []}
    doc.setdefault("stuck", [])
    doc.setdefault("classified", [])
    return doc


def write_stuck_report(home: Path, report: dict) -> Path:
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = report_path(home)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _holder_nick(row: dict) -> str:
    import gitclaim

    raw = str(
        row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
    ).strip()
    return (gitclaim.canonical_worker_nick(raw) or raw).strip().lower()


def _row_age_s(row: dict, now: float) -> float:
    """Age in seconds. Missing timestamps => 0 (do not treat as already-stale).

    Chair health seeds and mid-restart accepts often omit accepted_ts; voiding
    those on the first stuck tick would wipe in-flight work. Explicit ages still
    release after SILENT_ACCEPTED_S.
    """
    epoch = _parse_ts(row.get("accepted_ts") or row.get("offered_ts") or row.get("ts"))
    if epoch is None:
        return 0.0
    return max(0.0, float(now) - float(epoch))


def _protected_hold_row(row: dict) -> str | None:
    """FR #5510: never auto-release these; report only."""
    import gitclaim

    if gitclaim.row_needs_human(row, ""):
        return "needs_human"
    mid = str(gitclaim.row_require_machine(row) or "").strip()
    if mid:
        return f"require_machine:{mid}"
    # Self-MRB: accepted by an author seat — leave for human / explicit assign.
    holder = _holder_nick(row)
    if holder and gitclaim.nick_is_row_author(row, holder):
        return "self_mrb"
    return None


def classify_queue_row(
    row: dict,
    *,
    bucket: str,
    now: float,
    live: set[str],
    idle: set[str],
    activity: dict[str, float] | None = None,
) -> dict:
    """Classify one queue row into unaccepted|accepted|held (+ stuck flags)."""
    import gitclaim

    repo = str(row.get("repo") or "")
    task = str(row.get("task") or "").upper()
    ident = _norm_id(row.get("id"))
    base = {
        "repo": repo,
        "number": ident,
        "task": task,
        "title": str(row.get("title") or row.get("line") or "")[:120],
        "age_s": int(_row_age_s(row, now)),
        "holder": "",
        "rule": "",
        "state": bucket,
        "stuck": False,
        "stuck_reason": "",
    }
    if bucket == "accepted":
        holder = _holder_nick(row)
        base["holder"] = holder
        prot = _protected_hold_row(row)
        if prot:
            base["state"] = "held"
            base["rule"] = prot
            return base
        age = _row_age_s(row, now)
        live_l = {str(x).strip().lower() for x in (live or set()) if str(x).strip()}
        holder_live = bool(holder) and holder in live_l
        last = None
        if activity and holder:
            last = activity.get(holder)
        silent = False
        if last is not None:
            silent = (float(now) - float(last)) >= SILENT_ACCEPTED_S
        elif age >= SILENT_ACCEPTED_S:
            silent = True
        # Require SILENT_ACCEPTED_S age even for holder-gone so a chair restart
        # before seats reappear in live does not void a fresh ACK (health tests /
        # IRC flap). Still meets "within 40 min" acceptance.
        if age >= SILENT_ACCEPTED_S and not holder_live:
            base["stuck"] = True
            base["stuck_reason"] = "accepted_holder_gone"
        elif age >= SILENT_ACCEPTED_S and silent:
            base["stuck"] = True
            base["stuck_reason"] = "accepted_silent"
        return base

    # unaccepted
    if gitclaim.row_needs_human(row, ""):
        base["state"] = "held"
        base["rule"] = "needs_human"
        return base
    mid = str(gitclaim.row_require_machine(row) or "").strip()
    if mid:
        base["state"] = "held"
        base["rule"] = f"require_machine:{mid}"
        return base
    skip = gitclaim.row_skip_fr_reason(row) if task == "FR" else None
    if skip:
        base["state"] = "held"
        base["rule"] = f"skip:{skip}"
        return base
    hold = gitclaim.row_fr_hold_reason(row) if task == "FR" else None
    if hold:
        base["state"] = "held"
        base["rule"] = f"hold:{hold}"
        return base
    if gitclaim.row_on_cooldown(row, now, nick="", live=live):
        base["state"] = "held"
        base["rule"] = "cooldown_until"
        return base
    # Offerable but starved while a seat is idle/bored.
    age = _row_age_s(row, now)
    offered_to = str(row.get("offered_to") or "").strip()
    if (
        not offered_to
        and age >= UNACCEPTED_STARVE_S
        and idle
    ):
        base["stuck"] = True
        base["stuck_reason"] = "unaccepted_starved"
    return base


def classify_open_item(item: dict) -> dict:
    """Classify a catalog/GitHub open item (not yet matched to a queue row)."""
    import gitclaim

    repo = str(item.get("repo") or "")
    kind = str(item.get("kind") or item.get("task") or "").strip().lower()
    ident = _norm_id(item.get("id") or item.get("number"))
    title = str(item.get("title") or "")
    body = str(item.get("body") or "")
    labels = item.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    labels_t = tuple(str(x) for x in labels)
    draft = bool(item.get("draft"))
    out = {
        "repo": repo,
        "number": ident,
        "task": "MRB" if kind in ("pr", "pull", "mrb") else "FR",
        "title": title[:120],
        "age_s": int(item.get("age_s") or 0),
        "holder": "",
        "rule": "",
        "state": "untracked",
        "stuck": False,
        "stuck_reason": "",
    }
    if kind in ("pr", "pull", "mrb"):
        out["task"] = "MRB"
        if draft and not gitclaim.is_offerable_intake_skill_lesson_pr(
            title=title, body=body, labels=labels_t
        ):
            # Draft non-lesson: held as draft (report only).
            if gitclaim.is_intake_harvest_receipt_pr(
                title=title, body=body, labels=labels_t
            ):
                out["state"] = "held"
                out["rule"] = "receipt"
                return out
            out["state"] = "held"
            out["rule"] = "draft"
            return out
        if gitclaim.is_intake_harvest_receipt_pr(
            title=title, body=body, labels=labels_t
        ) and not gitclaim.is_offerable_intake_skill_lesson_pr(
            title=title, body=body, labels=labels_t
        ):
            out["state"] = "held"
            out["rule"] = "receipt"
            return out
        hold = gitclaim.pr_hold_reason(title=title, body=body, labels=labels_t)
        if hold:
            out["state"] = "held"
            out["rule"] = f"hold:{hold}"
            return out
        if item.get("ci_wait"):
            out["state"] = "held"
            out["rule"] = "ci_wait"
            return out
        # Offerable MRB missing from queue.
        out["stuck"] = True
        out["stuck_reason"] = "untracked_offerable"
        return out

    # issue / FR
    out["task"] = "FR"
    skip = gitclaim.issue_skip_fr_reason(
        title=title, body=body, labels=labels_t, state=str(item.get("state") or "open")
    )
    if skip:
        out["state"] = "held"
        out["rule"] = f"skip:{skip}"
        return out
    hold = gitclaim.fr_hold_reason(title=title, body=body, labels=labels_t)
    if hold:
        out["state"] = "held"
        out["rule"] = f"hold:{hold}"
        return out
    out["stuck"] = True
    out["stuck_reason"] = "untracked_offerable"
    return out


def _queue_index(doc: dict) -> dict[str, tuple[str, dict]]:
    idx: dict[str, tuple[str, dict]] = {}
    for bucket in ("unaccepted", "accepted"):
        for row in doc.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            key = _job_key(row.get("repo"), row.get("task"), row.get("id"))
            idx[key] = (bucket, row)
            # Also index bare repo#n for catalog match across FR/MRB.
            bare = f"{str(row.get('repo') or '').strip().lower()}|{_norm_id(row.get('id')).lower()}"
            idx.setdefault(bare, (bucket, row))
    return idx


def release_silent_accepted(
    home: Path,
    *,
    now: float,
    live: set[str],
    activity: dict[str, float] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[dict]:
    """Release stuck accepted rows (holder gone / silent). Returns released retry rows."""
    import gitclaim

    released: list[dict] = []
    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            kept: list[dict] = []
            for row in list(doc.get("accepted") or []):
                if not isinstance(row, dict):
                    continue
                info = classify_queue_row(
                    row,
                    bucket="accepted",
                    now=now,
                    live=live,
                    idle=set(),
                    activity=activity,
                )
                if not info.get("stuck"):
                    kept.append(row)
                    continue
                # Protected holds already classified as held (not stuck).
                retry = gitclaim._row_to_unaccepted_retry(row)
                retry["note"] = f"stuck-sweep:{info.get('stuck_reason')}"
                released.append(retry)
                if log:
                    log(
                        f"stuck-sweep release {row.get('repo')}{_norm_id(row.get('id'))} "
                        f"holder={info.get('holder')} reason={info.get('stuck_reason')}"
                    )
            if not released:
                return []
            doc["accepted"] = kept
            doc["unaccepted"] = list(doc.get("unaccepted") or []) + released
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return []
    with contextlib_suppress():
        gitclaim.rebuild_offer_precompute(home)
    with contextlib_suppress():
        gitclaim.push_idle_offers_via_chair_outbox(home)
    return released


def contextlib_suppress():
    import contextlib

    return contextlib.suppress(Exception)


def enqueue_untracked(
    home: Path,
    items: list[dict],
    *,
    log: Callable[[str], None] | None = None,
) -> list[dict]:
    """Enqueue untracked offerable open items. Never merges/closes."""
    import gitclaim

    added: list[dict] = []
    for item in items:
        if not item.get("stuck") or item.get("stuck_reason") != "untracked_offerable":
            continue
        if item.get("state") == "held":
            continue
        repo = str(item.get("repo") or "")
        task = str(item.get("task") or "FR").upper()
        ident = _norm_id(item.get("number") or item.get("id"))
        if not repo or not ident:
            continue
        title = str(item.get("title") or "")
        line = f"{task} {repo}{ident}" + (f" {title}" if title else "")
        claim = gitclaim.GitClaim(
            repo=repo,
            task=task if task in gitclaim.TASK_KINDS else "FR",
            id=ident,
            event="stuck_sweep",
            action="enqueue",
            line=line,
        )
        result = gitclaim.enqueue_unaccepted(home, claim)
        if result in ("added", "duplicate"):
            added.append(item)
            if log and result == "added":
                log(f"stuck-sweep enqueue {repo}{ident} task={task}")
    return added


def run_stuck_sweep(
    home: Path,
    *,
    now: float | None = None,
    live: set[str] | None = None,
    idle: set[str] | None = None,
    activity: dict[str, float] | None = None,
    open_items: list[dict] | None = None,
    act: bool = True,
    log: Callable[[str], None] | None = None,
    announce: Callable[[str], None] | None = None,
) -> dict:
    """Classify, optionally act, persist report, announce on fingerprint change."""
    import gitclaim

    home = Path(home)
    now_f = time.time() if now is None else float(now)
    live_set = set(live) if live is not None else gitclaim.live_seat_nicks(home, now=now_f)
    idle_set = (
        set(idle)
        if idle is not None
        else gitclaim.free_seat_nicks(home, live_set)
    )
    act_map = dict(activity or {})
    if activity is None:
        for nick in live_set:
            ts = gitclaim.last_worker_activity(home, nick)
            if ts is not None:
                act_map[str(nick).lower()] = float(ts)

    doc = gitclaim.load_queue(home)
    classified: list[dict] = []
    for row in doc.get("accepted") or []:
        if isinstance(row, dict):
            classified.append(
                classify_queue_row(
                    row,
                    bucket="accepted",
                    now=now_f,
                    live=live_set,
                    idle=idle_set,
                    activity=act_map,
                )
            )
    for row in doc.get("unaccepted") or []:
        if isinstance(row, dict):
            classified.append(
                classify_queue_row(
                    row,
                    bucket="unaccepted",
                    now=now_f,
                    live=live_set,
                    idle=idle_set,
                    activity=act_map,
                )
            )

    idx = _queue_index(doc)
    catalog = list(open_items) if open_items is not None else load_open_catalog(home)
    untracked_infos: list[dict] = []
    for item in catalog:
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repo") or "")
        ident = _norm_id(item.get("id") or item.get("number"))
        task_hint = str(item.get("task") or item.get("kind") or "").upper()
        key = _job_key(repo, "MRB" if task_hint in ("PR", "PULL", "MRB") else "FR", ident)
        bare = f"{repo.strip().lower()}|{ident.lower()}"
        if key in idx or bare in idx:
            continue
        info = classify_open_item(item)
        classified.append(info)
        if info.get("stuck_reason") == "untracked_offerable":
            untracked_infos.append(info)

    actions = {"released": 0, "enqueued": 0}
    if act:
        released = release_silent_accepted(
            home,
            now=now_f,
            live=live_set,
            activity=act_map,
            log=log,
        )
        actions["released"] = len(released)
        enq = enqueue_untracked(home, untracked_infos, log=log)
        actions["enqueued"] = len(enq)
        # Refresh classification after acts (best-effort).
        if released or enq:
            doc2 = gitclaim.load_queue(home)
            # Re-stamp released rows as unaccepted in report.
            for r in released:
                classified.append(
                    {
                        "repo": r.get("repo"),
                        "number": _norm_id(r.get("id")),
                        "task": str(r.get("task") or "").upper(),
                        "title": str(r.get("title") or r.get("line") or "")[:120],
                        "age_s": 0,
                        "holder": "",
                        "rule": "",
                        "state": "unaccepted",
                        "stuck": False,
                        "stuck_reason": "released",
                    }
                )
            del doc2

    stuck = [c for c in classified if c.get("stuck")]
    # Held items always appear in the report (acceptance: listed with rule).
    held = [c for c in classified if c.get("state") == "held"]
    report = {
        "v": 1,
        "ts": _utc_now(),
        "now": now_f,
        "stuck": stuck,
        "held": held,
        "classified": classified,
        "actions": actions,
    }
    write_stuck_report(home, report)

    fp = "|".join(
        sorted(
            f"{s.get('repo')}{s.get('number')}:{s.get('stuck_reason') or s.get('rule')}"
            for s in stuck + held
        )
    )
    prev = ""
    fp_path = announce_fp_path(home)
    try:
        if fp_path.is_file():
            prev = fp_path.read_text(encoding="utf-8").strip()
    except OSError:
        prev = ""
    if fp != prev:
        try:
            fp_path.write_text(fp + "\n", encoding="utf-8")
        except OSError:
            pass
        if announce and (stuck or held):
            n_stuck = len(stuck)
            n_held = len(held)
            announce(
                f"stuck-sweep stuck={n_stuck} held={n_held} "
                f"released={actions['released']} enqueued={actions['enqueued']}"
            )
        elif announce and not stuck and not held and prev:
            announce("stuck-sweep clear")

    if log:
        log(
            f"stuck-sweep classified={len(classified)} stuck={len(stuck)} "
            f"held={len(held)} released={actions['released']} "
            f"enqueued={actions['enqueued']}"
        )
    return report


def format_stuck_lines(home: Path, *, limit: int = 40) -> list[str]:
    """Lines for ``!stuck`` (PM)."""
    report = load_stuck_report(home)
    stuck = list(report.get("stuck") or [])
    held = list(report.get("held") or [])
    if not stuck and not held:
        return ["stuck: (none)"]
    lines = [f"stuck: {len(stuck)} stuck, {len(held)} held (rule-listed)"]
    for row in (stuck + held)[:limit]:
        state = row.get("state") or "?"
        rule = row.get("stuck_reason") or row.get("rule") or ""
        holder = row.get("holder") or "-"
        age = row.get("age_s")
        lines.append(
            f"  {row.get('repo')}{row.get('number')} {row.get('task')} "
            f"state={state} rule={rule} holder={holder} age_s={age}"
        )
    if len(stuck) + len(held) > limit:
        lines.append(f"  … {len(stuck) + len(held) - limit} more")
    return lines


def digest_stuck_section(home: Path) -> list[dict]:
    """Public digest ``stuck`` list (repo, number, task, state, rule, age, holder)."""
    report = load_stuck_report(home)
    out: list[dict] = []
    for row in list(report.get("stuck") or []) + list(report.get("held") or []):
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "repo": row.get("repo"),
                "number": row.get("number"),
                "task": row.get("task"),
                "state": row.get("state"),
                "rule": row.get("stuck_reason") or row.get("rule") or "",
                "age_s": row.get("age_s"),
                "holder": row.get("holder") or "",
            }
        )
    return out
