"""FR #5288: client allow-list retains the in-service Priority module."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"
PRIO_DOC = ROOT / "airc/docs/airc-priority-client.md"
ALLOW = ROOT / "airc/tests/test_fr3514_client_allowlist_payload.py"


def _ps(script: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_fr5288_allowlist_names_priority_module():
    t = COMMON.read_text(encoding="utf-8-sig")
    start = t.index("function Get-BobiverseAircClientAllowedScriptNames")
    end = t.index("function Get-BobiverseAircMsiAgentLayerScriptNames")
    allow = t[start:end]
    assert "airc_priority.py" in allow
    assert "FR #5288" in allow
    rem = ALLOW.read_text(encoding="utf-8")
    assert r"scripts\airc_priority.py" in rem
    assert r"airc\priority-worker\priority_worker.py" in rem


def test_fr5288_client_purge_keeps_priority_worker_and_module(tmp_path: Path):
    stage = tmp_path / "client-stage"
    (stage / "scripts").mkdir(parents=True)
    pw = stage / "airc" / "priority-worker"
    pw.mkdir(parents=True)
    (pw / "priority_worker.py").write_text("# stub\n", encoding="utf-8")
    (stage / "scripts" / "airc_priority.py").write_text("# stub\n", encoding="utf-8")
    (stage / "scripts" / "gitclaim.py").write_text("# drop\n", encoding="utf-8")
    (stage / "VERSION").write_text("0.0.0\n", encoding="utf-8")
    proc = _ps(
        f". '{COMMON}'; $null = @(Remove-BobiverseAircClientExtraPayload -InstallRoot '{stage}')"
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert (pw / "priority_worker.py").is_file()
    assert (stage / "scripts" / "airc_priority.py").is_file()
    assert not (stage / "scripts" / "gitclaim.py").exists()


def test_fr5288_docs_client_and_fleet_default_on():
    for path in (SKILL, POST, PRIO_DOC):
        text = path.read_text(encoding="utf-8")
        assert "5288" in text, path.name
        assert "priority" in text.lower()
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")
