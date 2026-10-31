"""FR #5291: EXTENSION GPO ForceInstall Chrome+Edge via DC (Priority web FR-B)."""
from __future__ import annotations

import json

import airc_console as ac
import airc_extension as ex
from airc_auth_helpers import ops_auth
from repo_layout import ROOT


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_fr5291_locked_defaults():
    assert ex.DEFAULT_EXTENSION_ID == "cgmpadejahkaggjpffnhaoiafbnicgpa"
    assert ex.DEFAULT_UPDATE_URL == "https://clients2.google.com/service/update2/crx"
    assert ex.DEFAULT_GPO_NAME == "Priority-web-extension"
    assert ex.DEFAULT_GPO_NAME != "Airc-Priority-Web-Extension"
    assert ex.FORCE_INSTALL_ENTRY == (
        "cgmpadejahkaggjpffnhaoiafbnicgpa;https://clients2.google.com/service/update2/crx"
    )
    assert ex.gpo_script_path().is_file()
    assert ex.gpo_script_path().name == "Invoke-AircExtensionGpo.ps1"


def test_fr5291_no_dc_fail_closed():
    def runner(**_kw):
        return {
            "ok": False,
            "gpo": "fail",
            "reason": "no_dc",
            "wrote_gpo": False,
            "browsers": [],
            "policy_names": [],
        }

    body = ex.run_extension_gpo_work("install", whatif=False, runner=runner)
    assert body["ok"] is False
    assert body["gpo"] == "fail"
    assert body["reason"] == "no_dc"
    assert body.get("wrote_gpo") is False
    assert body.get("wrote_registry") is False


def test_fr5291_whatif_never_writes():
    seen = {}

    def runner(**kw):
        seen.update(kw)
        return {
            "ok": True,
            "gpo": "absent",
            "reason": "whatif_plan",
            "wrote_gpo": False,
            "browsers": ["chrome", "edge"],
            "policy_names": [ex.DEFAULT_GPO_NAME],
            "would_set": ex.FORCE_INSTALL_ENTRY,
        }

    body = ex.run_extension_gpo_work("install", whatif=True, runner=runner)
    assert seen.get("whatif") is True
    assert body["wrote_gpo"] is False
    assert body.get("wrote_registry") is False
    assert "chrome" in body["browsers"] and "edge" in body["browsers"]
    assert ex.DEFAULT_GPO_NAME in body["policy_names"]


def test_fr5291_success_chrome_and_edge_gpo_ok():
    def runner(**_kw):
        return {
            "ok": True,
            "gpo": "ok",
            "reason": "prepared",
            "wrote_gpo": True,
            "browsers": ["chrome", "edge"],
            "policy_names": ["Priority-web-extension"],
            "force_install_written": ex.FORCE_INSTALL_ENTRY,
            "dc": "WALRUS.wonderland.local",
        }

    body = ex.run_extension_gpo_work("install", runner=runner)
    assert body["ok"] is True
    assert body["gpo"] == "ok"
    assert body["wrote_gpo"] is True
    assert set(body["browsers"]) == {"chrome", "edge"}
    assert body["policy_names"] == ["Priority-web-extension"]
    assert ex.DEFAULT_EXTENSION_ID in body["force_install_written"]
    blob = json.dumps(body).lower()
    assert "password=" not in blob


def test_fr5291_wait_reply_includes_gpo_result():
    def worker(**_kw):
        return {
            "ok": True,
            "gpo": "ok",
            "reason": "prepared",
            "browsers": ["chrome", "edge"],
            "policy_names": [ex.DEFAULT_GPO_NAME],
        }

    res = ex.run_extension_verb(action="install", worker=worker, wait=True, job_id="c25bd00e")
    assert "EXTENSION accepted" in res.reply
    assert "gpo_result=ok" in res.reply
    assert "browsers=chrome,edge" in res.reply.replace(" ", "")
    assert "password=" not in res.reply.lower()


def test_fr5291_console_extension_still_isolated():
    calls = {"n": 0}

    def worker(**_kw):
        calls["n"] += 1
        return {"ok": True, "gpo": "ok", "browsers": ["chrome", "edge"]}

    core = _core(extension_runner=lambda **kw: ex.run_extension_verb(worker=worker, wait=True, **kw))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=c25bd00e EXTENSION install")
    assert hr is not None and hr.action == "extension"
    assert "EXTENSION accepted" in (hr.reply or "")
    assert calls["n"] == 1
    assert "password=" not in (hr.reply or "").lower()


def test_fr5291_docs_and_script_pins():
    doc = (ROOT / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "EXTENSION" in doc
    assert "Priority-web-extension" in doc or "FR #5291" in doc or "ForceInstall" in doc
    ps = (ROOT / "airc/scripts/Invoke-AircExtensionGpo.ps1").read_text(encoding="utf-8")
    assert "Priority-web-extension" in ps
    assert "ExtensionInstallForcelist" in ps
    assert "cgmpadejahkaggjpffnhaoiafbnicgpa" in ps
    assert "clients2.google.com/service/update2/crx" in ps
    assert "New-GPO" in ps and "Set-GPRegistryValue" in ps
    assert "Invoke-Command" in ps
    assert "no_dc" in ps
    assert "\ufeff" not in ps
    assert "\u2014" not in ps
