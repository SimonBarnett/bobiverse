"""#4188: the !build runner hands GH auth to gh steps and fails early without it."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobiverse_build as bb  # noqa: E402
import run_bobiverse_build as rbb  # noqa: E402

FAKE = "ghp_FAKE_TOKEN_FOR_TESTS_ONLY"


def _capture():
    seen = []

    def inner(cmd, cwd=None, env=None, timeout=None, *, name="cmd", ref_or_baseline=""):
        seen.append((name, dict(env or {})))
        return SimpleNamespace(exit_code=0, timed_out=False, stdout="", name=name)

    return seen, inner


def test_assert_step_gets_runner_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", FAKE)
    seen, inner = _capture()
    run = bb.guarded_run_command(tmp_path, [tmp_path / "live"], inner=inner)
    run("x", env={}, name="assert", ref_or_baseline="HEAD")
    env = seen[0][1]
    assert env["GH_TOKEN"] == FAKE and env["GITHUB_TOKEN"] == FAKE


def test_suite_steps_stay_tokenless(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", FAKE)
    seen, inner = _capture()
    run = bb.guarded_run_command(tmp_path, [tmp_path / "live"], inner=inner)
    run("x", env={}, name="pytest-common", ref_or_baseline="HEAD")
    assert seen[0][1]["GH_TOKEN"] == "" and seen[0][1]["GITHUB_TOKEN"] == ""


def test_github_token_fallback(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", FAKE)
    assert bb.gh_auth_env()["GH_TOKEN"] == FAKE
    assert bb.gh_auth_env({}) == {}


def test_preflight_ok_and_missing():
    ok = lambda *a, **k: SimpleNamespace(returncode=0)  # noqa: E731
    bad = lambda *a, **k: SimpleNamespace(returncode=1)  # noqa: E731
    assert bb.gh_auth_preflight(ok, env={"GH_TOKEN": FAKE}) is None
    why = bb.gh_auth_preflight(bad, env={})
    assert why and "gh auth missing" in why and "#4188" in why and FAKE not in why


def test_preflight_gh_not_installed():
    def boom(*a, **k):
        raise FileNotFoundError("gh")

    assert "gh auth missing" in bb.gh_auth_preflight(boom, env={})


def test_runner_refuses_before_checkout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rbb.bb, "gh_auth_preflight", lambda *a, **k: bb.GH_AUTH_MISSING)
    monkeypatch.setattr(rbb, "checkout", lambda *a, **k: (_ for _ in ()).throw(AssertionError("checked out")))
    out = tmp_path / "r.json"
    rc = rbb.main(["--version", "0.1.32.2", "--checkout", "--work-dir", str(tmp_path / "w"),
                   "--result-file", str(out)])
    assert rc == 4
    res = json.loads(out.read_text())
    assert res["gh_auth"] == "missing" and "gh auth missing" in res["errors"][0]
    assert not (tmp_path / "w").exists()


def test_runner_never_records_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", FAKE)
    monkeypatch.setattr(rbb.bb, "gh_auth_preflight", lambda *a, **k: bb.GH_AUTH_MISSING)
    out = tmp_path / "r.json"
    rbb.main(["--version", "0.1.32.2", "--result-file", str(out)])
    assert FAKE not in out.read_text()
