"""FR #738: do not re-offer MRB for CLOSED (non-open) PRs."""
from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError

import bobreport
import gitclaim
import registered_machines


def _digest(home, machines):
    registered_machines.save_registered(home, set(machines))
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {str(w): {"state": "idle"} for w in workers}
    bobreport.save_digest(home, doc)


def test_mrb_row_offerable_false_when_state_closed():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#637",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/637",
        "state": "closed",
    }
    assert gitclaim.mrb_row_offerable(row) is False


def test_mrb_row_offerable_false_when_merged_false():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#637",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/637",
        "merged": False,
    }
    assert gitclaim.mrb_row_offerable(row) is False


def test_mrb_row_offerable_false_when_pr_exists_says_closed():
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#637",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/637",
    }

    def pr_exists(repo: str, num: str) -> bool:
        # Simulates github_pr_exists_checker after FR #738 (closed → False).
        return False

    assert gitclaim.mrb_row_offerable(row, pr_exists=pr_exists) is False


def test_offer_skips_closed_fail_pr(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"marchhare": [41928], "ionos": [1]})
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#637",
                    "seq": 1,
                    "ts": "t",
                    "line": "MRB #637",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/637",
                    "state": "closed",
                    "merged": False,
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, _ = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st == "empty"


def test_github_pr_exists_checker_requires_open(monkeypatch, tmp_path):
    """CLOSED PRs return HTTP 200 — checker must still refuse (FR #738)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("GH_TOKEN", "test-token-not-real")

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"state": "closed", "merged": False, "number": 637}).encode()

    def fake_urlopen(req, timeout=8):
        return _Resp()

    monkeypatch.setattr(gitclaim.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "gh_filer.ensure_gh_token_env", lambda: "env", raising=False
    )
    # gh_filer may not import; inject via module
    import sys
    import types

    if "gh_filer" not in sys.modules:
        mod = types.ModuleType("gh_filer")
        mod.ensure_gh_token_env = lambda: "env"
        sys.modules["gh_filer"] = mod
    else:
        monkeypatch.setattr(
            sys.modules["gh_filer"], "ensure_gh_token_env", lambda: "env"
        )

    checker = gitclaim.github_pr_exists_checker(home=tmp_path)
    assert checker is not None
    assert checker("SimonBarnett/bobiverse", "637") is False

    class _OpenResp(_Resp):
        def read(self):
            return json.dumps({"state": "open", "number": 640}).encode()

    monkeypatch.setattr(
        gitclaim.urllib.request, "urlopen", lambda req, timeout=8: _OpenResp()
    )
    # new cache
    checker2 = gitclaim.github_pr_exists_checker(home=tmp_path, cache={})
    assert checker2("SimonBarnett/bobiverse", "640") is True
