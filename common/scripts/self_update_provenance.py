"""FR #8112: refuse self-update that would replace a newer hotpatched build.

A hotpatched install (BUILD.json commit from main) must not be overwritten by a
release whose source commit does not contain that SHA. Used by
``Update-BobiverseService.ps1`` for bob / airc / jeeves.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SHA_RX = re.compile(r"^[0-9a-fA-F]{7,40}$")


def normalize_sha(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if _SHA_RX.fullmatch(raw):
        return raw
    return ""


def read_installed_commit(install_root: Path | str) -> str:
    """Return the installed source commit from BUILD.json (or empty)."""
    root = Path(install_root)
    build = root / "BUILD.json"
    if not build.is_file():
        return ""
    try:
        data = json.loads(build.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("commit_full", "commit", "source_commit", "git_commit"):
        sha = normalize_sha(data.get(key))
        if sha:
            return sha
    return ""


def decide_update_vs_hotpatch(
    *,
    installed_sha: str,
    candidate_sha: str,
    ancestry: str | None,
) -> tuple[bool, str]:
    """Return ``(allow_update, reason)``.

    ``ancestry`` is GitHub compare status for ``installed...candidate``
    (head = candidate relative to base = installed):

    - ``ahead`` / ``identical`` → allow (release contains or equals installed)
    - ``behind`` → refuse (release is an ancestor of the hotpatch)
    - ``diverged`` / unknown → refuse (no automatic downgrade)
    """
    inst = normalize_sha(installed_sha)
    cand = normalize_sha(candidate_sha)
    if not inst:
        return False, "unknown-installed-provenance"
    if not cand:
        return False, "unknown-candidate-provenance"
    if inst == cand:
        return True, "identical"
    status = str(ancestry or "").strip().lower()
    if status in ("ahead", "identical"):
        return True, status or "identical"
    if status == "behind":
        return False, "candidate-behind-installed"
    if status == "diverged":
        return False, "diverged"
    return False, "unknown-ancestry"


def format_skip_log(
    *,
    installed_sha: str,
    candidate_sha: str,
    reason: str,
) -> str:
    """One-line Check log fragment (no secrets)."""
    return (
        "check result=skipped-hotpatch-newer "
        "installed_sha=%s candidate_sha=%s reason=%s"
        % (
            normalize_sha(installed_sha) or "unknown",
            normalize_sha(candidate_sha) or "unknown",
            str(reason or "unknown").strip() or "unknown",
        )
    )


def _cmd_read(argv: list[str]) -> int:
    if not argv:
        return 2
    sha = read_installed_commit(argv[0])
    sys.stdout.write(sha)
    return 0


def _cmd_decide(argv: list[str]) -> int:
    """decide <installed> <candidate> <ancestry> -> JSON allow/reason/log."""
    if len(argv) < 3:
        return 2
    allow, reason = decide_update_vs_hotpatch(
        installed_sha=argv[0],
        candidate_sha=argv[1],
        ancestry=argv[2],
    )
    payload = {
        "allow": bool(allow),
        "reason": reason,
        "log": format_skip_log(
            installed_sha=argv[0],
            candidate_sha=argv[1],
            reason=reason,
        ),
    }
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return 2
    cmd, rest = args[0], args[1:]
    if cmd == "read":
        return _cmd_read(rest)
    if cmd == "decide":
        return _cmd_decide(rest)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
