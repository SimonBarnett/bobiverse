"""FR #2340: purge CLOSED-issue FR rows; refuse enqueue of closed opened events."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest import mock

import gitclaim


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def test_fr_row_offerable_rejects_stamped_closed_state():
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#2218",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/2218",
        "title": "harvest: closed twin",
        "state": "closed",
    }
    assert gitclaim.fr_row_offerable(row) is False


def test_fr_row_offerable_rejects_via_issue_open_checker():
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#2152",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/2152",
        "title": "harvest: closed twin",
    }
    assert gitclaim.fr_row_offerable(row) is True
    assert (
        gitclaim.fr_row_offerable(row, issue_open=lambda r, n: str(n) != "2152")
        is False
    )
    assert (
        gitclaim.fr_row_offerable(row, issue_open=lambda r, n: True) is True
    )


def test_purge_closed_fr_unaccepted_drops_stamped_and_live():
    doc = {
        "unaccepted": [
            {"task": "FR", "repo": "o/a", "id": "#1", "title": "open", "state": "open"},
            {"task": "FR", "repo": "o/a", "id": "#2", "title": "stamped closed", "state": "closed"},
            {"task": "FR", "repo": "o/a", "id": "#3", "title": "live closed"},
            {"task": "MRB", "repo": "o/a", "id": "#4", "url": "https://github.com/o/a/pull/4"},
        ]
    }
    n = gitclaim._purge_closed_fr_unaccepted(
        doc, issue_open=lambda r, n: str(n) != "3"
    )
    assert n == 2
    assert [r["id"] for r in doc["unaccepted"]] == ["#1", "#4"]


def test_offer_focus_top_purges_closed_fr_before_offer(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2218",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/2218",
                    "title": "closed harvest twin",
                    "line": "FR #2218",
                    "seq": 1,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2340",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/2340",
                    "title": "purge CLOSED FR rows",
                    "line": "FR #2340",
                    "seq": 2,
                    "state": "open",
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    issue_open = lambda r, n: str(n) == "2340"
    st, job = gitclaim.offer_focus_top(
        home, "marchhare-40208", "#marchhare", issue_open=issue_open
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#2340"
    left = {r["id"] for r in gitclaim.load_unaccepted(home)}
    assert "#2218" not in left
    assert "#2340" in left


def test_claim_from_payload_refuses_opened_when_state_closed():
    payload = {
        "action": "opened",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "issue": {
            "number": 2152,
            "title": "harvest: already closed",
            "body": "evidence",
            "state": "closed",
            "labels": [{"name": "via-intake"}],
        },
    }
    assert gitclaim.claim_from_payload("issues", payload) is None


def test_append_unaccepted_skips_closed_state_and_stamps_open():
    doc = {"unaccepted": [], "accepted": [], "done": []}
    closed = gitclaim.GitClaim(
        repo="o/a",
        task="FR",
        id="#9",
        event="issues",
        action="opened",
        line="",
        title="x",
        state="closed",
    )
    assert gitclaim._append_unaccepted(doc, closed) == "skipped"
    assert doc["unaccepted"] == []

    open_c = gitclaim.GitClaim(
        repo="o/a",
        task="FR",
        id="#10",
        event="issues",
        action="opened",
        line="",
        title="real",
        state="open",
    )
    assert gitclaim._append_unaccepted(doc, open_c) == "added"
    assert doc["unaccepted"][0]["state"] == "open"


def test_assign_row_refuses_closed_fr(tmp_path: Path, monkeypatch):
    import bobreport
    import registered_machines

    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"40208": {"state": "idle"}}
    bobreport.save_digest(home, digest)
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {"marchhare-40208"})
    monkeypatch.setattr(gitclaim, "ledger_load", lambda h: {})
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2323",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/2323",
                    "title": "closed",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, reason = gitclaim.assign_row(
        home,
        "marchhare-40208",
        "SimonBarnett/bobiverse",
        "FR",
        "#2323",
        issue_open=lambda r, n: False,
    )
    assert st == "refused"
    assert "CLOSED" in str(reason) or "pull" in str(reason).lower()


def test_github_issue_open_checker_requires_open_state():
    bodies = {
        "1": json.dumps({"state": "open", "number": 1}).encode(),
        "2": json.dumps({"state": "closed", "number": 2}).encode(),
    }

    class _Resp:
        def __init__(self, raw: bytes):
            self.status = 200
            self._raw = raw

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=8):
        url = getattr(req, "full_url", None) or str(req)
        for num, raw in bodies.items():
            if url.rstrip("/").endswith("/" + num):
                return _Resp(raw)
        raise AssertionError(url)

    fake_gh = types.ModuleType("gh_filer")
    fake_gh.ensure_gh_token_env = lambda: "env"
    prev = sys.modules.get("gh_filer")
    sys.modules["gh_filer"] = fake_gh
    try:
        with mock.patch.dict(
            "os.environ", {"GH_TOKEN": "fake-token-not-real", "GITHUB_TOKEN": ""}
        ):
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                check = gitclaim.github_issue_open_checker(cache={})
                assert check is not None
                assert check("o/r", "1") is True
                assert check("o/r", "2") is False
    finally:
        if prev is None:
            sys.modules.pop("gh_filer", None)
        else:
            sys.modules["gh_filer"] = prev
