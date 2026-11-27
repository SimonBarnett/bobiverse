"""FR #10013: remaining=0 skips Copilot GitHub GETs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import chair_health as ch  # noqa: E402


class _Chair:
    digest_home = None
    home = None
    clock = staticmethod(lambda: 0.0)
    log = staticmethod(lambda _s: None)

    def token_loader(self):
        return "example-token", "test"


def test_fr10013_remaining_zero_skips_copilot_get(tmp_path, monkeypatch):
    (tmp_path / "github-api-budget.json").write_text(
        json.dumps(
            {
                "v": 1,
                "hour": int(0),
                "used": 0,
                "rate_remaining": 0,
                "rate_reset": 9e12,
            }
        ),
        encoding="utf-8",
    )
    # Keep the stored hour aligned with the chair clock (0) via budget clock default.
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("copilot_internal")),
    )
    job = _Chair()
    job.digest_home = tmp_path
    job.home = tmp_path
    # Bind unbound method.
    ch.ChairJobs._copilot_tick(job)
    docs = (ROOT / "jeeves" / "docs" / "jeeves-commands.md").read_text(encoding="utf-8")
    assert "FR #10013" in docs
