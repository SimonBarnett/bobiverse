# -*- coding: utf-8 -*-
"""FR #9780: !recycle accepts shop seat nick <machine>-<pid> (unit + docs pins)."""
from __future__ import annotations

from pathlib import Path

import bob_recycle
import bobreport
import registered_machines as rm


def test_fr9780_resolve_recycle_seat_maps_nick(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.save_registered(tmp_path, {"flamingo", "marchhare", "redqueen"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    hit = bob_recycle.resolve_recycle_seat("flamingo-17160")
    assert hit == ("flamingo", "flamingo-17160")
    assert bob_recycle.resolve_recycle_machine("flamingo-17160") == "flamingo"
    assert bob_recycle.resolve_recycle_machine("flamingo") == "flamingo"
    assert bob_recycle.resolve_recycle_seat("nosuchbox-1") is None
    assert bob_recycle.resolve_recycle_machine("nosuchbox-1") is None
    # Bob-<machine> ear form still resolves.
    assert bob_recycle.resolve_recycle_machine("bob-flamingo") == "flamingo"


def test_fr9780_docs_mention_seat_nick():
    root = Path(__file__).resolve().parents[2]
    text = (root / "jeeves/docs/jeeves-commands.md").read_text(encoding="utf-8")
    assert "FR #9780" in text
    assert "<machine>-<pid>" in text
