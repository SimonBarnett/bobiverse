"""FR #9183: prune finished job worktrees, idle sweep, free-space guard.

After DONE/GIVEUP/NACK the seat removes that job's worktree. While idle it
retries locked removals and sweeps extras. Before admitting a new job, if the
destination volume is below the free-space floor it sweeps once; if still low
it NACKs ``disk-low`` and files one deduplicated intake issue per machine.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Optional

# FR #9183: default 5 GB (was 2 GB in FR #8023 admission).
DEFAULT_MIN_FREE_GB = 5.0
DEFAULT_IDLE_MAX_AGE_HOURS = 24.0
_LOCK_RX = re.compile(
    r"(?i)access is denied|being used by another process|cannot remove|"
    r"device or resource busy|permission denied|\.pytest_cache|EBUSY|EACCES|locked"
)

_retry_lock = threading.Lock()
_retry_queue: Deque[str] = deque()
_retry_seen: set[str] = set()


def job_worktree_min_free_gb(env: dict | None = None) -> float:
    """Configurable free-space floor for job worktree volumes (FR #9183)."""
    env = os.environ if env is None else env
    raw = str(env.get("BOB_JOB_WORKTREE_MIN_FREE_GB") or "").strip()
    if not raw:
        return float(DEFAULT_MIN_FREE_GB)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(DEFAULT_MIN_FREE_GB)


def idle_worktree_max_age_hours(env: dict | None = None) -> float:
    env = os.environ if env is None else env
    raw = str(env.get("BOB_JOB_WORKTREE_IDLE_MAX_AGE_H") or "").strip()
    if not raw:
        return float(DEFAULT_IDLE_MAX_AGE_HOURS)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(DEFAULT_IDLE_MAX_AGE_HOURS)


def free_gb_for_path(path: str | Path) -> float:
    """Free space in GiB for the volume that holds *path* (or its parent)."""
    p = Path(path or ".")
    probe = p if p.exists() else (p.parent if str(p.parent) else Path("."))
    try:
        usage = shutil.disk_usage(str(probe))
    except OSError:
        return 0.0
    return float(usage.free) / (1024.0 ** 3)


def is_protected_worktree_path(
    path: str | Path,
    *,
    install_roots: list[str | Path] | None = None,
    keep_paths: list[str | Path] | None = None,
) -> bool:
    """True when *path* must never be removed (install/main/hotpatch/keep)."""
    try:
        raw = str(Path(path).resolve())
    except OSError:
        raw = str(path or "").strip()
    if not raw:
        return True
    low = raw.lower().replace("/", "\\")
    name = Path(raw).name.lower()
    if name in ("main", "master", "bob", "jeeves", "airc", "common"):
        # Leaf name alone is not enough for bob/jeeves - also require install match.
        pass
    if "_hotpatch_" in low or "\\_hotpatch" in low:
        return True
    for root in install_roots or ():
        try:
            rr = str(Path(root).resolve()).lower().replace("/", "\\")
        except OSError:
            rr = str(root or "").lower().replace("/", "\\")
        if not rr:
            continue
        if low == rr or low.rstrip("\\") == rr.rstrip("\\"):
            return True
        # Direct child named exactly the install product leaf still protected via equality above.
    for keep in keep_paths or ():
        try:
            kk = str(Path(keep).resolve()).lower().replace("/", "\\")
        except OSError:
            kk = str(keep or "").lower().replace("/", "\\")
        if kk and (low == kk or low.rstrip("\\") == kk.rstrip("\\")):
            return True
    return False


def _resolve_repo_root(job_worktree: Path, run) -> str:
    try:
        common = run(
            ["git", "-C", str(job_worktree), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if int(getattr(common, "returncode", 1)) == 0:
            common_dir = (common.stdout or "").strip()
            if common_dir:
                cpath = Path(common_dir)
                if not cpath.is_absolute():
                    cpath = (job_worktree / cpath).resolve()
                text = str(cpath)
                low = text.lower()
                if low.endswith(os.sep + ".git") or low.endswith("/.git"):
                    return str(cpath.parent)
                marker = low.rfind(f"{os.sep}.git{os.sep}")
                if marker < 0:
                    marker = low.rfind("/.git/")
                if marker >= 0:
                    return text[:marker]
    except Exception:
        pass
    try:
        top = run(
            ["git", "-C", str(job_worktree), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if int(getattr(top, "returncode", 1)) == 0:
            return (top.stdout or "").strip()
    except Exception:
        pass
    return ""


def _looks_locked(stderr: str, stdout: str = "") -> bool:
    blob = f"{stderr or ''}\n{stdout or ''}"
    return bool(_LOCK_RX.search(blob))


def queue_locked_worktree(path: str | Path) -> None:
    """Remember a locked worktree for the next idle retry (FR #9183)."""
    raw = str(path or "").strip()
    if not raw:
        return
    with _retry_lock:
        key = raw.lower()
        if key in _retry_seen:
            return
        _retry_seen.add(key)
        _retry_queue.append(raw)


def pending_locked_worktrees() -> list[str]:
    with _retry_lock:
        return list(_retry_queue)


def clear_locked_worktree_queue_for_tests() -> None:
    with _retry_lock:
        _retry_queue.clear()
        _retry_seen.clear()


def remove_finished_job_worktree(
    job_worktree: str | Path,
    *,
    install_root: str | Path | None = None,
    keep_paths: list[str | Path] | None = None,
    run=None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> str:
    """Remove the finished job's worktree. Returns ok|skipped:*|retry:locked|failed:*.

    Never raises into the worker loop. Locked trees are queued for idle retry.
    """
    run = subprocess.run if run is None else run
    raw = str(job_worktree or "").strip()
    if not raw:
        if log_fn:
            log_fn("job-wt-prune: skipped:no-path")
        return "skipped:no-path"
    root = Path(raw)
    installs = [install_root] if install_root else []
    if is_protected_worktree_path(root, install_roots=installs, keep_paths=keep_paths):
        if log_fn:
            log_fn(f"job-wt-prune: skipped:protected {raw}")
        return "skipped:protected"
    if not root.exists():
        if log_fn:
            log_fn(f"job-wt-prune: skipped:missing {raw}")
        return "skipped:missing"

    repo_root = ""
    try:
        repo_root = _resolve_repo_root(root, run)
    except Exception:
        repo_root = ""
    if install_root and not repo_root:
        repo_root = str(install_root)
    if not repo_root:
        if log_fn:
            log_fn(f"job-wt-prune: skipped:no-repo-root {raw}")
        return "skipped:no-repo-root"
    # Never treat the job tree itself as an install root (git-common-dir may be relative).

    try:
        rem = run(
            ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(root)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (getattr(rem, "stdout", "") or "") + (getattr(rem, "stderr", "") or "")
        code = int(getattr(rem, "returncode", 1) or 0)
        if code != 0:
            if _looks_locked(getattr(rem, "stderr", "") or "", getattr(rem, "stdout", "") or ""):
                queue_locked_worktree(root)
                if log_fn:
                    log_fn(f"job-wt-prune: retry:locked {raw}")
                return "retry:locked"
            if log_fn:
                log_fn(f"job-wt-prune: failed:exit-{code} {out[-200:]}")
            return f"failed:exit-{code}"
        try:
            run(
                ["git", "-C", str(repo_root), "worktree", "prune"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:
            pass
        # Belt: if git deregistered but folder remains, leave it for Clear/idle.
        if log_fn:
            log_fn(f"job-wt-prune: ok {raw}")
        return "ok"
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}:{e}"
        if _looks_locked(msg):
            queue_locked_worktree(root)
            if log_fn:
                log_fn(f"job-wt-prune: retry:locked {raw}")
            return "retry:locked"
        if log_fn:
            log_fn(f"job-wt-prune: failed:{type(e).__name__}")
        return f"failed:{type(e).__name__}"


def drain_locked_worktree_retries(
    *,
    install_root: str | Path | None = None,
    keep_paths: list[str | Path] | None = None,
    run=None,
    log_fn: Optional[Callable[[str], None]] = None,
    limit: int = 8,
) -> list[str]:
    """Retry previously locked removals (idle path). Never raises."""
    results: list[str] = []
    for _ in range(max(0, int(limit))):
        with _retry_lock:
            if not _retry_queue:
                break
            path = _retry_queue.popleft()
            _retry_seen.discard(path.lower())
        status = remove_finished_job_worktree(
            path,
            install_root=install_root,
            keep_paths=keep_paths,
            run=run,
            log_fn=log_fn,
        )
        results.append(f"{path}=>{status}")
        if status == "retry:locked":
            # Already re-queued inside remove_finished_job_worktree.
            pass
    return results


def disk_low_intake_marker_path(machine: str, *, home: str | Path | None = None) -> Path:
    base = Path(home) if home else Path(
        os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    ) / "Bobiverse"
    day = time.strftime("%Y%m%d", time.gmtime())
    mid = re.sub(r"[^A-Za-z0-9._-]+", "_", (machine or "unknown").strip()) or "unknown"
    return base / "disk-low-intake" / f"{mid}-{day}.flag"


def file_disk_low_intake_once(
    *,
    machine: str,
    free_gb: float,
    min_free_gb: float,
    volume: str = "",
    home: str | Path | None = None,
    post_intake: Optional[Callable[..., object]] = None,
) -> bool:
    """File at most one disk-low intake per machine per UTC day. Returns True when posted."""
    marker = disk_low_intake_marker_path(machine, home=home)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        if marker.is_file():
            return False
        marker.write_text(
            f"free_gb={free_gb:.2f} min={min_free_gb:.2f} volume={volume}\n",
            encoding="utf-8",
        )
    except OSError:
        # If we cannot mark, still attempt one post (tests inject post_intake).
        pass
    title = f"disk-low: {machine or 'machine'} job-worktree volume below {min_free_gb:.0f} GB"
    body = (
        f"Machine `{machine}` free={free_gb:.2f} GB (min {min_free_gb:.2f} GB) "
        f"volume=`{volume}`. Worker swept then NACKed disk-low (FR #9183). "
        f"No secrets. Safe cleanup: stale job worktrees only."
    )
    key = f"disk-low:{machine}:{time.strftime('%Y%m%d', time.gmtime())}"
    if post_intake is not None:
        try:
            post_intake(title=title, body=body, key=key, machine=machine)
            return True
        except Exception:
            return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    try:
        import crash_report

        crash_report._post_intake(
            title, body, repo="SimonBarnett/bobiverse", sig=key, exe="bob-worker"
        )
        return True
    except Exception:
        return False


def admit_job_worktree_disk(
    dest_parent: str | Path,
    *,
    job_key: str = "",
    machine: str = "",
    env: dict | None = None,
    sweep_fn: Optional[Callable[[], None]] = None,
    post_intake: Optional[Callable[..., object]] = None,
    home: str | Path | None = None,
) -> str:
    """Return '' when OK, else a full NACK line ending in disk-low (FR #9183)."""
    env = os.environ if env is None else env
    min_gb = job_worktree_min_free_gb(env)
    free = free_gb_for_path(dest_parent)
    if free >= min_gb:
        return ""
    if sweep_fn is not None:
        try:
            sweep_fn()
        except Exception:
            pass
        free = free_gb_for_path(dest_parent)
        if free >= min_gb:
            return ""
    file_disk_low_intake_once(
        machine=machine or str(env.get("COMPUTERNAME") or env.get("BOB_MACHINE") or "unknown"),
        free_gb=free,
        min_free_gb=min_gb,
        volume=str(dest_parent),
        home=home,
        post_intake=post_intake,
    )
    key = (job_key or "job").strip() or "job"
    return f"NACK {key} disk-low (FR #9183)"


def sweep_job_worktrees_via_clear(
    repo_root: str | Path,
    *,
    keep_path: str | Path = "",
    min_free_gb: float | None = None,
    run=None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> str:
    """Best-effort Clear soft-cap (MaxExtraJobTrees=0). Never raises."""
    run = subprocess.run if run is None else run
    root = str(repo_root or "").strip()
    if not root:
        return "skipped:no-repo-root"
    ps = shutil.which("powershell") or shutil.which("powershell.exe")
    if not ps:
        return "skipped:powershell-missing"
    script = None
    for cand in (
        Path(root) / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1",
        Path(root) / "scripts" / "Clear-BobiverseJobWorktrees.ps1",
    ):
        if cand.is_file():
            script = cand
            break
    if script is None:
        return "skipped:script-missing"
    floor = float(DEFAULT_MIN_FREE_GB if min_free_gb is None else min_free_gb)
    argv = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-RepoRoot",
        root,
        "-MaxExtraJobTrees",
        "0",
        "-MinFreeGB",
        str(floor),
        "-SkipSeatDisk",
    ]
    keep = str(keep_path or "").strip()
    if keep:
        argv.extend(["-KeepPath", keep])
    try:
        proc = run(argv, capture_output=True, text=True, timeout=300)
        code = int(getattr(proc, "returncode", 1) or 0)
        if log_fn:
            log_fn(f"job-wt-sweep: clear exit={code}")
        return "ok" if code == 0 else f"failed:exit-{code}"
    except Exception as e:  # noqa: BLE001
        if log_fn:
            log_fn(f"job-wt-sweep: clear failed:{type(e).__name__}")
        return f"failed:{type(e).__name__}"


def path_older_than_hours(path: str | Path, hours: float, *, now: float | None = None) -> bool:
    """True when path mtime is older than *hours* (missing => False)."""
    if hours <= 0:
        return True
    try:
        mtime = Path(path).stat().st_mtime
    except OSError:
        return False
    clock = time.time() if now is None else float(now)
    return (clock - float(mtime)) >= (float(hours) * 3600.0)
