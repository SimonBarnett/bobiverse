"""docs/mrb-4696: hostile pins for FR #4695 fr_done clear on reopen."""
from __future__ import annotations

import gitclaim

REPO = "SimonBarnett/a-search"
IDENT = "#3968"


def _stamp(home, ident=IDENT):
    key = gitclaim._lkey(REPO, ident)

    def _fn(doc: dict) -> None:
        doc.setdefault("fr_done", {})[key] = gitclaim._utc_now()

    gitclaim._ledger_update(home, _fn)
    return key


def test_clear_fr_done_stamp_false_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    assert gitclaim.clear_fr_done_stamp(tmp_path, REPO, IDENT) is False


def test_requeue_without_home_leaves_fr_done(tmp_path, monkeypatch):
    """Callers that omit home must not clear (compat); apply_queue_event always passes home."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    key = _stamp(tmp_path)
    doc = {"v": 1, "unaccepted": [], "accepted": [], "done": [
        {
            "repo": REPO,
            "task": "FR",
            "id": IDENT,
            "seq": 1,
            "ts": "t",
            "line": "DONE FR",
            "done_ts": "2026-10-18T09:23:25Z",
            "nick": "x",
        }
    ]}
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id=IDENT,
        event="issues",
        action="reopened",
        line="GIT issues reopened",
        title="t",
        body="b",
        labels=["feature-request"],
        state="open",
    )
    changed = gitclaim.requeue_reopened_issue(doc, claim, via="test", home=None)
    assert changed in ("added", "updated", "duplicate")
    led = gitclaim.ledger_load(tmp_path)
    assert key in (led.get("fr_done") or {})


def test_skipped_non_fr_requeue_does_not_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    key = _stamp(tmp_path)
    doc = {"v": 1, "unaccepted": [], "accepted": [], "done": []}
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id=IDENT,
        event="issues",
        action="reopened",
        line="GIT issues reopened",
        title="t",
        body="b",
        state="open",
    )
    assert gitclaim.requeue_reopened_issue(doc, claim, via="test", home=tmp_path) == "skipped"
    out = capsys.readouterr().out
    assert "reopen cleared fr_done" not in out
    led = gitclaim.ledger_load(tmp_path)
    assert key in (led.get("fr_done") or {})
