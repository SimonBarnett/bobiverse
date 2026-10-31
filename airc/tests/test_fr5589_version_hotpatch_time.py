"""FR #5589: VERSION built= is BUILD.json time; hotpatched= is HOTPATCH time."""
from __future__ import annotations

import json

from pathlib import Path

import airc_jobs as jobs


def test_fr5589_hotpatched_utc_does_not_replace_built(tmp_path):
    airc = tmp_path / "airc"
    airc.mkdir()
    (airc / "VERSION").write_text("1.0.7\n", encoding="utf-8")
    (airc / "BUILD.json").write_text(
        json.dumps(
            {
                "commit": "oldoldold",
                "built_utc": "2026-10-28T10:46:54Z",
            }
        ),
        encoding="utf-8",
    )
    (airc / "HOTPATCH.json").write_text(
        json.dumps(
            {
                "commit": "f0cdf784ae9c3087e080497760f0f6a799502a98",
                "hotpatched_utc": "2026-10-31T22:18:11Z",
            }
        ),
        encoding="utf-8",
    )
    proto = jobs.JobProtocol(
        jobs.JobStore(tmp_path / "home"),
        ai_root=tmp_path,
        machine="marchhare",
        airc_running=True,
    )
    body = proto.handle("bob-mh", "VERSION", {"id": "aabbccdd"})[0]
    assert "built=2026-10-28T10:46:54Z" in body
    assert "hotpatched=2026-10-31T22:18:11Z" in body
    assert "hotpatch=1" in body
    assert "commit=f0cdf784ae9c3087e080497760f0f6a799502a98" in body
    assert "built=2026-10-31T22:18:11Z" not in body


def test_fr5589_legacy_hotpatch_built_utc_is_hotpatched_token(tmp_path):
    airc = tmp_path / "airc"
    airc.mkdir()
    (airc / "VERSION").write_text("1.0.7\n", encoding="utf-8")
    (airc / "BUILD.json").write_text(
        json.dumps({"commit": "aaaaaaaa", "built_utc": "2026-10-28T10:46:54Z"}),
        encoding="utf-8",
    )
    (airc / "HOTPATCH.json").write_text(
        json.dumps({"hotpatch_commit": "bbbbbbbb", "built_utc": "2026-10-31T22:18:11Z"}),
        encoding="utf-8",
    )
    meta = jobs.collect_airc_build_meta(tmp_path)
    assert meta["built_utc"] == "2026-10-28T10:46:54Z"
    assert meta["hotpatched_utc"] == "2026-10-31T22:18:11Z"
    assert meta["commit"] == "bbbbbbbb"
    line = jobs.format_version_lines(
        versions={"airc": "1.0.7"}, machine="mh", build=meta
    )[0]
    assert "built=2026-10-28T10:46:54Z" in line
    assert "hotpatched=2026-10-31T22:18:11Z" in line


def test_fr5589_pins():
    srcp = Path(jobs.__file__).resolve()
    src = srcp.read_text(encoding="utf-8")
    assert "FR #5589" in src
    assert "hotpatched=" in src
    assert "hotpatched_utc" in src
    docs = srcp.parents[1] / "docs" / "airc-remote-control.md"
    assert "hotpatched_utc" in docs.read_text(encoding="utf-8")
    assert not srcp.read_bytes().startswith(b"\xef\xbb\xbf")
