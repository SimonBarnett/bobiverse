"""FR #3834: airc control channel = registered #<machine> else #wonderland.

Drops #<domain|workgroup> fallback. Bob ears JOIN #wonderland; workers do not.
"""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
from repo_layout import ROOT

SERVICE = ROOT / "airc/scripts/airc_console_service.py"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
OPS = ROOT / "airc/docs/airc-ops.md"
START_AIRC = ROOT / "airc/scripts/Start-AircConsole.ps1"
START_BOB = ROOT / "bob/scripts/Start-Bob.ps1"
BOBREPORT = ROOT / "common/scripts/bobreport.py"
CHAN_PRIVS = ROOT / "common/scripts/chan_privs.py"
INBOUND = ROOT / "common/scripts/inbound_transcript.py"


def test_wonderland_helpers():
    assert ac.WONDERLAND_CHANNEL == "#wonderland"
    assert ac.wonderland_channel() == "#wonderland"
    assert ac.control_channel_reason("registered") == "registered-machine"
    assert ac.control_channel_reason("wonderland") == "wonderland-fallback"
    assert ac.control_channel_reason("domain-lobby") == "wonderland-fallback"
    line = ac.control_channel_log_line("#wonderland", "wonderland")
    assert "control-channel=#wonderland" in line
    assert "reason=wonderland-fallback" in line
    assert ac.normalize_shop_mode("domain-lobby") == "wonderland"
    assert ac.normalize_shop_mode("wonderland") == "wonderland"
    assert ac.normalize_shop_mode("auto") == "auto"
    assert ac.normalize_shop_mode("registered") == "registered"


def test_service_has_no_domain_control_fallback():
    t = SERVICE.read_text(encoding="utf-8")
    assert "wonderland_channel" in t
    assert 'self._apply_shop_mode("wonderland")' in t
    assert "chanserv-probe timeout -> wonderland" in t
    assert "normalize_shop_mode" in t
    # Control path must not join domain_channel / domain-lobby mode any more.
    assert 'self._apply_shop_mode("domain-lobby")' not in t
    assert "self.channel = self.domain_channel" not in t
    assert 'info(control_channel_log_line(self.channel, "wonderland"))' in t
    assert 'choices=["auto", "registered", "wonderland", "domain-lobby"]' in t


def test_start_airc_shop_mode_accepts_wonderland():
    t = START_AIRC.read_text(encoding="utf-8-sig")
    assert "wonderland" in t
    assert "ValidateSet('auto', 'registered', 'wonderland', 'domain-lobby')" in t


def test_bob_ear_joins_wonderland_workers_do_not():
    start = START_BOB.read_text(encoding="utf-8-sig")
    assert '#bobiverse,#wonderland,$shop' in start or (
        "#bobiverse,#wonderland," in start and "$shop" in start
    )
    br = BOBREPORT.read_text(encoding="utf-8")
    assert 'WONDERLAND_CHANNEL = "#wonderland"' in br
    assert "return [FLEET_CHANNEL, WONDERLAND_CHANNEL, shop]" in br
    assert "return [FLEET_CHANNEL, WONDERLAND_CHANNEL] + shops" in br
    # Workers / talk seats stay shop-only (no wonderland).
    assert "return [shop_channel(worker[0])]" in br
    assert "return [shop_channel(talk_mid)]" in br
    inbound = INBOUND.read_text(encoding="utf-8")
    assert "#bobiverse,#wonderland,#{mid}" in inbound


def test_jeeves_grants_bob_ear_ops_in_wonderland():
    t = CHAN_PRIVS.read_text(encoding="utf-8")
    assert 'WONDERLAND_CHANNEL = "#wonderland"' in t
    assert "cl == WONDERLAND_CHANNEL" in t
    assert 'Action(\n                        "grant"' in t or '"o"' in t
    assert "ear is ops in {WONDERLAND_CHANNEL}" in t or "ear is ops in" in t


def test_docs_skill_wonderland_rule():
    skill = SKILL.read_text(encoding="utf-8")
    assert "#wonderland" in skill
    assert "wonderland-fallback" in skill or "FR #3834" in skill
    assert "domain-fallback" not in skill or "supersedes" in skill.lower() or "FR #3834" in skill
    ops = OPS.read_text(encoding="utf-8")
    assert "#wonderland" in ops
    assert "FR #3834" in ops or "wonderland" in ops.lower()


def test_no_domain_workgroup_join_in_control_path_source():
    """Acceptance: no code path joins #<domain|workgroup> as control channel."""
    t = SERVICE.read_text(encoding="utf-8")
    # domain_channel may still exist for log/compat helpers, but must not be assigned to self.channel
    assert "self.channel = self.domain_channel" not in t
    assert "self.channel = domain_channel" not in t
