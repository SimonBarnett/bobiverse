"""Shared machine clone resolver + provisioner (FR #8152).

One helper for OpenCode, Grok, Cursor and Aider seat paths. Locates a job repo
clone from env, install root, ``BOB_AI_ROOT``, or the bob-bridge stores
(``repos`` / ``clones`` / ``mirrors``). Bare repos are valid worktree sources.
When missing, provisions into ``<bridge>\\repos\\<leaf>.git`` via ``gh`` / ``git``
with a timeout and no secret prints. Callers run this off the IRC read thread
(FR #6328). Clone failures surface as ``clone-failed:<class>`` (FR #8016).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

CLONE_TIMEOUT_S = 120.0

_TOKEN_RX = re.compile(
    r"(?i)(github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+|gho_[A-Za-z0-9]+|"
    r"ghu_[A-Za-z0-9]+|ghs_[A-Za-z0-9]+|ghr_[A-Za-z0-9]+)"
)


def redact_secrets(text: str) -> str:
    if not text:
        return ""
    return _TOKEN_RX.sub("[REDACTED]", text)


def redact_git_detail(text: str, *, max_len: int = 160) -> str:
    blob = redact_secrets(text or "")
    blob = " ".join(blob.split())
    if len(blob) > max_len:
        blob = blob[: max_len - 3].rstrip() + "..."
    return blob


def repo_leaf(repo: str) -> str:
    """Last path segment; ``..`` refused. Matches Get-BobiverseJobWorktreePath leaf."""
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


def owner_repo(repo: str) -> str:
    """Return ``owner/name`` when *repo* looks like one, else empty."""
    text = (repo or "").replace("\\", "/").strip().strip("/")
    if not text or ".." in text.split("/"):
        return ""
    parts = [p for p in text.split("/") if p]
    if len(parts) != 2:
        return ""
    owner, name = parts
    if not owner or not name or owner in {".", ".."} or name in {".", ".."}:
        return ""
    if not re.match(r"^[A-Za-z0-9._-]+$", owner):
        return ""
    if not re.match(r"^[A-Za-z0-9._-]+$", name):
        return ""
    return f"{owner}/{name}"


def is_git_repo(root: str | Path) -> bool:
    """True for a linked/checkout (``.git``) or a bare repo (``HEAD`` + objects)."""
    path = Path(root)
    if not path.exists():
        return False
    if (path / ".git").exists():
        return True
    # Bare: HEAD file and objects/ (or packed-refs) without a working tree.
    if (path / "HEAD").is_file() and (
        (path / "objects").is_dir() or (path / "packed-refs").is_file()
    ):
        return True
    return False


def bridge_home(env: dict | None = None) -> str:
    """``BOB_BRIDGE_HOME``, else ``%USERPROFILE%\\.grok\\bob-bridge``.

    When *env* is ``None``, reads the process environment (production). When a
    dict is passed (tests), only that dict is consulted so hermetic suites do
    not leak into the operator profile.
    """
    source = os.environ if env is None else env
    explicit = str(source.get("BOB_BRIDGE_HOME") or "").strip().strip('"')
    if explicit:
        return str(Path(explicit))
    profile = str(source.get("USERPROFILE") or source.get("HOME") or "").strip()
    if not profile:
        return ""
    return str(Path(profile) / ".grok" / "bob-bridge")


def bridge_clone_candidates(bridge: str, leaf: str) -> list[str]:
    """Shared store order: repos/<leaf>(.git), clones/<leaf>, mirrors/<leaf>(.git)."""
    if not bridge or not leaf:
        return []
    base = Path(bridge)
    return [
        str(base / "repos" / leaf),
        str(base / "repos" / f"{leaf}.git"),
        str(base / "clones" / leaf),
        str(base / "mirrors" / leaf),
        str(base / "mirrors" / f"{leaf}.git"),
    ]


def resolve_repo_clone(
    repo: str,
    env: dict | None = None,
    install_root: str | Path | None = None,
) -> str:
    """Locate the machine clone for *repo*. Never invents a path; never clones.

    Order: ``BOB_REPO_CLONE_<leaf>``, bobiverse->install_root,
    ``BOB_AI_ROOT\\<leaf>``, then bob-bridge ``repos`` / ``clones`` / ``mirrors``.
    Bare ``BOB_REPO_CLONE`` is ignored (docs/mrb-6324).
    """
    env = os.environ if env is None else env
    leaf = repo_leaf(repo)
    if not leaf:
        return ""
    for key in (
        f"BOB_REPO_CLONE_{leaf}",
        f"BOB_REPO_CLONE_{leaf.upper()}",
    ):
        raw = str(env.get(key) or "").strip().strip('"')
        if raw and is_git_repo(raw):
            return str(Path(raw))
    if leaf.lower() == "bobiverse" and install_root:
        root = Path(str(install_root))
        if is_git_repo(root):
            return str(root)
    ai_root = str(env.get("BOB_AI_ROOT") or "").strip().strip('"')
    if not ai_root and install_root:
        inst = Path(str(install_root))
        if inst.name.lower() == "bob":
            ai_root = str(inst.parent)
    if ai_root:
        cand = Path(ai_root) / leaf
        if is_git_repo(cand):
            return str(cand)
    bridge = bridge_home(env)
    if bridge:
        for cand in bridge_clone_candidates(bridge, leaf):
            if is_git_repo(cand):
                return str(Path(cand))
    return ""


def classify_clone_stderr(stderr: str) -> str:
    """Map clone stderr to a short class for ``clone-failed:<class>`` (FR #8016)."""
    blob = (stderr or "").lower()
    if not blob.strip():
        return "git-clone"
    if "timed out" in blob or "timeout" in blob:
        return "timeout"
    if (
        "authentication" in blob
        or "permission denied" in blob
        or "could not read username" in blob
        or "auth" in blob and ("fail" in blob or "error" in blob)
        or "403" in blob
        or "401" in blob
    ):
        return "auth"
    if (
        "not found" in blob
        or "does not exist" in blob
        or "could not find" in blob
        or "404" in blob
    ):
        return "not-found"
    if (
        "could not resolve" in blob
        or "failed to connect" in blob
        or "network" in blob
        or "connection refused" in blob
        or "temporary failure" in blob
    ):
        return "network"
    return "git-clone"


def _is_timeout_exc(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name == "TimeoutExpired":
        return True
    try:
        import subprocess as _sp

        return isinstance(exc, _sp.TimeoutExpired)
    except Exception:
        return False


def _proc_err_text(proc) -> str:
    err = getattr(proc, "stderr", "") or ""
    out = getattr(proc, "stdout", "") or ""
    if isinstance(err, bytes):
        err = err.decode("utf-8", errors="replace")
    if isinstance(out, bytes):
        out = out.decode("utf-8", errors="replace")
    return f"{err}\n{out}".strip()


def provision_repo_clone(
    repo: str,
    env: dict | None = None,
    *,
    run=None,
    timeout: float = CLONE_TIMEOUT_S,
) -> tuple[str, str, str]:
    """Clone *repo* into ``<bridge>\\repos\\<leaf>.git`` (bare).

    Returns ``(path, error_class, detail)``. *path* is set on success; on failure
    *error_class* is ``clone-failed:<class>`` and *detail* is redacted stderr.
    Does not print secrets. Callers must run this off the IRC read thread.
    """
    import subprocess as _sp

    run = run or _sp.run
    env = os.environ if env is None else env
    leaf = repo_leaf(repo)
    full = owner_repo(repo)
    if not leaf or not full:
        # Cannot attempt a clone without owner/name — same class as missing clone.
        return "", "no-clone", ""
    # Re-check in case another seat raced us.
    existing = resolve_repo_clone(repo, env)
    if existing:
        return existing, "", ""
    bridge = bridge_home(env)
    if not bridge:
        # No shared store configured in this env — caller NACKs no-clone.
        return "", "no-clone", ""
    dest = Path(bridge) / "repos" / f"{leaf}.git"
    if is_git_repo(dest):
        return str(dest), "", ""
    if dest.exists():
        return "", "clone-failed:path-exists", redact_git_detail(str(dest))
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return "", "clone-failed:disk", redact_git_detail(str(exc))

    # Prefer gh (uses machine auth); fall back to git HTTPS (also uses gh credential helper).
    attempts: list[list[str]] = [
        ["gh", "repo", "clone", full, str(dest), "--", "--bare"],
        ["git", "clone", "--bare", f"https://github.com/{full}.git", str(dest)],
    ]
    last_class = "git-clone"
    last_detail = ""
    for args in attempts:
        try:
            proc = run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except Exception as exc:
            if _is_timeout_exc(exc):
                return "", "clone-failed:timeout", ""
            last_class = "git-clone"
            last_detail = redact_git_detail(str(exc))
            continue
        if int(getattr(proc, "returncode", 1)) == 0 and is_git_repo(dest):
            return str(dest), "", ""
        err_text = _proc_err_text(proc)
        last_class = classify_clone_stderr(err_text)
        last_detail = redact_git_detail(err_text)
        # Auth failure: do not fall through to a second attempt that will also fail.
        if last_class == "auth":
            break
        # Clean a partial dest before the next attempt.
        if dest.exists() and not is_git_repo(dest):
            try:
                import shutil

                shutil.rmtree(dest, ignore_errors=True)
            except Exception:
                pass
    return "", f"clone-failed:{last_class}", last_detail


def ensure_repo_clone(
    repo: str,
    env: dict | None = None,
    install_root: str | Path | None = None,
    *,
    run=None,
    provision: bool = True,
    timeout: float = CLONE_TIMEOUT_S,
) -> tuple[str, str, str]:
    """Resolve an existing clone, else provision one when *provision* is true.

    Returns ``(path, error_class, detail)``. Empty path with empty error means
    "not found and provision disabled" (caller may NACK ``no-clone``).
    """
    found = resolve_repo_clone(repo, env, install_root=install_root)
    if found:
        return found, "", ""
    if not provision:
        return "", "", ""
    return provision_repo_clone(repo, env, run=run, timeout=timeout)
