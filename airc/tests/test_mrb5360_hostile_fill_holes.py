"""MRB #5360 hostile pins for FR #5292 fill-holes."""
from __future__ import annotations

from repo_layout import ROOT

EXT = ROOT / "airc/scripts/airc_extension.py"


def test_mrb5360_no_lgpo_and_both_policy_trees():
    t = EXT.read_text(encoding="utf-8")
    assert "LGPO" not in t
    assert "ExtensionInstallForcelist" in t
    assert "Google\\Chrome" in t or r"Google\Chrome" in t
    assert "Microsoft\\Edge" in t or r"Microsoft\Edge" in t
    assert "cgmpadejahkaggjpffnhaoiafbnicgpa" in t
    assert "clients2.google.com" in t
    assert "extra_hosts" in t
    import airc_extension as ex

    v = ex.force_install_value()
    assert v.startswith(ex.DEFAULT_EXTENSION_ID + ";")


def test_mrb5360_unreachable_is_failure_not_invented():
    import airc_extension as ex

    def boom_apply(*_a):
        raise OSError(53, "The network path was not found")

    body = ex.fill_holes_work(
        "install",
        ldap_enum=lambda: ["only-ad"],
        ping_host=lambda _h: False,
        apply_force_install=boom_apply,
        tcp_probe=lambda *_a, **_k: False,
        extra_hosts=["ghost"],
    )
    assert [h["host"] for h in body["hosts"]] == ["only-ad"]
    # FR #5661: classified cause (not invented hosts); unreachable only for silence.
    assert body["hosts"][0]["ok"] is False
    assert body["hosts"][0]["error"] in {"smb_blocked", "host_down", "unreachable"}
    assert body["wrote_gpo"] is False
    assert body["wrote_registry"] is False
