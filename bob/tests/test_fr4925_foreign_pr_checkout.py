"""FR #4925: never gh pr checkout --repo other from bob install CWD.

Pins skill docs + Assert-BobiverseForeignPrCheckout.ps1 refuse/allow exits.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

ASSERT = ROOT / "common" / "scripts" / "Assert-BobiverseForeignPrCheckout.ps1"
MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
FLEET = ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"

WIN = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell assert is Windows-only")


def _read(path: Path) -> str:
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", f"BOM in {path}"
    return raw.decode("utf-8")


def test_fr4925_assert_script_exists_and_documents_refuse():
    text = _read(ASSERT)
    assert "FR #4925" in text
    assert "exit 2" in text
    assert "-Repo" in text
    assert "WarnOnly" in text
    assert "Get-BobiverseNormalizedOwnerRepo" in text or "simonbarnett/bobiverse" in text.lower()


def test_fr4925_skills_pin_cast_iron_and_assert_name():
    for path, label in ((MRB, "mrb"), (FR, "fr"), (FLEET, "fleet-ops")):
        t = _read(path)
        assert "FR #4925" in t, f"{label} missing FR #4925"
        assert "Assert-BobiverseForeignPrCheckout" in t, f"{label} missing Assert name"
        assert "gh pr checkout" in t.lower() or "Foreign" in t


def test_fr4925_mrb_mermaid_avoids_install_checkout():
    t = _read(MRB)
    # Mermaid must steer to temp worktree, not bare gh pr checkout from install.
    assert "%TEMP%" in t or "temp worktree" in t.lower()
    assert "never gh pr checkout" in t.lower() or "never run `gh pr checkout" in t.lower()


@WIN
def test_fr4925_assert_refuse_when_origin_bobiverse_repo_differs(tmp_path: Path):
    repo = tmp_path / "install"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/SimonBarnett/bobiverse.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(ASSERT),
            "-Repo",
            "SimonBarnett/a-search",
            "-Path",
            str(repo),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "REFUSE" in (r.stdout + r.stderr) or "FR #4925" in (r.stdout + r.stderr)


@WIN
def test_fr4925_assert_allow_same_repo(tmp_path: Path):
    repo = tmp_path / "install"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:SimonBarnett/bobiverse.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(ASSERT),
            "-Repo",
            "SimonBarnett/bobiverse",
            "-Path",
            str(repo),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)


@WIN
def test_fr4925_assert_allow_non_bobiverse_origin(tmp_path: Path):
    repo = tmp_path / "product"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/SimonBarnett/a-search.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(ASSERT),
            "-Repo",
            "SimonBarnett/a-search",
            "-Path",
            str(repo),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
