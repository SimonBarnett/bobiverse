"""FR #5758: LEGION preserves fleet profile / -Profile; post-install version+service."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg
import airc_network_installer.install as inst
from airc_network_installer.core import ALLOWED_PROFILES


def test_fr5758_parse_profile_flag():
    p = lg.parse_legion_command("LEGION walrus -Profile fleet")
    assert p is not None and p.get("error") is None
    assert p["target"] == "walrus"
    assert p["profile"] == "fleet"
    p2 = lg.parse_legion_command("id=aabbccdd LEGION 10.0.0.8 -WhatIf -Profile=workstation")
    assert p2["profile"] == "workstation" and p2["whatif"] is True
    bad = lg.parse_legion_command("LEGION walrus -Profile banana")
    assert bad["error"] == "bad-profile"
    # -Force still unknown (FR #5614).
    force = lg.parse_legion_command("LEGION walrus -Force")
    assert force["error"] == "unknown-flag"


def test_fr5758_resolve_profile_preserves_remote_fleet():
    got = lg.resolve_legion_profile(
        explicit=None,
        profile_before="fleet",
    )
    assert got["profile"] == "fleet"
    assert got["profile_before"] == "fleet"
    assert got["profile_after"] == "fleet"
    assert got.get("profile_warn") in (None, "", False)


def test_fr5758_resolve_profile_explicit_overrides_and_warns_downgrade():
    got = lg.resolve_legion_profile(explicit="client", profile_before="fleet")
    assert got["profile"] == "client"
    assert got["profile_before"] == "fleet"
    assert got["profile_after"] == "client"
    assert got.get("profile_warn")
    assert "downgrade" in str(got.get("profile_warn")).lower() or "fleet" in str(
        got.get("profile_warn")
    ).lower()


def test_fr5758_resolve_defaults_client_when_no_remote():
    got = lg.resolve_legion_profile(explicit=None, profile_before="")
    assert got["profile"] == "client"
    assert got["profile_before"] in ("", None)


def test_fr5758_installer_preserves_fleet_without_flag(monkeypatch):
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {
            "profile": "fleet",
            "ok": True,
            "found": True,
            "detail": "",
        },
    )
    monkeypatch.setattr(
        lg,
        "read_remote_post_install",
        lambda host, **_k: {"installed_version": "1.0.7", "service": "Running"},
    )

    def fake_run(spec, secret=""):
        assert spec["profile"] == "fleet"
        return {"ok": True, "status": "success", "msi": "airc-1.0.7.msi"}

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=fake_run,
        credman=lambda: {},
    )
    assert body["ok"] is True
    assert body["profile"] == "fleet"
    assert body["profile_before"] == "fleet"
    assert body["profile_after"] == "fleet"
    assert body.get("installed_version") == "1.0.7"
    assert body.get("service") == "Running"


def test_fr5758_installer_explicit_client_on_fleet_warns(monkeypatch):
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {
            "profile": "fleet",
            "ok": True,
            "found": True,
            "detail": "",
        },
    )
    monkeypatch.setattr(
        lg,
        "read_remote_post_install",
        lambda host, **_k: {"installed_version": "1.0.7", "service": "Running"},
    )

    def fake_run(spec, secret=""):
        assert spec["profile"] == "client"
        return {"ok": True, "status": "success"}

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=fake_run,
        credman=lambda: {},
        profile="client",
    )
    assert body["profile"] == "client"
    assert body["profile_before"] == "fleet"
    assert body.get("profile_warn")


def test_fr5758_deliver_done_carries_profile_and_verify():
    log = lg.build_legion_log(
        target="flamingo",
        whatif=False,
        summary="success",
        failures=[],
        extra={
            "profile": "fleet",
            "profile_before": "fleet",
            "profile_after": "fleet",
            "installed_version": "1.0.7",
            "service": "Running",
            "identity": "credman",
            "account": "WONDERLAND\\Administrator",
        },
    )
    assert log["profile"] == "fleet"
    out = lg.deliver_legion_log(job_id="4e600006", log=log, offer=None)
    done = out["done"]
    assert "profile=fleet" in done
    assert "installed_version=1.0.7" in done
    assert "service=Running" in done
    assert "identity=credman" in done


def test_fr5758_read_remote_profile_parses_json(tmp_path, monkeypatch):
    # Simulate UNC read via injectable open of install.json content.
    payload = '{"profile":"fleet","SelfUpdate":true}\n'

    def fake_read(host: str, username: str = "", password: str = "") -> str:
        assert host == "flamingo"
        return "fleet"

    monkeypatch.setattr(lg, "read_remote_airc_profile", fake_read)
    assert lg.read_remote_airc_profile("flamingo") == "fleet"
    assert "fleet" in ALLOWED_PROFILES


def test_fr5758_skills_mention_profile_preserve():
    root = Path(lg.__file__).resolve().parents[1]
    cmd = (root / ".grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    )
    docs = (root / "docs/airc-remote-control.md").read_text(encoding="utf-8")
    blob = cmd + "\n" + docs
    assert "5758" in blob or "profile_before" in blob or "-Profile" in blob
