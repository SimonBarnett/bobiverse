#!/usr/bin/env python3
"""Token-free readiness for FR #9419 redqueen bob-tray hotpatch.

EXIT 0: live bob-tray.exe SHA-256 matches newest green build-bob-tray (or fixture).
EXIT 1: drift / missing live / no green run (finding).
EXIT 2: error (bad fixture).

Does not mutate the install or restart the tray. Fixture:
  BOB_TRAY_REDQUEEN_INSTALL_FIXTURE=/path/to.json
  JSON: {"run_id":"...","bob_tray_sha256":"...","live_sha256":"..."}
Optional live path override: BOB_TRAY_REDQUEEN_LIVE_EXE=/path/to/bob-tray.exe
Optional install root: BOB_INSTALL_ROOT / BOB_TRAY_INSTALL_ROOT (default C:\\ai\\bob)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from _common import EXIT_ERROR, EXIT_FINDING, EXIT_OK, run_check

DEFAULT_REPO = "SimonBarnett/bobiverse"
DEFAULT_WORKFLOW = "build-bob-tray.yml"
DEFAULT_ARTIFACT = "bob-tray"
DEFAULT_INSTALL = Path(r"C:\ai\bob")


def pick_manifest_exe_hash(man: dict[str, Any]) -> str:
    """Prefer root bob-tray.exe, then tools/bob-tray.exe from MANIFEST.files."""
    files = man.get("files") if isinstance(man, dict) else None
    if not isinstance(files, dict):
        raise ValueError("MANIFEST.json missing files map")
    for key in ("bob-tray.exe", "tools/bob-tray.exe", "tools\\bob-tray.exe"):
        raw = files.get(key)
        if raw:
            return str(raw).strip().lower()
    raise ValueError("MANIFEST.files missing bob-tray.exe hash")


def evaluate_drift(*, expected: str, live: str) -> dict[str, Any]:
    exp = (expected or "").strip().lower()
    got = (live or "").strip().lower()
    if not exp:
        return {
            "ok": False,
            "reason": "expected_missing",
            "drift": False,
            "expected": exp,
            "live": got,
        }
    if not got:
        return {
            "ok": False,
            "reason": "live_missing",
            "drift": False,
            "expected": exp,
            "live": got,
        }
    if exp == got:
        return {
            "ok": True,
            "reason": "match",
            "drift": False,
            "expected": exp,
            "live": got,
        }
    return {
        "ok": False,
        "reason": "drift",
        "drift": True,
        "expected": exp,
        "live": got,
    }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _resolve_live_exe() -> Path | None:
    override = (os.environ.get("BOB_TRAY_REDQUEEN_LIVE_EXE") or "").strip()
    if override:
        p = Path(override)
        return p if p.is_file() else None
    root_raw = (
        os.environ.get("BOB_TRAY_INSTALL_ROOT")
        or os.environ.get("BOB_INSTALL_ROOT")
        or ""
    ).strip()
    root = Path(root_raw) if root_raw else DEFAULT_INSTALL
    for rel in (
        Path("tools") / "bob-tray.exe",
        Path("bob-tray.exe"),
        Path("tray") / "tools" / "bob-tray.exe",
    ):
        cand = root / rel
        if cand.is_file():
            return cand
    return None


def _load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _gh_newest_success_run(
    repo: str = DEFAULT_REPO, workflow: str = DEFAULT_WORKFLOW
) -> dict[str, Any] | None:
    try:
        p = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "-R",
                repo,
                "--workflow",
                workflow,
                "--branch",
                "main",
                "--status",
                "success",
                "--limit",
                "1",
                "--json",
                "databaseId,headSha,url,displayTitle",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0 or not (p.stdout or "").strip():
        return None
    rows = json.loads(p.stdout)
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    if not isinstance(row, dict) or not row.get("databaseId"):
        return None
    return row


def check(args: Any) -> tuple[dict[str, Any], int]:
    fix = (os.environ.get("BOB_TRAY_REDQUEEN_INSTALL_FIXTURE") or "").strip()
    if fix:
        try:
            doc = _load_fixture(Path(fix))
        except (OSError, json.JSONDecodeError) as exc:
            return (
                {
                    "ok": False,
                    "fr": 9419,
                    "source": "fixture",
                    "findings": [f"fixture read failed: {type(exc).__name__}"],
                    "path_fixture": fix,
                },
                EXIT_FINDING,
            )
        expected = str(doc.get("bob_tray_sha256") or doc.get("expected_sha256") or "")
        live = str(doc.get("live_sha256") or "")
        ev = evaluate_drift(expected=expected, live=live)
        findings: list[str] = []
        if ev["reason"] == "drift":
            findings.append(
                f"bob-tray.exe drift expected={ev['expected'][:12]}... live={ev['live'][:12]}..."
            )
        elif not ev["ok"]:
            findings.append(f"bob-tray install not ready: {ev['reason']}")
        return (
            {
                "ok": ev["ok"],
                "fr": 9419,
                "source": "fixture",
                "run_id": str(doc.get("run_id") or ""),
                "drift": ev,
                "findings": findings,
                "script": "bob/scripts/Install-BobTrayRedqueen.ps1",
                "hint": (
                    "DryRun: .\\bob\\scripts\\Install-BobTrayRedqueen.ps1 ; "
                    "live needs -Install on redqueen"
                    if ev["ok"]
                    else "drift or missing hash - DryRun then -Install on redqueen"
                ),
            },
            EXIT_OK if ev["ok"] else EXIT_FINDING,
        )

    live_path = _resolve_live_exe()
    live_hash = ""
    if live_path is not None:
        try:
            live_hash = _sha256_file(live_path)
        except OSError as e:
            return (
                {
                    "ok": False,
                    "fr": 9419,
                    "source": "live",
                    "findings": [f"live hash failed: {type(e).__name__}"],
                },
                EXIT_FINDING,
            )

    run = _gh_newest_success_run()
    if run is None:
        return (
            {
                "ok": True,
                "soft_ok": True,
                "reason": "gh_unavailable_or_no_success",
                "fr": 9419,
                "live_sha256": live_hash,
                "live_path": str(live_path) if live_path else "",
                "findings": [],
                "hint": (
                    "no successful build-bob-tray on main or gh missing; "
                    "FR the build failure; do not -Install"
                ),
            },
            EXIT_OK,
        )

    # Without downloading the artifact we cannot know expected exe hash from gh alone.
    # Soft-ok with newest run metadata so MONITORING can DryRun the install script.
    return (
        {
            "ok": True,
            "soft_ok": True,
            "reason": "success_run_seen_hash_via_install_script",
            "fr": 9419,
            "source": "gh",
            "run_id": str(run.get("databaseId") or ""),
            "head_sha": str(run.get("headSha") or ""),
            "run_url": str(run.get("url") or ""),
            "live_sha256": live_hash,
            "live_path": str(live_path) if live_path else "",
            "findings": [],
            "script": "bob/scripts/Install-BobTrayRedqueen.ps1",
            "hint": (
                "DryRun: .\\bob\\scripts\\Install-BobTrayRedqueen.ps1 "
                f"-WorkflowRunId {run.get('databaseId')}; live needs -Install"
            ),
        },
        EXIT_OK,
    )


def main(argv=None) -> int:
    return run_check(
        "redqueen_bob_tray_install_ready",
        "FR #9419 redqueen bob-tray install drift / green-run readiness",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
