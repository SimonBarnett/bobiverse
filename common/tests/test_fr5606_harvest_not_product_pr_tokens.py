"""FR #5606: harvest twin must not link a product FR tip via generic tokens.

Live incident: after MRB #5599, Invoke-BobiverseHarvest returned
url=.../pull/5601 (product FR #5587 NETWORK ou tip) for a CredMan
apply_as/wrote-bool lesson. FR #5569 already skips non-lesson PRs in
find_open_harvest_lesson_twin; this FR hardens the matcher so a full
product PR body is never treated as a lesson bullet, and common verbs
(return/none/true/bool) are not distinctive twin tokens.
"""
from __future__ import annotations

from pathlib import Path

import intake

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
CREDMAN_LESSON = (
    "FR #5585 MRB: when apply returns wrote bool, CredMan "
    "default_apply_force_install_as must return that bool too — "
    "void/None makes _apply_wrote claim wrote=True"
)
PRODUCT_5601 = {
    "repo": REPO,
    "number": 5601,
    "title": "FR #5587: NETWORK ou is parent-container DN",
    "body": (
        "## Summary\n"
        "- `ou_from_dn` returns the parent-container DN "
        "(strip leaf RDN at first unescaped comma).\n"
        "- `CN=REDQUEEN,CN=Computers,DC=...` -> `CN=Computers,DC=...` "
        "(no longer domain-root-only).\n\n"
        "Closes SimonBarnett/bobiverse#5587\n\n"
        "Duplicates closed: none (searched: NETWORK ou CN=Computers domain root)\n\n"
        "## Evidence\n"
        "- Fail-first: `CN=Computers` case returned `DC=wonderland,DC=local`; "
        "after fix returns full parent container.\n"
    ),
    "labels": [],
    "url": f"https://github.com/{REPO}/pull/5601",
    "branch": "fr-5587",
    "draft": False,
}


class _AllOpenPullsFiler(intake.FakeGitHubFiler):
    def list_open_pulls(self, repo: str) -> list[dict]:
        return [
            r
            for r in self.prs
            if str(r.get("repo") or "") == repo and not r.get("closed")
        ]


def test_fr5606_generic_tokens_do_not_cover_unrelated_product_body():
    """return/returns/none alone must not twin CredMan lesson to NETWORK tip."""
    assert not intake.harvest_pr_covers_new_lesson(
        PRODUCT_5601["title"],
        PRODUCT_5601["body"],
        CREDMAN_LESSON,
        new_title="harvest: MRB #5599 PASS: FR #5585 CredMan apply_as wrote bool",
    )
    assert not intake._harvest_pr_matches_lessons(
        PRODUCT_5601,
        [CREDMAN_LESSON],
        new_title="harvest: MRB #5599 PASS: FR #5585 CredMan apply_as wrote bool",
    )


def test_fr5606_product_pr_not_open_twin_even_if_filter_bypassed_shape():
    """Open-twin helper still returns None for the product tip."""
    filer = _AllOpenPullsFiler()
    filer.prs.append(dict(PRODUCT_5601))
    hit = intake.find_open_harvest_lesson_twin(
        filer,
        REPO,
        [CREDMAN_LESSON],
        seat="redqueen-15876",
        new_title="harvest: MRB #5599 PASS CredMan",
    )
    assert hit is None


def test_fr5606_file_submission_opens_lesson_not_product_5601(tmp_path: Path):
    filer = _AllOpenPullsFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n\n## Harvested lessons (intake)\n"
    filer.prs.append(dict(PRODUCT_5601))
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #5599 PASS: FR #5585 CredMan apply_as wrote bool",
            "body": (
                "Session summary:\nMRB #5599 PASS CredMan\n\n"
                f"Lessons:\n- {CREDMAN_LESSON}\n"
            ),
            "idempotency_key": "hv-fr5606-a",
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
                "machine": "redqueen",
                "seat": "redqueen-15876",
            },
        }
    )
    assert err is None, err
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr5606a")
    assert rec["state"] == "filed"
    assert rec.get("url") != PRODUCT_5601["url"]
    assert rec.get("number") != 5601
    assert any(str(p.get("title") or "").startswith("lesson(") for p in filer.prs)


def test_fr5606_return_none_are_generic_tokens():
    for tok in ("return", "returns", "none", "true", "false", "void", "bool", "null"):
        assert tok in intake._HARVEST_GENERIC_TOKENS
