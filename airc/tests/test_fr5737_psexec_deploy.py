"""FR #5737: airc deploys PsExec at install (pinned hash); LEGION offline ensure/plan."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import airc_legion as lg
import airc_network_installer.install as inst
import airc_network_installer.psexec_deploy as dep
from repo_layout import ROOT

PIN = ROOT / "airc/scripts/airc_network_installer/psexec_pin.json"
DEPLOY_PS = ROOT / "airc/scripts/Deploy-AircPsExec.ps1"
INSTALL_PS = ROOT / "airc/scripts/Install-Airc.ps1"
UPDATE_PS = ROOT / "common/scripts/Update-BobiverseService.ps1"
SKILL_C = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"
SKILL_T = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fake_zip_and_pin(tmp_path: Path, monkeypatch) -> tuple[Path, bytes, dict[str, str]]:
    """Build a tiny zip containing PsExec.exe; pin hashes to match."""
    exe_bytes = b"MZ-FAKE-PSEXEC-" + b"5737" * 8
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("PsExec.exe", exe_bytes)
    zip_bytes = buf.getvalue()
    pin = {
        "zip_url": "https://example.invalid/PSTools.zip",
        "zip_sha256": _sha(zip_bytes),
        "psexec_sha256": _sha(exe_bytes),
    }
    monkeypatch.setattr(dep, "load_psexec_pin", lambda: dict(pin))
    monkeypatch.setattr(inst, "load_psexec_pin", lambda: dict(pin))
    zpath = tmp_path / "PSTools.zip"
    zpath.write_bytes(zip_bytes)
    tools = tmp_path / "tools"
    monkeypatch.setenv("ProgramData", str(tmp_path / "pd"))
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tools / "PsExec.exe"))
    monkeypatch.delenv("AIRC_NO_PSEXEC_DEPLOY", raising=False)
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)
    return zpath, exe_bytes, pin


def test_fr5737_pin_file_present():
    raw = json.loads(PIN.read_text(encoding="utf-8"))
    assert raw["zip_url"].startswith("https://download.sysinternals.com/")
    assert len(raw["zip_sha256"]) == 64
    assert len(raw["psexec_sha256"]) == 64
    assert "redistribut" in raw["note"].lower() or "license" in raw["note"].lower()
    assert not PIN.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr5737_deploy_from_zip_no_network(tmp_path, monkeypatch):
    zpath, exe_bytes, _pin = _fake_zip_and_pin(tmp_path, monkeypatch)

    def boom(*_a, **_k):
        raise AssertionError("network download must not run when zip_path given")

    hit = dep.deploy_psexec(
        zip_path=zpath,
        allow_network=True,
        urlretrieve=boom,
    )
    assert hit["ok"] is True
    dest = Path(hit["path"])
    assert dest.is_file()
    assert dest.read_bytes() == exe_bytes
    assert dep.psexec_hash_ok(dest, expected=_sha(exe_bytes))
    cache = Path(hit["cache"])
    assert cache.is_file()
    assert dep.cache_zip_ok(cache, expected=_sha(zpath.read_bytes()))


def test_fr5737_ensure_redeploys_on_hash_mismatch_no_network(tmp_path, monkeypatch):
    zpath, exe_bytes, pin = _fake_zip_and_pin(tmp_path, monkeypatch)
    hit = dep.deploy_psexec(zip_path=zpath, allow_network=False)
    assert hit["ok"]
    dest = Path(hit["path"])
    # Corrupt the deployed exe
    dest.write_bytes(b"CORRUPT")
    assert not dep.psexec_hash_ok(dest, expected=pin["psexec_sha256"])

    def boom(*_a, **_k):
        raise AssertionError("ensure must not hit the network")

    monkeypatch.setattr("urllib.request.urlretrieve", boom)
    path = dep.ensure_psexec("")
    assert path
    assert Path(path).read_bytes() == exe_bytes


def test_fr5737_plan_deployed_and_undeployed(tmp_path, monkeypatch):
    zpath, _exe, _pin = _fake_zip_and_pin(tmp_path, monkeypatch)
    plan = dep.plan_psexec("")
    assert plan["state"] == "undeployed"
    dep.deploy_psexec(zip_path=zpath, allow_network=False)
    plan2 = dep.plan_psexec("")
    assert plan2["state"] == "deployed"
    Path(plan2["path"]).unlink()
    plan3 = dep.plan_psexec("")
    assert plan3["state"] == "would-redeploy"


def test_fr5737_ensure_ignores_path_copy(tmp_path, monkeypatch):
    zpath, exe_bytes, _pin = _fake_zip_and_pin(tmp_path, monkeypatch)
    # PATH has a decoy; airc deploy is authoritative.
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    decoy_exe = decoy / "PsExec.exe"
    decoy_exe.write_bytes(b"DECOY")
    import os
    monkeypatch.setenv("PATH", str(decoy) + ";" + (os.environ.get("PATH") or ""))
    path = dep.ensure_psexec("")
    assert path is None  # undeployed
    dep.deploy_psexec(zip_path=zpath, allow_network=False)
    path2 = dep.ensure_psexec("")
    assert path2 and Path(path2).read_bytes() == exe_bytes
    assert Path(path2).resolve() != decoy_exe.resolve()


def test_fr5737_whatif_ok_when_deployed(tmp_path, monkeypatch):
    zpath, _exe, _pin = _fake_zip_and_pin(tmp_path, monkeypatch)
    dep.deploy_psexec(zip_path=zpath, allow_network=False)
    monkeypatch.setattr(inst, "plan_psexec", dep.plan_psexec)
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
    assert out.get("error") not in ("psexec-missing", "psexec-undeployed")


def test_fr5737_whatif_undeployed_fails(tmp_path, monkeypatch):
    _fake_zip_and_pin(tmp_path, monkeypatch)
    monkeypatch.setattr(inst, "plan_psexec", dep.plan_psexec)
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


def test_fr5737_live_ensure_no_urlretrieve(tmp_path, monkeypatch):
    zpath, exe_bytes, _pin = _fake_zip_and_pin(tmp_path, monkeypatch)
    dep.deploy_psexec(zip_path=zpath, allow_network=False)

    def boom(*_a, **_k):
        raise AssertionError("urlretrieve")

    monkeypatch.setattr("urllib.request.urlretrieve", boom)
    path = dep.ensure_psexec("")
    assert path and Path(path).read_bytes() == exe_bytes
    # corrupt + redeploy still offline
    Path(path).write_bytes(b"x")
    path2 = dep.ensure_psexec("")
    assert path2 and Path(path2).read_bytes() == exe_bytes


def test_fr5737_install_and_update_hooks():
    inst_txt = INSTALL_PS.read_text(encoding="utf-8")
    assert "FR #5737" in inst_txt
    assert "Deploy-AircPsExec.ps1" in inst_txt
    upd = UPDATE_PS.read_text(encoding="utf-8")
    assert "FR #5737" in upd
    assert "Deploy-AircPsExec" in upd
    assert DEPLOY_PS.is_file()
    deploy_txt = DEPLOY_PS.read_text(encoding="utf-8")
    assert "icacls" in deploy_txt
    assert "SYSTEM" in deploy_txt and "Administrators" in deploy_txt
    # -accepteula is on the LEGION run argv (install.py), not the deploy script.
    install_py = (ROOT / "airc/scripts/airc_network_installer/install.py").read_text(
        encoding="utf-8"
    )
    assert "-accepteula" in install_py


def test_fr5737_skills_document():
    blob = SKILL_C.read_text(encoding="utf-8") + "\n" + SKILL_T.read_text(encoding="utf-8")
    assert "5737" in blob
    assert "psexec-undeployed" in blob or "install-time" in blob.lower() or "pinned" in blob.lower()
