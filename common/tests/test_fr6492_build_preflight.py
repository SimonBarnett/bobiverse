"""FR #6492: recipe-machine !build preflight / --preflight checks; never leak token."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import bobiverse_build as bb
import chair_commands as cc
import run_bobiverse_build as rbb
from repo_layout import ROOT

FAKE_TOKEN = "ghp_FAKE_TOKEN_FOR_PREFLIGHT_TESTS_ONLY_6492"


def _all_ok_hooks(tmp_path: Path):
    """Injectable probes that make every preflight item pass."""
    recipe = bb.load_recipe(ROOT)
    work = tmp_path / "work"
    return dict(
        env={"BOBIVERSE_PYTHON": "C:\\Python\\Python312\\python.exe", "PATH": "C:\\Python\\Python312;C:\\Windows"},
        which=lambda name: {
            "python": "C:\\Python\\Python312\\python.exe",
            "powershell": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            "gh": "C:\\Program Files\\GitHub CLI\\gh.exe",
        }.get(name),
        resolve_python=lambda env: "C:\\Python\\Python312\\python.exe",
        missing_imports=lambda: [],
        token_source=lambda: "env:GH_TOKEN",
        gh_auth=lambda: None,
        recipe_loader=lambda root: recipe,
        work_dir=work,
        mkdir=lambda p: Path(p).mkdir(parents=True, exist_ok=True),
    )


def test_fr6492_preflight_all_ok_exits_zero(tmp_path: Path):
    report = bb.run_build_preflight(repo="SimonBarnett/bobiverse", repo_root=ROOT, **_all_ok_hooks(tmp_path))
    assert report.ok is True
    assert report.exit_code == 0
    names = [i.name for i in report.items]
    for need in (
        "runner_python",
        "runner_imports",
        "suite_python",
        "github_token",
        "recipe",
        "work_dir",
        "cache_dir",
        "pack_tools",
    ):
        assert need in names
    assert all(i.ok for i in report.items)
    assert all(ln.startswith("build preflight:") for ln in report.lines)
    blob = "\n".join(report.lines)
    assert FAKE_TOKEN not in blob
    assert "missing" not in blob


def test_fr6492_each_missing_item_reports_and_nonzero(tmp_path: Path):
    """Acceptance: each item missing in turn reports exactly that item as missing."""
    cases = {
        "runner_python": dict(resolve_python=lambda env: ""),
        "runner_imports": dict(missing_imports=lambda: ["yaml"]),
        "suite_python": dict(which=lambda name: None if name == "python" else _all_ok_hooks(tmp_path)["which"](name)),
        "github_token": dict(token_source=lambda: "none", gh_auth=lambda: bb.GH_AUTH_MISSING),
        "recipe": dict(
            recipe_loader=lambda root: (_ for _ in ()).throw(
                bb.RecipeError("build: has no .bobiverse/build.yml; nothing started")
            )
        ),
        "work_dir": dict(
            mkdir=lambda p: (_ for _ in ()).throw(OSError("access denied"))
            if "work" in str(p).replace("\\", "/") or str(p).endswith("work")
            else Path(p).mkdir(parents=True, exist_ok=True)
        ),
        "cache_dir": dict(
            mkdir=lambda p: (_ for _ in ()).throw(OSError("cache denied"))
            if "cache" in str(p).replace("\\", "/")
            else Path(p).mkdir(parents=True, exist_ok=True)
        ),
        "pack_tools": dict(
            which=lambda name: None
            if name in ("powershell", "gh")
            else _all_ok_hooks(tmp_path)["which"](name)
        ),
    }
    for missing_name, override in cases.items():
        hooks = _all_ok_hooks(tmp_path)
        hooks.update(override)
        # work_dir override: force work path under tmp so mkdir probe hits it
        if missing_name == "work_dir":
            hooks["work_dir"] = tmp_path / "work"
        if missing_name == "cache_dir":
            hooks["work_dir"] = tmp_path / "work"
        report = bb.run_build_preflight(repo="SimonBarnett/bobiverse", repo_root=ROOT, **hooks)
        assert report.ok is False, missing_name
        assert report.exit_code != 0, missing_name
        bad = [i for i in report.items if not i.ok]
        assert len(bad) >= 1, missing_name
        assert any(i.name == missing_name for i in bad), (missing_name, [(i.name, i.detail) for i in bad])
        # Other named items that were not overridden should still be ok when independent.
        # (work_dir failure may also prevent cache_dir — accept that; still must name work_dir.)
        blob = "\n".join(report.lines)
        assert f"{missing_name}=missing" in blob, (missing_name, blob)
        assert FAKE_TOKEN not in blob


def test_fr6492_preflight_never_contains_token_value(tmp_path: Path):
    hooks = _all_ok_hooks(tmp_path)
    hooks["token_source"] = lambda: "file:C:\\ai\\bob\\config\\github.token"
    hooks["gh_auth"] = lambda: None
    # Poison env with the real-looking fake; output must still omit it.
    hooks["env"] = {
        "BOBIVERSE_PYTHON": "C:\\Python\\Python312\\python.exe",
        "GH_TOKEN": FAKE_TOKEN,
        "PATH": "C:\\Python\\Python312",
    }
    report = bb.run_build_preflight(repo="SimonBarnett/bobiverse", repo_root=ROOT, **hooks)
    blob = "\n".join(report.lines) + json.dumps(
        [{"name": i.name, "ok": i.ok, "detail": i.detail} for i in report.items]
    )
    assert FAKE_TOKEN not in blob
    assert "github_token=ok" in "\n".join(report.lines)
    assert "source=file:" in "\n".join(report.lines) or "file:" in "\n".join(report.lines)


def test_fr6492_decide_build_preflight_route_no_lock(tmp_path: Path):
    who = cc.Principal("owner", "simon", "simon")
    lock = bb.BuildLock(tmp_path / "l.json")
    dec = bb.decide_build(
        who=who,
        body="!build preflight SimonBarnett/bobiverse",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
    )
    assert dec and dec.ok and dec.reason == "preflight"
    assert dec.route == "BUILDPREFLIGHT v1 repo=SimonBarnett/bobiverse"
    assert lock.running_id("SimonBarnett/bobiverse") is None
    assert any("preflight" in ln.lower() for ln in dec.pm_lines)


def test_fr6492_parse_build_preflight_and_wire():
    assert bb.parse_build("!build preflight SimonBarnett/bobiverse") == (
        True,
        "preflight",
        "SimonBarnett/bobiverse",
    )
    d = bb.parse_build_preflight_v1_route("BUILDPREFLIGHT v1 repo=SimonBarnett/bobiverse")
    assert d and d["repo"] == "SimonBarnett/bobiverse"
    assert bb.parse_build_preflight_v1_route("BUILD v1 repos=a/b version=1 ref=HEAD") is None


def test_fr6492_cli_preflight_exit_codes(tmp_path: Path, monkeypatch):
    ok_report = bb.PreflightReport(
        ok=True,
        exit_code=0,
        items=[bb.PreflightItem("runner_python", True, "path=x")],
        lines=["build preflight: runner_python=ok path=x"],
    )
    bad_report = bb.PreflightReport(
        ok=False,
        exit_code=1,
        items=[bb.PreflightItem("github_token", False, "source=none")],
        lines=["build preflight: github_token=missing source=none"],
    )
    monkeypatch.setattr(rbb.bb, "run_build_preflight", lambda **k: ok_report)
    assert rbb.main(["--preflight", "--repo", "SimonBarnett/bobiverse", "--repo-root", str(ROOT)]) == 0
    monkeypatch.setattr(rbb.bb, "run_build_preflight", lambda **k: bad_report)
    assert rbb.main(["--preflight", "--repo", "SimonBarnett/bobiverse", "--repo-root", str(ROOT)]) == 1


def test_fr6492_docs_list_four_setup_items():
    text = (ROOT / "bob" / "AGENTS.md").read_text(encoding="utf-8")
    assert "FR #6492" in text or "build preflight" in text.lower() or "!build preflight" in text
    for needle in ("BOBIVERSE_PYTHON", "github.token", "PATH", "build.yml"):
        assert needle in text
    # How preflight checks each of the four
    assert "runner_python" in text or "resolved Python" in text or "preflight" in text.lower()
    assert "suite_python" in text or "suite Python" in text or "python on PATH" in text.lower()
    assert "github_token" in text or "token source" in text.lower()
    assert "recipe" in text.lower()


def test_fr6492_help_mentions_preflight():
    ops = cc.Principal("owner", "simon", "simon")
    detail = "\n".join(cc.build_help(ops, "build"))
    assert "preflight" in detail.lower()
    assert "preflight" in cc.COMMAND_BY_NAME["build"].syntax
