"""MRB #5477 hostile extras for FR #5433 keep-active exhausted_until."""
from __future__ import annotations

import json

import copilot_dispatch as cd

NOW = 1_700_000_000.0


def test_mrb5477_exact_expiry_extends(tmp_path):
    announced: list[str] = []
    first = cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=NOW, announce=announced.append
    )
    until = first["exhausted_until"]
    at_expiry = cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=until, announce=announced.append
    )
    assert at_expiry["exhausted_until"] == cd.first_of_next_month_utc(until)
    assert len(announced) == 2


def test_mrb5477_cursor_keep_does_not_pause_copilot(tmp_path):
    announced: list[str] = []
    cd.mark_tokens_exhausted(tmp_path, fuel="cursor", now=NOW, announce=announced.append)
    later = NOW + 60
    cd.mark_tokens_exhausted(tmp_path, fuel="cursor", now=later, announce=announced.append)
    assert len(announced) == 1
    assert not cd.cooldown_active(tmp_path, now=later, fuel="copilot")
    raw = json.loads((tmp_path / cd.ALLOWANCE_NAME).read_text(encoding="utf-8"))
    assert "exhausted_until" not in raw or raw.get("state") != "exhausted"


def test_mrb5477_released_zero_on_second_keep(tmp_path):
    announced: list[str] = []
    first = cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=NOW, announce=announced.append
    )
    second = cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=NOW + 1, announce=announced.append
    )
    assert first["released"] == 0
    assert second["released"] == 0
    assert second["exhausted_until"] == first["exhausted_until"]
