"""MRB #5751 hostile pins: EXTENSION DONE identity + credman_targets + identity_reason."""
from __future__ import annotations

from pathlib import Path

import airc_extension as ex
import airc_identity as ident
from repo_layout import ROOT

IDENT = ROOT / "airc" / "scripts" / "airc_identity.py"
EXT = ROOT / "airc" / "scripts" / "airc_extension.py"
CMD = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
TROUBLE = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"


def test_mrb5751_identity_module_has_credman_targets_and_reason():
    blob = IDENT.read_text(encoding="utf-8")
    assert "def configure_credman_targets" in blob
    assert "def credman_target_for" in blob
    assert "identity_reason" in blob
    assert "format_identity_fallback_log" in blob
    assert "5745" in blob
    assert b"\x07" not in IDENT.read_bytes()


def test_mrb5751_extension_deliver_done_suffix_wired():
    blob = EXT.read_text(encoding="utf-8")
    assert "done_identity_suffix" in blob or "_done_identity_suffix" in blob
    assert "identity_reason" in blob
    log = ex.build_extension_log(
        "install",
        whatif=False,
        hosts=[{"host": "X", "ok": True}],
        failures=[],
        gpo={"ok": True},
        fallback={"attempted": True, "host_count": 1},
        extra={"identity": "credman", "account": "WONDERLAND\\Admin"},
    )
    out = ex.deliver_extension_log(job_id="aabbccdd", log=log, offer=None)
    assert "identity=credman" in out["done"]
    assert "account=WONDERLAND\\Admin" in out["done"]


def test_mrb5751_skills_mention_5745_and_no_bel():
    cmd = CMD.read_text(encoding="utf-8")
    trouble = TROUBLE.read_text(encoding="utf-8")
    assert "5745" in cmd
    assert "credman_targets" in cmd
    assert "5745" in trouble
    assert "identity_reason" in trouble or "identity-fallback" in trouble
    assert "auth_failed" in trouble
    assert b"\x07" not in CMD.read_bytes()
    assert b"\x07" not in TROUBLE.read_bytes()


def test_mrb5751_credman_target_override_behaviour():
    ident.configure_credman_targets(
        {"credman_targets": {"extension": "PriorityAirc/CustomExt"}}
    )
    assert ident.credman_target_for("extension") == "PriorityAirc/CustomExt"
    ident.configure_credman_targets(None)
    assert ident.credman_target_for("extension") == "PriorityAirc/ExtensionAdmin"
