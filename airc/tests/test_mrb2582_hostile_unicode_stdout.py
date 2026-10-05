"""MRB #2582 hostile: cmd chcp prefix + skill bullet contiguous + encode order."""
from __future__ import annotations

import base64

import airc_console as ac
from repo_layout import ROOT


def test_mrb2582_cmd_gets_chcp_65001_prefix():
    req = ac.parse_shell_request("cmd:echo hi")
    argv = ac.build_shell_argv(req)
    assert argv[-1].lower().startswith("chcp 65001")
    assert "echo hi" in argv[-1]


def test_mrb2582_cmd_existing_chcp_not_double_prefixed():
    req = ac.parse_shell_request("cmd:chcp 437>nul & echo hi")
    argv = ac.build_shell_argv(req)
    body = argv[-1].lower()
    assert body.count("chcp ") == 1
    assert body.startswith("chcp 437")


def test_mrb2582_skill_bullet_contiguous():
    skill = (ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md").read_text(
        encoding="utf-8-sig"
    )
    assert "Command StdOut Unicode (FR #2580)" in skill
    assert "$OutputEncoding" in skill
    assert "chcp 65001" in skill
    trouble = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_text(encoding="utf-8-sig")
    assert "FR #2580" in trouble
    assert "OutputEncoding" in trouble


def test_mrb2582_encode_preamble_before_user_script():
    enc = ac.encode_ps_encoded_command("Write-Output hi")
    text = base64.b64decode(enc).decode("utf-16-le")
    assert text.index("UTF8Encoding") < text.index("Write-Output hi")
    assert text.count("Write-Output hi") == 1
