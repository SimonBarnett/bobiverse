#!/usr/bin/env python3
"""Ensure and VERIFY the Bob git webhook on a SimonBarnett repo.

Skill: plan-bob-webhooks (orchestrator plan-git-from-plan).

    python tools/bob_git_hook.py SimonBarnett/<name>
    python tools/bob_git_hook.py SimonBarnett/<name> --replay-missed

Steps (exit 0 only when all pass):
1. Hook matches the fleet config exactly (create if absent, PATCH if it drifts):
   url https://irc.ntsa.uk/bob/v1/git, content_type json, insecure_ssl 0,
   events issues+pull_request+push, active. Other hooks are left alone.
2. A ``ping`` delivery returned 2xx (sends one if none is recorded).
3. Issues / PRs opened BEFORE the hook existed never reached Jeeves (GitHub
   does not backfill). They are replayed to the receiver as ``opened``
   events built from GitHub's own API objects. Automatic when this run
   created the hook, or with --replay-missed.
4. Jeeves' ``GIT ...`` line for the repo is seen in a local #bobiverse
   irc.log, or (replays) the item is in the digest unaccepted queue.

Secrets: fleet hooks carry NO secret (the receiver does not check HMAC).
``--secret-file`` exists for a future signed receiver; the value is read
from the file and never printed. Never type a secret on the command line.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Iterable

HOOK_URL = "https://irc.ntsa.uk/bob/v1/git"
DIGEST_URL = "https://irc.ntsa.uk/bob/v1/report"
EVENTS = ("issues", "pull_request", "push")
CONTENT_TYPE = "json"
INSECURE_SSL = "0"

GhRunner = Callable[[list, "str | None"], str]
Poster = Callable[[str, bytes, dict], int]


def fleet_hook_body(url: str = HOOK_URL, secret: str | None = None) -> dict:
    config = {"url": url, "content_type": CONTENT_TYPE, "insecure_ssl": INSECURE_SSL}
    if secret:
        config["secret"] = secret
    return {"name": "web", "active": True, "events": list(EVENTS), "config": config}


def default_gh(args: list, stdin: str | None = None) -> str:
    proc = subprocess.run(
        ["gh", "api", *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {' '.join(args[:3])} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def gh_json(gh: GhRunner, args: list, stdin: str | None = None):
    out = gh(args, stdin)
    return json.loads(out) if out.strip() else None


def hook_drift(hook: dict, url: str = HOOK_URL, want_secret: bool = False) -> list:
    """Fields where ``hook`` differs from the fleet config. Empty list = matches."""
    cfg = hook.get("config") or {}
    drift = []
    if cfg.get("url") != url:
        drift.append("url")
    if cfg.get("content_type") != CONTENT_TYPE:
        drift.append("content_type")
    if str(cfg.get("insecure_ssl", "0")) != INSECURE_SSL:
        drift.append("insecure_ssl")
    if sorted(hook.get("events") or []) != sorted(EVENTS):
        drift.append("events")
    if not hook.get("active", False):
        drift.append("active")
    # GitHub masks a set secret as "********".
    if want_secret and not cfg.get("secret"):
        drift.append("secret")
    return drift


def find_hook(hooks: Iterable, url: str = HOOK_URL):
    for h in hooks or []:
        if (h.get("config") or {}).get("url") == url:
            return h
    return None


def ensure_hook(repo: str, gh: GhRunner, url: str = HOOK_URL, secret: str | None = None):
    """Return (hook, created). Creates or PATCHes to the exact fleet config."""
    hooks = gh_json(gh, [f"repos/{repo}/hooks"]) or []
    hook = find_hook(hooks, url)
    body = json.dumps(fleet_hook_body(url, secret))
    if hook is None:
        hook = gh_json(gh, [f"repos/{repo}/hooks", "-X", "POST", "--input", "-"], body)
        return hook, True
    drift = hook_drift(hook, url, want_secret=bool(secret))
    if drift:
        hook = gh_json(gh, [f"repos/{repo}/hooks/{hook['id']}", "-X", "PATCH", "--input", "-"], body)
    return hook, False


def ok_ping(deliveries: Iterable):
    for d in deliveries or []:
        code = d.get("status_code") or 0
        if d.get("event") == "ping" and 200 <= int(code) < 300:
            return d
    return None


def wait_ping(repo: str, hook_id, gh: GhRunner, timeout: float = 60, sleep=time.sleep):
    """Return the 2xx ping delivery, sending one ping if none is recorded."""
    sent = False
    deadline = time.monotonic() + timeout
    while True:
        dels = gh_json(gh, [f"repos/{repo}/hooks/{hook_id}/deliveries?per_page=30"]) or []
        hit = ok_ping(dels)
        if hit:
            return hit
        if not sent and not any(d.get("event") == "ping" for d in dels):
            gh([f"repos/{repo}/hooks/{hook_id}/pings", "-X", "POST"], None)
            sent = True
        if time.monotonic() >= deadline:
            return None
        sleep(3)


def missed_items(items: Iterable, hook_created_at: str) -> list:
    """Open issues/PRs created before the hook existed (ISO-8601 Z strings compare)."""
    out = []
    for it in items or []:
        if it.get("state") != "open":
            continue
        if str(it.get("created_at") or "") < str(hook_created_at or ""):
            out.append(it)
    return sorted(out, key=lambda i: i.get("number") or 0)


def build_replay(item: dict, repository: dict, pull: dict | None = None):
    """(event, payload) GitHub would have sent for ``opened``."""
    if item.get("pull_request") is not None or pull is not None:
        obj = pull or item
        return "pull_request", {
            "action": "opened",
            "number": obj.get("number"),
            "pull_request": obj,
            "repository": repository,
            "sender": obj.get("user") or {},
        }
    return "issues", {
        "action": "opened",
        "issue": item,
        "repository": repository,
        "sender": item.get("user") or {},
    }


def default_post(url: str, body: bytes, headers: dict) -> int:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def post_replay(event: str, payload: dict, url: str = HOOK_URL, post: Poster = default_post) -> int:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GitHub-Hookshot/bob-git-hook-replay",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": f"replay-{uuid.uuid4()}",
    }
    return post(url, json.dumps(payload, separators=(",", ":")).encode("utf-8"), headers)


def announce_needle(event: str, repo: str, number=None, action: str = "opened") -> str:
    if event == "ping":
        return f"GIT ping {repo}"
    return f"GIT {event} {repo} {action} #{number}"


def default_log_paths() -> list:
    """Candidate #bobiverse irc.log paths (exist-check happens later).

    FR #88: the legacy ``~/.agentic-irc-bobiverse`` home often loops
    ``NICKNAME_RESERVED`` for ``bob-<machine>`` when ircBob already holds
    that NickServ account. Also consider the dedicated git-announce home
    and optional ``BOB_HOME`` / install ear logs (when ``BOB_IRC_DEBUG``).
    """
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    paths = [
        home / ".agentic-irc-bobiverse" / "irc.log",
        home / ".agentic-irc-gitannounce" / "irc.log",
        home / ".bobiverse" / "irc.log",
    ]
    bob_home = (os.environ.get("BOB_HOME") or "").strip()
    if bob_home:
        paths.append(Path(bob_home) / "irc.log")
    install = (os.environ.get("BOB_INSTALL_ROOT") or "").strip()
    if install:
        paths.append(Path(install) / "home" / "irc.log")
        paths.append(Path(install) / "bob" / "home" / "irc.log")
    return paths


def _tail_lines(path: Path, max_bytes: int = 2_000_000) -> list:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()


def announce_seen(needle: str, log_paths: Iterable) -> str | None:
    """Return the Jeeves #bobiverse line containing ``needle`` (last match)."""
    hit = None
    for p in log_paths:
        for ln in _tail_lines(Path(p)):
            if "PRIVMSG #bobiverse :" in ln and ln.startswith(":Jeeves!") and needle in ln:
                hit = ln
    return hit


def diagnose_listener_logs(log_paths: Iterable, sample: int = 200) -> str | None:
    """Return a short diagnosis when logs show a dead nick loop (FR #88).

    Does **not** relax the announce gate — callers still exit 2 until a
    real ``:Jeeves! ... PRIVMSG #bobiverse :GIT ...`` line appears.
    """
    reserved_hits = 0
    reserved_nicks: set[str] = set()
    jeeves_privmsg = 0
    scanned = 0
    for p in log_paths:
        lines = _tail_lines(Path(p))
        if not lines:
            continue
        for ln in lines[-sample:]:
            scanned += 1
            if "NICKNAME_RESERVED" in ln or (" 433 " in ln and "Nickname is reserved" in ln):
                reserved_hits += 1
                parts = ln.split()
                for i, tok in enumerate(parts):
                    if tok in ("*", "NICKNAME_RESERVED") and i + 1 < len(parts):
                        cand = parts[i + 1].lstrip(":")
                        if cand.startswith("bob-") or cand.endswith("_l"):
                            reserved_nicks.add(cand)
            if ln.startswith(":Jeeves!") and "PRIVMSG #bobiverse :" in ln:
                jeeves_privmsg += 1
    if scanned == 0:
        return None
    if jeeves_privmsg == 0 and reserved_hits >= max(5, scanned // 10):
        nicks = ", ".join(sorted(reserved_nicks)[:6]) or "bob-<machine>"
        return (
            f"NICKNAME_RESERVED loop for {nicks} — local irc.log is not joined to "
            "#bobiverse (ear NickServ nick without matching SASL, or stale agentic-irc). "
            "Start tools/Start-BobiverseGitAnnounceListen.ps1 (free nick) or pass "
            "--irc-log to a healthy log; do not weaken the announce gate."
        )
    return None


def format_announce_fail(missing: list, logs: list, listener_diag: str | None = None) -> str:
    where = ", ".join(str(p) for p in logs) or "no local #bobiverse irc.log"
    msg = (
        f"FAIL Jeeves announce not seen for: {missing} (checked {where}). "
        "Check #bobiverse; do not declare webhook setup done."
    )
    if listener_diag:
        msg += f" Listener diagnosis: {listener_diag}"
    return msg


def digest_has(repo: str, ident: str, digest: dict | None) -> bool:
    q = ((digest or {}).get("queue") or {}).get("unaccepted") or []
    return any(e.get("repo") == repo and str(e.get("id")) == ident for e in q)


def fetch_digest(url: str = DIGEST_URL) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - verification is best-effort per source
        return None


def wait_announce(needles: list, log_paths: list, timeout: float, sleep=time.sleep) -> dict:
    found: dict = {}
    deadline = time.monotonic() + timeout
    while True:
        for n in needles:
            if n not in found:
                line = announce_seen(n, log_paths)
                if line:
                    found[n] = line
        if len(found) == len(needles) or time.monotonic() >= deadline:
            return found
        sleep(3)


def main(argv=None, gh: GhRunner = default_gh, post: Poster = default_post) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", help="owner/name (bare name = SimonBarnett/<name>)")
    ap.add_argument("--replay-missed", action="store_true", help="replay items opened before the hook")
    ap.add_argument("--no-replay", action="store_true")
    ap.add_argument("--secret-file", help="optional; value read from file, never printed")
    ap.add_argument("--irc-log", action="append", help="#bobiverse irc.log to check (repeatable)")
    ap.add_argument("--timeout", type=float, default=60)
    a = ap.parse_args(argv)
    repo = a.repo if "/" in a.repo else f"SimonBarnett/{a.repo}"
    secret = None
    if a.secret_file:
        secret = Path(a.secret_file).read_text(encoding="utf-8").strip() or None

    hook, created = ensure_hook(repo, gh, secret=secret)
    drift = hook_drift(hook, want_secret=bool(secret))
    if drift:
        print(f"FAIL hook on {repo} still differs from fleet config: {drift}")
        return 1
    print(f"OK hook {hook['id']} on {repo}: {HOOK_URL} json events={','.join(EVENTS)} "
          f"secret={'set' if (hook.get('config') or {}).get('secret') else 'none (fleet standard)'}"
          f"{' (created)' if created else ''}")

    ping = wait_ping(repo, hook["id"], gh, timeout=a.timeout)
    if not ping:
        print(f"FAIL no 2xx ping delivery for hook {hook['id']} within {a.timeout:.0f}s")
        return 1
    print(f"OK ping delivery {ping.get('id')} -> {ping.get('status_code')}")

    needles = [announce_needle("ping", repo)]
    replayed: list = []
    if (created or a.replay_missed) and not a.no_replay:
        repository = gh_json(gh, [f"repos/{repo}"]) or {}
        items = gh_json(gh, [f"repos/{repo}/issues?state=open&per_page=100"]) or []
        for it in missed_items(items, hook.get("created_at", "")):
            pull = None
            if it.get("pull_request") is not None:
                pull = gh_json(gh, [f"repos/{repo}/pulls/{it['number']}"])
            event, payload = build_replay(it, repository, pull)
            code = post_replay(event, payload, post=post)
            print(f"{'OK' if 200 <= code < 300 else 'FAIL'} replay {event} opened #{it['number']} -> {code}")
            if not 200 <= code < 300:
                return 1
            replayed.append((event, it["number"]))
            needles.append(announce_needle(event, repo, it["number"]))

    logs = [Path(p) for p in (a.irc_log or [])] or default_log_paths()
    logs = [p for p in logs if p.is_file()]
    found = wait_announce(needles, logs, 0) if logs else {}
    if logs and needles[0] not in found:
        # Old hook: its ping line may be long gone from the log. One fresh ping.
        gh([f"repos/{repo}/hooks/{hook['id']}/pings", "-X", "POST"], None)
    if logs and len(found) < len(needles):
        found = wait_announce(needles, logs, a.timeout)
    missing = [n for n in needles if n not in found]
    for n, line in found.items():
        print(f"OK Jeeves: {line[line.index('GIT '):][:160]}")
    if missing and replayed:
        digest = fetch_digest()
        for event, num in replayed:
            n = announce_needle(event, repo, num)
            if n in missing and digest_has(repo, f"#{num}", digest):
                print(f"OK digest queue has {repo} #{num} (Jeeves announced it; no local irc.log line)")
                missing.remove(n)
    if missing:
        diag = diagnose_listener_logs(logs) if logs else None
        print(format_announce_fail(missing, logs, diag))
        return 2
    print(f"DONE {repo} webhook wired and announced by Jeeves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
