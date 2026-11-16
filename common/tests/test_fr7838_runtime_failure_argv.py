# -*- coding: utf-8 -*-
"""FR #7838: quoted WriteAllText errors must not be split into the failure site."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "scripts" / "Report-BobRuntimeFailure.ps1"
MSG = (
    'Exception calling "WriteAllText" with "2" argument(s): '
    '"There is not enough space on the disk."'
)


def test_fr7838_quoted_message_stays_intact_and_site_is_kept(tmp_path):
    shim = tmp_path / "python.cmd"
    out = tmp_path / "captured.txt"
    shim.write_text(
        textwrap.dedent(
            f"""\
            @echo off
            > "{out}" echo COMPONENT=%BOB_RF_COMPONENT%
            >> "{out}" echo SITE=%BOB_RF_SITE%
            >> "{out}" echo MESSAGE=%BOB_RF_MESSAGE%
            echo False deadbeef True
            """
        ),
        encoding="ascii",
    )
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env.get("PATH", "")
    for key in ("BOB_RF_COMPONENT", "BOB_RF_MESSAGE", "BOB_RF_SITE"):
        env.pop(key, None)
    script = textwrap.dedent(
        f"""
        . '{PS1}'
        $r = Report-BobRuntimeFailure -Component tray -Site 'Write-BobIrcStatus' -Exception @'
{MSG}
'@
        if ($env:BOB_RF_MESSAGE) {{ throw 'env leaked' }}
        Write-Output $r.via
        """
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "runtime_failure" in proc.stdout
    body = out.read_text(encoding="utf-8", errors="replace")
    assert "COMPONENT=tray" in body
    assert "SITE=Write-BobIrcStatus" in body
    assert "There is not enough space on the disk." in body
    assert "SITE=is" not in body
