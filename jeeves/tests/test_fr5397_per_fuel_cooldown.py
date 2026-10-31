"""FR #5397: per-fuel exhausted_until; cursor cooldown does not share Copilot."""
from __future__ import annotations

import json

import copilot_dispatch as cd

NOW = 1_700_000_000.0


def test_fr5397_cursor_cooldown_does_not_block_copilot(tmp_path):
    cd.set_allowance(tmp_path, remaining=4)
    cd.mark_tokens_exhausted(tmp_path, fuel="cursor", now=NOW)
    assert cd.cooldown_active(tmp_path, now=NOW, fuel="cursor")
    assert not cd.cooldown_active(tmp_path, now=NOW, fuel="copilot")
    assert cd.has_allowance(tmp_path, now=NOW)
    raw = json.loads((tmp_path / cd.ALLOWANCE_NAME).read_text(encoding="utf-8"))
    assert raw["fuels"]["cursor"]["exhausted_until"] == NOW + cd.fuel_cooldown_seconds("cursor")
    assert raw.get("state") != "exhausted"


def test_fr5397_copilot_still_uses_legacy_key(tmp_path):
    cd.mark_tokens_exhausted(tmp_path, fuel="copilot", now=NOW)
    assert cd.cooldown_active(tmp_path, now=NOW, fuel="copilot")
    assert not cd.cooldown_active(tmp_path, now=NOW, fuel="cursor")
    raw = json.loads((tmp_path / cd.ALLOWANCE_NAME).read_text(encoding="utf-8"))
    assert raw["exhausted_until"] == NOW + cd.COPILOT_COOLDOWN_S
    assert raw["fuels"]["copilot"]["exhausted_until"] == raw["exhausted_until"]


def test_fr5397_legacy_top_level_still_counts_as_copilot(tmp_path):
    cd.set_allowance(tmp_path, remaining=1)
    p = tmp_path / cd.ALLOWANCE_NAME
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["exhausted_until"] = NOW + 100
    p.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    assert cd.cooldown_active(tmp_path, now=NOW, fuel="copilot")
    assert not cd.cooldown_active(tmp_path, now=NOW, fuel="grok")


def test_fr5397_pins():
    from pathlib import Path

    src = Path(cd.__file__).read_text(encoding="utf-8")
    assert "FR #5397" in src
    assert "fuels" in src
    assert "_ = fuel" not in src
    assert not Path(cd.__file__).read_bytes().startswith(b"\xef\xbb\xbf")
