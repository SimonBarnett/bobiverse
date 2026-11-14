"""FR #7288: Jeeves fleet pools read CredMan then Jeeves-root fallbacks."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import fleet_pool_fetch as fp


def test_fr7288_credman_targets_documented():
    assert fp.CREDMAN_GITHUB_TARGET == "bobiverse/jeeves/github-token"
    assert fp.CREDMAN_OPENCODE_GO_TARGET == "bobiverse/jeeves/opencode-go-key"


def test_fr7288_github_credman_wins(monkeypatch, tmp_path: Path):
    root = tmp_path / "jeeves"
    (root / "config").mkdir(parents=True)
    (root / "config" / "github.token").write_text("file-token-SHOULD-NOT-WIN\n", encoding="utf-8")
    monkeypatch.setenv("JEEVES_INSTALL_ROOT", str(root))
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def fake_cred(target: str):
        if target == fp.CREDMAN_GITHUB_TARGET:
            return {"username": "token", "password": "credman-gh-token"}
        return {}

    monkeypatch.setattr(fp, "read_credman_secret", fake_cred)
    tok, src, tried = fp.resolve_fleet_github_token()
    assert tok == "credman-gh-token"
    assert src == f"credman:{fp.CREDMAN_GITHUB_TARGET}"
    assert fp.CREDMAN_GITHUB_TARGET in ",".join(tried)


def test_fr7288_github_credman_miss_falls_back_to_jeeves_file(monkeypatch, tmp_path: Path):
    root = tmp_path / "jeeves"
    (root / "config").mkdir(parents=True)
    (root / "config" / "github.token").write_text("jeeves-file-token\n", encoding="utf-8")
    monkeypatch.setenv("JEEVES_INSTALL_ROOT", str(root))
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(fp, "read_credman_secret", lambda _t: {})
    tok, src, tried = fp.resolve_fleet_github_token()
    assert tok == "jeeves-file-token"
    assert src == "file:github.token"
    assert any("credman:" in t for t in tried)


def test_fr7288_github_root_is_jeeves_not_ear_scripts(monkeypatch, tmp_path: Path):
    ear = tmp_path / "bob"
    (ear / "scripts").mkdir(parents=True)
    (ear / "config").mkdir(parents=True)
    (ear / "config" / "github.token").write_text("ear-token\n", encoding="utf-8")
    jeeves = tmp_path / "jeeves"
    (jeeves / "config").mkdir(parents=True)
    (jeeves / "config" / "github.token").write_text("jeeves-token\n", encoding="utf-8")
    monkeypatch.setenv("JEEVES_INSTALL_ROOT", str(jeeves))
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(ear))  # ear-looking; JEEVES wins
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(fp, "read_credman_secret", lambda _t: {})
    tok, src, _tried = fp.resolve_fleet_github_token()
    assert tok == "jeeves-token"
    assert src == "file:github.token"
    root = fp.fleet_jeeves_install_root()
    assert root is not None
    assert root.resolve() == jeeves.resolve()
    assert "scripts" not in root.name.lower() or (root / "config").is_dir()


def test_fr7288_opencode_credman_wins(monkeypatch, tmp_path: Path):
    root = tmp_path / "jeeves"
    (root / "config").mkdir(parents=True)
    (root / "config" / "opencode-go.apikey").write_text("file-go-key\n", encoding="utf-8")
    monkeypatch.setenv("JEEVES_INSTALL_ROOT", str(root))
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.setattr(
        fp,
        "read_credman_secret",
        lambda t: {"password": "credman-go-key"} if t == fp.CREDMAN_OPENCODE_GO_TARGET else {},
    )
    key, src, tried = fp.resolve_fleet_opencode_go_key()
    assert key == "credman-go-key"
    assert src == f"credman:{fp.CREDMAN_OPENCODE_GO_TARGET}"
    assert any("credman:" in x for x in tried)


def test_fr7288_missing_everything_clear_source_list(monkeypatch, tmp_path: Path):
    root = tmp_path / "jeeves-empty"
    root.mkdir()
    (root / "config").mkdir()
    monkeypatch.setenv("JEEVES_INSTALL_ROOT", str(root))
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "BOB_OPENCODE_GO_API_KEY", "BOB_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(fp, "read_credman_secret", lambda _t: {})
    tok, src, tried = fp.resolve_fleet_github_token()
    assert tok == ""
    assert src.startswith("none:")
    assert "credman:" in src
    assert "env:GH_TOKEN" in src or "env:" in src
    key, ksrc, ktried = fp.resolve_fleet_opencode_go_key()
    assert key == ""
    assert ksrc.startswith("none:") or ksrc == "none"
    assert any("credman:" in x for x in ktried)


def test_fr7288_digest_source_tag_never_secret(monkeypatch, tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    bobreport.save_digest(home, bobreport.empty_digest())
    root = tmp_path / "jeeves"
    (root / "config").mkdir(parents=True)
    monkeypatch.setenv("JEEVES_INSTALL_ROOT", str(root))
    secret = "SUPER_SECRET_TOKEN_VALUE_XYZ"
    monkeypatch.setattr(
        fp,
        "read_credman_secret",
        lambda t: {"password": secret} if t == fp.CREDMAN_GITHUB_TARGET else {},
    )

    def copilot(_home, now):
        tok, src, _ = fp.resolve_fleet_github_token()
        assert tok == secret
        iso = fp.iso_utc(now)
        return {
            "id": "copilot",
            "remaining": 9,
            "fetched_at": iso,
            "last_attempt_at": iso,
            "error": None,
            "source": src,
            "fresh": True,
        }

    def opencode(_home, now):
        iso = fp.iso_utc(now)
        return {
            "opencode-free": {
                "id": "opencode-free",
                "remaining": 1,
                "fetched_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
            "opencode-go": {
                "id": "opencode-go",
                "remaining": 1,
                "fetched_at": iso,
                "error": None,
                "source": "go-zen-usage",
                "fresh": True,
            },
            "windows": {},
        }

    out = fp.tick_fleet_pools(
        home, now=1_700_000_000.0, force=True, fetch_copilot=copilot, fetch_opencode=opencode
    )
    blob = json.dumps(out) + json.dumps(bobreport.load_digest(home))
    assert secret not in blob
    assert f"credman:{fp.CREDMAN_GITHUB_TARGET}" in blob


def test_fr7288_bob_install_root_does_not_steal_github_file(monkeypatch, tmp_path: Path):
    """Without JEEVES_INSTALL_ROOT, BOB_INSTALL_ROOT (ear) must not win the file fallback."""
    ear = tmp_path / "bob"
    (ear / "config").mkdir(parents=True)
    (ear / "config" / "github.token").write_text("FAKE_EAR_TOKEN\n", encoding="utf-8")
    jeeves = tmp_path / "jeeves"
    (jeeves / "config").mkdir(parents=True)
    (jeeves / "config" / "github.token").write_text("FAKE_JEEVES_TOKEN\n", encoding="utf-8")
    monkeypatch.delenv("JEEVES_INSTALL_ROOT", raising=False)
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(ear))
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(fp, "read_credman_secret", lambda _t: {})
    import ai_root

    monkeypatch.setattr(
        ai_root,
        "product_root",
        lambda product, **k: str(jeeves) if product == "jeeves" else str(ear),
    )
    tok, src, _tried = fp.resolve_fleet_github_token()
    assert tok == "FAKE_JEEVES_TOKEN"
    assert src == "file:github.token"
    root = fp.fleet_jeeves_install_root()
    assert root is not None
    assert root.resolve() == jeeves.resolve()


def test_fr7288_opencode_file_uses_jeeves_not_ear(monkeypatch, tmp_path: Path):
    ear = tmp_path / "bob"
    (ear / "config").mkdir(parents=True)
    (ear / "config" / "opencode-go.apikey").write_text("FAKE_EAR_GO\n", encoding="utf-8")
    jeeves = tmp_path / "jeeves"
    (jeeves / "config").mkdir(parents=True)
    (jeeves / "config" / "opencode-go.apikey").write_text("FAKE_JEEVES_GO\n", encoding="utf-8")
    monkeypatch.setenv("JEEVES_INSTALL_ROOT", str(jeeves))
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(ear))
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.setattr(fp, "read_credman_secret", lambda _t: {})
    key, src, _tried = fp.resolve_fleet_opencode_go_key()
    assert key == "FAKE_JEEVES_GO"
    assert "file:" in src


def test_fr7288_env_github_wins_after_credman_miss(monkeypatch, tmp_path: Path):
    root = tmp_path / "jeeves"
    (root / "config").mkdir(parents=True)
    (root / "config" / "github.token").write_text("FAKE_FILE_SHOULD_LOSE\n", encoding="utf-8")
    monkeypatch.setenv("JEEVES_INSTALL_ROOT", str(root))
    monkeypatch.setenv("GH_TOKEN", "FAKE_ENV_GH")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(fp, "read_credman_secret", lambda _t: {})
    tok, src, _tried = fp.resolve_fleet_github_token()
    assert tok == "FAKE_ENV_GH"
    assert src == "env:GH_TOKEN"


def test_fr7288_fetch_copilot_no_token_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(fp, "resolve_fleet_github_token", lambda: ("", "none:credman:x,env:GH_TOKEN", ["credman:x"]))
    meter = fp.fetch_copilot_default(tmp_path, now=1_700_000_000.0)
    assert meter.get("error") == "no_token"
    assert str(meter.get("source") or "").startswith("none:")
    assert meter.get("fresh") is False


def test_fr7288_docs_list_targets_and_cmdkey():
    docs = (Path(__file__).resolve().parents[2] / "jeeves" / "docs" / "fleet-pools-credentials.md")
    assert docs.is_file()
    text = docs.read_text(encoding="utf-8")
    assert fp.CREDMAN_GITHUB_TARGET in text
    assert fp.CREDMAN_OPENCODE_GO_TARGET in text
    assert "cmdkey" in text.lower() or "CredWrite" in text or "New-StoredCredential" in text
    assert "LocalSystem" in text or "SYSTEM" in text
    assert "never" in text.lower() and ("log" in text.lower() or "digest" in text.lower())
    hooks = Path(__file__).resolve().parents[2] / "jeeves" / "docs" / "webhooks.md"
    htxt = hooks.read_text(encoding="utf-8")
    assert "fleet-pools-credentials.md" in htxt
    assert "7288" in htxt
