"""FR #3928: MRB merge gate — owner hold blocks merge; require posted MRB PASS board.

Workers call ``evaluate_merge_gate`` (pure) or ``assert_mrb_merge_allowed`` (live GitHub)
before ``gh pr merge``. Chair offer skip lives in ``gitclaim.pr_hold_reason`` /
``mrb_row_offerable``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

# Owner/member hold comments (class of a-search#1334 Simon hold).
HOLD_TEXT_RE = re.compile(
    r"(?i)(?:\bon\s+hold\b|\bmust\s+not\s+merge\b|\bdo\s+not\s+merge\b|"
    r"\bhold(?:ing)?\s+(?:this\s+)?(?:pr|pull(?:\s+request)?)\b)"
)
HOLD_CLEAR_RE = re.compile(
    r"(?i)(?:\b(?:off|lift(?:ed)?|clear(?:ed)?|release(?:d)?)\s+hold\b|"
    r"\bhold\s+(?:is\s+)?(?:lifted|cleared|released|off)\b|"
    r"\bok\s+to\s+merge\b|\bclear(?:ed)?\s+to\s+merge\b)"
)
MRB_PASS_BOARD_RE = re.compile(
    r"(?i)##\s*MRB\s+board[\s\S]{0,400}?\*\*Verdict:\*\*\s*PASS\b"
)
OWNERISH = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def _assoc(c: dict) -> str:
    return str(c.get("author_association") or c.get("authorAssociation") or "").upper()


def _body(c: dict) -> str:
    return str(c.get("body") or "")


def _created(c: dict) -> str:
    return str(c.get("created_at") or c.get("createdAt") or "")


def find_active_owner_hold(comments: list[dict] | None) -> str | None:
    """Return hold snippet if an ownerish hold is active (not cleared later)."""
    ordered = sorted(list(comments or []), key=_created)
    hold_body: str | None = None
    for c in ordered:
        if _assoc(c) not in OWNERISH:
            continue
        text = _body(c)
        if HOLD_CLEAR_RE.search(text):
            hold_body = None
            continue
        if HOLD_TEXT_RE.search(text):
            hold_body = text.strip().splitlines()[0][:240]
    return hold_body


def find_mrb_pass_board(comments: list[dict] | None) -> str | None:
    """Return first comment body that looks like an MRB PASS board."""
    for c in comments or []:
        text = _body(c)
        if MRB_PASS_BOARD_RE.search(text):
            return text.strip().splitlines()[0][:240]
    return None


def evaluate_merge_gate(comments: list[dict] | None) -> tuple[bool, str]:
    """Pure gate: (ok, reason). reason empty when ok."""
    hold = find_active_owner_hold(comments)
    if hold:
        return False, f"owner hold active: {hold}"
    board = find_mrb_pass_board(comments)
    if not board:
        return False, "no MRB PASS board comment posted yet"
    return True, ""


def _gh_token() -> str:
    return (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()


def fetch_issue_comments(repo: str, num: str, *, token: str | None = None) -> list[dict]:
    """GET /repos/{repo}/issues/{num}/comments (PRs share the issues comments API)."""
    tok = (token if token is not None else _gh_token()).strip()
    if not tok:
        raise RuntimeError("GH_TOKEN/GITHUB_TOKEN required for live merge gate")
    api = f"https://api.github.com/repos/{repo}/issues/{str(num).lstrip('#')}/comments?per_page=100"
    req = urllib.request.Request(
        api,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-mrb-merge-gate",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub comments HTTP {e.code} for {repo}#{num}") from e
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected comments payload for {repo}#{num}")
    return [c for c in data if isinstance(c, dict)]


def assert_mrb_merge_allowed(repo: str, num: str, *, token: str | None = None) -> None:
    """Raise RuntimeError when merge must be refused."""
    comments = fetch_issue_comments(repo, num, token=token)
    ok, reason = evaluate_merge_gate(comments)
    if not ok:
        raise RuntimeError(f"FR #3928 merge refused for {repo}#{num}: {reason}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] in {"-h", "--help"}:
        sys.stderr.write(
            "usage: mrb_merge_gate.py <owner/repo> <pr-number>\n"
            "Exit 0 when merge allowed; 2 when refused; 1 on error.\n"
        )
        return 1
    repo, num = args[0], args[1]
    try:
        assert_mrb_merge_allowed(repo, num)
    except RuntimeError as e:
        msg = str(e)
        if msg.startswith("FR #3928 merge refused"):
            sys.stderr.write(msg + "\n")
            return 2
        sys.stderr.write(msg + "\n")
        return 1
    sys.stdout.write(f"ok: merge allowed for {repo}#{num}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
