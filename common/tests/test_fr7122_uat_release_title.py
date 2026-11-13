"""FR #7122: Priority Agent UAT titles/tags come from a deterministic helper."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import uat_release as ur


def test_priority_title_and_tag_not_uat_pass_date():
    plan = ur.plan_uat_pass_release(
        repo="SimonBarnett/priority-mcp",
        version="1.0.74",
        existing_tags=("uat-2026-11-06", "launcher-v1.0.74"),
        date="2026-11-13",
    )
    assert plan.title == "Priority Agent v1.0.75"
    assert plan.tag == "v1.0.75"
    assert plan.version == "1.0.75"
    assert "UAT PASS" not in plan.title
    assert "2026-11-13" not in plan.title
    assert "UAT PASS" in plan.notes
    assert "2026-11-13" in plan.notes


def test_alias_repo_same_product():
    plan = ur.plan_uat_pass_release(
        repo="SimonBarnett/agentic_fomprep",
        version="1.0.74",
        existing_tags=(),
        date="2026-11-13",
    )
    assert plan.title.startswith("Priority Agent v")
    assert plan.tag.startswith("v")


def test_increment_patch_from_version_file():
    assert ur.bump_patch("1.2.3") == "1.2.4"


def test_refuse_when_tag_exists():
    with pytest.raises(ur.UatReleaseError, match="tag already exists"):
        ur.plan_uat_pass_release(
            repo="SimonBarnett/priority-mcp",
            version="1.0.74",
            existing_tags=("v1.0.75",),
            date="2026-11-13",
        )


def test_refuse_when_not_greater_than_highest_v_tag():
    with pytest.raises(ur.UatReleaseError, match="not greater"):
        ur.plan_uat_pass_release(
            repo="SimonBarnett/priority-mcp",
            version="1.0.10",
            existing_tags=("v1.0.74",),
            date="2026-11-13",
        )


def test_other_repo_keeps_legacy_title():
    plan = ur.plan_uat_pass_release(
        repo="SimonBarnett/bobiverse",
        version="1.0.8",
        existing_tags=("v1.0.8",),
        date="2026-11-13",
    )
    assert plan.title.startswith("UAT PASS 2026-11-13")
    assert plan.tag.startswith("uat-2026-11-13")
    assert plan.product is None


def test_cli_json(tmp_path: Path, capsys):
    vf = tmp_path / "VERSION"
    vf.write_text("1.0.74\n", encoding="utf-8")
    rc = ur.main(
        [
            "--repo",
            "SimonBarnett/priority-mcp",
            "--version-file",
            str(vf),
            "--existing-tags",
            "launcher-v1.0.74,uat-2026-11-06",
            "--date",
            "2026-11-13",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["title"] == "Priority Agent v1.0.75"
    assert data["tag"] == "v1.0.75"
