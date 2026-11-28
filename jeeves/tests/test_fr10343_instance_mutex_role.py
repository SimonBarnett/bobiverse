"""FR #10343: http-only and chair roles share digest home, distinct mutexes."""
from __future__ import annotations

import jeeves_locks


def test_fr10343_mutex_roles_differ_for_same_digest_home(tmp_path):
    home = tmp_path
    http_name = jeeves_locks.mutex_name_for_home(home, "http")
    chair_name = jeeves_locks.mutex_name_for_home(home, "chair")
    assert http_name != chair_name
    assert http_name.endswith("-http")
    assert chair_name.endswith("-chair")


def test_fr10343_resolve_role_split_services():
    assert jeeves_locks.resolve_instance_mutex_role(
        http_only=True, chair=False, chair_only=False
    ) == "http"
    assert jeeves_locks.resolve_instance_mutex_role(
        http_only=False, chair=True, chair_only=False
    ) == "chair"
    assert jeeves_locks.resolve_instance_mutex_role(
        http_only=False, chair=False, chair_only=True
    ) == "chair"


def test_fr10343_dual_acquire_same_role_blocks_on_windows(tmp_path, monkeypatch):
    if __import__("os").name != "nt":
        return
    home = tmp_path
    assert jeeves_locks.try_acquire_instance_mutex(home, "http") is True
    try:
        assert jeeves_locks.try_acquire_instance_mutex(home, "http") is False
        assert jeeves_locks.try_acquire_instance_mutex(home, "chair") is True
    finally:
        jeeves_locks.release_instance_mutex()
        jeeves_locks.release_instance_mutex()