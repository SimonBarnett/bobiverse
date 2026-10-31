# FR #4345: Assert-BobiverseDns.ps1 playbook pins (content gates; no live DNS in CI).
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Assert-BobiverseDns.ps1"


def test_assert_bobiverse_dns_script_exists_no_bom():
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "script must be UTF-8 no BOM for shared common scripts"


def test_assert_bobiverse_dns_pins_required_hosts_and_repair_switches():
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in (
        "github.com",
        "api.github.com",
        "irc.ntsa.uk",
        "bob.ntsa.uk",
        "8.8.8.8",
        "1.1.1.1",
        "RepairDnsServers",
        "ClearStaleHostsPins",
        "Resolve-DnsName",
        "Set-DnsClientServerAddress",
        "needsElevation",
        "FR #4345",
    ):
        assert needle in text, f"missing needle {needle!r}"


def test_fleet_ops_skill_documents_dns_failure_row():
    skill = ROOT / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "Assert-BobiverseDns.ps1" in text
    assert "remote name could not be resolved" in text or "DNS fail" in text
    assert "FR #4345" in text
