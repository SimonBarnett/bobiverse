"""Download latest airc MSI + .sha256 from GitHub Releases (FR #3991)."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Optional

from .core import AIRC_ASSET_PREFIX, REPO


def _get_json(url: str, *, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "bobiverse-airc-network-installer"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path, *, timeout: float = 300.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "bobiverse-airc-network-installer"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def parse_sha256_sidecar(text: str, expected_name: str) -> str:
    """Parse `hash  filename` or bare hash lines; return lowercase hex."""
    want = expected_name.lower()
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) == 1 and len(parts[0]) == 64:
            return parts[0].lower()
        if len(parts) >= 2 and parts[-1].lower().endswith(want):
            return parts[0].lower()
        if len(parts) >= 2 and parts[0].lower() == want:
            return parts[1].lower()
    raise RuntimeError(f"no sha256 entry for {expected_name} in sidecar")


def download_latest_airc_msi(
    dest_dir: Path,
    *,
    repo: str = REPO,
    opener=_get_json,
    downloader=_download,
) -> tuple[Path, str]:
    """
    Always fetch the Latest release airc-*.msi and its .sha256 asset.
    Returns (msi_path, tag_name). Refuses on hash mismatch.
    """
    api = f"https://api.github.com/repos/{repo}/releases/latest"
    data = opener(api)
    tag = str(data.get("tag_name") or "unknown")
    assets = list(data.get("assets") or [])
    msi_asset = None
    sha_asset = None
    for asset in assets:
        name = str(asset.get("name") or "")
        low = name.lower()
        if low.startswith(AIRC_ASSET_PREFIX) and low.endswith(".msi"):
            msi_asset = asset
        if low.startswith(AIRC_ASSET_PREFIX) and low.endswith(".msi.sha256"):
            sha_asset = asset
    if msi_asset is None:
        raise RuntimeError(f"No airc-*.msi asset in release {tag}")
    msi_name = str(msi_asset["name"])
    dest = dest_dir / msi_name
    downloader(str(msi_asset["browser_download_url"]), dest)
    got = sha256_file(dest)
    if sha_asset is None:
        # sibling name convention
        raise RuntimeError(f"No {msi_name}.sha256 asset in release {tag}")
    sha_path = dest_dir / str(sha_asset["name"])
    downloader(str(sha_asset["browser_download_url"]), sha_path)
    expect = parse_sha256_sidecar(sha_path.read_text(encoding="utf-8"), msi_name)
    if got != expect:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"sha256 mismatch for {msi_name}: got {got} expect {expect}")
    return dest, tag
