"""FR #10244: a job worktree whose git admin dir lost gitdir/commondir/HEAD must be repaired,
and Clear must not prune such admin metadata while a live job tree still depends on it."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
CLEAR = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell") or not shutil.which("git"),
    reason="needs Windows PowerShell and git",
)


def test_repair_helper_defined_in_common_and_ascii():
    text = COMMON.read_text(encoding="utf-8")
    assert "function Repair-BobiverseJobWorktreeAdmin" in text
    assert "FR #10244" in text
    assert "git-still-broken" in text
    raw = COMMON.read_bytes()
    body = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    assert all(b < 0x80 for b in body), "Bobiverse-Common.ps1 must stay ASCII"


def test_clear_repairs_before_prune_and_skips_prune_when_unrepairable():
    text = CLEAR.read_text(encoding="utf-8")
    repair_at = text.index("Repair-BobiverseJobWorktreeAdmin -WorktreePath")
    prune_at = text.index("if (($counts.removed -gt 0 -or $Force) -and -not $admSkipPrune)")
    assert repair_at < prune_at, "admin repair pass must run before the prune gate"
    assert "skipping git worktree prune" in text


@WIN
def test_repair_rebuilds_missing_admin_files_and_git_works(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    wt = tmp_path / "wt" / "fr-10244"
    wt.parent.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-q", "-b", "fr-10244", str(wt), "main"],
        check=True,
    )
    adm = repo / ".git" / "worktrees" / "fr-10244"
    for name in ("gitdir", "commondir", "HEAD"):
        (adm / name).unlink()
    broken = subprocess.run(["git", "-C", str(wt), "rev-parse", "--git-dir"], capture_output=True)
    assert broken.returncode != 0

    script = tmp_path / "run_repair.ps1"
    script.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Continue'",
                f". '{COMMON}'",
                f"$first = Repair-BobiverseJobWorktreeAdmin -WorktreePath '{wt}'",
                f"$second = Repair-BobiverseJobWorktreeAdmin -WorktreePath '{wt}'",
                "Write-Output ('first=' + $first)",
                "Write-Output ('second=' + $second)",
            ]
        ),
        encoding="ascii",
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
    )
    assert "first=repaired" in r.stdout, r.stdout + r.stderr
    assert "second=ok" in r.stdout, r.stdout + r.stderr
    ok = subprocess.run(["git", "-C", str(wt), "rev-parse", "--git-dir"], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    branch = subprocess.run(
        ["git", "-C", str(wt), "branch", "--show-current"], capture_output=True, text=True
    )
    assert branch.stdout.strip() == "fr-10244"
