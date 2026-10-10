"""Hostile pins for MRB #3869 / FR #3863 airc upgrade SASL (docs/mrb-3869)."""
from __future__ import annotations

from pathlib import Path

import airc_console_service as svc
from repo_layout import ROOT

SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def make(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        [
            "--machine",
            "walrus",
            "--home",
            str(tmp_path),
            "--shop-mode",
            "registered",
            "--operators",
            "op",
        ]
    )
    s = svc.AircConsoleService(args)
    s.sent = []
    s.send = lambda line: s.sent.append(line)  # type: ignore[assignment]
    s.logs = []
    monkeypatch.setattr(svc, "info", lambda m: s.logs.append(m))
    return s


def test_mrb3869_hostile_marker_alone_still_known(tmp_path, monkeypatch):
    """Existing nickserv-ok keeps account known even if mint flag is weird."""
    (tmp_path / "console.password").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    (tmp_path / "console.nickserv-ok").write_text("prior\n", encoding="ascii")
    s = make(tmp_path, monkeypatch)
    assert s._nickserv_account_known()
    s.handshake()
    assert any(l.startswith("CAP REQ :") and "sasl" in l for l in s.sent), s.sent


def test_mrb3869_hostile_empty_password_file_mints_and_skips(tmp_path, monkeypatch):
    """Whitespace-only console.password is not a reuse — mint + FR #3763 skip."""
    (tmp_path / "console.password").write_text("   \n", encoding="utf-8")
    s = make(tmp_path, monkeypatch)
    assert getattr(s, "_nickserv_pw_minted", False)
    assert not s._nickserv_account_known()
    s.handshake()
    assert any("skip SASL" in m and "FR #3763" in m for m in s.logs), s.logs


def test_mrb3869_hostile_contiguous_source_and_skill_phrases():
    text = SERVICE.read_text(encoding="utf-8")
    assert "_nickserv_pw_minted = bool(self.nickserv_password) and not pw_existed" in text
    assert "INFO FR #3863 try SASL: console.password reused" in text
    assert "reused console.password (not minted this run) also counts" in text
    skill = SKILL.read_text(encoding="utf-8")
    assert "Upgrade 0.1.28→0.1.29+ : `skip SASL` then `433 reserved` loop (FR #3863)" in skill
    assert "Tip treats reused GUID as account-known and tries SASL" in skill
    # no BOM on skill
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
