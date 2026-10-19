"""FR #4725: default resync-repos.txt includes SimonBarnett/ce-priority."""
from __future__ import annotations

from pathlib import Path

import chair_health as ch
from repo_layout import ROOT


def test_default_resync_repos_includes_ce_priority():
    assert "SimonBarnett/ce-priority" in ch.DEFAULT_RESYNC_REPOS
    for name in (
        "SimonBarnett/a-search",
        "SimonBarnett/agentic_fomprep",
        "SimonBarnett/bobiverse",
        "SimonBarnett/xai-cookbook",
        "SimonBarnett/Club-Madeira",
        "SimonBarnett/ce-priority",
    ):
        assert name in ch.DEFAULT_RESYNC_REPOS


def test_ensure_creates_file_with_ce_priority(tmp_path: Path):
    path = ch.ensure_resync_repos_file(tmp_path)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "SimonBarnett/ce-priority" in text
    assert "SimonBarnett/a-search" in text
    assert text.startswith("#")


def test_ensure_merges_ce_priority_into_existing_list(tmp_path: Path):
    path = tmp_path / ch.RESYNC_REPOS_NAME
    path.write_text(
        "# list\nSimonBarnett/a-search\nSimonBarnett/bobiverse\n",
        encoding="utf-8",
    )
    ch.ensure_resync_repos_file(tmp_path)
    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert "SimonBarnett/a-search" in lines
    assert "SimonBarnett/bobiverse" in lines
    assert "SimonBarnett/ce-priority" in lines
    assert lines.count("SimonBarnett/a-search") == 1


def test_ensure_does_not_drop_operator_extras(tmp_path: Path):
    path = tmp_path / ch.RESYNC_REPOS_NAME
    path.write_text("SimonBarnett/custom-extra\nSimonBarnett/ce-priority\n", encoding="utf-8")
    ch.ensure_resync_repos_file(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "SimonBarnett/custom-extra" in text
    assert "SimonBarnett/ce-priority" in text
    assert "SimonBarnett/a-search" in text


def test_chair_jobs_seeds_both_homes(tmp_path: Path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    ch.ChairJobs(
        chair,
        digest,
        log=lambda s: None,
        announce=lambda s: None,
        http=lambda *a, **k: 200,
        token_loader=lambda: ("", "none"),
        clock=lambda: 0.0,
        sleep=lambda s: None,
        spawn=False,
    )
    for home in (chair, digest):
        text = (home / ch.RESYNC_REPOS_NAME).read_text(encoding="utf-8")
        assert "SimonBarnett/ce-priority" in text


def test_pack_default_file_lists_ce_priority():
    pack = ROOT / "jeeves" / "defaults" / "resync-repos.txt"
    if not pack.is_file():
        pack = ROOT / "defaults" / "resync-repos.txt"
    assert pack.is_file(), "jeeves/defaults/resync-repos.txt missing from pack"
    text = pack.read_text(encoding="utf-8")
    assert "SimonBarnett/ce-priority" in text
    for name in ch.DEFAULT_RESYNC_REPOS:
        assert name in text


def test_install_jeeves_mentions_fr4725_seed():
    inst = ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1"
    if not inst.is_file():
        inst = ROOT / "scripts" / "Install-Jeeves.ps1"
    text = inst.read_text(encoding="utf-8")
    assert "4725" in text
    assert "ensure_resync_repos_file" in text or "resync-repos.txt" in text


def test_pack_stages_resync_repos_defaults():
    pack = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
    if not pack.is_file():
        pack = ROOT / "scripts" / "Pack-BobiverseRelease.ps1"
    text = pack.read_text(encoding="utf-8")
    assert "4725" in text
    assert "defaults\\resync-repos.txt" in text or "defaults/resync-repos.txt" in text
