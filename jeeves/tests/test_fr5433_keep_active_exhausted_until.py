"""FR #5433: mark_tokens_exhausted keeps an already-active until and skips re-announce."""
from __future__ import annotations

import json

import copilot_dispatch as cd

NOW = 1_700_000_000.0


def test_fr5433_second_call_keeps_until_and_skips_announce(tmp_path):
    announced: list[str] = []
    first = cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=NOW, announce=announced.append
    )
    until = first["exhausted_until"]
    assert until == cd.first_of_next_month_utc(NOW)
    assert len(announced) == 1

    later = NOW + 3600
    second = cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=later, announce=announced.append
    )
    assert second["exhausted_until"] == until
    assert len(announced) == 1
    raw = json.loads((tmp_path / cd.ALLOWANCE_NAME).read_text(encoding="utf-8"))
    assert raw["exhausted_until"] == until
    assert raw["fuels"]["copilot"]["exhausted_until"] == until
    assert cd.cooldown_active(tmp_path, now=later, fuel="copilot")


def test_fr5433_expired_until_extends_and_announces(tmp_path):
    announced: list[str] = []
    cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=NOW, announce=announced.append
    )
    first_until = cd.first_of_next_month_utc(NOW)
    expired = first_until + 5
    again = cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=expired, announce=announced.append
    )
    assert again["exhausted_until"] == cd.first_of_next_month_utc(expired)
    assert len(announced) == 2


def test_fr5433_cursor_already_active_not_extended(tmp_path):
    announced: list[str] = []
    first = cd.mark_tokens_exhausted(
        tmp_path, fuel="cursor", now=NOW, announce=announced.append
    )
    later = NOW + 10
    second = cd.mark_tokens_exhausted(
        tmp_path, fuel="cursor", now=later, announce=announced.append
    )
    assert second["exhausted_until"] == first["exhausted_until"]
    assert len(announced) == 1
    assert not cd.cooldown_active(tmp_path, now=later, fuel="copilot")


def test_fr5433_pins():
    from pathlib import Path

    src = Path(cd.__file__).read_text(encoding="utf-8")
    assert "FR #5433" in src
    assert "_ = already" not in src
    assert "if already and now_f < already" in src
    assert not Path(cd.__file__).read_bytes().startswith(b"\xef\xbb\xbf")
