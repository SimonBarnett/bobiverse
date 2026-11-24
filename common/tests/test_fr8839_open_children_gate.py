# -*- coding: utf-8 -*-
"""FR #8839 / CI-G1 S1: open-children gate fails when open Depends-on children remain.

Fail-when: silent pass while an open child still Depends-on #P.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import open_children_gate as ocg  # noqa: E402

REPO = "SimonBarnett/bobiverse"


def _issue(num: int, body: str, *, state: str = "open", repo: str = REPO, **kw) -> dict:
    row = {
        "number": num,
        "body": body,
        "state": state,
        "repo": repo,
        "title": f"Issue {num}",
        "html_url": f"https://github.com/{repo}/issues/{num}",
    }
    row.update(kw)
    return row


def test_fr8839_fail_when_open_child_depends_on_parent():
    """S1 fail-when: must not exit 0 while open child Depends-on #P."""
    issues = [
        _issue(10, "Depends-on: #5\n", title="child"),
        _issue(11, "Depends-on: (none)\n"),
    ]
    code, lines = ocg.gate_open_children(REPO, 5, issues=issues)
    assert code == 1
    text = "\n".join(lines)
    assert "FAIL" in text
    assert f"{REPO}#10" in text
    assert "Issue 11" not in text


def test_fr8839_ok_when_no_open_children():
    issues = [
        _issue(10, "Depends-on: #5\n", state="closed"),
        _issue(11, "Depends-on: #9\n"),
        _issue(12, "Depends-on: (none)\n"),
    ]
    code, lines = ocg.gate_open_children(REPO, 5, issues=issues)
    assert code == 0
    assert "ok" in "\n".join(lines)


def test_fr8839_qualified_and_relative_refs():
    issues = [
        _issue(20, "Depends-on: SimonBarnett/bobiverse#7\n"),
        _issue(21, "**Depends-on:** #7\n"),
        _issue(22, "Depends-on: other/repo#7\n", repo="other/repo"),
    ]
    kids = ocg.find_open_children(REPO, 7, issues)
    nums = {int(k["number"]) for k in kids}
    assert nums == {20, 21}


def test_fr8839_fetch_seam_used_when_issues_omitted():
    calls: list[str] = []

    def fetch(repo: str) -> list[dict]:
        calls.append(repo)
        return [_issue(3, "Depends-on: #1\n")]

    code, lines = ocg.gate_open_children(REPO, 1, fetch_issues=fetch)
    assert calls == [REPO]
    assert code == 1
    assert "#3" in "\n".join(lines)


def test_fr8839_cli_issues_json(tmp_path: Path):
    path = tmp_path / "issues.json"
    path.write_text(
        json.dumps(
            [
                _issue(30, "Depends-on: #100\n", title="blocked child"),
                _issue(31, "Depends-on: #99\n"),
            ]
        ),
        encoding="utf-8",
    )
    rc = ocg.main(["--repo", REPO, "--parent", "100", "--issues-json", str(path)])
    assert rc == 1
    rc_ok = ocg.main(["--repo", REPO, "--parent", "50", "--issues-json", str(path)])
    assert rc_ok == 0


def test_fr8839_cli_pr_json_closes(tmp_path: Path):
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        json.dumps([_issue(40, "Depends-on: #8839\n", title="open child of 8839")]),
        encoding="utf-8",
    )
    pr_path = tmp_path / "pr.json"
    pr_path.write_text(
        json.dumps(
            {
                "number": 999,
                "body": "Closes SimonBarnett/bobiverse#8839\n",
                "closingIssuesReferences": [
                    {
                        "number": 8839,
                        "repository": {
                            "name": "bobiverse",
                            "owner": {"login": "SimonBarnett"},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rc = ocg.main(
        [
            "--repo",
            REPO,
            "--pr-json",
            str(pr_path),
            "--issues-json",
            str(issues_path),
        ]
    )
    assert rc == 1


def test_fr8839_pr_co_closes_child_is_ok(tmp_path: Path):
    """Same PR Closes parent + Depends-on child: CI-G1 must not fail (FR #9858 tip)."""
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        json.dumps(
            [
                _issue(9858, "Depends-on: #9856\n", title="FR-B parent"),
                _issue(
                    9860,
                    "Depends-on: #9856 #9858\n",
                    title="FR-D child of 9858",
                ),
            ]
        ),
        encoding="utf-8",
    )
    pr_path = tmp_path / "pr.json"
    pr_path.write_text(
        json.dumps(
            {
                "number": 9904,
                "body": (
                    "Closes SimonBarnett/bobiverse#9858\n"
                    "Closes SimonBarnett/bobiverse#9860\n"
                ),
                "closingIssuesReferences": [
                    {
                        "number": 9858,
                        "repository": {
                            "name": "bobiverse",
                            "owner": {"login": "SimonBarnett"},
                        },
                    },
                    {
                        "number": 9860,
                        "repository": {
                            "name": "bobiverse",
                            "owner": {"login": "SimonBarnett"},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    rc = ocg.main(
        [
            "--repo",
            REPO,
            "--pr-json",
            str(pr_path),
            "--issues-json",
            str(issues_path),
        ]
    )
    assert rc == 0


def test_fr8839_gate_excludes_co_closed_children():
    issues = [_issue(9860, "Depends-on: #9858\n", title="co-closed child")]
    exclude = {(REPO.lower(), 9860)}
    code, lines = ocg.gate_open_children(
        REPO, 9858, issues=issues, exclude_closing=exclude
    )
    assert code == 0
    assert "ok" in "\n".join(lines)


def test_fr8839_parents_from_pr_body_fallback():
    parents = ocg.parents_from_pr_closing_refs(
        {"body": "Closes #42\nFixes other/x#9\n", "number": 1},
        default_repo=REPO,
    )
    assert (REPO, 42) in parents
    assert ("other/x", 9) in parents
