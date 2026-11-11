"""FR #6487: YAML recipe parse errors must not be masked as missing build.yml."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import chair_commands as cc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobiverse_build as bb  # noqa: E402


def _write_yaml_recipe(root: Path, text: str) -> Path:
    d = root / ".bobiverse"
    d.mkdir(parents=True)
    p = d / "build.yml"
    p.write_text(text, encoding="utf-8")
    return p


def test_fr6487_missing_file_still_says_no_build_yml(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    try:
        bb.load_recipe_from_candidates([empty], repo="SimonBarnett/bobiverse")
        assert False, "expected RecipeError"
    except bb.RecipeError as exc:
        assert "no .bobiverse/build.yml" in str(exc)
        assert "nothing started" in str(exc)


def test_fr6487_yaml_unavailable_names_pyyaml(tmp_path: Path, monkeypatch):
    root = tmp_path / "install"
    root.mkdir()
    _write_yaml_recipe(
        root,
        "machine: flamingo\nsuites:\n  - name: c\n    cmd: true\n",
    )
    monkeypatch.setattr(bb, "yaml", None)
    try:
        bb.load_recipe_from_candidates([root], repo="SimonBarnett/bobiverse")
        assert False, "expected RecipeError"
    except bb.RecipeError as exc:
        msg = str(exc)
        assert "PyYAML" in msg
        assert "no .bobiverse/build.yml" not in msg


def test_fr6487_invalid_recipe_names_validation(tmp_path: Path):
    root = tmp_path / "install"
    root.mkdir()
    # Valid YAML, invalid recipe (no suites).
    _write_yaml_recipe(root, "machine: flamingo\nsuites: []\n")
    try:
        bb.load_recipe_from_candidates([root], repo="SimonBarnett/bobiverse")
        assert False, "expected RecipeError"
    except bb.RecipeError as exc:
        msg = str(exc)
        assert "suites" in msg.lower() or "non-empty" in msg.lower()
        assert "no .bobiverse/build.yml" not in msg


def test_fr6487_local_or_remote_does_not_mask_parse_error(tmp_path: Path, monkeypatch):
    root = tmp_path / "packaged"
    root.mkdir()
    _write_yaml_recipe(
        root,
        "machine: flamingo\nsuites:\n  - name: c\n    cmd: true\n",
    )
    monkeypatch.setattr(bb, "yaml", None)
    remote_calls: list = []

    def gh(*a, **k):
        remote_calls.append(a)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    try:
        bb.load_bobiverse_recipe_local_or_remote(
            [root],
            "SimonBarnett/bobiverse",
            ref="main",
            gh_runner=gh,
        )
        assert False, "expected RecipeError"
    except bb.RecipeError as exc:
        assert "PyYAML" in str(exc)
    assert remote_calls == [], "must not fall through to remote when local file exists"


def test_fr6487_decide_build_surfaces_pyyaml_error(tmp_path: Path, monkeypatch):
    who = cc.Principal("owner", "simon", "simon")
    lock = bb.BuildLock(tmp_path / "locks.json")
    root = tmp_path / "install"
    root.mkdir()
    _write_yaml_recipe(
        root,
        "machine: flamingo\nsuites:\n  - name: c\n    cmd: true\n",
    )
    monkeypatch.setattr(bb, "yaml", None)

    def loader(repo: str):
        return bb.load_recipe_from_candidates([root], repo=repo)

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.0",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader,
        lock=lock,
    )
    assert dec is not None
    joined = "\n".join(dec.pm_lines)
    assert "PyYAML" in joined
    assert "no .bobiverse/build.yml" not in joined


def test_fr6487_build_scripts_pin_yaml_hidden_import():
    root = Path(__file__).resolve().parents[2]
    jeeves = (root / "jeeves" / "scripts" / "Build-Jeeves.ps1").read_text(encoding="utf-8")
    ear = (root / "bob" / "scripts" / "Build-BobEar.ps1").read_text(encoding="utf-8")
    req = (root / "common" / "requirements-freeze.txt").read_text(encoding="utf-8")
    assert "yaml" in jeeves and "hidden-import" in jeeves
    assert "collect-all" in jeeves
    assert "--hidden-import" in ear or "hidden-import" in ear
    assert "yaml" in ear
    assert "FR #6487" in jeeves
    assert "FR #6487" in ear
    assert "PyYAML" in req
    assert (root / "common" / "scripts" / "assert_jeeves_yaml_embed.py").is_file()


def test_fr6487_irc_agent_build_v1_logs_recipe_error():
    src = (
        Path(__file__).resolve().parents[1] / "scripts" / "irc_agent.py"
    ).read_text(encoding="utf-8")
    assert "FR #6487" in src
    assert "WARN BUILD v1 recipe load" in src or "WARN build v1 recipe" in src.lower()
    # Must not quietly assign ionos after a bare except on load_recipe alone.
    assert "load_recipe_from_candidates" in src or "recipe load failed" in src.lower()
