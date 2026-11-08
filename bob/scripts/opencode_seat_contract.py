"""FR #6240: OpenCode Windows seat contract. No credential reads.

Headless ``opencode run`` auto-rejects ``external_directory`` asks. It has
``--dir`` and no ``--interactive`` flag. ``--auto`` would approve those asks
and is never used. ``BOB_HOME`` may be empty. ``BOB_OUTBOX`` is the run-dir
protocol path the worker sets.
"""
from __future__ import annotations

import re
from pathlib import Path

# Credential stores and password folders must never become --dir.
# Slashes are normalized before the match so C:/passwords and C:\passwords agree.
DIR_FORBIDDEN_RX = re.compile(
    r"(?i)(\\.config\\gh|hosts\.yml|\.git-credentials|\\passwords(?:\\|$)|\\.netrc)"
)
_ASSIGN_RX = re.compile(
    r"(?i)\b(FR|MRB|UAT)\s+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)#(\d+)\b"
)
_TOKEN_RX = re.compile(
    r"(?i)(github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+|gho_[A-Za-z0-9]+|"
    r"ghu_[A-Za-z0-9]+|ghs_[A-Za-z0-9]+|ghr_[A-Za-z0-9]+)"
)

GH_BLOCK_MESSAGE = (
    "opencode-ready: blocked gh_auth_missing. "
    "Next: gh auth login in this Windows user. "
    "Do not read hosts.yml, do not search credential stores, do not invent GH_TOKEN."
)
DIR_FORBIDDEN_MESSAGE = (
    "opencode-ready: blocked opencode_dir_forbidden. "
    "Next: unset BOB_OPENCODE_DIR. Do not point OpenCode at a credential store."
)
WORKTREE_ABSENT_MESSAGE = (
    "opencode-ready: blocked worktree_absent. "
    "Next: create the assigned job worktree (Get-BobiverseJobWorktreePath) "
    "or answer external_directory in interactive opencode (the TUI). "
    "opencode run auto-rejects that ask and has no --interactive flag. "
    "Do not pass --auto. This run is not a completed job."
)


def redact_secrets(text: str) -> str:
    if not text:
        return ""
    return _TOKEN_RX.sub("[REDACTED]", text)


def _guard_forms(path: str) -> list[str]:
    raw = (path or "").strip().strip('"')
    forms = []
    if raw:
        forms.append(raw.replace("/", "\\"))
    try:
        resolved = str(Path(raw).resolve(strict=False))
    except (OSError, ValueError):
        resolved = ""
    if resolved:
        forms.append(resolved.replace("/", "\\"))
    return forms


def dir_is_forbidden(path: str) -> bool:
    """True for credential paths, including slash variants and symlink targets.

    Does not open or read any file in the path.
    """
    return any(DIR_FORBIDDEN_RX.search(form) for form in _guard_forms(path))


def gh_auth_blocks(stdout: str, stderr: str, exit_code: int) -> tuple[bool, str]:
    """Classify ``gh auth status`` text. Never opens a credential file.

    The returned message does not include the CLI output (it can echo an account).
    """
    blob = ((stdout or "") + "\n" + (stderr or "")).lower()
    code = int(exit_code)
    logged_in = code == 0 and ("logged in" in blob or "active account" in blob)
    if logged_in:
        return False, ""
    if (
        "gh auth login" in blob
        or "to get started with github cli" in blob
        or "not logged" in blob
        or code != 0
    ):
        return True, GH_BLOCK_MESSAGE
    return True, (
        "opencode-ready: blocked gh_auth_unknown. "
        "Next: gh auth status. Do not read credential files."
    )


def worktree_base_from_env(env: dict | None) -> str:
    """Same base as Get-BobiverseJobWorktreeBase when the env is already set.

    Does not invent a drive and does not create a directory.
    """
    env = env or {}
    explicit = str(env.get("BOB_JOB_WORKTREE_BASE") or "").strip()
    if explicit:
        return explicit
    bridge = str(env.get("BOB_BRIDGE_HOME") or "").strip()
    if not bridge:
        return ""
    return str(Path(bridge) / "worktrees")


def project_dir_for_assign(line: str, env: dict | None) -> str:
    """``<base>/<repo-leaf>/<fr-N>`` for one assign line, or ``''``."""
    match = _ASSIGN_RX.search(line or "")
    base = worktree_base_from_env(env)
    if not match or not base:
        return ""
    kind, _owner, repo, num = match.groups()
    repo_leaf = re.sub(r"[^A-Za-z0-9._-]+", "-", repo).strip("-") or "job"
    return str(Path(base) / repo_leaf / f"{kind.lower()}-{num}")


def write_project_dir(run_dir: str | Path, line: str, env: dict | None) -> str:
    """Record the job worktree for the next opencode run. Does not create it."""
    path = project_dir_for_assign(line, env)
    if not path:
        return ""
    dest = Path(run_dir) / "opencode-project-dir.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(path + "\n", encoding="utf-8")
    return path


def resolve_project_dir(path: str) -> dict:
    """Decide whether this run may pass ``--dir``.

    Empty means no job has been recorded: the seat may start in the worker
    folder, and that is not a claim that the job tree is reachable.
    A recorded path that is missing or a credential path blocks this run.
    A real directory that is not forbidden is the OpenCode project directory.
    Nothing here grants ``external_directory``.
    """
    raw = (path or "").strip()
    if not raw:
        return {"state": "no_job", "blocked": False, "dir": "", "message": ""}
    if dir_is_forbidden(raw):
        return {"state": "forbidden", "blocked": True, "dir": "", "message": DIR_FORBIDDEN_MESSAGE}
    folder = Path(raw)
    if not folder.is_dir():
        return {"state": "absent", "blocked": True, "dir": "", "message": WORKTREE_ABSENT_MESSAGE}
    try:
        resolved = str(folder.resolve(strict=False))
    except (OSError, ValueError):
        resolved = raw
    if dir_is_forbidden(resolved):
        return {"state": "forbidden", "blocked": True, "dir": "", "message": DIR_FORBIDDEN_MESSAGE}
    return {"state": "project", "blocked": False, "dir": resolved, "message": ""}


def probe_gh_auth(run) -> tuple[bool, str]:
    """Run ``gh auth status`` via ``run``. Never reads hosts.yml or token files."""
    try:
        proc = run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return True, GH_BLOCK_MESSAGE
    code = int(getattr(proc, "returncode", 1) or 0)
    return gh_auth_blocks(
        getattr(proc, "stdout", "") or "",
        getattr(proc, "stderr", "") or "",
        code,
    )


def opencode_run_args(model: str, prompt: str, opencode_dir: str = "") -> list[str]:
    """argv after the opencode executable. Never includes ``--auto``.

    ``opencode_dir`` is the job worktree for this run, not a seat-wide default.
    A missing or forbidden path raises. An empty path omits ``--dir``.
    """
    decision = resolve_project_dir(opencode_dir)
    if decision["blocked"]:
        raise ValueError(decision["message"])
    if not decision["dir"]:
        return ["run", "-m", model, prompt]
    return ["run", "--dir", decision["dir"], "-m", model, prompt]
