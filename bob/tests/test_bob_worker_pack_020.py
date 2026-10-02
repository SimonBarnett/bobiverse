"""bob worker / plan (t762u..t772u): tray menu structure + one-window launch, the MSI payload (stage), the agent folders' skills text
(CAST IRON harvest rule, start guide, ACK/DONE contract, one skill each for FR/MRB/UAT with a mermaid diagram), and that a refresh
never deletes plan\\work or a running exe."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
TRAY = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
SK = ROOT / ".grok" / "skills"
WIN = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="needs Windows PowerShell")
RULE = ("CAST IRON RULE - HARVEST AND FILE EVERYTHING", "Report-BobiverseIntakeIssue.ps1", "Invoke-BobiverseHarvest.ps1",
        "https://irc.ntsa.uk/bob/v1/intake", "-Repo SimonBarnett/bobiverse")
RESUME_RX = re.compile(r"(?i)(--resume|--continue|-r\b|--session\b|--chat\b)")
JOB_SKILLS = ("bobiverse-bob-job-irc", "bobiverse-bob-job-fr", "bobiverse-bob-job-mrb", "bobiverse-bob-job-uat")


def _tray() -> str:
    return TRAY.read_text(encoding="utf-8-sig")


def _fn(text: str, name: str) -> str:
    m = re.search(r"(?m)^function %s \{" % re.escape(name), text)
    assert m, name
    end = re.search(r"(?m)^\}\s*$", text[m.start():])
    return text[m.start(): m.start() + end.end()]


# ------------------------------------------------------------------------------------------------ tray menu structure
def test_tray_agent_and_plan_are_plain_single_click_items_without_submenus():
    t = _tray()
    block = t[t.index("$miStatus = $menu.Items.Add('Status')"): t.index("$notify.ContextMenuStrip = $menu")]
    assert "$menu.Items.Add('Agent')" in block and "$menu.Items.Add('Plan')" in block
    assert "Add('Agents')" not in block and ".Text = 'Agents'" not in block
    assert "DropDown" not in block
    assert "$miAgents.Add_Click({ Start-BobTrayWorkerExe -Mode 'agent' })" in block
    assert "$miPlan.Add_Click({ Start-BobTrayWorkerExe -Mode 'plan' })" in block
    for gone in ("Build-BobTrayAgentsMenu", "Build-BobTrayPlanMenu", "Start-BobTrayPlanAgent", "New-BobTrayPlanWorkspace", "BobPlans"):
        assert gone not in t, gone
    assert "function Stop-BobTrayAgentWatchSeat" in t      # #32: seats are never killed by the tray on its own


def test_tray_worker_launch_never_resumes_and_gives_the_exe_its_one_visible_console():
    fn = _fn(_tray(), "Start-BobTrayWorkerExe")
    assert not RESUME_RX.search(fn.replace("--mode", "").replace("--install-root", "").replace("--machine-id", ""))
    assert "worker\\bob-worker.exe" in fn and "'--mode', $Mode" in fn and "--install-root" in fn
    assert "Bobiverse\\worker\\bin" in fn                    # per-user run-copy: the installed exe is never locked by a seat
    assert "NEW agent every click" in fn
    assert "$psi.CreateNoWindow = $false" in fn              # t771u: the exe's console IS the one window (agent inherits it)
    assert "UseShellExecute = $false" in fn
    assert "Resume" not in fn and "Attach" not in fn.replace("AttachConsole", "")
    assert fn.count("Process]::Start") == 1                  # one process per click: no watcher/helper window


@WIN
def test_tray_second_click_starts_a_second_new_process_from_the_same_run_copy(tmp_path):
    import os

    ps = tmp_path / "t.ps1"
    fake = tmp_path / "inst"
    (fake / "worker").mkdir(parents=True)
    (fake / "plan").mkdir()
    shutil.copy(Path(r"C:\Windows\System32\whoami.exe"), fake / "worker" / "bob-worker.exe")
    ps.write_text(
        "$ErrorActionPreference='Stop'\n"
        "Add-Type -AssemblyName System.Windows.Forms\n"
        f"$RepoRoot='{fake}'\n"
        "function Write-TrayLog($m){ Write-Output ('LOG ' + $m) }\n"
        "function Get-BobTrayMachineId { 'testbox' }\n"
        f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{TRAY}',[ref]$null,[ref]$null)\n"
        "$fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Start-BobTrayWorkerExe'},$true).Extent.Text\n"
        "Invoke-Expression $fn\n"
        "Start-BobTrayWorkerExe -Mode agent\nStart-BobTrayWorkerExe -Mode agent\nStart-BobTrayWorkerExe -Mode plan\n",
        encoding="utf-8")
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path / "lad"))
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps)], capture_output=True, text=True,
                       timeout=120, env=env, creationflags=0x08000000)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    pids = re.findall(r"started bob-worker\.exe pid=(\d+) mode=(agent|plan)", r.stdout)
    assert [m for _, m in pids] == ["agent", "agent", "plan"], r.stdout
    assert len({p for p, _ in pids}) == 3, "every click must start a NEW process"
    copies = list((tmp_path / "lad" / "Bobiverse" / "worker" / "bin").glob("bob-worker-*.exe"))
    assert len(copies) == 1, copies


def test_tray_missing_exe_is_logged_not_started():
    fn = _fn(_tray(), "Start-BobTrayWorkerExe")
    assert "worker exe missing" in fn and fn.index("worker exe missing") < fn.index("Process]::Start")


# ------------------------------------------------------------------------------------------------ exe command-line surface
def test_exe_accepts_what_the_tray_passes():
    sys.path.insert(0, str(ROOT / "scripts"))
    import argparse  # noqa: F401
    import bob_worker as bw

    src = (ROOT / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    for flag in ("--mode", "--install-root", "--machine-id", "--dry-run"):
        assert flag in src
    assert bw.main(["--mode", "plan", "--install-root", r"C:\nonexistent-bob", "--dry-run"]) == bw.EXIT_OK


# ------------------------------------------------------------------------------------------------ the MSI payload (stage)
@pytest.fixture(scope="module")
def bob_stage(tmp_path_factory):
    if sys.platform != "win32" or not shutil.which("powershell"):
        pytest.skip("needs Windows PowerShell")
    out = tmp_path_factory.mktemp("dist")
    run = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                          str(ROOT / "scripts" / "Pack-BobiverseRelease.ps1"), "-Product", "bob", "-SkipMsi", "-KeepStage",
                          "-SkipWorkerExe", "-OutDir", str(out)], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stdout[-1500:] + run.stderr[-1500:]
    ver = (ROOT / "src" / "VERSION").read_text().strip()
    return out / f"bob-{ver}"


def test_stage_has_worker_plan_folders_and_the_exe_inputs(bob_stage):
    s = bob_stage
    wk = ["AGENTS.md", "CLAUDE.md", "GROK.md", ".cursor/rules/bobiverse-worker.mdc", ".grok/skills/bobiverse-bob/SKILL.md",
          ".grok/skills/bobiverse-bob-worker/SKILL.md", ".grok/skills/bobiverse-bob-plan/SKILL.md",
          ".grok/skills/bobiverse-worker-seat/SKILL.md", ".grok/skills/bobiverse-fleet-ops/SKILL.md", ".grok/skills/harvest/SKILL.md"]
    wk += [f".grok/skills/{j}/SKILL.md" for j in JOB_SKILLS]
    for f in wk:
        assert (s / "worker" / f).is_file(), f"worker/{f}"
    for f in ("AGENTS.md", "CLAUDE.md", "GROK.md", ".cursor/rules/bobiverse-plan.mdc", ".grok/skills/visionary/SKILL.md",
              ".grok/skills/plan-create-repo/SKILL.md", ".grok/skills/harvest/SKILL.md", "docs/templates/vision.md",
              "tools/validate-vision-pack.py"):
        assert (s / "plan" / f).is_file(), f"plan/{f}"
    assert (s / "tools" / "Get-BobAgentFuel.ps1").is_file()
    assert (s / "scripts" / "bob_worker.py").is_file() and (s / "scripts" / "Build-BobWorker.ps1").is_file()
    assert (s / "assets" / "bob-systray.ico").is_file()
    for j in JOB_SKILLS:                                       # the bob book (install root) carries them too
        assert (s / ".grok" / "skills" / j / "SKILL.md").is_file(), j
    tray = (s / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8-sig")
    assert "Start-BobTrayWorkerExe" in tray and "Build-BobTrayAgentsMenu" not in tray


def test_stage_skills_carry_the_harvest_rule_with_install_absolute_paths(bob_stage):
    files = sorted((bob_stage / "worker").rglob("SKILL.md")) + sorted((bob_stage / "plan").rglob("SKILL.md")) + [
        bob_stage / "worker" / "AGENTS.md", bob_stage / "plan" / "AGENTS.md", bob_stage / "worker" / "CLAUDE.md",
        bob_stage / "plan" / "GROK.md", bob_stage / "worker" / ".cursor" / "rules" / "bobiverse-worker.mdc",
        bob_stage / "plan" / ".cursor" / "rules" / "bobiverse-plan.mdc"]
    assert len(files) >= 11 + 8 + 6
    for f in files:
        t = f.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        for mk in RULE:
            assert mk in t, f"{f.relative_to(bob_stage)}: missing {mk!r}"
        assert "..\\scripts\\Report-BobiverseIntakeIssue.ps1" in t, f.relative_to(bob_stage)
        assert ".\\scripts\\Report-BobiverseIntakeIssue.ps1" not in t.replace("..\\scripts\\", ""), f.relative_to(bob_stage)
        if f.name == "SKILL.md":
            assert t.index("CAST IRON RULE - HARVEST AND FILE EVERYTHING") < (t.find("\n## ") if "\n## " in t else 10**9), f


def test_worker_and_plan_folders_say_always_a_new_agent(bob_stage):
    for folder in ("worker", "plan"):
        agents = (bob_stage / folder / "AGENTS.md").read_text(encoding="utf-8-sig")
        assert re.search(r"(?i)NEW (plan |worker )?agent", agents), folder
        assert re.search(r"(?i)never.{0,60}(resume|continue|attach)", agents), folder


@WIN
def test_sync_agent_folders_never_deletes_plan_work_or_the_running_exe(tmp_path):
    dest = tmp_path / "inst"
    (dest / "plan" / "work" / "plan-20260101-000000").mkdir(parents=True)
    keep = dest / "plan" / "work" / "plan-20260101-000000" / "vision.md"
    keep.write_text("my plan", encoding="utf-8")
    (dest / "worker").mkdir()
    exe = dest / "worker" / "bob-worker.exe"
    exe.write_bytes(b"MZ-pretend-running")
    ps = tmp_path / "s.ps1"
    ps.write_text(". '%s'\n$n = Sync-BobiverseAgentFolders -RepoRoot '%s' -Destination '%s'\nWrite-Output \"MADE=$n\"\n"
                  % (ROOT / "scripts" / "Bobiverse-Common.ps1", ROOT, dest), encoding="utf-8")
    for _ in range(2):   # idempotent
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps)], capture_output=True, text=True,
                           timeout=120, creationflags=0x08000000)
        assert r.returncode == 0 and "MADE=2" in r.stdout, r.stdout[-600:] + r.stderr[-600:]
    assert keep.read_text(encoding="utf-8") == "my plan"
    assert exe.read_bytes() == b"MZ-pretend-running"
    assert (dest / "worker" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").is_file()
    assert (dest / "worker" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md").is_file()
    assert (dest / "plan" / "AGENTS.md").is_file()


def test_install_sync_and_pack_use_the_shared_folder_builder():
    sc = ROOT / "scripts"
    assert "Sync-BobiverseAgentFolders" in (sc / "Install-Bob.ps1").read_text(encoding="utf-8-sig")
    assert "Sync-BobiverseAgentFolders" in (sc / "Sync-BobiverseFromRepo.ps1").read_text(encoding="utf-8-sig")
    pack = (sc / "Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
    assert "Sync-BobiverseAgentFolders" in pack and "Build-BobWorker.ps1" in pack and "worker\\bob-worker.exe" in pack
    assert re.search(r"SkipWorkerExe.{0,200}SkipMsi|SkipMsi.{0,200}SkipWorkerExe", pack, re.S)


# ------------------------------------------------------------------------------------------------ the bob book (start guides)
BOOK_TOPICS = {
    "bobiverse-bob-worker": ["tray", "Agent", "bob-worker.exe", "--mode agent", "agent.cmd", "agent.exe", "prompt", r"<ai root>\bob\worker",
                             "#<machine>", "<machine>-<pid>", "IRC is lost", "kill", "no reconnect", "hung", "backoff", "logs",
                             "Troubleshooting", "NEW agent", "--resume", "PING", "pong", "Exit codes", "run copy", "Plan",
                             "ONE window", "!bored", "bobiverse-bob-job-irc"],
    "bobiverse-bob-plan": ["tray", "Plan", "--mode plan", r"<ai root>\bob\plan", "visionary", "NEW agent", "--resume", "agent.cmd", "agent.exe",
                           "logs", "Troubleshooting", "work", "ONE window"],
}


@pytest.mark.parametrize("book", sorted(BOOK_TOPICS))
def test_bob_book_start_guides_cover_every_required_topic(book):
    t = (SK / book / "SKILL.md").read_text(encoding="utf-8-sig")
    missing = [x for x in BOOK_TOPICS[book] if x.lower() not in t.lower()]
    assert not missing, missing
    for mk in RULE:
        assert mk in t, mk
    assert re.search(r"(?i)never.{0,80}(resume|continue|attach)", t)
    assert not re.search(r"(?i)(xai-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|password\s*[:=]\s*[A-Za-z0-9]{6,})", t)
    for h in re.findall(r"https?://([A-Za-z0-9.-]+)", t):
        assert h.lower() in {"irc.ntsa.uk", "github.com", "api.github.com", "cursor.com", "raw.githubusercontent.com"}, h


def test_bob_agents_md_points_at_the_new_guides():
    t = (ROOT / "AGENTS.bob.md").read_text(encoding="utf-8-sig")
    for x in ("bobiverse-bob-worker", "bobiverse-bob-plan", "bobiverse-bob-job-irc", "NEW", "cursor", "grok"):
        assert x.lower() in t.lower(), x
    assert re.search(r"(?i)never.{0,40}resume", t)


# ------------------------------------------------------------------------------------------------ job skills (t772u): ACK/DONE + one skill each for FR / MRB / UAT
@pytest.mark.parametrize("name", JOB_SKILLS)
def test_job_skill_exists_with_a_mermaid_block_and_mentions_ack_and_done(name):
    f = SK / name / "SKILL.md"
    assert f.is_file(), name
    t = f.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    assert re.match(r"---\nname: %s\ndescription: >\n  .+\n---\n" % re.escape(name), t, re.S), "frontmatter"
    assert re.search(r"```mermaid\n(flowchart|sequenceDiagram)", t), "no mermaid diagram"
    assert t.count("```mermaid") == 1 and t.count("```") % 2 == 0
    assert "ACK" in t and "DONE" in t
    for mk in RULE:
        assert mk in t, mk
    assert t.index("CAST IRON RULE - HARVEST AND FILE EVERYTHING") < t.find("\n## ")
    assert "NACK" in t or "GIVEUP" in t
    assert not re.search(r"(?i)(xai-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|password\s*[:=]\s*[A-Za-z0-9]{6,})", t)


@pytest.mark.parametrize("name", JOB_SKILLS[1:])
def test_each_job_skill_has_steps_evidence_owners_and_the_diagram_flows_ack_to_done(name):
    t = (SK / name / "SKILL.md").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    for h in ("## Process", "## Steps", "## Evidence required", "## Who owns what", "## Rules"):
        assert h in t, h
    mer = t.split("```mermaid\n", 1)[1].split("```", 1)[0]
    assert "ACK" in mer and "DONE" in mer and mer.index("ACK") < mer.index("DONE")
    assert re.search(r"(?i)assign", mer)
    assert re.search(r"(?i)evidence|verdict|review|tests", mer)
    assert re.search(r"(?i)originating agent", t)


def test_job_skills_match_the_jeeves_wire_contract():
    irc = (SK / "bobiverse-bob-job-irc" / "SKILL.md").read_text(encoding="utf-8-sig")
    for x in ("ACK <TYPE> <owner/repo>#<N>", "DONE <TYPE> <owner/repo>#<N> [PASS|FAIL] <url>", "NACK <TYPE>", "GIVEUP <TYPE>", "!focus",
              "#<machine>", "nothing queued", "FR #224", "docs/jeeves-commands.md", "never a PM"):
        assert x.lower() in irc.lower(), x
    assert re.search(r"(?i)nothing after the url", irc)
    assert re.search(r"(?i)never post .{0,10}!bored.{0,12}yourself|never.{0,30}`?!bored", irc)
    # the Jeeves grammar really is what the skill says
    jc = (ROOT / "docs" / "jeeves-commands.md").read_text(encoding="utf-8-sig")
    assert "`!bored`, `ACK`, `DONE`, `NACK`/`GIVEUP`" in jc
    mrb = (SK / "bobiverse-bob-job-mrb" / "SKILL.md").read_text(encoding="utf-8-sig")
    assert re.search(r"(?i)different seat", mrb) and "docs/mrb-" in mrb and re.search(r"(?i)exactly ONE", mrb)
    fr = (SK / "bobiverse-bob-job-fr" / "SKILL.md").read_text(encoding="utf-8-sig")
    assert re.search(r"(?i)never merge|no merge", fr)
    uat = (SK / "bobiverse-bob-job-uat" / "SKILL.md").read_text(encoding="utf-8-sig")
    assert re.search(r"(?i)evidence before stamp", uat)


def test_worker_agents_file_lists_the_job_skills():
    t = (ROOT / "bob-agents" / "worker" / "AGENTS.md").read_text(encoding="utf-8-sig")
    for j in JOB_SKILLS[:1] + ("bobiverse-bob-job-fr", "bobiverse-bob-job-mrb", "bobiverse-bob-job-uat"):
        assert j in t, j
    assert "!bored" in t