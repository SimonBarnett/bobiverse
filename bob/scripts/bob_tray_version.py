"""FR #6924: tray product label = MSI VERSION + optional deployed short SHA.

``VERSION`` / ARP stay the MSI ProductVersion. The short SHA comes from a
deployed identity file (prefer ``MANIFEST.json``, else ``provenance.txt``,
else ``HOTPATCH.json`` / ``BUILD.json``) so Sync/hotpatch can move the label
without a new MSI.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional

_HEX = re.compile(r"^[0-9a-fA-F]{7,40}$")
_JSON_KEYS = ("source_commit", "workflow_commit", "commit", "hotpatch_commit", "sha")
_PROV_KEYS = ("source_commit", "workflow_commit", "commit")


def short_sha(raw: str) -> str:
    """Return lowercase 7-char hex prefix, or empty if not a git SHA-ish token."""
    s = (raw or "").strip()
    if not s or not _HEX.match(s):
        return ""
    return s.lower()[:7]


def _first_line(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            return (fh.readline() or "").strip()
    except OSError:
        return ""


def read_product_version(root: Path | str, *, env: Optional[Mapping[str, str]] = None) -> str:
    """MSI/VERSION number only (never invent a marketing version)."""
    e = env if env is not None else os.environ
    v = (e.get("BOBIVERSE_BOB_VERSION") or "").strip()
    if v:
        return v
    root_p = Path(root)
    ai = (e.get("BOB_AI_ROOT") or "").strip()
    cands = [
        root_p / "VERSION",
        root_p / "src" / "VERSION",
    ]
    if ai:
        cands.append(Path(ai) / "bob" / "VERSION")
    parent = root_p.parent
    cands.append(parent / "bob" / "VERSION")
    for c in cands:
        t = _first_line(c)
        if t:
            return t
    return "unknown"


def _sha_from_mapping(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in _JSON_KEYS:
        got = short_sha(str(data.get(key) or ""))
        if got:
            return got
    return ""


def _sha_from_json_file(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ""
    return _sha_from_mapping(data)


def _sha_from_provenance(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""
    found: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip().lower()
        if k in _PROV_KEYS:
            got = short_sha(v)
            if got:
                found[k] = got
    for key in _PROV_KEYS:
        if key in found:
            return found[key]
    return ""


def _sha_from_root_identity(root_p: Path) -> str:
    """Install-root (or CI stage) identity: MANIFEST, provenance, HOTPATCH, BUILD."""
    got = _sha_from_json_file(root_p / "MANIFEST.json")
    if got:
        return got
    got = _sha_from_provenance(root_p / "provenance.txt")
    if got:
        return got
    for name in ("HOTPATCH.json", "BUILD.json"):
        got = _sha_from_json_file(root_p / name)
        if got:
            return got
    return ""


def read_exe_source_sha(root: Path | str) -> str:
    """SHA of the running tray binaries (FR #7247): tools\\MANIFEST first.

    Slab copies the CI artifact next to ``tools\\bob-tray.exe``. Install-root
    MANIFEST.json is the scripts / Sync identity and may be older.
    """
    root_p = Path(root)
    tools = root_p / "tools"
    if root_p.name.lower() == "tools":
        tools = root_p
    got = _sha_from_json_file(tools / "MANIFEST.json")
    if got:
        return got
    got = _sha_from_provenance(tools / "provenance.txt")
    if got:
        return got
    return ""


def read_scripts_source_sha(root: Path | str) -> str:
    """SHA of the running display/engine scripts (install-root identity)."""
    root_p = Path(root)
    if root_p.name.lower() == "tools":
        parent = root_p.parent
        if parent:
            got = _sha_from_root_identity(parent)
            if got:
                return got
    return _sha_from_root_identity(root_p)


def format_running_build_sha(exe_sha: str, scripts_sha: str) -> str:
    """One short SHA, or ``exe aaa / scripts bbb`` when the two builds differ."""
    exe = (exe_sha or "").strip()
    scripts = (scripts_sha or "").strip()
    if exe and scripts and exe != scripts:
        return f"exe {exe} / scripts {scripts}"
    return exe or scripts


def read_deployed_source_sha(root: Path | str) -> str:
    """FR #6924 / #7247: running-build token for the footer (may be a pair)."""
    return format_running_build_sha(read_exe_source_sha(root), read_scripts_source_sha(root))


def product_version_label(root: Path | str, *, env: Optional[Mapping[str, str]] = None) -> str:
    """Full tip/About/Status string, e.g. ``bob 1.0.3`` or ``bob 1.0.3 (8622b03)``."""
    ver = read_product_version(root, env=env)
    sha = read_deployed_source_sha(root)
    if sha:
        return f"bob {ver} ({sha})"
    return f"bob {ver}"


def bob_version_token(root: Path | str, *, env: Optional[Mapping[str, str]] = None) -> str:
    """C# ``Common.BobVersion`` body (About/Status prefix ``bob `` themselves)."""
    ver = read_product_version(root, env=env)
    sha = read_deployed_source_sha(root)
    if sha:
        return f"{ver} ({sha})"
    return ver
