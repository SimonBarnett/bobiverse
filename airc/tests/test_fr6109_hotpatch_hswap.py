"""FR #6109: hotpatch verify must not alias $t/$T; HSwap prunes leftover pack files."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

VERIFY = ROOT / "airc/scripts/Invoke-AircHotpatchVerify.ps1"
HSWAP = ROOT / "airc/scripts/Invoke-AircPriorityHSwap.ps1"


def test_fr6109_scripts_exist_utf8_no_bom():
    assert VERIFY.is_file(), VERIFY
    assert HSWAP.is_file(), HSWAP
    for path in (VERIFY, HSWAP):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        text = raw.decode("utf-8")
        assert "FR #6109" in text


def test_fr6109_verify_does_not_reuse_t_casefold():
    text = VERIFY.read_text(encoding="utf-8")
    # PowerShell $t and $T are the same variable. Cleanup must not Remove-Item the file text.
    assigns = re.findall(r"(?im)\$t\s*=", text)
    assert assigns == [], "do not use $t/$T; they collide (file text vs temp path)"
    assert "Remove-Item" in text
    assert "$VerifyTempDir" in text
    assert "$VerifyText" in text
    assert re.search(r"Remove-Item[^\n]*\$VerifyTempDir", text)


def test_fr6109_hswap_prunes_removed_sdk(tmp_path):
    pack = tmp_path / "pack" / "priority-worker"
    dest = tmp_path / "dest" / "priority-worker"
    (pack / "owned.txt").parent.mkdir(parents=True)
    (pack / "owned.txt").write_text("pack\n", encoding="utf-8")
    leftover = dest / "sdk" / "priority-web-sdk" / "index.js"
    leftover.parent.mkdir(parents=True)
    leftover.write_text("stale vendor\n", encoding="utf-8")
    (dest / "owned.txt").parent.mkdir(parents=True, exist_ok=True)
    (dest / "owned.txt").write_text("old\n", encoding="utf-8")
    cmd = [
        "powershell",
        "-NoProfile",
        "-File",
        str(HSWAP),
        "-PackRoot",
        str(pack),
        "-TargetRoot",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (dest / "owned.txt").read_text(encoding="utf-8") == "pack\n"
    assert not leftover.exists()
    assert not (dest / "sdk" / "priority-web-sdk").exists()


def test_fr6109_verify_cleanup_uses_temp_not_text(tmp_path):
    probe = tmp_path / "probe.txt"
    probe.write_text("not-a-path\n", encoding="utf-8")
    cmd = [
        "powershell",
        "-NoProfile",
        "-File",
        str(VERIFY),
        "-ProbeFile",
        str(probe),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert probe.is_file(), "cleanup must not Remove-Item the probe file text"
    assert "verify-ok" in (proc.stdout or "")
