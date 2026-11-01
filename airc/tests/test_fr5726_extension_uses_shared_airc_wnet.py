"""FR #5726: EXTENSION must use shared airc_wnet (no duplicate ctypes block)."""
from __future__ import annotations

from pathlib import Path

import airc_extension as ex
import airc_wnet

ROOT = Path(__file__).resolve().parents[2]


def test_fr5726_extension_reexports_shared_wnet():
    assert ex.wnet_add_ipc is airc_wnet.wnet_add_ipc
    assert ex.wnet_cancel is airc_wnet.wnet_cancel
    # is_ipc_auth_failed wraps is_access_denied + is_wnet_auth_failed
    assert ex.is_ipc_auth_failed(OSError(1326, "Logon failure")) is True
    assert ex.is_ipc_auth_failed(OSError(53, "The network path was not found")) is False


def test_fr5726_no_duplicate_ctypes_netresource_in_extension():
    src = (ROOT / "airc" / "scripts" / "airc_extension.py").read_text(encoding="utf-8")
    assert "class NETRESOURCEW" not in src
    assert "WinDLL(\"mpr\"" not in src and "WinDLL('mpr'" not in src
    assert "from airc_wnet import" in src
