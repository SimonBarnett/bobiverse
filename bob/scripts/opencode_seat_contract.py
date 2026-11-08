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
AMBIGUOUS_MESSAGE = (
    "opencode-ready: blocked job_context_ambiguous. "
    "Next: one worker message contained more than one job. No ACK."
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


def canonicalize_path(path: str) -> str:
    """Lexical ``.`` / ``..`` normalization. Does not touch the filesystem.

    ``D:\\ai\\..`` becomes ``D:\\``, which ``is_drive_root`` then refuses.
    This matches ``[IO.Path]::GetFullPath`` for drive paths without reading files.
    """
    raw = (path or "").strip().strip('"')
    if not raw:
        return ""
    slash = raw.replace("/", "\\")
    drive_match = re.match(r"^([A-Za-z]:)(.*)$", slash)
    if drive_match or ("\\" in raw and not raw.startswith("/")):
        if not drive_match:
            return slash
        rest = drive_match.group(2).lstrip("\\")
        stack: list[str] = []
        for part in rest.split("\\"):
            if part in ("", "."):
                continue
            if part == "..":
                if stack:
                    stack.pop()
                continue
            stack.append(part)
        if not stack:
            return drive_match.group(1) + "\\"
        return drive_match.group(1) + "\\" + "\\".join(stack)
    absolute = raw.startswith("/")
    stack = []
    for part in raw.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif not absolute:
                stack.append("..")
            continue
        stack.append(part)
    if absolute:
        return "/" + "/".join(stack)
    return "/".join(stack) or "."


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
        chosen = canonicalize_path(explicit)
    else:
        bridge = str(env.get("BOB_BRIDGE_HOME") or "").strip()
        if bridge:
            bridge_c = canonicalize_path(bridge)
            if is_drive_root(bridge_c):
                raise WorktreeBaseError(BASE_REFUSED_MESSAGE)
            chosen = canonicalize_path(_join_path(bridge_c, "worktrees"))
        else:
            sys_drive = system_drive or str(env.get("SystemDrive") or "C:")
            probe = disks if disks is not None else _local_fixed_disks()
            chosen = canonicalize_path(_join_path(data_drive_root(probe, sys_drive), "ai", "worktrees"))
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


FRAME_MARK = "@@BOBJOB1"


def message_job_keys(line: str) -> list[str]:
    """Job keys on one worker ``FROM nick target body`` message.

    Any other text, including the standing prompt and its example
    ``FR SimonBarnett/a-search#637``, has no job keys. The body is the
    text after the FROM envelope, not a search of an arbitrary string.
    """
    text = (line or "").strip()
    parts = text.split(None, 3)
    if len(parts) < 4 or parts[0].upper() != "FROM":
        return []
    found: list[str] = []
    for match in _JOB_KEY_RX.finditer(parts[3]):
        key = f"{match.group(1).upper()} {match.group(2)}"
        if key not in found:
            found.append(key)
    return found


def _nack_key(key: str, reason: str) -> str:
    if not key:
        return ""
    return f"NACK {key} {reason} (FR #6240)"


def _nack(line: str, reason: str) -> str:
    keys = message_job_keys(line)
    if not keys:
        return ""
    return _nack_key(keys[0], reason)


def _project_dir_for_key(
    key: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> str:
    match = re.match(r"(?i)^(FR|MRB|UAT)\s+(\S+)#(\d+)$", (key or "").strip())
    if not match:
        return ""
    base = job_worktree_base(env, disks=disks, system_drive=system_drive)
    kind, repo, num = match.groups()
    leaf = _repo_leaf(repo)
    if not leaf:
        return ""
    path = canonicalize_path(_join_path(base, leaf, f"{kind.lower()}-{num}"))
    if is_drive_root(path):
        return ""
    base_norm = canonicalize_path(base).replace("/", "\\").rstrip("\\").lower()
    path_norm = path.replace("/", "\\").rstrip("\\").lower()
    if not path_norm.startswith(base_norm + "\\"):
        return ""
    return path


def project_dir_for_assign(
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> str:
    """``<base>\\<repo-leaf>\\<fr-N>`` for one FROM assign, else ``''``."""
    keys = message_job_keys(line)
    if len(keys) != 1:
        return ""
    return _project_dir_for_key(keys[0], env, disks=disks, system_drive=system_drive)


def classify_opencode_job(
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> dict:
    """Job context for one worker message. Does not create a directory.

    Text that is not a single FROM assign, including the standing prompt, is
    ``not_assign``. Two job ids in one message are ``ambiguous`` and must not
    be ACK'd as the first id. A bad single assign returns one NACK and no path.
    """
    keys = message_job_keys(line)
    if not keys:
        return {"state": "not_assign", "nack": "", "nacks": [], "path": "", "key": "", "message": ""}
    if len(keys) != 1:
        nacks = [_nack_key(key, "job-context-ambiguous") for key in keys]
        return {
            "state": "ambiguous",
            "nack": "\n".join(nacks),
            "nacks": nacks,
            "path": "",
            "key": "",
            "message": AMBIGUOUS_MESSAGE,
        }
    key = keys[0]
    try:
        path = _project_dir_for_key(key, env, disks=disks, system_drive=system_drive)
    except WorktreeBaseError:
        nack = _nack_key(key, "worktree-base-refused")
        return {
            "state": "base_refused",
            "nack": nack,
            "nacks": [nack],
            "path": "",
            "key": key,
            "message": BASE_REFUSED_MESSAGE,
        }
    if not path:
        nack = _nack_key(key, "job-context-malformed")
        return {
            "state": "malformed",
            "nack": nack,
            "nacks": [nack],
            "path": "",
            "key": key,
            "message": MALFORMED_MESSAGE,
        }
    decision = resolve_project_dir(path)
    if decision["state"] == "forbidden":
        nack = _nack_key(key, "opencode-dir-forbidden")
        return {
            "state": "forbidden",
            "nack": nack,
            "nacks": [nack],
            "path": "",
            "key": key,
            "message": decision["message"],
        }
    if decision["state"] != "project":
        nack = _nack_key(key, "worktree-absent")
        return {
            "state": "absent",
            "nack": nack,
            "nacks": [nack],
            "path": path,
            "key": key,
            "message": decision["message"],
        }
    return {"state": "project", "nack": "", "nacks": [], "path": path, "key": key, "message": ""}


def frame_opencode_message(line: str, key: str, directory: str) -> str:
    """Bind this message to its directory. The wrapper strips the prefix.

    The standing prompt is never framed. A later message cannot change this
    message's directory.
    """
    if any(ch in (key or "") for ch in "\t\r\n") or any(ch in (directory or "") for ch in "\t\r\n"):
        raise ValueError("job context cannot be framed")
    return f"{FRAME_MARK}\t{key}\t{directory}\t{line}"


def parse_opencode_frame(raw: str) -> dict | None:
    """Return ``{key, dir, line}`` when ``raw`` is a worker job frame, else None."""
    text = raw or ""
    if not text.startswith(FRAME_MARK + "\t"):
        return None
    parts = text.split("\t", 3)
    if len(parts) != 4 or not parts[1]:
        return None
    return {"key": parts[1], "dir": parts[2], "line": parts[3]}


def prepare_opencode_wire(
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> dict:
    """Frame a single accepted assign. A refusal carries NACK text and no wire."""
    decision = classify_opencode_job(line, env, disks=disks, system_drive=system_drive)
    if decision["state"] == "not_assign":
        return {**decision, "wire": line}
    if decision["nack"]:
        return {**decision, "wire": ""}
    return {**decision, "wire": frame_opencode_message(line, decision["key"], decision["path"])}


def opencode_job_context_nack(
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> str:
    """NACK text when this message must not be ACK'd, else ``''``."""
    return classify_opencode_job(line, env, disks=disks, system_drive=system_drive)["nack"]


def write_project_dir(
    run_dir: str | Path,
    line: str,
    env: dict | None = None,
    disks: list | None = None,
    system_drive: str = "",
) -> str:
    """Return the job directory when it exists. Does not write a shared path file."""
    del run_dir
    decision = classify_opencode_job(line, env, disks=disks, system_drive=system_drive)
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
