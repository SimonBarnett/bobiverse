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


def read_deployed_source_sha(root: Path | str) -> str:
    """Prefer MANIFEST.json, else provenance.txt, else HOTPATCH/BUILD commit."""
    root_p = Path(root)
    for name in ("MANIFEST.json",):
        got = _sha_from_json_file(root_p / name)
        if got:
            return got
    for rel in ("provenance.txt", Path("tools") / "provenance.txt"):
        got = _sha_from_provenance(root_p / rel)
        if got:
            return got
    for name in ("HOTPATCH.json", "BUILD.json"):
        got = _sha_from_json_file(root_p / name)
        if got:
            return got
    return ""


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
