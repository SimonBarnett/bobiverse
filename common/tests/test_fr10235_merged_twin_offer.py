"""FR #10235: an FR whose title matches a MERGED PR is a twin and is never offered.

Class of #10114 / #10217: twin FRs were assigned even though fix PRs had already
merged to main. The offer gate now asks for a merged-PR title match before offering.
"""

from __future__ import annotations

import io
import json
import sys
import types
from pathlib import Path
from unittest import mock

import gitclaim


TITLE_TWIN = "Intake: check merged PRs for same title before assigning FR"
TITLE_OPEN = "Some other open feature request"


def _row(num: str, title: str) -> dict:
    return {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": f"#{num}",
        "url": f"https://github.com/SimonBarnett/bobiverse/issues/{num}",
        "title": title,
        "line": f"FR #{num}",
        "seq": int(num),
        "state": "open",
    }


def _home(tmp_path: Path, rows: list[dict]) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )
    return h


def _twin_only(repo: str, title: str) -> bool:
    return gitclaim._merged_twin_norm(title) == gitclaim._merged_twin_norm(TITLE_TWIN)


def test_fr_row_offerable_rejects_merged_twin_title():
    row = _row("10217", TITLE_TWIN)
    assert gitclaim.fr_row_offerable(row, merged_twin=_twin_only) is False


def test_fr_row_offerable_keeps_row_without_merged_twin():
    row = _row("10217", TITLE_TWIN)
    assert gitclaim.fr_row_offerable(row) is True
    assert gitclaim.fr_row_offerable(row, merged_twin=lambda r, t: False) is True


def test_fr_row_offerable_unknown_lookup_still_offers():
    row = _row("10217", TITLE_TWIN)

    def boom(repo, title):
        raise gitclaim.GitHubLookupUnknown("rate limited")

    assert gitclaim.fr_row_offerable(row, merged_twin=boom) is True


def test_offer_focus_top_skips_twin_and_offers_next(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 0)
    home = _home(
        tmp_path,
        [_row("10217", TITLE_TWIN), _row("10235", TITLE_OPEN)],
    )
    st, job = gitclaim.offer_focus_top(
        home, "marchhare-40208", "#marchhare", merged_twin=_twin_only
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#10235"


def test_offer_top_skips_twin(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gitclaim, "BORED_GITHUB_CALL_BUDGET", 0)
    home = _home(
        tmp_path,
        [_row("10217", TITLE_TWIN), _row("10235", TITLE_OPEN)],
    )
    st, job = gitclaim.offer_top(
        home, "marchhare-40208", "#marchhare", merged_twin=_twin_only
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#10235"


def test_merged_twin_norm_is_case_and_whitespace_insensitive():
    assert gitclaim._merged_twin_norm("  A   B\tc ") == gitclaim._merged_twin_norm("a b C")


class _Resp:
    def __init__(self, payload: dict):
        self.status = 200
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_gh_env():
    fake_gh = types.ModuleType("gh_filer")
    fake_gh.ensure_gh_token_env = lambda: "env"
    return fake_gh


def test_github_merged_twin_checker_matches_exact_merged_pr_title(monkeypatch):
    payload = {
        "total_count": 2,
        "items": [
            {"title": "Something else", "pull_request": {}},
            {"title": TITLE_TWIN.upper(), "pull_request": {}},
        ],
    }
    seen: list[str] = []

    def fake_urlopen(req, timeout=8):
        seen.append(getattr(req, "full_url", "") or str(req))
        return _Resp(payload)

    prev = sys.modules.get("gh_filer")
    sys.modules["gh_filer"] = _fake_gh_env()
    try:
        with mock.patch.dict(
            "os.environ", {"GH_TOKEN": "fake-token-not-real", "GITHUB_TOKEN": ""}
        ):
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                check = gitclaim.github_merged_twin_checker(cache={})
                assert check is not None
                assert check("SimonBarnett/bobiverse", TITLE_TWIN) is True
    finally:
        if prev is None:
            sys.modules.pop("gh_filer", None)
        else:
            sys.modules["gh_filer"] = prev
    assert seen and "search/issues" in seen[0]
    assert "is%3Apr" in seen[0] and "is%3Amerged" in seen[0]


def test_github_merged_twin_checker_no_exact_match_is_false(monkeypatch):
    payload = {"total_count": 1, "items": [{"title": "Unrelated", "pull_request": {}}]}
    prev = sys.modules.get("gh_filer")
    sys.modules["gh_filer"] = _fake_gh_env()
    try:
        with mock.patch.dict(
            "os.environ", {"GH_TOKEN": "fake-token-not-real", "GITHUB_TOKEN": ""}
        ):
            with mock.patch("urllib.request.urlopen", return_value=_Resp(payload)):
                check = gitclaim.github_merged_twin_checker(cache={})
                assert check("SimonBarnett/bobiverse", TITLE_TWIN) is False
    finally:
        if prev is None:
            sys.modules.pop("gh_filer", None)
        else:
            sys.modules["gh_filer"] = prev


def test_github_merged_twin_checker_http_error_is_unknown_not_twin(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=8):
        raise urllib.error.HTTPError(
            getattr(req, "full_url", ""), 503, "unavailable", {}, io.BytesIO(b"")
        )

    prev = sys.modules.get("gh_filer")
    sys.modules["gh_filer"] = _fake_gh_env()
    try:
        with mock.patch.dict(
            "os.environ", {"GH_TOKEN": "fake-token-not-real", "GITHUB_TOKEN": ""}
        ):
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                check = gitclaim.github_merged_twin_checker(cache={})
                try:
                    check("SimonBarnett/bobiverse", TITLE_TWIN)
                except gitclaim.GitHubLookupUnknown:
                    pass
                else:
                    raise AssertionError("expected GitHubLookupUnknown")
    finally:
        if prev is None:
            sys.modules.pop("gh_filer", None)
        else:
            sys.modules["gh_filer"] = prev
