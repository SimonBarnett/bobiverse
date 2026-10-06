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
DUPLICATE_RULE = ("One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, "
                  "close the later one and comment a reference to the first; never leave both open; "
                  "done issues are closed too.")
HARVEST_RECEIPT_RULE = ("Harvest receipt rule: any receipt whose title or body says DONE, twin, duplicate, filed, or merged "
                       "is closed by the worker/MRB as soon as it is filed; a receipt is never left open.")
HARVEST_RECEIPT_RULE_FILES = (
    "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md",
    "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md",
    "bob/.grok/skills/bobiverse-bob-worker/SKILL.md",
    "common/.grok/skills/harvest-agent-skills/SKILL.md",
)

DUPLICATE_RULE_FILES = (
    "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md",
    "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md",
    "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md",
    "bob/.grok/skills/bobiverse-bob-worker/SKILL.md",
    "bob/.grok/skills/bobiverse-bob-plan/SKILL.md",
    "bob/agents/worker/.grok/skills/bobiverse-worker-seat/SKILL.md",
    "bob/agents/worker/AGENTS.md",
    "bob/agents/plan/AGENTS.md",
    "common/.grok/skills/harvest/SKILL.md",
    "common/.grok/skills/harvest-agent-skills/SKILL.md",
    "jeeves/.grok/skills/bobiverse-jeeves/SKILL.md",
    "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md",
    "jeeves/docs/jeeves-commands.md",
)


def test_duplicate_issue_rule_is_present_in_every_active_instruction_copy():
    for rel in DUPLICATE_RULE_FILES:
        path = ROOT / rel
        assert path.is_file(), rel
        assert DUPLICATE_RULE in path.read_text(encoding="utf-8-sig"), rel


def test_harvest_receipt_rule_is_in_worker_mrb_and_harvest_books():
    for rel in HARVEST_RECEIPT_RULE_FILES:
        assert HARVEST_RECEIPT_RULE in (ROOT / rel).read_text(encoding="utf-8-sig"), rel


def test_startup_prompts_carry_duplicate_closure_rule():
    sys.path.insert(0, str(ROOT / "scripts"))
    import bob_worker

    assert DUPLICATE_RULE in bob_worker.worker_prompt("C:\\worker", "C:\\home", "testbox", "Bob-testbox")
    assert DUPLICATE_RULE in bob_worker.rules_text("C:\\worker", "worker")

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
    # t787u: ProcessStartInfo + CreateNoWindow=false inherits the tray's HIDDEN console -> invisible agent. Own new console instead.
    # t787u pin: after the own-console note the launch uses VisibleProcess helper and never CreateNoWindow
    # ($wd is assigned earlier in the function; do not require a second $wd= after the marker).
    after_t787u = fn.split("t787u", 1)[1]
    assert "Start-BobTrayVisibleProcessWithSessionEnv" in fn and "CreateNoWindow" not in after_t787u
    assert "New-Object System.Diagnostics.ProcessStartInfo" not in fn and "Process]::Start" not in fn
    assert fn.count("Start-BobTrayVisibleProcessWithSessionEnv") == 1   # one process per click: no watcher/helper window
    assert "Resume" not in fn and "Attach" not in fn.replace("AttachConsole", "")


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
        "function Get-BobTrayWorkerCapRefusal { '' }  # t815u: the harness must not depend on the live process table\n"
        f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{TRAY}',[ref]$null,[ref]$null)\n"
        "foreach($name in 'ConvertTo-BobTrayProcessArgumentString','Initialize-BobTrayConsoleLauncher','Register-BobTrayGrokSession','Start-BobTrayVisibleProcessWithSessionEnv','Start-BobTrayWorkerExe'){\n"
        "  $fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true).Extent.Text\n"
        "  Invoke-Expression $fn }\n"
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


@WIN
def test_tray_click_from_a_hidden_tray_opens_one_visible_console_window(tmp_path):
    """t787u regression: the tray is a HIDDEN powershell; the worker exe must get its OWN visible console (it ran invisibly
    inside the tray's hidden console before). cmd.exe stands in for the exe: it ignores the tray's flags and stays alive."""
    import os
    import time

    if not os.environ.get("SESSIONNAME") and not os.environ.get("USERNAME"):
        pytest.skip("needs an interactive session")
    fake = tmp_path / "inst"
    (fake / "worker").mkdir(parents=True)
    (fake / "plan").mkdir()
    shutil.copy(Path(r"C:\Windows\System32\cmd.exe"), fake / "worker" / "bob-worker.exe")
    out = tmp_path / "out.txt"
    ps = tmp_path / "t.ps1"
    ps.write_text(
        "$ErrorActionPreference='Stop'\n"
        "Add-Type -AssemblyName System.Windows.Forms\n"
        f"$RepoRoot='{fake}'\n"
        f"function Write-TrayLog($m){{ Add-Content '{out}' ('LOG ' + $m) }}\n"
        "function Get-BobTrayMachineId { 'testbox' }\n"
        "function Get-BobTrayWorkerCapRefusal { '' }  # t815u: the harness must not depend on the live process table\n"
        f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{TRAY}',[ref]$null,[ref]$null)\n"
        "foreach($name in 'ConvertTo-BobTrayProcessArgumentString','Initialize-BobTrayConsoleLauncher','Register-BobTrayGrokSession','Start-BobTrayVisibleProcessWithSessionEnv','Start-BobTrayWorkerExe'){\n"
        "  $fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true).Extent.Text\n"
        "  Invoke-Expression $fn }\n"
        "Add-Type -TypeDefinition @'\nusing System; using System.Text; using System.Runtime.InteropServices;\npublic class WinProbe {\n"
        " public delegate bool EP(IntPtr h, IntPtr l);\n"
        " [DllImport(\"user32.dll\")] static extern bool EnumWindows(EP cb, IntPtr l);\n"
        " [DllImport(\"user32.dll\")] static extern bool IsWindowVisible(IntPtr h);\n"
        " [DllImport(\"user32.dll\")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);\n"
        " [DllImport(\"user32.dll\")] static extern int GetClassName(IntPtr h, StringBuilder s, int n);\n"
        " public static int Visible(int pid){ int n=0; EnumWindows((h,x)=>{ uint p; GetWindowThreadProcessId(h,out p); var c=new StringBuilder(64); GetClassName(h,c,64);"
        " if(p==pid && c.ToString()==\"ConsoleWindowClass\" && IsWindowVisible(h)) n++; return true;}, IntPtr.Zero); return n; }\n}\n'@\n"
        "Start-BobTrayWorkerExe -Mode agent\n"
        "$log = Get-Content '" + str(out) + "'\n"
        "$pidv = [int](($log | Select-String 'pid=(\\d+)').Matches[0].Groups[1].Value)\n"
        "$vis = 0; for($i=0;$i -lt 40 -and $vis -eq 0;$i++){ Start-Sleep -Milliseconds 250; $vis = [WinProbe]::Visible($pidv) }\n"
        "Add-Content '" + str(out) + "' ('RESULT pid=' + $pidv + ' visible_console_windows=' + $vis)\n"
        "Stop-Process -Id $pidv -Force -ErrorAction SilentlyContinue\n",
        encoding="utf-8")
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path / "lad"))
    # a HIDDEN parent, exactly like the tray (-WindowStyle Hidden)
    r = subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", str(ps)],
                       capture_output=True, text=True, timeout=120, env=env)
    txt = out.read_text(encoding="utf-8") if out.exists() else ""
    assert r.returncode == 0, txt + r.stdout[-500:] + r.stderr[-800:]
    m = re.search(r"visible_console_windows=(\d+)", txt)
    assert m and int(m.group(1)) == 1, txt


def test_tray_missing_exe_is_logged_not_started():
    fn = _fn(_tray(), "Start-BobTrayWorkerExe")
    assert "worker exe missing" in fn and fn.index("worker exe missing") < fn.index("Start-BobTrayVisibleProcessWithSessionEnv")


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
    # FR #2835: Sync-BobiverseAgentFolders drops nested skill-dba\.grok; keep the pin if a copy sneaks back.
    files = [f for f in files if "skill-dba" not in f.as_posix().split("/")]
    assert len(files) >= 11 + 8 + 6
    for f in files:
        t = f.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        for mk in RULE:
            assert mk in t, f"{f.relative_to(bob_stage)}: missing {mk!r}"
        assert "..\\scripts\\Report-BobiverseIntakeIssue.ps1" in t, f.relative_to(bob_stage)
        assert ".\\scripts\\Report-BobiverseIntakeIssue.ps1" not in t.replace("..\\scripts\\", ""), f.relative_to(bob_stage)
        # FR #1704: rewritten instruction paths must not gain a third leading dot. Fleet-ops prose may
        # still name the triple-dot failure mode next to FR #1704 / "triple".
        assert "...\\scripts\\Report-BobiverseIntakeIssue" not in t, f.relative_to(bob_stage)
        assert "...\\scripts\\Invoke-BobiverseHarvest" not in t, f.relative_to(bob_stage)
        for m in re.finditer(r"\.\.\.\\scripts\\", t):
            window = t[max(0, m.start() - 240): m.end() + 120]
            assert "FR #1704" in window or "triple" in window.lower(), (
                f"{f.relative_to(bob_stage)}: staged path rewrite doubled the dot (FR #1704)"
            )
        if f.name == "SKILL.md":
            assert t.index("CAST IRON RULE - HARVEST AND FILE EVERYTHING") < (t.find("\n## ") if "\n## " in t else 10**9), f
    # Nested foreign skill-book snapshot must not land in the staged worker tree.
    nested = [p for p in (bob_stage / "worker").rglob("SKILL.md") if "skill-dba/.grok/skills" in p.as_posix()]
    assert nested == [], nested


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
    # FR #2419: FR DONE is url-only; MRB/UAT keep PASS|FAIL (no single combined DONE template).
    for x in ("ACK <TYPE> <owner/repo>#<N>", "DONE FR", "DONE MRB", "PASS|FAIL", "NACK <TYPE>", "GIVEUP <TYPE>", "!focus",
              "#<machine>", "nothing queued", "FR #224", "docs/jeeves-commands.md", "never a PM"):
        assert x.lower() in irc.lower(), x
    assert "2419" in irc
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
def test_tray_does_not_spawn_a_missing_watch_bobjobs():
    """t784u: Watch-BobJobs.ps1 is not shipped; the tray used to start a hidden powershell for it every 30 s."""
    from repo_layout import REPO
    tray = (REPO / "bob/tray/tools/Watch-BobTray.ps1").read_text(encoding="utf-8-sig")
    start = tray.split("function Start-JobsWatcher")[1].split("function Set-Attention")[0]
    guard = start.index("Test-Path -LiteralPath $watchJobs")
    assert guard < start.index("Start-Process"), "the existence check must come before Start-Process"
    assert "return" in start[guard:start.index("Start-Process")]

# ------------------------------------------------------------------------------------------------ t820u: the UAT flow = verify vs VISION/specs -> FR per gap (no release) | docs + release
def test_uat_skill_is_the_vision_gap_flow_with_fr_per_gap_or_docs_and_release():
    t = (SK / "bobiverse-bob-job-uat" / "SKILL.md").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    mer = t.split("```mermaid\n", 1)[1].split("```", 1)[0]
    assert t.count("```mermaid") == 1
    # diagram: assign -> ACK -> read VISION/specs -> verify -> gaps? -> (FR per gap, no release, FAIL) | (docs/READMEs, release, PASS) -> DONE
    for needle in ("VISION", "specs", "Any gaps?", "FR per gap", "NO release", "documentation and READMEs", "Create the release", "gh release create"):
        assert needle in mer, needle
    assert mer.index("ACK UAT") < mer.index("VISION") < mer.index("Any gaps?") < mer.index("FR per gap") < mer.index("DONE UAT")
    assert mer.index("Any gaps?") < mer.index("documentation and READMEs") < mer.index("Create the release") < mer.rindex("DONE UAT")
    assert "-->|\"gaps\"|" in mer.replace(" ", "") .replace('-->|"gaps"|', '-->|"gaps"|') or '|"gaps"|' in mer
    assert '|"no gaps"|' in mer
    # the FAIL branch never reaches the release node: nothing between 'gaps' and its DONE mentions the release
    fail = mer[mer.index('|"gaps"|'):mer.index('|"no gaps"|')]
    assert "release" not in fail.lower().replace("no release", "")
    # text: steps, evidence, owners, rules
    assert re.search(r"(?i)one FR per gap", t) and re.search(r"(?i)gaps => no release", t)
    assert "Report-BobiverseIntakeIssue.ps1 -Repo owner/name -Kind fr" in t
    assert re.search(r"(?i)update the docs and READMEs", t) and "Pack-BobiverseRelease.ps1 -Product all" in t and "gh release create" in t
    assert re.search(r"(?i)never by Jeeves", t) and re.search(r"(?i)Jeeves / the chair .*never verifies", t)
    assert "DONE UAT owner/repo#0 FAIL" in t and "DONE UAT owner/repo#0 PASS" in t              # t853u: UAT is per REPO (#0)
    assert re.search(r"(?i)UAT is per REPO", t) and re.search(r"(?i)never per PR", t)
    assert "every issue" in mer or "all issues closed" in mer and "all PRs merged" in mer
    assert re.search(r"(?i)NACK UAT", t) and "GIVEUP" in t
    assert re.search(r"(?i)evidence before stamp", t)


def test_uat_skill_wires_design_uat_companion_with_g1_g2_g3():
    """FR #780 / MRB #783: design-UAT must be absorbed into the UAT skill tree and linked from SKILL.md."""
    skill = (SK / "bobiverse-bob-job-uat" / "SKILL.md").read_text(encoding="utf-8-sig")
    companion = SK / "bobiverse-bob-job-uat" / "design-uat.md"
    assert companion.is_file(), "design-uat.md companion must ship beside bobiverse-bob-job-uat/SKILL.md"
    assert "design-uat.md" in skill
    assert re.search(r"(?i)Visual UAT", skill)
    for gate in ("G1", "G2", "G3"):
        assert gate in skill, gate
    body = companion.read_text(encoding="utf-8-sig")
    assert "G1" in body and "G2" in body and "G3" in body
    assert re.search(r"(?i)ready for human UAT", body)
    assert "bob-design-uat" in body
    assert "delta_px" in body and "NOT_IN_BRIEF" in body


def test_uat_release_exception_is_stated_in_the_worker_rules_and_the_wire_skill_and_docs():
    a = (ROOT / "bob-agents" / "worker" / "AGENTS.md").read_text(encoding="utf-8-sig")
    assert re.search(r"(?i)EXCEPT in an assigned UAT job that finds NO gaps", a) and "any gap = an FR each via intake and NO release" in a
    irc = (SK / "bobiverse-bob-job-irc" / "SKILL.md").read_text(encoding="utf-8-sig")
    assert "ACK <TYPE> <owner/repo>#<N>" in irc and re.search(r"(?i)a FAIL means an FR per gap and NO release", irc)
    doc = (ROOT / "docs" / "bob-worker.md").read_text(encoding="utf-8-sig")
    assert "## UAT job flow" in doc and "no release" in doc.lower() and "`gh release create`" in doc
# ---- t826u: a successful MRB / an FR PR closes the issue that created it -------------------------------------------------------
def _skill(name: str) -> str:
    return (SK / f"bobiverse-bob-job-{name}" / "SKILL.md").read_text(encoding="utf-8-sig")


def test_fr_skill_requires_closes_owner_repo_n_and_verifies_it_before_done():
    t = _skill("fr")
    assert "Closes <owner>/<repo>#N" in t
    assert "closingIssuesReferences" in t
    assert t.index("Verify the link before DONE") < t.index("Send **DONE**")
    assert "Fixes #N" not in t
    low = t.lower()
    assert "one pr" in low and ("never merge" in low or "no merge" in low or "do not merge" in low)


def test_mrb_skill_merges_if_authorised_else_confirms_closes_and_closes_issue_itself():
    t = _skill("mrb")
    low = t.lower()
    assert "authoris" in low and "merge" in low
    assert "Closes <owner>/<repo>#N" in t
    assert "gh issue close" in t and "--comment" in t
    assert "non-default branch" in low
    assert "gh issue view" in t and "--json state" in t
    assert "verified" in low  # DONE only after the issue is verified closed / linked


def test_uat_and_irc_skills_carry_the_closed_issue_check():
    assert "closed" in _skill("uat").lower() and "originating issue" in _skill("uat").lower()
    irc = _skill("irc")
    assert "verify before DONE" in irc and "closingIssuesReferences" in irc


def test_worker_agents_and_docs_state_the_issue_closing_rule():
    for p in (ROOT / "bob-agents" / "worker" / "AGENTS.md", ROOT / "docs" / "bob-worker.md"):
        t = p.read_text(encoding="utf-8-sig")
        assert "Closes <owner>/<repo>#N" in t, p
    assert "t826u" in (ROOT / "docs" / "bob-worker.md").read_text(encoding="utf-8-sig")

def test_skill_intake_consolidates_every_issue_for_the_book():
    rule = ("Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), "
            "it must close all open issues for that skill book (every harvest/skill issue targeting the same book), "
            "open one consolidated PR for them, and cite every issue it closes (Closes #N for each); "
            "no per-issue PRs for the same skill book; the worker closes the issues itself as part of DONE.")
    files = (
        "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-worker/SKILL.md",
        "common/.grok/skills/harvest-agent-skills/SKILL.md",
        "common/.grok/skills/harvest/SKILL.md",
        "jeeves/docs/jeeves-commands.md",
    )
    for rel in files:
        assert rule in (ROOT / rel).read_text(encoding="utf-8-sig"), rel
    sys.path.insert(0, str(ROOT / "scripts"))
    import bob_worker
    assert rule in bob_worker.worker_prompt("C:\\worker", "C:\\home", "testbox", "Bob-testbox")
    assert rule in bob_worker.rules_text("C:\\worker", "worker")
