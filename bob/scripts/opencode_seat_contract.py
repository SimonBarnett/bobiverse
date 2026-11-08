"""FR #6240: OpenCode Windows seat contract. No credential reads.

Headless ``opencode run`` auto-rejects ``external_directory`` asks. It has
``--dir`` and no ``--interactive`` flag. ``--auto`` would approve those asks
and is never used. ``BOB_HOME`` may be empty. ``BOB_OUTBOX`` is the run-dir
protocol path the worker sets.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# Credential stores and password folders must never become --dir.
# Slashes are normalized before the match so C:/passwords and C:\passwords agree.
DIR_FORBIDDEN_RX = re.compile(
    r"(?i)(\\.config\\gh|hosts\.yml|\.git-credentials|\\passwords(?:\\|$)|\\.netrc)"
)
# Same assign shape as the worker: TYPE + non-space ref ending in #digits.
# Repo may be owner/name or a leaf. A drive-root or ".." ref is refused later.
_ASSIGN_RX = re.compile(r"(?i)\b(FR|MRB|UAT)\s+(\S+)#(\d+)\b")
_JOB_KEY_RX = re.compile(r"(?i)\b(FR|MRB|UAT)\s+(\S+#\d+)\b")
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
    "Next: the job worktree path is a credential path. Do not point OpenCode at a credential store."
)
WORKTREE_ABSENT_MESSAGE = (
    "opencode-ready: blocked worktree_absent. "
    "Next: create the assigned job worktree (Get-BobiverseJobWorktreePath). "
    "Headless opencode run auto-rejects external_directory and has no --interactive flag. "
    "An interactive TUI answer is not evidence that a later opencode run will allow the outbox. "
    "Do not pass --auto. This run is not a completed job."
)
BASE_REFUSED_MESSAGE = (
    "opencode-ready: blocked worktree_base_refused. "
    "Next: set BOB_JOB_WORKTREE_BASE to <drive>\\ai\\worktrees. A drive root is refused."
)
MALFORMED_MESSAGE = (
    "opencode-ready: blocked job_context_malformed. "
    "Next: the assign did not match owner/repo#N or repo#N. No DONE."
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


class WorktreeBaseError(ValueError):
    """FR #4988: the job worktree base resolved to a drive root or was refused."""


def is_drive_root(path: str) -> bool:
    """True for ``D:`` or ``D:\\`` (and slash forms). Not true for ``D:\\ai\\worktrees``."""
    raw = (path or "").strip().strip('"').replace("/", "\\")
    if not raw:
        return False
    trimmed = raw.rstrip("\\")
    if re.fullmatch(r"[A-Za-z]:", trimmed):
        return True
    root = ""
    match = re.match(r"^([A-Za-z]:)\\", raw)
    if match:
        root = match.group(1)
    return bool(root) and trimmed.upper() == root.upper()


def data_drive_root(disks: list | None, system_drive: str = "C:") -> str:
    """Prefer non-system ``D:\\``, else another fixed disk, else the system drive.

    ``disks`` entries are ``{"Root": "D:\\\\", "DriveType": 3}``. DriveType 3 is a
    fixed disk, matching ``Get-BobiverseDataDriveRoot``.
    """
    sys = (system_drive or "C:").strip().rstrip("\\") + "\\"
    fixed: list[str] = []
    for disk in disks or []:
        root = str((disk or {}).get("Root") or "")
        if not root:
            continue
        if not root.endswith("\\"):
            root += "\\"
        if str((disk or {}).get("DriveType")) != "3":
            continue
        fixed.append(root)
    for root in fixed:
        if root.lower() != sys.lower() and re.fullmatch(r"(?i)d:\\", root):
            return root
    for root in fixed:
        if root.lower() != sys.lower():
            return root
    return sys


def _local_fixed_disks() -> list[dict]:
    """Fixed disks on Windows only. Does not read files. Empty off Windows."""
    if os.name != "nt":
        return []
    try:
        import ctypes
    except Exception:
        return []
    out = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{letter}:\\"
        try:
            kind = int(ctypes.windll.kernel32.GetDriveTypeW(root))
        except Exception:
            continue
        if kind == 3:
            out.append({"Root": root, "DriveType": 3})
    return out


def job_worktree_base(
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> str:
    """Override order matches ``Get-BobiverseJobWorktreeBase``. Never a drive root.

    Unset env uses ``<data-drive>\\ai\\worktrees``. This does not create the directory.
    """
    env = env or {}
    explicit = str(env.get("BOB_JOB_WORKTREE_BASE") or "").strip()
    if explicit:
        chosen = explicit
    else:
        bridge = str(env.get("BOB_BRIDGE_HOME") or "").strip()
        if bridge:
            if is_drive_root(bridge):
                raise WorktreeBaseError(BASE_REFUSED_MESSAGE)
            chosen = str(Path(bridge) / "worktrees")
        else:
            sys_drive = system_drive or str(env.get("SystemDrive") or "C:")
            probe = disks if disks is not None else _local_fixed_disks()
            chosen = _join_path(data_drive_root(probe, sys_drive), "ai", "worktrees")
    if is_drive_root(chosen):
        raise WorktreeBaseError(BASE_REFUSED_MESSAGE)
    return chosen.rstrip("\\/")


def _join_path(base: str, *parts: str) -> str:
    """Join a Windows drive path with backslashes. Local test paths keep ``Path``."""
    raw = (base or "").strip()
    if re.match(r"^[A-Za-z]:", raw) or "\\" in raw:
        joined = raw.replace("/", "\\").rstrip("\\")
        for part in parts:
            piece = (part or "").replace("/", "\\").strip("\\")
            if piece:
                joined = joined + "\\" + piece
        return joined
    path = Path(raw)
    for part in parts:
        path = path / part
    return str(path)


def _repo_leaf(repo: str) -> str:
    """Last path segment, matching ``Get-BobiverseJobWorktreePath``. ``..`` is refused."""
    text = (repo or "").replace("\\", "/").strip().strip("/")
    if not text or ".." in text.split("/"):
        return ""
    if "/" in text:
        text = text.split("/")[-1]
    if text in {".", ".."}:
        return ""
    leaf = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    if not leaf or set(leaf) <= {"."}:
        return ""
    return leaf


def _job_key(line: str) -> str:
    match = _JOB_KEY_RX.search(line or "")
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2)}"


def _nack(line: str, reason: str) -> str:
    key = _job_key(line)
    if not key:
        return ""
    return f"NACK {key} {reason} (FR #6240)"


def project_dir_for_assign(
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> str:
    """``<base>\\<repo-leaf>\\<fr-N>`` or ``''`` when the assign text does not match.

    A matched assign whose leaf is ``..`` or empty returns ``''`` so the caller
    NACKs instead of launching in the worker folder.
    """
    match = _ASSIGN_RX.search(line or "")
    if not match:
        return ""
    base = job_worktree_base(env, disks=disks, system_drive=system_drive)
    kind, repo, num = match.groups()
    leaf = _repo_leaf(repo)
    if not leaf:
        return ""
    job = f"{kind.lower()}-{num}"
    path = _join_path(base, leaf, job)
    if is_drive_root(path):
        return ""
    base_norm = base.replace("/", "\\").rstrip("\\").lower()
    path_norm = path.replace("/", "\\").rstrip("\\").lower()
    if not path_norm.startswith(base_norm + "\\"):
        return ""
    return path


def classify_opencode_job(
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> dict:
    """Job context for one line. Does not create a directory and does not write a file.

    ``not_assign`` is a startup or chat line: no ``--dir`` is required.
    An assign that cannot be a safe existing directory returns a NACK and no path.
    """
    if not _JOB_KEY_RX.search(line or ""):
        return {"state": "not_assign", "nack": "", "path": "", "message": ""}
    try:
        path = project_dir_for_assign(line, env, disks=disks, system_drive=system_drive)
    except WorktreeBaseError:
        return {
            "state": "base_refused",
            "nack": _nack(line, "worktree-base-refused"),
            "path": "",
            "message": BASE_REFUSED_MESSAGE,
        }
    if not path:
        return {
            "state": "malformed",
            "nack": _nack(line, "job-context-malformed"),
            "path": "",
            "message": MALFORMED_MESSAGE,
        }
    decision = resolve_project_dir(path)
    if decision["state"] == "forbidden":
        return {
            "state": "forbidden",
            "nack": _nack(line, "opencode-dir-forbidden"),
            "path": "",
            "message": decision["message"],
        }
    if decision["state"] != "project":
        return {
            "state": "absent",
            "nack": _nack(line, "worktree-absent"),
            "path": path,
            "message": decision["message"],
        }
    return {"state": "project", "nack": "", "path": path, "message": ""}


def record_opencode_job(
    run_dir: str | Path,
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> dict:
    """Write ``opencode-project-dir.txt`` only when the job directory exists and is safe."""
    decision = classify_opencode_job(line, env, disks=disks, system_drive=system_drive)
    if decision["state"] != "project" or not decision["path"] or not run_dir:
        return decision
    dest = Path(run_dir) / "opencode-project-dir.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(decision["path"] + "\n", encoding="utf-8")
    return decision


def opencode_job_context_nack(
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> str:
    """NACK text when this assign must not be ACK'd, else ``''``."""
    return classify_opencode_job(line, env, disks=disks, system_drive=system_drive)["nack"]


def write_project_dir(
    run_dir: str | Path,
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> str:
    """Record the job worktree. Returns ``''`` when the run must not use ``--dir``."""
    decision = record_opencode_job(run_dir, line, env, disks=disks, system_drive=system_drive)
    if decision["state"] == "project":
        return decision["path"]
    return ""


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
