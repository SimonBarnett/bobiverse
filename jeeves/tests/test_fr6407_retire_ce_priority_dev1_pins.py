"""FR #6407: retire ce-priority-dev1 pins; !unpin/!pin survive resync."""
from __future__ import annotations

import gitclaim
import registered_machines


# Real titles/bodies from GitHub (acceptance).
_CE6_TITLE = (
    "FR: WP0 live §15 proof on CE-PRIORITY-DEV1 (shell compile/install) "
    "+ live formlimited_audit run"
)
_CE6_BODY = (
    "Moved from agentic_fomprep#56. "
    "PRIORITY_WP0_INSTANCE=ce-priority-dev. WP0 live proof. "
    "AllowedComputer: CE-PRIORITY-DEV1. Gate C leftover.\n"
    "require_machine: ce-priority-dev1\n"
)
_CE16_TITLE = "Day Works v1.3: finish WP3-WP4 and Gates C-G per dayworks/docs/vision.md"
_CE16_BODY = (
    "Vision pack for CE Day Works v1.3 on Priority ERP.\n"
    "Remaining: WP3, WP4, Gates C-G.\n"
)
_CE17_TITLE = (
    "dayworks: FR: WP3 ZCLA_ELEDITLOGREM + ZCLA_DWDESCREV detailed spec (unblock O1)"
)
_CE17_BODY = (
    "Gate C CASE/DOCNO/steps for UNPARK. Standing rules forbid inventing ENAMEs.\n"
)
_FOM56_TITLE = "FR: WP0 live §15 proof (shell compile/install on ce-priority-dev)"
_FOM56_BODY = "PRIORITY_WP0_INSTANCE=ce-priority-dev for shell compile. WP0 live."


def test_ce_priority_6_16_17_and_fomprep_56_infer_no_pin():
    cases = [
        ("SimonBarnett/ce-priority", "#6", _CE6_TITLE, _CE6_BODY, ["feature-request"]),
        ("SimonBarnett/ce-priority", "#16", _CE16_TITLE, _CE16_BODY, ["feature-request"]),
        ("SimonBarnett/ce-priority", "#17", _CE17_TITLE, _CE17_BODY, ["feature-request"]),
        (
            "SimonBarnett/agentic_fomprep",
            "#56",
            _FOM56_TITLE,
            _FOM56_BODY,
            ["feature-request"],
        ),
    ]
    for repo, ident, title, body, labels in cases:
        assert (
            gitclaim.infer_require_machine(
                title=title, body=body, labels=labels, repo=repo, ident=ident
            )
            == ""
        ), (repo, ident)
        row = {
            "repo": repo,
            "id": ident,
            "title": title,
            "body": body,
            "labels": labels,
            "task": "FR",
        }
        assert gitclaim.row_require_machine(row) == "", (repo, ident)


def test_needs_ce_priority_dev1_label_no_longer_pins():
    assert (
        gitclaim.infer_require_machine(
            title="Day Works follow-up",
            body="no machine name here",
            labels=["needs-ce-priority-dev1"],
            repo="SimonBarnett/ce-priority",
            ident="#99",
        )
        == ""
    )


def test_stamped_ce_priority_dev1_loads_as_any(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    path = gitclaim.queue_path(tmp_path)
    gitclaim._write_queue(
        path,
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/ce-priority",
                    "task": "FR",
                    "id": "#6",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/ce-priority#6",
                    "require_machine": "ce-priority-dev1",
                    "title": _CE6_TITLE,
                    "body": _CE6_BODY,
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    doc = gitclaim.load_queue(tmp_path)
    row = doc["unaccepted"][0]
    assert row.get("require_machine") == "any"
    assert gitclaim.row_require_machine(row) == ""
    # Persisted so a restart keeps any.
    reloaded = gitclaim._read_queue_file(path)
    assert reloaded["unaccepted"][0].get("require_machine") == "any"


def test_unpin_survives_resync_and_restamp(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "ionos", "marchhare"})
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/ce-priority",
                    "task": "FR",
                    "id": "#6",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/ce-priority#6",
                    "require_machine": "ce-priority-dev1",
                    "title": _CE6_TITLE,
                    "body": _CE6_BODY,
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    out = gitclaim.set_require_machine_job(tmp_path, "SimonBarnett/ce-priority", "#6", "any")
    assert out["ok"] is True
    assert out["require_machine"] == "any"
    row = gitclaim.load_unaccepted(tmp_path)[0]
    assert row["require_machine"] == "any"
    gitclaim._stamp_require_machine(row)
    assert row["require_machine"] == "any"
    assert gitclaim.row_require_machine(row) == ""

    def fetch(url: str):
        if "/pulls" in url:
            return []
        if "/issues" in url:
            return [
                {
                    "number": 6,
                    "title": _CE6_TITLE,
                    "body": _CE6_BODY,
                    "html_url": "https://github.com/SimonBarnett/ce-priority/issues/6",
                    "labels": [{"name": "feature-request"}],
                    "user": {"login": "u"},
                    "pull_request": None,
                    "state": "open",
                }
            ]
        return []

    gitclaim.resync_from_github(tmp_path, ["SimonBarnett/ce-priority"], fetch_json=fetch)
    rows = gitclaim.load_unaccepted(tmp_path)
    assert len(rows) == 1
    assert rows[0]["require_machine"] == "any"
    assert gitclaim.row_require_machine(rows[0]) == ""


def test_pin_sets_machine_and_survives_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/a-search",
                    "task": "FR",
                    "id": "#9",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/a-search#9",
                    "title": "docs only",
                    "body": "no pin cues",
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    out = gitclaim.set_require_machine_job(
        tmp_path, "SimonBarnett/a-search", "#9", "redqueen"
    )
    assert out["ok"] is True
    assert out["require_machine"] == "redqueen"
    row = gitclaim.load_unaccepted(tmp_path)[0]
    assert row["require_machine"] == "redqueen"
    gitclaim._stamp_require_machine(row)
    assert row["require_machine"] == "redqueen"
    assert gitclaim.row_require_machine(row) == "redqueen"


def test_parse_pin_unpin_cmds():
    assert gitclaim.parse_unpin_cmd("!unpin SimonBarnett/ce-priority#6") == (
        "SimonBarnett/ce-priority",
        "#6",
    )
    assert gitclaim.parse_unpin_cmd("!unpin o/a#1") == ("o/a", "#1")
    assert gitclaim.parse_unpin_cmd("!unpin") is None
    assert gitclaim.parse_pin_cmd("!pin SimonBarnett/a-search#9 redqueen") == (
        "SimonBarnett/a-search",
        "#9",
        "redqueen",
    )
    assert gitclaim.parse_pin_cmd("!pin o/a#1 ionos") == ("o/a", "#1", "ionos")
    assert gitclaim.parse_pin_cmd("!pin o/a#1") is None
    assert gitclaim.parse_pin_cmd("!unpin o/a#1") is None


def test_ionos_redqueen_marchhare_pins_still_work():
    assert (
        gitclaim.infer_require_machine(
            title="FR: install+smoke on ionos",
            body="require_machine: ionos\n",
            labels=["feature-request"],
            repo="SimonBarnett/bobiverse",
            ident="#99901",
        )
        == "ionos"
    )
    assert (
        gitclaim.infer_require_machine(
            title="a-hasresults-monitor redeploy",
            body="FilterLogEvents near a-search on walrus",
            labels=["feature-request"],
            repo="SimonBarnett/a-search",
            ident="#99902",
        )
        == "redqueen"
    )
    assert (
        gitclaim.infer_require_machine(
            title="",
            body="",
            labels=(),
            repo="SimonBarnett/bobiverse",
            ident="#6144",
        )
        == "marchhare"
    )


def test_unpin_does_not_override_remaining_hard_pin(tmp_path, monkeypatch):
    """Documented policy: operator any survives cues; remaining hard pins still win."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1714",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/bobiverse#1714",
                    "require_machine": "any",
                    "title": "",
                    "body": "",
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    row = gitclaim.load_unaccepted(tmp_path)[0]
    assert gitclaim.row_require_machine(row) == "ionos"
    gitclaim._stamp_require_machine(row)
    assert row.get("require_machine") == "ionos"
