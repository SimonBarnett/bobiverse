"""FR #7660: the warm engine shell imports a module once across steps."""
from __future__ import annotations

import subprocess
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "tray" / "tools" / "BobTrayWarmStep.ps1"


def test_fr7660_module_imports_once_and_second_step_is_fast(tmp_path: Path):
    mod = tmp_path / "src"
    mod.mkdir()
    (mod / "Warm.psm1").write_text(
        "$script:WarmImports = 1 + [int]$script:WarmImports\nfunction Get-WarmCount { $script:WarmImports }\n",
        encoding="ascii",
    )
    (mod / "BobBridge.psd1").write_text(
        "@{ RootModule = 'Warm.psm1'; ModuleVersion = '0.0.1'; FunctionsToExport = @('Get-WarmCount') }\n",
        encoding="ascii",
    )
    script = tmp_path / "run.ps1"
    script.write_text(
        "\n".join(
            [
                f". '{HELPER}'",
                f"$a = Invoke-BobTrayWarmEngineStep -Name 'one' -Root '{tmp_path}' -TimeoutSec 20 -Body {{ Get-WarmCount }}",
                f"$b = Invoke-BobTrayWarmEngineStep -Name 'two' -Root '{tmp_path}' -TimeoutSec 20 -Body {{ Get-WarmCount }}",
                "Write-Output ($a.ok.ToString() + '|' + $a.output + '|' + $b.ok.ToString() + '|' + $b.output + '|' + [int]$b.seconds)",
            ]
        ),
        encoding="ascii",
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    line = [ln for ln in r.stdout.splitlines() if "|" in ln][-1]
    ok1, n1, ok2, n2, sec = line.split("|")
    assert ok1 == "True" and ok2 == "True"
    assert n1.strip() == "1"
    assert n2.strip() == "1"
    assert int(sec) < 45
