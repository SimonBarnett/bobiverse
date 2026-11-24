"""FR #9698: chair auto-files one machine-pinned bobiverse issue on disk GIVEUP/NACK.

When a seat returns ``worktree-create-failed:disk`` / ``disk-low`` (FR #6240),
ircJeeves must ensure **one** open SimonBarnett/bobiverse issue exists for that
machine with a dedicated body line ``require_machine: <machine>`` (ops note) and
label ``needs-<machine>`` (bobiverse pin — FR #9637 body text alone does not pin).

Twin-check first; comment on an existing open twin instead of filing a second.
Never raises to the shop-listen path.
"""
from __future__ import annotations

import re
from typing import Any, Callable

REPO = "SimonBarnett/bobiverse"
TITLE_SUFFIX = "disk starvation — worktree-create-failed:disk"
MARKER = "<!-- bob_fr9698_disk_starvation_chair -->"
_DISK_TOKEN_RE = re.compile(
    r"(?i)(?:worktree-create-failed:disk(?:-low)?|\bdisk-low\b|\bdisk\s*starvation\b)"
)


def is_disk_starvation_reason(reason: str | None) -> bool:
    """True for FR #6240 disk-class NACK/GIVEUP reasons."""
    raw = str(reason or "").strip()
    if not raw:
        return False
    if _DISK_TOKEN_RE.search(raw):
        return True
    # Token forms after shop_listen truncation / reason= prefix.
    low = raw.lower().replace(" ", "")
    return (
        "worktree-create-failed:disk" in low
        or low.startswith("disk-low")
        or ":disk-low" in low
        or (
            "worktree-create-failed" in low
            and (low.endswith(":disk") or ":disk" in low)
        )
    )


def machine_from_seat(nick: str | None) -> str:
    """Seat nick -> machine id (never hard-code a host name)."""
    raw = str(nick or "").strip()
    if not raw:
        return ""
    try:
        import bobreport

        mid = str(bobreport.machine_from_nick(raw) or "").strip()
        if mid:
            return mid.lower()
        parsed = bobreport.parse_seat_nick(raw)
        if parsed and parsed[0]:
            return str(parsed[0]).strip().lower()
    except Exception:
        pass
    # Fallback: machine-pid / machine_pid
    for sep in ("-", "_"):
        if sep in raw:
            return raw.split(sep, 1)[0].strip().lower()
    return raw.lower()


def issue_title(machine: str) -> str:
    mid = str(machine or "").strip().lower() or "unknown"
    return f"{mid}: {TITLE_SUFFIX}"


def needs_machine_label(machine: str) -> str:
    mid = str(machine or "").strip().lower()
    return f"needs-{mid}" if mid else "needs-unknown"


def issue_body(
    *,
    machine: str,
    nick: str = "",
    job: str = "",
    reason: str = "",
    free_gb: str | float | None = None,
) -> str:
    mid = str(machine or "").strip().lower() or "unknown"
    free_s = "" if free_gb is None else str(free_gb)
    lines = [
        f"require_machine: {mid}",
        "",
        MARKER,
        "",
        "## What",
        f"Disk starvation on `{mid}` (worktree-create-failed:disk / disk-low FR #6240).",
        "Machine-pinned for the Jeeves agent (FR #9698 chair auto-file).",
        "",
        "## Evidence",
        f"- seats: {nick or '(unknown)'}",
        f"- jobs: {job or '(unknown)'}",
        f"- reasons: {reason or '(unknown)'}",
    ]
    if free_s:
        lines.append(f"- FreeGB: {free_s}")
    lines.extend(
        [
            "",
            "## Fix",
            f"Run `Invoke-BobiverseDiskStarvationRemediate.ps1 -Machine {mid}` "
            "(Clear-BobiverseJobWorktrees + Clear-BobiverseSeatDisk + orphan bob-bridge).",
            "Then ops `!cleargiveup` for blocked rows on that machine.",
            "",
            f"---\n_via-intake FR=#9698 chair disk GIVEUP/NACK_\n",
        ]
    )
    return "\n".join(lines)


def is_disk_starvation_twin(issue: dict[str, Any] | None, machine: str) -> bool:
    """True when an open issue is the machine's disk-starvation twin."""
    if not isinstance(issue, dict):
        return False
    mid = str(machine or "").strip().lower()
    if not mid:
        return False
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    blob = f"{title}\n{body}".lower()
    if MARKER.lower() in blob:
        return mid in blob
    if mid not in title.lower() and f"require_machine: {mid}" not in body.lower():
        # Title form "<machine>: disk starvation..."
        if not title.lower().startswith(f"{mid}:"):
            return False
    return (
        "disk starvation" in blob
        or "worktree-create-failed:disk" in blob
        or "disk-low" in blob
    )


def find_open_twin(
    issues: list[dict[str, Any]] | None,
    machine: str,
) -> dict[str, Any] | None:
    for iss in issues or []:
        if is_disk_starvation_twin(iss, machine):
            return iss
    return None


def ensure_disk_starvation_issue(
    *,
    machine: str,
    nick: str = "",
    job: str = "",
    reason: str = "",
    free_gb: str | float | None = None,
    list_open: Callable[[], list[dict[str, Any]]] | None = None,
    create: Callable[..., Any] | None = None,
    comment: Callable[[int, str], Any] | None = None,
    add_labels: Callable[[int, list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Create or refresh the machine-pinned disk issue. Never raises."""
    out: dict[str, Any] = {
        "ok": False,
        "action": "skipped",
        "machine": str(machine or "").strip().lower(),
        "issue": None,
        "error": None,
    }
    mid = out["machine"]
    if not mid:
        out["error"] = "no machine"
        return out
    try:
        issues: list[dict[str, Any]] = []
        if list_open is not None:
            issues = list(list_open() or [])
        twin = find_open_twin(issues, mid)
        note = (
            f"FR #9698 disk GIVEUP/NACK refresh: seat=`{nick}` job=`{job}` "
            f"reason=`{str(reason)[:160]}`"
        )
        if twin is not None:
            num = int(twin.get("number") or 0)
            out["issue"] = num or twin.get("number")
            out["action"] = "twin_comment"
            if comment is not None and num:
                comment(num, note)
            out["ok"] = True
            return out
        if create is None:
            out["error"] = "no create"
            return out
        title = issue_title(mid)
        body = issue_body(
            machine=mid,
            nick=nick,
            job=job,
            reason=reason,
            free_gb=free_gb,
        )
        label = needs_machine_label(mid)
        # Prefer create(title, body, labels=...) when supported.
        created = None
        try:
            created = create(title, body, labels=[label, "feature-request"])
        except TypeError:
            created = create(title, body)
        num = 0
        if isinstance(created, dict):
            num = int(created.get("number") or 0)
        elif isinstance(created, int):
            num = int(created)
        out["issue"] = num or created
        out["action"] = "created"
        if add_labels is not None and num:
            with_suppress = True
            try:
                add_labels(num, [label, "feature-request"])
            except Exception:
                if not with_suppress:
                    raise
        out["ok"] = True
        return out
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out


def default_gh_hooks(
    machine: str = "",
) -> tuple[
    Callable[[], list[dict[str, Any]]],
    Callable[..., Any],
    Callable[[int, str], Any],
]:
    """Build list_open / create / comment via ``gh_filer`` (never raises)."""

    def _list_open() -> list[dict[str, Any]]:
        try:
            import json

            from gh_filer import GitHubFiler, ensure_gh_token_env

            ensure_gh_token_env()
            filer = GitHubFiler()
            mid = str(machine or "").strip().lower()
            q = f'{mid}: disk starvation' if mid else "disk starvation"
            proc = filer._run_issue(
                "list",
                "-R",
                REPO,
                "--search",
                f"{q} in:title",
                "--state",
                "open",
                "--json",
                "number,url,state,title,body",
                "--limit",
                "20",
            )
            if proc.returncode != 0:
                # Broader search
                proc = filer._run_issue(
                    "list",
                    "-R",
                    REPO,
                    "--search",
                    "disk starvation OR worktree-create-failed:disk",
                    "--state",
                    "open",
                    "--json",
                    "number,url,state,title,body",
                    "--limit",
                    "30",
                )
            if proc.returncode != 0:
                return []
            rows = json.loads(proc.stdout or "[]")
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def _create(title: str, body: str, labels: list[str] | None = None) -> Any:
        from gh_filer import GitHubFiler

        filer = GitHubFiler()
        labs = list(labels or [])
        return filer.create_issue(REPO, title, body, labs)

    def _comment(number: int, body: str) -> None:
        from gh_filer import GitHubFiler

        GitHubFiler().comment_issue(REPO, int(number), body)

    return _list_open, _create, _comment


def maybe_file_from_giveup(
    *,
    nick: str | None,
    reason: str | None,
    repo: str = "",
    task: str = "",
    ident: str = "",
    free_gb: str | float | None = None,
    list_open: Callable[[], list[dict[str, Any]]] | None = None,
    create: Callable[..., Any] | None = None,
    comment: Callable[[int, str], Any] | None = None,
    add_labels: Callable[[int, list[str]], Any] | None = None,
    use_default_gh: bool = True,
) -> dict[str, Any] | None:
    """Shop-listen hook: file when reason is disk-class. Returns None if not disk."""
    if not is_disk_starvation_reason(reason):
        return None
    mid = machine_from_seat(nick)
    job = ""
    if repo and task and ident:
        job = f"{repo} {str(task).upper()} {ident}".strip()
    elif repo or ident:
        job = f"{repo}#{str(ident).lstrip('#')}".strip("#")
    if use_default_gh and (list_open is None or create is None or comment is None):
        try:
            d_list, d_create, d_comment = default_gh_hooks(mid)
        except Exception:
            d_list = d_create = d_comment = None  # type: ignore[assignment]
        if list_open is None:
            list_open = d_list
        if create is None:
            create = d_create
        if comment is None:
            comment = d_comment
    return ensure_disk_starvation_issue(
        machine=mid,
        nick=str(nick or ""),
        job=job,
        reason=str(reason or ""),
        free_gb=free_gb,
        list_open=list_open,
        create=create,
        comment=comment,
        add_labels=add_labels,
    )
