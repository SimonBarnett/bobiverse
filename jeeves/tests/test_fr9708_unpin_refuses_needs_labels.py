# -*- coding: utf-8 -*-
"""FR #9708: !unpin refuses while needs-* labels remain (CAST IRON)."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def test_fr9708_unpin_refuses_when_needs_walrus_on_row(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"walrus", "flamingo"})
    bobreport.save_digest(home, bobreport.empty_digest())
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#9628",
        "seq": 1,
        "ts": "t",
        "line": "FR SimonBarnett/bobiverse#9628",
        "title": "chair: offer_to_idle",
        "body": "",
        "labels": ["feature-request", "needs-walrus"],
        "state": "open",
        "require_machine": "walrus",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    out = gitclaim.set_require_machine_job(home, "SimonBarnett/bobiverse", "#9628", "any")
    assert out.get("ok") is False
    assert str(out.get("error") or "").startswith("needs_labels:")
    assert "needs-walrus" in str(out.get("error"))
    assert gitclaim.load_unaccepted(home)[0].get("require_machine") == "walrus"


def test_fr9708_unpin_ok_after_needs_label_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"walrus"})
    bobreport.save_digest(home, bobreport.empty_digest())
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#9628",
        "seq": 1,
        "ts": "t",
        "line": "FR SimonBarnett/bobiverse#9628",
        "title": "chair: offer_to_idle",
        "body": "",
        "labels": ["feature-request"],
        "state": "open",
        "require_machine": "walrus",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    out = gitclaim.set_require_machine_job(home, "SimonBarnett/bobiverse", "#9628", "any")
    assert out.get("ok") is True
    assert out.get("require_machine") == "any"
    assert gitclaim.load_unaccepted(home)[0].get("require_machine") == "any"


def test_fr9708_docs_cite_cast_iron():
    docs = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "docs"
        / "jeeves-commands.md"
    ).read_text(encoding="utf-8")
    assert "9708" in docs
    assert "needs-* still present" in docs or "remove labels then !unpin" in docs
