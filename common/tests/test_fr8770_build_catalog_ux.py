"""FR #8770: !build catalog UX — usage constant, auto version, local-first, yml path."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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
        dep=kw.get("dep", ["bob-ear"]),
        version=kw.get("version", ""),
        ref=kw.get("ref", ""),
    )


def _four_catalog() -> list[bc.BuildCatalogEntry]:
    return [
        _entry(name="Bobiverse fleet MSI", yml="SimonBarnett/bobiverse", install="fleet"),
        _entry(name="Bobiverse flamingo", yml="SimonBarnett/bobiverse", install="flamingo"),
        _entry(
            name="Priority Agent",
            yml="SimonBarnett/priority-mcp",
            install="flamingo",
            output=r"D:\Temp\priority",
        ),
        _entry(
            name="Plan Agent",
            yml="SimonBarnett/skills-visionary",
            install="flamingo",
            output=r"D:\Temp\plan",
        ),
    ]


def _decide(body: str, *, lock=None, loader=None, catalog=None, **kw):
    return bb.decide_build(
        who=OWNER,
        body=body,
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader or (lambda r, rel="": bb.load_recipe(ROOT)),
        lock=lock,
        catalog_entries=_four_catalog() if catalog is None else catalog,
        new_build_id=lambda: "b-8770",
        **kw,
    )


def test_fr8770_usage_constant_identity():
    assert bb.BUILD_USAGE_LINES is bc.BUILD_USAGE_LINES
    spec = cc.get_command("build")
    assert spec.usage_lines is bc.BUILD_USAGE_LINES
    assert "!build |" in spec.syntax


def test_fr8770_four_entry_list_rows_bounded_and_footer():
    calls: list[str] = []

    def resolver(repo: str):
        calls.append(repo)
        return "2.0.2"

    dec = _decide("!build", version_resolver=resolver)
    assert dec and dec.ok and dec.reason == "list"
    rows = [ln for ln in dec.pm_lines if ln.startswith("  ")]
    assert len(rows) == 4
    for ln in rows:
        assert len(ln.encode("utf-8")) <= 400
        assert "yml=" not in ln
        assert "dep=" not in ln
        assert "output=" not in ln
        assert "version=next:2.0.2" in ln
    assert dec.pm_lines[-2:] == list(bc.BUILD_USAGE_LINES)
    # Duplicate SimonBarnett/bobiverse looked up once.
    assert calls.count("SimonBarnett/bobiverse") == 1
    assert len(calls) == 3


def test_fr8770_help_and_bad_input_usage_no_lock(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    loaded = {"n": 0}

    def loader(repo, rel=""):
        loaded["n"] += 1
        return bb.load_recipe(ROOT)

    help_dec = _decide("!build help", lock=lock, loader=loader, catalog=[])
    assert help_dec and help_dec.ok and help_dec.reason == "help"
    assert help_dec.pm_lines == list(bc.BUILD_USAGE_LINES)
    assert help_dec.route == ""
    assert loaded["n"] == 0
    assert lock.running() == []

    bad = _decide("!build dry-run", catalog=[], loader=loader)
    assert bad and not bad.ok and bad.reason == "usage"
    assert bad.pm_lines == list(bc.BUILD_USAGE_LINES)


def test_fr8770_help_detail_uses_usage_lines():
    lines = cc.build_help(OWNER, "build")
    assert lines[0] == bc.BUILD_USAGE_LINES[0] or lines[0].startswith("build:")
    assert any("next patch" in ln or "version default" in ln for ln in lines[:2])
    assert len(lines) <= cc.HELP_DETAIL_MAX_LINES


def test_fr8770_version_resolver_next_patch(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    cat = [_entry(name="X", version="", yml="SimonBarnett/bobiverse")]
    dec = _decide(
        "!build 1",
        lock=lock,
        catalog=cat,
        version_resolver=lambda r: "2.0.2",
    )
    assert dec and dec.ok
    assert dec.version == "2.0.2"
    assert "version=2.0.2" in dec.route
    assert lock.running_id("SimonBarnett/bobiverse") == "b-8770"


def test_fr8770_next_patch_from_v_tags_pure():
    assert bb.next_patch_from_v_tags(["v2.0.1", "v1.9.9"]) == "2.0.2"
    assert bb.next_patch_from_v_tags(["v1.2.3.4"]) == "1.2.3.5"
    # Prefer longer arity on equal numeric prefix.
    assert bb.next_patch_from_v_tags(["v1.2.3", "v1.2.3.0"]) == "1.2.3.1"
    # Ignore prerelease / no-v / malformed.
    assert bb.next_patch_from_v_tags(["v2.0.1-rc1", "2.0.1", "v2.0", "refs/tags/v2.0.0"]) == "2.0.1"
    assert bb.next_patch_from_v_tags([]) is None
    assert bb.next_patch_from_v_tags(["v1.0.0-beta", "latest"]) is None


def test_fr8770_no_tags_refusal_and_tag_lookup_error(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    cat = [_entry(name="X", version="")]

    none_dec = _decide(
        "!build 1",
        lock=lock,
        catalog=cat,
        version_resolver=lambda r: None,
    )
    assert none_dec and not none_dec.ok
    assert "has no version" in none_dec.pm_lines[0]
    assert lock.running_id("SimonBarnett/bobiverse") is None

    def boom(_repo):
        raise bb.TagLookupError("timeout after 8.0s")

    err_dec = _decide("!build 1", lock=lock, catalog=cat, version_resolver=boom)
    assert err_dec and not err_dec.ok and err_dec.reason == "tag_lookup"
    assert "tag lookup failed" in err_dec.pm_lines[0]
    assert lock.running_id("SimonBarnett/bobiverse") is None


def test_fr8770_list_remote_v_tags_injectable():
    payload = json.dumps(
        [
            {"ref": "refs/tags/v2.0.1"},
            {"ref": "refs/tags/v2.0.0"},
            {"ref": "refs/tags/v2.0.1-rc1"},
        ]
    )

    def runner(args, **kw):
        return SimpleNamespace(returncode=0, stdout=payload, stderr="")

    tags = bb.list_remote_v_tags("SimonBarnett/bobiverse", gh_runner=runner)
    assert "v2.0.1" in tags and "v2.0.0" in tags
    assert bb.resolve_next_build_version("o/r", gh_runner=runner) == "2.0.2"

    def fail(args, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 404: Not Found")

    try:
        bb.list_remote_v_tags("o/r", gh_runner=fail)
        assert False, "expected TagLookupError"
    except bb.TagLookupError:
        pass


def test_fr8770_bare_status_idle_and_running(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    idle = _decide("!build status", lock=lock, catalog=_four_catalog())
    assert idle and idle.ok and idle.pm_lines == ["build: no build running"]

    lock.try_acquire("SimonBarnett/bobiverse", "b-live")
    lock.try_acquire("OtherOrg/missing", "b-x")
    # max_parallel=1 may refuse second — use fresh lock with higher parallel
    lock2 = bb.BuildLock(tmp_path / "l2.json", max_parallel=2)
    lock2.try_acquire("SimonBarnett/bobiverse", "b-live")
    lock2.try_acquire("OtherOrg/missing", "b-x")
    st = _decide("!build status", lock=lock2, catalog=_four_catalog())
    assert st and st.ok
    joined = "\n".join(st.pm_lines).lower()
    # BuildLock stores normalize_repo keys (lower-case owner/repo).
    assert "running simonbarnett/bobiverse" in joined
    assert "entries=1,2" in joined
    assert "running otherorg/missing" in joined
    assert "entries=-" in joined
    assert "age=" in joined and "seen=" in joined


def test_fr8770_local_first_catalog_helper(tmp_path: Path):
    digest = tmp_path / "digest"
    chair = tmp_path / "chair"
    digest.mkdir()
    chair.mkdir()
    http_calls = {"n": 0}

    def http():
        http_calls["n"] += 1
        return [_entry(name="from-http", version="9.9.9")]

    # Empty locals → HTTP.
    rows = bc.load_catalog_entries_local_first([digest, chair], http_fetcher=http)
    assert len(rows) == 1 and rows[0].name == "from-http"
    assert http_calls["n"] == 1

    (digest / bc.BUILDS_CATALOG_NAME).write_text(
        json.dumps(
            [
                {
                    "name": "local",
                    "yml": "SimonBarnett/bobiverse",
                    "output": r"D:\Temp\x",
                    "install": "fleet",
                    "dep": [],
                    "version": "",
                    "ref": "",
                }
            ]
        ),
        encoding="utf-8",
    )
    http_calls["n"] = 0
    rows2 = bc.load_catalog_entries_local_first([digest, chair], http_fetcher=http)
    assert len(rows2) == 1 and rows2[0].name == "local"
    assert http_calls["n"] == 0

    def boom():
        raise TimeoutError("down")

    rows3 = bc.load_catalog_entries_local_first(
        [tmp_path / "empty1", tmp_path / "empty2"],
        http_fetcher=boom,
    )
    assert rows3 == []


def test_fr8770_custom_yml_route_and_legacy_parse(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    seen: dict = {}

    def loader(repo, rel=""):
        seen["rel"] = rel
        return bb.load_recipe(ROOT)

    cat = [
        _entry(
            name="Custom",
            yml="SimonBarnett/bobiverse:pack/build.yml",
            version="1.2.3",
        )
    ]
    dec = _decide("!build 1", lock=lock, catalog=cat, loader=loader)
    assert dec and dec.ok
    assert seen.get("rel") == "pack/build.yml"
    assert "recipe=pack/build.yml" in dec.route

    legacy = bb.parse_build_v1_route(
        "BUILD v1 repos=SimonBarnett/bobiverse version=1.2.3 ref=HEAD id=b-1"
    )
    assert legacy is not None
    assert legacy.get("recipe_rel") == ""

    with_recipe = bb.parse_build_v1_route(
        "BUILD v1 repos=SimonBarnett/bobiverse version=1.2.3 ref=HEAD "
        "id=b-1 recipe=pack/build.yml"
    )
    assert with_recipe is not None
    assert with_recipe["recipe_rel"] == "pack/build.yml"

    job = bb.enqueue_build_job(with_recipe, queue_dir=tmp_path, local_machine="flamingo")
    payload = json.loads(job.read_text(encoding="utf-8"))
    assert payload["recipe_rel"] == "pack/build.yml"


def test_fr8770_yml_traversal_rejected():
    bad, why = bc.validate_entry(
        {
            "name": "bad",
            "yml": "SimonBarnett/bobiverse:../etc/passwd",
            "output": r"D:\Temp\x",
            "install": "fleet",
        }
    )
    assert bad is None
    assert "yml" in why.lower() or "path" in why.lower() or "segment" in why.lower()

    try:
        bc.parse_yml_field("o/r:foo/../../etc")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_fr8770_multibyte_name_clip():
    name = "名" * 200
    entries = [
        _entry(name=name, yml="o/r", version="1.0.0", ref="main", install="fleet")
    ]
    lines = bc.format_catalog_lines(entries)
    row = lines[1]
    assert len(row.encode("utf-8")) <= 400
    # Must not raise on decode — clip is codepoint-safe.
    row.encode("utf-8").decode("utf-8")


def test_fr8770_fetch_remote_recipe_encodes_rel():
    seen: list[str] = []
    yml = (
        "machine: flamingo\n"
        "suites:\n"
        "  - name: unit\n"
        "    cmd: python -m pytest -q\n"
    )

    def runner(args, **kw):
        seen.append(" ".join(args))
        return SimpleNamespace(returncode=0, stdout=yml, stderr="")

    recipe = bb.fetch_remote_recipe(
        "SimonBarnett/bobiverse", rel="pack/build.yml", gh_runner=runner
    )
    assert recipe is not None
    assert recipe.machine == "flamingo"
    assert seen
    assert "contents/pack/build.yml" in seen[0]
