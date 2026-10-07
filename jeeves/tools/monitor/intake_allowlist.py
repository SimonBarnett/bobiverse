#!/usr/bin/env python3
"""Live intake allow-rule drift check (FR #3117 / FR #3135).

Probes POST /bob/v1/intake with do-not-file titles for each required repo.
HTTP 403 error=repo_not_allowed means the live ircJeeves allow rule drifted
behind common/scripts/intake.py (usually missing Sync/compose after an allow
PR). FR #3135: source must expose repo_allowed / SimonBarnett owner gate.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from _common import EXIT_FINDING, EXIT_OK, run_check

DEFAULT_INTAKE_URL = "https://irc.ntsa.uk/bob/v1/intake"
# Must stay aligned with common/scripts/intake.py DEFAULT_ALLOW_REPOS (FR #3023 / #3050 / #3117).
REQUIRED_ALLOW_REPOS = (
    "SimonBarnett/bobiverse",
    "SimonBarnett/skills-visionary",
    "SimonBarnett/agentic_fomprep",
    "SimonBarnett/a-search",
    "SimonBarnett/trutex",
)
_PROBE_TITLE = "do-not-file probe-do-not-file intake-allowlist-monitor"
_PROBE_BODY = "probe-shape-only intake_allowlist monitor; discard"
_HTTP_TIMEOUT_S = 20.0


def intake_url() -> str:
    raw = (os.environ.get("BOB_INTAKE_URL") or "").strip()
    return raw or DEFAULT_INTAKE_URL


def required_repos() -> tuple[str, ...]:
    raw = (os.environ.get("BOB_INTAKE_REQUIRED_REPOS") or "").strip()
    if not raw:
        return REQUIRED_ALLOW_REPOS
    parts = tuple(p.strip() for p in raw.split(",") if p.strip())
    return parts or REQUIRED_ALLOW_REPOS


def find_intake_py(start: Optional[Path] = None) -> Optional[Path]:
    """Best-effort locate common/scripts/intake.py from install or repo layout."""
    env = (os.environ.get("BOB_INTAKE_PY") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_file() else None
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "common" / "scripts" / "intake.py",  # repo/jeeves/tools/monitor
        here.parents[2] / "common" / "scripts" / "intake.py",
        here.parents[2] / "scripts" / "intake.py",  # composed flat under install
    ]
    if start is not None:
        candidates.insert(0, Path(start) / "common" / "scripts" / "intake.py")
        candidates.insert(1, Path(start) / "scripts" / "intake.py")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def parse_default_allow_repos(text: str) -> set[str]:
    """Extract string literals inside DEFAULT_ALLOW_REPOS = frozenset({...})."""
    m = re.search(
        r"DEFAULT_ALLOW_REPOS\s*=\s*frozenset\s*\(\s*\{(.*?)\}\s*\)",
        text,
        flags=re.DOTALL,
    )
    if not m:
        return set()
    return set(re.findall(r'"([^"]+/[^"]+)"', m.group(1)))


def probe_repo(
    url: str,
    repo: str,
    opener: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """POST a do-not-file probe; return status/error shape (no secrets)."""
    payload = {
        "repo": repo,
        "kind": "harvest",
        "title": _PROBE_TITLE,
        "body": _PROBE_BODY,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=_HTTP_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", None) or resp.getcode()
            err = ""
            try:
                parsed = json.loads(body) if body else {}
                if isinstance(parsed, dict):
                    err = str(parsed.get("error") or "")
            except json.JSONDecodeError:
                parsed = {}
            return {
                "repo": repo,
                "http_status": int(status),
                "error": err,
                "allowed": int(status) != 403,
            }
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        err = ""
        try:
            parsed = json.loads(body) if body else {}
            if isinstance(parsed, dict):
                err = str(parsed.get("error") or "")
        except json.JSONDecodeError:
            parsed = {}
        if not err and e.code == 403:
            err = "repo_not_allowed"
        return {
            "repo": repo,
            "http_status": int(e.code),
            "error": err,
            "allowed": int(e.code) != 403,
        }
    except Exception as e:
        return {
            "repo": repo,
            "http_status": 0,
            "error": f"{type(e).__name__}: {e}",
            "allowed": False,
            "probe_error": True,
        }


def check(args, opener: Optional[Callable[..., Any]] = None):
    findings: list[str] = []
    url = intake_url()
    required = required_repos()
    source_path = find_intake_py()
    source_repos: set[str] = set()
    source_ok = True
    if source_path is not None:
        try:
            text = source_path.read_text(encoding="utf-8-sig")
            source_repos = parse_default_allow_repos(text)
            # FR #3135: prefer owner-gate helper; keep example DEFAULT_ALLOW_REPOS as docs.
            if "def repo_allowed" not in text and "repo_allowed(" not in text:
                source_ok = False
                findings.append("source intake.py missing repo_allowed (FR #3135)")
            if "simonbarnett" not in text.lower():
                source_ok = False
                findings.append("source intake.py missing SimonBarnett owner gate")
            missing_src = [r for r in required if r not in source_repos]
            if missing_src and "def repo_allowed" not in text:
                source_ok = False
                findings.append(
                    "source DEFAULT_ALLOW_REPOS missing: " + ", ".join(missing_src)
                )
        except OSError as e:
            source_ok = False
            findings.append(f"source intake.py unreadable: {e}")
    else:
        # Offline/unit hosts may lack the tree; live probe still runs.
        source_path = None

    probes: list[dict[str, Any]] = []
    for repo in required:
        row = probe_repo(url, repo, opener=opener)
        probes.append(row)
        if row.get("probe_error"):
            findings.append(f"probe error {repo}: {row.get('error')}")
            continue
        if not row.get("allowed"):
            err = row.get("error") or "repo_not_allowed"
            findings.append(
                f"live intake 403 {err} for {repo} (Sync/compose ircJeeves after allowlist PR)"
            )

    ok = not findings
    return (
        {
            "ok": ok,
            "intake_url": url,
            "required": list(required),
            "source_path": str(source_path) if source_path else "",
            "source_ok": source_ok,
            "source_repos": sorted(source_repos),
            "probes": probes,
            "findings": findings,
            "remediation": (
                "Confirm common/scripts/intake.py DEFAULT_ALLOW_REPOS; "
                "on ionos run Sync-BobiverseFromRepo (or service restart compose) "
                "so live ircJeeves picks up the allowlist."
            ),
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "intake_allowlist",
        "Live intake allowlist drift (exit 0 ok / 1 finding / 2 error) — FR #3117",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
