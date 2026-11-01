"""FR #5712: LEGION -WhatIf plans PsExec would-download (no download / no writes)."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg
import airc_network_installer.install as inst
from repo_layout import ROOT

SKILL_CMD = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"
SKILL_T = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"


def _snap(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root)).replace("\\", "/")] = p.read_bytes()
    return out


def test_fr5712_plan_psexec_would_download_no_writes(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.setenv("ProgramData", str(tmp_path / "pd"))
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tmp_path / "tools" / "PsExec.exe"))
    monkeypatch.setattr(inst, "find_psexec", lambda explicit="": None)

    def boom_download(*_a, **_k):
        raise AssertionError("offer_download_psexec must not run during plan")

    def boom_retrieve(*_a, **_k):
        raise AssertionError("urlretrieve must not run during plan")

    monkeypatch.setattr(inst, "offer_download_psexec", boom_download)
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlretrieve", boom_retrieve)
    before = _snap(tmp_path)
    plan = inst.plan_psexec(
        "",
        probe=lambda *_a, **_k: {
            "reachable": True,
            "reason": "http-200",
            "url": inst.PSEXEC_ZIP_URL,
        },
    )
    after = _snap(tmp_path)
    assert plan["state"] == "would-download"
    assert plan["url"] == inst.PSEXEC_ZIP_URL
    assert plan["dest"]
    assert before == after


def test_fr5712_plan_psexec_unreachable(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tmp_path / "PsExec.exe"))
    monkeypatch.setattr(inst, "find_psexec", lambda explicit="": None)
    plan = inst.plan_psexec(
        "",
        probe=lambda *_a, **_k: {
            "reachable": False,
            "reason": "URLError:timed-out",
            "url": inst.PSEXEC_ZIP_URL,
        },
    )
    assert plan["state"] == "unreachable"
    assert "timed" in plan["reason"] or "URLError" in plan["reason"]


def test_fr5712_plan_psexec_cached_and_opt_out(tmp_path, monkeypatch):
    dest = tmp_path / "PsExec.exe"
    dest.write_bytes(b"MZ")
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(dest))
    monkeypatch.setattr(inst, "find_psexec", lambda explicit="": None)
    plan = inst.plan_psexec("")
    assert plan["state"] == "cached"
    assert Path(plan["path"]) == dest.resolve()

    monkeypatch.setenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", "1")
    plan2 = inst.plan_psexec("")
    assert plan2["state"] == "missing"


def test_fr5712_whatif_would_download_ok(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tmp_path / "PsExec.exe"))
    monkeypatch.setattr(inst, "find_psexec", lambda explicit="": None)
    monkeypatch.setattr(
        inst,
        "offer_download_psexec",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no download")),
    )
    monkeypatch.setattr(
        inst,
        "plan_psexec",
        lambda explicit="", dest=None, probe=None: {
            "state": "would-download",
            "url": inst.PSEXEC_ZIP_URL,
            "dest": str(tmp_path / "PsExec.exe"),
            "reason": "http-200",
        },
    )
    before = _snap(tmp_path)
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
    after = _snap(tmp_path)
    assert out["ok"] is True
    assert out["status"] == "dry-run"
    assert out["psexec"] == "would-download"
    assert out.get("psexec_download", {}).get("url") == inst.PSEXEC_ZIP_URL
    assert not out.get("failures")
    assert before == after


def test_fr5712_whatif_unreachable_fails(monkeypatch, tmp_path):
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tmp_path / "PsExec.exe"))
    monkeypatch.setattr(
        inst,
        "plan_psexec",
        lambda explicit="", dest=None, probe=None: {
            "state": "unreachable",
            "url": inst.PSEXEC_ZIP_URL,
            "dest": str(tmp_path / "PsExec.exe"),
            "reason": "URLError:offline",
        },
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
    assert out["ok"] is False
    assert out["error"] == "psexec-source-unreachable"
    assert any(
        f.get("error") == "psexec-source-unreachable" for f in (out.get("failures") or [])
    )


def test_fr5712_installer_work_plan_copies_download_meta(monkeypatch, tmp_path):
    dest = str(tmp_path / "PsExec.exe")

    def fake_run(spec, *, secret=""):
        return {
            "ok": True,
            "status": "dry-run",
            "host": "flamingo",
            "psexec": "would-download",
            "msi": "latest",
            "psexec_download": {"url": inst.PSEXEC_ZIP_URL, "dest": dest},
        }

    body = lg.installer_legion_work(
        "flamingo",
        whatif=True,
        run_fn=fake_run,
        credman=lambda: {},
    )
    assert body["ok"] is True
    assert body["psexec"] == "would-download"
    plan = body.get("plan") or {}
    assert plan.get("psexec") == "would-download"
    assert plan.get("psexec_url") == inst.PSEXEC_ZIP_URL
    assert plan.get("psexec_dest") == dest
    assert "will_fail" not in plan


def test_fr5712_skills_document_would_download():
    blob = SKILL_CMD.read_text(encoding="utf-8") + "\n" + SKILL_T.read_text(encoding="utf-8")
    assert "5712" in blob
    assert "would-download" in blob
    assert "psexec-source-unreachable" in blob
    assert "plan_psexec" in blob
