"""FR #8490: builds catalog module + GET /bob/v1/builds webhook."""
from __future__ import annotations

import json
from pathlib import Path

import builds_catalog as bc
from bobcallback import handle_request


def _entry(**kwargs):
    base = {
        "name": "Bobiverse fleet MSI",
        "yml": "SimonBarnett/bobiverse:.bobiverse/build.yml",
        "output": r"D:\Temp\bobiverse-build",
        "install": "fleet",
        "dep": ["bob-ear", "bob-tray"],
        "version": "0.1.40",
        "ref": "main",
    }
    base.update(kwargs)
    return base


def test_parse_yml_field_default_and_explicit():
    repo, rel = bc.parse_yml_field("SimonBarnett/bobiverse")
    assert repo == "SimonBarnett/bobiverse"
    assert rel == ".bobiverse/build.yml"
    repo2, rel2 = bc.parse_yml_field("SimonBarnett/bobiverse:pack/build.yml")
    assert repo2 == "SimonBarnett/bobiverse"
    assert rel2 == "pack/build.yml"


def test_validate_entry_ok_and_required():
    entry, why = bc.validate_entry(_entry())
    assert why == ""
    assert entry is not None
    assert entry.name == "Bobiverse fleet MSI"
    assert entry.install == "fleet"
    assert entry.dep == ["bob-ear", "bob-tray"]
    assert entry.version == "0.1.40"
    assert entry.ref == "main"

    missing, why2 = bc.validate_entry({"name": "x"})
    assert missing is None
    assert "yml" in why2 or "missing" in why2


def test_validate_skips_bad_version_and_install():
    bad_ver, why = bc.validate_entry(_entry(version="v0.1.40"))
    assert bad_ver is None
    assert "version" in why
    bad_inst, why2 = bc.validate_entry(_entry(install="Not A Machine"))
    assert bad_inst is None
    assert "install" in why2
    ok_empty_ver, why3 = bc.validate_entry(_entry(version="", ref=""))
    assert ok_empty_ver is not None
    assert why3 == ""


def test_load_catalog_file_skips_bad_and_missing(tmp_path: Path):
    assert bc.load_catalog_file(tmp_path) == []
    path = tmp_path / bc.BUILDS_CATALOG_NAME
    path.write_text(
        json.dumps(
            [
                _entry(name="good"),
                _entry(name="", yml="bad"),
                _entry(name="also-good", install="flamingo", version="1.2.3.4"),
                "not-an-object",
            ]
        ),
        encoding="utf-8",
    )
    rows = bc.load_catalog_file(tmp_path)
    assert len(rows) == 2
    assert rows[0].name == "good"
    assert rows[1].install == "flamingo"
    assert rows[1].version == "1.2.3.4"


def test_expand_install_targets_fleet_and_single():
    roster = ["walrus", "flamingo", "walrus", "", "ionos"]
    assert bc.expand_install_targets("fleet", roster) == ["flamingo", "ionos", "walrus"]
    assert bc.expand_install_targets("flamingo", roster) == ["flamingo"]
    assert bc.expand_install_targets("", roster) == []


def test_entry_at_and_format_lines():
    entries = [
        bc.BuildCatalogEntry(
            name="A",
            yml="o/r",
            output=r"D:\Temp\a",
            install="fleet",
            dep=["x"],
            version="0.1.0",
            ref="main",
        ),
        bc.BuildCatalogEntry(
            name="B",
            yml="o/r2:.bobiverse/build.yml",
            output=r"D:\Temp\b",
            install="flamingo",
        ),
    ]
    assert bc.entry_at(entries, 1).name == "A"
    assert bc.entry_at(entries, 2).name == "B"
    assert bc.entry_at(entries, 0) is None
    assert bc.entry_at(entries, 3) is None
    lines = bc.format_catalog_lines(entries)
    assert lines[0] == "build catalog:"
    assert "1) A" in lines[1]
    assert "2) B" in lines[2]


def test_catalog_to_json_compact_public_shape():
    e = bc.BuildCatalogEntry(
        name="N",
        yml="SimonBarnett/bobiverse",
        output=r"D:\Temp\out",
        install="fleet",
        dep=["bob-ear"],
        version="0.1.40",
        ref="main",
    )
    raw = bc.catalog_to_json([e])
    assert b" " not in raw  # compact separators
    doc = json.loads(raw.decode("utf-8"))
    assert doc == [
        {
            "name": "N",
            "yml": "SimonBarnett/bobiverse",
            "output": r"D:\Temp\out",
            "install": "fleet",
            "dep": ["bob-ear"],
            "version": "0.1.40",
            "ref": "main",
        }
    ]


def test_handle_request_builds_get_and_head(tmp_path: Path):
    (tmp_path / bc.BUILDS_CATALOG_NAME).write_text(
        json.dumps([_entry(name="Via webhook")]),
        encoding="utf-8",
    )
    code, payload = handle_request(
        "GET",
        bc.BUILDS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    rows = json.loads(payload.decode("utf-8"))
    assert len(rows) == 1
    assert rows[0]["name"] == "Via webhook"
    assert rows[0]["yml"].startswith("SimonBarnett/bobiverse")

    code2, payload2 = handle_request(
        "HEAD",
        bc.BUILDS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code2 == 200
    assert payload2 == b""


def test_handle_request_builds_missing_file_empty_array(tmp_path: Path):
    code, payload = handle_request(
        "GET",
        "/bob/v1/builds",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    assert json.loads(payload.decode("utf-8")) == []


def test_default_builds_url_env(monkeypatch):
    monkeypatch.delenv(bc.BUILDS_URL_ENV, raising=False)
    assert bc.default_builds_url() == bc.DEFAULT_BUILDS_URL
    monkeypatch.setenv(bc.BUILDS_URL_ENV, "http://127.0.0.1:7700/bob/v1/builds")
    assert bc.default_builds_url() == "http://127.0.0.1:7700/bob/v1/builds"


def test_example_defaults_file_validates():
    example = (
        Path(__file__).resolve().parents[1] / "defaults" / "builds-catalog.example.json"
    )
    assert example.is_file()
    raw = json.loads(example.read_text(encoding="utf-8"))
    assert isinstance(raw, list) and raw
    for item in raw:
        entry, why = bc.validate_entry(item)
        assert entry is not None, why
        assert entry.install in ("fleet",) or entry.install
