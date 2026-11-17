"""Helpers for airc Update-BobiverseService Check/Apply fixture tests (FR #8144)."""
from __future__ import annotations

import json
import os
from pathlib import Path

# Fixed SHAs so DryRun ReleaseJson checks do not trip FR #8112 unknown-provenance.
FIXTURE_INSTALLED_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def stamp_fixture_provenance(install_root: Path, release: dict | None = None) -> dict | None:
    """Write BUILD.json under the fixture InstallRoot; attach matching commit on release."""
    install_root = Path(install_root)
    install_root.mkdir(parents=True, exist_ok=True)
    (install_root / "BUILD.json").write_text(
        json.dumps(
            {
                "product": "airc",
                "version": (install_root / "VERSION").read_text(encoding="utf-8").strip()
                if (install_root / "VERSION").is_file()
                else "0.0.0",
                "commit": FIXTURE_INSTALLED_SHA,
            }
        ),
        encoding="utf-8",
    )
    if release is None:
        return None
    out = dict(release)
    out["commit"] = FIXTURE_INSTALLED_SHA
    out["target_commitish"] = FIXTURE_INSTALLED_SHA
    return out


def fixture_update_env(extra: dict | None = None) -> dict:
    """Env for Check/Apply subprocess: no live auto-update noise; allow hotpatch gate."""
    e = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "BOB_AUTOUPDATE",
            "BOBIVERSE_NO_UPDATE",
            "AIRC_INSTALL_ROOT",
            "BOBIVERSE_SELF_UPDATE_COMPARE_STATUS",
        )
    }
    e["BOB_CRASH_REPORT"] = "local-only"
    e["BOBIVERSE_CRASH_REPORT"] = "local-only"
    # Fixture InstallRoot has stamped BUILD.json; treat candidate as containing it.
    e["BOBIVERSE_SELF_UPDATE_COMPARE_STATUS"] = "ahead"
    if extra:
        e.update(extra)
    return e


def read_update_log(state_dir: Path) -> str:
    path = Path(state_dir) / "update.log"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8-sig")