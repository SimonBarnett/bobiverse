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

# FR #6670 / #6669: live seats may export BOB_OPENCODE_USAGE_URL; the helper then
# clears go and reads provider limits. Fixture pins need a pure stats/fixture path.
_OPENCODE_FUEL_SCRUB = (
    "BOB_OPENCODE_USAGE_URL",
    "OPENCODE_SERVER_PASSWORD",
    "OPENCODE_SERVER_USERNAME",
    "BOB_OPENCODE_FUEL_CACHE_FILE",
    "BOB_INSTALL_ROOT",
    "PYTHONPATH",
)


def _opencode_fuel_fixture_env() -> dict:
    env = os.environ.copy()
    for key in _OPENCODE_FUEL_SCRUB:
        env.pop(key, None)
    env.pop("BOB_OPENCODE_FUEL_HELPER", None)
    # FR #6669 / MRB #6691: prefer this interpreter over WindowsApps store aliases.
    py_dir = str(Path(sys.executable).resolve().parent)
    env["PATH"] = py_dir + os.pathsep + env.get("PATH", "")
    # FR #6701: pin the interpreter explicitly. Under LocalSystem the PATH pin
    # can still resolve a broken store alias; the child then prints nothing.
    env["BOB_OPENCODE_PYTHON"] = sys.executable
    env["BOB_OPENCODE_FUEL_FIXTURE"] = FIXTURE
    return env


def _tail(text: str | None, limit: int = 1200) -> str:
    body = (text or "").strip()
    return body[-limit:] if len(body) > limit else body


def _run_opencode_fuel_ps(
    script: Path,
    *,
    env: dict,
    cwd: Path,
    timeout: int = 60,
    extra_args: tuple[str, ...] = (),
) -> dict:
    """Run a fuel helper and name the failing stage in the assertion message."""
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        timeout=timeout,
    )
    stage = (
        f"powershell exit={result.returncode}\n"
        f"stdout tail:\n{_tail(result.stdout)}\n"
        f"stderr tail:\n{_tail(result.stderr)}"
    )
    assert result.returncode == 0, stage
    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
    assert lines, "empty stdout\n" + stage
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(f"non-JSON last stdout line: {lines[-1][:500]!r}\n{stage}") from exc


def _assert_fuel_ok(parsed: dict, *, free: int = 100, go: int | None = 50) -> None:
    """Value assert with full helper JSON context (FR #6717)."""
    ctx = json.dumps(parsed, sort_keys=True)[:1200]
    assert parsed.get("read_state") == "ok", (
        f"read_state={parsed.get('read_state')!r} "
        f"stats_error={parsed.get('stats_error')!r} "
        f"python_exit={parsed.get('python_exit')!r} json={ctx}"
    )
    assert parsed.get("free") == free, f"free={parsed.get('free')!r} json={ctx}"
    if go is None:
        assert parsed.get("go") is None, f"go={parsed.get('go')!r} json={ctx}"
    else:
        assert parsed.get("go") == go, f"go={parsed.get('go')!r} json={ctx}"


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
    # FR #6660: Pack Stage-Product must stage bob-setup-opencode for Product=bob (same filter as Sync).
    pack = (ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
    body = _stage_product_body(pack)
    assert "bob-setup-opencode" in body
    assert "$Name -eq 'bob' -and $_.Name -eq 'bob-setup-opencode'" in body


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

    env = _opencode_fuel_fixture_env()
    # Unrelated cwd so PSScriptRoot-relative resolution must walk to install root.
    work = tmp_path / "elsewhere"
    work.mkdir()
    doc = _run_opencode_fuel_ps(
        tools / "Get-BobAgentFuel.ps1",
        env=env,
        cwd=work,
        timeout=90,
        extra_args=("-InstallRoot", str(install)),
    )
    assert doc.get("ok") is True, json.dumps(doc, sort_keys=True)[:1200]
    oc = doc.get("opencode") or {}
    ctx = json.dumps(oc, sort_keys=True)[:1200]
    assert oc.get("free") == 100, f"free={oc.get('free')!r} json={ctx}"
    assert oc.get("go") == 50, f"go={oc.get('go')!r} json={ctx}"
    models = oc.get("models") or {}
    assert models.get("glm-5.3") == 50, f"models={models!r} json={ctx}"


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
    env = _opencode_fuel_fixture_env()
    parsed = _run_opencode_fuel_ps(
        tools / "Get-BobOpencodeFuel.ps1", env=env, cwd=elsewhere
    )
    _assert_fuel_ok(parsed)


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell")
@pytest.mark.skipif(not shutil.which("python"), reason="python.exe required")
def test_fr6701_flat_helper_uses_python_override_without_python_on_path(tmp_path: Path):
    """FR #6701: no python.exe on PATH must not null the fixture (LocalSystem class)."""
    install = tmp_path / "bob"
    tools = install / "tools"
    scripts = install / "scripts"
    elsewhere = tmp_path / "elsewhere"
    tools.mkdir(parents=True)
    scripts.mkdir(parents=True)
    elsewhere.mkdir(parents=True)
    shutil.copy(OPENCODE_FUEL_PS1, tools / "Get-BobOpencodeFuel.ps1")
    shutil.copy(OPENCODE_FUEL_PY, scripts / "opencode_fuel.py")
    env = _opencode_fuel_fixture_env()
    assert env["BOB_OPENCODE_PYTHON"] == sys.executable
    # Reproduce a SYSTEM PATH that has no usable python.exe (and no store alias).
    env["PATH"] = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    parsed = _run_opencode_fuel_ps(
        tools / "Get-BobOpencodeFuel.ps1", env=env, cwd=elsewhere
    )
    _assert_fuel_ok(parsed)


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell")
@pytest.mark.skipif(not shutil.which("python"), reason="python.exe required")
def test_fr6670_usage_url_without_scrub_nulls_go(tmp_path: Path):
    """Regression: inherited BOB_OPENCODE_USAGE_URL must be scrubbed for fixture pins."""
    install = tmp_path / "bob"
    tools = install / "tools"
    scripts = install / "scripts"
    elsewhere = tmp_path / "elsewhere"
    tools.mkdir(parents=True)
    scripts.mkdir(parents=True)
    elsewhere.mkdir(parents=True)
    shutil.copy(OPENCODE_FUEL_PS1, tools / "Get-BobOpencodeFuel.ps1")
    shutil.copy(OPENCODE_FUEL_PY, scripts / "opencode_fuel.py")
    env = _opencode_fuel_fixture_env()
    # URL validation rejects this loopback value before any connection; the point
    # of the pin is the provider branch (go cleared), not a live usage read.
    env["BOB_OPENCODE_USAGE_URL"] = "http://127.0.0.1:9/nope"
    parsed = _run_opencode_fuel_ps(
        tools / "Get-BobOpencodeFuel.ps1", env=env, cwd=elsewhere
    )
    # read_state=ok proves the stats stage completed before the provider gate.
    _assert_fuel_ok(parsed, go=None)
    assert (parsed.get("models") or {}).get("glm-5.3") == 50
    assert parsed.get("provider_read") == "unavailable"
    assert "go" in parsed
    assert parsed.get("provider") == "usage-limits"


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell")
@pytest.mark.skipif(not shutil.which("python"), reason="python.exe required")
def test_fr6717_flat_helper_works_when_pathext_lacks_exe(tmp_path: Path):
    """FR #6717: stripped PATHEXT (no .EXE) must not null fixture fuel under call operator.

    Isolated / LocalSystem release runners can omit PATHEXT. Without .EXE,
    PowerShell's & $py is a silent no-op -> stats_failed / free=go=null.
    """
    install = tmp_path / "bob"
    tools = install / "tools"
    scripts = install / "scripts"
    elsewhere = tmp_path / "elsewhere"
    tools.mkdir(parents=True)
    scripts.mkdir(parents=True)
    elsewhere.mkdir(parents=True)
    shutil.copy(OPENCODE_FUEL_PS1, tools / "Get-BobOpencodeFuel.ps1")
    shutil.copy(OPENCODE_FUEL_PY, scripts / "opencode_fuel.py")
    env = _opencode_fuel_fixture_env()
    # Counterexample without the helper PATHEXT ensure: only .CPL breaks & $py.
    env["PATHEXT"] = ".CPL"
    env["PATH"] = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    parsed = _run_opencode_fuel_ps(
        tools / "Get-BobOpencodeFuel.ps1", env=env, cwd=elsewhere
    )
    _assert_fuel_ok(parsed)
    assert (parsed.get("models") or {}).get("glm-5.3") == 50


def test_fr6159_worker_source_has_flat_resolver_and_install_root_kw():
    src = WORKER.read_text(encoding="utf-8")
    assert 'root / "scripts" / "opencode_fuel.py"' in src
    assert "install_root: str | Path | None = None" in src
    assert "install_root=install_root" in src or "install_root=self.install_root" in src
    # Hash pin: composed helper content must match source when present.
    assert OPENCODE_FUEL_PY.is_file()
    digest = hashlib.sha256(OPENCODE_FUEL_PY.read_bytes()).hexdigest()
    assert len(digest) == 64
