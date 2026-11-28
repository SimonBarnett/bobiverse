"""FR #10010: _public_queue survives a boom urlopen."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bobreport  # noqa: E402
import gitclaim  # noqa: E402


def test_fr10010_public_queue_no_urlopen(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
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
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("github")),
    )
    q = bobreport._public_queue(tmp_path)
    assert q["unaccepted"][0]["id"] == "#1"
