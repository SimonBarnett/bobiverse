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


def test_auto_mode_always_probes_even_with_explicit_nick():
    """1.0.0 regression (walrus): auto must ChanServ-probe; never force-registered on --nick.

    Explicit nick used to skip the probe and JOIN #<machine> unregistered (ops mess).
    """
    t = SERVICE.read_text(encoding="utf-8")
    block_001 = t.split('if cmd == "001":', 1)[1].split('if cmd == "433":', 1)[0]
    assert "_start_chanserv_probe" in block_001
    assert "_nick_explicit" not in block_001
    assert 'else "registered"' not in block_001
    assert 'if self.shop_mode == "registered"' in block_001
    assert 'elif self.shop_mode == "wonderland"' in block_001


def test_auto_initial_channel_is_wonderland_until_probe():
    """Before ChanServ settles, auto must not advertise/join #<machine>."""
    t = SERVICE.read_text(encoding="utf-8")
    init = t.split("class AircConsoleService:", 1)[1].split("def _start_chanserv_probe", 1)[0]
    assert 'if self.shop_mode == "registered":' in init
    assert "self.channel = self.shop_channel" in init
    assert "self.channel = self.wonderland_channel" in init
    # auto / wonderland share wonderland until probe; not else: shop_channel
    assert "else:\n            self.channel = self.shop_channel" not in init


def test_install_start_messages_mention_wonderland_fallback():
    """Install/Start must not claim unconditional JOIN #<machine> (msi-install.log on walrus)."""
    inst = (ROOT / "airc/scripts/Install-AircConsole.ps1").read_text(encoding="utf-8-sig")
    start = START_AIRC.read_text(encoding="utf-8-sig")
    assert "console will JOIN #" not in inst
    assert "else #wonderland" in inst
    assert "fleet shop #" not in start
    assert "else #wonderland" in start
