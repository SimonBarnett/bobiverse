"""FR #7432: install .git/info/exclude must un-ignore .github/workflows for job worktrees."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON_PS1 = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
FR_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"


def test_fr7432_exclude_template_unignores_github():
    text = COMMON_PS1.read_text(encoding="utf-8")
    assert "function Get-BobiverseInstallGitExcludeText" in text
    assert "!/.github/" in text
    assert "!/.github/**" in text
    assert "7432" in text


def test_fr7432_fr_skill_documents_github_unignore():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "7432" in text
    assert ".github" in text
    assert "git add -f" in text


@pytest.mark.skipif(not (Path(sys.executable).exists()), reason="python required")
def test_fr7432_exclude_text_allows_github_workflow_add(tmp_path: Path):
    """Generated exclude must let plain git add stage .github/workflows without -f."""
    ps = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f". '{COMMON_PS1}'; "
                "Get-BobiverseInstallGitExcludeText -Product bob"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ps.returncode == 0, ps.stderr
    exclude = ps.stdout
    assert "!/.github/" in exclude
    assert "!/.github/**" in exclude

    repo = tmp_path / "r"
    (repo / ".git" / "info").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "bob").mkdir()
    (repo / ".github" / "workflows" / "build-x.yml").write_text("name: x\n", encoding="utf-8")
    (repo / ".git" / "info" / "exclude").write_text(exclude, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    add = subprocess.run(
        ["git", "add", ".github/workflows/build-x.yml"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert add.returncode == 0, add.stderr
    st = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "build-x.yml" in st.stdout
    assert "?? .github" not in st.stdout  # staged, not untracked-ignored
