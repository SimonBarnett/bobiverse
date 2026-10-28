"""MRB #5149 hostile pins for FR #5148: search vs core rate floor."""
from __future__ import annotations

from pathlib import Path

import github_api_budget as gab


class _Hdr(dict):
    def get(self, k, default=None):
        for key in (k, k.lower(), k.title()):
            if key in self:
                return dict.get(self, key, default)
        return default


def test_mrb5149_search_resources_frozenset_includes_search_and_code_search():
    assert "search" in gab.SEARCH_RESOURCES
    assert "code_search" in gab.SEARCH_RESOURCES
    assert "core" not in gab.SEARCH_RESOURCES


def test_mrb5149_code_search_remaining_does_not_overwrite_core(tmp_path: Path):
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    bud.rate_remaining = 3000
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "code_search",
                "X-RateLimit-Remaining": "5",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    assert bud.rate_remaining == 3000
    assert bud.search_rate_remaining == 5
    assert bud.allow("reconcile", essential=False) is True


def test_mrb5149_graphql_remaining_does_not_overwrite_core(tmp_path: Path):
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    bud.rate_remaining = 2800
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "graphql",
                "X-RateLimit-Remaining": "40",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    assert bud.rate_remaining == 2800
    assert bud.allow("reconcile", essential=False) is True


def test_mrb5149_search_then_core_headers_keep_core_floor_decision(tmp_path: Path):
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "search",
                "X-RateLimit-Remaining": "29",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "core",
                "X-RateLimit-Remaining": "3286",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    assert bud.search_rate_remaining == 29
    assert bud.rate_remaining == 3286
    assert bud.allow("reconcile") is True
    assert bud.in_backoff() is False


def test_mrb5149_persist_roundtrip_keeps_search_bucket(tmp_path: Path):
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    bud.rate_remaining = 2000
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "search",
                "X-RateLimit-Remaining": "29",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    bud._persist_budget()
    bud2 = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    assert bud2.search_rate_remaining == 29
    assert bud2.rate_remaining == 2000
    assert bud2.allow("reconcile") is True


def test_mrb5149_source_pins_floor_comment_and_search_resources():
    src = Path(gab.__file__).read_text(encoding="utf-8")
    assert "FR #5148" in src
    assert "SEARCH_RESOURCES" in src
    assert "search_rate_remaining" in src
