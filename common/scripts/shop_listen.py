"""FR #211: Jeeves shop listener --- ACK/DONE -> queue + digest activity webhook.

Script-only, no tokens, no channel PRIVMSG. Parses worker lines in #{machine},
updates queue.json, and POSTs /bob/v1/report (or local apply_callback) so TipForm
START tiles show busy/idle descriptions.

Grammar (single line, case-insensitive verb):
  ACK  <TYPE> <owner/repo>#<n|main|main-red> [title...]
  DONE <TYPE> <owner/repo>#<n|main|main-red> <result> [url|rest...]
  NACK|GIVEUP <TYPE> <owner/repo>#<n|main|main-red> [reason...]

TYPE is FR|MRB|UAT|PR|FIX|BUILD.
Id matches gitclaim.ID_RE (FR #4857 / #4911): digits or synthetic #main / #main-red.
DONE result: FR = PR url only (no PASS/FAIL --- FR #2419 strips/ignores them if present).
MRB/UAT = PASS|FAIL [url]. Legacy ``PR <url>`` still accepted.
GIVEUP/NACK optional trailing reason is logged on the shop-listen INFO line (FR #1701).
"""
from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import bobreport
import gitclaim
import talk_seat_pid

# FR #1701: keep chair stdout / cmd-trace readable; reason is diagnostic only.
_GIVEUP_REASON_MAX = 120
_SECRETISH = re.compile(
    r"(?i)(password|token|secret|api[_-]?key|authorization)\s*[:=]\s*\S+"
)

# FR #4911: share gitclaim.ID_RE shape (`#\d+` | `#main` | `#main-red`) so DONE/ACK
# for main-side FIX rows parse; digits-only left seats stranded for BUSY_STALE_S.
_VERB_RE = re.compile(
    r"(?is)^\s*(?:@?\S+[:\s]+)?(?P<verb>ACK|DONE|NACK|GIVEUP)\s+"
    r"(?P<task>FR|MRB|UAT|PR|FIX|BUILD)\s+"
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<num>\d+|main(?:-red)?)"
    r"(?:\s+(?P<rest>.+))?\s*$"
)


_CR_COUNTER_RE = re.compile(
    r"(?i)\b(cr_findings|confirmed|fp)=(\d+)\b"
)


def mrb_cr_counters(rest: str) -> dict[str, int]:
    """FR #5317: optional ``cr_findings=N confirmed=N fp=N`` after the DONE URL."""
    out: dict[str, int] = {}
    for key, raw in _CR_COUNTER_RE.findall(rest or ""):
        out[str(key).lower()] = int(raw)
    return out


@dataclass(frozen=True)
class ShopJobLine:
    verb: str  # ACK|DONE|NACK|GIVEUP
    task: str
    repo: str
    id: str  # #n
    rest: str = ""
    result: str = ""
    title: str = ""
    url: str = ""


def _strip_bom_and_nested_privmsg(body: str) -> str:
    """FR #226 belt-and-braces: BOM + accidental PRIVMSG prefix still parse as ACK/DONE."""
    text = body or ""
    while text.startswith("\ufeff"):
        text = text[1:]
    text = text.strip()
    # Nested: PRIVMSG #chan :actual  OR  PRIVMSG #chan :PRIVMSG #chan :actual
    for _ in range(6):
        if not text.upper().startswith("PRIVMSG "):
            break
        rest = text[8:]
        if " :" not in rest:
            break
        _tgt, _, text = rest.partition(" :")
        while text.startswith("\ufeff"):
            text = text[1:]
        text = text.lstrip(" \t")
    return text.strip()


def parse_shop_job_line(body: str) -> ShopJobLine | None:
    text = _strip_bom_and_nested_privmsg(body or "")
    if not text:
        return None
    m = _VERB_RE.match(text)
    if not m:
        return None
    verb = m.group("verb").upper()
    task = m.group("task").upper()
    repo = m.group("repo")
    raw_num = str(m.group("num") or "").strip()
    if raw_num.isdigit():
        ident = f"#{int(raw_num)}"
    else:
        # Synthetic FIX ids (FR #4857): normalize to lower #main / #main-red.
        ident = f"#{raw_num.lower()}"
    if not gitclaim.ID_RE.fullmatch(ident):
        return None
    rest = (m.group("rest") or "").strip()
    result = ""
    title = ""
    url = ""
    if verb == "ACK":
        title = rest
    elif verb == "DONE":
        parts = rest.split()
        if parts and task == "FR":
            # FR #2419: PASS/FAIL belong to MRB/UAT only. Ignore them on FR DONE so the
            # PR url still completes ACC (mistaken PASS must not strand accepted rows).
            i = 0
            if parts[0].upper() == "PASS":
                i = 2 if len(parts) > 1 and parts[1].lower().startswith("merge") else 1
            elif parts[0].upper() == "FAIL":
                i = 1
                if len(parts) > 1 and not parts[1].lower().startswith("http"):
                    i = 2
            if i < len(parts) and parts[i].upper() == "PR":
                result = "PR"
                i += 1
            rest_tokens = parts[i:]
            for tok in rest_tokens:
                if tok.startswith("http://") or tok.startswith("https://"):
                    url = tok
                    break
            if url and result != "PR":
                result = url
            elif rest_tokens and not url and not result:
                result = rest_tokens[0]
            title = " ".join(rest_tokens)
        elif parts:
            # MRB/UAT/PR/FIX/BUILD: PASS merged | FAIL fix#12 | PR | url
            if parts[0].upper() == "PASS":
                result = "PASS merged" if len(parts) > 1 and parts[1].lower().startswith("merge") else "PASS"
                rest2 = " ".join(parts[2:]) if result == "PASS merged" else " ".join(parts[1:])
            elif parts[0].upper() == "FAIL":
                # Wire is ``FAIL <url>`` or ``FAIL fix#N <url>``. If the next token is a
                # URL, do not glue it into result (MRB #2426 hostile).
                if len(parts) > 1 and (
                    parts[1].startswith("http://") or parts[1].startswith("https://")
                ):
                    result = "FAIL"
                    rest2 = " ".join(parts[1:])
                else:
                    result = " ".join(parts[:2]) if len(parts) > 1 else "FAIL"
                    rest2 = " ".join(parts[2:]) if len(parts) > 1 else ""
            elif parts[0].upper() == "PR":
                result = "PR"
                rest2 = " ".join(parts[1:])
            elif parts[0].startswith("http://") or parts[0].startswith("https://"):
                url = parts[0]
                result = parts[0]
                rest2 = " ".join(parts[1:])
            else:
                result = parts[0]
                rest2 = " ".join(parts[1:])
            for tok in rest2.split():
                if tok.startswith("http://") or tok.startswith("https://"):
                    url = tok
                    break
            if not title:
                title = rest2
    else:
        title = rest
    return ShopJobLine(
        verb=verb,
        task=task,
        repo=repo,
        id=ident,
        rest=rest,
        result=result,
        title=title.strip(),
        url=url,
    )


def short_work(task: str, repo: str, ident: str) -> str:
    """Short worker status for the digest / tray: ``<reponame> FR|MRB|UAT #<num>`` (e.g. ``bobiverse FR #68``)."""
    name = str(repo or "").strip().rsplit("/", 1)[-1]
    num = str(ident or "").strip().lstrip("#")
    kind = str(task or "").strip().upper()
    return " ".join(p for p in (name, kind, f"#{num}" if num else "") if p)


def truncate_giveup_reason(raw: str, max_len: int = _GIVEUP_REASON_MAX) -> str:
    """Collapse whitespace, redact secretish tokens, truncate for shop-listen logs (FR #1701)."""
    text = " ".join(str(raw or "").split())
    if not text:
        return ""
    text = _SECRETISH.sub(r"\1=[redacted]", text)
    limit = max(8, int(max_len or _GIVEUP_REASON_MAX))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def format_shop_listen_info(result: dict, *, nick: str) -> str:
    """INFO shop-listen line for chair stdout. Includes reason= on NACK/GIVEUP (FR #1701).

    FR #1714: always emit DONE lines even when status=missing (ACC already gone) so
    wire evidence exists for orphan workers-map / nak-busy diagnosis.
    """
    verb = str((result or {}).get("verb") or "")
    status = str((result or {}).get("status") or "")
    act = (result or {}).get("activity")
    webhook = (result or {}).get("webhook")
    line = (
        f"INFO shop-listen {verb} status={status} nick={nick} "
        f"activity={act!r} webhook={webhook}"
    )
    if verb in ("NACK", "GIVEUP"):
        reason = truncate_giveup_reason(str((result or {}).get("reason") or ""))
        line = f"{line} reason={reason!r}"
    if verb == "DONE" and status == "missing":
        line = f"{line} note=missing-acc-still-idle-seat"
    if verb == "DONE" and status == "duplicate":
        # FR #5095: repeated DONE for an already-done row is a logged no-op.
        line = f"{line} note=duplicate-done-noop"
    return line


def activity_description(job: dict | ShopJobLine, title: str = "") -> str:
    """Worker status / tray START tile text: short ``<reponame> FR|MRB|UAT #<num>`` (no title, t816u)."""
    del title
    if isinstance(job, ShopJobLine):
        return short_work(job.task, job.repo, job.id)
    return short_work(str(job.get("task") or ""), str(job.get("repo") or ""), str(job.get("id") or ""))


def _title_from_line(line: str) -> str:
    if " by " in line and line.startswith("GIT "):
        mid = line.rsplit(" by ", 1)[0]
        parts = mid.split()
        if len(parts) >= 5:
            return " ".join(parts[5:]).strip()
    return ""


def worker_pid_from_nick(nick: str) -> int | None:
    n = (nick or "").strip()
    parsed = talk_seat_pid.parse_talk_seat_nick(n)
    if parsed:
        try:
            return int(parsed[1])
        except (TypeError, ValueError):
            return None
    # w-mh-41124
    w = bobreport.parse_worker_nick(n)
    if w:
        try:
            return int(w[1])
        except (TypeError, ValueError):
            return None
    m = re.search(r"-(\d+)$", n)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def is_shop_worker_nick(nick: str, channel: str) -> bool:
    """Only {machine}-pid or w-* in their own #{machine}."""
    n = (nick or "").strip()
    if not n or n.lower().startswith("bob-") or n.lower() in ("jeeves", "simon"):
        return False
    mid = bobreport.parse_talk_seat_nick(n) or (
        bobreport.parse_worker_nick(n)[0] if bobreport.parse_worker_nick(n) else None
    )
    if not mid:
        return False
    return bobreport.normalize_channel(channel).lower() == bobreport.shop_channel(mid).lower()


def format_activity_payload(
    *,
    machine: str,
    pid: int,
    nick: str,
    kind: str,
    working_on: str,
    state: str = "running",
) -> dict:
    return {
        "op": "merge",
        "machine": machine,
        "pid": int(pid),
        "nick": nick,
        "kind": kind or "grok",
        "state": state,
        "online": True,
        "working_on": working_on if state != "idle" else "",
    }


def apply_activity_local(home: Path, payload: dict, briefer: str = "Jeeves"):
    """Apply activity to local digest (tests / same-box chair).

    FR #69: resolve ``BOB_DIGEST_HOME`` so a chair ``--home`` (~/.jeeves) still updates
    the ChanServ-mirrored digest home, not a stale chair-home roster copy.
    """
    return bobreport.apply_callback(bobreport.fleet_digest_home(Path(home)), payload, briefer)


def post_activity(
    home: Path,
    payload: dict,
    *,
    post_fn: Callable[[dict], int] | None = None,
    briefer: str = "Jeeves",
) -> int:
    """POST to report URL or apply locally. Returns HTTP-like code (0/200/204)."""
    if post_fn is not None:
        return int(post_fn(payload))
    # Prefer local apply (chair owns digest home); optional HTTP via post_working_on
    out = apply_activity_local(home, payload, briefer=briefer)
    if getattr(out, "ok", False):
        return 204
    return 400


def _find_unaccepted(doc: dict, repo: str, task: str, ident: str) -> int | None:
    for i, row in enumerate(doc.get("unaccepted") or []):
        if (
            str(row.get("repo") or "") == repo
            and str(row.get("task") or "").upper() == task.upper()
            and str(row.get("id") or "") == ident
        ):
            return i
    return None


def _find_accepted(doc: dict, repo: str, task: str, ident: str) -> int | None:
    for i, row in enumerate(doc.get("accepted") or []):
        if (
            str(row.get("repo") or "") == repo
            and str(row.get("task") or "").upper() == task.upper()
            and str(row.get("id") or "") == ident
        ):
            return i
    return None


def accept_job_by_ref(
    home: Path,
    *,
    nick: str,
    channel: str,
    repo: str,
    task: str,
    ident: str,
    title: str = "",
) -> tuple[str, dict | None]:
    """Move matching unaccepted (or offered) row to accepted. Idempotent if already accepted by nick."""
    try:
        with gitclaim._lock(home):
            try:
                doc = gitclaim._load_queue_unlocked(home)
            except (OSError, ValueError):
                return "error", None
            # already accepted by this nick?
            for row in doc.get("accepted") or []:
                if (
                    str(row.get("repo")) == repo
                    and str(row.get("id")) == ident
                    and str(row.get("task") or "").upper() == task.upper()
                    and str(row.get("nick") or "") == nick
                ):
                    return "duplicate", dict(row)
            idx = _find_unaccepted(doc, repo, task, ident)
            if idx is None:
                # try any task kind same repo#id
                for i, row in enumerate(doc.get("unaccepted") or []):
                    if str(row.get("repo")) == repo and str(row.get("id")) == ident:
                        idx = i
                        break
            if idx is None:
                return "missing", None
            job = dict(doc["unaccepted"].pop(idx))
            job["nick"] = nick
            job["channel"] = bobreport.normalize_channel(channel)
            job["accepted_ts"] = gitclaim._utc_now()
            job["task"] = str(job.get("task") or task).upper()
            if title:
                job["title"] = title
            doc.setdefault("accepted", []).append(job)
            if len(doc["accepted"]) > gitclaim.ACCEPTED_CAP:
                doc["accepted"] = doc["accepted"][-gitclaim.ACCEPTED_CAP :]
            # FR #4604: FIX seat must not self-MRB the same PR after synchronize re-queue.
            if str(job.get("task") or "").upper() == "FIX":
                gitclaim.stamp_fix_seats_on_mrb_rows(
                    doc, repo, str(job.get("id") or ident), nick
                )
            try:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def _find_done(doc: dict, repo: str, task: str, ident: str) -> int | None:
    """FR #5095: locate done[] by repo+id+task (never repo+id alone)."""
    for i, row in enumerate(doc.get("done") or []):
        if (
            str(row.get("repo") or "") == repo
            and str(row.get("task") or "").upper() == task.upper()
            and str(row.get("id") or "") == ident
        ):
            return i
    return None


def complete_job_by_ref(
    home: Path,
    *,
    nick: str,
    repo: str,
    task: str,
    ident: str,
    result: str = "",
    url: str = "",
) -> tuple[str, dict | None]:
    """Mark accepted (or unaccepted) job done; apply light supersede hooks.

    FR #4422: never mark an FR done without a /pull/ URL (implement PR evidence).
    FR #5095: match on repo + id + task only (never repo + id alone). A repeated
    DONE for an already-done row is a no-op (status=duplicate) so a drain-retry
    DONE FIX cannot close the FR #4929 requeued MRB for the same PR.
    """
    task_u = str(task or "").upper()
    pull_src = (url or result or "").strip()
    if task_u == "FR" and "/pull/" not in pull_src:
        return "refused", None
    try:
        with gitclaim._lock(home):
            try:
                doc = gitclaim._load_queue_unlocked(home)
            except (OSError, ValueError):
                return "error", None
            job = None
            # FR #5095: accepted / unaccepted match must include task.
            ai = _find_accepted(doc, repo, task, ident)
            if ai is not None:
                job = dict(doc["accepted"].pop(ai))
            else:
                ui = _find_unaccepted(doc, repo, task, ident)
                if ui is not None:
                    job = dict(doc["unaccepted"].pop(ui))
            if job is None:
                # Already-done same task: no-op (do not touch sibling task rows).
                di = _find_done(doc, repo, task, ident)
                if di is not None:
                    return "duplicate", dict(doc["done"][di])
                return "missing", None
            job["done_ts"] = gitclaim._utc_now()
            job["done_by"] = nick
            job["result"] = result
            if url:
                job["url"] = url
            doc.setdefault("done", []).append(job)
            if len(doc["done"]) > gitclaim.ACCEPTED_CAP:
                doc["done"] = doc["done"][-gitclaim.ACCEPTED_CAP :]
            # FR #4604: FIX seat must not self-MRB the same PR after synchronize re-queue.
            if str(job.get("task") or "").upper() == "FIX":
                gitclaim.stamp_fix_seats_on_mrb_rows(
                    doc, repo, str(job.get("id") or ident), nick
                )
                # FR #4929: DONE FIX must requeue MRB even when synchronize arrived
                # (and was purged) before this DONE --- otherwise the new head sits
                # with no MRB until a manual !resync.
                pull = str(url or job.get("url") or "").strip()
                if not gitclaim.PULL_URL_RE.search(pull):
                    pull = (
                        f"https://github.com/{repo}/pull/"
                        f"{str(job.get('id') or ident).lstrip('#')}"
                    )
                gitclaim.ensure_mrb_requeued_after_head_move(
                    doc,
                    home,
                    repo=repo,
                    pr=str(job.get("id") or ident),
                    url=pull,
                    reason="done-fix",
                )
                gitclaim.stamp_fix_seats_on_mrb_rows(
                    doc, repo, str(job.get("id") or ident), nick
                )
            # FR #740 / #738 / #1323: DONE MRB (PASS or FAIL) purges any lingering unaccepted
            # duplicate and stamps ledger mrb_done so the next !bored cannot re-offer the same PR.
            if str(job.get("task") or "").upper() == "MRB":
                gitclaim._remove_unaccepted_tasks(doc, repo, ident, {"MRB"})
                gitclaim.stamp_mrb_done(home, repo, ident)
            # supersede light: DONE FR with PR url -> queue MRB if url has /pull/ (FR #254).
            # FR #4851: if the issue was already closed (cancel_pending / state=closed)
            # before this DONE, do not auto-queue MRB --- stamp needs_human instead.
            if str(job.get("task") or "").upper() == "FR" and (
                result.upper().startswith("PR") or "/pull/" in (url or result)
            ):
                closed_mid = (
                    str(job.get("state") or "").strip().lower() == "closed"
                    or bool(job.get("cancel_pending"))
                )
                gitclaim._remove_unaccepted_tasks(doc, repo, ident, {"FR"})
                if closed_mid:
                    job["needs_human"] = True
                    job["state"] = "closed"
                else:
                    pr_repo = repo
                    pr_id = ""
                    parsed = gitclaim.parse_github_pull_url(url or result or "")
                    if parsed:
                        pr_repo, pr_id = parsed
                    else:
                        m = re.search(r"/pull/(\d+)", url or result or "")
                        if m:
                            pr_id = f"#{m.group(1)}"
                    if pr_id:
                        claim = gitclaim.GitClaim(
                            repo=pr_repo,
                            task="MRB",
                            id=pr_id,
                            event="pull_request",
                            action="opened",
                            line=str(job.get("line") or ""),
                            refs=(ident,),
                        )
                        # FR implementer becomes MRB author_seat / implementer_seat (FR #265).
                        # FR #2623: a DONE that only cites another seat's open PR must keep the
                        # true implementer (existing MRB stamp or earlier DONE FR for this pull).
                        done_nick = str(job.get("nick") or job.get("done_by") or nick or "").strip()
                        fr_author = gitclaim.resolve_done_fr_implementer_seat(
                            doc,
                            pr_repo=pr_repo,
                            pr_id=pr_id,
                            issue_repo=repo,
                            issue_id=ident,
                            done_nick=done_nick,
                        )
                        extra = {}
                        if fr_author:
                            extra["author_seat"] = fr_author
                            extra["implementer_seat"] = fr_author
                        extra["supersedes"] = gitclaim.fr_issue_key(repo, ident)
                        # FR #2604: stamp the pull URL so mrb_row_offerable is True. Webhook /
                        # resync paths already set url; DONE FR used to enqueue without it, so
                        # the new MRB sat unaccepted but never offered (0 offerable).
                        pull_src = (url or result or "").strip()
                        if "/pull/" in pull_src:
                            extra["url"] = pull_src
                        elif pr_id:
                            extra["url"] = (
                                f"https://github.com/{pr_repo}/pull/{str(pr_id).lstrip('#')}"
                            )
                        gitclaim._append_unaccepted(doc, claim, **extra)
            # t853u: an MRB PASS no longer queues per-PR / per-issue UAT rows; UAT is one row per repo,
            # created by the GitHub resync once every issue is closed and every PR is merged.
            try:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def is_self_mrb_giveup_reason(raw: str) -> bool:
    """True when a GIVEUP reason is self-MRB (FR #4658), not a review GIVEUP."""
    return "self-mrb" in str(raw or "").lower()


def return_job_to_unaccepted(
    home: Path,
    *,
    repo: str,
    task: str,
    ident: str,
    now: float | None = None,
    reason: str = "",
    expected_nick: str = "",
) -> tuple[str, dict | None]:
    """Return an accepted job to unaccepted after NACK/GIVEUP (FR #180 cooldown + needs_human)."""
    import time as _time
    from datetime import datetime, timedelta, timezone

    now_f = _time.time() if now is None else float(now)
    try:
        with gitclaim._lock(home):
            try:
                doc = gitclaim._load_queue_unlocked(home)
            except (OSError, ValueError):
                return "error", None
            ai = _find_accepted(doc, repo, task, ident)
            if ai is None:
                for i, row in enumerate(doc.get("accepted") or []):
                    if str(row.get("repo")) == repo and str(row.get("id")) == ident:
                        ai = i
                        break
            if ai is None:
                return "missing", None
            if expected_nick and str(doc["accepted"][ai].get("nick") or "").lower() != expected_nick.lower():
                return "missing", None
            job = dict(doc["accepted"].pop(ai))
            gave_up_by = str(job.get("nick") or "").strip()
            # FR #4851: NACK/GIVEUP of a closed / cancel_pending FR finalizes to done
            # CLOSED (never re-enter unaccepted) and clears digest doing.
            closed_cancel = (
                str(job.get("task") or "").upper() == "FR"
                and (
                    str(job.get("state") or "").strip().lower() == "closed"
                    or bool(job.get("cancel_pending"))
                )
            )
            if closed_cancel:
                fin = dict(job)
                fin["result"] = "CLOSED"
                fin["done_ts"] = gitclaim._utc_now()
                fin["state"] = "closed"
                fin["done_by"] = gave_up_by
                if reason:
                    fin["cancel_reason"] = str(reason).strip()[:200]
                for k in (
                    "nick",
                    "accepted_ts",
                    "offered_to",
                    "offered_ts",
                    "offered_channel",
                    "channel",
                    "cancel_pending",
                ):
                    fin.pop(k, None)
                doc.setdefault("done", []).append(fin)
                if len(doc["done"]) > gitclaim.ACCEPTED_CAP:
                    doc["done"] = doc["done"][-gitclaim.ACCEPTED_CAP :]
                try:
                    gitclaim._write_queue(gitclaim.queue_path(home), doc)
                except OSError:
                    return "error", None
                ident_clear = str(fin.get("id") or ident or "").lstrip("#")
                if gave_up_by and ident_clear:
                    with contextlib.suppress(Exception):
                        bobreport.clear_seat_doing(
                            home, gave_up_by, only_if_work_contains=ident_clear
                        )
                return "ok", fin
            # FR #3277 / #4658: author or pusher self-MRB GIVEUP must not burn the
            # GIVEUP_NEEDS_HUMAN_COUNT budget or stamp needs_human. The seat is
            # excluded; a fresh seat must stay offerable.
            self_mrb_giveup = (
                str(job.get("task") or "").upper() == "MRB"
                and bool(gave_up_by)
                and (
                    gitclaim.nick_is_row_author(job, gave_up_by)
                    or is_self_mrb_giveup_reason(reason)
                )
            )
            # FR #4881: out-of-fuel is about the seat (FR #4181 mark), not the job.
            # Do not burn giveup_count, giveup_seats, cooldown, or needs_human ---
            # empty giveup_seats + cooldown_until would block every seat.
            out_of_fuel_giveup = gitclaim.is_out_of_fuel_reason(reason)
            seat_not_job_giveup = self_mrb_giveup or out_of_fuel_giveup
            for k in ("nick", "accepted_ts", "offered_to", "offered_ts", "offered_channel", "channel"):
                job.pop(k, None)
            try:
                prior = int(job.get("giveup_count") or 0)
            except (TypeError, ValueError):
                prior = 0
            if seat_not_job_giveup:
                count = prior
            else:
                count = prior + 1
                job["giveup_count"] = count
            job["giveup_ts"] = gitclaim._utc_now()
            # FR #628: never hand this row back to a seat that already gave it up.
            # Store canonical <machine>-<pid> so w-io-* / w-mh-* match later offers.
            # FR #4881: out-of-fuel must not append giveup_seats (seat mark is enough).
            seats = []
            seen_seats: set[str] = set()
            for raw in str(job.get("giveup_seats") or "").split(","):
                raw = raw.strip()
                if not raw:
                    continue
                canon = (gitclaim.canonical_worker_nick(raw) or raw).strip()
                key = canon.lower()
                if key in seen_seats:
                    continue
                seen_seats.add(key)
                seats.append(canon)
            if gave_up_by and not out_of_fuel_giveup:
                canon_g = (gitclaim.canonical_worker_nick(gave_up_by) or gave_up_by).strip()
                if canon_g and canon_g.lower() not in seen_seats:
                    seats.append(canon_g)
            if seats:
                job["giveup_seats"] = ",".join(seats)
            if self_mrb_giveup and gave_up_by:
                gitclaim.append_author_seat(job, gave_up_by)
            # FR #180 / #1363: stamp cooldown_until after job-caused GIVEUP/NACK.
            # FR #4881: skip for out-of-fuel (no giveup_seats => global cooldown).
            if not out_of_fuel_giveup:
                until = datetime.fromtimestamp(now_f, tz=timezone.utc) + timedelta(
                    seconds=float(gitclaim.GIVEUP_COOLDOWN_S)
                )
                job["cooldown_until"] = until.replace(microsecond=0).isoformat().replace(
                    "+00:00", "Z"
                )
            if (not seat_not_job_giveup) and count >= int(gitclaim.GIVEUP_NEEDS_HUMAN_COUNT):
                job["needs_human"] = True
            # needs-mrb1 must not force needs_human (operator 2026-10-04: hallucination).
            doc.setdefault("unaccepted", []).append(job)
            try:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def handle_shop_worker_line(
    home: Path,
    *,
    nick: str,
    channel: str,
    body: str,
    kind: str = "grok",
    post_fn: Callable[[dict], int] | None = None,
    briefer: str = "Jeeves",
) -> dict:
    """Chair path: parse line, update queue, fire activity webhook. No channel reply."""
    out: dict = {"handled": False, "status": "", "verb": ""}
    if not is_shop_worker_nick(nick, channel):
        return out
    parsed = parse_shop_job_line(body)
    if not parsed:
        return out
    out["handled"] = True
    out["verb"] = parsed.verb
    mid = bobreport.parse_talk_seat_nick(nick) or (
        bobreport.parse_worker_nick(nick)[0] if bobreport.parse_worker_nick(nick) else None
    )
    pid = worker_pid_from_nick(nick)
    if not mid or pid is None:
        out["status"] = "bad-nick"
        return out

    if parsed.verb == "ACK":
        st, job = accept_job_by_ref(
            home,
            nick=nick,
            channel=channel,
            repo=parsed.repo,
            task=parsed.task,
            ident=parsed.id,
            title=parsed.title,
        )
        out["status"] = st
        out["job"] = job
        try:  # t852u: durable seat ledger (survives resync)
            gitclaim.ledger_note_event(home, nick, "ACK", parsed.task, parsed.repo, parsed.id, job if isinstance(job, dict) else None)
        except Exception:  # noqa: BLE001
            pass
        if st == "missing":
            # FR #4642: a re-ACK of a job this seat already DONE'd must not recreate
            # an ack-missing hold (lost follow-up DONE then nak-busy forever).
            if gitclaim.seat_done_without_later_offer(
                home, nick, parsed.repo, parsed.task, parsed.id
            ):
                out["status"] = "duplicate-after-done"
                return out
            # The seat is working on what it ACKed even when the queue row is gone (re-synced, already
            # accepted, offered twice): the digest must still show it as doing (t816u).
            job = {"task": parsed.task, "repo": parsed.repo, "id": parsed.id}
            # FR #4115: record a seat hold so !bored / done-offer treat the seat as busy
            # (no accepted row exists for status=missing after a Jeeves restart).
            try:
                # FR #4415: mark via=ack-missing so seat_open_job does not void
                # this hold when the queue row is absent (contrast: offer holds).
                gitclaim.note_seat_hold(home, nick, job, via="ack-missing")
            except Exception:  # noqa: BLE001
                pass
        if st in ("ok", "duplicate", "missing") and job is not None:
            desc = activity_description(job, parsed.title)
            payload = format_activity_payload(
                machine=mid, pid=pid, nick=nick, kind=kind, working_on=desc, state="running"
            )
            code = post_activity(home, payload, post_fn=post_fn, briefer=briefer)
            out["webhook"] = code
            out["activity"] = desc
        return out

    if parsed.verb in ("NACK", "GIVEUP"):
        # FR #1701: trailing reason from the GIVEUP/NACK PRIVMSG for chair stdout/cmd-trace.
        # FR #4658: self-MRB must be known before the row is returned, or pusher
        # seats burn giveup_count and stamp needs_human.
        reason = truncate_giveup_reason(parsed.rest or parsed.title or "")
        st, job = return_job_to_unaccepted(
            home,
            repo=parsed.repo,
            task=parsed.task,
            ident=parsed.id,
            reason=reason,
        )
        out["status"] = st
        out["job"] = job
        out["reason"] = reason
        try:  # t852u: remember who gave this up, forever (resync drops row stamps)
            gitclaim.ledger_note_event(home, nick, parsed.verb, parsed.task, parsed.repo, parsed.id, job if isinstance(job, dict) else None)
        except Exception:  # noqa: BLE001
            pass
        payload = format_activity_payload(
            machine=mid, pid=pid, nick=nick, kind=kind, working_on="", state="idle"
        )
        out["webhook"] = post_activity(home, payload, post_fn=post_fn, briefer=briefer)
        out["activity"] = ""
        return out

    if parsed.verb == "DONE":
        st, job = complete_job_by_ref(
            home,
            nick=nick,
            repo=parsed.repo,
            task=parsed.task,
            ident=parsed.id,
            result=parsed.result,
            url=parsed.url,
        )
        out["status"] = st
        out["job"] = job
        try:
            gitclaim.ledger_note_event(
                home, nick, "DONE", parsed.task, parsed.repo, parsed.id,
                job if isinstance(job, dict) else None, result=parsed.result, url=parsed.url,
            )
        except Exception:  # noqa: BLE001
            pass
        
        # FR #3948: DONE MRB PASS -> merge-on-green ledger (seat never polls CI).
        if str(parsed.task or "").upper() == "MRB" and str(parsed.result or "").upper() == "PASS":
            try:
                import mrb_merge_on_green

                mog = mrb_merge_on_green.enqueue_from_done(
                    home,
                    repo=parsed.repo,
                    pr_url=parsed.url or "",
                    result=parsed.result or "",
                    nick=nick,
                )
                if mog:
                    out["merge_on_green"] = mog
            except Exception:  # noqa: BLE001
                pass
        # FR #4718: DONE MRB FAIL with no fix PR queues FIX for that head at once.
        if str(parsed.task or "").upper() == "MRB" and str(parsed.result or "").upper() == "FAIL":
            try:
                import mrb_merge_on_green

                fail_fix = mrb_merge_on_green.enqueue_from_mrb_fail_done(
                    home,
                    repo=parsed.repo,
                    pr_url=parsed.url or str((job or {}).get("url") or ""),
                    nick=nick,
                    sha=str((job or {}).get("pass_sha") or ""),
                )
                if fail_fix:
                    out["mrb_fail_fix"] = fail_fix
            except Exception:  # noqa: BLE001
                pass
        payload = format_activity_payload(
            machine=mid, pid=pid, nick=nick, kind=kind, working_on="", state="idle"
        )
        out["webhook"] = post_activity(home, payload, post_fn=post_fn, briefer=briefer)
        out["activity"] = ""
        return out

    out["status"] = "unknown"
    return out


def handle_shop_worker_quit(
    home: Path,
    *,
    nick: str,
    kind: str = "grok",
    post_fn: Callable[[dict], int] | None = None,
    briefer: str = "Jeeves",
) -> dict:
    """On QUIT: idle webhook + return this nick's accepted jobs to unaccepted."""
    out: dict = {"handled": False}
    mid = bobreport.parse_talk_seat_nick(nick) or (
        bobreport.parse_worker_nick(nick)[0] if bobreport.parse_worker_nick(nick) else None
    )
    pid = worker_pid_from_nick(nick)
    if not mid or pid is None:
        return out
    out["handled"] = True
    # return accepted jobs owned by nick
    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            keep = []
            returned = 0
            for row in doc.get("accepted") or []:
                if str(row.get("nick") or "") == nick:
                    j = dict(row)
                    for k in ("nick", "accepted_ts", "offered_to", "offered_ts"):
                        j.pop(k, None)
                    doc.setdefault("unaccepted", []).append(j)
                    returned += 1
                else:
                    keep.append(row)
            doc["accepted"] = keep
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
            out["returned"] = returned
    except (TimeoutError, OSError, ValueError):
        out["status"] = "error"
        return out
    payload = format_activity_payload(
        machine=mid, pid=pid, nick=nick, kind=kind, working_on="", state="idle"
    )
    out["webhook"] = post_activity(home, payload, post_fn=post_fn, briefer=briefer)
    out["status"] = "ok"
    return out
