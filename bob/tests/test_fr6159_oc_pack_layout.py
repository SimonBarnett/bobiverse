"""FR #6159 FR-OC-PACK: Sync/MSI flat layout ships OpenCode helpers + skill.

Pins:
- Sync/Pack compose paths for opencode_fuel.py, tray fuel readers, bob-setup-opencode
- Flat install Get-BobOpencodeFuel / Get-BobAgentFuel with fixture (no common\\scripts)
- Wrapper resolver prefers <install_root>/scripts then common/scripts
- Missing helper fails the layout pin
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

SYNC = ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
AGENT_FUEL = ROOT / "bob" / "tray" / "tools" / "Get-BobAgentFuel.ps1"
OPENCODE_FUEL_PS1 = ROOT / "bob" / "tray" / "tools" / "Get-BobOpencodeFuel.ps1"
OPENCODE_FUEL_PY = ROOT / "common" / "scripts" / "opencode_fuel.py"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bob-setup-opencode" / "SKILL.md"
WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"

FIXTURE = '{"costs": {"glm-5.3": 7.5}, "free_models": ["beam-free"]}'

OPENCODE_LAYOUT_PATHS = (
    "scripts/opencode_fuel.py",
    "tools/Get-BobOpencodeFuel.ps1",
    "tools/Get-BobAgentFuel.ps1",
    ".grok/skills/bob-setup-opencode/SKILL.md",
    "worker/.grok/skills/bob-setup-opencode/SKILL.md",
)


def assert_opencode_layout(root: Path) -> None:
    """Raise AssertionError naming each missing OpenCode pack path (FR #6159)."""
    missing = [rel for rel in OPENCODE_LAYOUT_PATHS if not (root / rel).is_file()]
    if missing:
        raise AssertionError("FR #6159 OpenCode layout missing: " + ", ".join(missing))


def _stage_product_body(pack: str) -> str:
    start = pack.index("function Stage-Product")
    nxt = pack.index("\nfunction ", start + 1)
    return pack[start:nxt]


def test_pack_union_fails_closed_without_opencode_fuel_helper(tmp_path):
    """The pack calls the fuel guard on every stage. Missing file throws; a real file does not."""
    pack = (ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
    guard_at = pack.index("function Assert-BobiverseStageHasOpencodeFuel")
    assert guard_at < pack.index("function Stage-Product")
    guard = pack[guard_at:pack.index("function Stage-Product")]
    assert "Test-Path -LiteralPath $ocFuel -PathType Leaf" in guard
    assert "throw 'bobiverse pack missing scripts\\opencode_fuel.py (common\\scripts union)'" in guard
    body = _stage_product_body(pack)
    copy_at = body.index("Copy-BobiverseRepoDirs -Root $RepoRoot -Sub 'scripts'")
    call_at = body.index("Assert-BobiverseStageHasOpencodeFuel -Stage $stage")
    between = body[copy_at:call_at]
    assert "if (" not in between
    assert "opencode_fuel.py" not in pack[pack.index("/XF"):pack.index("/XF") + 80] if "/XF" in pack else True
    assert OPENCODE_FUEL_PY.is_file()
    text = OPENCODE_FUEL_PY.read_text(encoding="utf-8")
    assert "def fuel_from_stats" in text or "def fuel_from_windowed_stats" in text

    def missing_helper(stage: Path) -> bool:
        return not (stage / "scripts" / "opencode_fuel.py").is_file()

    empty = tmp_path / "empty-stage"
    (empty / "scripts").mkdir(parents=True)
    present = tmp_path / "present-stage"
    dest = present / "scripts" / "opencode_fuel.py"
    dest.parent.mkdir(parents=True)
    dest.write_text(text, encoding="utf-8")
    assert missing_helper(empty) and not missing_helper(present)


def test_fr6159_source_assets_present():
    assert AGENT_FUEL.is_file()
    assert OPENCODE_FUEL_PS1.is_file()
    assert OPENCODE_FUEL_PY.is_file()
    assert SKILL.is_file()
    assert "CAST IRON RULE - HARVEST AND FILE EVERYTHING" in SKILL.read_text(encoding="utf-8")
    assert "name: bob-setup-opencode" in SKILL.read_text(encoding="utf-8")


def test_fr6159_sync_and_shared_ship_opencode_skill():
    sync = SYNC.read_text(encoding="utf-8-sig")
    assert "$Product -eq 'bob' -and $_.Name -eq 'bob-setup-opencode'" in sync
    assert "tools-no-xo" in sync.lower() or "FR #6154" in sync
    common = COMMON.read_text(encoding="utf-8-sig")
    assert "'bob-setup-opencode'" in common
    assert "Name = 'worker'" in common


def test_fr6159_get_bob_opencode_fuel_prefers_flat_scripts_file():
    src = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "scripts\\opencode_fuel.py" in src
    assert "common\\scripts\\opencode_fuel.py" in src
    assert "PathType Leaf" in src
    assert "FR #6159" in src


def test_fr6159_layout_pin_helper_names_missing_path(tmp_path: Path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "Get-BobAgentFuel.ps1").write_text("#", encoding="utf-8")
    with pytest.raises(AssertionError) as ei:
        assert_opencode_layout(tmp_path)
    msg = str(ei.value)
    assert "scripts/opencode_fuel.py" in msg
    assert "Get-BobOpencodeFuel.ps1" in msg


def test_fr6159_resolve_flat_install_root_scripts(tmp_path: Path):
    sys.path.insert(0, str(ROOT / "bob" / "scripts"))
    import bob_worker as bw  # noqa: WPS433

    install = tmp_path / "bob"
    # Non-existent extraction dir for source_file so source-relative candidates miss.
    source = tmp_path / "missing-extract" / "bob_worker.py"
    helper = install / "scripts" / "opencode_fuel.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("# flat helper\n", encoding="utf-8")
    # Empty common/scripts dir must not win over missing file.
    (install / "common" / "scripts").mkdir(parents=True)

    resolved = bw._resolve_opencode_fuel_helper_path(
        source_file=str(source), install_root=str(install)
    )
    assert resolved == helper.resolve()


def test_fr6159_resolve_scripts_wins_over_common(tmp_path: Path):
    sys.path.insert(0, str(ROOT / "bob" / "scripts"))
    import bob_worker as bw  # noqa: WPS433

    install = tmp_path / "bob"
    source = tmp_path / "missing-extract" / "bob_worker.py"
    flat = install / "scripts" / "opencode_fuel.py"
    nested = install / "common" / "scripts" / "opencode_fuel.py"
    flat.parent.mkdir(parents=True)
    nested.parent.mkdir(parents=True)
    flat.write_text("# flat\n", encoding="utf-8")
    nested.write_text("# nested\n", encoding="utf-8")
    resolved = bw._resolve_opencode_fuel_helper_path(
        source_file=str(source), install_root=str(install)
    )
    assert resolved == flat.resolve()


def test_fr6159_resolve_cwd_parent_flat_scripts(tmp_path: Path):
    sys.path.insert(0, str(ROOT / "bob" / "scripts"))
    import bob_worker as bw  # noqa: WPS433

    source = tmp_path / "missing-extract" / "bob_worker.py"
    install = tmp_path / "bob"
    cwd = install / "worker"
    cwd.mkdir(parents=True)
    helper = install / "scripts" / "opencode_fuel.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("# cwd flat\n", encoding="utf-8")
    resolved = bw._resolve_opencode_fuel_helper_path(
        cwd=str(cwd), source_file=str(source)
    )
    assert resolved == helper.resolve()


def test_fr6159_build_launch_embeds_flat_helper(tmp_path: Path, monkeypatch):
    sys.path.insert(0, str(ROOT / "bob" / "scripts"))
    import bob_worker as bw  # noqa: WPS433

    install = tmp_path / "bob"
    helper = install / "scripts" / "opencode_fuel.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("# helper\n", encoding="utf-8")
    cwd = install / "worker"
    cwd.mkdir(parents=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    seen: dict = {}

    def fake_resolve(*, cwd=None, source_file=None, install_root=None):  # noqa: ARG001
        seen["install_root"] = install_root
        seen["cwd"] = cwd
        return helper.resolve()

    monkeypatch.setattr(bw, "_resolve_opencode_fuel_helper_path", fake_resolve)
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(cwd),
        "Do work.",
        "opencode.exe",
        run_dir,
        install_root=str(install),
    )
    assert seen.get("install_root") == str(install)
    assert seen.get("cwd") == str(cwd)
    script = next(v for k, v in spec.files.items() if k.endswith("launch-opencode.ps1"))
    esc = str(helper.resolve()).replace("'", "''")
    assert f"$pyHelper = '{esc}'" in script


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell")
@pytest.mark.skipif(not shutil.which("python"), reason="python.exe required")
def test_fr6159_flat_install_agent_fuel_returns_opencode(tmp_path: Path):
    """Composed flat install: tools + scripts only (no common\\scripts)."""
    install = tmp_path / "bob"
    tools = install / "tools"
    scripts = install / "scripts"
    tools.mkdir(parents=True)
    scripts.mkdir(parents=True)
    shutil.copy(OPENCODE_FUEL_PS1, tools / "Get-BobOpencodeFuel.ps1")
    shutil.copy(AGENT_FUEL, tools / "Get-BobAgentFuel.ps1")
    shutil.copy(OPENCODE_FUEL_PY, scripts / "opencode_fuel.py")
    # Minimal BobBridge module so Get-BobAgentFuel can import (cursor/xai stubs).
    src = install / "src"
    src.mkdir()
    (src / "BobBridge.psd1").write_text(
        "@{ ModuleVersion='0.0.0'; RootModule='BobBridge.psm1'; FunctionsToExport='*' }\n",
        encoding="utf-8",
    )
    (src / "BobBridge.psm1").write_text(
        "\n".join(
            [
                "function Get-BobCursorAgentWeeklyRemaining { $null }",
                "function Get-BobCursorGroupRemainFromLocalDoc { param($LocalCursorDoc,$GroupId) $null }",
                "function Get-BobWeeklyRemaining { $null }",
                "function Get-BobGrokAuthSnapshot { $null }",
                "function Get-BobGrokAvailability { param($Weekly,$Auth) @{ state='unknown'; reason='stub'; remaining_pct=$null } }",
                "Export-ModuleMember -Function *",
                "",
            ]
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["BOB_OPENCODE_FUEL_FIXTURE"] = FIXTURE
    env.pop("PYTHONPATH", None)
    # Unrelated cwd so PSScriptRoot-relative resolution must walk to install root.
    work = tmp_path / "elsewhere"
    work.mkdir()
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tools / "Get-BobAgentFuel.ps1"),
            "-InstallRoot",
            str(install),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(work),
        timeout=90,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    line = result.stdout.strip().splitlines()[-1]
    doc = json.loads(line)
    assert doc.get("ok") is True
    oc = doc.get("opencode") or {}
    assert oc.get("free") == 100
    assert oc.get("go") == 50
    models = oc.get("models") or {}
    assert models.get("glm-5.3") == 50


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell")
@pytest.mark.skipif(not shutil.which("python"), reason="python.exe required")
def test_fr6159_flat_opencode_fuel_helper_alone(tmp_path: Path):
    install = tmp_path / "bob"
    tools = install / "tools"
    scripts = install / "scripts"
    elsewhere = tmp_path / "elsewhere"
    tools.mkdir(parents=True)
    scripts.mkdir(parents=True)
    elsewhere.mkdir(parents=True)
    shutil.copy(OPENCODE_FUEL_PS1, tools / "Get-BobOpencodeFuel.ps1")
    shutil.copy(OPENCODE_FUEL_PY, scripts / "opencode_fuel.py")
    env = os.environ.copy()
    env["BOB_OPENCODE_FUEL_FIXTURE"] = FIXTURE
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tools / "Get-BobOpencodeFuel.ps1"),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(elsewhere),
        timeout=60,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    parsed = json.loads(result.stdout.strip().splitlines()[-1])
    assert parsed["free"] == 100
    assert parsed["go"] == 50


def test_fr6159_worker_source_has_flat_resolver_and_install_root_kw():
    src = WORKER.read_text(encoding="utf-8")
    assert 'root / "scripts" / "opencode_fuel.py"' in src
    assert "install_root: str | Path | None = None" in src
    assert "install_root=install_root" in src or "install_root=self.install_root" in src
    # Hash pin: composed helper content must match source when present.
    assert OPENCODE_FUEL_PY.is_file()
    digest = hashlib.sha256(OPENCODE_FUEL_PY.read_bytes()).hexdigest()
    assert len(digest) == 64
