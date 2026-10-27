"""FR #5030: stamp require_machine=redqueen for a-search redeploy/monitor/log ops."""
from __future__ import annotations

import sys

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def test_fr5030_dedicated_body_pin_redqueen():
    assert (
        gitclaim.infer_require_machine(
            title="hasresults follow-up",
            body="require_machine: redqueen\n\nRedeploy live workers.",
            labels=("bug",),
            repo="SimonBarnett/a-search",
            ident="#5221",
        )
        == "redqueen"
    )
    assert (
        gitclaim.infer_require_machine(
            title="ops",
            body="require_machine = redqueen\n",
            labels=("feature-request",),
            repo="SimonBarnett/a-search",
        )
        == "redqueen"
    )


def test_fr5030_title_require_machine_equals_redqueen():
    assert (
        gitclaim.infer_require_machine(
            title="ops: require_machine=redqueen for hasresults redeploy",
            body="flamingo cannot run CloudWatch FilterLogEvents",
            labels=("via-intake",),
            repo="SimonBarnett/a-search",
        )
        == "redqueen"
    )


def test_fr5030_offer_gap_without_pin_title_does_not_self_pin():
    """FR #4422-class: meta 'without require_machine=redqueen' must stay offerable."""
    assert (
        gitclaim.infer_require_machine(
            title="offer gap: FR #5221 offered to flamingo without require_machine=redqueen",
            body="Chair should stamp; flamingo GIVEUP'd.",
            labels=("via-intake",),
            repo="SimonBarnett/a-search",
            ident="#5225",
        )
        == ""
    )


def test_fr5030_hasresults_monitor_cues():
    assert (
        gitclaim.infer_require_machine(
            title="install a-hasresults-monitor",
            body="Register-HasresultsMonitorService.ps1 after deploy",
            labels=("bug",),
            repo="SimonBarnett/a-search",
        )
        == "redqueen"
    )
    assert (
        gitclaim.infer_require_machine(
            title="FR: wire a-hasresults-monitor SEA",
            body="NSSM service on the box",
            labels=("feature-request",),
            repo="SimonBarnett/a-search",
        )
        == "redqueen"
    )


def test_fr5030_redeploy_live_workers_walrus_near_a_search():
    assert (
        gitclaim.infer_require_machine(
            title="Bug: hasresults not set; live workers still pre-#5198",
            body=(
                "Required: redeploy live workers and walrus on the a-search host; "
                "confirm provider Lambdas pick up _search-done."
            ),
            labels=("bug",),
            repo="SimonBarnett/a-search",
        )
        == "redqueen"
    )


def test_fr5030_filterlogevents_near_a_search():
    assert (
        gitclaim.infer_require_machine(
            title="verify ebay-live after deploy",
            body=(
                "Use CloudWatch FilterLogEvents on a-search provider-ebay-live "
                "and read a-sqlsearch / walrus drain logs."
            ),
            labels=("bug",),
            repo="SimonBarnett/a-search",
        )
        == "redqueen"
    )


def test_fr5030_bare_redqueen_mention_does_not_pin():
    assert (
        gitclaim.infer_require_machine(
            title="docs mention redqueen host layout",
            body="The redqueen box has an S: drive mapping for a-clubs.",
            labels=("docs",),
            repo="SimonBarnett/a-search",
        )
        == ""
    )


def test_fr5030_hard_pin_a_search_5221():
    assert (
        gitclaim.infer_require_machine(
            title="Bug: hasresults not set",
            body="short body without soft cues",
            labels=(),
            repo="SimonBarnett/a-search",
            ident="5221",
        )
        == "redqueen"
    )
    assert (
        gitclaim.infer_require_machine(
            title="Bug: hasresults not set",
            body="short body without soft cues",
            labels=(),
            repo="SimonBarnett/a-search",
            ident="#5221",
        )
        == "redqueen"
    )


def test_fr5030_bobiverse_soft_text_does_not_pin():
    """FR #4512: soft ops cues must not pin bobiverse; dedicated line still may."""
    assert (
        gitclaim.infer_require_machine(
            title="document a-hasresults-monitor offer gap",
            body="Register-HasresultsMonitorService evidence from a-search#5221",
            labels=("via-intake",),
            repo="SimonBarnett/bobiverse",
            ident="#5030",
        )
        == ""
    )
    assert (
        gitclaim.infer_require_machine(
            title="chair stamp",
            body="require_machine: redqueen\n\nAdd gitclaim cues.",
            labels=("feature-request",),
            repo="SimonBarnett/bobiverse",
            ident="#5030",
        )
        == "redqueen"
    )


def test_fr5030_stamp_persists_on_row():
    row = {
        "repo": "SimonBarnett/a-search",
        "id": "#5221",
        "title": "Bug: hasresults not set",
        "body": "short",
        "require_machine": "",
    }
    gitclaim._stamp_require_machine(row)
    assert row["require_machine"] == "redqueen"

def test_mrb5033_redeploy_live_workers_without_a_search_does_not_pin_other_repos():
    """Hostile: bare redeploy+live-workers must not stamp redqueen on non-a-search repos."""
    assert (
        gitclaim.infer_require_machine(
            title="redeploy live workers after patch",
            body="walrus restart needed on the formprep box",
            labels=("bug",),
            repo="SimonBarnett/agentic_fomprep",
        )
        == ""
    )
