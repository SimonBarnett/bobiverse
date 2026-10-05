"""FR #2522: plugin registry for jeeves.exe --self-test / --heal checks.

A check is a ``check_<name>.py`` file in a checks folder with:

* ``CHECK_NAME = "<name>"`` (lowercase token, must not shadow a builtin)
* ``def run(home: Path, chair_home: Path) -> tuple[dict, list[str], list[str]]`` returning
  ``(detail, findings, errors)`` - deterministic, token-free, no IRC mutation
* optional ``INCLUDE_IN_DEFAULT = True`` (default) to run on a bare ``--self-test``

Folders searched (first match per name wins): ``JEEVES_CHECKS_DIR``; the repo ``jeeves/checks``;
``<JEEVES_INSTALL_ROOT>/checks``; ``<exe dir>/checks`` and the bundled ``checks`` inside a frozen jeeves.exe.
New or changed checks ship through a PR + MRB (Build-Jeeves bundles ``jeeves/checks``); never live-edit the running exe.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Any

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


def checks_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent
    out: list[Path] = []
    env = (os.environ.get("JEEVES_CHECKS_DIR") or "").strip()
    if env:
        out.append(Path(env))
    out.append(here.parents[1] / "jeeves" / "checks")  # repo: common/scripts -> <repo>/jeeves/checks
    out.append(here.parent / "checks")  # composed install: <root>/scripts + <root>/checks
    inst = (os.environ.get("JEEVES_INSTALL_ROOT") or "").strip()
    if inst:
        out.append(Path(inst) / "checks")
    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).resolve().parent / "checks")
        mei = getattr(sys, "_MEIPASS", None)
        if mei:
            out.append(Path(mei) / "checks")
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        k = str(p).lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"jeeves_check_{path.stem}", str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_plugin_checks(reserved: tuple[str, ...] = ()) -> dict[str, dict[str, Any]]:
    """name -> {run, include_default, path}. Broken or malformed plugins are reported under ``_errors``."""
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for folder in checks_dirs():
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("check_*.py")):
            try:
                mod = _load(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"plugin_load:{path.name}:{type(exc).__name__}")
                continue
            name = str(getattr(mod, "CHECK_NAME", "") or "").strip().lower()
            run = getattr(mod, "run", None)
            if not NAME_RE.match(name) or not callable(run):
                errors.append(f"plugin_malformed:{path.name}")
                continue
            if name in reserved:
                errors.append(f"plugin_shadows_builtin:{name}")
                continue
            if name in found:
                continue
            found[name] = {
                "run": run,
                "include_default": bool(getattr(mod, "INCLUDE_IN_DEFAULT", True)),
                "path": str(path),
            }
    if errors:
        found["_errors"] = {"errors": errors}
    return found
