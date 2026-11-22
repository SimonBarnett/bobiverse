"""FR #8490 slice C: !build numbered catalog UX (list / n / overrides / old-form refuse)."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import builds_catalog as bc
import chair_commands as cc
from repo_layout import ROOT

OWNER = cc.Principal("owner", "simon", "simon")


def _entry(**kw) -> bc.BuildCatalogEntry:
    return bc.BuildCatalogEntry(
        name=kw.get("name", "Bobiverse"),
        yml=kw.get("yml", "SimonBarnett/bobiverse:.bobiverse/build.yml"),
        output=kw.get("output", r"D:\Temp\bobiverse-build"),
        install=kw.get("install", "fleet"),
        dep=kw.get("dep", ["bob-ear", "bob-tray", "bob-worker"]),
        version=kw.get("version", "0.1.40"),
        ref=kw.get("ref", "main"),
    )


def _cat(*entries: bc.BuildCatalogEntry) -> list[bc.BuildCatalogEntry]:
    return list(entries) if entries else [_entry()]


def _decide(body: str, *, lock=None, loader=None, catalog=None, **kw):
    return bb.decide_build(
        who=OWNER,
        body=body,
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader or (lambda r: bb.load_recipe(ROOT)),
        lock=lock,
        catalog_entries=_cat() if catalog is None else catalog,
        new_build_id=lambda: "b-8490",
        **kw,
    )


def test_fr8490_parse_build_list_and_index():
    assert bb.parse_build("!build") == (True, "list", "")
    assert bb.parse_build("!build 1") == (True, "run", "1")
    assert bb.parse_build("!build 2 0.1.41 main") == (True, "run", "2 0.1.41 main")
    assert bb.parse_build("!build dry-run 1")[1] == "dry-run"
    assert bb.parse_build("!build status 1") == (True, "status", "1")
    assert bb.parse_build("!build cancel 1") == (True, "cancel", "1")
    assert bb.parse_build("!build SimonBarnett/bobiverse 0.1.40") == (
        True,
        "run",
        "SimonBarnett/bobiverse 0.1.40",
    )


def test_fr8490_list_empty_and_populated():
    empty = _decide("!build", catalog=[])
    assert empty and empty.ok and empty.reason == "list"
    assert any("catalog empty" in ln for ln in empty.pm_lines)

    dec = _decide("!build")
    assert dec and dec.ok and dec.reason == "list"
    joined = "\n".join(dec.pm_lines)
    assert "1) Bobiverse" in joined
    # FR #8770: list rows omit yml=/dep=/output= (those stay in dry-run).
    assert "yml=" not in joined
    assert "dep=" not in joined
    assert "SimonBarnett/bobiverse" in joined
    assert "install=fleet" in joined
    assert dec.pm_lines[-2:] == list(bb.BUILD_USAGE_LINES)

    dry = _decide("!build dry-run 1")
    assert dry and dry.ok and dry.dry_run
    dry_joined = "\n".join(dry.pm_lines)
    assert "dep=bob-ear,bob-tray,bob-worker" in dry_joined
    assert "output=" in dry_joined


def test_fr8490_run_index_uses_catalog_defaults(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    dec = _decide("!build 1", lock=lock)
    assert dec and dec.ok
    assert dec.catalog_index == 1
    assert dec.catalog_name == "Bobiverse"
    assert dec.version == "0.1.40"
    assert dec.ref == "main"
    assert dec.output == r"D:\Temp\bobiverse-build"
    assert dec.install == "fleet"
    assert "output=D:\\Temp\\bobiverse-build" in dec.route or "output=D:/Temp/bobiverse-build" in dec.route.replace(
        "\\", "/"
    )
    assert "install=fleet" in dec.route
    assert lock.running_id("SimonBarnett/bobiverse") == "b-8490"


def test_fr8490_run_version_ref_override(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    dec = _decide("!build 1 2.0.0 feature-x", lock=lock)
    assert dec and dec.ok
    assert dec.version == "2.0.0"
    assert dec.ref == "feature-x"
    assert "version=2.0.0" in dec.route and "ref=feature-x" in dec.route


def test_fr8490_old_owner_repo_refused():
    dec = _decide("!build SimonBarnett/bobiverse 0.1.40")
    assert dec and not dec.ok and dec.reason == "usage"
    assert any("owner/repo form removed" in ln for ln in dec.pm_lines)
    assert dec.route == ""


def test_fr8490_bad_index_refused():
    dec = _decide("!build 9")
    assert dec and not dec.ok and dec.reason == "bad_index"
    assert any("no catalog entry 9" in ln for ln in dec.pm_lines)


def test_fr8490_dry_run_status_cancel_preflight(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    dry = _decide("!build dry-run 1", lock=lock)
    assert dry and dry.ok and dry.dry_run
    assert lock.running_id("SimonBarnett/bobiverse") is None
    assert any("machine=" in ln and "build dry-run:" in ln for ln in dry.pm_lines)

    lock.try_acquire("SimonBarnett/bobiverse", "b-live")
    st = _decide("!build status 1", lock=lock)
    assert st and st.status_only and "b-live" in " ".join(st.pm_lines)

    cancel = _decide("!build cancel 1", lock=lock)
    assert cancel and cancel.cancel
    assert lock.running_id("SimonBarnett/bobiverse") is None

    pre = _decide("!build preflight 1", lock=lock)
    assert pre and pre.ok and pre.reason == "preflight"
    assert pre.route == "BUILDPREFLIGHT v1 repo=SimonBarnett/bobiverse"


def test_fr8490_build_v1_route_parses_output_install():
    d = bb.parse_build_v1_route(
        "BUILD v1 repos=SimonBarnett/bobiverse version=0.1.40 ref=main "
        "id=b-1 output=D:\\Temp\\out install=fleet"
    )
    assert d is not None
    assert d["output"].replace("/", "\\") == r"D:\Temp\out"
    assert d["install"] == "fleet"


def test_fr8490_help_syntax_mentions_catalog():
    spec = cc.get_command("build")
    assert "!build n" in spec.syntax or "!build |" in spec.syntax
    assert "8490" in (spec.details or "") or "catalog" in (spec.details or "").lower()
    detail = "\n".join(cc.build_help(OWNER, "build"))
    assert "!build 1" in detail or "numbered" in detail.lower() or "catalog" in detail.lower()
