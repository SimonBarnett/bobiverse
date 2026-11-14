"""FR #6864 / #6891: process-local skill catalog bound for the Grok worker.

S7 (vision): the worker process prompt / ``grok inspect`` skills list names only
the core stub while a fat skill-dag index exists. Bundled platform skills may
remain (vision LOCKED).

## Measured levers (FR #6891)

| Lever | Result |
|---|---|
| Do not interpolate the skill-dag index into ``worker_prompt`` | Necessary but **not** sufficient. Harness still injects skill name+description from project/user/configToml/bundled. |
| ``BOB_SKILL_DAG_BOUND`` env alone | Harness does not read it. |
| Edit user ``~/.grok/config.toml`` ``[skills]`` | Forbidden (Plan / human Grok). |
| ``GROK_CONFIG`` overlay for ``[skills]`` / ``[mcp_servers]`` | Allowlist drops those tables. |
| Project ``.grok/config.toml`` ``[skills] disabled/ignore`` | Does **not** suppress project skill discovery. |
| Seat-local ``GROK_HOME`` (no ``auth.json`` copy; ``GROK_AUTH_PATH`` = machine store; empty ``skills.paths``; restore ``bundled_skill_dirs``) | Drops user + configToml skills; login is the one machine store (FR #7183); **does not** drop project skills when cwd is under a trusted install tree (e.g. ``C:\\ai\\bob``). |
| Seat cwd under the trusted install tree with only ``skill-dag-core`` | Still loads every ``.grok/skills`` under the install project root. |
| Seat cwd **outside** the install tree + seat ``GROK_HOME`` + only ``skill-dag-core`` under that cwd's ``.grok/skills`` + trust that cwd | **Works.** ``grok inspect`` lists ``skill-dag-core`` (+ bundled). Index fixtures outside ``.grok/skills`` stay out. ``--add-dir`` to the install is refused by the harness. |

Lever used in production: prepare a bound agent cwd under the seat ``run_dir``
(outside the install tree), seat-local ``GROK_HOME``, and launch grok with that
cwd. MCP keeps absolute ``--root`` paths into the real install skill trees.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Iterator

CORE_STUB_ID = "skill-dag-core"
CORE_STUB_LINE = (
    "Process-local skill catalog is the core stub only (skill-dag-core). "
    "Do not list other skill-dag index nodes in this prompt; resolve per job."
)
CORE_STUB_SKILL_MD = f"""---
name: {CORE_STUB_ID}
description: {CORE_STUB_LINE}
---
# {CORE_STUB_ID}

{CORE_STUB_LINE}
"""

BOUND_CWD_NAME = "bound-cwd"
GROK_HOME_NAME = "grok-home"


def catalog_prompt_bound(index_nodes: list[dict] | None) -> str:
    """Prompt fragment for an index of any size (never interpolates node text)."""
    del index_nodes
    return CORE_STUB_LINE


def apply_bound_env(
    env: dict | None,
    *,
    grok_home: str | Path | None = None,
    grok_auth_path: str | Path | None = None,
) -> dict:
    """Process-local env: bound marker, no GROK_CONFIG skills overlay, optional GROK_HOME.

    FR #7183: ``GROK_AUTH_PATH`` points at the one machine credential file. Seat
    ``GROK_HOME`` is sessions/logs/config only — never a copied ``auth.json``.
    """
    out = dict(env or {})
    out["BOB_SKILL_DAG_BOUND"] = CORE_STUB_ID
    out.pop("GROK_CONFIG", None)
    if grok_home is not None:
        out["GROK_HOME"] = str(grok_home)
    if grok_auth_path is not None:
        out["GROK_AUTH_PATH"] = str(grok_auth_path)
    return out


def default_user_grok_home(*, env: dict | None = None) -> Path:
    e = os.environ if env is None else env
    raw = (e.get("GROK_HOME") or "").strip()
    if raw and Path(raw).name != GROK_HOME_NAME:
        return Path(raw)
    return Path.home() / ".grok"


def machine_grok_auth_path(
    *, env: dict | None = None, user_grok_home: str | Path | None = None
) -> Path:
    """Single machine Grok credential file (FR #7183). Never a per-seat copy."""
    e = os.environ if env is None else env
    bob = (e.get("BOB_GROK_AUTH_PATH") or "").strip()
    if bob:
        return Path(bob)
    src = Path(user_grok_home) if user_grok_home else default_user_grok_home(env=e)
    return src / "auth.json"


def grok_session_usable(*, auth_path: str | Path | None = None, env: dict | None = None) -> bool:
    """True when the machine store exists and has at least one account object.

    Reads JSON structure only. Never logs or returns token values.
    """
    path = Path(auth_path) if auth_path else machine_grok_auth_path(env=env)
    try:
        if not path.is_file():
            return False
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError, TypeError, ValueError):
        return False
    return isinstance(obj, dict) and any(obj)


def _try_auth_lock(fh, timeout_s: float) -> bool:
    deadline = time.monotonic() + max(0.05, float(timeout_s))
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)


def _unlock_auth(fh) -> None:
    with contextlib.suppress(OSError):
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def grok_machine_auth_lock(
    auth_path: str | Path, *, timeout_s: float = 8.0
) -> Iterator[None]:
    """Cross-process lock beside the machine auth file (FR #7183 refresh race)."""
    lock_path = Path(str(auth_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    try:
        if not _try_auth_lock(fh, timeout_s):
            raise TimeoutError("grok auth lock")
        yield
    finally:
        _unlock_auth(fh)
        fh.close()


def commit_refreshed_auth(auth_path: str | Path, body: str, *, timeout_s: float = 8.0) -> None:
    """Atomically replace the machine auth file under the cross-process lock."""
    path = Path(auth_path)
    text = str(body)
    tmp = path.with_name(path.name + ".tmp")
    with grok_machine_auth_lock(path, timeout_s=timeout_s):
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)


def prepare_seat_grok_home(
    run_dir: str | Path,
    *,
    trust_paths: list[str | Path] | None = None,
    user_grok_home: str | Path | None = None,
) -> Path:
    """Create ``<run_dir>/grok-home`` for sessions/logs/config (never copies auth.json)."""
    run = Path(run_dir)
    home = run / GROK_HOME_NAME
    home.mkdir(parents=True, exist_ok=True)
    src = Path(user_grok_home) if user_grok_home else default_user_grok_home()
    # FR #7183: never copy auth.json. version.json is not a credential.
    s_ver = src / "version.json"
    if s_ver.is_file():
        shutil.copy2(s_ver, home / "version.json")
    bundled = src / "bundled" / "skills"
    bundled_lit = json.dumps(bundled.as_posix()) if bundled.is_dir() else "[]"
    if bundled.is_dir():
        bundled_line = f"bundled_skill_dirs = [{json.dumps(bundled.as_posix())}]"
    else:
        bundled_line = "bundled_skill_dirs = []"
    (home / "config.toml").write_text(
        "\n".join(
            [
                "[cli]",
                'installer = "internal"',
                'reasoning_effort = "low"',
                "[skills]",
                "paths = []",
                "ignore = []",
                "disabled = []",
                "server_skill_dirs = []",
                bundled_line,
                "[ui]",
                'permission_mode = "always-approve"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    # Trust bound cwd(s) so project skills under that cwd load (core stub only).
    lines: list[str] = []
    ts = int(time.time())
    for raw in trust_paths or []:
        p = str(Path(raw))
        # Match grok trusted_folders.toml key shape: [folders.'C:\path']
        lines.append(f"[folders.'{p}']")
        lines.append("trusted = true")
        lines.append(f"decided_at = {ts}")
        lines.append("")
    (home / "trusted_folders.toml").write_text("\n".join(lines) if lines else "", encoding="utf-8")
    return home


def prepare_bound_agent_cwd(
    run_dir: str | Path,
    worker_dir: str | Path,
    *,
    mcp_script: str | Path | None = None,
    mcp_roots: list[str | Path] | None = None,
) -> Path:
    """Build ``<run_dir>/bound-cwd`` outside the install tree with only skill-dag-core.

    MCP config uses absolute paths into the real install so resolve/get_skill still
    see the full skill trees. Harness project discovery stays on this cwd only.
    """
    run = Path(run_dir)
    worker = Path(worker_dir).resolve()
    bound = run / BOUND_CWD_NAME
    skills = bound / ".grok" / "skills" / CORE_STUB_ID
    skills.mkdir(parents=True, exist_ok=True)
    (skills / "SKILL.md").write_text(CORE_STUB_SKILL_MD, encoding="utf-8")
    agents = worker / "AGENTS.md"
    if agents.is_file():
        shutil.copy2(agents, bound / "AGENTS.md")
    else:
        (bound / "AGENTS.md").write_text(
            "# Bound agent cwd (FR #6891)\n\nCore stub only; resolve skills via skill-dag MCP.\n",
            encoding="utf-8",
        )
    for name in ("GROK.md", "CLAUDE.md"):
        src = worker / name
        if src.is_file():
            shutil.copy2(src, bound / name)
    script = Path(mcp_script) if mcp_script else (worker.parent / "common" / "scripts" / "skill_dag_mcp.py")
    roots = list(mcp_roots or [])
    if not roots:
        for cand in (
            worker / ".grok" / "skills",
            worker.parent / ".grok" / "skills",
            Path.home() / ".grok" / "skills",
        ):
            if cand.is_dir():
                roots.append(cand)
    grok_dir = bound / ".grok"
    grok_dir.mkdir(parents=True, exist_ok=True)
    ptr = grok_dir / "skill-dag-job-worktree"
    if not ptr.is_file():
        ptr.write_text("", encoding="utf-8")
    args = [script.as_posix()]
    for r in roots:
        args.extend(["--root", Path(r).resolve().as_posix()])
    args.extend(["--job-worktree-file", ptr.as_posix()])
    args_toml = ", ".join(json.dumps(a) for a in args)
    (grok_dir / "config.toml").write_text(
        "[mcp_servers.skill-dag]\n"
        'command = "python"\n'
        f"args = [{args_toml}]\n",
        encoding="utf-8",
    )
    # Minimal git metadata helps some harness trust paths; trust file is authoritative.
    git_dir = bound / ".git"
    if not git_dir.exists():
        try:
            subprocess.run(
                ["git", "init", "-q"],
                cwd=str(bound),
                check=False,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    return bound


def find_agent_exe() -> Path | None:
    for cand in (
        Path(os.environ.get("GROK_AGENT_EXE") or ""),
        Path.home() / ".grok" / "bin" / "agent.exe",
        Path.home() / ".grok" / "bin" / "grok.exe",
    ):
        if cand.is_file():
            return cand
    return None


def capture_inspect_skills(
    cwd: str | Path,
    *,
    grok_home: str | Path | None = None,
    agent_exe: str | Path | None = None,
    timeout_s: float = 120.0,
) -> list[dict[str, Any]]:
    """Run ``grok inspect --json`` and return the ``skills`` list (S7 measurement)."""
    exe = Path(agent_exe) if agent_exe else find_agent_exe()
    if exe is None or not exe.is_file():
        raise FileNotFoundError("grok agent.exe not found for inspect")
    env = os.environ.copy()
    if grok_home is not None:
        env["GROK_HOME"] = str(grok_home)
        env["GROK_AUTH_PATH"] = str(machine_grok_auth_path(env=env))
    else:
        env.pop("GROK_HOME", None)
    env.pop("GROK_CONFIG", None)
    proc = subprocess.run(
        [str(exe), "inspect", "--json"],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    raw = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"grok inspect returned no JSON (exit {proc.returncode}): {raw[:400]}")
    obj = json.loads(raw[start:])
    skills = obj.get("skills")
    if not isinstance(skills, list):
        raise RuntimeError("grok inspect JSON missing skills list")
    return skills


def non_bundled_skill_names(skills: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for s in skills:
        src = s.get("source") if isinstance(s, dict) else None
        st = src.get("type") if isinstance(src, dict) else None
        if st == "bundled":
            continue
        name = s.get("name") if isinstance(s, dict) else None
        if name:
            out.append(str(name))
    return out


def assert_s7_catalog_bound(skills: list[dict[str, Any]]) -> None:
    """S7: non-bundled harness skills must be only the core stub."""
    names = non_bundled_skill_names(skills)
    unexpected = [n for n in names if n != CORE_STUB_ID]
    assert not unexpected, (
        f"S7 unbound: non-bundled skills beyond {CORE_STUB_ID}: {unexpected[:20]}"
        f" (count={len(unexpected)})"
    )
    assert CORE_STUB_ID in names, f"S7: missing {CORE_STUB_ID} in inspect skills"
