"""FR #5610: sandbox rejects Windows reserved device names before any I/O."""
from __future__ import annotations

import pytest

import airc_jobs as jobs


def test_fr5610_resolve_rejects_nul_and_com1_txt(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    for raw in ("NUL", "nul.txt", r"sub\COM1.txt", "COM1", "LPT1.log", "AUX", "PRN", "CON"):
        with pytest.raises(jobs.JobProtocolError) as ei:
            jobs.resolve_sandbox_path(drop, raw)
        assert ei.value.code == "bad_path"
        assert "reserved device name" in str(ei.value)


def test_fr5610_put_nul_does_not_create_file(tmp_path):
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store)
    line = proto.handle(
        "bob-tm",
        "PUT",
        {"path": "NUL", "id": "ab7a4c9b", "bytes": "10", "sha256": "a" * 64},
    )[0]
    assert "err" in line
    assert "bad_path" in line
    assert "reserved device name" in line
    assert not list(store.drop_root.rglob("*")) or all(
        p.is_dir() for p in store.drop_root.rglob("*")
    )


def test_fr5610_put_com1_txt_subdir_no_write(tmp_path):
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store)
    line = proto.handle(
        "bob-tm",
        "PUT",
        {"path": r"sub\COM1.txt", "id": "616ff661", "bytes": "10", "sha256": "b" * 64},
    )[0]
    assert "bad_path" in line
    assert "reserved device name" in line
    assert not (store.drop_root / "sub").exists()


def test_fr5610_safe_name_still_resolves(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    dest = jobs.resolve_sandbox_path(drop, "notes.txt")
    assert dest == (drop / "notes.txt").resolve()
    dest2 = jobs.resolve_sandbox_path(drop, r"sub\combo.txt")
    assert dest2 == (drop / "sub" / "combo.txt").resolve()
