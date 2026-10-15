"""FR #4315: common suite must not touch the live Administrator .bobiverse digest home.

!build sets BOBIVERSE_BUILD_SUITE=1 + BOB_HOME_NO_MIGRATE=1 and redirects USERPROFILE /
BOB_DIGEST_HOME (#4183). Under that env:
- ``_admin_profile`` must not resolve to the real ``C:\\Users\\Administrator``
- ``digest_home`` must stay under the redirected profile
- a planted live queue.json must stay byte-identical across ensure_homes / migrate calls
- fr2350 home-isolate tests must delenv BOB_HOME_NO_MIGRATE when they assert migrate /
  skipped-noncanonical (see test_fr2350_home_isolate.py)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import bob_home
import bobiverse_build as bb


def test_admin_profile_redirects_under_build_suite(tmp_path, monkeypatch):
    prof = tmp_path / "iso-profile"
    prof.mkdir()
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("USERPROFILE", str(prof))
    monkeypatch.setenv("HOME", str(prof))
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    assert bob_home._admin_profile() == prof
    assert bob_home._admin_profile() != Path(r"C:\Users\Administrator")
    assert bob_home.digest_home() == prof / bob_home.DIGEST_NAME


def test_isolated_suite_env_does_not_mutate_planted_live_queue(tmp_path, monkeypatch):
    """Simulate the ionos live digest home beside an isolated suite env."""
    live = tmp_path / "Users" / "Administrator" / ".bobiverse"
    live.mkdir(parents=True)
    rows = [{"repo": "o/r", "task": "FR", "id": f"#{i}"} for i in range(12)]
    qpath = live / "queue.json"
    before = json.dumps({"v": 1, "unaccepted": rows, "accepted": [], "done": []}, indent=2) + "\n"
    qpath.write_text(before, encoding="utf-8")
    before_bytes = qpath.read_bytes()

    env = bb.isolated_suite_env(tmp_path / "work", "common-HEAD")
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Re-import path resolution under the isolated env.
    assert str(bob_home.digest_home()).startswith(str(tmp_path / "work"))
    assert bob_home._admin_profile() == Path(env["USERPROFILE"])

    scratch = tmp_path / "work" / "ear-scratch"
    scratch.mkdir(parents=True)
    bob_home.ensure_homes(digest=scratch, log=lambda *_: None)
    bob_home.migrate_legacy(Path(env["BOB_DIGEST_HOME"]), role="digest")

    assert qpath.read_bytes() == before_bytes


def test_fr2350_migrate_works_when_no_migrate_cleared(tmp_path, monkeypatch):
    """Build isolation sets BOB_HOME_NO_MIGRATE=1; fr2350 must clear it to assert migrate."""
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")
    monkeypatch.setenv("BOB_MIGRATE_LEGACY", "1")
    profile = tmp_path / "profile"
    profile.mkdir()
    old = profile / bob_home.LEGACY_DIGEST_NAME
    old.mkdir()
    (old / "queue.json").write_text(
        '{"v":1,"unaccepted":[],"marker":"legacy-seed"}', encoding="utf-8"
    )
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)

    # Still blocked while NO_MIGRATE is set.
    scratch = tmp_path / "blocked-scratch"
    assert bob_home.migrate_legacy(scratch, role="digest")["status"] == "skipped-opt-out"

    monkeypatch.delenv("BOB_HOME_NO_MIGRATE", raising=False)
    scratch2 = tmp_path / "ok-scratch"
    res = bob_home.migrate_legacy(scratch2, role="digest")
    assert res["status"] == "migrated"
    assert (scratch2 / "queue.json").is_file()
