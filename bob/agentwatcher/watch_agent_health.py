"""Native Watch-AgentHealth launcher source.
The release ships this as Watch-AgentHealth.exe; the PowerShell file remains the
full, reviewable implementation and is passed through unchanged for compatibility.
"""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

def main() -> int:
    here = Path(__file__).resolve().parent
    script = here / "Watch-AgentHealth.ps1"
    if not script.exists():
        script = Path(os.environ.get("BOB_WATCH_AGENTHEALTH_PS1", str(script)))
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *sys.argv[1:]]
    return subprocess.call(cmd, cwd=str(here))
if __name__ == "__main__":
    raise SystemExit(main())
