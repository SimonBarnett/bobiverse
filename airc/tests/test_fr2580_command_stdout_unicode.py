"""FR #2580: airc Command StdOut preserves non-ASCII (Greek/CJK).

Redirected powershell.exe defaults $OutputEncoding to ASCII, which best-fits
α→a / CJK→? before airc decodes stdout as UTF-8 (U+FFFD). Live MarchHare
evidence: StdOut hex 55-4E-49-3D-61-EF-BF-BD-3F-3F-0A for UNI=αβ世界.
"""
from __future__ import annotations

import os
import shutil

import pytest

import airc_console as ac


pytestmark = pytest.mark.skipif(
    os.name != "nt" or not shutil.which("powershell.exe"),
    reason="FR #2580 requires Windows PowerShell",
)

UNI_SCRIPT = (
    "$s = [string]([char]0x03B1+[char]0x03B2+[char]0x4E16+[char]0x754C); "
    'Write-Output ("UNI=$s")'
)
EXPECTED = "UNI=αβ世界"


def test_plain_ps_stdout_preserves_greek_and_cjk():
    req = ac.parse_shell_request(UNI_SCRIPT)
    out = ac.run_shell_request(req, timeout_s=45)
    assert out.exit_code == 0
    lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    assert EXPECTED in lines, repr(out.stdout)


def test_format_shell_replies_preserves_unicode_in_out_body():
    req = ac.parse_shell_request(UNI_SCRIPT)
    out = ac.run_shell_request(req, timeout_s=45)
    records = ac.format_shell_replies(out)
    bodies = [
        r.split(" ", 3)[-1]
        for r in records
        if r.startswith(f"out id={out.job_id} ")
    ]
    joined = "".join(bodies)
    assert EXPECTED in joined, repr(bodies)
    assert "\ufffd" not in joined
    assert records[-1] == f"DONE id={out.job_id} exit=0"


def test_encode_ps_sets_utf8_output_encoding_preamble():
    """EncodedCommand payload must force UTF-8 stdout before user script."""
    enc = ac.encode_ps_encoded_command("Write-Output hi")
    import base64

    raw = base64.b64decode(enc)
    text = raw.decode("utf-16-le")
    assert "UTF8Encoding" in text
    assert "$OutputEncoding" in text
    assert "Write-Output hi" in text


def test_psb64_utf16_payload_also_gets_utf8_stdout_wrap():
    import base64

    payload = base64.b64encode(UNI_SCRIPT.encode("utf-16-le")).decode("ascii")
    req = ac.parse_shell_request("psb64:" + payload)
    out = ac.run_shell_request(req, timeout_s=45)
    assert out.exit_code == 0
    assert EXPECTED in out.stdout
    assert "\ufffd" not in out.stdout
