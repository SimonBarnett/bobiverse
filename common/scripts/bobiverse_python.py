"""FR #7020: resolve a real python.exe for LocalSystem / NSSM services.

Order (first existing file wins; never returns the Microsoft Store stub):
1. configured env ``BOBIVERSE_PYTHON`` / ``BOB_PYTHON``
2. install stamp ``<InstallRoot>\\config\\python.path`` (path only; written at MSI)
3. HKLM ``SOFTWARE\\Python\\PythonCore\\*\\InstallPath``
4. ``py -3`` launcher
5. ``PATH`` (``python`` / ``python3``)
6. well-known filesystem locations

Never logs secrets. Returns ``(path_or_None, source_tag)``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


_STORE_STUB = "\\windowsapps\\"
_STAMP_REL = ("config", "python.path")


def _is_real_python(path: str | Path | None) -> bool:
    if not path:
        return False
    text = str(path).strip().strip('"')
    if not text:
        return False
    low = text.replace("/", "\\").lower()
    if _STORE_STUB in low:
        return False
    try:
        return Path(text).is_file()
    except OSError:
        return False


def _install_root(env: dict | None = None) -> Path | None:
    e = env if env is not None else os.environ
    for key in ("BOB_INSTALL_ROOT", "BOBIVERSE_INSTALL_ROOT"):
        raw = str(e.get(key) or "").strip().rstrip("\\/")
        if raw:
            return Path(raw)
    return None


def python_stamp_path(env: dict | None = None) -> Path | None:
    root = _install_root(env)
    if root is None:
        return None
    return root.joinpath(*_STAMP_REL)


def write_python_stamp(exe: str, env: dict | None = None) -> Path | None:
    """Write path-only stamp for later SYSTEM resolve. Never writes secrets."""
    stamp = python_stamp_path(env)
    if stamp is None or not _is_real_python(exe):
        return None
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(Path(exe)) + "\n", encoding="utf-8")
        return stamp
    except OSError:
        return None


def _from_env(env: dict) -> tuple[str | None, str]:
    for key in ("BOBIVERSE_PYTHON", "BOB_PYTHON"):
        raw = str(env.get(key) or "").strip().strip('"')
        if _is_real_python(raw):
            return str(Path(raw)), f"env:{key}"
    return None, ""


def _from_stamp(env: dict) -> tuple[str | None, str]:
    stamp = python_stamp_path(env)
    if stamp is None or not stamp.is_file():
        return None, ""
    try:
        raw = (stamp.read_text(encoding="utf-8-sig") or "").strip().splitlines()
    except OSError:
        return None, ""
    if not raw:
        return None, ""
    text = raw[0].strip().strip('"')
    if _is_real_python(text):
        return str(Path(text)), "stamp:config/python.path"
    return None, ""


def _from_registry() -> tuple[str | None, str]:
    if os.name != "nt":
        return None, ""
    try:
        import winreg
    except ImportError:
        return None, ""
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Python\PythonCore"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Python\PythonCore"),
    )
    versions: list[str] = []
    for hive, base in roots:
        try:
            with winreg.OpenKey(hive, base) as key:
                i = 0
                while True:
                    try:
                        versions.append(winreg.EnumKey(key, i))
                        i += 1
                    except OSError:
                        break
        except OSError:
            continue
    # Prefer higher version tags (3.13 before 3.12 ...).
    for ver in sorted(set(versions), reverse=True):
        for hive, base in roots:
            try:
                with winreg.OpenKey(hive, rf"{base}\{ver}\InstallPath") as ip:
                    val, _ = winreg.QueryValueEx(ip, None)
            except OSError:
                continue
            if not isinstance(val, str) or not val.strip():
                continue
            exe = Path(val.strip()) / "python.exe"
            if _is_real_python(exe):
                return str(exe), f"registry:PythonCore\\{ver}"
    return None, ""


def _from_py_launcher() -> tuple[str | None, str]:
    py = shutil.which("py") or shutil.which("py.exe")
    if not py:
        return None, ""
    try:
        r = subprocess.run(
            [py, "-3", "-c", "import sys;print(sys.executable)"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, ""
    line = (r.stdout or "").strip().splitlines()
    if not line:
        return None, ""
    exe = line[-1].strip().strip('"')
    if _is_real_python(exe):
        return str(Path(exe)), "py-launcher"
    return None, ""


def _from_path() -> tuple[str | None, str]:
    for name in ("python", "python3", "python.exe", "python3.exe"):
        found = shutil.which(name)
        if _is_real_python(found):
            return str(Path(found)), f"path:{name}"
    return None, ""


def _from_filesystem() -> tuple[str | None, str]:
    cands: list[str] = []
    for ver in ("313", "312", "311", "310"):
        cands.extend(
            [
                rf"C:\Python\Python{ver}\python.exe",
                rf"C:\Python{ver}\python.exe",
            ]
        )
        pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
        cands.append(str(Path(pf) / f"Python{ver}" / "python.exe"))
        la = os.environ.get("LOCALAPPDATA") or ""
        if la:
            cands.append(
                str(Path(la) / "Programs" / "Python" / f"Python{ver}" / "python.exe")
            )
        # SYSTEM often cannot see interactive LOCALAPPDATA; probe common seats.
        for user in ("Administrator", "Si", "simon"):
            cands.append(
                str(
                    Path(os.environ.get("SystemDrive") or "C:")
                    / "Users"
                    / user
                    / "AppData"
                    / "Local"
                    / "Programs"
                    / "Python"
                    / f"Python{ver}"
                    / "python.exe"
                )
            )
    for c in cands:
        if _is_real_python(c):
            return str(Path(c)), "filesystem"
    return None, ""


def resolve_service_python(
    env: dict | None = None,
) -> tuple[str | None, str]:
    """Return ``(python_exe|None, source_tag)``. Empty source when not found."""
    e = dict(env) if env is not None else dict(os.environ)
    for fn in (
        lambda: _from_env(e),
        lambda: _from_stamp(e),
        _from_registry,
        _from_py_launcher,
        _from_path,
        _from_filesystem,
    ):
        path, src = fn()
        if path:
            return path, src
    return None, "missing"


def resolve_service_python_or_raise(env: dict | None = None) -> str:
    path, src = resolve_service_python(env)
    if not path:
        raise FileNotFoundError(
            "python.exe not found for service "
            "(set BOBIVERSE_PYTHON / config\\python.path / install Python)"
        )
    # Touch stamp when we resolved from a non-stamp source so later ticks are fast.
    if src and not src.startswith("stamp:"):
        write_python_stamp(path, env)
    return path
