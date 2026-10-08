"""Thin GitHub filer: shells out to `gh` (real); Fake path for tests.

Bobiverse flat-script surface for `intake.GitHubFiler`. Creates issues via
`gh issue create` and harvest/skill draft PRs via `gh api` git data +
`POST /pulls` with `draft: true` (FR #2579).

Auth: `GH_TOKEN` / `GITHUB_TOKEN` env, else `~/.grok/bob/github.token`
(one line). Missing labels are retried without `--label` so intake still files.
"""
from __future__ import annotations

import json
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
    try:  # t780u: the jeeves install under the discovered <drive>:\ai (BOB_AI_ROOT overrides)
        import ai_root
        paths.append(Path(ai_root.product_root("jeeves")) / "config" / "github.token")
    except Exception:
        pass
    # #53: the jeeves install owns the webhook receiver: <InstallRoot>\config\github.token
    # next to scripts\ (works for any InstallRoot, not just <ai root>\jeeves).
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

    def ensure_labels(self, repo: str, labels: list[str]) -> None:
        """Create missing labels best-effort so hold stamps like ``owner-missing`` stick (FR #3658)."""
        ensure_gh_token_env()
        for lab in labels or []:
            name = str(lab or "").strip()
            if not name:
                continue
            # GET first — 0 means present.
            try:
                probe = subprocess.run(
                    [self.gh_bin, "api", f"repos/{repo}/labels/{name}"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                    env=os.environ.copy(),
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if probe.returncode == 0:
                continue
            # Create with a stable color; ignore race if another process created it.
            try:
                subprocess.run(
                    [
                        self.gh_bin,
                        "label",
                        "create",
                        name,
                        "-R",
                        str(repo),
                        "--color",
                        "B60205",
                        "--description",
                        "Held until intended owner repo exists (FR #3317 / #3658)",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                    env=os.environ.copy(),
                )
            except (OSError, subprocess.TimeoutExpired):
                continue

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
        labs = list(labels or [])
        if labs:
            self.ensure_labels(repo, labs)
        try:
            proc = self._run_create(repo, title, body, labs)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitHubDown(str(exc)) from exc
        if proc.returncode != 0 and labs:
            err = (proc.stderr or proc.stdout or "").strip()
            if _LABEL_FAIL.search(err):
                # Self-heal once more after ensure, then fall back to unlabeled create
                # (title SKIP_FR still covers harvest: hold for … — FR #3658).
                self.ensure_labels(repo, labs)
                try:
                    proc = self._run_create(repo, title, body, labs)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise GitHubDown(str(exc)) from exc
            if proc.returncode != 0 and _LABEL_FAIL.search(
                (proc.stderr or proc.stdout or "").strip()
            ):
                try:
                    proc = self._run_create(repo, title, body, [])
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise GitHubDown(str(exc)) from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "gh issue create failed").strip()
            raise GitHubDown(err[:500])
        return self._parse_issue(proc.stdout or "")

    def _api(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 120,
    ) -> Any:
        """JSON ``gh api`` helper. Raises GitHubDown on transport/API failure."""
        ensure_gh_token_env()
        if not shutil.which(self.gh_bin) and self.gh_bin == "gh":
            raise GitHubDown("gh not found")
        cmd = [self.gh_bin, "api", "-X", method.upper(), path]
        raw_in = None
        if payload is not None:
            cmd.extend(["--input", "-"])
            raw_in = json.dumps(payload)
        try:
            proc = subprocess.run(
                cmd,
                input=raw_in,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitHubDown(str(exc)) from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "gh api failed").strip()
            raise GitHubDown(err[:500])
        text_out = (proc.stdout or "").strip()
        if not text_out:
            return {}
        try:
            return json.loads(text_out)
        except json.JSONDecodeError as exc:
            raise GitHubDown(f"gh api non-json: {text_out[:200]}") from exc

    def get_file_content(self, repo: str, path: str) -> str:
        """Return UTF-8 file contents from the default branch (FR #2705)."""
        ensure_gh_token_env()
        repo = str(repo or "").strip()
        path = str(path or "").strip().replace("\\", "/").lstrip("/")
        if not repo or "/" not in repo or not path:
            return ""
        try:
            meta = self._api("GET", f"repos/{repo}/contents/{path}")
        except GitHubDown:
            return ""
        if not isinstance(meta, dict):
            return ""
        import base64

        encoding = str(meta.get("encoding") or "")
        content = str(meta.get("content") or "")
        if encoding == "base64" and content:
            try:
                return base64.b64decode(content.replace("\n", "")).decode("utf-8")
            except Exception:
                return ""
        return content

    def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
    ) -> dict[str, Any]:
        """Create a non-draft PR with the given files (FR #2705 harvest-lesson)."""
        return self._create_pr_with_files(
            repo, title, body, branch, files, labels, draft=False
        )

    def create_draft_pr(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
    ) -> dict[str, Any]:
        """Create a draft PR with the given files via Git Data API (FR #2579).

        Empty ``files`` still opens a draft: writes
        ``docs/intake-harvest/<branch-safe>.md`` with the harvest body so the
        branch is non-empty. Returns ``{url, number, branch}``.
        """
        return self._create_pr_with_files(
            repo, title, body, branch, files, labels, draft=True
        )

    def _create_pr_with_files(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
        *,
        draft: bool,
    ) -> dict[str, Any]:
        ensure_gh_token_env()
        repo = str(repo or "").strip()
        branch = str(branch or "").strip()
        tag = "create_pr" if not draft else "create_draft_pr"
        if not repo or "/" not in repo:
            raise GitHubDown(f"{tag}: bad repo")
        if not branch or ".." in branch or branch.startswith("/"):
            raise GitHubDown(f"{tag}: bad branch")

        meta = self._api("GET", f"repos/{repo}")
        default_branch = str(meta.get("default_branch") or "main")
        ref = self._api("GET", f"repos/{repo}/git/ref/heads/{default_branch}")
        base_sha = str((ref.get("object") or {}).get("sha") or "")
        if not base_sha:
            raise GitHubDown(f"{tag}: missing base sha for {default_branch}")
        commit = self._api("GET", f"repos/{repo}/git/commits/{base_sha}")
        base_tree = str((commit.get("tree") or {}).get("sha") or "")
        if not base_tree:
            raise GitHubDown(f"{tag}: missing base tree")

        entries = list(files or [])
        if not entries:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-") or "harvest"
            entries = [
                {
                    "path": f"docs/intake-harvest/{safe}.md",
                    "content": (body or title or "harvest").rstrip() + "\n",
                }
            ]

        tree_items: list[dict[str, str]] = []
        for item in entries:
            path = str(item.get("path") or "").strip().replace("\\", "/")
            content = str(item.get("content") or "")
            if not path or ".." in path.split("/") or path.startswith("/"):
                raise GitHubDown(f"{tag}: bad file path {path!r}")
            blob = self._api(
                "POST",
                f"repos/{repo}/git/blobs",
                {"content": content, "encoding": "utf-8"},
            )
            blob_sha = str(blob.get("sha") or "")
            if not blob_sha:
                raise GitHubDown(f"{tag}: blob failed for {path}")
            tree_items.append(
                {"path": path, "mode": "100644", "type": "blob", "sha": blob_sha}
            )

        new_tree = self._api(
            "POST",
            f"repos/{repo}/git/trees",
            {"base_tree": base_tree, "tree": tree_items},
        )
        tree_sha = str(new_tree.get("sha") or "")
        if not tree_sha:
            raise GitHubDown(f"{tag}: tree create failed")

        new_commit = self._api(
            "POST",
            f"repos/{repo}/git/commits",
            {
                "message": str(title or "intake harvest")[:200],
                "tree": tree_sha,
                "parents": [base_sha],
            },
        )
        commit_sha = str(new_commit.get("sha") or "")
        if not commit_sha:
            raise GitHubDown(f"{tag}: commit create failed")

        ref_name = f"refs/heads/{branch}"
        try:
            self._api(
                "POST",
                f"repos/{repo}/git/refs",
                {"ref": ref_name, "sha": commit_sha},
            )
        except GitHubDown:
            self._api(
                "PATCH",
                f"repos/{repo}/git/refs/heads/{branch}",
                {"sha": commit_sha, "force": True},
            )

        pr = self._api(
            "POST",
            f"repos/{repo}/pulls",
            {
                "title": str(title or "intake harvest")[:200],
                "body": str(body or ""),
                "head": branch,
                "base": default_branch,
                "draft": bool(draft),
            },
        )
        number = int(pr.get("number") or 0)
        url = str(pr.get("html_url") or "")
        if not number or not url:
            raise GitHubDown(f"{tag}: pull create returned no number/url")

        if labels:
            try:
                self._api(
                    "POST",
                    f"repos/{repo}/issues/{number}/labels",
                    {"labels": [str(x) for x in labels if str(x).strip()]},
                )
            except GitHubDown:
                pass

        return {"url": url, "number": number, "branch": branch}

    def find_pull_by_head(self, repo: str, head_branch: str) -> dict[str, Any] | None:
        """Return an open/closed PR for ``head_branch`` if present (FR #2595 drain dedupe)."""
        repo = str(repo or "").strip()
        head_branch = str(head_branch or "").strip()
        if not repo or "/" not in repo or not head_branch:
            return None
        owner = repo.split("/", 1)[0]
        # head must be owner:branch for the pulls filter.
        q = f"repos/{repo}/pulls?state=all&head={owner}:{head_branch}&per_page=5"
        try:
            rows = self._api("GET", q)
        except GitHubDown:
            return None
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        number = int(row.get("number") or 0)
        url = str(row.get("html_url") or "")
        if not number or not url:
            return None
        return {"url": url, "number": number, "branch": head_branch}


def default_filer() -> GitHubFiler:
    return GhCliFiler()
