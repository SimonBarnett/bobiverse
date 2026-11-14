"""FR #7238: overlay origin main `.grok/skills` into a dirty install without ff.

Never copies secrets. Never switches the install branch. Skill trees only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SKILL_TREES = (
    "bob/.grok/skills",
    "common/.grok/skills",
    "jeeves/.grok/skills",
    "airc/.grok/skills",
)
WORKER_BOOKS = (
    "bobiverse-bob",
    "bobiverse-bob-worker",
    "bobiverse-bob-plan",
    "bobiverse-bob-job-irc",
    "bobiverse-bob-job-fr",
    "bobiverse-bob-job-mrb",
    "bobiverse-bob-job-uat",
    "bobiverse-fleet-ops",
    "harvest",
    "harvest-agent-skills",
    "bob-setup-opencode",
)
PLAN_BOOKS = ("harvest", "harvest-agent-skills")
STAMP_NAME = "skills-sha.txt"


def skills_sha_stamp_path(install_root: str | Path) -> Path:
    return Path(install_root) / "run" / STAMP_NAME


def read_skills_sha(install_root: str | Path) -> str:
    path = skills_sha_stamp_path(install_root)
    try:
        line = (path.read_text(encoding="utf-8-sig") or "").strip().splitlines()
    except OSError:
        return ""
    if not line:
        return ""
    sha = line[0].strip()
    if len(sha) < 7 or any(c for c in sha if c not in "0123456789abcdefABCDEF"):
        return ""
    return sha.lower()


def _git(install: Path, args: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(install), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _write_stamp(install: Path, sha: str) -> None:
    stamp = skills_sha_stamp_path(install)
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(sha + "\n", encoding="utf-8")
    except OSError:
        return


def _find_book(install: Path, name: str) -> Path | None:
    for rel in ("bob/.grok/skills", "common/.grok/skills", "jeeves/.grok/skills"):
        cand = install / Path(rel) / name
        if cand.is_dir():
            return cand
    return None


def _mirror_agent_books(install: Path, dest_leaf: str, books: tuple[str, ...]) -> None:
    dest = install / dest_leaf / ".grok" / "skills"
    if not (install / dest_leaf).is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for name in books:
        src = _find_book(install, name)
        if src is None:
            continue
        target = dest / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(src, target)


def sync_install_skills_from_origin(
    install_root: str | Path,
    *,
    branch: str = "main",
    job_busy: bool = False,
    fetch: bool = True,
) -> dict[str, Any]:
    """Checkout origin/<branch> skill trees only. Safe on a dirty worktree.

    When ``job_busy`` is True, skip so a loaded job does not see a mid-turn rewrite.
    """
    install = Path(install_root)
    if job_busy:
        return {"ok": False, "reason": "mid-job", "sha": read_skills_sha(install)}
    if not (install / ".git").exists() and not (install / ".git").is_file():
        return {"ok": False, "reason": "not-git", "sha": ""}
    if fetch:
        fr = _git(install, ["fetch", "origin", branch])
        if fr.returncode != 0:
            # Still try checkout of last-known origin/branch.
            pass
    spec = f"origin/{branch}"
    sha_p = _git(install, ["rev-parse", spec])
    sha = (sha_p.stdout or "").strip()
    if sha_p.returncode != 0 or len(sha) < 7:
        return {"ok": False, "reason": "no-origin-sha", "sha": ""}
    existing: list[str] = []
    for rel in SKILL_TREES:
        probe = _git(install, ["cat-file", "-e", f"{spec}:{rel}"])
        if probe.returncode == 0:
            existing.append(rel.replace("\\", "/"))
    if not existing:
        return {"ok": False, "reason": "no-skill-trees", "sha": sha}
    co = _git(install, ["checkout", spec, "--", *existing])
    if co.returncode != 0:
        err = ((co.stderr or "") + (co.stdout or "")).strip().replace("\n", " ")[:240]
        return {"ok": False, "reason": f"checkout-failed {err}", "sha": sha}
    _mirror_agent_books(install, "worker", WORKER_BOOKS)
    _mirror_agent_books(install, "plan", PLAN_BOOKS)
    _write_stamp(install, sha)
    return {"ok": True, "reason": "synced", "sha": sha, "trees": existing}


def maybe_sync_install_skills(*, install_root: str | Path | None = None, job_busy: bool = False) -> dict[str, Any]:
    root = str(install_root or os.environ.get("BOB_INSTALL_ROOT") or "").strip()
    if not root:
        return {"ok": False, "reason": "no-install", "sha": ""}
    return sync_install_skills_from_origin(root, job_busy=job_busy)
