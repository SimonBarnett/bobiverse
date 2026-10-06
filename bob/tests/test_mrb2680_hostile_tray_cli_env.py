"""MRB #2680 hostile: tray/CLI env parity edges (FR #2669)."""
from __future__ import annotations

import bob_worker as bw
from repo_layout import resolve


def test_mrb2680_unc_prefix_preserved():
    out = bw.normalize_bob_home_path(r"\\server\share\bob")
    assert out.startswith(r"\\")
    assert r"share\bob" in out.replace("/", "\\")
    assert r"\\\server" not in out


def test_mrb2680_forward_slashes_normalized():
    assert bw.normalize_bob_home_path("C:/Users/x/.bobiverse") == r"C:\Users\x\.bobiverse"


def test_mrb2680_seat_env_extra_keys_are_bob_only():
    """child['env'] must not reintroduce CURSOR_*/SAND_* after prepare scrub."""
    extra = bw.seat_env_extra(r"C:\run\seat", "marchhare", "marchhare-1")
    for k in extra:
        assert k.startswith("BOB_"), k
        assert not k.upper().startswith("CURSOR_")
        assert not k.upper().startswith("SAND_")


def test_mrb2680_prepare_documents_extra_cursor_gap_then_seat_safe():
    """Belt check: seat extras stay clean; CURSOR in base/extra is scrubbed (FR #2683)."""
    base = {"CURSOR_API_KEY": "fake", "BOB_IRC_HOME": r"C:\\Users\\x\\.bob"}
    out = bw.prepare_seat_child_env(base, bw.seat_env_extra(r"C:\r", "m", "m-1"))
    assert "CURSOR_API_KEY" not in out
    assert out["BOB_IRC_HOME"] == r"C:\Users\x\.bob"
    assert "BOB_OUTBOX" in out
    # FR #2683: even a hostile extra overlay cannot reintroduce agent-host keys.
    hostile = bw.prepare_seat_child_env(base, {"CURSOR_FROM_EXTRA": "b"})
    assert "CURSOR_FROM_EXTRA" not in hostile
    assert "CURSOR_API_KEY" not in hostile


def test_mrb2680_fleet_tray_source_uses_single_quoted_assigns():
    fleet = resolve("bob/tray/tools/Start-BobFleetTray.ps1").read_text(encoding="utf-8-sig")
    assert "FR #2669" in fleet
    assert "hasDoubledEnv" in fleet
    assert ".Replace('\\', '\\\\')" not in fleet
    assert '$env:BOB_BRIDGE_HOME = ' in fleet or "BOB_BRIDGE_HOME" in fleet
    # Single-quoted assign pattern from the FR fix
    assert "''{0}''" in fleet or "'''{0}'''" in fleet or "''{0}'''" in fleet


def test_mrb2680_troubleshooting_mentions_doubled_bob_home():
    skill = resolve("bob/.grok/skills/bobiverse-bob-troubleshooting/SKILL.md").read_text(encoding="utf-8")
    low = skill.lower()
    assert "2669" in skill or "doubled" in low or "backslash" in low
    assert "bob_irc_home" in low or "bob_bridge_home" in low or "start-bobfleettray" in low
