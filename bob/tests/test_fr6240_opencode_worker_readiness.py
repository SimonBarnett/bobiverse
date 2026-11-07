"""FR #6240: OpenCode Windows worker readiness — native search, worktree, gh auth."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "common" / "scripts"))
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_worker_readiness as ready  # noqa: E402

ASSERT = ROOT / "bob" / "scripts" / "Assert-BobOpencodeWorkerReadiness.ps1"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bob-setup-opencode" / "SKILL.md"
HELPER = ROOT / "common" / "scripts" / "opencode_worker_readiness.py"


def test_fr6240_helper_and_assert_exist():
    assert HELPER.is_file()
    assert ASSERT.is_file()
    text = ASSERT.read_text(encoding="utf-8-sig")
    assert "FR #6240" in text
    assert "hosts.yml" in text  # documented forbid
    assert "grep" in text.lower() or "native" in text.lower()


def test_fr6240_redact_secrets_strips_pats():
    raw = "Token: github_pat_ABCDEFG1234567890 and ghp_AAAABBBBCCCC"
    out = ready.redact_secrets(raw)
    assert "github_pat_" not in out
    assert "ghp_" not in out
    assert "[REDACTED]" in out


def test_fr6240_native_search_finds_files_without_grep(tmp_path: Path):
    (tmp_path / "a.py").write_text("# opencode marker\n", encoding="utf-8")
    (tmp_path / "b.cs").write_text("// unrelated\n", encoding="utf-8")
    (tmp_path / "note.md").write_text("OpenCode readiness\n", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("opencode in txt ignored\n", encoding="utf-8")
    r = ready.windows_native_search(tmp_path, needle="opencode", max_hits=10)
    assert r["ok"] is True
    assert r["tool"] == "pathlib"
    assert len(r["hits"]) >= 2
    assert all(h.endswith((".py", ".md", ".cs", ".ps1")) for h in r["hits"])
    assert not any(h.endswith(".txt") for h in r["hits"])


def test_fr6240_native_search_bounds_hits(tmp_path: Path):
    for i in range(8):
        (tmp_path / f"f{i}.py").write_text("opencode\n", encoding="utf-8")
    r = ready.windows_native_search(tmp_path, needle="opencode", max_hits=3)
    assert r["ok"] is True
    assert len(r["hits"]) == 3


def test_fr6240_worktree_authorized_inside_ok(tmp_path: Path):
    wt = tmp_path / "fr-6240"
    wt.mkdir()
    r = ready.classify_worktree_access(cwd=wt, worktree=wt, permission="authorized")
    assert r["ok"] is True
    assert r["state"] == "authorized"


def test_fr6240_worktree_cwd_outside_blocked(tmp_path: Path):
    wt = tmp_path / "job"
    other = tmp_path / "install"
    wt.mkdir()
    other.mkdir()
    r = ready.classify_worktree_access(cwd=other, worktree=wt, permission="authorized")
    assert r["ok"] is False
    assert r["blocker"] == "external_directory_risk"
    assert "consent" in r["next_step"].lower() or "CWD" in r["next_step"]


def test_fr6240_worktree_rejected_stays_blocked(tmp_path: Path):
    wt = tmp_path / "job"
    wt.mkdir()
    r = ready.classify_worktree_access(cwd=wt, worktree=wt, permission="rejected")
    assert r["ok"] is False
    assert r["blocker"] == "worktree_permission_rejected"
    assert "bypass" in r["next_step"].lower()


def test_fr6240_worktree_missing_permission_blocked(tmp_path: Path):
    wt = tmp_path / "job"
    wt.mkdir()
    r = ready.classify_worktree_access(cwd=wt, worktree=wt, permission="missing")
    assert r["ok"] is False
    assert r["blocker"] == "worktree_permission_missing"


def test_fr6240_gh_auth_missing_no_credential_hunt():
    r = ready.classify_gh_auth(
        exit_code=1,
        stdout="",
        stderr="To get started with GitHub CLI, please run: gh auth login\n",
    )
    assert r["ok"] is False
    assert r["blocker"] == "gh_auth_missing"
    assert "gh auth login" in r["next_step"]
    assert "hosts.yml" in r["next_step"] or "token" in r["next_step"].lower()
    # must not recommend hunting
    assert "agentic_irc" not in r["next_step"].lower()
    assert "search" not in r["next_step"].lower() or "Do not search" in r["next_step"]


def test_fr6240_gh_auth_ok_redacts_token_material():
    r = ready.classify_gh_auth(
        exit_code=0,
        stdout="✓ Logged in to github.com account Example (keyring)\nToken: github_pat_SECRETVALUEHERE\n",
        stderr="",
    )
    assert r["ok"] is True
    assert "github_pat_" not in r["detail"]
    assert "SECRET" not in r["detail"]


def test_fr6240_forbidden_paths_documented():
    paths = ready.forbidden_credential_probe_paths()
    joined = " ".join(paths).lower()
    assert "hosts.yml" in joined
    assert "agentic_irc" in joined


def test_fr6240_summarize_not_completed_when_blocked():
    s = ready.summarize_readiness(
        search={"ok": True},
        worktree={"ok": False, "blocker": "worktree_permission_rejected", "next_step": "ask"},
        gh={"ok": True},
    )
    assert s["ok"] is False
    assert s["completed"] is False
    assert "worktree_permission_rejected" in s["blockers"]


def test_fr6240_skill_documents_windows_readiness():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #6240" in text or "6240" in text
    assert "Select-String" in text or "Get-ChildItem" in text or "pathlib" in text
    assert "Assert-BobOpencodeWorkerReadiness" in text
    assert "gh auth login" in text
    assert "hosts.yml" in text
    # forbid is documented; primary recipe must be PowerShell/pathlib
    assert "Do **not** run" in text or "Do not" in text
    assert "Get-ChildItem" in text or "Select-String" in text or "pathlib" in text


def _run_assert(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ASSERT),
        *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def test_fr6240_assert_exits_2_when_permission_rejected(tmp_path: Path):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "x.py").write_text("opencode\n", encoding="utf-8")
    proc = _run_assert(
        [
            "-InstallRoot",
            str(wt),
            "-WorktreePath",
            str(wt),
            "-Permission",
            "rejected",
            "-SkipGhAuth",
        ]
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "worktree" in (proc.stdout + proc.stderr).lower()


def test_fr6240_assert_exits_3_when_gh_auth_missing(tmp_path: Path):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "x.py").write_text("opencode\n", encoding="utf-8")
    # cwd=wt so worktree ok; fixture missing gh via -File (preserves exit code)
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ASSERT),
            "-InstallRoot",
            str(wt),
            "-WorktreePath",
            str(wt),
            "-Permission",
            "authorized",
            "-GhAuthStderr",
            "To get started with GitHub CLI, please run: gh auth login",
            "-GhAuthExitCode",
            "1",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(wt),
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "gh" in combined.lower()
    assert "Do not" in combined or "hosts.yml" in combined


def test_fr6240_assert_ok_skip_gh_authorized_worktree(tmp_path: Path):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "x.py").write_text("opencode seat\n", encoding="utf-8")
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"Set-Location -LiteralPath '{wt}'; & '{ASSERT}' -InstallRoot '{wt}' "
            f"-WorktreePath '{wt}' -SkipGhAuth",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK FR #6240" in proc.stdout
