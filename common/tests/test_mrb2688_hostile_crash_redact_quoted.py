"""Hostile MRB #2688: multi-word quoted JSON redact edges + Py/C# parity (FR #2679)."""
from __future__ import annotations

import crash_report
from repo_layout import resolve


def test_mrb2688_two_multiword_secrets_same_blob():
    raw = '{"password": "one two", "token": "three four five"}'
    out = crash_report.redact(raw)
    for bad in ("one two", "two", "three four five", "four five", "three"):
        assert bad not in out, (bad, out)
    assert out.count("<redacted>") >= 2


def test_mrb2688_empty_quoted_value():
    out = crash_report.redact('{"password": ""}')
    assert "password=<redacted>" in out


def test_mrb2688_xai_and_gh_token_quoted_multiword():
    out = crash_report.redact(
        '{"XAI_API_KEY": "sk fake parts", "GH_TOKEN": "ghp more bits"}'
    )
    assert "sk fake parts" not in out
    assert "ghp more bits" not in out
    assert "fake parts" not in out
    assert "<redacted>" in out


def test_mrb2688_bare_password_eq_does_not_eat_next_field():
    out = crash_report.redact("password=onlyToken keep=this")
    assert "onlyToken" not in out
    assert "keep=this" in out


def test_mrb2688_csharp_quoted_alternate_before_bare():
    """SecretKvRe must list full quoted value before bare token class (FR #2679)."""
    text = resolve("bob/tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")
    assert "2679" in text
    quoted = '""[^""]*""'
    bare = '[^\\s"",}]+'
    assert quoted in text
    assert bare in text
    assert text.find(quoted) < text.find(bare)


def test_mrb2688_python_secret_kv_quoted_before_bare():
    src = resolve("common/scripts/crash_report.py").read_text(encoding="utf-8")
    assert "2679" in src
    assert '(?:"[^"]*"|' in src
    assert src.find('"[^"]*"') < src.find('[^\\s",}]+')


def test_mrb2688_worker_skill_mentions_multiword_quoted():
    skill = resolve("bob/.grok/skills/bobiverse-bob-worker/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "2679" in skill
    assert "multi-word" in skill.lower()
