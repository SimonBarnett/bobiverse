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

from _common import EXIT_FINDING, EXIT_OK, find_upward_file, run_check

DEFAULT_INTAKE_URL = "https://bob.ntsa.uk/bob/v1/intake"
# Must stay aligned with common/scripts/intake.py DEFAULT_ALLOW_REPOS (FR #3023 / #3050 / #3117).
REQUIRED_ALLOW_REPOS = (
    "SimonBarnett/bobiverse",
    "SimonBarnett/skills-visionary",
    "SimonBarnett/priority-mcp",
    "SimonBarnett/a-search",
    "SimonBarnett/trutex",
)
_PROBE_TITLE = "do-not-file probe-do-not-file intake-allowlist-monitor"
_PROBE_BODY = "probe-shape-only intake_allowlist monitor; discard"
_HTTP_TIMEOUT_S = 20.0
# FR #8861: bob.ntsa.uk is behind Cloudflare; Python-urllib's default UA gets
# HTTP 403 "error code: 1010". That is not repo_not_allowed.
_PROBE_USER_AGENT = "BobiverseIntakeAllowlist/1.0 (+https://github.com/SimonBarnett/bobiverse)"


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
    """Best-effort locate common/scripts/intake.py from install or repo layout.

    FR #8580: walk upward instead of ``parents[N]`` (shallow ``J:\\tools\\monitor``).
    """
    env = (os.environ.get("BOB_INTAKE_PY") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_file() else None
    roots: list[Path] = []
    if start is not None:
        roots.append(Path(start))
    roots.append(Path(__file__).resolve().parent)
    for root in roots:
        found = find_upward_file(root, "common", "scripts", "intake.py")
        if found is not None:
            return found
        found = find_upward_file(root, "scripts", "intake.py")
        if found is not None:
            return found
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


def _classify_http_result(status: int, body: str, *, reason: str = "") -> dict[str, Any]:
    """FR #9100 / #8861: denial only when status is 403 and JSON error is repo_not_allowed.

    Every other non-2xx (Cloudflare HTML 403, empty route-gate 403, 5xx even with
    a misleading JSON error string) is ``probe_error``. 2xx is allowed.
    """
    err = ""
    try:
        parsed = json.loads(body) if body else {}
        if isinstance(parsed, dict):
            err = str(parsed.get("error") or "")
    except json.JSONDecodeError:
        parsed = {}
    status_i = int(status)
    if 200 <= status_i < 300:
        return {
            "http_status": status_i,
            "error": err,
            "allowed": True,
        }
    if status_i == 403 and err == "repo_not_allowed":
        return {
            "http_status": status_i,
            "error": err,
            "allowed": False,
        }
    snippet = (body or "").strip().replace("\n", " ")[:120]
    detail = snippet or err or reason or "error"
    return {
        "http_status": status_i,
        "error": f"http_{status_i}:{detail}",
        "allowed": False,
        "probe_error": True,
    }


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
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": _PROBE_USER_AGENT,
            "Accept": "application/json",
        },
        method="POST",
    )
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=_HTTP_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", None) or resp.getcode()
            row = _classify_http_result(int(status), body)
            row["repo"] = repo
            return row
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        row = _classify_http_result(int(e.code), body, reason=str(e.reason or ""))
        row["repo"] = repo
        return row
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

    has_denial = any(
        (not p.get("probe_error")) and (not p.get("allowed")) for p in probes
    )
    has_probe_err = any(p.get("probe_error") for p in probes)
    remediation_parts: list[str] = []
    if has_denial:
        remediation_parts.append(
            "JSON error=repo_not_allowed: confirm common/scripts/intake.py repo_allowed / "
            "SimonBarnett owner gate (FR #3135) and Sync/compose ircJeeves on the chair."
        )
    if has_probe_err:
        remediation_parts.append(
            "HTTP error without repo_not_allowed JSON (e.g. Cloudflare 1010 or the route "
            "gate's empty 403): probe blocked before intake. Not allowlist drift. Do not "
            "Sync (FR #8861 / #9100)."
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
            "remediation": " ".join(remediation_parts),
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
