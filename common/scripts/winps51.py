"""FR #7315: Windows PowerShell 5.1 children must not inherit pwsh 7 PSModulePath."""
from __future__ import annotations

import os
from typing import Mapping, MutableMapping, Optional

WINPS51_MODULE_PATH = r"C:\Windows\System32\WindowsPowerShell\v1.0\Modules"


def apply_winps51_module_path(env: MutableMapping[str, str]) -> MutableMapping[str, str]:
    env["PSModulePath"] = WINPS51_MODULE_PATH
    return env


def env_for_powershell_exe(base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Env for ``powershell.exe`` (5.1): 5.1 Modules only so Get-FileHash resolves."""
    env = dict(os.environ if base is None else base)
    apply_winps51_module_path(env)
    return env
