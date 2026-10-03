"""FR #740 / #738: never re-offer MERGED or CLOSED MRB rows after DONE."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import gitclaim
import registered_machines
import shop_listen


REPO = "SimonBarnett/bobiverse"


def _queue(home: Path, *, unaccepted=None, accepted=None, done=None):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted or []),
            "done": list(done or []),
        },
    )


def _mrb_row(num=656, **extra):
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/{num}",
    }
    row.update(extra)
    return row


def test_mrb_row_offerable_false_when_pr_exists_reports_closed():
    row = _mrb_row()
    assert gitclaim.mrb_row_offerable(row, pr_exists=lambda r, n: False) is False
    assert gitclaim.mrb_row_offerable(row, pr_exists=lambda r, n: True) is True


def test_mrb_already_done_detects_prior_pass_or_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(
        tmp_path,
        done=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#656",
                "nick": "marchhare-41928",
                "result": "PASS",
                "url": f"https://github.com/{REPO}/pull/656",
            }
        ],
    )
    doc = gitclaim._load_queue_unlocked(tmp_path)
    assert gitclaim.mrb_already_done(doc, _mrb_row(656))
    assert not gitclaim.mrb_already_done(doc, _mrb_row(999))


def test_offer_skips_mrb_already_in_done_even_without_pr_exists(tmp_path, monkeypatch):
    """FR #740: after DONE PASS, do not re-offer the same MRB (no GitHub token needed)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"1": {"state": "idle"}}
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {"9": {"state": "idle"}}
    bobreport.save_digest(tmp_path, digest)
    _queue(
        tmp_path,
        unaccepted=[_mrb_row(656)],
        done=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#656",
                "nick": "marchhare-41928",
                "result": "PASS https://github.com/{}/pull/656".format(REPO),
            }
        ],
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "flamingo-9", "#flamingo")
    assert st == "empty"
    # leftover unaccepted row purged
    left = [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("task") == "MRB"]
    assert left == []


def test_offer_skips_closed_fail_mrb_via_pr_exists(tmp_path, monkeypatch):
    """FR #738: CLOSED non-merged PR must not be re-offered as MRB."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {"9": {"state": "idle"}}
    bobreport.save_digest(tmp_path, digest)
    _queue(tmp_path, unaccepted=[_mrb_row(637)])

    def pr_exists(repo: str, num: str) -> bool:
        return False  # closed / merged → not open

    st, job = gitclaim.offer_focus_top(
        tmp_path, "flamingo-9", "#flamingo", pr_exists=pr_exists
    )
    assert st == "empty"
    assert gitclaim.load_unaccepted(tmp_path) == []


def test_done_mrb_purges_lingering_unaccepted_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    _queue(
        tmp_path,
        accepted=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#656",
                "seq": 1,
                "nick": "marchhare-1",
                "ts": "t",
                "line": "x",
                "channel": "#marchhare",
                "accepted_ts": "t",
                "url": f"https://github.com/{REPO}/pull/656",
            }
        ],
        unaccepted=[_mrb_row(656, seq=2)],  # duplicate left behind
    )
    st, _ = shop_listen.complete_job_by_ref(
        tmp_path,
        repo=REPO,
        task="MRB",
        ident="#656",
        nick="marchhare-1",
        result="PASS",
        url=f"https://github.com/{REPO}/pull/656",
    )
    assert st == "ok"
    assert [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("task") == "MRB"] == []


def test_github_pr_exists_checker_requires_open_state():
    """Merged/closed PRs return HTTP 200 but must not count as offerable."""
    import sys
    import types

    bodies = {
        "1": json.dumps({"state": "open", "merged": False, "number": 1}).encode(),
        "2": json.dumps({"state": "closed", "merged": True, "number": 2}).encode(),
        "3": json.dumps({"state": "closed", "merged": False, "number": 3}).encode(),
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
                check = gitclaim.github_pr_exists_checker(cache={})
                assert check is not None
                assert check("o/r", "1") is True
                assert check("o/r", "2") is False
                assert check("o/r", "3") is False
    finally:
        if prev is None:
            sys.modules.pop("gh_filer", None)
        else:
            sys.modules["gh_filer"] = prev
