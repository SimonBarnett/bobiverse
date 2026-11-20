"""FR #8377: open_pr_mrb_missing monitor + Invoke-JeevesMonitorCheck registration."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import open_pr_mrb_missing as opmm  # noqa: E402

REPO_NAME = "SimonBarnett/bobiverse"


def _pr(number: int, title: str = "FR #8348: fix", draft: bool = False, body: str = ""):
    return {
        "number": number,
        "title": title,
        "body": body,
        "draft": draft,
        "html_url": f"https://github.com/{REPO_NAME}/pull/{number}",
        "base": {"ref": "main", "repo": {"full_name": REPO_NAME}},
    }


def test_module_and_wrapper_exist():
    root = REPO / "jeeves"
    assert (root / "tools" / "monitor" / "open_pr_mrb_missing.py").is_file()
    assert (root / "scripts" / "Test-JeevesMonitorOpenPrMrbMissing.ps1").is_file()
    text = (root / "scripts" / "Invoke-JeevesMonitorCheck.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "open_pr_mrb_missing" in text


def test_ok_without_fixture(monkeypatch, tmp_path):
    monkeypatch.delenv("JEEVES_OPEN_PR_MRB_MISSING_FIXTURE", raising=False)
    args = SimpleNamespace(chair_home=str(tmp_path), digest_home="", dry_run=False)
    payload, code = opmm.check(args)
    assert code == 0
    assert payload["ok"] is True
    assert payload.get("skipped") == "no_fixture"


def test_finding_when_open_pr_has_no_row(monkeypatch, tmp_path):
    (tmp_path / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    fixture = tmp_path / "pulls.json"
    fixture.write_text(
        json.dumps({"repo": REPO_NAME, "pulls": [_pr(8353)]}), encoding="utf-8"
    )
    monkeypatch.setenv("JEEVES_OPEN_PR_MRB_MISSING_FIXTURE", str(fixture))
    args = SimpleNamespace(chair_home=str(tmp_path), digest_home="", dry_run=False)
    payload, code = opmm.check(args)
    assert code == 1
    assert payload["ok"] is False
    assert payload["missing_count"] == 1
    assert payload["missing"][0]["number"] == 8353
    assert any("8353" in f for f in payload["findings"])


def test_ok_when_mrb_row_present(monkeypatch, tmp_path):
    (tmp_path / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": REPO_NAME,
                        "task": "MRB",
                        "id": "#8353",
                        "seq": 1,
                        "url": f"https://github.com/{REPO_NAME}/pull/8353",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    fixture = tmp_path / "pulls.json"
    fixture.write_text(
        json.dumps({"repo": REPO_NAME, "pulls": [_pr(8353)]}), encoding="utf-8"
    )
    monkeypatch.setenv("JEEVES_OPEN_PR_MRB_MISSING_FIXTURE", str(fixture))
    args = SimpleNamespace(chair_home=str(tmp_path), digest_home="", dry_run=False)
    payload, code = opmm.check(args)
    assert code == 0
    assert payload["ok"] is True
    assert payload["missing_count"] == 0


def test_fix_row_covers_and_receipt_skipped(monkeypatch, tmp_path):
    (tmp_path / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": REPO_NAME,
                        "task": "FIX",
                        "id": "#8353",
                        "seq": 1,
                        "url": f"https://github.com/{REPO_NAME}/pull/8353",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    fixture = tmp_path / "pulls.json"
    fixture.write_text(
        json.dumps(
            {
                "repo": REPO_NAME,
                "pulls": [
                    _pr(8353),
                    # intake harvest receipt: not expected to hold an MRB row.
                    _pr(
                        9999,
                        title="harvest: DONE FR",
                        body="Session summary:\nInvoke-BobiverseHarvest",
                    ),
                    # draft: not expected.
                    _pr(8888, draft=True),
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_OPEN_PR_MRB_MISSING_FIXTURE", str(fixture))
    args = SimpleNamespace(chair_home=str(tmp_path), digest_home="", dry_run=False)
    payload, code = opmm.check(args)
    assert code == 0
    assert payload["ok"] is True
    assert payload["expected_count"] == 1
    assert payload["missing_count"] == 0
