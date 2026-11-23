# -*- coding: utf-8 -*-
"""FR #8841 / CI-G2 S1: build-jeeves runs the open-children gate on pull_request.

Fail-when: workflow omits gate; PR builds with open children.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "build-jeeves.yml"
SCRIPT = ROOT / "common" / "scripts" / "open_children_gate.py"
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import open_children_gate as ocg  # noqa: E402


def _wf() -> str:
    raw = WF.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), WF
    return raw.decode("utf-8")


def test_fr8841_workflow_invokes_open_children_gate():
    assert WF.is_file()
    assert SCRIPT.is_file(), "CI-G1 script must ship with this stack"
    text = _wf()
    assert "open_children_gate.py" in text
    assert "Open-children gate" in text or "open-children gate" in text.lower()
    assert "github.event_name == 'pull_request'" in text or 'github.event_name == "pull_request"' in text
    assert "--pr" in text
    assert "FR #8841" in text or "CI-G2" in text or "8841" in text
    # Gate must be able to fail the job
    assert "open-children-gate exit" in text or "LASTEXITCODE" in text
    # Token for Issues/PR API
    assert "GITHUB_TOKEN" in text or "GH_TOKEN" in text
    assert "issues: read" in text
    assert "pull-requests: read" in text
    # Path filters mention the gate + this pin test
    assert "open_children_gate.py" in text
    assert "test_fr8841_wire_open_children_build_jeeves.py" in text


def test_fr8841_live_pr_soft_ok_without_closes(monkeypatch, tmp_path: Path):
    """PR mode with empty Closes list is soft-ok (exit 0), not misconfig exit 2."""

    def fake_fetch(repo: str, pr_num, *, token: str = ""):
        return {"number": int(pr_num), "body": "no closes here\n"}

    monkeypatch.setattr(ocg, "fetch_pr_dict", fake_fetch)
    monkeypatch.setattr(ocg, "fetch_open_issues", lambda repo, **kw: [])
    rc = ocg.main(["--repo", "SimonBarnett/bobiverse", "--pr", "123"])
    assert rc == 0


def test_fr8841_live_pr_fails_on_open_child(monkeypatch):
    def fake_fetch(repo: str, pr_num, *, token: str = ""):
        return {
            "number": int(pr_num),
            "body": "Closes #50\n",
            "closingIssuesReferences": [{"number": 50}],
        }

    def fake_issues(repo: str, **kw):
        return [
            {
                "number": 60,
                "body": "Depends-on: #50\n",
                "state": "open",
                "repo": repo,
                "title": "open child",
            }
        ]

    monkeypatch.setattr(ocg, "fetch_pr_dict", fake_fetch)
    monkeypatch.setattr(ocg, "fetch_open_issues", fake_issues)
    rc = ocg.main(["--repo", "SimonBarnett/bobiverse", "--pr", "9"])
    assert rc == 1
