"""FR #1 / vision.md S1-S4: bobiverse MSI fleet acceptance locks.

Locks the deliverables from docs/vision.md and docs/feature-request-bobiverse-msi-fleet.md:
  S1 Three MSIs publish (pack wires jeeves/bob/airc + distinct UpgradeCodes + MajorUpgrade)
  S2 !register + Bob mode grants (+o shop / +h #bobiverse)
  S3 Recycle path (systray Restart-BobEar + !recycle)
  S4 Self-update on service start (Update-BobiverseService from Start-*)
Plus: tools IF MISSING, skills staged per MSI, AGENTS per product.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from repo_layout import ROOT  # t773u / FR #2633: split repo; legacy flat paths resolve per service

S = ROOT / "scripts"
DOCS = ROOT / "docs"
SKILLS = ROOT / ".grok" / "skills"
PACK = S / "Pack-BobiverseRelease.ps1"
BOOT = S / "Install-BootstrapTools.ps1"
UPD = S / "Update-BobiverseService.ps1"
REPO = "SimonBarnett/bobiverse"
PRODUCTS = ("jeeves", "bob", "airc")
UPGRADE = {
    "jeeves": "B7E3C9A1-4F2D-4E8B-9C11-A1BC00FEE001",
    "bob": "B7E3C9A1-4F2D-4E8B-9C11-A1BC0000B0B1",
    "airc": "B7E3C9A1-4F2D-4E8B-9C11-A1BC00A1C001",
}
# Must never collide with agentic_irc airc-console (issue #12).
AIRC_CONSOLE_LEGACY = "B7E3C9A1-4F2D-4E8B-9C11-A1BC00501E01"


def _t(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


# --- S1: three MSIs / clean reinstall ---------------------------------------


def test_s1_pack_builds_all_three_products():
    t = _t(PACK)
    assert "@('jeeves', 'bob', 'airc')" in t or '"jeeves", "bob", "airc"' in t.replace(" ", "")
    for p in PRODUCTS:
        assert f"'{p}'" in t
        assert UPGRADE[p] in t
        assert f"Install-{p[0].upper() + p[1:]}.cmd" in t or {
            "jeeves": "Install-Jeeves.cmd",
            "bob": "Install-Bob.cmd",
            "airc": "Install-Airc.cmd",
        }[p] in t
    assert AIRC_CONSOLE_LEGACY not in t or UPGRADE["airc"] != AIRC_CONSOLE_LEGACY
    assert UPGRADE["airc"] != AIRC_CONSOLE_LEGACY
    assert "MajorUpgrade" in t
    assert 'Schedule="afterInstallInitialize"' in t
    assert len(set(UPGRADE.values())) == 3


def test_s1_install_entrypoints_exist():
    for name in (
        "Install-Jeeves.ps1",
        "Install-Jeeves.cmd",
        "Install-Bob.ps1",
        "Install-Bob.cmd",
        "Install-Airc.ps1",
        "Install-Airc.cmd",
        "Install-BootstrapTools.ps1",
        "Pack-BobiverseRelease.ps1",
    ):
        assert (S / name).is_file(), name


def test_s1_version_file_present():
    ver = ROOT / "src" / "VERSION"
    assert ver.is_file()
    text = ver.read_text(encoding="utf-8").strip()
    assert re.match(r"^\d+\.\d+\.\d+", text), text


@pytest.mark.skipif(os.environ.get("BOBIVERSE_SKIP_LIVE") == "1", reason="live release check opted out")
def test_s1_latest_release_lists_three_msi_assets():
    """Live S1: gh release assets (network). Soft-skip when offline."""
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bobiverse-fr1-acceptance", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        pytest.skip(f"release API unreachable: {e}")
    names = {a.get("name", "") for a in data.get("assets") or []}
    tag = data.get("tag_name") or ""
    ver = tag.lstrip("v")
    for p in PRODUCTS:
        assert f"{p}-{ver}.msi" in names, f"missing {p}-{ver}.msi in {tag}; have {sorted(names)}"


# --- tools IF MISSING + skills ----------------------------------------------


def test_tools_if_missing_skips_present_tools():
    t = _t(BOOT)
    assert "IF MISSING" in t
    assert "$ForceTools" in t
    assert "tool-present" in t
    assert "if (-not $ForceTools -and (& $Present))" in t
    for inst in ("Install-Bob.ps1", "Install-Jeeves.ps1", "Install-Airc.ps1"):
        it = _t(S / inst)
        assert "Install-BootstrapTools.ps1" in it
        assert "ForceTools" in it


def test_msi_stages_product_skills_and_agents():
    t = _t(PACK)
    assert "bobiverse-$Name" in t or "bobiverse-" in t
    assert ".grok\\skills" in t or ".grok/skills" in t.replace("\\", "/")
    assert "AGENTS.$Name.md" in t
    for p in PRODUCTS:
        assert (ROOT / f"AGENTS.{p}.md").is_file(), f"AGENTS.{p}.md"
        assert (SKILLS / f"bobiverse-{p}" / "SKILL.md").is_file(), f"skill bobiverse-{p}"
    assert (SKILLS / "harvest" / "SKILL.md").is_file() or (SKILLS / "harvest-agent-skills" / "SKILL.md").is_file()


# --- S2: !register + Bob mode grants ----------------------------------------


def test_s2_register_parse_and_bob_nick():
    import sys

    sys.path.insert(0, str(S))
    import registered_machines as rm

    assert rm.parse_register_command("!register MarchHare") == "marchhare"
    assert rm.bob_nick_for_machine("marchhare") == "Bob-marchhare"
    assert rm.machine_from_bob_nick("Bob-marchhare") == "marchhare"


def test_s2_chan_privs_grant_bob_plus_o_shop_and_plus_h_fleet():
    t = _t(S / "chan_privs.py")
    assert "+o in its OWN" in t or "ear is ops in its own channel" in t
    assert "+h in #bobiverse" in t or "half-op in" in t
    assert 'FLEET_CHANNEL = "#bobiverse"' in t
    # plan_actions must emit grant o on shop and grant h on fleet
    assert 'Action("grant", chan, nick, "o"' in t
    assert 'Action("grant", chan, nick, "h"' in t
    irc = _t(S / "irc_agent.py")
    assert "!register" in irc
    assert "operators only" in irc or "ERR !register denied" in irc


# --- S3: recycle / systray restart ------------------------------------------


def test_s3_restart_bob_ear_and_tray_wiring():
    ear = _t(S / "Restart-BobEar.ps1")
    assert "Restart-Service" in ear
    assert "ircBob" in ear
    assert "depart-request" in ear
    # FR #2943: service ear home (not profile-only .bobiverse) + outbox announce.
    assert "Get-BobiverseEarServiceHome" in ear or ("home" in ear and "outbox.txt" in ear)
    assert "outbox.txt" in ear
    tray = _t(S / "Start-BobTray.ps1")
    # Tray start recycles ircBob via Start-BobFleetTray (Restart-BobEar remains the ear-only path).
    assert "Start-BobFleetTray" in tray or "Restart-BobEar" in tray
    assert "ircBob" in tray
    assert (S / "bob_recycle.py").is_file()
    common = _t(S / "Bobiverse-Common.ps1")
    assert "function Get-BobiverseEarServiceHome" in common


def test_s3_recycle_parse_jeeves_and_machine(monkeypatch):
    import sys

    sys.path.insert(0, str(S))
    import bob_recycle

    assert bob_recycle.parse_recycle_query("!recycle jeeves") == ("run", "jeeves")
    # CI runners are not fleet boxes: pin chair home so marchhare resolves without roster.
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "marchhare")
    assert bob_recycle.parse_recycle_query("!recycle marchhare")[0] == "run"


# --- S4: self-update on service start ---------------------------------------


def test_s4_start_scripts_invoke_updater():
    for name in ("Start-Bob.ps1", "Start-Jeeves.ps1", "Start-AircConsole.ps1"):
        t = _t(S / name)
        assert "Update-BobiverseService.ps1" in t, name
        assert "self-update" in t.lower() or "v0.1.17" in t
    assert UPD.is_file()
    ut = _t(UPD)
    assert "sha256" in ut.lower() or "SHA256" in ut
    assert "BOBIVERSE_NO_UPDATE" in ut or "BOB_AUTOUPDATE" in ut
    # CAST IRON: never touch Ergo / seats from updater
    assert "Ergo" in ut or "BobIrcd" in ut or "never" in ut.lower()


def test_s4_vision_and_fr_docs_present():
    vision = _t(DOCS / "vision.md")
    assert "S1" in vision and "S2" in vision and "S3" in vision and "S4" in vision
    assert "jeeves-*.msi" in vision and "bob-*.msi" in vision and "airc-*.msi" in vision
    fr = _t(DOCS / "feature-request-bobiverse-msi-fleet.md")
    assert "Three MSIs" in fr or "jeeves" in fr.lower()
    assert "Release self-update" in fr or "self-update" in fr.lower()
