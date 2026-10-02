"""Thin GitHub filer: shells out to `gh issue create` (real); Fake path for tests.

Bobiverse flat-script surface for ``intake.GitHubFiler``. Draft PRs are not
implemented here — ``intake.file_submission`` falls back to an issue listing.

Auth: ``GH_TOKEN`` / ``GITHUB_TOKEN`` env, else ``~/.grok/bob/github.token``
(one line). Missing labels are retried without ``--label`` so intake still files.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from intake import FakeGitHubFiler, GitHubDown, GitHubFiler

__all__ = [
    "FakeGitHubFiler",
    "GitHubDown",
    "GitHubFiler",
    "GhCliFiler",
    "default_filer",
    "ensure_gh_token_env",
]

_ISSUE_NUM = re.compile(r"/issues/(\d+)\s*$")
_LABEL_FAIL = re.compile(r"(?i)label|not found|could not add")


def _token_candidate_paths() -> list[Path]:
    """Paths to try for a one-line GitHub token (LocalSystem-safe)."""
    paths: list[Path] = [Path.home() / ".grok" / "bob" / "github.token"]
    # airc/bobcallback often run as LocalSystem; interactive gh auth is under Administrator.
    paths.append(Path(r"C:\Users\Administrator\.grok\bob\github.token"))
    paths.append(Path(r"C:\ai\jeeves\config\github.token"))
    # #53: the jeeves install owns the webhook receiver: <InstallRoot>\config\github.token
    # next to scripts\ (works for any InstallRoot, not just C:\ai\jeeves).
    paths.insert(0, Path(__file__).resolve().parent.parent / "config" / "github.token")
    cfg_env = (os.environ.get("BOB_CONFIG_DIR") or "").strip()
    if cfg_env:
        paths.insert(0, Path(cfg_env).expanduser() / "github.token")
    digest = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
    if digest:
        paths.append(Path(digest) / "github.token")
        paths.append(Path(digest) / "config" / "github.token")
    return paths


def ensure_gh_token_env() -> str:
    """Ensure GH_TOKEN is set for subprocess gh. Returns token source tag (never value)."""
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = (os.environ.get(name) or "").strip()
        if v:
            if name == "GITHUB_TOKEN" and not (os.environ.get("GH_TOKEN") or "").strip():
                os.environ["GH_TOKEN"] = v
            return f"env:{name}"
    for path in _token_candidate_paths():
        try:
            if path.is_file():
                tok = path.read_text(encoding="utf-8").strip()
                if tok:
                    os.environ["GH_TOKEN"] = tok
                    return f"file:{path}"
        except OSError:
            continue
    return "none"


class GhCliFiler:
    """Production filer: ``gh issue create -R <repo>``."""

    def __init__(self, gh_bin: str | None = None) -> None:
        ensure_gh_token_env()
        which = shutil.which("gh") if not gh_bin else shutil.which(gh_bin) or gh_bin
        self.gh_bin = which or "gh"

    def _run_create(self, repo: str, title: str, body: str, labels: list[str]) -> subprocess.CompletedProcess[str]:
        cmd = [
            self.gh_bin,
            "issue",
            "create",
            "-R",
            str(repo),
            "--title",
            str(title),
            "--body",
            str(body or ""),
        ]
        for lab in labels or []:
            cmd.extend(["--label", str(lab)])
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=os.environ.copy(),
        )

    @staticmethod
    def _parse_issue(stdout: str) -> dict[str, Any]:
        url = ""
        for line in reversed((stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("http"):
                url = line
                break
        number = 0
        m = _ISSUE_NUM.search(url)
        if m:
            number = int(m.group(1))
        return {"url": url, "number": number}

    def create_issue(
        self,
        repo: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        ensure_gh_token_env()
        if not shutil.which(self.gh_bin) and self.gh_bin == "gh":
            raise GitHubDown("gh not found")
        try:
            proc = self._run_create(repo, title, body, list(labels or []))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitHubDown(str(exc)) from exc
        if proc.returncode != 0 and labels:
            err = (proc.stderr or proc.stdout or "").strip()
            if _LABEL_FAIL.search(err):
                try:
                    proc = self._run_create(repo, title, body, [])
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise GitHubDown(str(exc)) from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "gh issue create failed").strip()
            raise GitHubDown(err[:500])
        return self._parse_issue(proc.stdout or "")

    def create_draft_pr(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
    ) -> dict[str, Any]:
        # Intentionally unsupported: intake.file_submission catches Exception
        # and files an issue with the path list instead.
        raise RuntimeError("gh_filer: draft PR not implemented; use issue fallback")


def default_filer() -> GitHubFiler:
    return GhCliFiler()
