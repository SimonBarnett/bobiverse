"""MRB #2583 hostile gates for FR #2579 create_draft_pr (product PR #2583).

Locks: no stub RuntimeError in GhCliFiler.create_draft_pr; draft pulls only;
path traversal rejected; harvest stub failures must not log queued_github_down.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gh_filer  # noqa: E402
import intake  # noqa: E402

GH = ROOT / "common" / "scripts" / "gh_filer.py"
INTAKE = ROOT / "common" / "scripts" / "intake.py"
SKILL = (
    ROOT
    / "jeeves"
    / ".grok"
    / "skills"
    / "bobiverse-jeeves-troubleshooting"
    / "SKILL.md"
)


def _fn_body(text: str, name: str) -> str:
    m = re.search(r"def\s+" + re.escape(name) + r"\s*\(", text)
    assert m, name
    rest = text[m.start() :]
    m2 = re.search(r"\n    def\s+\w+", rest[1:])
    return rest if not m2 else rest[: m2.start() + 1]


def test_mrb2583_ghcli_create_draft_pr_not_stub():
    full = GH.read_text(encoding="utf-8")
    body = _fn_body(full, "create_draft_pr")
    assert "draft PR not implemented" not in body
    # FR #2705: create_draft_pr passes draft=True; git data + draft JSON live in _create_pr_with_files.
    assert "draft=True" in body
    shared = _fn_body(full, "_create_pr_with_files")
    assert '"draft": bool(draft)' in shared or '"draft": True' in shared
    assert "/git/blobs" in shared
    assert "/pulls" in shared
    assert "FR #2579" in body or "FR #2579" in shared


def test_mrb2583_rejects_path_traversal():
    class F(gh_filer.GhCliFiler):
        def __init__(self) -> None:
            self.gh_bin = "gh"

        def _api(self, method: str, path: str, payload=None, *, timeout: int = 120):
            if method.upper() == "GET" and path.count("/") == 2:
                return {"default_branch": "main"}
            if "/git/ref/heads/" in path:
                return {"object": {"sha": "base"}}
            if "/git/commits/" in path:
                return {"tree": {"sha": "tree"}}
            raise AssertionError(f"should fail before {method} {path}")

    with pytest.raises(gh_filer.GitHubDown, match="bad file path"):
        F().create_draft_pr(
            "SimonBarnett/bobiverse",
            "t",
            "b",
            "intake/evil",
            [{"path": "../secrets.txt", "content": "x"}],
            [],
        )


def test_mrb2583_process_intake_reason_whitelist():
    text = INTAKE.read_text(encoding="utf-8")
    assert "queued_draft_pr_unsupported" in text
    assert "getattr(exc, 'reason'" in text or 'getattr(exc, "reason"' in text
    assert "draft_pr_unsupported" in text


def test_mrb2583_troubleshooting_mentions_fr2579():
    t = SKILL.read_text(encoding="utf-8")
    assert "FR #2579" in t or "2579" in t
    assert "create_draft_pr" in t or "draft PR" in t.lower() or "github_down" in t


def test_mrb2583_githubdown_carries_reason():
    assert hasattr(gh_filer, "GitHubDown") or hasattr(intake, "GitHubDown")
    GD = getattr(intake, "GitHubDown", None) or getattr(gh_filer, "GitHubDown")
    exc = GD("harvest draft PR filing failed", reason="draft_pr_unsupported")
    assert getattr(exc, "reason", None) == "draft_pr_unsupported"
