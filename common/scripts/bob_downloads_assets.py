"""FR #7410: resolve bob / jeeves / airc MSI assets from a GitHub Releases payload.

Asset-name policy (pin in tests + PR):
  1. Prefer stable alias `{product}-latest.msi` when present on the latest release.
  2. Else use versioned `{product}-{X.Y.Z}.msi` (semver digits only).
  3. Ignore network-installer and non-MSI companions for the primary button.
  4. Optional sha256: same basename + `.sha256` when uploaded.
  5. Public URL shape:
     https://github.com/SimonBarnett/bobiverse/releases/latest/download/{asset_name}

Products: bob (Bob ear), jeeves, airc.
"""
from __future__ import annotations

from pathlib import Path

import json
import re
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen

PRODUCTS = ("bob", "jeeves", "airc")
REPO = "SimonBarnett/bobiverse"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_BASE = f"https://github.com/{REPO}/releases/latest/download"

_VERSIONED = re.compile(
    r"^(?P<product>bob|jeeves|airc)-(?P<ver>\d+\.\d+\.\d+)\.msi$",
    re.IGNORECASE,
)
_ALIAS = re.compile(
    r"^(?P<product>bob|jeeves|airc)-latest\.msi$",
    re.IGNORECASE,
)


def _asset_names(payload: Mapping[str, Any]) -> list[str]:
    assets = payload.get("assets") or []
    names: list[str] = []
    for a in assets:
        if isinstance(a, Mapping):
            name = a.get("name")
            if isinstance(name, str) and name:
                names.append(name)
        elif isinstance(a, str):
            names.append(a)
    return names


def pick_product_msi(names: Iterable[str], product: str) -> str | None:
    """Pick the MSI asset name for one product under the FR #7410 policy."""
    product = product.lower()
    name_list = list(names)
    alias = f"{product}-latest.msi"
    for n in name_list:
        if n.lower() == alias:
            return n
    versioned: list[tuple[tuple[int, int, int], str]] = []
    for n in name_list:
        m = _VERSIONED.match(n)
        if not m:
            continue
        if m.group("product").lower() != product:
            continue
        ver = tuple(int(x) for x in m.group("ver").split("."))
        versioned.append((ver, n))
    if not versioned:
        return None
    versioned.sort(key=lambda t: t[0], reverse=True)
    return versioned[0][1]


def resolve_latest_assets(payload: Mapping[str, Any]) -> dict[str, dict[str, str | None]]:
    """Map product -> {msi, sha256, url, sha256_url, tag}."""
    names = _asset_names(payload)
    lower_set = {n.lower(): n for n in names}
    tag = payload.get("tag_name") or payload.get("name") or ""
    out: dict[str, dict[str, str | None]] = {}
    for product in PRODUCTS:
        msi = pick_product_msi(names, product)
        sha = None
        if msi:
            sha_key = (msi + ".sha256").lower()
            sha = lower_set.get(sha_key)
        out[product] = {
            "msi": msi,
            "sha256": sha,
            "url": f"{DOWNLOAD_BASE}/{msi}" if msi else None,
            "sha256_url": f"{DOWNLOAD_BASE}/{sha}" if sha else None,
            "tag": str(tag) if tag else None,
        }
    return out


def fetch_latest_release(timeout: float = 30.0) -> dict[str, Any]:
    req = Request(
        LATEST_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-fr-7410-downloads",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="FR #7410 resolve latest bob/jeeves/airc MSIs")
    p.add_argument("--json-file", help="Offline release JSON (skip network)")
    p.add_argument("--pretty", action="store_true")
    args = p.parse_args(argv)
    if args.json_file:
        payload = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    else:
        payload = fetch_latest_release()
    resolved = resolve_latest_assets(payload)
    text = json.dumps(resolved, indent=2 if args.pretty else None, sort_keys=True)
    sys.stdout.write(text + ("\n" if not text.endswith("\n") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
