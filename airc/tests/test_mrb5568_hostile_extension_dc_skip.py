"""MRB #5568 hostile pins: EXTENSION status read-only + ADSI DC skip (FR #5538)."""
from __future__ import annotations

import airc_extension as ex
from repo_layout import ROOT


def test_mrb5568_default_dc_hostnames_is_adsi():
    src = (ROOT / "airc" / "scripts" / "airc_extension.py").read_text(encoding="utf-8")
    start = src.index("def default_dc_hostnames")
    end = src.index("\ndef force_install_value", start)
    body = src[start:end]
    assert "adsisearcher" in body
    assert "8192" in body
    assert "subprocess.run" in body


def test_mrb5568_writes_gate_and_forcelist_helpers():
    assert ex.next_forcelist_name(["1"], ["other;https://x"], "abc") == "2"
    assert ex.next_forcelist_name(["1"], ["abc;https://x"], "abc") is None
    writes: list = []
    body = ex.fill_holes_work(
        "status",
        ldap_enum=lambda: ["pc1"],
        ping_host=lambda _h: True,
        apply_force_install=lambda *a: writes.append(a),
        whatif=False,
    )
    assert writes == []
    assert body["wrote_registry"] is False
    assert body["hosts"][0].get("skipped") == "status"


def test_mrb5568_install_skips_dc_before_write():
    writes: list = []
    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["dc1"],
        ping_host=lambda _h: True,
        apply_force_install=lambda *a: writes.append(a),
        is_dc=lambda _h: True,
        whatif=False,
    )
    assert writes == []
    assert body["hosts"][0].get("skipped") == "dc"


def test_mrb5568_skill_cites_5538():
    skill = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "5538" in skill
    assert "read-only" in skill.lower() or "status" in skill.lower()
