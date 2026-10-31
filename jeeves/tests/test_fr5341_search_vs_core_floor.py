"""FR #5341: core 500 floor must not apply to the search 30/min bucket."""
from __future__ import annotations

from pathlib import Path

import chair_health as ch
import github_api_budget as gab


class _Hdr(dict):
    def get(self, k, default=None):
        for key in (k, k.lower(), k.title()):
            if key in self:
                return dict.get(self, key, default)
        return default


def test_fr5341_core_4000_search_25_lets_sync_run(tmp_path: Path):
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    bud.rate_remaining = 4000
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "search",
                "X-RateLimit-Remaining": "25",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    assert bud.rate_remaining == 4000
    assert bud.search_rate_remaining == 25
    assert bud.allow("reconcile", essential=False) is True
    assert bud.in_backoff() is False


def test_fr5341_core_400_still_backs_off(tmp_path: Path):
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "core",
                "X-RateLimit-Remaining": "400",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    assert bud.rate_remaining == 400
    assert bud.allow("reconcile", essential=False) is False
    assert bud.in_backoff() is True
    assert "rate-limit-floor" in bud.skip_reason("reconcile")


def test_fr5341_search_floor_does_not_block_core_reconcile(tmp_path: Path):
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    bud.rate_remaining = 4000
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "search",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    assert bud.allow("reconcile") is True
    assert bud.allow("search", essential=False) is False


def test_fr5341_resync_cycle_core_4000_search_25(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "SimonBarnett/bobiverse")
    (tmp_path / "registered-machines.json").write_text('{"v":1,"machines":[]}', encoding="utf-8")
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    bud.rate_remaining = 4000
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "search",
                "X-RateLimit-Remaining": "25",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    calls: list[str] = []

    def getter(url: str, force_refresh: bool = False):
        del force_refresh
        calls.append(url)
        if "/search/" in url:
            return {"items": []}
        return []

    out = ch.resync_cycle(
        tmp_path,
        token="tok",
        ignored=[],
        fetch_json=getter,
        budget=bud,
        essential=False,
        log=logs.append,
        owners={"simonbarnett"},
    )
    assert out.get("note") != "budget-backoff"
    assert "SimonBarnett/bobiverse" not in (out.get("failed") or [])
    assert any("/repos/SimonBarnett/bobiverse/issues" in u for u in calls)
