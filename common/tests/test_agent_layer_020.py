"""Agent-start layer (t759u): every installed service dir ships AGENTS.md / CLAUDE.md / GROK.md / .cursor rule and a
product skill book, each starting with the CAST IRON harvest rule; nothing secret; the pack stages it all."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
SKILLS = ROOT / ".grok" / "skills"
PRODUCTS = ("jeeves", "bob", "airc")
RULE_MARKERS = ("CAST IRON RULE - HARVEST AND FILE EVERYTHING", "Report-BobiverseIntakeIssue.ps1",
                "Invoke-BobiverseHarvest.ps1", "https://irc.ntsa.uk/bob/v1/intake", "-Repo SimonBarnett/bobiverse")
BOOKS = {
    "jeeves": [
        "bobiverse-jeeves",
        "bobiverse-jeeves-commands",
        "bobiverse-jeeves-troubleshooting",
        "bobiverse-jeeves-monitor",  # FR #756 MONITORING overlay
    ],
    "bob": ["bobiverse-bob", "bobiverse-bob-commands", "bobiverse-bob-troubleshooting"],
    "airc": ["bobiverse-airc", "bobiverse-airc-commands", "bobiverse-airc-troubleshooting"],
}
SHARED = ["bobiverse-fleet-ops", "harvest", "harvest-agent-skills"]
WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")


def _all_skill_files():
    return sorted(SKILLS.glob("*/SKILL.md"))


def test_every_skill_book_exists_and_has_matching_frontmatter():
    for names in BOOKS.values():
        for n in names:
            assert (SKILLS / n / "SKILL.md").is_file(), n
    for n in SHARED:
        assert (SKILLS / n / "SKILL.md").is_file(), n
    for f in _all_skill_files():
        t = f.read_text(encoding="utf-8-sig")
        m = re.match(r"---\nname: (\S+)\ndescription: >\n  .+\n---\n", t.replace("\r\n", "\n"), re.S)
        assert m, f"{f}: bad frontmatter"
        assert m.group(1) == f.parent.name, f


def test_cast_iron_rule_is_in_every_skill_and_every_agents_file():
    files = _all_skill_files() + [ROOT / f"AGENTS.{p}.md" for p in PRODUCTS]
    assert len(files) >= 9 + 3 + 3
    keep_flow = "## Keep the flow of work to the workers going"
    for f in files:
        t = f.read_text(encoding="utf-8-sig")
        for mk in RULE_MARKERS:
            assert mk in t, f"{f.name}: missing {mk!r}"
        # CAST IRON near the top. FR #756 (jeeves MONITORING): optional keep-the-flow
        # ## section may precede the CAST IRON blockquote; otherwise CAST IRON is before the first ##.
        norm = t.replace("\r\n", "\n")
        iron = norm.index("CAST IRON RULE - HARVEST AND FILE EVERYTHING")
        first_h2 = norm.find("\n## ")
        if first_h2 >= 0 and keep_flow in norm:
            # allow keep-the-flow as the first ##; CAST IRON must still appear before any later ##
            after_flow = norm.find("\n## ", norm.find(keep_flow) + len(keep_flow))
            assert iron < (after_flow if after_flow >= 0 else 10**9), f
        else:
            assert iron < (first_h2 if first_h2 >= 0 else 10**9), f


def test_rule_commands_are_real_script_parameters():
    rep = (ROOT / "scripts" / "Report-BobiverseIntakeIssue.ps1").read_text(encoding="utf-8-sig")
    hv = (ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    for p in ("$Title", "$Body", "$Repo", "$Kind"):
        assert p in rep
    assert "'issue', 'fr', 'skill', 'harvest'" in rep
    for p in ("$Summary", "$Lesson", "$SkillFile", "[switch]$Flush", "/bob/v1/intake", "harvest-outbox", "secretRx",
              "repo_not_allowed", "DROPPED", "Get-IntakeAllowRepos"):
        assert p in hv


def test_agents_files_cover_the_required_topics():
    need = ("Hotpatch safely", "back up", "Ergo", "secrets", "PowerShell only", "Machine ids", "Read first", "Common ops")
    for p in PRODUCTS:
        t = (ROOT / f"AGENTS.{p}.md").read_text(encoding="utf-8-sig")
        for n in need:
            assert n.lower() in t.lower(), (p, n)
        for book in BOOKS[p] + ["bobiverse-fleet-ops"]:
            assert f".grok/skills/{book}/SKILL.md" in t, (p, book)
    fleet = (SKILLS / "bobiverse-fleet-ops" / "SKILL.md").read_text(encoding="utf-8")
    for topic in ("Health checks", "Install / upgrade / self-update / rollback", "Hotpatch safely", "Channel privilege rules",
                  "Test procedures", "Machine id naming rules", "sasl-fail 904", "BOM", "--host", "hard-linked",
                  "digest.json*.tmp", "chanreg", "ChanServ"):
        assert topic in fleet, topic
    jv = (SKILLS / "bobiverse-jeeves" / "SKILL.md").read_text(encoding="utf-8")
    for topic in ("webhook-health.json", "15 min", "30 min", "config\\github.token", "resync-token-source.log", "7700", "6697"):
        assert topic in jv, topic
    assert "docs/jeeves-commands.md" in (SKILLS / "bobiverse-jeeves-commands" / "SKILL.md").read_text(encoding="utf-8")


ALLOWED_HOSTS = {"irc.ntsa.uk", "github.com", "api.github.com", "raw.githubusercontent.com", "nodejs.org"}


def test_no_secrets_and_no_private_hostnames_in_the_agent_layer():
    files = _all_skill_files() + [ROOT / f"AGENTS.{p}.md" for p in PRODUCTS] + [ROOT / "docs" / "jeeves-commands.md"]
    secret = re.compile(r"(ghp_[A-Za-z0-9]{16,}|github_pat_\w{16,}|xox[abpr]-[\w-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY|"
                        r"(?i:(password|passwd|secret|token)\s*[:=]\s*[A-Za-z0-9/+_.-]{8,}))")
    host = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:uk|com|org|net|io|local|lan|corp)\b", re.I)
    ip = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    for f in files:
        t = f.read_text(encoding="utf-8-sig")
        assert not secret.search(t), f"{f.name}: secret-shaped text"
        for h in host.findall(t):
            assert h.lower() in ALLOWED_HOSTS, f"{f.name}: non-public host {h}"
        for a in ip.findall(t):
            assert a == "127.0.0.1", f"{f.name}: ip {a}"
        assert not re.search(r"C:\\Users\\(?!Administrator|Default)\w+", t), f"{f.name}: personal profile path"


def test_installers_and_updaters_refresh_the_layer():
    sc = ROOT / "scripts"
    com = (sc / "Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
    assert "function Install-BobiverseAgentLayer" in com and "function Get-BobiverseSkillNames" in com
    for n, prod in (("Install-Jeeves.ps1", "jeeves"), ("Install-Bob.ps1", "bob"), ("Install-Airc.ps1", "airc")):
        t = (sc / n).read_text(encoding="utf-8-sig")
        assert f"Install-BobiverseAgentLayer -RepoRoot $repoRoot -InstallRoot $InstallRoot -Product '{prod}'" in t, n
        assert f"Get-BobiverseSkillNames -SkillsRoot $skillsDest -Product '{prod}'" in t, n
    upd = (sc / "Update-BobiverseService.ps1").read_text(encoding="utf-8-sig")
    assert "bobiverse-fleet-ops" in upd and '-like "bobiverse-$Product-*"' in upd
    syn = (sc / "Sync-BobiverseFromRepo.ps1").read_text(encoding="utf-8-sig")
    assert "sync-agent-layer" in syn and "CLAUDE.md" in syn and "GROK.md" in syn and "bobiverse-fleet-ops" in syn


@WIN
@pytest.mark.parametrize("prod", PRODUCTS)
def test_pack_stages_the_agent_layer_for_each_product(tmp_path, prod):
    out = tmp_path / "dist"
    run = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                          str(ROOT / "scripts" / "Pack-BobiverseRelease.ps1"), "-Product", prod, "-SkipMsi", "-KeepStage", "-SkipWorkerExe",
                          "-OutDir", str(out)], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stdout[-1500:] + run.stderr[-1500:]
    ver = (ROOT / "src" / "VERSION").read_text().strip()
    stage = out / f"{prod}-{ver}"
    assert stage.is_dir(), list(out.iterdir())
    for f in ("AGENTS.md", "CLAUDE.md", "GROK.md", f".cursor/rules/bobiverse-{prod}.mdc",
              "scripts/Invoke-BobiverseHarvest.ps1", "scripts/Report-BobiverseIntakeIssue.ps1", "assets/bob-systray.ico"):
        assert (stage / f).is_file(), f
    for f in ("AGENTS.md", "CLAUDE.md", "GROK.md", f".cursor/rules/bobiverse-{prod}.mdc"):
        t = (stage / f).read_text(encoding="utf-8-sig")
        for mk in RULE_MARKERS:
            assert mk in t, (f, mk)
    mdc = (stage / f".cursor/rules/bobiverse-{prod}.mdc").read_text(encoding="utf-8")
    assert mdc.startswith("---\n") and "alwaysApply: true" in mdc
    for book in BOOKS[prod] + SHARED:
        sk = stage / ".grok" / "skills" / book / "SKILL.md"
        assert sk.is_file(), book
        t = sk.read_text(encoding="utf-8-sig")
        for mk in RULE_MARKERS:
            assert mk in t, (book, mk)
    other = [p for p in PRODUCTS if p != prod]
    for p in other:
        assert not (stage / ".grok" / "skills" / f"bobiverse-{p}").exists(), f"{prod} pack leaked {p} skill"
    if prod == "jeeves":
        assert (stage / "docs" / "jeeves-commands.md").is_file()
    assert not list(stage.rglob("*.password")) and not list(stage.rglob("github.token"))
