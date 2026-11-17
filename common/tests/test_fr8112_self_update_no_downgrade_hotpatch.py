"""FR #8112: self-update must not downgrade a newer hotpatched build."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import self_update_provenance as prov
from repo_layout import ROOT

UPD = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")
REPO = "SimonBarnett/bobiverse"

# Fixed SHAs for ancestry scenarios (not real network compares).
INSTALLED = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # hotpatch tip X
ANCESTOR = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"  # release older than X
DESCENDANT = "cccccccccccccccccccccccccccccccccccccccc"  # release containing X


def test_fr8112_ancestor_release_refuses_update():
    allow, reason = prov.decide_update_vs_hotpatch(
        installed_sha=INSTALLED,
        candidate_sha=ANCESTOR,
        ancestry="behind",
    )
    assert allow is False
    assert reason == "candidate-behind-installed"
    log = prov.format_skip_log(
        installed_sha=INSTALLED, candidate_sha=ANCESTOR, reason=reason
    )
    assert "skipped-hotpatch-newer" in log
    assert "installed_sha=" + INSTALLED[:7] in log or INSTALLED in log
    assert "candidate_sha=" + ANCESTOR in log
    assert "reason=candidate-behind-installed" in log


def test_fr8112_release_containing_installed_allows_update():
    allow, reason = prov.decide_update_vs_hotpatch(
        installed_sha=INSTALLED,
        candidate_sha=DESCENDANT,
        ancestry="ahead",
    )
    assert allow is True
    assert reason == "ahead"


def test_fr8112_unknown_installed_provenance_refuses():
    allow, reason = prov.decide_update_vs_hotpatch(
        installed_sha="",
        candidate_sha=DESCENDANT,
        ancestry="ahead",
    )
    assert allow is False
    assert reason == "unknown-installed-provenance"
    log = prov.format_skip_log(
        installed_sha="", candidate_sha=DESCENDANT, reason=reason
    )
    assert "skipped-hotpatch-newer" in log
    assert "installed_sha=unknown" in log
    assert "reason=unknown-installed-provenance" in log


def test_fr8112_read_installed_commit_from_build_json(tmp_path: Path):
    (tmp_path / "BUILD.json").write_text(
        json.dumps(
            {
                "product": "airc",
                "version": "1.0.7",
                "commit": "c641df7b",
            }
        ),
        encoding="utf-8",
    )
    assert prov.read_installed_commit(tmp_path) == "c641df7b"


def test_fr8112_identical_shas_allow():
    allow, reason = prov.decide_update_vs_hotpatch(
        installed_sha=INSTALLED,
        candidate_sha=INSTALLED,
        ancestry="behind",  # ignored when equal
    )
    assert allow is True
    assert reason == "identical"


def _release(ver: str, product: str = "airc", commit: str = "") -> dict:
    base = f"https://github.com/{REPO}/releases/download/v{ver}"
    assets = [
        {
            "name": f"{product}-{ver}.msi",
            "browser_download_url": f"{base}/{product}-{ver}.msi",
        },
        {
            "name": f"{product}-{ver}.msi.sha256",
            "browser_download_url": f"{base}/{product}-{ver}.msi.sha256",
        },
    ]
    body = {"tag_name": f"v{ver}", "assets": assets}
    if commit:
        body["commit"] = commit
        body["target_commitish"] = commit
    return body


@pytest.fixture
def env(tmp_path: Path):
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n", encoding="utf-8")
    state = tmp_path / "state"

    def run(*extra, release=None, envvars=None, product="airc"):
        args = [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPD),
            "-Product",
            product,
            "-InstallRoot",
            str(root),
            "-StateDir",
            str(state),
            "-Mode",
            "Check",
            "-DryRun",
        ]
        if release is not None:
            rj = tmp_path / "release.json"
            rj.write_text(json.dumps(release), encoding="utf-8")
            args += ["-ReleaseJson", str(rj)]
        args += list(extra)
        e = {
            k: v
            for k, v in os.environ.items()
            if k not in ("BOB_AUTOUPDATE", "BOBIVERSE_NO_UPDATE")
        }
        e["BOB_CRASH_REPORT"] = "local-only"
        e["BOBIVERSE_CRASH_REPORT"] = "local-only"
        e.update(envvars or {})
        p = subprocess.run(args, capture_output=True, text=True, env=e, timeout=120)
        log = (state / "update.log").read_text() if (state / "update.log").exists() else ""
        return p, log

    run.root, run.state, run.tmp = root, state, tmp_path
    return run


@win
def test_fr8112_ps1_skips_when_candidate_behind_hotpatch(env):
    (env.root / "BUILD.json").write_text(
        json.dumps({"product": "airc", "version": "0.1.16", "commit": INSTALLED}),
        encoding="utf-8",
    )
    p, log = env(
        release=_release("0.1.17", commit=ANCESTOR),
        envvars={"BOBIVERSE_SELF_UPDATE_COMPARE_STATUS": "behind"},
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "skipped-hotpatch-newer" in log
    assert "would-update" not in log
    assert INSTALLED in log
    assert ANCESTOR in log
    assert "candidate-behind-installed" in log


@win
def test_fr8112_ps1_allows_when_release_contains_hotpatch(env):
    (env.root / "BUILD.json").write_text(
        json.dumps({"product": "airc", "version": "0.1.16", "commit": INSTALLED}),
        encoding="utf-8",
    )
    p, log = env(
        release=_release("0.1.17", commit=DESCENDANT),
        envvars={"BOBIVERSE_SELF_UPDATE_COMPARE_STATUS": "ahead"},
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "would-update" in log
    assert "skipped-hotpatch-newer" not in log


@win
def test_fr8112_ps1_skips_unknown_installed_provenance(env):
    # No BUILD.json commit
    p, log = env(
        release=_release("0.1.17", commit=DESCENDANT),
        envvars={"BOBIVERSE_SELF_UPDATE_COMPARE_STATUS": "ahead"},
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "skipped-hotpatch-newer" in log
    assert "unknown-installed-provenance" in log
    assert "would-update" not in log
