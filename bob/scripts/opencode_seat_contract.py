"""FR #6240: OpenCode Windows seat contract. No credential reads.

Headless ``opencode run`` auto-rejects ``external_directory`` asks. It has
``--dir`` and no ``--interactive`` flag. ``--auto`` would approve those asks
and is never used. ``BOB_HOME`` may be empty. ``BOB_OUTBOX`` is the run-dir
protocol path the worker sets.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Credential stores and password folders must never become --dir or an allow rule.
DIR_FORBIDDEN_RX = re.compile(
    r"(?i)(\\.config\\gh|hosts\.yml|\.git-credentials|\\passwords|\.netrc)"
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
DIR_MISSING_MESSAGE = (
    "opencode-ready: blocked opencode_dir_missing. "
    "Next: set BOB_OPENCODE_DIR to the assigned worktree from Get-BobiverseJobWorktreePath. "
    "Headless opencode run has no --interactive flag and auto-rejects external_directory. "
    "Do not pass --auto."
)


def redact_secrets(text: str) -> str:
    if not text:
        return ""
    return _TOKEN_RX.sub("[REDACTED]", text)


def dir_is_forbidden(path: str) -> bool:
    return bool(DIR_FORBIDDEN_RX.search(path or ""))


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


def permission_config(run_dir: str | Path) -> dict:
    """Allow external_directory only for this seat's run directory.

    ``*`` stays ``ask``. Headless ``opencode run`` auto-rejects ask, so every
    other external path (credential stores, other repos) stays blocked.
    The specific allow is last so it wins over ``*``.
    """
    run = str(run_dir or "").rstrip("\\/")
    if not run or dir_is_forbidden(run):
        raise ValueError("run dir missing or forbidden")
    specific = run + "\\*"
    return {
        "$schema": "https://opencode.ai/config.json",
        "permission": {
            "external_directory": {
                "*": "ask",
                specific: "allow",
            }
        },
    }


def permission_config_text(run_dir: str | Path) -> str:
    return json.dumps(permission_config(run_dir), indent=2)


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
    """argv after the opencode executable. Never includes ``--auto``."""
    args = ["run", "-m", model, prompt]
    directory = (opencode_dir or "").strip()
    if not directory:
        return args
    if dir_is_forbidden(directory):
        raise ValueError(DIR_FORBIDDEN_MESSAGE)
    return ["run", "--dir", directory, "-m", model, prompt]
