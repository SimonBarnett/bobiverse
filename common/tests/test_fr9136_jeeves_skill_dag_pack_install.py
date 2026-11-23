"""FR #9136: Jeeves pack/install ships skill-dag MCP under install scripts\\.

Live J:\\scripts lacked skill_dag_mcp.py (MSI 1.0.7 predated the MCP; tip
overlay needs .git). Pack must assert the trio; Install/Sync must land them
and write InstallRoot\\.cursor\\mcp.json pointing at install scripts + skills.
Never hardcode C:\\ai\\bob into the MSI stage or mcp.json.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
INSTALL = ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1"
ADMIN = ROOT / "jeeves" / "docs" / "jeeves-admin.md"
POST = ROOT / "common" / "docs" / "post-install.md"
SKILL_DAG = (
    "skill_dag_mcp.py",
    "skill_dag_index.py",
    "skill_dag_bound.py",
)

PS = shutil.which("powershell.exe") or shutil.which("powershell")

pytestmark_win = pytest.mark.skipif(
    sys.platform != "win32" or not PS,
    reason="windows powershell",
)


def test_fr9136_sources_exist_under_bob_scripts():
    for name in SKILL_DAG:
        p = ROOT / "bob" / "scripts" / name
        assert p.is_file(), f"missing canonical {p}"


def test_fr9136_pack_asserts_skill_dag_trio():
    p = PACK.read_text(encoding="utf-8")
    assert "function Assert-BobiverseStageHasSkillDagMcp" in p
    assert "Assert-BobiverseStageHasSkillDagMcp -Stage $stage" in p
    assert p.index("function Assert-BobiverseStageHasSkillDagMcp") < p.index(
        "Assert-BobiverseStageHasSkillDagMcp -Stage $stage"
    )
    for name in SKILL_DAG:
        assert name in p
    assert "bobiverse pack missing scripts\\{0}" in p or "bobiverse pack missing scripts\\{0}" in p.replace(
        "/", "\\"
    )
    assert "bob\\scripts union; FR #9136" in p.replace("/", "\\")
    block = p.split("Assert-BobiverseStageHasSkillDagMcp", 1)[1][:800]
    assert "C:\\ai\\bob\\scripts" not in block


def test_fr9136_common_ensure_and_mcp_helpers():
    c = COMMON.read_text(encoding="utf-8")
    assert "function Get-BobiverseSkillDagScriptNames" in c
    assert "function Ensure-BobiverseSkillDagScripts" in c
    assert "function Write-BobiverseInstallSkillDagMcp" in c
    assert "FR #9136" in c
    for name in SKILL_DAG:
        assert name in c
    # Tip allowlist covers the full trio (mcp alone is not enough for imports).
    allow = c[c.index("function Get-BobiverseTipFileAllowlist") : c.index("function Sync-BobiverseTipFile")]
    assert "bob/scripts/skill_dag_mcp.py" in allow
    assert "bob/scripts/skill_dag_index.py" in allow
    assert "bob/scripts/skill_dag_bound.py" in allow


def test_fr9136_install_jeeves_calls_ensure_and_mcp():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "Ensure-BobiverseSkillDagScripts" in t
    assert "Write-BobiverseInstallSkillDagMcp" in t
    assert "FR #9136" in t
    # After scripts lay / SkipCopy; before final done.
    ensure_at = t.index("Ensure-BobiverseSkillDagScripts")
    mcp_at = t.index("Write-BobiverseInstallSkillDagMcp")
    done_at = t.index("INFO Install-Jeeves done")
    assert ensure_at < mcp_at < done_at


def test_fr9136_sync_force_skill_dag_and_mcp():
    s = SYNC.read_text(encoding="utf-8")
    assert "FR #9136" in s
    assert "Ensure-BobiverseSkillDagScripts" in s
    assert "Write-BobiverseInstallSkillDagMcp" in s
    assert "skill_dag_mcp.py" in s


def test_fr9136_docs_mention_install_skill_dag():
    admin = ADMIN.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    blob = admin + "\n" + post
    assert "skill_dag_mcp.py" in blob
    assert ".cursor" in blob and "mcp.json" in blob
    assert "Do not borrow" in blob or "never" in blob.lower()
    assert "<InstallRoot>\\scripts\\skill_dag_mcp.py" in blob.replace("/", "\\") or (
        "<InstallRoot>\\scripts\\skill_dag_mcp.py" in blob
    )


@pytestmark_win
def test_fr9136_ensure_copies_trio_and_writes_mcp(tmp_path: Path):
    src = tmp_path / "src"
    for name in SKILL_DAG:
        (src / "bob" / "scripts").mkdir(parents=True, exist_ok=True)
        (src / "bob" / "scripts" / name).write_text(
            f"# {name} FR #9136\n" + ("x\n" * 20), encoding="utf-8"
        )
    (src / ".grok" / "skills" / "harvest").mkdir(parents=True, exist_ok=True)
    (src / ".grok" / "skills" / "harvest" / "SKILL.md").write_text(
        "---\nname: harvest\ndescription: pin\n---\n\n# harvest\n",
        encoding="utf-8",
    )
    install = tmp_path / "install"
    (install / "scripts").mkdir(parents=True)
    (install / ".grok" / "skills").mkdir(parents=True)
    # Skills root for mcp.json --root
    shutil.copytree(src / ".grok" / "skills", install / ".grok" / "skills", dirs_exist_ok=True)

    script = tmp_path / "run.ps1"
    script.write_text(
        "\n".join(
            [
                f". '{COMMON}'",
                f"$r = Ensure-BobiverseSkillDagScripts -InstallRoot '{install}' -SourceRoot '{src}'",
                "if (-not $r.Ok) { Write-Output $r.Reason; exit 1 }",
                f"$m = Write-BobiverseInstallSkillDagMcp -InstallRoot '{install}' -Python '{sys.executable}'",
                "if (-not $m.Ok) { Write-Output $m.Reason; exit 2 }",
                "Write-Output $m.Path",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    p = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out
    for name in SKILL_DAG:
        dest = install / "scripts" / name
        assert dest.is_file(), name
        assert "FR #9136" in dest.read_text(encoding="utf-8")
    mcp = install / ".cursor" / "mcp.json"
    assert mcp.is_file()
    doc = json.loads(mcp.read_text(encoding="utf-8"))
    server = doc["mcpServers"]["skill-dag"]
    assert server["command"]
    args = server["args"]
    assert any(str(install / "scripts" / "skill_dag_mcp.py") in a.replace("/", "\\") or a.endswith("skill_dag_mcp.py") for a in args)
    assert "--root" in args
    root_arg = args[args.index("--root") + 1]
    assert str(install / ".grok" / "skills") in root_arg.replace("/", "\\") or root_arg.endswith(".grok\\skills") or root_arg.endswith(".grok/skills")
    assert "C:\\ai\\bob" not in json.dumps(doc)
