"""FR #10008: remaining=0 stops chair REST callers."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bobreport  # noqa: E402
import chair_health as ch  # noqa: E402
import gitclaim  # noqa: E402


def _pause(home: Path) -> None:
    (home / "github-api-budget.json").write_text(
        json.dumps({"v": 1, "hour": 0, "used": 0, "rate_remaining": 0, "rate_reset": 9e12}),
        encoding="utf-8",
    )


def test_fr10008_remaining_zero_no_urlopen(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _pause(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "task": "FR",
                    "id": "#1",
                    "repo": "SimonBarnett/bobiverse",
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("urlopen")),
    )
    q = bobreport._public_queue(tmp_path)
    assert q["unaccepted"]
    out = ch.run_ticket_closure_cycle(chair_home=tmp_path, digest_home=tmp_path)
    assert out.get("skipped") == "github-backoff"

    class _Chair:
        digest_home = tmp_path
        home = tmp_path
        log = staticmethod(lambda _s: None)
        clock = staticmethod(lambda: 0.0)

        def token_loader(self):
            return "example-token", "test"

    ch.ChairJobs._copilot_tick(_Chair())
