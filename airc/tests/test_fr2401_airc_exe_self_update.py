"""FR #2401: frozen airc.exe kicks Sync/Update like Start-AircConsole -ServiceMode."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

SERVICE = ROOT / "airc/scripts/airc_console_service.py"
START = ROOT / "airc/scripts/Start-AircConsole.ps1"
UPD = ROOT / "common/scripts/Update-BobiverseService.ps1"
OPS = ROOT / "airc/docs/airc-ops.md"
THIS = Path(__file__)

MOJIBAKE_DASH = ("\u00e2" + "\u20ac")


def test_fr2401_frozen_host_wires_update_and_sync():
    text = SERVICE.read_text(encoding="utf-8")
    assert "kick_frozen_service_start_hooks" in text
    assert "is_frozen_airc_exe" in text
    assert "_MEIPASS" in text or "sys.frozen" in text or 'getattr(sys, "frozen"' in text
    assert "Update-BobiverseService.ps1" in text
    assert "Sync-BobiverseFromRepo.ps1" in text
    assert 'BOBIVERSE_NO_UPDATE' in text
    assert "-ServiceName" in text and "Airc" in text
    assert "kick_frozen_service_start_hooks()" in text
    # Only frozen path — legacy Start-AircConsole must not double-run via unguarded call
    assert "if not is_frozen_airc_exe()" in text or "if not is_frozen_airc_exe():" in text
    assert "args.selftest" in text
    # In main(): selftest returns before the hooks call
    main_idx = text.index("def main(")
    selftest_idx = text.index("if args.selftest", main_idx)
    hooks_call_idx = text.index("kick_frozen_service_start_hooks()", selftest_idx)
    assert selftest_idx < hooks_call_idx


def test_fr2401_legacy_start_still_has_service_mode_update():
    text = START.read_text(encoding="utf-8-sig")
    assert "Update-BobiverseService.ps1" in text
    assert "ServiceMode" in text
    assert UPD.is_file()


def test_fr2401_ops_doc_mentions_frozen_hooks():
    text = OPS.read_text(encoding="utf-8")
    assert "2401" in text
    assert "airc.exe" in text or "frozen" in text.lower()
    assert "Update-BobiverseService" in text


def test_fr2401_selftest_still_passes_unfrozen():
    env = {k: v for k, v in os.environ.items()}
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(ROOT / "airc" / "scripts"),
            str(ROOT / "common" / "scripts"),
            env.get("PYTHONPATH", ""),
        ]
    )
    r = subprocess.run(
        [sys.executable, str(SERVICE), "--selftest"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "selftest ok" in r.stdout
    # Unfrozen selftest must not invoke updater (hooks gated on frozen)
    assert "frozen self-update" not in r.stdout
    assert "frozen sync-from-repo" not in r.stdout


def test_fr2401_encoding_utf8_no_bom_no_mojibake():
    for path in (SERVICE, THIS):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
        assert raw.endswith(b"\n"), f"missing trailing newline in {path}"
        text = raw.decode("utf-8")
        assert "\ufeff" not in text
        if path != THIS:
            assert MOJIBAKE_DASH not in text, f"mojibake in {path}"
