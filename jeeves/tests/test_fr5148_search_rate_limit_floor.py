"""FR #5148: search-bucket remaining must not trip the core 500 floor."""
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


def test_fr5148_search_remaining_29_does_not_block_reconcile(tmp_path: Path):
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    bud.rate_remaining = 3286
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "search",
                "X-RateLimit-Remaining": "29",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    assert bud.rate_remaining == 3286
    assert bud.allow("reconcile", essential=False) is True
    assert bud.in_backoff() is False
    assert not any("rate-limit-floor" in ln for ln in logs)


def test_fr5148_core_remaining_29_still_triggers_floor(tmp_path: Path):
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "core",
                "X-RateLimit-Remaining": "29",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    assert bud.rate_remaining == 29
    assert bud.allow("reconcile", essential=False) is False
    assert any("rate-limit-floor" in ln for ln in logs)
    why = bud.skip_reason("reconcile")
    assert "rate-limit-floor" in why
    assert "remaining=29" in why


def test_fr5148_missing_resource_header_is_core(tmp_path: Path):
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    bud.note_headers(_Hdr({"X-RateLimit-Remaining": "29", "X-RateLimit-Reset": "1999999999"}))
    assert bud.rate_remaining == 29
    assert bud.allow("reconcile") is False


def test_fr5148_resync_cycle_after_search_headers_processes_repos(tmp_path: Path, monkeypatch):
    """Search 29 remaining must not yield github-resync ok repos=0 failed=N."""
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "SimonBarnett/bobiverse")
    (tmp_path / "registered-machines.json").write_text('{"v":1,"machines":[]}', encoding="utf-8")
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
    assert bud.allow("reconcile") is True
    assert "SimonBarnett/bobiverse" not in (out.get("failed") or [])
    # Configured repo is fetched (issues + pulls), not skipped as failed= after search.
    assert any("/repos/SimonBarnett/bobiverse/issues" in u for u in calls)


def test_fr5148_chair_logs_resync_degraded_when_core_floor_blocks(tmp_path: Path):
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    bud.note_headers(
        _Hdr(
            {
                "X-RateLimit-Resource": "core",
                "X-RateLimit-Remaining": "29",
                "X-RateLimit-Reset": "1999999999",
            }
        )
    )
    out = ch.resync_cycle(
        tmp_path,
        token="tok",
        ignored=[],
        budget=bud,
        essential=False,
        log=logs.append,
        owners={"simonbarnett"},
    )
    assert out.get("note") in ("budget-backoff", "resync_degraded")
    joined = "\n".join(logs)
    assert "resync_degraded" in joined or "github-resync skipped" in joined
    assert "failed=11" not in joined
    assert not any(ln.startswith("INFO github-resync ok") and "failed=" in ln for ln in logs)
