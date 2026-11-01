"""FR #5743: PsExec extract must not SameFileError when zip member == dest basename."""
from __future__ import annotations

import hashlib
import io
import shutil
import zipfile
from pathlib import Path

import airc_legion as lg
import airc_network_installer.install as inst
import airc_network_installer.psexec_deploy as dep
from repo_layout import ROOT

DEPLOY = ROOT / "airc/scripts/airc_network_installer/psexec_deploy.py"
LEGION = ROOT / "airc/scripts/airc_legion.py"
SKILL_T = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_with_member(member: str, payload: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, payload)
    return buf.getvalue()


def test_fr5743_extract_member_equals_dest_basename(tmp_path):
    """Real PSTools.zip layout: member name is exactly PsExec.exe (== dest.name)."""
    exe = b"MZ-FAKE-5743-" + b"X" * 32
    zpath = tmp_path / "PSTools.zip"
    zpath.write_bytes(_zip_with_member("PsExec.exe", exe))
    dest = tmp_path / "tools" / "PsExec.exe"
    out = dep.extract_psexec_from_zip(zpath, dest)
    assert out == dest
    assert dest.is_file()
    assert dest.read_bytes() == exe


def test_fr5743_extract_skips_copy_when_src_is_dest(tmp_path):
    """Belt: production extract survives when dest already holds the member bytes."""
    exe = b"MZ-ALREADY-ON-DEST"
    dest = tmp_path / "tools" / "PsExec.exe"
    dest.parent.mkdir(parents=True, exist_ok=True)
    zpath = tmp_path / "PSTools.zip"
    zpath.write_bytes(_zip_with_member("PsExec.exe", exe))
    # Old bug shape: member extracted straight into dest.parent (== dest).
    with zipfile.ZipFile(zpath, "r") as zf:
        zf.extract("PsExec.exe", dest.parent)
    assert dest.is_file()
    # Production helper uses a temp dir + same-path skip; must not raise.
    out = dep.extract_psexec_from_zip(zpath, dest)
    assert out == dest
    assert dest.read_bytes() == exe


def test_fr5743_ensure_result_surfaces_samefile(tmp_path, monkeypatch):
    monkeypatch.setenv("ProgramData", str(tmp_path / "pd"))
    monkeypatch.setenv("AIRC_PSEXEC_PATH", str(tmp_path / "tools" / "PsExec.exe"))
    monkeypatch.delenv("AIRC_NO_PSEXEC_DEPLOY", raising=False)
    monkeypatch.delenv("AIRC_LEGION_NO_PSEXEC_DOWNLOAD", raising=False)

    # Valid cache so redeploy is attempted.
    exe = b"MZ-5743"
    zbytes = _zip_with_member("PsExec.exe", exe)
    pin = {
        "zip_url": "https://example.invalid/PSTools.zip",
        "zip_sha256": _sha(zbytes),
        "psexec_sha256": _sha(exe),
    }
    monkeypatch.setattr(dep, "load_psexec_pin", lambda: dict(pin))
    cache = dep.cache_zip_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(zbytes)

    def boom(*_a, **_k):
        raise shutil.SameFileError("PsExec.exe")

    monkeypatch.setattr(dep, "extract_psexec_from_zip", boom)
    hit = dep.ensure_psexec_result("")
    assert hit["ok"] is False
    assert hit["error"] == "psexec-download-failed:SameFileError"
    assert dep.ensure_psexec("") is None


def test_fr5743_legion_live_surfaces_download_failed(monkeypatch, tmp_path):
    msi = tmp_path / "Airc-9.9.9.msi"
    msi.write_bytes(b"MZ")

    monkeypatch.setattr(
        lg,
        "_resolve_legion_msi_path",
        lambda spec: msi,
    )
    monkeypatch.setattr(
        inst,
        "ensure_psexec_result",
        lambda explicit="", dest=None: {
            "ok": False,
            "path": "",
            "error": "psexec-download-failed:SameFileError",
        },
    )
    # Back-compat wrapper still imported in some paths
    monkeypatch.setattr(inst, "ensure_psexec", lambda explicit="", dest=None: None)

    out = lg.default_installer_run(
        {
            "hosts": ["flamingo"],
            "dry_run": False,
            "profile": "client",
            "force": False,
            "timeout_s": 30,
            "msi": str(msi),
        }
    )
    assert out["ok"] is False
    assert out["error"] == "psexec-download-failed:SameFileError"
    assert any(
        f.get("error") == "psexec-download-failed:SameFileError"
        for f in (out.get("failures") or [])
    )


def test_fr5743_code_and_docs():
    blob = DEPLOY.read_text(encoding="utf-8")
    assert "def ensure_psexec_result" in blob
    assert "psexec-download-failed" in blob
    assert "SameFileError" in blob or "src.resolve() == dest.resolve()" in blob
    assert "5743" in blob
    leg = LEGION.read_text(encoding="utf-8")
    assert "ensure_psexec_result" in leg or "psexec-download-failed" in leg
    skill = SKILL_T.read_text(encoding="utf-8")
    assert "5743" in skill or "psexec-download-failed" in skill
    assert not DEPLOY.read_bytes().startswith(b"\xef\xbb\xbf")
