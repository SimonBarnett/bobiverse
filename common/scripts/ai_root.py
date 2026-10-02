"""The "<drive>:\\ai" root (t780u) - python twin of Get-BobiverseAiRoot in Bobiverse-Common.ps1.

Fleet trees live under ``<drive>:\\ai`` but the drive is not always C: (MarchHare kept repos and agent homes on D:\\ai).
Scan the FIXED physical disks (DriveType 3; removable / network / CD ignored). If several have an ``ai`` folder prefer the one
already holding bob/jeeves/airc/ergo installs, then the one the fleet services point at, then the system drive, then drive letter.
None found -> ``<SystemDrive>\\ai`` (created only on request). Env ``BOB_AI_ROOT`` overrides everything.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

PRODUCTS = ("bob", "jeeves", "airc", "ergo")
SERVICES = ("ircBob", "ircJeeves", "BobIrcd", "Airc")
DRIVE_FIXED = 3


@dataclass
class Disk:
    root: str  # e.g. "D:\\"
    drive_type: int


@dataclass
class Selection:
    path: str
    found: bool
    reason: str
    candidates: list[str] = field(default_factory=list)


def _norm(p: str) -> str:
    return str(p).replace("/", "\\").rstrip("\\")


def select_ai_root(
    disks: Sequence[Disk],
    service_dirs: Iterable[str] = (),
    system_drive: str = "C:",
    override: str = "",
) -> Selection:
    """Pure selection; ``disks`` come from :func:`fixed_disks` (tests inject their own)."""
    if override:
        return Selection(_norm(override), True, "BOB_AI_ROOT override")
    sys_root = system_drive.rstrip("\\") + "\\"
    cands: list[str] = []
    for d in disks:
        if int(d.drive_type) != DRIVE_FIXED:
            continue
        root = d.root if d.root.endswith(("\\", "/")) else d.root + "\\"
        ai = os.path.join(root, "ai")
        if os.path.isdir(ai):
            cands.append(_norm(ai))
    if not cands:
        return Selection(_norm(os.path.join(sys_root, "ai")), False, "no fixed disk has an ai folder; default is <SystemDrive>\\ai")
    if len(cands) == 1:
        return Selection(cands[0], True, "only fixed disk with an ai folder", cands)
    svc = [_norm(s).lower() for s in service_dirs if s]

    def score(c: str) -> tuple:
        inst = sum(1 for p in PRODUCTS if os.path.isdir(os.path.join(c, p)))
        n_svc = sum(1 for s in svc if s == c.lower() or s.startswith(c.lower() + "\\"))
        is_sys = 1 if os.path.splitdrive(c)[0].lower() == system_drive.rstrip("\\").lower() else 0
        return (-inst, -n_svc, -is_sys, c.lower())

    best = sorted(cands, key=score)[0]
    inst, n_svc, is_sys, _ = score(best)
    why = (f"holds {-inst} bob/jeeves/airc/ergo install folder(s)" if inst else
           "fleet services point at it" if n_svc else "system drive" if is_sys else "first by drive letter")
    return Selection(best, True, f"several fixed disks have ai; chose: {why}", cands)


def fixed_disks() -> list[Disk]:
    """Fixed physical disks only (GetDriveTypeW == DRIVE_FIXED). Non-Windows: no disks."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        mask = kernel32.GetLogicalDrives()
        out: list[Disk] = []
        for i in range(26):
            if mask & (1 << i):
                root = f"{chr(65 + i)}:\\"
                dt = int(kernel32.GetDriveTypeW(root))
                out.append(Disk(root, dt))
        return [d for d in out if d.drive_type == DRIVE_FIXED]
    except Exception:
        return []


def service_dirs() -> list[str]:
    """Directories the fleet services already run from (NSSM AppDirectory / ImagePath); empty off Windows."""
    dirs: list[str] = []
    try:
        import winreg  # type: ignore[import-not-found]

        for n in SERVICES:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SYSTEM\CurrentControlSet\Services\{n}") as k:
                    img, _ = winreg.QueryValueEx(k, "ImagePath")
                    if img:
                        dirs.append(str(img).strip('"'))
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SYSTEM\CurrentControlSet\Services\{n}\Parameters") as k:
                    ad, _ = winreg.QueryValueEx(k, "AppDirectory")
                    if ad:
                        dirs.append(str(ad))
            except OSError:
                continue
    except ImportError:
        pass
    return dirs


def find_ai_root(
    create: bool = False,
    disks: Sequence[Disk] | None = None,
    services: Iterable[str] | None = None,
    system_drive: str | None = None,
    env: dict | None = None,
) -> str:
    e = os.environ if env is None else env
    override = (e.get("BOB_AI_ROOT") or "").strip()
    sysd = system_drive or e.get("SystemDrive") or "C:"
    sel = select_ai_root(
        fixed_disks() if disks is None and not override else (disks or []),
        service_dirs() if services is None and not override else (services or []),
        sysd,
        override,
    )
    if create and not sel.found and not os.path.exists(sel.path):
        os.makedirs(sel.path, exist_ok=True)
    return sel.path


def product_root(product: str, **kw) -> str:
    return os.path.join(find_ai_root(**kw), product)