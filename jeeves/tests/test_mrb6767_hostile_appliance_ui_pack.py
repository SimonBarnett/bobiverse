"""MRB #6767: Jeeves appliance UI pack is docs-only and stays LAN-closed."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "jeeves" / "docs" / "appliance-ui-20261112"
FR = ROOT / "jeeves" / "docs" / "feature-request-jeeves-appliance-ui-2026-11-12.md"
TRAY_LOGO = ROOT / "bob" / "tray" / "assets" / "ntsa-gut-logo.png"
PACK_LOGO = PACK / "mocks" / "ntsa-gut-logo.png"


def test_mrb6767_pack_files_and_issued_rows():
    assert FR.is_file()
    assert (PACK / "functional-spec.md").is_file()
    tsv = (PACK / "ISSUED.tsv").read_text(encoding="utf-8")
    assert tsv.encode("utf-8")[:3] != b"\xef\xbb\xbf"
    ids = []
    for line in tsv.splitlines():
        parts = line.split("\t")
        assert len(parts) >= 3
        ids.append(int(parts[1]))
        slice_id = parts[0]
        assert (PACK / "fr" / f"FR-{slice_id}.md").is_file()
    assert ids == list(range(6749, 6763))


def test_mrb6767_hold_draft_exists_and_is_unfiled():
    hold = PACK / "fr" / "HOLD-external-access.md"
    assert hold.is_file()
    text = hold.read_text(encoding="utf-8")
    assert "Do not open a GitHub issue" in text
    spec = (PACK / "functional-spec.md").read_text(encoding="utf-8")
    assert "fr/HOLD-external-access.md" in spec
    fr = FR.read_text(encoding="utf-8")
    assert "External access stays closed" in fr
    assert "bob.ntsa.uk" in fr
    assert "irc.ntsa.uk" in fr


def test_mrb6767_login_mock_one_account_no_port():
    login = (PACK / "mocks" / "login.html").read_text(encoding="utf-8")
    assert 'name="domain"' not in login
    assert ":7701" not in login
    assert 'name="username"' in login
    assert 'type="password"' in login
    err = (PACK / "mocks" / "error.html").read_text(encoding="utf-8")
    assert "password was not accepted" in err.lower() or "not accepted" in err.lower()
    assert "value=\"secret" not in err.lower()


def test_mrb6767_queue_empty_copy_and_whitelist_docs():
    empty = (PACK / "mocks" / "empty.html").read_text(encoding="utf-8")
    assert "Nothing is waiting." in empty
    assert "Nothing is in progress." in empty
    fr06 = (PACK / "fr" / "FR-06.md").read_text(encoding="utf-8")
    assert "GET /api/queue" in fr06
    assert "worker" in fr06
    spec = (PACK / "functional-spec.md").read_text(encoding="utf-8")
    assert "repo, task, id, and worker" in spec


def test_mrb6767_logo_bytes_match_tray_asset():
    assert TRAY_LOGO.is_file()
    assert PACK_LOGO.is_file()
    assert PACK_LOGO.read_bytes() == TRAY_LOGO.read_bytes()


def test_mrb6767_pools_mock_not_cursor_spending_group():
    html = (PACK / "mocks" / "pools.html").read_text(encoding="utf-8")
    assert "Copilot - 37% left" in html
    assert "overspend" in html.lower()
    assert "out of tokens" in html
    assert "[stale]" in html
    assert "n/a" in html
    assert "spending-group" not in html.lower()
    assert "cursor" not in html.lower()


def test_mrb6767_no_secret_shapes_in_pack_text():
    needles = ("bearer ", "ghs_", "password=", "gh_token=")
    for path in PACK.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png"}:
            continue
        raw = path.read_bytes()
        assert raw[:3] != b"\xef\xbb\xbf", path
        text = raw.decode("utf-8").lower()
        for bad in needles:
            assert bad not in text, f"{path}: {bad}"
