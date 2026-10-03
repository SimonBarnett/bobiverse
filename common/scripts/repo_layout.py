"""Repo layout helper for the tests (t773u / FR #963: lives in common/scripts so sparse FR/MRB trees work).

The repo is split per service (common/ jeeves/ bob/ airc/, each with scripts/ .grok/skills/ docs/ tests/ ...) while a STAGED /
INSTALLED tree is flat. Tests keep reading files by their legacy flat relative path (``ROOT / "scripts" / "x.py"``,
``ROOT / "third_party" / "bob-tray"``, ``ROOT / "docs" / "x.md"`` ...); ``ROOT`` resolves each one to where it lives now.
The alias table mirrors ``Get-BobiverseRepoPath`` in common/scripts/Bobiverse-Common.ps1.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVICES = ("common", "jeeves", "bob", "airc")


def scripts_dirs() -> list[Path]:
    return [REPO / s / "scripts" for s in SERVICES if (REPO / s / "scripts").is_dir()]


def union_files(sub: str) -> list[Path]:
    """Every file directly inside <service>/<sub> for all services (the flat staged ``<sub>`` listing)."""
    out: list[Path] = []
    for s in SERVICES:
        d = REPO / s / sub
        if d.is_dir():
            out.extend(sorted(p for p in d.iterdir() if p.is_file()))
    return out


def resolve(rel: str) -> Path:
    r = rel.strip("/\\").replace("\\", "/")
    alias = None
    if r in ("src/VERSION", "VERSION"):
        alias = "common/VERSION"
    elif re.match(r"^bob-agents(/.*)?$", r):
        alias = "bob/agents" + r[len("bob-agents"):]
    elif re.match(r"^AGENTS\.(jeeves|bob|airc)\.md$", r):
        alias = r.split(".")[1] + "/AGENTS.md"
    elif r.startswith("packaging/airc/"):
        alias = "airc/packaging/" + r[len("packaging/airc/"):]
    elif re.match(r"^third_party/bob-tray(/.*)?$", r):  # t829u: first-class bob sources; legacy flat spellings keep resolving
        alias = "bob/tray" + r[len("third_party/bob-tray"):]
    elif re.match(r"^third_party/Watch-AgentHealth(/.*)?$", r):
        alias = "bob/agentwatcher" + r[len("third_party/Watch-AgentHealth"):]
    elif re.match(r"^(tray|agentwatcher)(/.*)?$", r):
        alias = "bob/" + r
    elif re.match(r"^third_party/(nssm|ergo|wix|bootstrap)(/.*)?$", r):
        alias = "common/" + r
    if alias:
        return REPO / alias
    for s in SERVICES:
        c = REPO / s / r
        if c.exists():
            return c
    return REPO / r


class Legacy(os.PathLike):
    """``ROOT / "scripts" / "x.py"`` -> the real path in the split repo (lazily, so every join keeps the legacy spelling)."""

    def __init__(self, parts: tuple[str, ...] = ()):
        self._parts = parts

    def _real(self) -> Path:
        return resolve("/".join(self._parts)) if self._parts else REPO

    def __truediv__(self, other) -> "Legacy":
        return Legacy(self._parts + (str(other).replace("\\", "/"),))

    def __fspath__(self) -> str:
        return str(self._real())

    def __str__(self) -> str:
        return str(self._real())

    def __repr__(self) -> str:
        return f"Legacy({self._real()!s})"

    def _union_dirs(self) -> list[Path]:
        rel = "/".join(self._parts)
        return [REPO / s / rel for s in SERVICES if (REPO / s / rel).is_dir()] if self._parts else [REPO]

    def glob(self, pattern):
        """Directory listing as the FLAT staged tree has it: the union over every service's <rel> dir."""
        for d in self._union_dirs():
            yield from d.glob(pattern)

    def rglob(self, pattern):
        for d in self._union_dirs():
            yield from d.rglob(pattern)

    def __getattr__(self, name):
        return getattr(self._real(), name)

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))


ROOT = Legacy()