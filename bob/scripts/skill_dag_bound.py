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
| Seat-local ``GROK_HOME`` (copy ``auth.json``; empty ``skills.paths``; restore ``bundled_skill_dirs``) | Drops user + configToml skills; login works; **does not** drop project skills when cwd is under a trusted install tree (e.g. ``C:\\ai\\bob``). |
| Seat cwd under the trusted install tree with only ``skill-dag-core`` | Still loads every ``.grok/skills`` under the install project root. |
| Seat cwd **outside** the install tree + seat ``GROK_HOME`` + only ``skill-dag-core`` under that cwd's ``.grok/skills`` + trust that cwd | **Works.** ``grok inspect`` lists ``skill-dag-core`` (+ bundled). Index fixtures outside ``.grok/skills`` stay out. ``--add-dir`` to the install is refused by the harness. |

Lever used in production: prepare a bound agent cwd under the seat ``run_dir``
(outside the install tree), seat-local ``GROK_HOME``, and launch grok with that
cwd. MCP keeps absolute ``--root`` paths into the real install skill trees.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

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


def apply_bound_env(env: dict | None, *, grok_home: str | Path | None = None) -> dict:
    """Process-local env: bound marker, no GROK_CONFIG skills overlay, optional GROK_HOME."""
    out = dict(env or {})
    out["BOB_SKILL_DAG_BOUND"] = CORE_STUB_ID
    out.pop("GROK_CONFIG", None)
    if grok_home is not None:
        out["GROK_HOME"] = str(grok_home)
    return out


def default_user_grok_home() -> Path:
    return Path(os.environ.get("GROK_HOME") or (Path.home() / ".grok"))


def prepare_seat_grok_home(
    run_dir: str | Path,
    *,
    trust_paths: list[str | Path] | None = None,
    user_grok_home: str | Path | None = None,
) -> Path:
    """Create ``<run_dir>/grok-home`` for the child process (never writes user config.toml)."""
    run = Path(run_dir)
    home = run / GROK_HOME_NAME
    home.mkdir(parents=True, exist_ok=True)
    src = Path(user_grok_home) if user_grok_home else default_user_grok_home()
    # Login: copy auth material only. Do not copy user config.toml (skills tables).
    for name in ("auth.json", "version.json"):
        s = src / name
        if s.is_file():
            shutil.copy2(s, home / name)
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
