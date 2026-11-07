"""FR #6160 / FR-OC-FLEET: OpenCode fleet smoke checklist (no secrets)."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Assert-BobOpencodeFleetSmoke.ps1"
SKILL = ROOT / ".grok" / "skills" / "bob-setup-opencode" / "SKILL.md"
OPS = ROOT / "docs" / "opencode-fleet-enabled.md"
WORKER_DOC = ROOT / "docs" / "bob-worker.md"
PARK = ROOT / "docs" / "fr" / "opencode-seat-gaps" / "FR-OC-FLEET.md"

# Contiguous hunter-style secret shapes must not appear in docs/scripts.
_SECRETISH = re.compile(
    r"(?i)("
    r"sk-[A-Za-z0-9]{20,}"
    r"|Bearer\s+[A-Za-z0-9\-._~+/]+=*"
    r"|password\s*=\s*\S+"
    r"|api[_-]?key\s*=\s*\S+"
    r"|BEGIN\s+(RSA\s+)?PRIVATE\s+KEY"
    r")"
)


def _read(p: Path) -> str:
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), p
    return raw.decode("utf-8")


def test_fr6160_assert_script_exists_and_documents_exits():
    src = _read(SCRIPT)
    assert "FR #6160" in src or "FR-OC-FLEET" in src
    assert "never" in src.lower() and "auth.json" in src
    assert "Get-Content" not in src or "never" in src.lower()
    # Must not cat auth body
    assert "Get-Content -LiteralPath $AuthPath" not in src
    assert "ReadAllText($AuthPath)" not in src
    assert "-SkipPong" in src and "-SkipDryRun" in src
    assert "opencode_cmd" in src
    assert "bob-worker" in src
    for code in ("exit 0", "exit $script:FailCode", "Fail-Smoke 1", "Fail-Smoke 4"):
        assert code.split()[0] in src or "Fail-Smoke" in src
    assert "Fail-Smoke 1" in src  # opencode missing
    assert "Fail-Smoke 4" in src  # dry-run / worker missing


def test_fr6160_script_exits_nonzero_when_opencode_missing(tmp_path: Path):
    """Clear PATH so Resolve-OpencodeExe fails; expect exit 1."""
    if sys.platform != "win32":
        return
    # Minimal env: empty PATH, skip auth/pong/dry-run so only PATH check fails.
    env = dict(**{k: v for k, v in __import__("os").environ.items() if k.upper() != "PATH"})
    env["PATH"] = str(tmp_path)  # empty of opencode
    env["LOCALAPPDATA"] = str(tmp_path / "la")
    (tmp_path / "la").mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-SkipPong",
            "-SkipDryRun",
            "-SkipAuth",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)
    assert "FAIL" in proc.stdout or "opencode" in proc.stdout.lower()


def test_fr6160_script_exits_nonzero_when_worker_missing(tmp_path: Path):
    """Dry-run path: fake opencode on PATH but missing bob-worker -> exit 4."""
    if sys.platform != "win32":
        return
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    # stub opencode.cmd that prints a version
    stub = fake_bin / "opencode.cmd"
    stub.write_text("@echo off\r\necho 0.0.0-test\r\n", encoding="ascii")
    env = dict(__import__("os").environ)
    env["PATH"] = str(fake_bin) + ";" + env.get("PATH", "")
    env["LOCALAPPDATA"] = str(tmp_path / "la")
    (tmp_path / "la").mkdir(parents=True, exist_ok=True)
    bogus_root = tmp_path / "bob-install"
    (bogus_root / "worker").mkdir(parents=True)
    # no bob-worker.exe under worker/
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-SkipPong",
            "-SkipAuth",
            "-InstallRoot",
            str(bogus_root),
            "-WorkerExe",
            str(bogus_root / "worker" / "missing-bob-worker.exe"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 4, (proc.returncode, proc.stdout, proc.stderr)
    assert "dry-run" in proc.stdout.lower() or "bob-worker" in proc.stdout.lower()


def test_fr6160_docs_and_skill_have_no_secret_material():
    for path in (SCRIPT, SKILL, OPS, WORKER_DOC, PARK):
        text = _read(path)
        bad = _SECRETISH.findall(text)
        assert not bad, f"{path} looks secretish: {bad[:3]}"


def test_fr6160_skill_checklist_and_troubleshoot_aligned():
    skill = _read(SKILL)
    assert "Assert-BobOpencodeFleetSmoke" in skill
    assert "FR #6160" in skill or "FR-OC-FLEET" in skill
    assert "opencode-fleet-enabled.md" in skill
    # Failure modes table matches setup skill troubleshoot (FR testable #3)
    for row in (
        "opencode : The term 'opencode' is not recognized",
        "Auth errors / 401",
        "Model 429 / cap hit",
        "npm route fails on old Node",
    ):
        assert row in skill
    ops = _read(OPS)
    assert "Assert-BobOpencodeFleetSmoke" in ops
    assert "trial metrics" in ops.lower() or "PRs attempted" in ops or "prs_attempted" in ops
    assert "auth.json" in ops.lower()
    # never instruct to cat body
    assert "Get-Content" not in ops or "never" in ops.lower()
    assert "cat auth" not in ops.lower()


def test_fr6160_park_maps_issue():
    tsv = _read(ROOT / "docs" / "fr" / "opencode-seat-gaps" / "SMALL-FRS.tsv")
    assert "FR-OC-FLEET" in tsv and "6160" in tsv
    park = _read(PARK)
    assert "Assert" in park or "checklist" in park.lower() or "Smoke" in park
