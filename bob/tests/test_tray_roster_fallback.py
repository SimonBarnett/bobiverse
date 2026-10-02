import json
import re
from pathlib import Path
from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service

T = ROOT / "third_party" / "bob-tray"


def _txt(rel):
    return (T / rel).read_text(encoding="utf-8-sig")


def test_bobiverse_json_has_no_hardcoded_fleet_nicks():
    cfg = json.loads(_txt("config/bobiverse.json"))
    assert cfg["nicks"] == {} and cfg["shortids"] == {}
    assert "chairHome" not in cfg
    # the only ionos mention is a LEGACY alias that maps to the machine name
    assert cfg["legacyAliases"]["ionos"] == "win-mpre8vi4u6u"
    assert "ionos" not in json.dumps({k: v for k, v in cfg.items() if k != "legacyAliases"})


def test_seat_and_registry_configs_use_machine_name_not_ionos():
    assert "ionos" not in _txt("config/bob-seats.json")
    assert "ionos" not in _txt("config/fleet-registry.json")
    assert "win-mpre8vi4u6u" in _txt("config/bob-seats.json")


def test_machine_ids_come_from_roster_plus_local_not_config():
    t = _txt("src/Private/Get-BobIrc.ps1")
    body = t.split("function Get-BobiverseMachineIds", 1)[1].split("function Resolve-BobiverseMachineId", 1)[0]
    assert "$script:BobRosterIds" in body and "Get-ThisMachineId" in body
    assert "$cfg.nicks" not in body and "Get-BobiverseConfig" not in body


def test_hover_fallback_is_local_plus_digest_machine_keys_only():
    t = _txt("src/Public/Get-BobTrayHover.ps1")
    assert "roster_machine_ids" in t
    fb = t.split("digest has no roster", 1)[1].split("$digestView = Expand-BobReportDigestView", 1)[0]
    assert "$machineId" in fb and "$reportDigest.machines" in fb
    assert "Get-BobiverseConfig" not in fb and "nicks" not in fb
    seat = t.split("$seatIds = @(Select-BobUniqueCanonicalIds @($script:BobRosterIds))", 1)
    assert len(seat) == 2
    assert "Get-BobiverseMachineIds" not in t.split("$specBy = @{}", 1)[1].split("$knownTile", 1)[0]


def test_legacy_alias_resolution_present_and_machine_scoped():
    t = _txt("src/Private/Get-BobIrc.ps1")
    r = t.split("function Resolve-BobiverseMachineId", 1)[1].split("function ", 1)[0]
    assert "legacyAliases" in r


def test_no_ionos_machine_id_in_tray_src_logic():
    for rel in ("src/Private/Get-BobIrc.ps1", "src/Private/Invoke-BobRepoPair.ps1", "tools/Start-BobFleetTray.ps1"):
        for ln in _txt(rel).splitlines():
            if re.search(r"(?i)\bionos\b", ln):
                assert ln.lstrip().startswith("#"), (rel, ln)
