"""FR #69: shop-listen ACK/DONE must use digest-home ChanServ roster, not stale chair-home copy.

Production: Jeeves --home ~/.jeeves and BOB_DIGEST_HOME=~/.bobiverse. ChanServ mirror is
written only to the digest home; a migrated ~/.jeeves/registered-machines.json can be stale.
apply_callback / is_roster_machine must resolve via fleet_digest_home so webhook is 204.
"""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import registered_machines as rm
import shop_listen


def _split_homes(tmp_path: Path, monkeypatch):
    chair = tmp_path / "chair"          # ~/.jeeves stand-in
    digest = tmp_path / "digest"        # ~/.bobiverse stand-in
    chair.mkdir()
    digest.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    # Stale chair roster (the bug): only the Ergo host, missing fleet shops
    (chair / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": ["win-mpre8vi4u6u"], "source": "stale-migrate"}),
        encoding="utf-8",
    )
    # Live ChanServ mirror in digest home
    rm.sync_from_chanserv(digest, ["#bobiverse", "#marchhare", "#ce-priority-dev1", "#win-mpre8vi4u6u"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return chair, digest


def test_is_roster_machine_reads_digest_home_not_stale_chair(tmp_path, monkeypatch):
    chair, digest = _split_homes(tmp_path, monkeypatch)
    assert rm.load_registered(chair) == {"win-mpre8vi4u6u"}
    assert "ce-priority-dev1" in rm.load_registered(digest)
    # Callers pass chair home (irc_agent --home); roster must still see digest mirror
    assert bobreport.is_roster_machine(chair, "ce-priority-dev1")
    assert bobreport.is_roster_machine(chair, "marchhare")
    assert not bobreport.is_roster_machine(chair, "evil-box")


def test_apply_callback_merge_against_chair_home_uses_digest_roster(tmp_path, monkeypatch):
    chair, digest = _split_homes(tmp_path, monkeypatch)
    payload = {
        "op": "merge",
        "machine": "ce-priority-dev1",
        "pid": 42,
        "nick": "ce-priority-dev1-42",
        "kind": "grok",
        "state": "running",
        "online": True,
        "working_on": "FR o/r#69",
    }
    out = bobreport.apply_callback(chair, payload, "Jeeves")
    assert out.ok, getattr(out, "err", None)
    # Digest activity lands in digest home, not chair home
    assert (digest / "digest.json").is_file()
    assert not (chair / "digest.json").is_file()
    doc = bobreport.load_digest(digest)
    ent = (doc.get("machines") or {}).get("ce-priority-dev1") or {}
    assert ent.get("working_on") == "FR o/r#69" or "ce-priority-dev1" in (doc.get("machines") or {})


def test_shop_listen_post_activity_returns_204_with_split_homes(tmp_path, monkeypatch):
    chair, digest = _split_homes(tmp_path, monkeypatch)
    payload = shop_listen.format_activity_payload(
        machine="ce-priority-dev1",
        pid=99,
        nick="ce-priority-dev1-99",
        kind="grok",
        working_on="FR SimonBarnett/bobiverse#69",
        state="running",
    )
    code = shop_listen.post_activity(chair, payload, briefer="Jeeves")
    assert code == 204
    # Stale chair roster alone would have yielded 400 before the fix
    assert bobreport.is_roster_machine(digest, "ce-priority-dev1")


def test_chair_migration_skips_digest_only_roster_file(tmp_path):
    """Chair home must not receive a second registered-machines.json that can go stale."""
    import bob_home

    old = tmp_path / ".agentic-irc-jeeves"
    old.mkdir()
    (old / "operators.txt").write_text("simon\n", encoding="utf-8")
    (old / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": ["win-mpre8vi4u6u"]}), encoding="utf-8"
    )
    (old / "digest.json").write_text("{}", encoding="utf-8")
    (old / "queue.json").write_text("{}", encoding="utf-8")
    new = tmp_path / ".jeeves"
    res = bob_home.migrate_legacy(new, role="chair")
    assert res["status"] == "migrated"
    assert (new / "operators.txt").is_file()
    assert not (new / "registered-machines.json").is_file()
    assert not (new / "digest.json").is_file()
    assert not (new / "queue.json").is_file()
