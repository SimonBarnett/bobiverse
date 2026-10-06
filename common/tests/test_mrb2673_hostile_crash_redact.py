"""MRB #2673 hostile: crash redact edge cases + stronger C# parity (FR #2668)."""
from __future__ import annotations

import re

import crash_report
from repo_layout import resolve


def test_mrb2673_authorization_equals_bearer_consumes_token():
    out = crash_report.redact("Authorization=Bearer FAKEeqTOKEN99")
    assert "FAKEeqTOKEN99" not in out
    assert "Bearer=<redacted>" in out or "<redacted>" in out


def test_mrb2673_bypass_not_matched_as_pass():
    raw = "bypass: keepme_visible"
    out = crash_report.redact(raw)
    assert "keepme_visible" in out
    assert out == raw or "bypass" in out


def test_mrb2673_multi_secret_line():
    raw = "Bearer AA99 and pass: BB88 and https://u:CC77@h/path"
    out = crash_report.redact(raw)
    for bad in ("AA99", "BB88", "CC77"):
        assert bad not in out, out


def test_mrb2673_json_key_with_spaces_around_colon():
    out = crash_report.redact('{"api_key" : "FAKEspacedKEY"}')
    assert "FAKEspacedKEY" not in out


def test_mrb2673_csharp_has_named_regex_fields():
    """Parity gate: C# must keep the FR #2668 named Regex fields, not only soft markers."""
    text = resolve("bob/tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")
    for name in ("AuthSchemeRe", "NickServRe", "IrcPassRe", "UrlUserinfoRe", "SecretKvRe"):
        assert name in text, f"missing {name}"
    assert re.search(r"Bearer\|Basic|Basic\|Bearer", text)
    assert "IDENTIFY" in text and "REGISTER" in text
    # third_party alias (if present) must not lag bob/tray
    alt = resolve("third_party/bob-tray/dialogs/CrashHook.cs")
    if alt.exists():
        assert "AuthSchemeRe" in alt.read_text(encoding="utf-8-sig")


def test_mrb2673_worker_skill_mentions_expanded_redact_shapes():
    skill = resolve("bob/.grok/skills/bobiverse-bob-worker/SKILL.md").read_text(encoding="utf-8")
    # After docs update: crash redact shapes include Bearer / NickServ, not only password=/token=
    low = skill.lower()
    assert "redact" in low or "password=" in low
    assert "bearer" in low or "nickserv" in low or "fr #2668" in low or "2668" in skill
