"""FR #5655: LEGION PsExec provision, WhatIf fail-closed, DONE exit on failures."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg
from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/airc_network_installer/install.py"
LEGION = ROOT / "airc/scripts/airc_legion.py"
SKILL_CMD = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"
SKILL_T = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"


def test_fr5655_ensure_psexec_exists():
    t = INSTALL.read_text(encoding="utf-8")
    assert "def ensure_psexec" in t
    assert "FR #5655" in t
    assert "offer_download_psexec" in t
    assert "AIRC_LEGION_NO_PSEXEC_DOWNLOAD" in t
    assert "ProgramData" in t
    assert not INSTALL.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr5655_default_installer_uses_ensure_psexec():
    t = LEGION.read_text(encoding="utf-8")
    assert "ensure_psexec" in t
    assert "plan_psexec" in t
    assert "FR #5655" in t
    assert "will_fail" in t


def test_fr5712_whatif_plans_allowed_psexec_download_without_downloading(monkeypatch, tmp_path):
    import airc_network_installer.install as inst

    program_data = tmp_path / "ProgramData"
    monkeypatch.setenv("ProgramData", str(program_data))
    monkeypatch.delenv("AIRC_PSEXEC_PATH", raising=False)
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.setattr(inst, "find_psexec", lambda explicit="": None)
    downloads: list[Path] = []
    monkeypatch.setattr(
        inst,
        "offer_download_psexec",
        lambda dest: downloads.append(dest) or dest,
    )

    out = lg.default_installer_run(
        {
            "hosts": ["flamingo"],
            "dry_run": True,
            "profile": "client",
            "force": False,
            "timeout_s": 30,
            "msi": "",
        }
    )

    assert out["ok"] is True
    assert out["status"] == "dry-run"
    assert out["psexec"] == str(program_data / "bobiverse" / "tools" / "PsExec.exe")
    assert out["psexec_action"] == "download"
    assert downloads == []

    body = lg.installer_legion_work(
        "flamingo",
        whatif=True,
        run_fn=lg.default_installer_run,
        credman=lambda: {},
    )
    assert body["ok"] is True
    assert body["plan"]["psexec_action"] == "download"
    assert downloads == []


def test_fr5655_whatif_psexec_missing_fail_closed(monkeypatch):
    import airc_network_installer.install as inst

    monkeypatch.setenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", "1")
    monkeypatch.setattr(inst, "find_psexec", lambda explicit="": None)

    out = lg.default_installer_run(
        {
            "hosts": ["flamingo"],
            "dry_run": True,
            "profile": "client",
            "force": False,
            "timeout_s": 30,
            "msi": "",
        }
    )
    assert out["ok"] is False
    assert out["error"] == "psexec-missing"
    assert out["psexec"] == "psexec-missing"
    assert out.get("need")
    assert any(f.get("error") == "psexec-missing" for f in (out.get("failures") or []))


def test_fr5655_deliver_exit_nonzero_on_failures():
    log = lg.build_legion_log(
        target="flamingo",
        whatif=False,
        summary="failed",
        failures=[{"host": "flamingo", "error": "psexec-missing"}],
    )
    out = lg.deliver_legion_log(job_id="b1000001", log=log, offer=None)
    assert "exit=1" in out["done"]


def test_fr5655_deliver_exit_zero_when_clean():
    log = lg.build_legion_log(
        target="flamingo",
        whatif=False,
        summary="success",
        failures=[],
    )
    out = lg.deliver_legion_log(job_id="b1000002", log=log, offer=None)
    assert "exit=0" in out["done"]


def test_fr5655_skills_document():
    blob = SKILL_CMD.read_text(encoding="utf-8") + "\n" + SKILL_T.read_text(encoding="utf-8")
    assert "5655" in blob
    assert "psexec-missing" in blob
    assert "ProgramData" in blob or "ensure_psexec" in blob or "Sysinternals" in blob
