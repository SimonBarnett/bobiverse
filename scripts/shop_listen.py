"""FR #211: Jeeves shop listener — ACK/DONE → queue + digest activity webhook.

Script-only, no tokens, no channel PRIVMSG. Parses worker lines in #{machine},
updates queue.json, and POSTs /bob/v1/report (or local apply_callback) so TipForm
START tiles show busy/idle descriptions.

Grammar (single line, case-insensitive verb):
  ACK  <TYPE> <owner/repo>#<n> [title...]
  DONE <TYPE> <owner/repo>#<n> <result> [url|rest...]
  NACK|GIVEUP <TYPE> <owner/repo>#<n>

TYPE is FR|MRB|UAT|PR|FIX|BUILD. result examples: PASS merged | FAIL fix#m | PR <url>
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import bobreport
import gitclaim
import talk_seat_pid

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
        # result is first tokens until URL or end
        parts = rest.split()
        if parts:
            # PASS merged | FAIL fix#12 | PR
            if parts[0].upper() == "PASS":
                result = "PASS merged" if len(parts) > 1 and parts[1].lower().startswith("merge") else "PASS"
                rest2 = " ".join(parts[2:]) if result == "PASS merged" else " ".join(parts[1:])
            elif parts[0].upper() == "FAIL":
                result = " ".join(parts[:2]) if len(parts) > 1 else "FAIL"
                rest2 = " ".join(parts[2:]) if len(parts) > 1 else ""
            elif parts[0].upper() == "PR":
                result = "PR"
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


def activity_description(job: dict | ShopJobLine, title: str = "") -> str:
    """Tray START tile text: ``FR owner/repo#n title``."""
    if isinstance(job, ShopJobLine):
        task, repo, ident = job.task, job.repo, job.id
        tit = title or job.title
    else:
        task = str(job.get("task") or "")
        repo = str(job.get("repo") or "")
        ident = str(job.get("id") or "")
        tit = title or _title_from_line(str(job.get("line") or ""))
    core = f"{task} {repo}{ident}".strip()
    if tit:
        # strip secret markers from title for webhook
        if bobreport.looks_like_secret(tit):
            tit = "[title redacted]"
        return f"{core} {tit}".strip()
    return core


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
    """Apply activity to local digest (tests / same-box chair)."""
    return bobreport.apply_callback(home, payload, briefer)


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
            # supersede light: DONE FR with PR url → queue MRB if url has /pull/
            if str(job.get("task") or "").upper() == "FR" and (
                result.upper().startswith("PR") or "/pull/" in (url or result)
            ):
                pr_id = ""
                m = re.search(r"/pull/(\d+)", url or result or "")
                if m:
                    pr_id = f"#{m.group(1)}"
                if pr_id:
                    claim = gitclaim.GitClaim(
                        repo=repo,
                        task="MRB",
                        id=pr_id,
                        event="pull_request",
                        action="opened",
                        line=str(job.get("line") or ""),
                        refs=(ident,),
                    )
                    gitclaim._append_unaccepted(doc, claim)
            if str(job.get("task") or "").upper() == "MRB" and "PASS" in (result or "").upper():
                # UAT for refs if any
                refs = job.get("refs") or []
                if isinstance(refs, str):
                    refs = [refs]
                for ref in refs:
                    ref_s = str(ref)
                    if not ref_s.startswith("#"):
                        continue
                    uat = gitclaim.GitClaim(
                        repo=repo,
                        task="UAT",
                        id=ref_s,
                        event="issues",
                        action="uat",
                        line=str(job.get("line") or ""),
                        refs=(ident,),
                    )
                    gitclaim._append_unaccepted(doc, uat)
            try:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def return_job_to_unaccepted(home: Path, *, repo: str, task: str, ident: str) -> tuple[str, dict | None]:
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
            for k in ("nick", "accepted_ts", "offered_to", "offered_ts", "channel"):
                job.pop(k, None)
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
        if st in ("ok", "duplicate") and job is not None:
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
