"""FR #5534: VERSION includes BUILD.json / HOTPATCH.json commit and time."""
from __future__ import annotations

import json

import airc_jobs as jobs


def _proto(tmp_path, **kw):
    return jobs.JobProtocol(
        jobs.JobStore(tmp_path / "home"),
        ai_root=tmp_path,
        machine="marchhare",
        airc_running=True,
        **kw,
    )


def test_fr5534_version_includes_build_commit_and_time(tmp_path):
    airc = tmp_path / "airc"
    airc.mkdir()
    (airc / "VERSION").write_text("1.0.7\n", encoding="utf-8")
    (airc / "BUILD.json").write_text(
        json.dumps(
            {
                "product": "airc",
                "version": "1.0.7",
                "built_utc": "2026-10-31T20:14:00Z",
                "commit": "b79d1c641d3495a22459c1de3a4106fdb4b7c362",
            }
        ),
        encoding="utf-8",
    )
    lines = _proto(tmp_path).handle("bob-mh", "VERSION", {"id": "aabbccdd"})
    body = lines[0]
    assert "VERSION machine=marchhare airc_ver=1.0.7" in body
    assert "commit=b79d1c641d3495a22459c1de3a4106fdb4b7c362" in body
    assert "built=2026-10-31T20:14:00Z" in body
    assert lines[-1] == "DONE id=aabbccdd exit=0"
    assert "password" not in "\n".join(lines).lower()


def test_fr5534_hotpatch_overlays_commit(tmp_path):
    airc = tmp_path / "airc"
    airc.mkdir()
    (airc / "VERSION").write_text("1.0.7\n", encoding="utf-8")
    (airc / "BUILD.json").write_text(
        json.dumps({"commit": "aaaaaaaa", "built_utc": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    (airc / "HOTPATCH.json").write_text(
        json.dumps(
            {
                "commit": "bbbbbbbb",
                "built_utc": "2026-10-31T20:14:00Z",
            }
        ),
        encoding="utf-8",
    )
    lines = _proto(tmp_path).handle("bob-mh", "VERSION", {"id": "11223344"})
    body = lines[0]
    assert "commit=bbbbbbbb" in body
    assert "built=2026-01-01T00:00:00Z" in body
    assert "hotpatched=2026-10-31T20:14:00Z" in body
    assert "hotpatch=1" in body


def test_fr5534_no_build_json_omits_commit(tmp_path):
    airc = tmp_path / "airc"
    airc.mkdir()
    (airc / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    lines = _proto(tmp_path).handle("bob-mh", "VERSION", {"id": "c25bd00e"})
    assert "airc_ver=1.2.3" in lines[0]
    assert "commit=" not in lines[0]
    assert "built=" not in lines[0]


def test_fr5534_meta_sanitizes_spaces():
    meta = jobs.collect_airc_build_meta
    # helper used by format
    got = jobs.format_version_lines(
        versions={"airc": "1.0.7"},
        machine="tm",
        build={"commit": "dead bee", "built_utc": "2026-10-31T20:14:00Z extra"},
    )
    assert " " not in got[0].split("commit=", 1)[1].split()[0]
    assert "password" not in got[0].lower()
