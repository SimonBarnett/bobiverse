"""FR #10079: catalog build lists public Bob skills."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bob_skill_catalog as cat  # noqa: E402

REPO = ROOT.parent


def test_build_lists_name_title_description(tmp_path: Path):
    skill = tmp_path / "bob-shop" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\nname: bob-shop\ndescription: >\n  Shop wire for a Bob seat.\n---\n\n# Shop wire\n\nbody\n",
        encoding="utf-8",
    )
    doc = cat.build_catalog([tmp_path])
    assert doc["skills"] == [
        {
            "name": "bob-shop",
            "title": "Shop wire",
            "description": "Shop wire for a Bob seat.",
        }
    ]
    loaded = cat.load_skill([tmp_path], "bob-shop")
    assert loaded is not None
    assert loaded["skillMd"].startswith("---")
    assert "body" in loaded["skillMd"]


def test_secret_shaped_skill_is_omitted(tmp_path: Path):
    skill = tmp_path / "leaky" / "SKILL.md"
    skill.parent.mkdir()
    marker = "pass" + "word=" + "EXAMPLE"
    skill.write_text(
        "---\nname: leaky\ndescription: no\n---\n\n" + marker + "\n",
        encoding="utf-8",
    )
    assert cat.build_catalog([tmp_path])["skills"] == []
    assert cat.load_skill([tmp_path], "leaky") is None


def test_repo_job_irc_skill_is_public():
    roots = [
        REPO / "bob" / ".grok" / "skills",
        REPO / "jeeves" / ".grok" / "skills",
        REPO / "common" / ".grok" / "skills",
    ]
    doc = cat.build_catalog(roots)
    names = {row["name"] for row in doc["skills"]}
    assert "bobiverse-bob-job-irc" in names
    row = next(r for r in doc["skills"] if r["name"] == "bobiverse-bob-job-irc")
    assert row["title"]
    assert row["description"]
    loaded = cat.load_skill(roots, "bobiverse-bob-job-irc")
    assert loaded is not None
    assert "ACK" in loaded["skillMd"]
    blob = json.dumps(doc)
    assert "github_pat_" not in blob
    assert "ghp_" not in blob
