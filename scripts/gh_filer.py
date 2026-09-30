"""Thin GitHub filer: shells out to `gh issue create` (real); Fake path for tests.

Bobiverse flat-script surface for ``intake.GitHubFiler``. Draft PRs are not
implemented here — ``intake.file_submission`` falls back to an issue listing.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from intake import FakeGitHubFiler, GitHubDown, GitHubFiler

__all__ = [
    "FakeGitHubFiler",
    "GitHubDown",
    "GitHubFiler",
    "GhCliFiler",
    "default_filer",
]

_ISSUE_NUM = re.compile(r"/issues/(\d+)\s*$")


class GhCliFiler:
    """Production filer: ``gh issue create -R <repo>``."""

    def __init__(self, gh_bin: str | None = None) -> None:
        which = shutil.which("gh") if not gh_bin else shutil.which(gh_bin) or gh_bin
        self.gh_bin = which or "gh"

    def create_issue(
        self,
        repo: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        if not shutil.which(self.gh_bin) and self.gh_bin == "gh":
            raise GitHubDown("gh not found")
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
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitHubDown(str(exc)) from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "gh issue create failed").strip()
            raise GitHubDown(err[:500])
        url = ""
        for line in reversed((proc.stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("http"):
                url = line
                break
        number = 0
        m = _ISSUE_NUM.search(url)
        if m:
            number = int(m.group(1))
        return {"url": url, "number": number}

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
