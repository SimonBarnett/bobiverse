"""PyInstaller entry for airc-network-installer.exe (FR #3991)."""

from __future__ import annotations

from airc_network_installer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
