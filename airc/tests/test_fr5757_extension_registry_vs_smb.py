"""FR #5757: IPC-ok + ConnectRegistry 53 is remote_registry_stopped; GPO covers soft-fail."""
from __future__ import annotations

import airc_extension as ex
from repo_layout import ROOT


def _winerr(code: int, msg: str) -> OSError:
    exc = OSError(msg)
    exc.winerror = code  # type: ignore[attr-defined]
    return exc


def test_fr5757_ipc_ok_connectregistry_53_is_remote_registry_stopped():
    """SMB/IPC up + WinError 53 from ConnectRegistry must not be smb_blocked."""
    out = ex.classify_extension_host_error(
        _winerr(53, "[WinError 53] The network path was not found"),
        icmp_ok=True,
        smb_ok=True,
    )
    assert out["error"] == "remote_registry_stopped"
    assert out["error"] != "smb_blocked"


def test_fr5757_smb_down_53_still_smb_blocked_or_host_down():
    out = ex.classify_extension_host_error(
        _winerr(53, "[WinError 53] The network path was not found"),
        icmp_ok=True,
        smb_ok=False,
    )
    assert out["error"] in {"smb_blocked", "host_down"}


def test_fr5757_live_apply_ipc_ok_registry_53(monkeypatch):
    def boom_apply(host: str, product: str, value: str):
        raise _winerr(53, "[WinError 53] The network path was not found")

    body = ex.fill_holes_work(
        "install",
        whatif=False,
        ldap_enum=lambda: ["flamingo"],
        ping_host=lambda _h: True,
        apply_force_install=boom_apply,
        tcp_probe=lambda _h, _p=445: True,
        is_dc=lambda _h: False,
        is_windows_host=lambda _h: True,
    )
    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] == "remote_registry_stopped"
    assert row["error"] != "smb_blocked"


def test_fr5757_gpo_ok_softens_remote_registry_stopped():
    """GPO wrote successfully: registry-unreachable host is skipped:gpo, not a hard fail."""

    def boom_apply(host: str, product: str, value: str):
        raise _winerr(53, "[WinError 53] The network path was not found")

    def fake_gpo(action, *, whatif=False, extension_id=ex.DEFAULT_EXTENSION_ID, **_kw):
        return {
            "ok": True,
            "gpo": "ok",
            "wrote_gpo": True,
            "action": action,
            "whatif": whatif,
            "extension_id": extension_id,
            "browsers": ["chrome", "edge"],
            "policy_names": ["Priority-web-extension"],
        }

    import airc_extension as mod

    orig = mod.run_extension_gpo_work
    try:
        mod.run_extension_gpo_work = fake_gpo  # type: ignore[assignment]
        body = mod.extension_gpo_then_fill_holes(
            "install",
            whatif=False,
            ldap_enum=lambda: ["flamingo"],
            ping_host=lambda _h: True,
            apply_force_install=boom_apply,
            tcp_probe=lambda _h, _p=445: True,
            is_dc=lambda _h: False,
            is_windows_host=lambda _h: True,
        )
    finally:
        mod.run_extension_gpo_work = orig  # type: ignore[assignment]

    assert body.get("wrote_gpo") is True
    row = body["hosts"][0]
    assert row.get("ok") is True
    assert row.get("skipped") == "gpo"
    assert row.get("gpo_covers") is True
    assert row.get("warning") == "remote_registry_stopped"
    assert not row.get("error")
    log = ex.extension_log_from_payload("install", whatif=False, payload=body)
    fails = log.get("failures") or []
    assert not any(
        str(f.get("host") or "").lower() == "flamingo"
        and f.get("error") == "remote_registry_stopped"
        for f in fails
    )
    assert log.get("ok") is True or len(fails) == 0


def test_fr5757_gpo_ok_still_fails_host_down():
    """Offline/firewalled hosts remain hard failures even when GPO wrote."""

    def boom_apply(host: str, product: str, value: str):
        raise _winerr(53, "[WinError 53] The network path was not found")

    def fake_gpo(action, *, whatif=False, extension_id=ex.DEFAULT_EXTENSION_ID, **_kw):
        return {
            "ok": True,
            "gpo": "ok",
            "wrote_gpo": True,
            "action": action,
            "extension_id": extension_id,
        }

    import airc_extension as mod

    orig = mod.run_extension_gpo_work
    try:
        mod.run_extension_gpo_work = fake_gpo  # type: ignore[assignment]
        body = mod.extension_gpo_then_fill_holes(
            "install",
            whatif=False,
            ldap_enum=lambda: ["redqueen"],
            ping_host=lambda _h: False,
            apply_force_install=boom_apply,
            tcp_probe=lambda _h, _p=445: False,
            is_dc=lambda _h: False,
            is_windows_host=lambda _h: True,
        )
    finally:
        mod.run_extension_gpo_work = orig  # type: ignore[assignment]

    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] in {"smb_blocked", "host_down"}
    assert row.get("skipped") != "gpo"


def test_fr5757_skills_document():
    blob = (ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    ) + (ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "5757" in blob
    assert "remote_registry_stopped" in blob
    assert "gpo" in blob.lower()
