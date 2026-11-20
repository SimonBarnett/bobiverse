"""#4186: !build refuses non-numeric versions (WiX needs numeric ProductVersion).

FR #8490: decide_build uses numbered catalog (!build n); old owner/repo refused.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "scripts"))
import bobiverse_build as bb  # noqa: E402
import builds_catalog as bc  # noqa: E402
import chair_commands  # noqa: E402


class _Lock:
    def __init__(self):
        self.acquired = []

    def try_acquire(self, repo, bid):
        self.acquired.append(repo)
        return True, bid


def _entry(**kw) -> bc.BuildCatalogEntry:
    return bc.BuildCatalogEntry(
        name=kw.get("name", "Bobiverse"),
        yml=kw.get("yml", "SimonBarnett/bobiverse:.bobiverse/build.yml"),
        output=kw.get("output", r"D:\Temp\bobiverse-build"),
        install=kw.get("install", "fleet"),
        dep=kw.get("dep", []),
        version=kw.get("version", "0.1.40"),
        ref=kw.get("ref", "HEAD"),
    )


@pytest.mark.parametrize("v", ["0.1.32", "0.1.32.1"])
def test_numeric_versions_accepted(v):
    assert bb.version_refusal(v) is None


@pytest.mark.parametrize("v", ["0.1.32-test2", "v0.1.32", "", "0.1", "0.1.32.1.2", "0.1.x"])
def test_non_numeric_versions_refused(v):
    line = bb.version_refusal(v)
    assert line and "refused" in line and "numeric" in line


@pytest.mark.parametrize("v", ["0.1.32-test2", "v0.1.32"])
def test_decide_build_refuses_before_lock_or_recipe(v):
    lock = _Lock()
    loads = []
    dec = bb.decide_build(
        who=object(),
        body=f"!build 1 {v}",
        may=lambda *a: True,
        denied_line=lambda c: "denied",
        recipe_loader=lambda r: loads.append(r),
        lock=lock,
        catalog_entries=[_entry()],
    )
    assert dec is not None and not dec.ok and dec.reason == "bad_version"
    assert not dec.route and not lock.acquired and not loads
    assert "numeric" in dec.pm_lines[0]


def test_decide_build_empty_version_not_queued():
    lock = _Lock()
    dec = bb.decide_build(
        who=object(),
        body="!build 1",
        may=lambda *a: True,
        denied_line=lambda c: "denied",
        recipe_loader=lambda r: None,
        lock=lock,
        catalog_entries=[_entry(version="")],
    )
    assert dec is not None and not dec.ok and not dec.route and not lock.acquired


@pytest.mark.parametrize("v", ["0.1.32", "0.1.32.1"])
def test_decide_build_queues_numeric(v):
    lock = _Lock()
    dec = bb.decide_build(
        who=object(),
        body=f"!build 1 {v}",
        may=lambda *a: True,
        denied_line=lambda c: "denied",
        recipe_loader=lambda r: bb.BuildRecipe(machine="ionos"),
        lock=lock,
        catalog_entries=[_entry()],
        new_build_id=lambda: "b-1",
    )
    assert dec.ok
    assert f"version={v}" in dec.route
    assert "repos=SimonBarnett/bobiverse" in dec.route
    assert "id=b-1" in dec.route
    assert dec.catalog_index == 1


def test_help_documents_numeric_version():
    text = Path(chair_commands.__file__).read_text(encoding="utf-8")
    assert "x.y.z or x.y.z.w" in text
