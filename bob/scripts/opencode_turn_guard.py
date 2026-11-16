"""FR #7739: report an OpenCode hard-ceiling kill, and stop a dead job.

A ceiling kill used to only print ``opencode-watchdog: kill reason=``. A job
that Jeeves gave up or that was closed kept running until the 30 minute
ceiling, and finish recovery could still open a PR for that closed issue.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_FILED: set[str] = set()


def ceiling_sig(machine: str, nick: str, job: str) -> str:
    """One dedupe key per machine, seat, and job."""
    return f"oc-ceiling|{machine}|{nick}|{job}|hard-ceiling"[:128]


def report_opencode_hard_ceiling(
    machine: str,
    nick: str,
    job: str,
    elapsed_ms: int,
    reason: str,
    filer_post=None,
) -> dict:
    """Post one intake report. A second call with the same key is a no-op."""
    sig = ceiling_sig(machine, nick, job)
    if sig in _FILED:
        return {"posted": False, "skipped": True, "sig": sig}
    title = "bug: OpenCode hard-ceiling kill"
    body = (
        "what: opencode watchdog killed a turn at the hard ceiling\n"
        f"machine: {machine}\n"
        f"seat: {nick}\n"
        f"job: {job}\n"
        f"elapsed_ms: {int(elapsed_ms)}\n"
        f"reason: {reason}\n"
    )
    post = filer_post if filer_post is not None else _post_crash
    post(title, body, repo="SimonBarnett/bobiverse", sig=sig, exe="opencode-watchdog")
    _FILED.add(sig)
    return {"posted": True, "skipped": False, "sig": sig}


def report_opencode_capture_read(message: str, *, reporter=None) -> dict:
    """FR #7899: one auto-report when the capture file cannot be read. No file body."""
    text = " ".join(str(message or "opencode capture read failed").split())[:240]
    if reporter is None:
        here = Path(__file__).resolve()
        common = here.parent.parent.parent / "common" / "scripts"
        if common.is_dir() and str(common) not in sys.path:
            sys.path.insert(0, str(common))
        import runtime_failure

        reporter = runtime_failure.report_message
    reporter("bob-worker", text, site="opencode-capture-read")
    return {"ok": True, "message": text}


def _post_crash(title: str, body: str, *, repo: str, sig: str, exe: str) -> None:
    here = Path(__file__).resolve()
    common = here.parents[2] / "common" / "scripts"
    if str(common) not in sys.path:
        sys.path.insert(0, str(common))
    import crash_report

    crash_report._post_intake(title, body, repo=repo, sig=sig, exe=exe)


def opencode_turn_stop_reason(issue_state: str, outbox_text: str, job_key: str) -> str:
    """Why an in-flight OpenCode turn should end, or ``""`` to keep going.

    ``closed`` when the issue state is CLOSED. ``giveup`` when the outbox has
    GIVEUP or CANCEL for this job. ``reassigned`` when the outbox has an ASSIGN
    for a different job. Anything else keeps the turn.
    """
    if str(issue_state or "").strip().upper() == "CLOSED":
        return "closed"
    key = " ".join(str(job_key or "").split())
    if not key:
        return ""
    for raw in (outbox_text or "").splitlines():
        line = raw.strip()
        # Seat outbox lines are PRIVMSG #shop :GIVEUP FR owner/repo#N
        if line.upper().startswith("PRIVMSG ") and " :" in line:
            line = line.split(" :", 1)[1].strip()
        up = line.upper()
        if up.startswith("GIVEUP ") and key in line:
            return "giveup"
        if up.startswith("CANCEL ") and key in line:
            return "giveup"
        if up.startswith("ASSIGN ") and "#" in line and key not in line:
            return "reassigned"
    return ""


def opencode_issue_is_open(repo: str, number: str, run=None) -> bool:
    """False only when ``gh`` reports state CLOSED. A gh failure stays open."""
    import subprocess

    run = subprocess.run if run is None else run
    try:
        result = run(
            ["gh", "issue", "view", str(number), "--repo", repo, "--json", "state"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return True
    if getattr(result, "returncode", 1) != 0:
        return True
    try:
        state = json.loads(result.stdout or "{}").get("state") or ""
    except (json.JSONDecodeError, AttributeError, TypeError):
        return True
    return str(state).upper() != "CLOSED"


def _read_outbox(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _issue_state(job_key: str) -> str:
    """CLOSED or ``""``. A parse miss or a gh failure is not closed."""
    import re

    m = re.search(
        r"(?i)\b(?:FR|MRB|UAT|FIX)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b",
        job_key or "",
    )
    if not m:
        return ""
    if opencode_issue_is_open(m.group(1), m.group(2)):
        return ""
    return "CLOSED"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="opencode_turn_guard")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("ceiling")
    c.add_argument("--machine", default="")
    c.add_argument("--nick", default="")
    c.add_argument("--job", default="")
    c.add_argument("--elapsed-ms", type=int, default=0)
    c.add_argument("--reason", default="hard ceiling")
    s = sub.add_parser("stop")
    s.add_argument("--job", default="")
    s.add_argument("--outbox", default="")
    s.add_argument("--issue-state", default="")
    cap = sub.add_parser("capture-failed")
    cap.add_argument("--message", default="opencode capture read failed")
    args = p.parse_args(argv)
    if args.cmd == "capture-failed":
        try:
            report_opencode_capture_read(args.message)
        except Exception as exc:  # noqa: BLE001
            print(f"capture-report-failed {type(exc).__name__}")
            return 0
        print("capture-reported")
        return 0
    if args.cmd == "ceiling":
        try:
            report_opencode_hard_ceiling(
                args.machine, args.nick, args.job, args.elapsed_ms, args.reason
            )
        except Exception as exc:  # noqa: BLE001
            print(f"ceiling-report-failed {type(exc).__name__}")
            return 0
        print("ceiling-reported")
        return 0
    state = args.issue_state or _issue_state(args.job)
    reason = opencode_turn_stop_reason(state, _read_outbox(args.outbox), args.job)
    print(f"stop {reason}" if reason else "continue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
