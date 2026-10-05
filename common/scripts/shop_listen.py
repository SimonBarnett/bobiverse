"""FR #211: Jeeves shop listener — ACK/DONE → queue + digest activity webhook.

Script-only, no tokens, no channel PRIVMSG. Parses worker lines in #{machine},
updates queue.json, and POSTs /bob/v1/report (or local apply_callback) so TipForm
START tiles show busy/idle descriptions.

Grammar (single line, case-insensitive verb):
  ACK  <TYPE> <owner/repo>#<n> [title...]
  DONE <TYPE> <owner/repo>#<n> <result> [url|rest...]
  NACK|GIVEUP <TYPE> <owner/repo>#<n> [reason...]

TYPE is FR|MRB|UAT|PR|FIX|BUILD.
DONE result: FR = PR url only (no PASS/FAIL — FR #2419 strips/ignores them if present).
MRB/UAT = PASS|FAIL [url]. Legacy ``PR <url>`` still accepted.
GIVEUP/NACK optional trailing reason is logged on the shop-listen INFO line (FR #1701).
"""
from __future__ import annotations

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

_VERB_RE = re.compile(
    r"(?is)^\s*(?:@?\S+[:\s]+)?(?P<verb>ACK|DONE|NACK|GIVEUP)\s+"
    r"(?P<task>FR|MRB|UAT|PR|FIX|BUILD)\s+"
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<num>\d+)"
    r"(?:\s+(?P<rest>.+))?\s*$"
)


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
    ident = f"#{int(m.group('num'))}"
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
            try:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


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
    """Mark accepted (or unaccepted) job done; apply light supersede hooks."""
    try:
        with gitclaim._lock(home):
            try:
                doc = gitclaim._load_queue_unlocked(home)
            except (OSError, ValueError):
                return "error", None
            job = None
            # from accepted
            ai = _find_accepted(doc, repo, task, ident)
            if ai is None:
                for i, row in enumerate(doc.get("accepted") or []):
                    if str(row.get("repo")) == repo and str(row.get("id")) == ident:
                        ai = i
                        break
            if ai is not None:
                job = dict(doc["accepted"].pop(ai))
            else:
                ui = _find_unaccepted(doc, repo, task, ident)
                if ui is None:
                    for i, row in enumerate(doc.get("unaccepted") or []):
                        if str(row.get("repo")) == repo and str(row.get("id")) == ident:
                            ui = i
                            break
                if ui is not None:
                    job = dict(doc["unaccepted"].pop(ui))
            if job is None:
                return "missing", None
            job["done_ts"] = gitclaim._utc_now()
            job["done_by"] = nick
            job["result"] = result
            if url:
                job["url"] = url
            doc.setdefault("done", []).append(job)
            if len(doc["done"]) > gitclaim.ACCEPTED_CAP:
                doc["done"] = doc["done"][-gitclaim.ACCEPTED_CAP :]
            # FR #740 / #738 / #1323: DONE MRB (PASS or FAIL) purges any lingering unaccepted
            # duplicate and stamps ledger mrb_done so the next !bored cannot re-offer the same PR.
            if str(job.get("task") or "").upper() == "MRB":
                gitclaim._remove_unaccepted_tasks(doc, repo, ident, {"MRB"})
                gitclaim.stamp_mrb_done(home, repo, ident)
            # supersede light: DONE FR with PR url → queue MRB if url has /pull/ (FR #254).
            if str(job.get("task") or "").upper() == "FR" and (
                result.upper().startswith("PR") or "/pull/" in (url or result)
            ):
                pr_repo = repo
                pr_id = ""
                parsed = gitclaim.parse_github_pull_url(url or result or "")
                if parsed:
                    pr_repo, pr_id = parsed
                else:
                    m = re.search(r"/pull/(\d+)", url or result or "")
                    if m:
                        pr_id = f"#{m.group(1)}"
                # Drop any lingering unaccepted FR for this issue (resync / duplicate).
                gitclaim._remove_unaccepted_tasks(doc, repo, ident, {"FR"})
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
                    fr_author = str(job.get("nick") or job.get("done_by") or "").strip()
                    extra = {}
                    if fr_author:
                        extra["author_seat"] = fr_author
                        extra["implementer_seat"] = fr_author
                    extra["supersedes"] = gitclaim.fr_issue_key(repo, ident)
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


def return_job_to_unaccepted(
    home: Path, *, repo: str, task: str, ident: str, now: float | None = None
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
            job = dict(doc["accepted"].pop(ai))
            gave_up_by = str(job.get("nick") or "").strip()
            for k in ("nick", "accepted_ts", "offered_to", "offered_ts", "offered_channel", "channel"):
                job.pop(k, None)
            try:
                count = int(job.get("giveup_count") or 0) + 1
            except (TypeError, ValueError):
                count = 1
            job["giveup_count"] = count
            job["giveup_ts"] = gitclaim._utc_now()
            # FR #628: never hand this row back to a seat that already gave it up.
            # Store canonical <machine>-<pid> so w-io-* / w-mh-* match later offers.
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
            if gave_up_by:
                canon_g = (gitclaim.canonical_worker_nick(gave_up_by) or gave_up_by).strip()
                if canon_g and canon_g.lower() not in seen_seats:
                    seats.append(canon_g)
            if seats:
                job["giveup_seats"] = ",".join(seats)
            until = datetime.fromtimestamp(now_f, tz=timezone.utc) + timedelta(
                seconds=float(gitclaim.GIVEUP_COOLDOWN_S)
            )
            # FR #180 / #1363: always stamp cooldown_until after GIVEUP/NACK.
            job["cooldown_until"] = until.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            if count >= int(gitclaim.GIVEUP_NEEDS_HUMAN_COUNT):
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
            # The seat is working on what it ACKed even when the queue row is gone (re-synced, already
            # accepted, offered twice): the digest must still show it as doing (t816u).
            job = {"task": parsed.task, "repo": parsed.repo, "id": parsed.id}
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
        st, job = return_job_to_unaccepted(
            home, repo=parsed.repo, task=parsed.task, ident=parsed.id
        )
        out["status"] = st
        out["job"] = job
        # FR #1701: trailing reason from the GIVEUP/NACK PRIVMSG for chair stdout/cmd-trace.
        out["reason"] = truncate_giveup_reason(parsed.rest or parsed.title or "")
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
