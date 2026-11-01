"""FR #5745: EXTENSION DONE identity, airc.json credman_targets, identity_reason."""
from __future__ import annotations

import json
from pathlib import Path

import airc_extension as ex
import airc_identity as ident
import airc_legion as lg


FAKE_PW = "FAKE_fr5745_secret_not_real"


def test_fr5745_extension_deliver_done_carries_identity():
    log = ex.build_extension_log(
        "install",
        whatif=True,
        hosts=[{"host": "MARCHHARE", "ok": True, "auth": "credman"}],
        failures=[],
        gpo={"ok": True, "attempted": True},
        fallback={"attempted": True, "host_count": 1},
        extra={
            "identity": "credman",
            "identity_source": "credman",
            "account": "WONDERLAND\\Administrator",
            "identity_label": "credman (WONDERLAND\\Administrator)",
        },
    )
    assert log.get("identity") == "credman"
    assert log.get("account") == "WONDERLAND\\Administrator"
    out = ex.deliver_extension_log(job_id="4e600005", log=log, offer=None)
    assert "identity=credman" in out["done"]
    assert "account=WONDERLAND\\Administrator" in out["done"]
    assert FAKE_PW not in out["done"]


def test_fr5745_extension_log_from_payload_keeps_top_level_identity():
    payload = {
        "ok": True,
        "action": "install",
        "whatif": False,
        "identity": "system",
        "identity_label": "system (WONDERLAND\\MARCHHARE$)",
        "account": "WONDERLAND\\MARCHHARE$",
        "hosts": [{"host": "X", "ok": True}],
        "failures": [],
        "wrote_gpo": False,
        "gpo_reason": "gpo_step_skipped",
    }
    log = ex.extension_log_from_payload("install", payload=payload)
    assert log.get("identity") == "system"
    assert log.get("account") == "WONDERLAND\\MARCHHARE$"
    out = ex.deliver_extension_log(job_id="aabbccdd", log=log, offer=None)
    assert "identity=system" in out["done"]
    assert "account=WONDERLAND\\MARCHHARE$" in out["done"]


def test_fr5745_credman_targets_from_airc_json():
    ident.configure_credman_targets(None)
    assert ident.credman_target_for("legion") == "PriorityAirc/LegionAdmin"
    assert ident.credman_target_for("extension") == "PriorityAirc/ExtensionAdmin"
    assert ident.credman_target_for("network") == "PriorityAirc/NetworkAdmin"
    ident.configure_credman_targets(
        {
            "credman_targets": {
                "legion": "PriorityAirc/CustomLegion",
                "extension": "PriorityAirc/CustomExt",
                "network": "PriorityAirc/CustomNet",
            }
        }
    )
    assert ident.credman_target_for("legion") == "PriorityAirc/CustomLegion"
    assert ident.credman_target_for("EXTENSION") == "PriorityAirc/CustomExt"
    assert ident.credman_target_for("network") == "PriorityAirc/CustomNet"
    # Override wins.
    assert (
        ident.credman_target_for("legion", override="PriorityAirc/Override")
        == "PriorityAirc/Override"
    )
    ident.configure_credman_targets(None)


def test_fr5745_identity_reason_credman_missing(monkeypatch):
    monkeypatch.setattr(ident, "default_credman_reader", lambda t: {})
    got = ident.resolve_remote_identity(
        verb="legion",
        credman_target="PriorityAirc/LegionAdmin",
        system_fn=lambda: {
            "account": "WONDERLAND\\HOST$",
            "username": "WONDERLAND\\HOST$",
            "password": "",
        },
    )
    assert got.source == "system"
    assert got.credman_missing is True
    pub = got.public_dict()
    assert pub["identity_reason"] == "credman-missing:PriorityAirc/LegionAdmin"
    line = ident.format_identity_fallback_log(verb="legion", resolved=got)
    assert line is not None
    assert line.startswith("identity-fallback ")
    assert "credman-missing:PriorityAirc/LegionAdmin" in line
    assert "identity=system" in line
    assert FAKE_PW not in line


def test_fr5745_identity_reason_credman_read_error(monkeypatch):
    monkeypatch.setattr(
        ident, "default_credman_reader", lambda t: {"__error__": "WinError-5"}
    )
    got = ident.resolve_remote_identity(verb="extension")
    assert got.source == "system"
    assert got.public_dict()["identity_reason"] == "credman-read-error:WinError-5"


def test_fr5745_legion_body_includes_identity_reason(monkeypatch):
    monkeypatch.setattr(ident, "default_credman_reader", lambda t: {})
    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda spec: {"ok": True, "status": "ok"},
    )
    assert body.get("identity") == "system"
    assert body.get("credman_missing") is True
    assert str(body.get("identity_reason") or "").startswith("credman-missing:")


def test_fr5745_docs_mention_credman_targets_and_5745():
    root = Path(ex.__file__).resolve().parents[1]
    docs = (root / "docs/airc-remote-control.md").read_text(encoding="utf-8")
    skill = (root / ".grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "credman_targets" in docs or "FR #5745" in docs
    assert "FR #5745" in skill or "credman_targets" in skill
