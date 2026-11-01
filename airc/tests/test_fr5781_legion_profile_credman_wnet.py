"""FR #5781: LEGION profile read uses install-class WNet (IPC$); unread refuses silent client."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg
import airc_network_installer.install as inst


def test_fr5781_read_profile_wnets_ipc_like_install(monkeypatch):
    """CredMan path must WNet ``\\\\host\\IPC$`` (same as install_remote), not only c$."""
    calls: list[tuple[str, str]] = []

    def fake_net_use(unc: str, username: str, password: str) -> None:
        calls.append((unc, username))

    def fake_net_del(unc: str) -> None:
        calls.append(("DEL:" + unc, ""))

    monkeypatch.setattr(inst, "_net_use", fake_net_use)
    monkeypatch.setattr(inst, "_net_use_delete", fake_net_del)

    # No real UNC files — still must attempt IPC$ when username provided.
    out = inst.read_remote_airc_profile_result(
        "flamingo", username="WONDERLAND\\Administrator", password="FAKE_secret"
    )
    assert any(c[0].upper().endswith("IPC$") for c in calls), calls
    assert out.get("ok") in (True, False)  # result shaped
    assert "profile" in out


def test_fr5781_credman_read_keeps_fleet(monkeypatch):
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
        return {"ok": True, "status": "success"}

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=fake_run,
        credman=lambda: {
            "username": "WONDERLAND\\Administrator",
            "password": "FAKE_secret",
            "account": "WONDERLAND\\Administrator",
        },
    )
    assert body["ok"] is True
    assert body["profile"] == "fleet"
    assert body["profile_before"] == "fleet"
    assert body.get("error") not in ("profile_unreadable",)


def test_fr5781_unread_profile_refuses_without_explicit(monkeypatch):
    """SYSTEM/CredMan unread must not silently choose client — refuse."""
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {
            "profile": "",
            "ok": False,
            "found": False,
            "detail": "wnet-failed",
        },
    )

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda spec, secret="": {"ok": True, "status": "success"},
        credman=lambda: {
            "username": "WONDERLAND\\Administrator",
            "password": "FAKE_secret",
            "account": "WONDERLAND\\Administrator",
        },
    )
    assert body["ok"] is False
    assert body.get("error") == "profile_unreadable"
    assert body.get("invoked_installer") is False
    assert "profile" not in body or body.get("profile_warn") or body.get("detail")


def test_fr5781_unread_allows_explicit_profile(monkeypatch):
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {
            "profile": "",
            "ok": False,
            "found": False,
            "detail": "wnet-failed",
        },
    )
    monkeypatch.setattr(
        lg,
        "read_remote_post_install",
        lambda host, **_k: {"installed_version": "1.0.7", "service": "Running"},
    )
    seen = {}

    def fake_run(spec, secret=""):
        seen["profile"] = spec["profile"]
        return {"ok": True, "status": "success"}

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=fake_run,
        credman=lambda: {
            "username": "WONDERLAND\\Administrator",
            "password": "FAKE_secret",
        },
        profile="fleet",
    )
    assert body["ok"] is True
    assert seen.get("profile") == "fleet"
    assert body.get("profile_warn")  # unread + explicit still warns


def test_fr5781_missing_file_defaults_client_with_warn(monkeypatch):
    """WNet OK but no install.json → new host may default client with warn."""
    monkeypatch.setattr(
        lg,
        "read_remote_airc_profile_result",
        lambda host, **_k: {
            "profile": "",
            "ok": True,
            "found": False,
            "detail": "not-found",
        },
    )
    monkeypatch.setattr(
        lg,
        "read_remote_post_install",
        lambda host, **_k: {"installed_version": "1.0.7", "service": "Running"},
    )

    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda spec, secret="": {"ok": True, "status": "success"},
        credman=lambda: {"username": "u", "password": "FAKE_secret"},
    )
    assert body["ok"] is True
    assert body["profile"] == "client"
    assert "profile" in str(body.get("profile_warn") or "").lower() or "missing" in str(
        body.get("profile_warn") or ""
    ).lower() or "default" in str(body.get("profile_warn") or "").lower()


def test_fr5781_skills_mention():
    root = Path(lg.__file__).resolve().parents[1]
    blob = (root / ".grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    ) + (root / ".grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "5781" in blob or "profile_unreadable" in blob
