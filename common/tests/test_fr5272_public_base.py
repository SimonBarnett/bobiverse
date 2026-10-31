"""FR #5272: bob.ntsa.uk public webhook base; IRC host stays irc.ntsa.uk."""
from __future__ import annotations

from pathlib import Path

import bob_public_base as bpb
import bobreport
import chair_health as ch
import crash_report
import copilot_dispatch as cd
from repo_layout import ROOT


def test_default_public_base_is_bob():
    assert bpb.public_base({}) == "https://bob.ntsa.uk"
    assert bpb.default_digest_url({}) == "https://bob.ntsa.uk/bob/v1/report"
    assert bpb.default_intake_url({}) == "https://bob.ntsa.uk/bob/v1/intake"
    assert bpb.default_git_hook_url({}) == "https://bob.ntsa.uk/bob/v1/git"


def test_public_base_env_override(monkeypatch):
    monkeypatch.setenv("BOB_PUBLIC_BASE", "https://example.test/")
    monkeypatch.delenv("BOB_DIGEST_URL", raising=False)
    assert bpb.public_base() == "https://example.test"
    assert bpb.public_url("/bob/v1/report") == "https://example.test/bob/v1/report"
    assert bobreport.digest_url() == "https://example.test/bob/v1/report"
    monkeypatch.setenv("BOB_DIGEST_URL", "https://override.example/bob/v1/report")
    assert bobreport.digest_url() == "https://override.example/bob/v1/report"
    monkeypatch.delenv("BOB_DIGEST_URL", raising=False)
    monkeypatch.setenv("BOB_PUBLIC_BASE", "https://bob.ntsa.uk")
    assert ch.targets()["public"] == "https://bob.ntsa.uk"
    monkeypatch.setenv("BOB_PUBLIC_BASE", "https://probe.example")
    assert ch.targets()["public"] == "https://probe.example"


def test_module_defaults_use_bob_host():
    assert bobreport.DEFAULT_DIGEST_URL == "https://bob.ntsa.uk/bob/v1/report"
    assert crash_report.DEFAULT_INTAKE == "https://bob.ntsa.uk/bob/v1/intake"
    assert ch.PUBLIC_BASE == "https://bob.ntsa.uk"
    assert cd.GIT_HOOK_URL == "https://bob.ntsa.uk/bob/v1/git"


def test_irc_host_defaults_remain_irc():
    assert bpb.DEFAULT_IRC_HOST == "irc.ntsa.uk"
    irc_agent = (ROOT / "common/scripts/irc_agent.py").read_text(encoding="utf-8")
    assert 'default="irc.ntsa.uk"' in irc_agent or "default=\"irc.ntsa.uk\"" in irc_agent
    airc = (ROOT / "airc/scripts/airc_console_service.py").read_text(encoding="utf-8")
    assert "irc.ntsa.uk" in airc
    # no webhook HTTP URL may still use the IRC hostname
    bad = "https://" + "irc.ntsa.uk" + "/bob"
    bad_http = "http://" + "irc.ntsa.uk" + "/bob"
    here = Path(__file__).resolve()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == here:
            continue
        if path.suffix.lower() not in {".py", ".ps1", ".md", ".json", ".yml", ".yaml", ".txt"}:
            continue
        if ".git" in path.parts or "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        assert bad not in text, path
        assert bad_http not in text, path


def test_upgrade_note_documents_bob_public_base():
    text = (ROOT / "common/docs/post-install.md").read_text(encoding="utf-8")
    assert "bob.ntsa.uk" in text
    assert "BOB_PUBLIC_BASE" in text or "reportUrl" in text
