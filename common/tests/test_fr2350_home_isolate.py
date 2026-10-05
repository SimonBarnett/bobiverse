"""FR #2350: explicit scratch --home must not merge ~/.agentic-irc-bobiverse."""
from __future__ import annotations

import json
import os
from pathlib import Path

import bob_home


def _seed_legacy(profile: Path) -> Path:
    old = profile / bob_home.LEGACY_DIGEST_NAME
    old.mkdir(parents=True)
    (old / "queue.json").write_text('{"v":1,"unaccepted":[],"marker":"legacy-seed"}', encoding="utf-8")
    (old / "chair-outbox.txt").write_text("PRIVMSG #x :old\n", encoding="utf-8")
    (old / "nickserv.password").write_text("secret-not-logged", encoding="utf-8")
    (old / "identity.json").write_text('{"pk":"legacy"}', encoding="utf-8")
    return old


def test_scratch_home_skips_profile_legacy_merge(tmp_path, monkeypatch):
    """UAT scratch under %TEMP% must stay empty of legacy digest files."""
    profile = tmp_path / "Users" / "Administrator"
    profile.mkdir(parents=True)
    old = _seed_legacy(profile)
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)
    monkeypatch.delenv("BOB_MIGRATE_LEGACY", raising=False)
    monkeypatch.delenv("BOB_HOME_NO_MIGRATE", raising=False)

    scratch = tmp_path / "bob-ear-uat-2350-scratch"
    scratch.mkdir()
    (scratch / "outbox.txt").write_text("PRIVMSG #t :seed\n", encoding="utf-8")

    res = bob_home.migrate_legacy(scratch, role="digest")
    assert res["status"] == "skipped-noncanonical"
    assert not (scratch / "queue.json").exists()
    assert not (scratch / "nickserv.password").exists()
    assert not (scratch / "identity.json").exists()
    assert not (scratch / "chair-outbox.txt").exists()
    assert not (scratch / "outbox.txt.legacy").exists()
    assert (scratch / "outbox.txt").read_text(encoding="utf-8").startswith("PRIVMSG #t")
    assert old.is_dir()  # legacy left untouched


def test_ensure_homes_scratch_digest_isolated(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    _seed_legacy(profile)
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)
    monkeypatch.delenv("BOB_MIGRATE_LEGACY", raising=False)

    scratch = tmp_path / "run" / "ear-home"
    logs: list[str] = []
    out = bob_home.ensure_homes(digest=scratch, log=logs.append)
    assert out and out[0]["status"] == "skipped-noncanonical"
    assert not (scratch / "queue.json").exists()
    assert any(("skipped" in line.lower()) or ("noncanonical" in line.lower()) for line in logs)


def test_canonical_bobiverse_home_still_migrates(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    _seed_legacy(profile)
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)
    monkeypatch.delenv("BOB_HOME_NO_MIGRATE", raising=False)

    new = profile / bob_home.DIGEST_NAME
    res = bob_home.migrate_legacy(new, role="digest")
    assert res["status"] == "migrated"
    assert (new / "queue.json").is_file()
    assert json.loads((new / "queue.json").read_text(encoding="utf-8"))["marker"] == "legacy-seed"


def test_install_basename_home_still_migrates(tmp_path, monkeypatch):
    """Fleet <ai root>\\bob\\home keeps one-time cutover from profile legacy."""
    profile = tmp_path / "profile"
    profile.mkdir()
    _seed_legacy(profile)
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)

    new = tmp_path / "ai" / "bob" / "home"
    res = bob_home.migrate_legacy(new, role="digest")
    assert res["status"] == "migrated"
    assert (new / "queue.json").is_file()


def test_opt_in_migrate_legacy_env_allows_scratch(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    _seed_legacy(profile)
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)
    monkeypatch.setenv("BOB_MIGRATE_LEGACY", "1")

    scratch = tmp_path / "custom-scratch-home"
    res = bob_home.migrate_legacy(scratch, role="digest")
    assert res["status"] == "migrated"
    assert (scratch / "queue.json").is_file()


def test_opt_out_no_migrate_blocks_canonical(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    _seed_legacy(profile)
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")

    new = profile / bob_home.DIGEST_NAME
    res = bob_home.migrate_legacy(new, role="digest")
    assert res["status"] == "skipped-opt-out"
    assert not (new / "queue.json").exists()


def test_explicit_old_homes_kwarg_still_migrates_scratch(tmp_path, monkeypatch):
    """Callers that pass old_homes= explicitly are intentional (tests / tools)."""
    monkeypatch.delenv("BOB_MIGRATE_LEGACY", raising=False)
    monkeypatch.delenv("BOB_HOME_NO_MIGRATE", raising=False)
    old = tmp_path / "legacy"
    old.mkdir()
    (old / "digest.json").write_text("{}", encoding="utf-8")
    scratch = tmp_path / "scratch-explicit"
    res = bob_home.migrate_legacy(scratch, old_homes=[old], role="digest")
    assert res["status"] == "migrated"
    assert (scratch / "digest.json").is_file()


def test_mrb2357_no_migrate_wins_over_migrate_legacy(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    _seed_legacy(profile)
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)
    monkeypatch.setenv("BOB_MIGRATE_LEGACY", "1")
    monkeypatch.setenv("BOB_HOME_NO_MIGRATE", "1")
    new = profile / bob_home.DIGEST_NAME
    res = bob_home.migrate_legacy(new, role="digest")
    assert res["status"] == "skipped-opt-out"
    assert not (new / "queue.json").exists()


def test_mrb2357_canonical_jeeves_chair_still_migrates(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    old = profile / bob_home.LEGACY_CHAIR_NAME
    old.mkdir()
    (old / "chair-outbox.txt").write_text("PRIVMSG #c :x\n", encoding="utf-8")
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)
    monkeypatch.delenv("BOB_HOME_NO_MIGRATE", raising=False)
    new = profile / bob_home.CHAIR_NAME
    res = bob_home.migrate_legacy(new, role="chair")
    assert res["status"] == "migrated"
    assert (new / "chair-outbox.txt").is_file()


def test_mrb2357_scratch_with_marker_reports_already(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_MIGRATE_LEGACY", raising=False)
    scratch = tmp_path / "ear-scratch-marked"
    scratch.mkdir()
    (scratch / bob_home.MARKER).write_text("already\n", encoding="utf-8")
    res = bob_home.migrate_legacy(scratch, role="digest")
    assert res["status"] == "already"


def test_mrb2357_ensure_homes_logs_skipped_noncanonical(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    _seed_legacy(profile)
    monkeypatch.setattr(bob_home, "_profile", lambda: profile)
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: profile)
    monkeypatch.delenv("BOB_MIGRATE_LEGACY", raising=False)
    monkeypatch.delenv("BOB_HOME_NO_MIGRATE", raising=False)
    scratch = tmp_path / "run" / "ear-home-2"
    logs: list[str] = []
    out = bob_home.ensure_homes(digest=scratch, log=logs.append)
    assert out and out[0]["status"] == "skipped-noncanonical"
    assert any("skipped-noncanonical" in line for line in logs)
