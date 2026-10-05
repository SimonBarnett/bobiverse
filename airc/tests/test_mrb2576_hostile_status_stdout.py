"""Hostile MRB #2576 / FR #2575: STATUS out framing must match ConvertFrom-AircRemoteReply.

Additive gates after product merge: prove the STATUS out line shape is accepted by the
Invoke-AircRemote reply regex (the live gap was Wait OK + empty StdOut).
"""
from __future__ import annotations

import re
from pathlib import Path

import airc_jobs as jobs
from repo_layout import ROOT

INV = ROOT / "airc" / "scripts" / "Invoke-AircRemote.ps1"
OUT_RE = re.compile(
    r"^(?P<stream>out|err)\s+id=(?P<id>[0-9a-f]+)\s+seq=(?P<seq>\d+)\s(?P<body>.*)$"
)


def _versions(tmp_path: Path) -> None:
    for name in ("bob", "airc", "jeeves"):
        d = tmp_path / name
        d.mkdir()
        (d / "VERSION").write_text("2.0.0\n", encoding="utf-8")


def test_status_out_line_matches_invoke_convertfrom_regex(tmp_path):
    _versions(tmp_path)
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store, ai_root=tmp_path, machine="mh", airc_running=True)
    lines = proto.handle("bob-mh", "STATUS", {"id": "deadbeef"})
    m = OUT_RE.match(lines[0])
    assert m is not None, lines[0]
    assert m.group("stream") == "out"
    assert m.group("id") == "deadbeef"
    assert m.group("seq") == "1"
    assert m.group("body").startswith("STATUS machine=mh")
    assert lines[-1] == "DONE id=deadbeef exit=0"


def test_invoke_ps1_regex_literal_matches_status_shape():
    t = INV.read_text(encoding="utf-8-sig")
    assert r"^(?<stream>out|err)\s+id=(?<id>[0-9a-f]+)\s+seq=(?<seq>\d+)\s(?<body>.*)$" in t
    sample = "out id=aabbccdd seq=1 STATUS machine=tm airc=Running bob=1 airc_ver=1 jeeves=1"
    assert OUT_RE.match(sample)


def test_status_out_body_is_not_bare_status_prefix(tmp_path):
    """Regression of the live gap: bare STATUS lines never filled StdOut."""
    _versions(tmp_path)
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store, ai_root=tmp_path, machine="tm", airc_running=True)
    lines = proto.handle("bob-tm", "STATUS", {"id": "c25bd00e"})
    assert not lines[0].startswith("STATUS machine=")
    assert lines[0].startswith("out id=c25bd00e seq=1 STATUS machine=")
