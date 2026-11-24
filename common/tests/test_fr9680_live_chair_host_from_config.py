"""FR #9680: live chair host from BOB_CHAIR_MACHINE / JEEVES_CHAIR_HOST, not a hard-coded walrus."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import jeeves_chair_host as jch


def test_fr9680_no_hardcoded_live_chair_constant():
    src = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "_LIVE_CHAIR_HOST =" not in src
    assert "def live_chair_host(" in src
    assert "BOB_CHAIR_MACHINE" in src or "CHAIR_ENV" in src


def test_fr9680_live_chair_host_reads_bob_chair_machine(monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "NewChair")
    monkeypatch.delenv("JEEVES_CHAIR_HOST", raising=False)
    assert gitclaim.live_chair_host() == "newchair"


def test_fr9680_live_chair_host_falls_back_to_jeeves_chair_host(monkeypatch):
    monkeypatch.delenv("BOB_CHAIR_MACHINE", raising=False)
    monkeypatch.setenv("JEEVES_CHAIR_HOST", "AltChair")
    assert gitclaim.live_chair_host() == "altchair"


def test_fr9680_legacy_aliases_fold_to_configured_host(monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "newchair")
    monkeypatch.delenv("JEEVES_CHAIR_HOST", raising=False)
    assert gitclaim.fold_chair_host("ionos") == "newchair"
    assert gitclaim.fold_chair_host("bob-ionos") == "newchair"
    assert gitclaim.fold_chair_host("walrus") == "newchair"
    assert gitclaim.fold_chair_host("newchair") == "newchair"
    assert gitclaim.fold_chair_host("flamingo") == "flamingo"


def test_fr9680_needs_walrus_label_stamps_configured_host(monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "newchair")
    monkeypatch.delenv("JEEVES_CHAIR_HOST", raising=False)
    assert (
        gitclaim.infer_require_machine(
            title="chair compose",
            labels=("needs-walrus",),
            repo="SimonBarnett/other",
        )
        == "newchair"
    )
    assert (
        gitclaim.infer_require_machine(
            title="chair compose",
            labels=("needs-ionos",),
            repo="SimonBarnett/other",
        )
        == "newchair"
    )
    assert (
        gitclaim.infer_require_machine(
            title="Sync ircJeeves allowlist",
            body="ops note\n",
            labels=("needs-walrus",),
            repo="SimonBarnett/bobiverse",
        )
        == "newchair"
    )


def test_fr9680_title_cue_folds_to_configured_host(monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "newchair")
    monkeypatch.delenv("JEEVES_CHAIR_HOST", raising=False)
    assert (
        gitclaim.infer_require_machine(
            title="recycle ircJeeves after wedge",
            body="",
            repo="SimonBarnett/other",
        )
        == "newchair"
    )


def test_fr9680_default_still_walrus_when_env_unset(monkeypatch):
    monkeypatch.delenv("BOB_CHAIR_MACHINE", raising=False)
    monkeypatch.delenv("JEEVES_CHAIR_HOST", raising=False)
    assert gitclaim.live_chair_host() == jch.DEFAULT_CHAIR_HOST
    assert gitclaim.fold_chair_host("ionos") == jch.DEFAULT_CHAIR_HOST
