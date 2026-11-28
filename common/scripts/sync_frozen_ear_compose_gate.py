"""FR #10023: refuse flat scripts\\ compose when frozen bob-ear.exe lags tip behavior sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# Same list as bob/tests/test_fr6254_ear_build_provenance_align.py (deploy note paths).
BEHAVIOR_REL_PATHS = (
    "common/scripts/bobreport.py",
    "common/scripts/irc_agent.py",
    "common/scripts/opencode_fuel.py",
    "common/scripts/bobiverse_build.py",
    "bob/tray/src/Public/Get-BobTrayHover.ps1",
    "bob/tray/src/Private/Get-BobIrc.ps1",
    "bob/tray/tools/Watch-BobTray.ps1",
    "bob/tray/tools/Get-BobOpencodeFuel.ps1",
    "bob/tray/src/BobBridge.psm1",
)


def _norm_sha(data: bytes) -> str:
    data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(data).hexdigest()


def behavior_bundle_sha(repo_root: Path) -> str | None:
    """CRLF-canonical aggregate sha256 of BEHAVIOR_REL_PATHS (FR #6254 deploy note shape)."""
    root = Path(repo_root)
    parts: list[str] = []
    for rel in BEHAVIOR_REL_PATHS:
        p = root / rel.replace("/", "\\")
        if not p.is_file():
            p = root / rel
        if not p.is_file():
            return None
        parts.append(_norm_sha(p.read_bytes()))
    return hashlib.sha256("|".join(parts).encode("ascii")).hexdigest()


def parse_provenance_source_commit(prov_path: Path) -> str | None:
    if not prov_path.is_file():
        return None
    text = prov_path.read_text(encoding="utf-8-sig", errors="replace")
    for line in text.splitlines():
        m = re.match(r"^source_commit=([0-9a-fA-F]{7,40})\s*$", line.strip())
        if m:
            return m.group(1).lower()
        m = re.match(r"^behavior_source_sha=([0-9a-fA-F]{7,40})\s*$", line.strip())
        if m:
            return m.group(1).lower()
    return None


def git_head_sha(repo_root: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = (out or "").strip().lower()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def commits_compatible(ear_commit: str, tip_commit: str) -> bool:
    a = (ear_commit or "").strip().lower()
    b = (tip_commit or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    # Short provenance may prefix-match full HEAD.
    if len(a) < 40 and b.startswith(a):
        return True
    if len(b) < 40 and a.startswith(b):
        return True
    return False


def frozen_ear_scripts_compose_blocked(
    install_root: Path,
    clone_root: Path,
) -> tuple[bool, str]:
    """Return (blocked, log_line). Fail open when ear exe or provenance missing."""
    ear = install_root / "scripts" / "bob-ear.exe"
    if not ear.is_file():
        return False, ""
    prov = install_root / "scripts" / "provenance.txt"
    ear_commit = parse_provenance_source_commit(prov)
    tip_commit = git_head_sha(clone_root)
    if not ear_commit or not tip_commit:
        return False, ""
    if commits_compatible(ear_commit, tip_commit):
        return False, ""
    tip_bundle = behavior_bundle_sha(clone_root)
    msg = (
        "sync-skip-frozen-ear-scripts "
        f"ear_source={ear_commit[:12]} tip_head={tip_commit[:12]}"
        f"{(' tip_behavior_bundle=' + tip_bundle[:12]) if tip_bundle else ''}"
        " - rebuild/Install-BobEarExe or MSI >= tip before flat scripts overlay (FR #10023)"
    )
    return True, msg


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--install", required=True, type=Path)
    p.add_argument("--clone", required=True, type=Path)
    args = p.parse_args(argv)
    blocked, line = frozen_ear_scripts_compose_blocked(args.install, args.clone)
    print(json.dumps({"blocked": blocked, "line": line}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())