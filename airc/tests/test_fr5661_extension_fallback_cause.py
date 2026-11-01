"""FR #5661: EXTENSION fallback reports real cause, not blanket unreachable."""
from __future__ import annotations

import airc_extension as ex


def test_fr5661_classify_remote_registry_stopped():
    exc = OSError(1722, "The RPC server is unavailable")
    out = ex.classify_extension_host_error(exc, icmp_ok=True, smb_ok=True)
    assert out["error"] == "remote_registry_stopped"
    assert "rpc" in (out.get("detail") or "").lower() or "1722" in (out.get("detail") or "")


def test_fr5661_classify_smb_blocked():
    exc = OSError(53, "The network path was not found")
    out = ex.classify_extension_host_error(exc, icmp_ok=True, smb_ok=False)
    assert out["error"] == "smb_blocked"
    assert out.get("detail")


def test_fr5661_classify_access_denied():
    out = ex.classify_extension_host_error(
        PermissionError(5, "Access is denied"), icmp_ok=True, smb_ok=True
    )
    assert out["error"] == "access_denied"


def test_fr5661_classify_host_down_no_icmp_no_smb():
    out = ex.classify_extension_host_error(None, icmp_ok=False, smb_ok=False)
    assert out["error"] == "host_down"


def test_fr5661_whatif_registry_rpc_not_unreachable():
    def boom_read(host: str, product: str):
        raise OSError(1722, "The RPC server is unavailable")

    body = ex.fill_holes_work(
        "install",
        whatif=True,
        ldap_enum=lambda: ["flamingo"],
        ping_host=lambda _h: False,
        read_forcelist=boom_read,
        tcp_probe=lambda _h, _p=445: True,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(AssertionError("no write")),
    )
    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] == "remote_registry_stopped"
    assert row["error"] != "unreachable"
    assert row.get("detail")


def test_fr5661_whatif_smb_path_not_unreachable():
    def boom_read(host: str, product: str):
        raise OSError(53, "The network path was not found")

    body = ex.fill_holes_work(
        "install",
        whatif=True,
        ldap_enum=lambda: ["redqueen"],
        ping_host=lambda _h: False,
        read_forcelist=boom_read,
        tcp_probe=lambda _h, _p=445: False,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(AssertionError("no write")),
    )
    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] in {"smb_blocked", "host_down"}
    assert row["error"] != "unreachable"


def test_fr5661_icmp_fail_but_registry_ok_still_plans():
    """ICMP alone must not mark an online host unreachable (MarchHare retest)."""
    body = ex.fill_holes_work(
        "install",
        whatif=True,
        ldap_enum=lambda: ["redqueen"],
        ping_host=lambda _h: False,
        read_forcelist=lambda _h, _p: ([], []),
        tcp_probe=lambda _h, _p=445: True,
        apply_force_install=lambda *_a: (_ for _ in ()).throw(AssertionError("no write")),
    )
    row = body["hosts"][0]
    assert row["ok"] is True
    assert row.get("would_write") is True
    assert "error" not in row or not row.get("error")


def test_fr5661_live_apply_classifies_rpc():
    def boom_apply(host: str, product: str, value: str):
        raise OSError(1722, "The RPC server is unavailable")

    body = ex.fill_holes_work(
        "install",
        whatif=False,
        ldap_enum=lambda: ["flamingo"],
        ping_host=lambda _h: True,
        apply_force_install=boom_apply,
        tcp_probe=lambda _h, _p=445: True,
    )
    row = body["hosts"][0]
    assert row["ok"] is False
    assert row["error"] == "remote_registry_stopped"


def test_fr5661_log_failures_carry_cause():
    log = ex.extension_log_from_payload(
        "install",
        whatif=True,
        payload={
            "action": "install",
            "whatif": True,
            "hosts": [
                {
                    "host": "FLAMINGO",
                    "ok": False,
                    "error": "remote_registry_stopped",
                    "detail": "The RPC server is unavailable",
                }
            ],
            "failures": [],
            "ok": False,
        },
    )
    fails = log.get("failures") or []
    assert any(
        f.get("step") == "fallback"
        and f.get("error") == "remote_registry_stopped"
        and "RPC" in (f.get("detail") or "")
        for f in fails
    )


def test_fr5661_skills_mention_causes():
    from repo_layout import ROOT

    blob = (ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    ) + (ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "5661" in blob
    assert "remote_registry_stopped" in blob
    assert "smb_blocked" in blob
