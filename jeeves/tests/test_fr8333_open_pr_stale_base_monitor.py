"""FR #8333: open_pr_stale_base monitor + Invoke-JeevesMonitorCheck registration."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import open_pr_stale_base as opsb  # noqa: E402


def test_module_and_wrapper_exist():
    root = REPO / "jeeves"
    assert (root / "tools" / "monitor" / "open_pr_stale_base.py").is_file()
    assert (root / "scripts" / "Test-JeevesMonitorOpenPrStaleBase.ps1").is_file()
    text = (root / "scripts" / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "open_pr_stale_base" in text


def test_ok_without_fixture(monkeypatch):
    monkeypatch.delenv("JEEVES_OPEN_PR_STALE_BASE_FIXTURE", raising=False)
    args = SimpleNamespace(chair_home="", digest_home="", dry_run=False)
    payload, code = opsb.check(args)
    assert code == 0
    assert payload["ok"] is True
    assert payload.get("skipped") == "no_fixture"


def test_finding_from_fixture(tmp_path, monkeypatch):
    fixture = tmp_path / "pulls.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "number": 8320,
                    "title": "fix(mrb-8316): pins",
                    "draft": False,
                    "html_url": "https://github.com/SimonBarnett/bobiverse/pull/8320",
                    "base": {"ref": "fr-8310-land"},
                },
                {
                    "number": 8332,
                    "title": "FR #8331",
                    "draft": False,
                    "base": {"ref": "main"},
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_OPEN_PR_STALE_BASE_FIXTURE", str(fixture))
    args = SimpleNamespace(chair_home="", digest_home="", dry_run=False)
    payload, code = opsb.check(args)
    assert code == 1
    assert payload["ok"] is False
    assert len(payload["stale"]) == 1
    assert payload["stale"][0]["number"] == 8320
    assert any("8320" in f for f in payload["findings"])
