"""FR #2526: pytest-home refuse + offer all-require_machine is a note (no maintenance spawn)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import jeeves_main as jm


def test_fr2526_ephemeral_pytest_homes_refused(tmp_path, monkeypatch):
    bad = tmp_path / "pytest-of-Administrator" / "pytest-current" / "x"
    bad.mkdir(parents=True)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(bad))
    monkeypatch.setenv("USERPROFILE", r"C:\Users\FakeOperator")
    got = jm.resolve_digest_home(env={
        "BOB_DIGEST_HOME": str(bad),
        "USERPROFILE": r"C:\Users\FakeOperator",
    })
    assert str(got).replace("/", "\\").lower().endswith(r"c:\users\fakeoperator\.bobiverse")
    assert jm.is_ephemeral_test_home(bad) is True
    assert jm.is_ephemeral_test_home(Path(r"C:\Users\FakeOperator\.bobiverse")) is False


def test_fr2526_offer_all_require_machine_is_note_not_finding(tmp_path):
    home = tmp_path / "digest"
    home.mkdir()

    def fake_summary(_root, _nick):
        return {
            "unaccepted": 4,
            "offerable": 0,
            "out_of_focus": 0,
            "require_machine": 4,
            "self_mrb": 0,
            "ledger": 0,
            "sticky_offered": 0,
        }

    import gitclaim

    with patch.object(gitclaim, "summarize_empty_offer", side_effect=fake_summary):
        detail, findings, errors = jm._check_offer(home, home)
    assert findings == [] and errors == []
    assert detail.get("offer_all_require_machine") is True
    assert detail.get("ok") is True
    assert "require_machine" in (detail.get("note") or "")


def test_fr2526_offer_mixed_gates_still_finding(tmp_path):
    home = tmp_path / "digest"
    home.mkdir()

    def fake_summary(_root, _nick):
        return {
            "unaccepted": 3,
            "offerable": 0,
            "out_of_focus": 1,
            "require_machine": 2,
            "self_mrb": 0,
            "ledger": 0,
            "sticky_offered": 0,
        }

    import gitclaim

    with patch.object(gitclaim, "summarize_empty_offer", side_effect=fake_summary):
        detail, findings, errors = jm._check_offer(home, home)
    assert findings and detail.get("ok") is False
