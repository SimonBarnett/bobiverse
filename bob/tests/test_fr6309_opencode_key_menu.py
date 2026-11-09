"""FR #6309: TipForm masked OpenCode key set/select/remove + digest account clear."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[0]
DIALOGS = ROOT / "tray" / "dialogs"
TRAY_CS = DIALOGS / "BobTray.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
WRITE_PS1 = ROOT / "scripts" / "Write-BobOpencodeGoApiKey.ps1"
COMMON = REPO / "common" / "scripts"
sys.path.insert(0, str(COMMON))

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
PS = __import__("shutil").which("powershell.exe") or __import__("shutil").which("powershell")

# Never use realistic secret material (FR #3304).
FAKE_KEY_A = "FAKE_OPENCODE_KEY_PART_A" + "_PART_B"
FAKE_KEY_B = "FAKE_OPENCODE_KEY_ALT_A" + "_ALT_B"


@pytest.fixture(scope="module")
def dialogs(tmp_path_factory) -> Path:
    if not (WIN and CSC.is_file() and PS):
        pytest.skip("needs Windows + csc.exe + powershell")
    out = tmp_path_factory.mktemp("bobdlg6309")
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"),
            "-RepoRoot",
            str(REPO),
            "-OutDir",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return out


def test_fr6309_tray_source_has_opencode_keys_menu_and_masked_input():
    src = TRAY_CS.read_text(encoding="utf-8-sig")
    assert 'MenuItems.Add("OpenCode keys")' in src or '"OpenCode keys"' in src
    assert "PasswordChar" in src
    assert "opencode-keys" in src
    assert "selected.txt" in src
    assert "--opencode-key-write" in src
    assert "--opencode-key-select" in src
    assert "--opencode-key-remove" in src
    assert "class OpencodeKeysStore" in src
    store = src.split("class OpencodeKeysStore", 1)[1].split("class OpencodeKeyDialog", 1)[0]
    assert "WriteAllText(dest, key" in store
    assert "Write-Host" not in store
    assert "Console.Write(key" not in store


def test_fr6309_docs_mention_tipform_opencode_keys_menu():
    text = DOCS.read_text(encoding="utf-8")
    assert "OpenCode keys" in text
    assert "6309" in text or "FR #6309" in text


def test_fr6309_write_helper_still_masked():
    text = WRITE_PS1.read_text(encoding="utf-8")
    assert "Read-Host -AsSecureString" in text
    assert "SYSTEM" in text


def test_fr6309_peer_fuel_clears_stale_opencode_account():
    import bobreport

    peer = {
        "id": "flamingo",
        "online": True,
        "status": "operational",
        "weekly": 10,
        "weekly_known": True,
        "opencode_account": None,
        "opencode_windows": {
            "week": {"status": "unknown", "error": "no key set"},
        },
    }
    payload = bobreport.build_peer_fuel_merge_payload(peer, "flamingo")
    assert payload is not None
    assert "opencode_account" in payload
    assert payload.get("opencode_account") is None
    cleared = payload.get("cleared") or []
    assert "opencode_account" in cleared
    blob = json.dumps(payload)
    assert FAKE_KEY_A not in blob
    assert "apikey" not in blob.lower() or "opencode_account" in blob


@pytest.mark.skipif(os.name != "nt", reason="Windows tray headless helpers")
def test_fr6309_headless_write_select_remove_roundtrip(tmp_path, dialogs):
    """Headless tray flags write labelled keys without echoing material."""
    exe = dialogs / "bob-tray.exe"
    install = tmp_path / "bob"
    (install / "config").mkdir(parents=True)
    keyfile = tmp_path / "key.txt"
    keyfile.write_text(FAKE_KEY_A, encoding="utf-8")
    out = tmp_path / "out.txt"

    def run(*extra):
        cmd = [
            str(exe),
            "--root",
            str(install),
            "--no-engine",
            *extra,
            "--text-out",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (r.stdout or "") + (r.stderr or "") + out.read_text(encoding="utf-8") if out.exists() else ""
        return out.read_text(encoding="utf-8")

    body = run("--opencode-key-write", "--label", "work", "--key-file", str(keyfile))
    assert "ok=write" in body
    assert "label=work" in body
    assert FAKE_KEY_A not in body
    keys = install / "config" / "opencode-keys"
    assert (keys / "work.apikey").is_file()
    assert (keys / "selected.txt").read_text(encoding="utf-8").strip() == "work"
    stored = (keys / "work.apikey").read_text(encoding="utf-8").strip()
    assert stored == FAKE_KEY_A

    keyfile.write_text(FAKE_KEY_B, encoding="utf-8")
    body = run("--opencode-key-write", "--label", "personal", "--key-file", str(keyfile))
    assert "label=personal" in body
    body = run("--opencode-key-select", "--label", "work")
    assert "ok=select" in body
    assert (keys / "selected.txt").read_text(encoding="utf-8").strip() == "work"

    body = run("--opencode-key-remove", "--label", "work")
    assert "ok=remove" in body
    assert not (keys / "work.apikey").exists()
    # personal remains selected or selection cleared if was work — after remove work, select personal or clear
    sel = (keys / "selected.txt")
    if sel.exists():
        assert sel.read_text(encoding="utf-8").strip() in ("personal", "")

    body = run("--opencode-key-remove", "--label", "personal")
    assert "ok=remove" in body
    assert list(keys.glob("*.apikey")) == []
    # No keys left: selected cleared
    assert (not sel.exists()) or sel.read_text(encoding="utf-8").strip() == ""
