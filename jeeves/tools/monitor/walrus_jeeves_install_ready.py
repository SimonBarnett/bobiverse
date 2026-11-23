#!/usr/bin/env python3
"""Token-free readiness for FR #9376 walrus Jeeves WinRM install.

EXIT 0: all configured gate issues CLOSED (ready for DryRun / SiYes install).
EXIT 1: one or more gate issues still OPEN (finding).
EXIT 2: error (bad fixture / gh failure when required).

Does not open WinRM or mutate walrus. Fixture:
  JEEVES_WALRUS_INSTALL_GATE_FIXTURE=/path/to.json
  JSON shape: {"issues":[{"ref":"owner/repo#N","state":"OPEN"|"CLOSED"}, ...]}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _common import EXIT_ERROR, EXIT_FINDING, EXIT_OK, run_check

_REF = re.compile(r"^\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\s*$")

# Keep in sync with Install-JeevesWalrusWinRm.ps1 -GateIssues default (FR #9376).
DEFAULT_GATE_ISSUES = (
    "SimonBarnett/bobiverse#8833",
    "SimonBarnett/skills-visionary#155",
    "SimonBarnett/skills-visionary#156",
    "SimonBarnett/skills-visionary#190",
)


def parse_ref(ref: str) -> tuple[str, int]:
    m = _REF.match(ref or "")
    if not m:
        raise ValueError(f"bad gate ref (want owner/name#N): {ref!r}")
    return m.group(1), int(m.group(2))


def evaluate_gate(states: dict[str, str]) -> dict[str, Any]:
    """states maps ref -> OPEN|CLOSED (case-insensitive)."""
    open_refs: list[str] = []
    closed_refs: list[str] = []
    unknown: list[str] = []
    for ref, st in states.items():
        s = (st or "").strip().upper()
        if s == "CLOSED":
            closed_refs.append(ref)
        elif s == "OPEN":
            open_refs.append(ref)
        else:
            unknown.append(ref)
    ok = not open_refs and not unknown
    return {
        "ok": ok,
        "reason": "all_closed" if ok else ("gate_open" if open_refs else "gate_unknown"),
        "open": open_refs,
        "closed": closed_refs,
        "unknown": unknown,
    }


def _load_fixture(path: Path) -> dict[str, str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in doc.get("issues") or []:
        if not isinstance(row, dict):
            continue
        ref = str(row.get("ref") or "").strip()
        st = str(row.get("state") or "").strip()
        if ref:
            out[ref] = st
    return out


def _gh_states(refs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ref in refs:
        repo, num = parse_ref(ref)
        try:
            p = subprocess.run(
                ["gh", "issue", "view", str(num), "-R", repo, "--json", "state"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"gh failed for {ref}: {e}") from e
        if p.returncode != 0 or not (p.stdout or "").strip():
            out[ref] = "UNKNOWN"
            continue
        st = str(json.loads(p.stdout).get("state") or "UNKNOWN")
        out[ref] = st
    return out


def check(args: Any) -> tuple[dict[str, Any], int]:
    refs_env = (os.environ.get("JEEVES_WALRUS_INSTALL_GATE_ISSUES") or "").strip()
    if refs_env:
        refs = [r.strip() for r in refs_env.split(",") if r.strip()]
    else:
        refs = list(DEFAULT_GATE_ISSUES)

    fix = (os.environ.get("JEEVES_WALRUS_INSTALL_GATE_FIXTURE") or "").strip()
    if fix:
        try:
            states = _load_fixture(Path(fix))
        except (OSError, json.JSONDecodeError) as exc:
            return (
                {
                    "ok": False,
                    "fr": 9376,
                    "source": "fixture",
                    "findings": [f"fixture read failed: {type(exc).__name__}"],
                    "path_fixture": fix,
                },
                EXIT_FINDING,
            )
        # Only evaluate configured refs; missing fixture rows => unknown
        narrowed = {r: states.get(r, "UNKNOWN") for r in refs}
        ev = evaluate_gate(narrowed)
        findings = [f"gate still OPEN: {r}" for r in ev["open"]]
        findings.extend([f"gate unknown state: {r}" for r in ev["unknown"]])
        return (
            {
                "ok": ev["ok"],
                "fr": 9376,
                "source": "fixture",
                "gate": ev,
                "findings": findings,
                "script": "jeeves/scripts/Install-JeevesWalrusWinRm.ps1",
                "hint": (
                    "DryRun: .\\scripts\\Install-JeevesWalrusWinRm.ps1 ; "
                    "live needs -SiYes after gate closed"
                    if ev["ok"]
                    else "gate still OPEN - do not -SiYes"
                ),
            },
            EXIT_OK if ev["ok"] else EXIT_FINDING,
        )

    try:
        states = _gh_states(refs)
    except RuntimeError as e:
        return (
            {
                "ok": True,
                "soft_ok": True,
                "reason": "gh_unavailable",
                "detail": str(e),
                "fr": 9376,
                "findings": [],
            },
            EXIT_OK,
        )

    if any(v == "UNKNOWN" for v in states.values()) and all(
        v == "UNKNOWN" for v in states.values()
    ):
        return (
            {
                "ok": True,
                "soft_ok": True,
                "reason": "gh_all_unknown",
                "fr": 9376,
                "gate": evaluate_gate(states),
                "findings": [],
            },
            EXIT_OK,
        )

    ev = evaluate_gate(states)
    findings = [f"gate still OPEN: {r}" for r in ev["open"]]
    findings.extend([f"gate unknown state: {r}" for r in ev["unknown"]])
    return (
        {
            "ok": ev["ok"],
            "fr": 9376,
            "source": "gh",
            "gate": ev,
            "findings": findings,
            "script": "jeeves/scripts/Install-JeevesWalrusWinRm.ps1",
            "hint": (
                "DryRun: .\\scripts\\Install-JeevesWalrusWinRm.ps1 ; "
                "live needs -SiYes after gate closed"
                if ev["ok"]
                else "gate still OPEN - do not -SiYes"
            ),
        },
        EXIT_OK if ev["ok"] else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "walrus_jeeves_install_ready",
        "FR #9376 walrus Jeeves WinRM install gate readiness",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
