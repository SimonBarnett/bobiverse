"""FR #213: warn when a live service checkout is off main or has a fresh stash.

MRB/FR workers must never `git checkout` / `stash` / `reset` in trees that
`irc_agent` and monitors load from (e.g. D:\\ai\\agentic_irc). This module
only *inspects* a tree at process start and records warnings + a report file.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

EXPECTED_BRANCH = "main"
START_MARKER = ".agentic-irc-service-start"
WARN_REPORT = "service-tree-warn.json"


@dataclass
class LiveTreeSnapshot:
    path: str
    branch: str = ""
    dirty: bool = False
    status_porcelain: str = ""
    stash_refs: list[str] = field(default_factory=list)
    newest_stash_unix: float | None = None
    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    error: str = ""


def _git(cwd: Path, *args: str, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def resolve_service_tree(explicit: str | Path | None = None) -> Path | None:
    """Locate the service checkout: env, explicit path, or scripts/ parent."""
    if explicit is not None and str(explicit).strip():
        raw: str | Path = explicit
    else:
        raw = (os.environ.get("AGENTIC_IRC_SERVICE_TREE") or "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
        return p if (p / ".git").exists() or (p / ".git").is_file() else None
    here = Path(__file__).resolve().parent.parent
    if (here / ".git").exists() or (here / ".git").is_file():
        return here
    return None


def _is_git_repo(path: Path) -> bool:
    r = _git(path, "rev-parse", "--is-inside-work-tree")
    return r.returncode == 0 and "true" in (r.stdout or "").lower()


def read_branch(path: Path) -> str:
    r = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    if r.returncode != 0:
        return ""
    return (r.stdout or "").strip()


def read_status_porcelain(path: Path) -> str:
    r = _git(path, "status", "--porcelain")
    if r.returncode != 0:
        return ""
    return r.stdout or ""


def list_stash_meta(path: Path) -> list[tuple[str, float]]:
    """Return (ref_name, committer_unix) for each stash entry, newest first."""
    r = _git(
        path,
        "for-each-ref",
        "--sort=-committerdate",
        "--format=%(refname)|%(committerdate:unix)",
        "refs/stash",
    )
    if r.returncode != 0:
        # no stash ref is fine
        return []
    out: list[tuple[str, float]] = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        ref, ts = line.split("|", 1)
        try:
            out.append((ref.strip(), float(ts.strip())))
        except ValueError:
            continue
    # also walk stash@{n} via log if for-each-ref only shows tip
    r2 = _git(path, "stash", "list", "--format=%gd|%ct")
    if r2.returncode == 0 and (r2.stdout or "").strip():
        seen = {a for a, _ in out}
        for line in r2.stdout.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            ref, ts = line.split("|", 1)
            ref = ref.strip()
            try:
                tsf = float(ts.strip())
            except ValueError:
                continue
            if ref not in seen:
                out.append((ref, tsf))
                seen.add(ref)
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def read_last_start_unix(home: Path | None) -> float | None:
    if home is None:
        return None
    marker = home / START_MARKER
    if not marker.is_file():
        return None
    try:
        raw = marker.read_text(encoding="utf-8").strip()
        return float(raw.split()[0])
    except (OSError, ValueError, IndexError):
        try:
            return marker.stat().st_mtime
        except OSError:
            return None


def write_start_marker(home: Path | None, when: float | None = None) -> None:
    if home is None:
        return
    home.mkdir(parents=True, exist_ok=True)
    ts = float(when if when is not None else time.time())
    (home / START_MARKER).write_text(f"{ts:.3f}\n", encoding="utf-8", newline="\n")


def inspect_live_tree(
    tree: Path | None,
    *,
    home: Path | None = None,
    expected_branch: str = EXPECTED_BRANCH,
    now: float | None = None,
) -> LiveTreeSnapshot:
    """Inspect tree; never mutates git state."""
    if tree is None:
        return LiveTreeSnapshot(path="", ok=True, error="no service tree")
    path = Path(tree).resolve()
    snap = LiveTreeSnapshot(path=str(path))
    if not path.is_dir() or not _is_git_repo(path):
        snap.ok = True
        snap.error = "not a git work tree"
        return snap
    snap.branch = read_branch(path)
    snap.status_porcelain = read_status_porcelain(path)
    snap.dirty = bool(snap.status_porcelain.strip())
    stashes = list_stash_meta(path)
    snap.stash_refs = [r for r, _ in stashes]
    if stashes:
        snap.newest_stash_unix = stashes[0][1]

    if snap.branch and snap.branch != expected_branch:
        snap.ok = False
        snap.warnings.append(
            f"service tree branch is {snap.branch!r} (expected {expected_branch!r}) path={path}"
        )

    last_start = read_last_start_unix(home)
    tnow = float(now if now is not None else time.time())
    if snap.newest_stash_unix is not None and last_start is not None:
        if snap.newest_stash_unix > last_start:
            snap.ok = False
            snap.warnings.append(
                f"stash newer than last service start "
                f"(stash_ts={snap.newest_stash_unix:.0f} start_ts={last_start:.0f}) path={path}"
            )
    elif snap.newest_stash_unix is not None and last_start is None:
        # first start with an existing stash: warn once so ops see leftover worker stash
        snap.ok = False
        snap.warnings.append(
            f"service tree has stash but no prior start marker path={path}"
        )

    return snap


def write_warn_report(home: Path | None, snap: LiveTreeSnapshot, *, role: str = "irc_agent") -> Path | None:
    if home is None or not snap.warnings:
        return None
    home.mkdir(parents=True, exist_ok=True)
    dest = home / WARN_REPORT
    body = {
        "role": role,
        "ts": time.time(),
        "snapshot": asdict(snap),
    }
    dest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8", newline="\n")
    return dest


def check_and_report(
    *,
    tree: Path | str | None = None,
    home: Path | str | None = None,
    role: str = "irc_agent",
    log: Callable[[str], None] | None = None,
    expected_branch: str = EXPECTED_BRANCH,
    mark_start: bool = True,
) -> LiveTreeSnapshot:
    """Startup entry: inspect, log warnings, write report, refresh start marker."""
    log_fn = log or (lambda m: None)
    tree_p = resolve_service_tree(tree)
    home_p = Path(home).expanduser().resolve() if home else None
    snap = inspect_live_tree(tree_p, home=home_p, expected_branch=expected_branch)
    for w in snap.warnings:
        log_fn(f"WARN live-tree {w}")
    if snap.warnings:
        write_warn_report(home_p, snap, role=role)
        log_fn(f"WARN live-tree report written role={role}")
    if mark_start and home_p is not None:
        write_start_marker(home_p)
    return snap


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="FR #213 live service tree guard")
    p.add_argument("--tree", default="", help="service checkout (default: env or repo root)")
    p.add_argument("--home", default="", help="AGENTIC_IRC_HOME for start marker + report")
    p.add_argument("--role", default="cli")
    p.add_argument("--no-mark-start", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    def _log(m: str) -> None:
        print(m, flush=True)

    snap = check_and_report(
        tree=args.tree or None,
        home=args.home or None,
        role=args.role,
        log=_log,
        mark_start=not args.no_mark_start,
    )
    if args.json:
        print(json.dumps(asdict(snap), indent=2))
    return 0 if snap.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
