"""FR #5712 / #5737: LEGION -WhatIf plans PsExec without network writes.

FR #5712 introduced read-only plan_psexec. FR #5737 retires verb-time
would-download / network probe: install deploys a pinned copy; WhatIf reports
deployed / would-redeploy / undeployed.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import airc_legion as lg
import airc_network_installer.install as inst
import airc_network_installer.psexec_deploy as dep
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


def _pin_fake(tmp_path, monkeypatch):
    exe = b"MZ-FAKE-5712"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("PsExec.exe", exe)
    zbytes = buf.getvalue()
    pin = {
        "zip_url": "https://example.invalid/PSTools.zip",
        "zip_sha256": hashlib.sha256(zbytes).hexdigest(),
        "psexec_sha256": hashlib.sha256(exe).hexdigest(),
    }
    monkeypatch.setattr(dep, "load_psexec_pin", lambda: dict(pin))
    monkeypatch.setattr(inst, "load_psexec_pin", lambda: dict(pin))
    monkeypatch.setenv("ProgramData", str(tmp_path / "pd"))
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tmp_path / "tools" / "PsExec.exe"))
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.delenv("AIRC_NO_PSEXEC_DEPLOY", raising=False)
    zpath = tmp_path / "PSTools.zip"
    zpath.write_bytes(zbytes)
    return zpath, exe, pin


def test_fr5712_plan_psexec_would_download_no_writes(tmp_path, monkeypatch):
    """Superseded by #5737: without cache, plan is undeployed and writes nothing."""
    _pin_fake(tmp_path, monkeypatch)

    def boom_download(*_a, **_k):
        raise AssertionError("offer_download_psexec must not run during plan")

    def boom_retrieve(*_a, **_k):
        raise AssertionError("urlretrieve must not run during plan")

    monkeypatch.setattr(inst, "offer_download_psexec", boom_download)
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlretrieve", boom_retrieve)
    before = _snap(tmp_path)
    plan = inst.plan_psexec("")
    after = _snap(tmp_path)
    assert plan["state"] == "undeployed"
    assert before == after


def test_fr5712_plan_psexec_unreachable(tmp_path, monkeypatch):
    """Network probe is ignored; missing cache => undeployed (FR #5737)."""
    _pin_fake(tmp_path, monkeypatch)
    plan = inst.plan_psexec(
        "",
        probe=lambda *_a, **_k: {
            "reachable": False,
            "reason": "URLError:timed-out",
            "url": inst.PSEXEC_ZIP_URL,
        },
    )
    assert plan["state"] == "undeployed"


def test_fr5712_plan_psexec_cached_and_opt_out(tmp_path, monkeypatch):
    zpath, exe, pin = _pin_fake(tmp_path, monkeypatch)
    dep.deploy_psexec(zip_path=zpath, allow_network=False)
    plan = inst.plan_psexec("")
    assert plan["state"] == "deployed"
    assert Path(plan["path"]).read_bytes() == exe

    monkeypatch.setenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", "1")
    # Opt-out with hash-ok dest still reports deployed via ensure path; plan uses opt-out
    # only when dest is not hash-ok. Corrupt dest under opt-out -> missing.
    Path(plan["path"]).write_bytes(b"bad")
    plan2 = inst.plan_psexec("")
    assert plan2["state"] == "missing"


def test_fr5712_whatif_would_download_ok(tmp_path, monkeypatch):
    """WhatIf would-redeploy (local cache) is ok — replaces would-download."""
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tmp_path / "PsExec.exe"))
    monkeypatch.setattr(
        inst,
        "plan_psexec",
        lambda explicit="", dest=None, probe=None: {
            "state": "would-redeploy",
            "cache": str(tmp_path / "cache" / "PSTools.zip"),
            "dest": str(tmp_path / "PsExec.exe"),
            "reason": "exe-missing-or-hash-mismatch",
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
    assert out["psexec"] == "would-redeploy"
    assert not out.get("failures")
    assert before == after


def test_fr5712_whatif_unreachable_fails(monkeypatch, tmp_path):
    """Undeployed (no local cache) fails closed — replaces unreachable."""
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tmp_path / "PsExec.exe"))
    monkeypatch.setattr(
        inst,
        "plan_psexec",
        lambda explicit="", dest=None, probe=None: {
            "state": "undeployed",
            "dest": str(tmp_path / "PsExec.exe"),
            "reason": "run-airc-install-or-update",
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
    assert out["error"] == "psexec-undeployed"
    assert any(f.get("error") == "psexec-undeployed" for f in (out.get("failures") or []))


def test_fr5712_installer_work_plan_copies_download_meta(monkeypatch, tmp_path):
    dest = str(tmp_path / "PsExec.exe")
    cache = str(tmp_path / "cache" / "PSTools.zip")

    def fake_run(spec, *, secret=""):
        return {
            "ok": True,
            "status": "dry-run",
            "host": "flamingo",
            "psexec": "would-redeploy",
            "msi": "latest",
            "psexec_download": {"cache": cache, "dest": dest},
        }

    body = lg.installer_legion_work(
        "flamingo",
        whatif=True,
        run_fn=fake_run,
        credman=lambda: {},
    )
    assert body["ok"] is True
    assert body["psexec"] == "would-redeploy"
    plan = body.get("plan") or {}
    assert plan.get("psexec") == "would-redeploy"
    assert plan.get("psexec_dest") == dest
    assert "will_fail" not in plan


def test_fr5712_skills_document_would_download():
    blob = SKILL_CMD.read_text(encoding="utf-8") + "\n" + SKILL_T.read_text(encoding="utf-8")
    assert "5712" in blob
    assert "plan_psexec" in blob or "Deploy-AircPsExec" in blob or "5737" in blob
    assert "would-redeploy" in blob or "psexec-undeployed" in blob or "pinned" in blob.lower()
