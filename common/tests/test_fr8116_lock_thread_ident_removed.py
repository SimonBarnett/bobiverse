"""FR #8116: bobreport._lock_thread_ident removed after FR #8103 orphan_open path."""
from __future__ import annotations

from pathlib import Path

import bobreport


def test_fr8116_lock_thread_ident_helper_removed():
    assert not hasattr(bobreport, "_lock_thread_ident")
    src = Path(bobreport.__file__).read_text(encoding="utf-8")
    assert "def _lock_thread_ident" not in src
    # Orphan path still uses in-memory holder tracking + alive check.
    assert hasattr(bobreport, "_thread_ident_alive")
    assert hasattr(bobreport, "reclaim_orphaned_digest_lock")
